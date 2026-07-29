"""
Continuous paper trading service.

Runs the pipeline on a schedule, tracks open/settled positions,
and maintains a checkpoint file for resume.
"""
from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from prediction_bot.trading.strategy_rules import (
    STRATEGY_DEFAULT,
    StrategyConfig,
    compute_pnl,
)

logger = logging.getLogger(__name__)

CHECKPOINT_FILE = "data/paper_trading_checkpoint.json"


@dataclass
class Position:
    """An open or settled paper trade position."""
    sim_id: str
    ticker: str
    event_ticker: str
    team_a: str
    team_b: str
    side: str
    size: float
    fill_price: float
    model_prob: float
    predicted_winner: str
    opened_at: str
    settled_at: str = ""
    correct: bool | None = None
    pnl: float | None = None
    result: str = ""  # yes/no from Kalshi settlement

    @property
    def is_open(self) -> bool:
        return self.pnl is None

    @property
    def is_settled(self) -> bool:
        return self.pnl is not None


@dataclass
class PortfolioSnapshot:
    """Aggregate metrics at a point in time."""
    total_trades: int = 0
    open_positions: int = 0
    settled_positions: int = 0
    wins: int = 0
    losses: int = 0
    total_pnl: float = 0.0
    total_committed: float = 0.0
    roi: float = 0.0
    max_drawdown: float = 0.0
    current_drawdown: float = 0.0
    sharpe: float = 0.0
    timestamp: str = ""

    @property
    def win_rate(self) -> float:
        if self.settled_positions == 0:
            return 0.0
        return self.wins / self.settled_positions


class PaperTradingService:
    """Continuously scans, trades, and tracks paper positions."""

    def __init__(
        self,
        strategy: StrategyConfig | None = None,
        checkpoint_path: str = CHECKPOINT_FILE,
        scan_interval_minutes: int = 60,
    ) -> None:
        self.strategy = strategy or STRATEGY_DEFAULT
        self.checkpoint_path = Path(checkpoint_path)
        self.scan_interval = scan_interval_minutes
        self.positions: list[Position] = []
        self.executed_tickers: set[str] = set()
        self._load_checkpoint()

    def _load_checkpoint(self) -> None:
        if self.checkpoint_path.exists():
            raw = json.loads(self.checkpoint_path.read_text())
            self.positions = [Position(**p) for p in raw.get("positions", [])]
            self.executed_tickers = set(raw.get("executed_tickers", []))
            logger.info(
                "Loaded checkpoint: %d positions, %d executed tickers",
                len(self.positions),
                len(self.executed_tickers),
            )

    def _save_checkpoint(self) -> None:
        self.checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
        raw = {
            "positions": [
                {
                    "sim_id": p.sim_id,
                    "ticker": p.ticker,
                    "event_ticker": p.event_ticker,
                    "team_a": p.team_a,
                    "team_b": p.team_b,
                    "side": p.side,
                    "size": p.size,
                    "fill_price": p.fill_price,
                    "model_prob": p.model_prob,
                    "predicted_winner": p.predicted_winner,
                    "opened_at": p.opened_at,
                    "settled_at": p.settled_at,
                    "correct": p.correct,
                    "pnl": p.pnl,
                    "result": p.result,
                }
                for p in self.positions
            ],
            "executed_tickers": sorted(self.executed_tickers),
        }
        self.checkpoint_path.write_text(json.dumps(raw, indent=2, default=str))

    def settle_positions(self) -> int:
        """Check open positions against Kalshi for settlement.

        Returns number of newly settled positions.
        """
        import requests

        settled_count = 0
        for pos in self.positions:
            if not pos.is_open:
                continue
            try:
                url = (
                    "https://external-api.kalshi.com/trade-api/v2"
                    f"/markets/{pos.ticker}"
                )
                resp = requests.get(url, timeout=30)
                resp.raise_for_status()
                data = resp.json()
                market = data.get("market", data)
                result = market.get("result")
                if result not in ("yes", "no"):
                    continue  # still open

                yes_sub = (market.get("yes_sub_title") or "").lower()
                correct = (
                    (pos.predicted_winner.lower() == yes_sub)
                    if result == "yes"
                    else (pos.predicted_winner.lower() != yes_sub)
                )
                pos.correct = correct
                pos.result = result
                pos.settled_at = datetime.now(timezone.utc).isoformat()
                pos.pnl = compute_pnl(pos.model_prob, correct, pos.size)
                settled_count += 1
                logger.info(
                    "Settled %s: %s vs %s, predicted=%s, correct=%s, PnL=$%.2f",
                    pos.ticker, pos.team_a, pos.team_b,
                    pos.predicted_winner, correct, pos.pnl,
                )
            except Exception as e:
                logger.debug("Settlement check failed for %s: %s", pos.ticker, e)

        if settled_count:
            self._save_checkpoint()
        return settled_count

    def run_one_scan(self) -> dict[str, Any]:
        """Execute one scan-and-trade cycle. Returns summary dict."""
        from prediction_bot.trading.pipeline import run_paper_trading_pipeline

        # Settle open positions first
        settled = self.settle_positions()

        # Run pipeline
        pipeline_summary = run_paper_trading_pipeline(max_pages=3)

        # Extract new positions from the execution ledger
        new_positions = self._extract_new_positions()

        logger.info(
            "Cycle complete: %d settled, %d new trades, %d open positions",
            settled, len(new_positions), sum(1 for p in self.positions if p.is_open),
        )

        return self.snapshot()

    def _extract_new_positions(self) -> list[Position]:
        """Extract new positions from the execution ledger."""
        import sqlite3

        db_path = Path("data/execution_ledger.db")
        if not db_path.exists():
            return []

        new_positions: list[Position] = []
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        try:
            rows = conn.execute(
                "SELECT * FROM execution_ledger WHERE settled=0 ORDER BY id"
            ).fetchall()

            for row in rows:
                ticker = row["ticker"]
                if ticker in self.executed_tickers:
                    continue

                pos = Position(
                    sim_id=row["sim_id"],
                    ticker=ticker,
                    event_ticker=row["event_ticker"] or "",
                    team_a=row["team_a"] or "",
                    team_b=row["team_b"] or "",
                    side=row["side"],
                    size=row["fill_size"] or row["proposed_size"],
                    fill_price=row["fill_price"] or 0.0,
                    model_prob=row["model_prob"],
                    predicted_winner=row["predicted_winner"] or "",
                    opened_at=row["timestamp"],
                )
                self.positions.append(pos)
                self.executed_tickers.add(ticker)
                new_positions.append(pos)

                # Mark as tracked in ledger
                conn.execute(
                    "UPDATE execution_ledger SET settled=1 WHERE id=?",
                    (row["id"],),
                )
            conn.commit()
        finally:
            conn.close()

        if new_positions:
            self._save_checkpoint()
        return new_positions

    def snapshot(self) -> dict[str, Any]:
        """Compute current portfolio metrics."""
        import numpy as np

        settled = [p for p in self.positions if p.is_settled]
        open_pos = [p for p in self.positions if p.is_open]
        wins = sum(1 for p in settled if p.correct)
        losses = sum(1 for p in settled if p.correct is False)
        total_pnl = sum(p.pnl or 0.0 for p in settled)
        total_committed = sum(p.size for p in open_pos)
        roi = total_pnl / max(sum(p.size for p in settled), 1)

        # Drawdown from settled PnL sequence
        pnls = [p.pnl or 0.0 for p in settled]
        cumsum = list(np.cumsum(pnls)) if pnls else [0.0]
        running_max = list(np.maximum.accumulate(cumsum))
        drawdowns = [c - m for c, m in zip(cumsum, running_max)]
        max_dd = min(drawdowns) if drawdowns else 0.0
        current_dd = drawdowns[-1] if drawdowns else 0.0

        # Sharpe
        if len(pnls) > 1 and np.std(pnls) > 0:
            sharpe = float(np.mean(pnls) / np.std(pnls) * np.sqrt(len(pnls)))
        else:
            sharpe = 0.0

        return {
            "total_trades": len(self.positions),
            "open_positions": len(open_pos),
            "settled_positions": len(settled),
            "wins": wins,
            "losses": losses,
            "win_rate": wins / max(len(settled), 1),
            "total_pnl": total_pnl,
            "total_committed": total_committed,
            "roi": roi,
            "max_drawdown": max_dd,
            "current_drawdown": current_dd,
            "sharpe": sharpe,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    def run_loop(self, max_iterations: int | None = None) -> None:
        """Run continuous paper trading loop."""
        i = 0
        logger.info(
            "Starting paper trading service (interval=%d min, strategy=%s)",
            self.scan_interval, self.strategy.name,
        )

        while max_iterations is None or i < max_iterations:
            i += 1
            logger.info("── Cycle %d ──", i)
            snap = self.run_one_scan()
            logger.info(
                "Snapshot: %d trades | WR=%.0f%% | PnL=$%.2f | "
                "DD=$%.1f | Sharpe=%.2f",
                snap["settled_positions"],
                snap["win_rate"] * 100,
                snap["total_pnl"],
                snap["max_drawdown"],
                snap["sharpe"],
            )

            if max_iterations is None or i < (max_iterations or 1):
                logger.info("Sleeping %d min...", self.scan_interval)
                time.sleep(self.scan_interval * 60)


def print_portfolio_report(service: PaperTradingService) -> None:
    """Print a human-readable portfolio report."""
    snap = service.snapshot()

    print()
    print("=" * 60)
    print("  PAPER TRADING PORTFOLIO")
    print("=" * 60)
    print(f"  Total trades:      {snap['total_trades']}")
    print(f"  Settled:           {snap['settled_positions']}")
    print(f"  Open:              {snap['open_positions']}")
    print(f"  Wins/Losses:       {snap['wins']}/{snap['losses']}")
    print(f"  Win rate:          {snap['win_rate']:.0%}")
    print(f"  Total PnL:         ${snap['total_pnl']:+.2f}")
    print(f"  ROI:               {snap['roi']:+.1%}")
    print(f"  Max drawdown:      ${snap['max_drawdown']:+.2f}")
    print(f"  Current drawdown:  ${snap['current_drawdown']:+.2f}")
    print(f"  Sharpe:            {snap['sharpe']:.2f}")
    print(f"  Capital at risk:   ${snap['total_committed']:.2f}")

    if service.positions:
        print()
        print("  Recent positions:")
        for p in sorted(service.positions, key=lambda x: x.opened_at, reverse=True)[:5]:
            if p.is_settled:
                m = "✓" if p.correct else "✗"
                status = f"settled PnL=${p.pnl:+.0f}"
            else:
                m = "○"
                status = "open"
            print(
                f"  {m} {p.team_a} vs {p.team_b}  "
                f"prob={p.model_prob:.0%}  size=${p.size:.0f}  {status}"
            )
    print()
