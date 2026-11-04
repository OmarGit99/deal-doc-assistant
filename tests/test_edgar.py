import json
from datetime import date
from pathlib import Path

import httpx
import pytest

from app.ingest.edgar import (
    ExhibitError,
    SeedDeal,
    SeedError,
    build_client,
    fetch_exhibit,
    load_seed,
)

URL = "https://www.sec.gov/Archives/edgar/data/1043604/000119312524005659/d107225dex21.htm"
AGREEMENT = (
    "<html><body><p>AGREEMENT AND PLAN OF MERGER</p>"
    + "<p>Section 1.01. Definitions. The Company shall pay the fee.</p>" * 600
    + "</body></html>"
).encode()

CSV_HEADER = "deal_id,target,acquirer,announcement_date,form,accession_number,exhibit_url,notes\n"
GOOD_ROW = f"juniper-hpe-2024,Juniper,HPE,2024-01-09,8-K,0001193125-24-005659,{URL},\n"


def make_deal() -> SeedDeal:
    return SeedDeal(
        deal_id="juniper-hpe-2024",
        target="Juniper Networks, Inc.",
        acquirer="Hewlett Packard Enterprise Company",
        announcement_date=date(2024, 1, 9),
        form="8-K",
        accession_number="0001193125-24-005659",
        exhibit_url=URL,
    )


class FakeSec:
    """Plays back a list of responses and records every request."""

    def __init__(self, *responses: httpx.Response) -> None:
        self.responses = list(responses)
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        return self.responses.pop(0)

    def client(self) -> httpx.Client:
        return build_client("Test Runner test@example.com", httpx.MockTransport(self))


def no_sleep(_: float) -> None:
    pass


# --- fetch_exhibit ------------------------------------------------------------------


def test_downloads_once_then_serves_from_cache(tmp_path: Path) -> None:
    sec = FakeSec(httpx.Response(200, content=AGREEMENT))
    with sec.client() as client:
        first = fetch_exhibit(client, make_deal(), tmp_path, sleep=no_sleep)
        second = fetch_exhibit(client, make_deal(), tmp_path, sleep=no_sleep)

    assert first.downloaded and not second.downloaded
    assert len(sec.requests) == 1
    assert first.path.read_bytes() == AGREEMENT
    assert first.sha256 == second.sha256


def test_sends_declared_user_agent(tmp_path: Path) -> None:
    sec = FakeSec(httpx.Response(200, content=AGREEMENT))
    with sec.client() as client:
        fetch_exhibit(client, make_deal(), tmp_path, sleep=no_sleep)
    assert sec.requests[0].headers["User-Agent"] == "Test Runner test@example.com"


def test_writes_metadata_next_to_the_file(tmp_path: Path) -> None:
    sec = FakeSec(httpx.Response(200, content=AGREEMENT))
    with sec.client() as client:
        result = fetch_exhibit(client, make_deal(), tmp_path, sleep=no_sleep)

    meta = json.loads((tmp_path / "juniper-hpe-2024" / "meta.json").read_text())
    assert meta["sha256"] == result.sha256
    assert meta["url"] == URL
    assert meta["bytes"] == len(AGREEMENT)


def test_403_fails_immediately_without_retrying(tmp_path: Path) -> None:
    sec = FakeSec(httpx.Response(403))
    with sec.client() as client, pytest.raises(ExhibitError) as info:
        fetch_exhibit(client, make_deal(), tmp_path, sleep=no_sleep)

    assert info.value.deal_id == "juniper-hpe-2024"
    assert "403" in info.value.reason
    assert len(sec.requests) == 1


def test_retries_server_errors_with_backoff(tmp_path: Path) -> None:
    sec = FakeSec(httpx.Response(503), httpx.Response(429), httpx.Response(200, content=AGREEMENT))
    waits: list[float] = []
    with sec.client() as client:
        result = fetch_exhibit(client, make_deal(), tmp_path, backoff=1.0, sleep=waits.append)

    assert result.downloaded
    assert waits == [1.0, 2.0]  # exponential: 1s, then 2s


def test_gives_up_after_max_retries(tmp_path: Path) -> None:
    sec = FakeSec(*[httpx.Response(503) for _ in range(3)])
    with sec.client() as client, pytest.raises(ExhibitError, match="gave up after 3 attempts"):
        fetch_exhibit(client, make_deal(), tmp_path, max_retries=2, sleep=no_sleep)


def test_rejects_a_page_that_is_not_an_agreement(tmp_path: Path) -> None:
    sec = FakeSec(httpx.Response(200, content=b"<html>Page not found</html>"))
    with sec.client() as client, pytest.raises(ExhibitError):
        fetch_exhibit(client, make_deal(), tmp_path, sleep=no_sleep)

    # Nothing was cached, not even a half-written temp file.
    assert not (tmp_path / "juniper-hpe-2024").exists()


def test_force_downloads_again(tmp_path: Path) -> None:
    sec = FakeSec(httpx.Response(200, content=AGREEMENT), httpx.Response(200, content=AGREEMENT))
    with sec.client() as client:
        fetch_exhibit(client, make_deal(), tmp_path, sleep=no_sleep)
        again = fetch_exhibit(client, make_deal(), tmp_path, force=True, sleep=no_sleep)
    assert again.downloaded
    assert len(sec.requests) == 2


# --- load_seed ----------------------------------------------------------------------


def write_csv(tmp_path: Path, body: str, *, bom: bool = False) -> Path:
    path = tmp_path / "seed.csv"
    path.write_text(CSV_HEADER + body, encoding="utf-8-sig" if bom else "utf-8")
    return path


def test_loads_a_valid_row_even_with_excel_bom(tmp_path: Path) -> None:
    deals = load_seed(write_csv(tmp_path, GOOD_ROW, bom=True))
    assert [d.deal_id for d in deals] == ["juniper-hpe-2024"]
    assert deals[0].filename == "d107225dex21.htm"


def test_reports_bad_rows_with_line_numbers(tmp_path: Path) -> None:
    bad = "Juniper HPE,Juniper,HPE,2024-13-40,8-K,123,https://example.com/x.htm,\n"
    with pytest.raises(SeedError) as info:
        load_seed(write_csv(tmp_path, GOOD_ROW + bad))
    message = str(info.value)
    assert message.startswith("line 3:")
    for field in ("deal_id", "announcement_date", "accession_number", "exhibit_url"):
        assert field in message


def test_rejects_url_from_a_different_filing(tmp_path: Path) -> None:
    wrong = GOOD_ROW.replace("0001193125-24-005659", "0001193125-24-999999")
    with pytest.raises(SeedError, match="accession folder"):
        load_seed(write_csv(tmp_path, wrong))


def test_rejects_duplicate_deal_ids(tmp_path: Path) -> None:
    with pytest.raises(SeedError, match="duplicate deal_id"):
        load_seed(write_csv(tmp_path, GOOD_ROW + GOOD_ROW))
