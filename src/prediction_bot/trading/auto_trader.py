"""
AUTO trading engine — time-bounded, dataset-coverage-based eligibility.

Flow: scan → 24h filter → league coverage → Elo coverage → predict
      → Hermes review → strategy → safety → balance → submit → notify

Kill switches: ENABLE_LIVE_TRADING=false or AUTO_TRADING_ENABLED=false → no orders.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

import requests

from prediction_bot.agents.schema import normalize_contract
from prediction_bot.data.schema import _parse_price_dollars
from prediction_bot.monitoring.alerts import AlertManager
from prediction_bot.trading.filter import filter_markets
from prediction_bot.trading.order_client import KalshiOrderClient, generate_proposal
from prediction_bot.trading.strategy import (
    build_team_elo_lookup,
    hermes_review,
    normalize_team_name,
    predict_match,
)
from prediction_bot.trading.strategy_rules import (
    EligibilityRule,
    SizingRule,
    StrategyConfig,
)
from prediction_bot.trading.safety import (
    AUTO_TRADING_ENABLED,
    ENABLE_LIVE_TRADING,
    LIVE_TRADING_MODE,
    MAX_DAILY_LOSS,
    MAX_POSITION_PER_TRADE,
    MAX_TOTAL_OPEN_EXPOSURE,
    MAX_TRADES_PER_DAY,
    ProductionSafety,
)

logger = logging.getLogger(__name__)

SCAN_URL = (
    "https://external-api.kalshi.com/trade-api/v2/markets"
    "?status=open&limit=100&series_ticker=KXLOLGAME&mve_filter=exclude"
)

# Leagues present in Oracle's Elixir training dataset
# (computed from data/tier1_matches_enriched.parquet)
_COVERED_LEAGUES: set[str] = {
    "EWC", "FST", "LCK", "LCP", "LCS", "LEC", "LPL",
    "LTA", "LTA N", "LTA S", "MSI", "WLDs",
}


def _parse_iso(ts: str | None) -> datetime | None:
    if not ts:
        return None
    try:
        return datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None


def is_within_24h(raw_market: dict[str, Any]) -> tuple[bool, str]:
    """Check if the event starts within the next 24 hours.

    Uses close_time from the market data as event start proxy.
    """
    now = datetime.now(timezone.utc)
    cutoff = now + timedelta(hours=24)

    close_time = _parse_iso(raw_market.get("close_time"))
    occurrence = _parse_iso(raw_market.get("occurrence_datetime"))

    event_time = occurrence or close_time
    if not event_time:
        return False, "no event time available"

    if event_time <= now:
        return False, f"already started ({event_time.strftime('%H:%M UTC')})"
    if event_time > cutoff:
        hours_away = (event_time - now).total_seconds() / 3600
        return False, f"too far ({hours_away:.0f}h away)"

    hours_until = (event_time - now).total_seconds() / 3600
    return True, f"in {hours_until:.1f}h"


def check_league_coverage(tournament: str | None) -> tuple[bool, str]:
    """Check if the tournament league is covered by Oracle's Elixir."""
    if not tournament:
        return False, "no tournament info"
    # Match against known leagues (case-insensitive prefix match)
    t_upper = tournament.upper()
    for league in _COVERED_LEAGUES:
        if t_upper.startswith(league.upper()) or league.upper() in t_upper:
            return True, league
    return False, f"league not in dataset: {tournament}"


def run_auto_scan() -> dict[str, Any]:
    """Execute one fully automated scan-and-trade cycle."""
    alerts = AlertManager()
    safety = ProductionSafety()
    strategy = StrategyConfig(
        eligibility=EligibilityRule(prob_lo=0.62, prob_hi=0.85, min_edge=0.03),
        sizing=SizingRule(method="fixed", fixed_size=MAX_POSITION_PER_TRADE),
        name="auto-0.62-0.85",
    )

    summary: dict[str, Any] = {
        "mode": LIVE_TRADING_MODE,
        "can_submit": safety.can_submit_orders,
        "markets_scanned": 0,
        "passed_24h": 0,
        "passed_coverage": 0,
        "qualified": 0,
        "submitted": 0,
        "rejected": 0,
        "errors": 0,
        "trades": [],
        "rejections": {},
        "risk_limits": {
            "max_position": MAX_POSITION_PER_TRADE,
            "max_exposure": MAX_TOTAL_OPEN_EXPOSURE,
            "max_daily_loss": MAX_DAILY_LOSS,
            "max_trades_per_day": MAX_TRADES_PER_DAY,
            "daily_trades_used": safety.daily_trades,
            "live_trading": ENABLE_LIVE_TRADING,
            "auto_enabled": AUTO_TRADING_ENABLED,
        },
    }

    logger.info("AUTO SCAN START — can_submit=%s", safety.can_submit_orders)

    # ── Step 1: Scan ──────────────────────────────────────
    try:
        resp = requests.get(SCAN_URL, timeout=30)
        resp.raise_for_status()
        markets = resp.json().get("markets", [])
        summary["markets_scanned"] = len(markets)
    except Exception as e:
        logger.error("Scan failed: %s", e)
        summary["errors"] += 1
        return summary

    # ── Step 2: Filter all KXLOLGAME match winners (no Tier 1 hard filter) ─
    results = filter_markets(markets, tier1_only=False, scan_id="auto", query_params="")

    elo = build_team_elo_lookup()

    for fr in results:
        raw = next((m for m in markets if m.get("ticker") == fr.ticker), None)
        if not raw:
            continue

        # ── 24h time filter ────────────────────────────────
        within_24, time_reason = is_within_24h(raw)
        if not within_24:
            _inc_reason(summary, "time", f"time:{time_reason}")
            continue
        summary["passed_24h"] += 1

        # ── League coverage ────────────────────────────────
        covered, league_name = check_league_coverage(fr.tournament)
        if not covered:
            _inc_reason(summary, "league", f"league:{fr.tournament[:40]}")
            continue
        summary["passed_coverage"] += 1

        # ── Teams ──────────────────────────────────────────
        ta, tb = fr.team_a, fr.team_b
        if not ta or not tb:
            continue

        nta = normalize_team_name(ta)
        ntb = normalize_team_name(tb)
        elo_a = elo.get(nta)
        elo_b = elo.get(ntb)

        if elo_a is None or elo_b is None:
            missing = []
            if elo_a is None:
                missing.append(ta)
            if elo_b is None:
                missing.append(tb)
            _inc_reason(summary, "team_elo", f"elo:{','.join(missing)}")
            continue

        # ── Prediction ─────────────────────────────────────
        pred = predict_match(ta, tb, elo)
        nc = normalize_contract(raw)
        yo = (nc.yes_outcome or "").lower()
        if ta.lower() in yo:
            prob = pred["probability"]
            winner = ta
        elif tb.lower() in yo:
            prob = 1 - pred["probability"]
            winner = tb
        else:
            continue

        # ── Hermes review ──────────────────────────────────
        review = hermes_review(ta, tb, prob, elo, tournament=fr.tournament)
        if review["decision"] != "APPROVE":
            _inc_reason(summary, "hermes", f"hermes:{review['reasons'][0][:40]}")
            continue

        ask = float(_parse_price_dollars(raw.get("yes_ask_dollars")) or 0)
        edge = prob - ask if ask > 0 else None

        # ── Strategy ───────────────────────────────────────
        decision = strategy.evaluate_trade(
            prob=prob, edge=edge, hermes_approved=True, both_known=True,
        )
        if not decision["trade"]:
            _inc_reason(summary, "strategy", f"strategy:prob_band")
            continue

        summary["qualified"] += 1

        # ── Event time info for reporting ──────────────────
        event_time = _parse_iso(raw.get("occurrence_datetime") or raw.get("close_time"))
        hours_until = (
            (event_time - datetime.now(timezone.utc)).total_seconds() / 3600
            if event_time else 0
        )

        # ── Safety ─────────────────────────────────────────
        trade_size = decision["size"]
        check = safety.check_trade(fr.ticker, "bid", trade_size, raw)
        if not check.passed:
            summary["rejected"] += 1
            _inc_reason(summary, "safety", f"safety:{check.reason[:40]}")
            continue

        # ── Balance ────────────────────────────────────────
        order_cost = trade_size * (ask or prob)
        sufficient, balance = safety.check_balance(order_cost)
        if not sufficient:
            alerts.send({
                "type": "risk_limit",
                "limit": "insufficient_funds",
                "current": f"${balance:.2f}",
                "max": f"${order_cost:.2f}",
            })
            summary["rejected"] += 1
            _inc_reason(summary, "balance", "balance:insufficient")
            continue

        # ── Submit ─────────────────────────────────────────
        proposal = generate_proposal(
            ticker=fr.ticker, team_a=ta, team_b=tb,
            predicted_winner=winner, prob=prob, market_ask=ask, size=trade_size,
        )

        if not safety.can_submit_orders:
            logger.info("SIMULATED: %s (%s)", fr.ticker, proposal.reason)
            summary["trades"].append({
                "ticker": fr.ticker, "status": "simulated",
                "team": winner, "league": league_name,
                "hours_until": round(hours_until, 1),
            })
            continue

        client = KalshiOrderClient(mode="AUTO")
        result = client.approve(proposal)

        trade_info = {
            "ticker": fr.ticker,
            "order_id": result.order_id,
            "team": winner,
            "opponent": tb if winner == ta else ta,
            "league": league_name,
            "event_time": event_time.isoformat() if event_time else "",
            "hours_until": round(hours_until, 1),
            "price": ask,
            "size": trade_size,
            "prob": prob,
            "edge": round(edge, 4) if edge else None,
            "elo_a": round(elo_a, 1),
            "elo_b": round(elo_b, 1),
            "status": result.status,
        }

        if result.status == "accepted":
            safety.record_trade(fr.ticker, "bid", trade_size)
            summary["submitted"] += 1
            summary["trades"].append(trade_info)

            # Discord notification
            edge_str = f"{edge:+.1%}" if edge else "N/A"
            alerts.send({
                "type": "order_submitted",
                "report": (
                    f"🚀 AUTO TRADE EXECUTED\n"
                    f"Match: {winner} vs {trade_info['opponent']}\n"
                    f"League: {league_name}\n"
                    f"Starts: {event_time.strftime('%H:%M UTC') if event_time else '?'}"
                    f" ({hours_until:.1f}h)\n"
                    f"Side: YES {winner}\n"
                    f"Price: ${ask:.4f}\n"
                    f"Size: ${trade_size:.0f}\n"
                    f"Prob: {prob:.1%}\n"
                    f"Edge: {edge_str}\n"
                    f"Elo: {elo_a:.0f} vs {elo_b:.0f}\n"
                    f"Order: {result.order_id}"
                ),
            })
        else:
            summary["rejected"] += 1
            alerts.order_rejected(fr.ticker, result.message)

    # ── Discord daily summary ─────────────────────────────
    _send_daily_summary(alerts, summary)

    logger.info(
        "AUTO DONE — scanned=%d 24h=%d league=%d qualified=%d submitted=%d",
        summary["markets_scanned"], summary["passed_24h"],
        summary["passed_coverage"], summary["qualified"], summary["submitted"],
    )

    return summary


def _inc_reason(summary: dict[str, Any], category: str, detail: str) -> None:
    rejections = summary.setdefault("rejections", {})
    bucket = rejections.setdefault(category, {"count": 0, "details": []})
    bucket["count"] += 1
    if len(bucket["details"]) < 5:
        bucket["details"].append(detail)


def _send_daily_summary(alerts: AlertManager, summary: dict[str, Any]) -> None:
    limits = summary["risk_limits"]
    trades = summary["trades"]
    rejections = summary.get("rejections", {})

    lines = [
        "📊 AUTO TRADING SUMMARY",
        f"Mode: {summary['mode']} | Submit: {summary['can_submit']}",
        f"Scanned: {summary['markets_scanned']} | 24h: {summary['passed_24h']} "
        f"| Coverage: {summary['passed_coverage']} | Qualified: {summary['qualified']}",
        f"Submitted: {summary['submitted']} | Rejected: {summary['rejected']}",
        f"Risk: ${limits['max_position']}/trade | ${limits['max_exposure']} exp "
        f"| ${limits['max_daily_loss']} loss | {limits['daily_trades_used']}/{limits['max_trades_per_day']} trades",
    ]
    if rejections:
        lines.append("Rejections:")
        for cat, bucket in sorted(rejections.items()):
            lines.append(f"  {cat}: {bucket['count']}")

    if trades:
        lines.append("Trades:")
        for t in trades:
            league = t.get("league", "?")
            hours = t.get("hours_until", 0)
            lines.append(
                f"  {t.get('team','?')} vs {t.get('opponent','?')} "
                f"[{league}] in {hours:.0f}h "
                f"${t.get('size',0):.0f} @ {t.get('price',0):.4f} "
                f"[{t.get('status','?')}]"
            )
    alerts.send({"type": "daily_report", "report": "\n".join(lines)})


def print_auto_summary(summary: dict[str, Any]) -> None:
    """Print a human-readable auto trading summary."""
    limits = summary["risk_limits"]
    rejections = summary.get("rejections", {})
    print()
    print("=" * 60)
    print("  AUTO TRADING SCAN SUMMARY")
    print("=" * 60)
    print(f"  Mode:         {summary['mode']}")
    print(f"  Can submit:   {summary['can_submit']}")
    print(f"  Scanned:      {summary['markets_scanned']}")
    print(f"  Passed 24h:   {summary['passed_24h']}")
    print(f"  Passed league:{summary['passed_coverage']}")
    print(f"  Qualified:    {summary['qualified']}")
    print(f"  Submitted:    {summary['submitted']}")
    print(f"  Rejected:     {summary['rejected']}")
    print(f"  Errors:       {summary['errors']}")
    if rejections:
        print(f"  Rejections:")
        for cat, bucket in sorted(rejections.items()):
            print(f"    {cat}: {bucket['count']}")
    print()
    print("  Risk limits:")
    for k, v in limits.items():
        print(f"    {k}: {v}")

    if summary["trades"]:
        print()
        print("  Trades:")
        for t in summary["trades"]:
            print(
                f"    {t.get('ticker','?')[:45]} "
                f"{t.get('team','?'):15s} "
                f"[{t.get('league','?')}] "
                f"${t.get('size',0):.0f} "
                f"in {t.get('hours_until',0):.0f}h "
                f"[{t.get('status','?')}]"
            )
    print()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    s = run_auto_scan()
    print_auto_summary(s)
