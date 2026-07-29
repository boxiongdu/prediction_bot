"""
Paper trading pipeline — end-to-end orchestration.

Architecture:
  scanner.scan_all_markets() → filter.filter_markets()
  → predict + review → risk.check_trade()
  → executor.simulate_order() → execution_ledger
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)


def run_paper_trading_pipeline(
    max_pages: int | None = None,
    tier1_only: bool = True,
    min_edge: float = 0.03,
    max_position: float = 100.0,
) -> dict[str, Any]:
    """Run the complete paper trading pipeline.

    1. Scan all open Kalshi markets with full pagination
    2. Filter to LoL Tier 1 match-winner only
    3. Generate Elo-based predictions
    4. Hermes risk review
    5. Risk checks (edge, position size, duplicates)
    6. Dry-run order simulation
    7. Store everything in SQLite ledgers

    Returns summary dict with scan, filter, and execution stats.
    """
    from prediction_bot.trading.executor import DryRunExecutor, OrderProposal
    from prediction_bot.trading.filter import filter_markets
    from prediction_bot.trading.risk import RiskManager
    from prediction_bot.trading.scanner import scan_lol_markets
    from prediction_bot.trading.strategy import (
        build_team_elo_lookup,
        hermes_review,
        normalize_team_name,
        predict_match,
    )

    logger.info("=" * 60)
    logger.info("  PAPER TRADING PIPELINE v2")
    logger.info("=" * 60)

    # ── Step 1: Scan ────────────────────────────────────
    logger.info("Step 1: Scanning markets...")
    scan = scan_lol_markets(max_pages=max_pages)
    logger.info("Scanned %d KXLOL markets", scan.total_scanned)

    # ── Step 2: Filter ──────────────────────────────────
    logger.info("Step 2: Filtering markets...")
    results = filter_markets(
        scan.markets,
        tier1_only=tier1_only,
        scan_id=scan.scan_id,
        query_params=scan.query_params,
    )
    logger.info("Filtered to %d LoL Tier 1 match-winner events", len(results))

    if not results:
        return {
            "scan": {"total": scan.total_scanned},
            "filter": {"passed": 0},
            "execution": {"orders": 0, "filled": 0},
        }

    # ── Step 3: Build Elo lookup ────────────────────────
    logger.info("Step 3: Building Elo lookup...")
    elo_lookup = build_team_elo_lookup()

    # ── Step 4: Fetch order books ────────────────────────
    logger.info("Step 4: Fetching order books...")
    from prediction_bot.kalshi.orderbooks import fetch_order_books
    tickers = [r.ticker for r in results]
    order_books = fetch_order_books(tickers)
    logger.info("Fetched %d/%d order books", len(order_books), len(tickers))

    # ── Step 5: Predict, apply strategy rules, execute ──
    from prediction_bot.trading.strategy_rules import (
        StrategyConfig, EligibilityRule, SizingRule,
    )
    strategy = StrategyConfig(
        eligibility=EligibilityRule(
            prob_lo=0.60, prob_hi=0.85, min_edge=0.03,
        ),
        sizing=SizingRule(method="fixed", fixed_size=100.0),
        name="live-0.60-0.85",
    )
    executor = DryRunExecutor()
    trades_executed = 0
    rejected_reasons: dict[str, int] = {}

    for result in results:
        team_a = result.team_a
        team_b = result.team_b
        if not team_a or not team_b:
            continue

        # Find the raw market for price data
        raw = next(
            (m for m in scan.markets if m.get("ticker") == result.ticker),
            None,
        )
        if raw is None:
            continue

        # ── Prediction ──────────────────────────────────
        pred = predict_match(team_a, team_b, elo_lookup)
        model_prob = pred["probability"]

        # Determine which team this contract is about
        from prediction_bot.agents.schema import normalize_contract
        nc = normalize_contract(raw)
        yes_outcome = (nc.yes_outcome or "").lower()

        if team_a.lower() in yes_outcome:
            prob_for_side = model_prob
            predicted_winner = team_a
        elif team_b.lower() in yes_outcome:
            prob_for_side = 1 - model_prob
            predicted_winner = team_b
        else:
            continue

        # ── Market prices ───────────────────────────────
        from prediction_bot.data.schema import _parse_price_dollars
        yes_ask = _parse_price_dollars(raw.get("yes_ask_dollars"))
        yes_ask_f = float(yes_ask) if yes_ask else 0.0
        edge = prob_for_side - yes_ask_f

        # ── Hermes review ───────────────────────────────
        review = hermes_review(
            team_a=team_a,
            team_b=team_b,
            model_prob=prob_for_side,
            elo_lookup=elo_lookup,
            market_yes_ask=yes_ask_f if yes_ask_f > 0 else None,
            tournament=result.tournament,
        )

        # ── Strategy eligibility ─────────────────────────
        both_known = (
            normalize_team_name(team_a) in elo_lookup
            and normalize_team_name(team_b) in elo_lookup
        )
        decision = strategy.evaluate_trade(
            prob=prob_for_side,
            edge=edge if yes_ask_f > 0 else None,
            hermes_approved=(review["decision"] == "APPROVE"),
            both_known=both_known,
        )

        if not decision["trade"]:
            reason = decision.get("reason", "unknown")
            rejected_reasons[reason] = rejected_reasons.get(reason, 0) + 1
            continue

        trade_size = decision["size"]

        # ── Execute (simulated against order book) ────────
        ob = order_books.get(result.ticker)
        ob_ask = ob.best_ask if ob and ob.best_ask else yes_ask_f
        ob_bid = ob.best_bid if ob and ob.best_bid else None
        ob_spread = ob.spread if ob else None
        ob_depth = ob.ask_depth if ob else 0.0

        proposal = OrderProposal(
            ticker=result.ticker,
            event_ticker=raw.get("event_ticker", ""),
            side="YES",
            size=trade_size,
            limit_price=min(prob_for_side, 0.99),
            model_prob=prob_for_side,
            expected_edge=edge,
            team_a=team_a,
            team_b=team_b,
            predicted_winner=predicted_winner,
            best_ask=ob_ask,
            best_bid=ob_bid,
            spread=ob_spread,
            ask_depth=ob_depth,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

        sim = executor.simulate_fill_against_book(proposal, order_book=ob)
        sim.risk_flags = review.get("risk_flags", [])
        trades_executed += 1

    exec_summary = executor.ledger.summary()

    logger.info("Pipeline complete: %d orders simulated", trades_executed)

    return {
        "scan": {
            "total": scan.total_scanned,
            "scan_id": scan.scan_id,
            "discovery": scan.discovery_summary,
        },
        "filter": {
            "passed": len(results),
        },
        "execution": exec_summary,
    }


def print_pipeline_summary(summary: dict[str, Any]) -> None:
    """Print a human-readable summary."""
    s = summary.get("scan", {})
    f = summary.get("filter", {})
    e = summary.get("execution", {})

    print()
    print("=" * 60)
    print("  PAPER TRADING PIPELINE v2 — COMPLETE")
    print("=" * 60)
    print(f"  Markets scanned:    {s.get('total', 0)}")
    if s.get("discovery"):
        d = s["discovery"]
        print(f"    Passed filter:    {d.get('passed', 0)}")
        print(f"    Rejected:         {d.get('rejected', 0)}")
        if d.get("rejection_reasons"):
            for reason, count in sorted(
                d["rejection_reasons"].items(), key=lambda x: -x[1]
            )[:5]:
                print(f"      {reason}: {count}")
    print(f"  Tier 1 LoL events: {f.get('passed', 0)}")
    print(f"  Orders simulated:  {e.get('total_orders', 0)}")
    print(f"    Filled:          {e.get('filled', 0)}")
    print(f"    Rejected:        {e.get('rejected', 0)}")
    print(f"  Total notional:    ${e.get('total_notional', 0):.0f}")
    print()
    print("  Ledgers:")
    print("    data/market_discovery.db  — every market seen")
    print("    data/execution_ledger.db  — every simulated order")
    print("=" * 60)
