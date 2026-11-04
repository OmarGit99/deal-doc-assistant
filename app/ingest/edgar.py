"""Polite, cached downloads of merger-agreement exhibits from SEC EDGAR."""

import csv
import hashlib
import json
import os
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Self
from urllib.parse import urlparse

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from app.text import decode_html, normalize, strip_html

EDGAR_ARCHIVES = "https://www.sec.gov/Archives/edgar/data/"
TITLE_MARKER = "AGREEMENT AND PLAN OF MERGER"
MIN_TEXT_CHARS = 20_000  # real agreements are 150k+ characters; error pages are tiny
RETRY_STATUSES = frozenset({429, 500, 502, 503, 504})
USER_AGENT_ENV = "EDGAR_USER_AGENT"


class SeedError(Exception):
    """The seed CSV has bad rows. The message lists every problem with its line number."""


class ExhibitError(Exception):
    """A single deal's exhibit could not be downloaded or failed validation."""

    def __init__(self, deal_id: str, reason: str) -> None:
        super().__init__(f"{deal_id}: {reason}")
        self.deal_id = deal_id
        self.reason = reason


class SeedDeal(BaseModel):
    """One row of scripts/seed_deals.csv, checked on load."""

    model_config = ConfigDict(frozen=True, str_strip_whitespace=True)

    deal_id: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    target: str = Field(min_length=1)
    acquirer: str = Field(min_length=1)
    announcement_date: date
    form: str = Field(min_length=1)
    accession_number: str = Field(pattern=r"^\d{10}-\d{2}-\d{6}$")
    exhibit_url: str
    notes: str = ""
    preamble_target: str = ""
    preamble_acquirer: str = ""
    filing_note: str = ""

    @field_validator("exhibit_url")
    @classmethod
    def _url_is_edgar_archive(cls, value: str) -> str:
        if not value.startswith(EDGAR_ARCHIVES):
            raise ValueError(f"must start with {EDGAR_ARCHIVES}")
        return value

    @model_validator(mode="after")
    def _url_matches_accession(self) -> Self:
        # The archive folder is the accession number without dashes. A mismatch means
        # the URL was copied from a different filing.
        folder = self.accession_number.replace("-", "")
        if f"/{folder}/" not in self.exhibit_url:
            raise ValueError(f"exhibit_url is not inside accession folder {folder}")
        return self

    @property
    def filename(self) -> str:
        return Path(urlparse(self.exhibit_url).path).name


@dataclass(frozen=True)
class FetchResult:
    deal_id: str
    path: Path
    downloaded: bool  # False when served from the cache
    sha256: str
    size: int


def load_seed(path: Path) -> list[SeedDeal]:
    """Load and validate every row; report all bad rows at once."""
    deals: list[SeedDeal] = []
    errors: list[str] = []
    seen: dict[str, int] = {}
    # utf-8-sig strips the byte-order mark Excel adds when saving CSV on Windows.
    with path.open(newline="", encoding="utf-8-sig") as handle:
        for line_no, row in enumerate(csv.DictReader(handle), start=2):
            cleaned = {key: value or "" for key, value in row.items() if key is not None}
            try:
                deal = SeedDeal.model_validate(cleaned)
            except ValidationError as exc:
                problems = "; ".join(
                    f"{'.'.join(str(p) for p in err['loc']) or 'row'}: {err['msg']}"
                    for err in exc.errors()
                )
                errors.append(f"line {line_no}: {problems}")
                continue
            if deal.deal_id in seen:
                errors.append(
                    f"line {line_no}: duplicate deal_id {deal.deal_id!r} "
                    f"(first on line {seen[deal.deal_id]})"
                )
                continue
            seen[deal.deal_id] = line_no
            deals.append(deal)
    if errors:
        raise SeedError("\n".join(errors))
    return deals


def user_agent_from_env() -> str:
    """The SEC requires a User-Agent with a name and contact email."""
    value = os.environ.get(USER_AGENT_ENV, "").strip()
    if "@" not in value or " " not in value:
        raise RuntimeError(
            f"Set {USER_AGENT_ENV} to 'Your Name your@email' in .env, "
            "then run with: uv run --env-file .env ..."
        )
    return value


def build_client(user_agent: str, transport: httpx.BaseTransport | None = None) -> httpx.Client:
    return httpx.Client(
        headers={"User-Agent": user_agent, "Accept-Encoding": "gzip, deflate"},
        timeout=httpx.Timeout(30.0),
        follow_redirects=True,
        transport=transport,
    )


def validate_exhibit_text(text: str, deal_id: str) -> None:
    """Raise if the content does not look like a merger agreement."""
    plain = normalize(strip_html(text))
    if len(plain) < MIN_TEXT_CHARS:
        raise ExhibitError(deal_id, f"only {len(plain):,} characters of text; too short")
    if TITLE_MARKER not in plain.upper():
        raise ExhibitError(deal_id, f"text does not contain {TITLE_MARKER!r}")


def _get_with_retries(
    client: httpx.Client,
    url: str,
    deal_id: str,
    *,
    max_retries: int,
    backoff: float,
    sleep: Callable[[float], None],
) -> bytes:
    last_problem = "no attempts made"
    for attempt in range(max_retries + 1):
        try:
            response = client.get(url)
        except httpx.TransportError as exc:
            last_problem = f"network error: {exc!r}"
        else:
            if response.status_code == 200:
                return response.content
            if response.status_code == 403:
                raise ExhibitError(
                    deal_id,
                    "HTTP 403: the SEC refused the request. Check EDGAR_USER_AGENT; if it is "
                    "set correctly you may be rate-limited, so wait 10 minutes.",
                )
            if response.status_code not in RETRY_STATUSES:
                raise ExhibitError(deal_id, f"HTTP {response.status_code} for {url}")
            last_problem = f"HTTP {response.status_code}"
        if attempt < max_retries:
            sleep(backoff * 2**attempt)
    raise ExhibitError(deal_id, f"gave up after {max_retries + 1} attempts ({last_problem})")


def _write_atomic(path: Path, data: bytes) -> None:
    """Write to a temporary file, then swap it in, so a crash never leaves half a file."""
    tmp = path.with_name(path.name + ".part")
    tmp.write_bytes(data)
    tmp.replace(path)  # os.replace: atomic, and overwrites on Windows unlike rename()


def fetch_exhibit(
    client: httpx.Client,
    deal: SeedDeal,
    raw_dir: Path,
    *,
    force: bool = False,
    max_retries: int = 3,
    backoff: float = 1.0,
    sleep: Callable[[float], None] = time.sleep,
) -> FetchResult:
    """Return the cached exhibit for `deal`, downloading it only if needed."""
    deal_dir = raw_dir / deal.deal_id
    path = deal_dir / deal.filename

    if path.exists() and not force:
        content = path.read_bytes()
        validate_exhibit_text(decode_html(content), deal.deal_id)
        return FetchResult(
            deal.deal_id, path, False, hashlib.sha256(content).hexdigest(), len(content)
        )

    content = _get_with_retries(
        client,
        deal.exhibit_url,
        deal.deal_id,
        max_retries=max_retries,
        backoff=backoff,
        sleep=sleep,
    )
    # Validate before writing, so a bad response is never cached.
    validate_exhibit_text(decode_html(content), deal.deal_id)

    digest = hashlib.sha256(content).hexdigest()
    deal_dir.mkdir(parents=True, exist_ok=True)
    _write_atomic(path, content)
    meta = {
        "deal_id": deal.deal_id,
        "url": deal.exhibit_url,
        "accession_number": deal.accession_number,
        "sha256": digest,
        "bytes": len(content),
        "fetched_at": datetime.now(UTC).isoformat(timespec="seconds"),
    }
    _write_atomic(deal_dir / "meta.json", json.dumps(meta, indent=2).encode("utf-8"))
    return FetchResult(deal.deal_id, path, True, digest, len(content))


def cached_exhibit_path(deal: SeedDeal, raw_dir: Path) -> Path:
    return raw_dir / deal.deal_id / deal.filename
