"""Report templates for monitoring system.

Read-only formatting — never touches execution state.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def daily_report(data: dict[str, Any]) -> str:
    """Format a daily production report as plain text."""
    signals = data.get("signals", {})
    performance = data.get("performance", {})
    risk = data.get("risk", {})
    calibration = data.get("calibration", {})
    date = data.get("date", datetime.now(timezone.utc).strftime("%Y-%m-%d"))

    lines = [
        f"📊 DAILY REPORT — {date}",
        f"Mode: {data.get('mode', 'APPROVAL')}",
        "",
        "── Signals ──",
        f"  Scanned:      {signals.get('markets_scanned', 0):>5}",
        f"  Tier 1:       {signals.get('tier1_matches', 0):>5}",
        f"  Qualified:    {signals.get('qualified_trades', 0):>5}",
        f"  Submitted:    {signals.get('trades_submitted', 0):>5}",
        "",
        "── Performance ──",
        f"  Open:         {performance.get('open_positions', 0)}",
        f"  Settled:      {performance.get('settled_positions', 0)}",
        f"  Wins/Losses:  {performance.get('wins', 0)}/{performance.get('losses', 0)}",
        f"  Win rate:     {performance.get('win_rate', 0):.0%}",
        f"  Realized PnL: ${performance.get('realized_pnl', 0):+.2f}",
        f"  ROI:          {performance.get('roi', 0):+.1%}",
        "",
        "── Risk ──",
        f"  Exposure:     ${risk.get('current_exposure', 0):.2f}",
        f"  Max DD:       ${risk.get('max_drawdown', 0):.2f}",
        f"  Daily loss:   ${risk.get('daily_loss', 0):+.2f}",
        "",
    ]

    if calibration:
        lines.append("── Calibration ──")
        for bucket, bdata in sorted(calibration.items()):
            n = bdata.get("count", 0)
            if n > 0:
                wr = bdata.get("win_rate", 0)
                lines.append(f"  {bucket}: {n:>3d} trades, actual WR={wr:.0%}")
        lines.append("")

    return "\n".join(lines)


def weekly_report(data: dict[str, Any]) -> str:
    """Format a weekly comparison report."""
    live = data.get("live", {})
    backtest = data.get("backtest", {})
    week = data.get("week", "unknown")

    def compare(name: str, live_val: float, hist_val: float, fmt: str = ".1f") -> str:
        diff = live_val - hist_val
        arrow = "▲" if diff > 0 else "▼" if diff < 0 else "="
        return (
            f"  {name:<18s} {live_val:{fmt}}  "
            f"{hist_val:{fmt}}  {arrow} {abs(diff):{fmt}}"
        )

    lines = [
        f"📈 WEEKLY REPORT — {week}",
        f"Mode: {data.get('mode', 'APPROVAL')}",
        "",
        f"{'Metric':<18s} {'Live':>8s} {'Backtest':>8s}  Δ",
        f"{'-'*18} {'-'*8} {'-'*8}  --",
        compare("Trades", live.get("trades", 0), backtest.get("trades", 0), "3.0f"),
        compare("Win rate", live.get("win_rate", 0), backtest.get("win_rate", 0.79), ".0%"),
        compare("ROI", live.get("roi", 0), backtest.get("roi", 0.045), ".1%"),
        compare("Sharpe", live.get("sharpe", 0), backtest.get("sharpe", 1.0), ".2f"),
        compare("Max DD", live.get("max_dd", 0), backtest.get("max_dd", -429), ".0f"),
        "",
        "Expected range (historical ±1σ):",
        f"  PnL:    ${backtest.get('pnl_lo', 0):+.0f} to ${backtest.get('pnl_hi', 0):+.0f}",
        f"  Sharpe: {backtest.get('sharpe_lo', 0):.2f} to {backtest.get('sharpe_hi', 2):.2f}",
        "",
    ]

    return "\n".join(lines)


def alert_message(event: dict[str, Any]) -> str:
    """Format an alert notification."""
    event_type = event.get("type", "unknown")
    ts = event.get("timestamp", "")

    if event_type == "order_submitted":
        return (
            f"🔵 ORDER SUBMITTED\n"
            f"  {event.get('ticker', '?')}\n"
            f"  {event.get('side', '?')} {event.get('count', 0)} @ ${event.get('price', 0):.4f}\n"
            f"  Order: {event.get('order_id', '?')}\n"
            f"  {ts}"
        )

    if event_type == "order_filled":
        return (
            f"🟢 ORDER FILLED\n"
            f"  {event.get('ticker', '?')}\n"
            f"  {event.get('filled', 0)}/{event.get('count', 0)} @ ${event.get('fill_price', 0):.4f}\n"
            f"  Cost: ${event.get('cost', 0):.4f}\n"
            f"  Order: {event.get('order_id', '?')}\n"
            f"  {ts}"
        )

    if event_type == "order_rejected":
        return (
            f"🔴 ORDER REJECTED\n"
            f"  {event.get('ticker', '?')}\n"
            f"  Reason: {event.get('reason', 'unknown')}\n"
            f"  {ts}"
        )

    if event_type == "risk_limit":
        return (
            f"⚠️ RISK LIMIT TRIGGERED\n"
            f"  Limit: {event.get('limit', '?')}\n"
            f"  Current: {event.get('current', '?')}\n"
            f"  Max: {event.get('max', '?')}\n"
            f"  {ts}"
        )

    if event_type == "api_error":
        return (
            f"❌ API ERROR\n"
            f"  {event.get('endpoint', '?')}\n"
            f"  {event.get('error', 'unknown')}\n"
            f"  {ts}"
        )

    return f"📢 {event_type.upper()}: {event}"
