"""Prediction bot CLI — analyze, predict, evaluate.

Usage:
    prediction-bot audit                          # Run esports market audit
    prediction-bot analyze EVENT_ID              # Prepare research packet
    prediction-bot record                        # Ingest prediction from stdin
    prediction-bot evaluate                      # Evaluate settled predictions
    prediction-bot list                          # List stored predictions
    prediction-bot settle ID WINNER              # Settle a prediction with result
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime, timezone

from prediction_bot.agents.evaluation import (
    evaluate_store,
    format_evaluation_report,
)
from prediction_bot.agents.schema import (
    PredictionRequest,
    build_event,
    normalize_contract,
)
from prediction_bot.agents.workflow import (
    parse_prediction_response,
)
from prediction_bot.kalshi.client import KalshiClient
from prediction_bot.kalshi.discovery import is_esports
from prediction_bot.storage import PredictionRecord, PredictionStore

logger = logging.getLogger(__name__)

MODEL_NAME = "hermes+deepseek"
MODEL_VERSION = "0.1.0"


def _setup_logging(level: str = "INFO") -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
        stream=sys.stderr,
    )


# ---------------------------------------------------------------------------
# Subcommand: audit (delegates to existing audit module)
# ---------------------------------------------------------------------------


def cmd_audit(_args: argparse.Namespace) -> int:
    """Run the esports market audit."""
    from prediction_bot.scripts.audit import run_audit

    _setup_logging()
    report = run_audit()

    print("\nAudit complete.")
    print(f"  Total markets:     {report.total_markets}")
    print(f"  Esports markets:   {report.total_esports_markets}")
    print(f"  By game:           {report.markets_by_game}")
    if report.gap_counts:
        print(f"  Metadata gaps:     {report.gap_counts}")

    return 0


# ---------------------------------------------------------------------------
# Subcommand: analyze
# ---------------------------------------------------------------------------


def cmd_analyze(args: argparse.Namespace) -> int:
    """Fetch a Kalshi event by ticker, normalize it, and output a research packet."""
    _setup_logging()

    event_ticker = args.event_id
    client = KalshiClient()

    try:
        # Fetch markets for this event
        logger.info("Fetching markets for event_ticker=%s ...", event_ticker)
        page = client.get_markets(
            status=args.status,
            event_ticker=event_ticker,
            limit=50,
            mve_filter="exclude",
        )
        markets = page.get("markets", [])

        if not markets:
            # Try fetching without event_ticker filter to search
            logger.info("No markets found for event_ticker. Trying ticker search...")
            # Maybe the user passed a market ticker, not an event ticker
            # Try getting order book to see if it exists
            try:
                client.get_order_book(event_ticker)
                # It exists as a market ticker — need to find via broader search
                logger.info("Found as market ticker. Searching for event...")
                # Get all open esports markets and find matching
                all_raw = client.get_markets_paginated(
                    status="open", max_pages=5, mve_filter="exclude",
                )
                for raw in all_raw:
                    if is_esports(
                        raw.get("title", ""),
                        raw.get("subtitle"),
                        raw.get("yes_sub_title"),
                        raw.get("no_sub_title"),
                    ) and (raw.get("ticker") == event_ticker or raw.get("event_ticker") == event_ticker):
                        markets = [raw]
                        break
            except Exception:
                pass

        if not markets:
            print(f"ERROR: No markets found for event ticker '{event_ticker}'", file=sys.stderr)
            return 1

        # Normalize all markets into contracts, build event from them
        contracts = [normalize_contract(raw) for raw in markets]
        event = build_event(contracts)

        if event is None:
            print(f"ERROR: Could not build event from markets for '{event_ticker}'", file=sys.stderr)
            return 1

        # Build prediction request from the event
        request = PredictionRequest(
            event_id=event.event_id,
            game=event.game,
            tournament=event.tournament,
            participants=event.participants,
            contract_types=event.contract_types,
            start_time=event.start_time,
            available_information={
                "contracts": [
                    {
                        "ticker": c.ticker,
                        "type": c.contract_type,
                        "yes_outcome": c.yes_outcome,
                        "participants": c.participants,
                    }
                    for c in contracts
                ],
            },
        )

        # Output the contract analysis
        print("=" * 60)
        print("  CONTRACT ANALYSIS")
        print("=" * 60)
        print(f"  Event ID:       {event.event_id}")
        print(f"  Sport:          {event.sport or 'unknown'}")
        print(f"  Game:           {event.game or 'N/A'}")
        print(f"  Tournament:     {event.tournament or 'unknown'}")
        print(f"  Participants:   {', '.join(event.participants) if event.participants else 'unknown'}")
        print(f"  Start Time:     {event.start_time.isoformat() if event.start_time else 'unknown'}")
        print(f"  Contract Types: {', '.join(event.contract_types) if event.contract_types else 'unknown'}")
        print(f"  Contracts Found: {len(contracts)}")
        print()

        for c in contracts:
            print(f"    [{c.contract_type}] {c.ticker}")
            if c.map_number:
                print(f"      Map {c.map_number}: {c.yes_outcome}")
            else:
                print(f"      YES = {c.yes_outcome}")
        print()

        # Output the research prompt
        prompt = request.to_research_prompt()

        print("=" * 60)
        print("  RESEARCH PACKET")
        print("=" * 60)
        print()
        print(prompt)
        print()
        print("=" * 60)
        print("  PREDICTION REQUEST (JSON)")
        print("=" * 60)
        print(request.model_dump_json(indent=2))

        return 0

    finally:
        client.close()


# ---------------------------------------------------------------------------
# Subcommand: record
# ---------------------------------------------------------------------------


def cmd_record(args: argparse.Namespace) -> int:
    """Ingest a prediction response from stdin, validate, and store."""
    _setup_logging()

    # Read from stdin
    raw_text = sys.stdin.read()

    if not raw_text.strip():
        print("ERROR: No input provided on stdin.", file=sys.stderr)
        return 1

    store = PredictionStore()

    try:
        response = parse_prediction_response(raw_text)
    except ValueError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1

    # Build record
    record = PredictionRecord(
        event_id=response.event_id,
        timestamp=datetime.now(timezone.utc).isoformat(),
        game=args.game,
        tournament=args.tournament,
        team_a=args.team_a or "",
        team_b=args.team_b or "",
        predicted_winner=response.predicted_winner,
        team_a_probability=response.team_a_probability,
        team_b_probability=response.team_b_probability,
        confidence=response.confidence.value,
        abstain=response.abstain,
        reasoning_summary=response.reasoning_summary,
        key_factors=response.key_factors,
        risk_flags=response.risk_flags,
        model_name=MODEL_NAME,
        model_version=MODEL_VERSION,
    )

    pred_id = store.insert(record)

    # Display summary
    print()
    print("=" * 60)
    print("  PREDICTION SAVED")
    print("=" * 60)
    print(f"  Prediction ID:    {pred_id}")
    print(f"  Event ID:         {response.event_id}")
    print(f"  Predicted Winner: {response.predicted_winner}")
    print(
        f"  Probability:      {response.team_a_probability:.0%} / "
        f"{response.team_b_probability:.0%}"
    )
    print(f"  Confidence:       {response.confidence.value.upper()}")
    if response.abstain:
        print("  ABSTAINED:        insufficient information")
    if response.risk_flags:
        print(f"  Risk Flags:       {', '.join(response.risk_flags)}")
    print()

    return 0


# ---------------------------------------------------------------------------
# Subcommand: evaluate
# ---------------------------------------------------------------------------


def cmd_evaluate(args: argparse.Namespace) -> int:
    """Evaluate all settled predictions."""
    _setup_logging()

    store = PredictionStore()
    report = evaluate_store(store)

    print(format_evaluation_report(report))

    return 0


# ---------------------------------------------------------------------------
# Subcommand: list
# ---------------------------------------------------------------------------


def cmd_list(args: argparse.Namespace) -> int:
    """List stored predictions."""
    _setup_logging()

    store = PredictionStore()

    if args.unsettled:
        records = list(store.iter_unsettled())
    elif args.settled:
        records = list(store.iter_settled())
    else:
        records = list(store.iter_all())

    if not records:
        print("No predictions stored.")
        return 0

    print(f"{'ID':>4}  {'Event ID':<30}  {'Winner':<20}  {'Prob':>6}  {'Conf':>6}  {'Result':<20}")
    print(f"{'='*4}  {'='*30}  {'='*20}  {'='*6}  {'='*6}  {'='*20}")

    for r in records:
        prob = f"{max(r.team_a_probability, r.team_b_probability):.0%}"
        result = r.actual_result or ""
        if r.correct_prediction is True:
            result += " ✓"
        elif r.correct_prediction is False:
            result += " ✗"

        winner = r.predicted_winner[:20]
        if r.abstain:
            winner = "ABSTAIN"

        print(
            f"{r.id:>4}  {r.event_id:<30}  {winner:<20}  "
            f"{prob:>6}  {r.confidence.upper():>6}  {result:<20}"
        )

    print(f"\n{len(records)} prediction(s) total.")
    return 0


# ---------------------------------------------------------------------------
# Subcommand: settle
# ---------------------------------------------------------------------------


def cmd_settle(args: argparse.Namespace) -> int:
    """Record the actual outcome for a prediction."""
    _setup_logging()

    store = PredictionStore()
    record = store.get_by_id(args.id)

    if record is None:
        print(f"ERROR: No prediction found with id={args.id}", file=sys.stderr)
        return 1

    if record.actual_result is not None:
        print(
            f"WARNING: Prediction {args.id} is already settled "
            f"(result={record.actual_result})",
            file=sys.stderr,
        )

    winner = args.winner
    correct = (record.predicted_winner.lower() == winner.lower() and not record.abstain)

    store.update_result(args.id, winner, correct)

    print(f"Settled prediction {args.id}:")
    print(f"  Predicted: {record.predicted_winner}")
    print(f"  Actual:    {winner}")
    print(f"  Correct:   {correct}")

    return 0


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="prediction-bot — esports prediction research system",
    )
    sub = parser.add_subparsers(dest="command", help="Subcommand")

    # --- audit ---
    sub.add_parser("audit", help="Run esports market audit")

    # --- analyze ---
    p_analyze = sub.add_parser("analyze", help="Prepare research packet for an event")
    p_analyze.add_argument("event_id", help="Kalshi event ticker or market ticker")
    p_analyze.add_argument(
        "--status", default="open", help="Market status filter (default: open)"
    )

    # --- record ---
    p_record = sub.add_parser("record", help="Ingest prediction response from stdin")
    p_record.add_argument("--game", help="Game classification")
    p_record.add_argument("--tournament", help="Tournament name")
    p_record.add_argument("--team-a", dest="team_a", help="Team A name")
    p_record.add_argument("--team-b", dest="team_b", help="Team B name")

    # --- evaluate ---
    sub.add_parser("evaluate", help="Evaluate settled predictions")

    # --- list ---
    p_list = sub.add_parser("list", help="List stored predictions")
    p_list.add_argument("--unsettled", action="store_true", help="Show only unsettled")
    p_list.add_argument("--settled", action="store_true", help="Show only settled")

    # --- settle ---
    p_settle = sub.add_parser("settle", help="Record actual outcome for a prediction")
    p_settle.add_argument("id", type=int, help="Prediction ID")
    p_settle.add_argument("winner", help="Name of the actual winning team")

    # --- test-order ---
    p_test = sub.add_parser("test-order", help="Submit 1 contract for API testing")
    p_test.add_argument("--ticker", default="", help="Kalshi market ticker")
    p_test.add_argument("--price", type=float, default=0.01, help="Per-contract price")
    p_test.add_argument("--mode", default="APPROVAL", choices=["PAPER", "APPROVAL", "AUTO"])
    p_test.add_argument("--yes", action="store_true", help="Skip confirmation prompt")

    # --- cancel-test-order ---
    p_cancel = sub.add_parser("cancel-test-order", help="Cancel a test order")
    p_cancel.add_argument("order_id", help="Kalshi order ID to cancel")
    p_cancel.add_argument("--mode", default="APPROVAL", choices=["PAPER", "APPROVAL", "AUTO"])

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        sys.exit(1)

    # Late imports for test-order commands
    from prediction_bot.cli import cmd_cancel_test_order, cmd_test_order  # noqa: F811

    handlers = {
        "audit": cmd_audit,
        "analyze": cmd_analyze,
        "record": cmd_record,
        "evaluate": cmd_evaluate,
        "list": cmd_list,
        "settle": cmd_settle,
        "test-order": cmd_test_order,
        "cancel-test-order": cmd_cancel_test_order,
    }

    handler = handlers.get(args.command)
    if handler is None:
        print(f"Unknown command: {args.command}", file=sys.stderr)
        sys.exit(1)

    try:
        exit_code = handler(args)
    except Exception:
        logger.exception("Command '%s' failed", args.command)
        exit_code = 1

    sys.exit(exit_code)


if __name__ == "__main__":
    main()
