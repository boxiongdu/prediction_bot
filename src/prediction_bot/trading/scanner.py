"""
Market scanner — fetches all open Kalshi markets with full pagination.

Uses mve_filter=exclude to skip multi-event parlays, then filters
by ticker prefix (KXLOL*) in the filter module.

Records every market in DiscoveryLedger with query parameters, contract
classification, and rejection reasons for full auditability.
"""
from __future__ import annotations

import logging
import sqlite3
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────────
# Discovery ledger
# ──────────────────────────────────────────────────────────────────────

CREATE_DISCOVERY_SQL = """
CREATE TABLE IF NOT EXISTS market_discovery (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker          TEXT    NOT NULL,
    event_ticker    TEXT,
    title           TEXT,
    category        TEXT,
    close_time      TEXT,
    contract_type   TEXT,
    game            TEXT,
    tournament      TEXT,
    league_tier     TEXT,
    filter_status   TEXT    NOT NULL,
    reject_reason   TEXT,
    yes_bid         REAL,
    yes_ask         REAL,
    volume          REAL,
    query_params    TEXT,
    scan_id         TEXT    NOT NULL,
    scanned_at      TEXT    NOT NULL
);
"""

INSERT_DISCOVERY_SQL = """
INSERT INTO market_discovery (
    ticker, event_ticker, title, category, close_time,
    contract_type, game, tournament, league_tier,
    filter_status, reject_reason,
    yes_bid, yes_ask, volume,
    query_params, scan_id, scanned_at
) VALUES (
    :ticker, :event_ticker, :title, :category, :close_time,
    :contract_type, :game, :tournament, :league_tier,
    :filter_status, :reject_reason,
    :yes_bid, :yes_ask, :volume,
    :query_params, :scan_id, :scanned_at
);
"""


class DiscoveryLedger:
    """Records every market seen during scanning, pass or fail."""

    def __init__(self, db_path: str = "data/market_discovery.db") -> None:
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self._db_path))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(CREATE_DISCOVERY_SQL)
            conn.commit()

    def record(
        self,
        market: dict[str, Any],
        scan_id: str,
        query_params: str = "",
        filter_status: str = "pending",
        reject_reason: str = "",
        contract_type: str = "",
        game: str = "",
        tournament: str = "",
        league_tier: str = "",
    ) -> None:
        """Record a market in the discovery ledger."""
        from prediction_bot.data.schema import _parse_fp_quantity, _parse_price_dollars

        with self._connect() as conn:
            conn.execute(
                INSERT_DISCOVERY_SQL,
                {
                    "ticker": market.get("ticker", ""),
                    "event_ticker": market.get("event_ticker", ""),
                    "title": market.get("title", ""),
                    "category": market.get("category", ""),
                    "close_time": str(market.get("close_time", "")),
                    "contract_type": contract_type,
                    "game": game,
                    "tournament": tournament or "",
                    "league_tier": league_tier,
                    "filter_status": filter_status,
                    "reject_reason": reject_reason,
                    "yes_bid": float(
                        _parse_price_dollars(market.get("yes_bid_dollars")) or 0
                    ),
                    "yes_ask": float(
                        _parse_price_dollars(market.get("yes_ask_dollars")) or 0
                    ),
                    "volume": float(
                        _parse_fp_quantity(market.get("volume_fp")) or 0
                    ),
                    "query_params": query_params,
                    "scan_id": scan_id,
                    "scanned_at": datetime.now(timezone.utc).isoformat(),
                },
            )
            conn.commit()

    def summary(self, scan_id: str) -> dict[str, Any]:
        """Get discovery summary for a scan."""
        with self._connect() as conn:
            total = conn.execute(
                "SELECT COUNT(*) as cnt FROM market_discovery WHERE scan_id=?",
                (scan_id,),
            ).fetchone()["cnt"]
            passed = conn.execute(
                "SELECT COUNT(*) as cnt FROM market_discovery"
                " WHERE scan_id=? AND filter_status='passed'",
                (scan_id,),
            ).fetchone()["cnt"]
            rejected = conn.execute(
                "SELECT COUNT(*) as cnt FROM market_discovery"
                " WHERE scan_id=? AND filter_status='rejected'",
                (scan_id,),
            ).fetchone()["cnt"]

            reasons = conn.execute(
                """SELECT reject_reason, COUNT(*) as cnt
                   FROM market_discovery
                   WHERE scan_id=? AND filter_status='rejected'
                   GROUP BY reject_reason
                   ORDER BY cnt DESC""",
                (scan_id,),
            ).fetchall()

            return {
                "total": total,
                "passed": passed,
                "rejected": rejected,
                "rejection_reasons": {
                    r["reject_reason"]: r["cnt"] for r in reasons
                },
            }


# ──────────────────────────────────────────────────────────────────────
# Scanner
# ──────────────────────────────────────────────────────────────────────


@dataclass
class ScanResult:
    """Result of a market scan."""
    scan_id: str
    markets: list[dict[str, Any]]
    total_scanned: int
    query_params: str
    discovery_summary: dict[str, Any]


def scan_lol_markets(
    client=None,
    max_pages: int | None = None,
    discovery_db: str = "data/market_discovery.db",
) -> ScanResult:
    """Scan open Kalshi markets, filtered to KXLOL (LoL esports) tickers.

    Fetches all open markets with mve_filter=exclude using full cursor
    pagination. The KXLOL ticker-prefix filter is applied in filter.py.

    All markets are recorded in the discovery ledger before filtering.

    Args:
        client: Optional KalshiClient.
        max_pages: Max pages (None = scan until exhausted).
        discovery_db: Path to discovery SQLite database.

    Returns:
        ScanResult with raw markets and discovery summary.
    """
    from prediction_bot.kalshi.client import KalshiClient

    if client is None:
        client = KalshiClient()

    scan_id = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    query_params = "status=open&series_ticker=KXLOLGAME&mve_filter=exclude"
    ledger = DiscoveryLedger(discovery_db)
    all_markets: list[dict[str, Any]] = []
    cursor: str | None = None
    page = 0

    try:
        while True:
            if max_pages is not None and page >= max_pages:
                break

            resp = client.get_markets(
                status="open",
                limit=100,
                cursor=cursor,
                series_ticker="KXLOLGAME",
                mve_filter="exclude",
            )
            markets = resp.get("markets", [])
            all_markets.extend(markets)

            # All markets are already KXLOL (API-filtered)
            for m in markets:
                ledger.record(
                    m, scan_id,
                    query_params=query_params,
                    filter_status="pending",
                )

            cursor = resp.get("cursor")
            page += 1

            if page % 5 == 0:
                logger.info(
                    "KXLOLGAME scan page %d: %d markets (cursor=%s)",
                    page, len(all_markets),
                    str(cursor)[:30] if cursor else "None",
                )

            if not cursor or not markets:
                logger.info(
                    "KXLOLGAME scan complete: %d pages, %d markets",
                    page, len(all_markets),
                )
                break

            time.sleep(0.15)

    finally:
        client.close()

    summary = ledger.summary(scan_id)

    logger.info(
        "Scan complete: %d KXLOL markets. Reasons: %s",
        len(all_markets),
        summary["rejection_reasons"],
    )

    return ScanResult(
        scan_id=scan_id,
        markets=all_markets,
        total_scanned=len(all_markets),
        query_params=query_params,
        discovery_summary=summary,
    )
