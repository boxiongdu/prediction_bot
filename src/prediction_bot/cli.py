"""CLI for prediction-bot paper/live trading commands.

Usage:
  prediction-bot test-order [--ticker TICKER] [--price PRICE]
  prediction-bot cancel-test-order ORDER_ID
"""
from __future__ import annotations

import argparse
import logging
import sys

logger = logging.getLogger(__name__)


def cmd_test_order(args: argparse.Namespace) -> None:
    """Submit exactly 1 contract for API connectivity testing."""
    from prediction_bot.trading.order_client import KalshiOrderClient

    # Fetch a KXLOLGAME market if no ticker specified
    ticker = args.ticker
    if not ticker:
        import requests
        import time as tmod
        try:
            url = (
                "https://external-api.kalshi.com/trade-api/v2/markets"
                "?status=open&limit=5&series_ticker=KXLOLGAME&mve_filter=exclude"
            )
            resp = requests.get(url, timeout=30)
            resp.raise_for_status()
            data = resp.json()
            markets = data.get("markets", [])
            if markets:
                ticker = markets[0]["ticker"]
                print(f"No ticker specified. Using: {ticker}")
            else:
                print("ERROR: No open KXLOLGAME markets found.")
                sys.exit(1)
        except Exception as e:
            print(f"ERROR fetching markets: {e}")
            sys.exit(1)

    print(f"\n{'='*50}")
    print(f"  KALSHI API CONNECTIVITY TEST")
    print(f"{'='*50}")
    print(f"  Ticker:  {ticker}")
    print(f"  Price:   ${args.price:.4f} per contract")
    print(f"  Count:   1")
    print(f"  Mode:    {args.mode}")
    print(f"{'='*50}")

    # Validate market
    try:
        import requests
        resp = requests.get(
            f"https://external-api.kalshi.com/trade-api/v2/markets/{ticker}",
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        market = data.get("market", data)
        status = market.get("status", "")
        if status not in ("open", "active"):
            print(f"ERROR: Market status is '{status}', not 'open'/'active'.")
            sys.exit(1)
        print(f"  Market status: {status} ✓")
        print(f"  Yes ask:       ${float(market.get('yes_ask', 0)):.4f}")
        print(f"  Yes bid:       ${float(market.get('yes_bid', 0)):.4f}")
    except Exception as e:
        print(f"ERROR validating market: {e}")
        sys.exit(1)

    client = KalshiOrderClient(mode=args.mode)
    result = client.test_order(
        ticker=ticker,
        price=args.price,
        require_confirm=not args.yes,
    )

    print()
    print(f"  Status:         {result.status}")
    print(f"  Order ID:       {result.order_id}")
    print(f"  Client ID:      {result.client_order_id}")
    print(f"  Remaining:      {result.remaining_count}")
    print(f"  Message:        {result.message}")

    if result.status == "accepted":
        print()
        print("  To cancel: prediction-bot cancel-test-order", result.order_id)

    sys.exit(0 if result.status in ("accepted", "simulated") else 1)


def cmd_cancel_test_order(args: argparse.Namespace) -> None:
    """Cancel a previously submitted test order."""
    from prediction_bot.trading.order_client import KalshiOrderClient

    client = KalshiOrderClient(mode=args.mode)
    result = client.cancel_test_order(args.order_id)

    print()
    print(f"  Status:   {result.status}")
    print(f"  Order ID: {result.order_id}")
    print(f"  Message:  {result.message}")

    sys.exit(0 if result.status in ("cancelled", "simulated_cancelled") else 1)


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="prediction-bot",
        description="Paper/live trading CLI for Kalshi LoL prediction markets.",
    )
    sub = parser.add_subparsers(dest="command")

    # test-order
    p_test = sub.add_parser("test-order", help="Submit 1 contract for API testing")
    p_test.add_argument("--ticker", default="", help="Kalshi market ticker")
    p_test.add_argument("--price", type=float, default=0.01, help="Per-contract price")
    p_test.add_argument("--mode", default="APPROVAL", choices=["PAPER", "APPROVAL", "AUTO"])
    p_test.add_argument("--yes", action="store_true", help="Skip confirmation prompt")

    # cancel-test-order
    p_cancel = sub.add_parser("cancel-test-order", help="Cancel a test order")
    p_cancel.add_argument("order_id", help="Kalshi order ID to cancel")
    p_cancel.add_argument("--mode", default="APPROVAL", choices=["PAPER", "APPROVAL", "AUTO"])

    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    if args.command == "test-order":
        cmd_test_order(args)
    elif args.command == "cancel-test-order":
        cmd_cancel_test_order(args)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
