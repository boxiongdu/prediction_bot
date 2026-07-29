"""Kalshi market collection script.

Fetches all open Kalshi markets, splits them into sports and non-sports,
and saves both datasets for analysis and testing.

Uses:
  - Kalshi API (mve_filter='exclude' to remove multi-event parlays)
  - is_sports_market() classifier (ticker prefix + text fallback)

Output:
  data/raw/kalshi_market_sample.json       — sports markets (for normalization)
  data/raw/kalshi_non_sports_sample.json   — non-sports (for parser robustness testing)

Usage:
    python -m prediction_bot.scripts.collect    # default: 20 pages (~10k live markets)
    python -m prediction_bot.scripts.collect --pages 100
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

from prediction_bot.kalshi.client import KalshiClient

logger = logging.getLogger(__name__)


def _setup_logging(level: str = "INFO") -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
        stream=sys.stderr,
    )


def run_collect(max_pages: int = 20, output_dir: Path | None = None) -> None:
    """Fetch Kalshi markets, split sports/non-sports, and save.

    Args:
        max_pages: Number of API pages to fetch (500 markets/page).
        output_dir: Directory for output files. Defaults to data/raw/.
    """
    if output_dir is None:
        output_dir = Path("data/raw")
    output_dir.mkdir(parents=True, exist_ok=True)

    client = KalshiClient()
    try:
        # ── Fetch ──────────────────────────────────────────────
        logger.info(
            "Fetching open Kalshi markets (max_pages=%d, mve_filter=exclude)...",
            max_pages,
        )
        raw_markets = client.get_markets_paginated(
            status="open",
            max_pages=max_pages,
            mve_filter="exclude",
        )
        logger.info("Fetched %d raw markets.", len(raw_markets))

        # ── Classify: esports vs excluded ──────────────────────
        from prediction_bot.kalshi.discovery import split_markets_esports_excluded
        esports, excluded = split_markets_esports_excluded(raw_markets)
        logger.info(
            "Classification: %d esports, %d excluded (%d total).",
            len(esports),
            len(excluded),
            len(raw_markets),
        )

        assert len(esports) + len(excluded) == len(raw_markets), (
            f"Split mismatch: {len(esports)} + {len(excluded)} != {len(raw_markets)}"
        )

        # ── Save ───────────────────────────────────────────────
        esports_path = output_dir / "esports_markets.json"
        excluded_path = output_dir / "excluded_sports.json"

        for path, data, label in [
            (esports_path, esports, "esports"),
            (excluded_path, excluded, "excluded"),
        ]:
            with open(path, "w") as f:
                json.dump(data, f, indent=2, default=str)
            size_kb = path.stat().st_size / 1024
            logger.info("  %s → %s (%.1f KB, %d markets)", label, path, size_kb, len(data))

        # ── Summary ────────────────────────────────────────────
        print(f"\n{'='*50}")
        print("  MARKET COLLECTION COMPLETE")
        print(f"{'='*50}")
        print(f"  Total fetched:    {len(raw_markets)}")
        print(f"  Esports markets:  {len(esports)} ({_pct(len(esports), len(raw_markets))})")
        print(f"  Excluded:         {len(excluded)} ({_pct(len(excluded), len(raw_markets))})")
        print("\n  Output files:")
        print(f"    {esports_path}")
        print(f"    {excluded_path}")
        print()

    finally:
        client.close()


def _pct(part: int, whole: int) -> str:
    if whole == 0:
        return "0.0%"
    return f"{part / whole * 100:.1f}%"


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(
        description="Collect Kalshi markets, split sports vs non-sports.",
    )
    parser.add_argument(
        "--pages",
        type=int,
        default=20,
        help="Number of API pages to fetch (500 markets/page). Default: 20",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Output directory. Default: data/raw/",
    )
    args = parser.parse_args()

    _setup_logging()
    logger.info("Starting market collection...")

    try:
        run_collect(max_pages=args.pages, output_dir=args.output_dir)
    except Exception:
        logger.exception("Collection failed.")
        sys.exit(1)


if __name__ == "__main__":
    main()
