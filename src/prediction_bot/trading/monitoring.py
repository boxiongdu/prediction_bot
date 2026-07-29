"""
Daily production monitoring report.

Tracks signals, performance, risk, and calibration.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)

REPORT_PATH = "data/daily_report.json"


@dataclass
class DailyReport:
    """Daily production metrics for the trading system."""

    date: str = ""
    mode: str = "PAPER"

    # Signals
    markets_scanned: int = 0
    tier1_matches: int = 0
    qualified_trades: int = 0
    trades_submitted: int = 0

    # Performance
    open_positions: int = 0
    settled_positions: int = 0
    wins: int = 0
    losses: int = 0
    realized_pnl: float = 0.0
    roi: float = 0.0
    win_rate: float = 0.0

    # Risk
    current_exposure: float = 0.0
    max_drawdown: float = 0.0
    daily_loss: float = 0.0

    # Calibration
    calibration_buckets: dict[str, dict[str, Any]] = field(default_factory=dict)

    # Metadata
    strategy_version: str = "0.62-0.85"
    timestamp: str = ""


def generate_report(
    service=None,
    safety=None,
    positions: list[Any] | None = None,
    rejected_reasons: dict[str, int] | None = None,
) -> DailyReport:
    """Generate a daily production report from current state."""

    date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    report = DailyReport(
        date=date,
        mode=safety.mode if safety else "PAPER",
        timestamp=datetime.now(timezone.utc).isoformat(),
    )

    # From service (if available)
    if service:
        snap = service.snapshot()
        report.open_positions = snap.get("open_positions", 0)
        report.settled_positions = snap.get("settled_positions", 0)
        report.wins = snap.get("wins", 0)
        report.losses = snap.get("losses", 0)
        report.realized_pnl = snap.get("total_pnl", 0.0)
        report.win_rate = snap.get("win_rate", 0.0)
        report.roi = snap.get("roi", 0.0)
        report.max_drawdown = snap.get("max_drawdown", 0.0)
        report.current_exposure = snap.get("total_committed", 0.0)

        # Calibration
        report.calibration_buckets = _compute_calibration(service.positions)

    # From safety (if available)
    if safety:
        report.markets_scanned = safety._daily_state.get("markets_scanned", 0)
        report.qualified_trades = safety.daily_trades
        report.daily_loss = safety.daily_loss

    # Count submitted (real or paper)
    report.trades_submitted = report.qualified_trades

    return report


def _compute_calibration(positions: list[Any]) -> dict[str, dict[str, Any]]:
    """Compare predicted probability buckets to actual win rates."""
    buckets = {
        "0.60-0.65": {"predicted": 0, "correct": 0, "avg_prob": 0.0},
        "0.65-0.70": {"predicted": 0, "correct": 0, "avg_prob": 0.0},
        "0.70-0.75": {"predicted": 0, "correct": 0, "avg_prob": 0.0},
        "0.75-0.80": {"predicted": 0, "correct": 0, "avg_prob": 0.0},
        "0.80-0.85": {"predicted": 0, "correct": 0, "avg_prob": 0.0},
    }

    settled = [p for p in positions if getattr(p, "is_settled", False)]
    for p in settled:
        prob = getattr(p, "model_prob", 0.0)
        correct = getattr(p, "correct", False)
        bucket = _get_bucket(prob)
        if bucket:
            buckets[bucket]["predicted"] += 1
            if correct:
                buckets[bucket]["correct"] += 1

    for bucket in buckets:
        n = buckets[bucket]["predicted"]
        if n > 0:
            buckets[bucket]["win_rate"] = round(
                buckets[bucket]["correct"] / n, 3,
            )
        else:
            buckets[bucket]["win_rate"] = 0.0
        buckets[bucket]["count"] = n

    return buckets


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


def save_report(report: DailyReport, path: str = REPORT_PATH) -> None:
    """Save the report to disk."""
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps({
        "date": report.date,
        "mode": report.mode,
        "signals": {
            "markets_scanned": report.markets_scanned,
            "tier1_matches": report.tier1_matches,
            "qualified_trades": report.qualified_trades,
            "trades_submitted": report.trades_submitted,
        },
        "performance": {
            "open_positions": report.open_positions,
            "settled_positions": report.settled_positions,
            "wins": report.wins,
            "losses": report.losses,
            "realized_pnl": round(report.realized_pnl, 2),
            "roi": round(report.roi, 4),
            "win_rate": round(report.win_rate, 4),
        },
        "risk": {
            "current_exposure": round(report.current_exposure, 2),
            "max_drawdown": round(report.max_drawdown, 2),
            "daily_loss": round(report.daily_loss, 2),
        },
        "calibration": report.calibration_buckets,
        "strategy_version": report.strategy_version,
        "timestamp": report.timestamp,
    }, indent=2))


def print_daily_report(report: DailyReport) -> None:
    """Print a human-readable daily report."""
    print()
    print("=" * 60)
    print(f"  DAILY PRODUCTION REPORT — {report.date}")
    print("=" * 60)
    print(f"  Mode: {report.mode}")

    print()
    print("  ── Signals ──")
    print(f"  Markets scanned:    {report.markets_scanned}")
    print(f"  Tier 1 matches:     {report.tier1_matches}")
    print(f"  Qualified trades:   {report.qualified_trades}")
    print(f"  Trades submitted:   {report.trades_submitted}")

    print()
    print("  ── Performance ──")
    print(f"  Open positions:     {report.open_positions}")
    print(f"  Settled:            {report.settled_positions}")
    print(f"  Wins/Losses:        {report.wins}/{report.losses}")
    print(f"  Win rate:           {report.win_rate:.0%}")
    print(f"  Realized PnL:       ${report.realized_pnl:+.2f}")
    print(f"  ROI:                {report.roi:+.1%}")

    print()
    print("  ── Risk ──")
    print(f"  Current exposure:   ${report.current_exposure:.2f}")
    print(f"  Max drawdown:       ${report.max_drawdown:.2f}")
    print(f"  Daily loss:         ${report.daily_loss:+.2f}")

    if report.calibration_buckets:
        print()
        print("  ── Calibration ──")
        print(f"  {'Bucket':<12s} {'N':>4s} {'Predicted':>10s} {'Actual':>10s}")
        for bucket, data in sorted(report.calibration_buckets.items()):
            n = data.get("count", 0)
            if n > 0:
                print(
                    f"  {bucket:<12s} {n:>4d} "
                    f"{bucket.split('-')[1]:>9s} "
                    f"{data['win_rate']:>9.0%}"
                )

    print()
