"""Diagnostic: scrape 100 Kalshi markets and dump raw titles + parsed output."""
from __future__ import annotations

import json
from pathlib import Path

from prediction_bot.kalshi.client import KalshiClient

OUT = Path("artifacts/market_dump_100.json")


def main():
    client = KalshiClient()
    try:
        # Fetch raw markets, limited to 100
        result = client.get_markets(status="open", limit=100)
        raw_markets = result.get("markets", [])
        print(f"Fetched {len(raw_markets)} raw markets")

        # Dump first 10 raw titles + full ticker/event_ticker
        print("\n=== First 10 raw market keys ===")
        for i, m in enumerate(raw_markets[:10]):
            print(f"\n[{i}] ticker={m.get('ticker')}  event_ticker={m.get('event_ticker')}")
            print(f"    title={m.get('title')}")
            print(f"    subtitle={m.get('subtitle')}")
            yes_sub = m.get("yes_sub_title")
            no_sub = m.get("no_sub_title")
            if yes_sub:
                print(f"    yes_sub_title={yes_sub}")
            if no_sub:
                print(f"    no_sub_title={no_sub}")

        # Now parse one to see the schema output
        print("\n=== Parsed (first 5) ===")
        for i, raw in enumerate(raw_markets[:5]):
            parsed = client.parse_market(raw)
            print(f"\n[{i}] {parsed.ticker}")
            print(f"    title={parsed.title}")
            print(f"    subtitle={parsed.subtitle}")
            print(f"    yes_sub={parsed.yes_sub_title}")
            print(f"    no_sub={parsed.no_sub_title}")
            print(f"    yes_bid={parsed.yes_bid}  yes_ask={parsed.yes_ask}")
            print(f"    volume={parsed.volume}  oi={parsed.open_interest}")

        # Save full dump
        OUT.parent.mkdir(parents=True, exist_ok=True)
        with open(OUT, "w") as f:
            json.dump({"markets": raw_markets, "cursor": result.get("cursor")}, f, indent=2, default=str)
        print(f"\nFull dump saved to {OUT}")
    finally:
        client.close()


if __name__ == "__main__":
    main()
