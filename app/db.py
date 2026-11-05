"""Postgres connection and the deals table."""

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date

from sqlalchemy import Engine, create_engine, text

DEALS_DDL = """
CREATE TABLE IF NOT EXISTS deals (
    deal_id           TEXT PRIMARY KEY,
    target            TEXT NOT NULL,
    acquirer          TEXT NOT NULL,
    announcement_date DATE NOT NULL,
    source_url        TEXT NOT NULL,
    preamble_target   TEXT NOT NULL DEFAULT '',
    preamble_acquirer TEXT NOT NULL DEFAULT '',
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT now()
)
"""

UPSERT_DEAL = """
INSERT INTO deals (deal_id, target, acquirer, announcement_date, source_url,
                   preamble_target, preamble_acquirer)
VALUES (:deal_id, :target, :acquirer, :announcement_date, :source_url,
        :preamble_target, :preamble_acquirer)
ON CONFLICT (deal_id) DO UPDATE SET
    target = EXCLUDED.target,
    acquirer = EXCLUDED.acquirer,
    announcement_date = EXCLUDED.announcement_date,
    source_url = EXCLUDED.source_url,
    preamble_target = EXCLUDED.preamble_target,
    preamble_acquirer = EXCLUDED.preamble_acquirer,
    updated_at = now()
"""


@dataclass(frozen=True)
class DealRow:
    deal_id: str
    target: str
    acquirer: str
    announcement_date: date
    source_url: str
    preamble_target: str = ""
    preamble_acquirer: str = ""


def make_engine(database_url: str) -> Engine:
    # pool_pre_ping replaces connections that died while idle (Cloud SQL closes them).
    return create_engine(database_url, pool_pre_ping=True)


def ensure_deals_table(engine: Engine) -> None:
    with engine.begin() as conn:
        conn.execute(text(DEALS_DDL))


def upsert_deals(engine: Engine, deals: Iterable[DealRow]) -> int:
    rows = [deal.__dict__ for deal in deals]
    if rows:
        with engine.begin() as conn:
            conn.execute(text(UPSERT_DEAL), rows)
    return len(rows)


def list_deals(engine: Engine) -> list[DealRow]:
    with engine.connect() as conn:
        result = conn.execute(
            text(
                "SELECT deal_id, target, acquirer, announcement_date, source_url, "
                "preamble_target, preamble_acquirer FROM deals ORDER BY announcement_date DESC"
            )
        )
        return [DealRow(*row) for row in result]
