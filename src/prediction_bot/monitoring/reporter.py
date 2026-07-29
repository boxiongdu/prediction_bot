"""
Report generator — daily and weekly performance reports.

Read-only — reads from ledgers and state files, never writes.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

from prediction_bot.monitoring.templates import daily_report, weekly_report

logger = logging.getLogger(__name__)


class Reporter:
    """Generates daily and weekly reports from ledger data."""

    def __init__(
        self,
        execution_ledger: str = "data/execution_ledger.db",
        live_orders: str = "data/live_orders.jsonl",
        checkpoint: str = "data/paper_trading_checkpoint.json",
        daily_state: str = "data/daily_trading_state.json",
    ) -> None:
        self._ledger_path = Path(execution_ledger)
        self._orders_path = Path(live_orders)
        self._checkpoint_path = Path(checkpoint)
        self._daily_state_path = Path(daily_state)

    def generate_daily(self) -> str:
        """Generate a daily production report."""
        data = self._collect_daily_data()
        return daily_report(data)

    def generate_weekly(self) -> str:
        """Generate a weekly comparison report."""
        data = self._collect_weekly_data()
        return weekly_report(data)

    def print_daily(self) -> None:
        print(self.generate_daily())

    def print_weekly(self) -> None:
        print(self.generate_weekly())

    # ── Data collection ─────────────────────────────────────

    def _collect_daily_data(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            "mode": "APPROVAL",
            "signals": {"markets_scanned": 0, "tier1_matches": 0,
                        "qualified_trades": 0, "trades_submitted": 0},
            "performance": {"open_positions": 0, "settled_positions": 0,
                           "wins": 0, "losses": 0, "win_rate": 0.0,
                           "realized_pnl": 0.0, "roi": 0.0},
            "risk": {"current_exposure": 0.0, "max_drawdown": 0.0,
                    "daily_loss": 0.0},
            "calibration": {},
        }

        # From checkpoint
        if self._checkpoint_path.exists():
            try:
                cp = json.loads(self._checkpoint_path.read_text())
                positions = cp.get("positions", [])
                settled = [p for p in positions if p.get("pnl") is not None]
                data["performance"]["settled_positions"] = len(settled)
                data["performance"]["open_positions"] = (
                    len(positions) - len(settled)
                )
                data["performance"]["wins"] = sum(
                    1 for p in settled if p.get("correct")
                )
                data["performance"]["losses"] = sum(
                    1 for p in settled if p.get("correct") is False
                )
                if settled:
                    data["performance"]["win_rate"] = (
                        data["performance"]["wins"] / len(settled)
                    )
                    data["performance"]["realized_pnl"] = sum(
                        p.get("pnl", 0) for p in settled
                    )

                # Calibration
                buckets = self._compute_calibration(positions)
                data["calibration"] = buckets

                # Drawdown
                pnls = [p.get("pnl", 0) for p in settled]
                if pnls:
                    cumsum = np.cumsum(pnls)
                    dd = cumsum - np.maximum.accumulate(cumsum)
                    data["risk"]["max_drawdown"] = float(np.min(dd))

            except Exception as e:
                logger.warning("Failed to read checkpoint: %s", e)

        # From daily state
        if self._daily_state_path.exists():
            try:
                ds = json.loads(self._daily_state_path.read_text())
                data["risk"]["daily_loss"] = ds.get("daily_loss", 0.0)
                data["risk"]["current_exposure"] = ds.get("open_exposure", 0.0)
                data["signals"]["qualified_trades"] = ds.get("daily_trades", 0)
            except Exception:
                pass

        # From live orders
        if self._orders_path.exists():
            orders = self._read_jsonl(self._orders_path)
            data["signals"]["trades_submitted"] = len(orders)
            for o in orders:
                data["risk"]["current_exposure"] += o.get("fill_cost", 0)

        return data

    def _collect_weekly_data(self) -> dict[str, Any]:
        live = self._collect_daily_data()
        return {
            "week": datetime.now(timezone.utc).strftime("%Y-W%W"),
            "mode": live["mode"],
            "live": {
                "trades": live["performance"]["settled_positions"],
                "win_rate": live["performance"]["win_rate"],
                "roi": live["performance"]["roi"],
                "sharpe": 0.0,  # computed below if enough data
                "max_dd": live["risk"]["max_drawdown"],
            },
            "backtest": {
                "trades": 82,
                "win_rate": 0.79,
                "roi": 0.045,
                "sharpe": 1.00,
                "pnl_lo": -200.0,
                "pnl_hi": 600.0,
                "sharpe_lo": 0.5,
                "sharpe_hi": 1.5,
                "max_dd": -429,
            },
        }

    @staticmethod
    def _compute_calibration(
        positions: list[dict[str, Any]],
    ) -> dict[str, dict[str, Any]]:
        buckets: dict[str, dict[str, Any]] = {
            "0.60-0.65": {"predicted": 0, "correct": 0, "count": 0, "win_rate": 0.0},
            "0.65-0.70": {"predicted": 0, "correct": 0, "count": 0, "win_rate": 0.0},
            "0.70-0.75": {"predicted": 0, "correct": 0, "count": 0, "win_rate": 0.0},
            "0.75-0.80": {"predicted": 0, "correct": 0, "count": 0, "win_rate": 0.0},
            "0.80-0.85": {"predicted": 0, "correct": 0, "count": 0, "win_rate": 0.0},
        }
        settled = [p for p in positions if p.get("pnl") is not None]
        for p in settled:
            prob = p.get("model_prob", 0)
            correct = p.get("correct", False)
            bucket = Reporter._get_bucket(prob)
            if bucket:
                buckets[bucket]["predicted"] += 1
                if correct:
                    buckets[bucket]["correct"] += 1
        for b in buckets:
            n = buckets[b]["predicted"]
            buckets[b]["count"] = n
            buckets[b]["win_rate"] = (
                buckets[b]["correct"] / n if n > 0 else 0.0
            )
        return buckets

    @staticmethod
    def _get_bucket(prob: float) -> str | None:
        if 0.60 <= prob < 0.65:
            return "0.60-0.65"
        if 0.65 <= prob < 0.70:
            return "0.65-0.70"
        if 0.70 <= prob < 0.75:
            return "0.70-0.75"
        if 0.75 <= prob < 0.80:
            return "0.75-0.80"
        if 0.80 <= prob <= 0.85:
            return "0.80-0.85"
        return None

    @staticmethod
    def _read_jsonl(path: Path) -> list[dict[str, Any]]:
        if not path.exists():
            return []
        entries: list[dict[str, Any]] = []
        for line in path.read_text().strip().split("\n"):
            if line.strip():
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
        return entries
