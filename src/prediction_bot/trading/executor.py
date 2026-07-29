"""
Dry-run order executor — simulates fills against the Kalshi order book.

OrderProposal → RiskManager → DryRunExecutor.simulate_fill_against_book()
→ ExecutionLedger

Uses the order book simulator to compute realistic fills with slippage
and partial fills.
"""
from __future__ import annotations

import json
import logging
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from prediction_bot.kalshi.orderbooks import OrderBook

logger = logging.getLogger(__name__)


@dataclass
class OrderProposal:
    """A proposed trade before risk checks."""
    ticker: str
    event_ticker: str
    side: str
    size: float
    limit_price: float
    model_prob: float
    expected_edge: float
    team_a: str = ""
    team_b: str = ""
    predicted_winner: str = ""
    best_ask: float | None = None
    best_bid: float | None = None
    spread: float | None = None
    ask_depth: float = 0.0
    timestamp: str = ""


@dataclass
class OrderSimulation:
    """Result of a simulated order."""
    proposal: OrderProposal
    status: str
    fill_price: float | None = None
    fill_size: float | None = None
    unfilled_size: float = 0.0
    average_price: float | None = None
    total_cost: float = 0.0
    slippage_bps: float = 0.0
    levels_consumed: int = 0
    rejection_reason: str = ""
    risk_flags: list[str] = field(default_factory=list)
    sim_id: str = ""
    timestamp: str = ""


CREATE_EXECUTION_SQL = """
CREATE TABLE IF NOT EXISTS execution_ledger (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    sim_id          TEXT    NOT NULL,
    ticker          TEXT    NOT NULL,
    event_ticker    TEXT,
    side            TEXT    NOT NULL,
    proposed_size   REAL    NOT NULL,
    limit_price     REAL    NOT NULL,
    fill_price      REAL,
    fill_size       REAL,
    unfilled_size   REAL    DEFAULT 0,
    average_price   REAL,
    total_cost      REAL    DEFAULT 0,
    slippage_bps    REAL    DEFAULT 0,
    levels_consumed INTEGER DEFAULT 0,
    best_ask        REAL,
    best_bid        REAL,
    spread          REAL,
    ask_depth       REAL    DEFAULT 0,
    model_prob      REAL    NOT NULL,
    expected_edge   REAL    NOT NULL,
    status          TEXT    NOT NULL,
    rejection_reason TEXT,
    risk_flags      TEXT,
    team_a          TEXT,
    team_b          TEXT,
    predicted_winner TEXT,
    timestamp       TEXT    NOT NULL,
    settled         INTEGER DEFAULT 0,
    settlement_value REAL,
    pnl             REAL
);
"""

INSERT_EXECUTION_SQL = """
INSERT INTO execution_ledger (
    sim_id, ticker, event_ticker, side, proposed_size, limit_price,
    fill_price, fill_size, unfilled_size, average_price, total_cost,
    slippage_bps, levels_consumed,
    best_ask, best_bid, spread, ask_depth,
    model_prob, expected_edge,
    status, rejection_reason, risk_flags,
    team_a, team_b, predicted_winner,
    timestamp, settled
) VALUES (
    :sim_id, :ticker, :event_ticker, :side, :proposed_size, :limit_price,
    :fill_price, :fill_size, :unfilled_size, :average_price, :total_cost,
    :slippage_bps, :levels_consumed,
    :best_ask, :best_bid, :spread, :ask_depth,
    :model_prob, :expected_edge,
    :status, :rejection_reason, :risk_flags,
    :team_a, :team_b, :predicted_winner,
    :timestamp, :settled
);
"""


class ExecutionLedger:
    """Records all simulated orders with fill details."""

    def __init__(self, db_path: str = "data/execution_ledger.db") -> None:
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
            conn.execute(CREATE_EXECUTION_SQL)
            conn.commit()

    def record(self, sim: OrderSimulation) -> int:
        p = sim.proposal
        with self._connect() as conn:
            cursor = conn.execute(
                INSERT_EXECUTION_SQL,
                {
                    "sim_id": sim.sim_id,
                    "ticker": p.ticker,
                    "event_ticker": p.event_ticker,
                    "side": p.side,
                    "proposed_size": p.size,
                    "limit_price": p.limit_price,
                    "fill_price": sim.fill_price,
                    "fill_size": sim.fill_size,
                    "unfilled_size": sim.unfilled_size,
                    "average_price": sim.average_price,
                    "total_cost": sim.total_cost,
                    "slippage_bps": sim.slippage_bps,
                    "levels_consumed": sim.levels_consumed,
                    "best_ask": p.best_ask,
                    "best_bid": p.best_bid,
                    "spread": p.spread,
                    "ask_depth": p.ask_depth,
                    "model_prob": p.model_prob,
                    "expected_edge": p.expected_edge,
                    "status": sim.status,
                    "rejection_reason": sim.rejection_reason,
                    "risk_flags": json.dumps(sim.risk_flags),
                    "team_a": p.team_a,
                    "team_b": p.team_b,
                    "predicted_winner": p.predicted_winner,
                    "timestamp": sim.timestamp,
                    "settled": 0,
                },
            )
            conn.commit()
            return cursor.lastrowid or 0

    def summary(self) -> dict[str, Any]:
        with self._connect() as conn:
            total = conn.execute(
                "SELECT COUNT(*) as cnt FROM execution_ledger"
            ).fetchone()["cnt"]
            filled = conn.execute(
                "SELECT COUNT(*) as cnt FROM execution_ledger WHERE status='filled'"
            ).fetchone()["cnt"]
            partial = conn.execute(
                "SELECT COUNT(*) as cnt FROM execution_ledger WHERE status='partial_fill'"
            ).fetchone()["cnt"]
            rejected = conn.execute(
                "SELECT COUNT(*) as cnt FROM execution_ledger WHERE status IN ('rejected','no_liquidity')"
            ).fetchone()["cnt"]
            total_cost = conn.execute(
                "SELECT COALESCE(SUM(total_cost),0) as s FROM execution_ledger"
            ).fetchone()["s"]
            return {
                "total_orders": total,
                "filled": filled,
                "partial_fills": partial,
                "rejected": rejected,
                "total_notional": float(total_cost),
            }


class DryRunExecutor:
    """Simulates order execution against the Kalshi order book."""

    def __init__(self, ledger_path: str = "data/execution_ledger.db") -> None:
        self.ledger = ExecutionLedger(ledger_path)
        self._sim_counter = 0

    def simulate_fill_against_book(
        self,
        proposal: OrderProposal,
        order_book: OrderBook | None = None,
    ) -> OrderSimulation:
        """Simulate filling an order against the order book.

        Uses the multi-level fill simulator for realistic execution.
        Falls back to a simple fill-at-best-ask if no OB provided.
        """
        from prediction_bot.trading.orderbook import simulate_fill

        self._sim_counter += 1
        sim_id = datetime.now(timezone.utc).strftime(
            f"%Y%m%d_%H%M%S_{self._sim_counter:04d}"
        )

        if order_book is None or order_book.is_empty:
            # Fall back to best-ask fill from proposal metadata
            if proposal.best_ask is not None and proposal.best_ask <= proposal.limit_price:
                fill_price = proposal.best_ask
                fill_size = proposal.size
                status = "filled"
                unfilled = 0.0
                avg_price = fill_price
                total_cost = fill_size * fill_price
                slippage = 0.0
                levels = 1
            else:
                status = "no_liquidity"
                fill_price = None
                fill_size = None
                unfilled = proposal.size
                avg_price = None
                total_cost = 0.0
                slippage = 0.0
                levels = 0
        else:
            fill_result = simulate_fill(
                order_book=order_book,
                side=proposal.side,
                size=proposal.size,
                max_slippage_bps=100.0,
            )

            if fill_result.filled_size == 0:
                status = "no_liquidity"
                fill_price = None
                fill_size = None
                unfilled = proposal.size
                avg_price = None
                total_cost = 0.0
                slippage = 0.0
                levels = 0
            elif fill_result.is_partial:
                status = "partial_fill"
                fill_price = fill_result.average_price
                fill_size = fill_result.filled_size
                unfilled = fill_result.unfilled_size
                avg_price = fill_result.average_price
                total_cost = fill_result.total_cost
                slippage = fill_result.slippage_bps
                levels = fill_result.levels_consumed
            else:
                status = "filled"
                fill_price = fill_result.average_price
                fill_size = fill_result.filled_size
                unfilled = 0.0
                avg_price = fill_result.average_price
                total_cost = fill_result.total_cost
                slippage = fill_result.slippage_bps
                levels = fill_result.levels_consumed

        sim = OrderSimulation(
            proposal=proposal,
            status=status,
            fill_price=fill_price,
            fill_size=fill_size,
            unfilled_size=unfilled,
            average_price=avg_price,
            total_cost=total_cost,
            slippage_bps=slippage,
            levels_consumed=levels,
            sim_id=sim_id,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

        self.ledger.record(sim)
        logger.info(
            "Sim %s: %s %s $%.0f @ %.4f (%s, slip=%.1fbps)",
            sim_id, proposal.ticker, proposal.side,
            fill_size or 0, fill_price or 0, status, slippage,
        )

        return sim
