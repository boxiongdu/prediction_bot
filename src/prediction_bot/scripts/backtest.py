"""Phase 2: Historical esports prediction backtesting.

Pipeline:
  Kalshi API (settled) → filter esports+match_winner → normalize
  → strip settlement info → build prediction packet → store prediction
  → reveal outcome → evaluate → calibration report

No trading. No market prices. Match-winner contracts only.

Usage:
    python -m prediction_bot.scripts.backtest fetch     # fetch + filter + normalize
    python -m prediction_bot.scripts.backtest packets   # generate prediction packets
    python -m prediction_bot.scripts.backtest settle    # reveal outcomes + evaluate
    python -m prediction_bot.scripts.backtest full      # run the complete pipeline
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

from prediction_bot.agents.evaluation import (
    EvaluationReport,
    evaluate_predictions,
    format_evaluation_report,
)
from prediction_bot.agents.schema import (
    ContractType,
    build_event,
    normalize_contract,
)
from prediction_bot.agents.workflow import build_prediction_request
from prediction_bot.kalshi.client import KalshiClient
from prediction_bot.kalshi.discovery import is_esports_market
from prediction_bot.storage import PredictionRecord, PredictionStore

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Settlement fields to strip before prediction
# ---------------------------------------------------------------------------

_SETTLEMENT_FIELDS = frozenset({
    "result",
    "settlement_value_dollars",
    "settlement_ts",
    "settlement_timer_seconds",
    "yes_sub_title",   # often leaks which side won
    "no_sub_title",    # often leaks which side won
})


def _setup_logging(level: str = "INFO") -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
        stream=sys.stderr,
    )


# ---------------------------------------------------------------------------
# Step 1: Fetch & filter
# ---------------------------------------------------------------------------


def fetch_settled_esports(
    max_pages: int = 50,
    use_historical: bool = True,
    major_only: bool = True,
) -> list[dict]:
    """Fetch settled Kalshi markets, filter to esports match_winner only.

    Default: uses /historical/markets?mve_filter=exclude (finds older settled
    markets from months ago). Set use_historical=False for /markets?status=settled
    (recent markets only).

    When major_only=True (default), further filters to Tier 1 / major esports
    leagues only — excluding regional circuits, academy, amateur, and qualifiers
    where team data is less reliable.

    Args:
        max_pages: Number of API pages (1000 markets/page for historical,
                   500 for regular). Default 50 → 50000 historical events.
        use_historical: Use /historical/markets (default) or /markets?status=settled.
        major_only: If True, keep only Tier 1 major leagues.

    Returns:
        List of raw market dicts that are esports match_winner contracts
        from major leagues.
    """
    import requests as req_lib
    import time as time_mod

    BASE = "https://external-api.kalshi.com/trade-api/v2"

    if use_historical:
        # /historical/markets with mve_filter=exclude — finds older settled
        # markets (e.g. from May 2026) that /markets?status=settled misses.
        all_raw: list[dict] = []
        cursor: str | None = None
        for _ in range(max_pages):
            url = f"{BASE}/historical/markets?limit=1000&mve_filter=exclude"
            if cursor:
                url += f"&cursor={cursor}"
            resp = req_lib.get(url, timeout=60)
            resp.raise_for_status()
            page = resp.json()
            markets = page.get("markets", [])
            all_raw.extend(markets)
            cursor = page.get("cursor")
            if not cursor or not markets:
                break
            time_mod.sleep(0.3)
        raw = all_raw
        logger.info("Fetched %d markets from /historical/markets.", len(raw))
    else:
        client = KalshiClient()
        try:
            logger.info("Fetching settled markets (max_pages=%d)...", max_pages)
            raw = client.get_markets_paginated(
                status="settled",
                max_pages=max_pages,
                mve_filter="exclude",
            )
            logger.info("Fetched %d settled markets.", len(raw))
        finally:
            client.close()

    # ── Common filter: esports + match_winner or series_winner ──
    filtered: list[dict] = []
    for m in raw:
        if not is_esports_market(
            ticker=m.get("ticker", ""),
            title=m.get("title", ""),
            rules_primary=m.get("rules_primary", ""),
        ):
            continue
        nc = normalize_contract(m)
        if nc.contract_type not in (
            ContractType.MATCH_WINNER.value,
            ContractType.SERIES_WINNER.value,
        ):
            continue
        if m.get("result") not in ("yes", "no"):
            continue
        filtered.append(m)

    logger.info(
        "Filtered to %d esports match/series_winner markets (from %d).",
        len(filtered),
        len(raw),
    )

    # ── Major league filter ──
    if major_only:
        from prediction_bot.kalshi.discovery import is_major_esports_league
        major: list[dict] = []
        minor: list[dict] = []
        for m in filtered:
            if is_major_esports_league(
                ticker=m.get("ticker"),
                title=m.get("title"),
                rules_primary=m.get("rules_primary"),
                subtitle=m.get("subtitle"),
            ):
                major.append(m)
            else:
                minor.append(m)
        logger.info(
            "Major-league filter: kept %d, excluded %d minor/regional.",
            len(major),
            len(minor),
        )
        return major

    return filtered


# ---------------------------------------------------------------------------
# Step 2: Strip settlement fields
# ---------------------------------------------------------------------------


def _strip_settlement(raw: dict) -> dict:
    """Return a copy of the raw market with settlement fields removed."""
    return {k: v for k, v in raw.items() if k not in _SETTLEMENT_FIELDS}


# ---------------------------------------------------------------------------
# Step 3: Build prediction packets
# ---------------------------------------------------------------------------


def build_prediction_packets(
    markets: list[dict],
    output_dir: Path | None = None,
) -> list[dict]:
    """Build Hermes prediction packets from filtered markets.

    Each packet is a JSON-serialisable dict containing:
      - event_id, game, tournament, participants
      - the research prompt text
      - contract_type, start_time
      - a unique market_id (ticker) for outcome lookup

    Settlement fields are stripped before packet generation.

    Args:
        markets: Raw settled market dicts (already filtered).
        output_dir: If provided, write packets to JSON files.

    Returns:
        List of prediction packet dicts.
    """
    if output_dir is None:
        output_dir = Path("data/backtest/packets")
    output_dir.mkdir(parents=True, exist_ok=True)

    packets: list[dict] = []
    for raw in markets:
        # Strip settlement info
        clean = _strip_settlement(raw)

        # Normalize
        nc = normalize_contract(clean)

        # Build event from a single contract (match_winner only)
        event = build_event([nc])
        if event is None:
            continue

        # Build prediction request
        req = build_prediction_request(event)

        packet = {
            "market_id": raw["ticker"],
            "event_id": event.event_id,
            "game": event.game,
            "tournament": event.tournament,
            "participants": event.participants,
            "start_time": event.start_time.isoformat() if event.start_time else None,
            "contract_type": nc.contract_type,
            "research_prompt": req.to_research_prompt(),
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }
        packets.append(packet)

    # Write packets
    packets_path = output_dir / "prediction_packets.json"
    with open(packets_path, "w") as f:
        json.dump(packets, f, indent=2, default=str)

    logger.info(
        "Wrote %d prediction packets to %s", len(packets), packets_path,
    )
    return packets


# ---------------------------------------------------------------------------
# Step 4: Store predictions (without outcomes)
# ---------------------------------------------------------------------------


def store_predictions(
    markets: list[dict],
    predictions: list[dict],
    overwrite: bool = False,
) -> int:
    """Store predictions in the database WITHOUT outcome data.

    Takes raw prediction responses and inserts them as PredictionRecords.
    Use this after Hermes has produced predictions from the packets.

    Args:
        markets: Original raw market dicts (needed for team names, etc.).
        predictions: List of prediction response dicts with at minimum:
            event_id, predicted_winner, team_a_probability, team_b_probability,
            confidence, abstain, reasoning_summary.
        overwrite: If True, delete existing predictions for these event_ids first.

    Returns:
        Number of predictions stored.
    """
    store = PredictionStore()
    stored = 0

    # Build lookup: event_id → raw market
    market_by_event: dict[str, dict] = {}
    for m in markets:
        nc = normalize_contract(m)
        event = build_event([nc])
        if event:
            market_by_event[event.event_id] = m

    for pred in predictions:
        event_id = pred.get("event_id", "")
        m = market_by_event.get(event_id)
        if m is None:
            logger.debug("No market found for event_id=%s, skipping.", event_id)
            continue

        nc = normalize_contract(m)
        participants = nc.participants or []
        team_a = participants[0] if len(participants) > 0 else ""
        team_b = participants[1] if len(participants) > 1 else ""

        record = PredictionRecord(
            event_id=event_id,
            timestamp=datetime.now(timezone.utc).isoformat(),
            game=nc.game,
            tournament=nc.tournament,
            team_a=team_a,
            team_b=team_b,
            predicted_winner=pred.get("predicted_winner", ""),
            team_a_probability=float(pred.get("team_a_probability", 0.5)),
            team_b_probability=float(pred.get("team_b_probability", 0.5)),
            confidence=pred.get("confidence", "low"),
            abstain=bool(pred.get("abstain", False)),
            reasoning_summary=pred.get("reasoning_summary", ""),
            key_factors=pred.get("key_factors", []),
            risk_flags=pred.get("risk_flags", []),
        )
        store.insert(record)
        stored += 1

    logger.info("Stored %d predictions.", stored)
    return stored


# ---------------------------------------------------------------------------
# Step 5: Reveal outcomes + evaluate
# ---------------------------------------------------------------------------


def settle_and_evaluate(
    markets: list[dict],
    output_dir: Path | None = None,
) -> EvaluationReport:
    """Reveal settlement outcomes and evaluate stored predictions.

    For each stored prediction, looks up the actual result from the original
    settled market and records it. Then runs the full evaluation.

    Args:
        markets: Original raw settled market dicts.
        output_dir: Directory for output reports.

    Returns:
        EvaluationReport with calibration statistics.
    """
    store = PredictionStore()

    # Build ticker → result lookup
    result_by_ticker: dict[str, str] = {}
    for m in markets:
        ticker = m.get("ticker", "")
        result = m.get("result")
        if ticker and result in ("yes", "no"):
            result_by_ticker[ticker] = result

    # Also build event_id → (result, yes_sub_title, participants)
    result_by_event: dict[str, str] = {}
    yes_sub_by_event: dict[str, str] = {}
    participants_by_event: dict[str, list[str]] = {}
    for m in markets:
        nc = normalize_contract(m)
        result = m.get("result")
        if result in ("yes", "no"):
            event = build_event([nc])
            if event:
                result_by_event[event.event_id] = result
                yes_sub_by_event[event.event_id] = m.get("yes_sub_title", "")
                participants_by_event[event.event_id] = nc.participants or []

    # Find all unsettled predictions and resolve them
    settled_count = 0
    for record in store.iter_unsettled():
        # Try to match by event_id
        actual = result_by_event.get(record.event_id)
        if actual is None:
            # Fallback: the record's event_id might be a ticker
            actual = result_by_ticker.get(record.event_id)
        if actual is None:
            continue

        # Determine if correct: check yes_sub_title to identify the YES side.
        yes_side = yes_sub_by_event.get(record.event_id, "")
        participants = participants_by_event.get(record.event_id, [])
        correct = False
        if actual == "yes":
            correct = record.predicted_winner.lower() == yes_side.lower()
        elif actual == "no":
            no_side = ""
            if len(participants) >= 2:
                no_side = (
                    participants[1] if participants[0].lower() == yes_side.lower()
                    else participants[0]
                )
            correct = record.predicted_winner.lower() == no_side.lower()

        if record.id is None:
            continue
        store.update_result(record.id, actual, correct)
        settled_count += 1

    logger.info("Settled %d predictions.", settled_count)

    # Evaluate
    all_records = list(store.iter_all())
    report = evaluate_predictions(all_records)

    if output_dir is None:
        output_dir = Path("data/backtest")
    output_dir.mkdir(parents=True, exist_ok=True)

    # Write report
    report_path = output_dir / "calibration_report.md"
    with open(report_path, "w") as f:
        f.write(format_evaluation_report(report))

    # Write JSON
    json_path = output_dir / "calibration_report.json"
    with open(json_path, "w") as f:
        json.dump(
            {
                "total_predictions": report.total_predictions,
                "total_settled": report.total_settled,
                "total_correct": report.total_correct,
                "overall_accuracy": report.overall_accuracy,
                "brier_score": report.brier_score,
                "fair_coin_accuracy": report.fair_coin_accuracy,
                "confidence_breakdowns": [
                    {"confidence": cb.confidence, "total": cb.total,
                     "correct": cb.correct, "accuracy": cb.accuracy}
                    for cb in report.confidence_breakdowns
                ],
                "calibration_bins": [
                    {"bin": cb.bin_label, "count": cb.count,
                     "observed_rate": cb.observed_rate}
                    for cb in report.calibration_bins
                ],
            },
            f,
            indent=2,
        )

    logger.info("Calibration report: %s", report_path)

    return report


# ---------------------------------------------------------------------------
# Full pipeline
# ---------------------------------------------------------------------------


def run_full_backtest(max_pages: int = 50) -> int:
    """Run the complete backtest pipeline: fetch → packets → store → settle → evaluate.

    Args:
        max_pages: Number of API pages for fetching settled markets.
            Default 50 → 50000 historical events.

    Returns:
        Exit code (0 = success, 1 = error).
    """
    # Step 1+2: Fetch + filter
    logger.info("=== Step 1+2: Fetch + filter ===")
    markets = fetch_settled_esports(max_pages=max_pages)
    if not markets:
        logger.error("No esports match_winner markets found.")
        return 1

    # Step 3: Build prediction packets
    logger.info("=== Step 3: Build prediction packets ===")
    output_dir = Path("data/backtest")
    packets = build_prediction_packets(markets, output_dir=output_dir)

    # Step 4: Store predictions (simulated — no Hermes available)
    # In production, you'd feed packets to Hermes and collect responses.
    # Here we store dummy predictions for pipeline validation.
    logger.info(
        "=== Step 4: Store predictions ==="
    )
    logger.info(
        "Generated %d prediction packets. Feed these to Hermes to produce "
        "predictions, then use 'backtest settle' to evaluate.",
        len(packets),
    )

    print(f"\n{'='*60}")
    print("  BACKTEST PIPELINE: FETCH + PACKETS COMPLETE")
    print(f"{'='*60}")
    print(f"  Settled markets fetched:    {len(markets)}")
    print(f"  Prediction packets written:  {len(packets)}")
    print(f"  Output directory:            {output_dir}")
    print("\n  Next steps:")
    print("  1. Feed prediction_packets.json to Hermes")
    print("  2. Run: python -m prediction_bot.scripts.backtest settle")
    print()

    return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(
        description="Phase 2: Historical esports prediction backtesting.",
    )
    sub = parser.add_subparsers(dest="command", help="Subcommand")

    p_fetch = sub.add_parser("fetch", help="Fetch settled esports markets")
    p_fetch.add_argument("--pages", type=int, default=50)

    p_packets = sub.add_parser("packets", help="Generate prediction packets from fetched data")
    p_packets.add_argument("--input", type=Path, default=Path("data/backtest/settled_esports.json"))

    p_settle = sub.add_parser("settle", help="Reveal outcomes and evaluate")
    p_settle.add_argument(
        "--markets", type=Path, default=Path("data/backtest/settled_esports.json"),
    )

    sub.add_parser("full", help="Run complete pipeline")

    args = parser.parse_args()
    _setup_logging()

    if args.command is None:
        parser.print_help()
        sys.exit(1)

    try:
        if args.command == "fetch":
            markets = fetch_settled_esports(max_pages=args.pages)
            out = Path("data/backtest")
            out.mkdir(parents=True, exist_ok=True)
            with open(out / "settled_esports.json", "w") as f:
                json.dump(markets, f, indent=2, default=str)
            print(f"Saved {len(markets)} markets to {out / 'settled_esports.json'}")

        elif args.command == "packets":
            with open(args.input) as f:
                markets = json.load(f)
            build_prediction_packets(markets)

        elif args.command == "settle":
            with open(args.markets) as f:
                markets = json.load(f)
            report = settle_and_evaluate(markets)
            print(format_evaluation_report(report))

        elif args.command == "full":
            sys.exit(run_full_backtest())

    except Exception:
        logger.exception("Backtest failed.")
        sys.exit(1)


if __name__ == "__main__":
    main()
