"""Sports market audit CLI.

Downloads currently open Kalshi markets, normalizes every market via
normalize_contract(), and produces CSV/JSON/markdown reports with
contract-type, sport, and game breakdowns.

Usage:
    python -m prediction_bot.scripts.audit          # default output
    prediction-bot                                   # if installed via pip
"""

from __future__ import annotations

import csv
import json
import logging
import sys
from decimal import Decimal
from pathlib import Path
from typing import Any

import numpy as np

from prediction_bot.agents.schema import ContractType, normalize_contract
from prediction_bot.config.paths import artifacts_dir
from prediction_bot.data.schema import (
    EsportsMarketAuditEntry,
    FeasibilityReport,
    MetadataGap,
)
from prediction_bot.kalshi.client import KalshiClient
from prediction_bot.kalshi.discovery import is_esports_market

logger = logging.getLogger(__name__)


def _setup_logging(level: str = "INFO") -> None:
    """Configure structured logging."""
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
        stream=sys.stderr,
    )


def _compute_stats(values: list[float]) -> dict[str, float]:
    """Compute summary statistics for a list of values."""
    _empty = {
        "count": 0, "mean": 0.0, "median": 0.0,
        "p25": 0.0, "p75": 0.0, "min": 0.0, "max": 0.0,
    }
    if not values:
        return _empty
    arr = np.array([v for v in values if v is not None], dtype=np.float64)
    if len(arr) == 0:
        return _empty
    return {
        "count": int(len(arr)),
        "mean": float(np.mean(arr)),
        "median": float(np.median(arr)),
        "p25": float(np.percentile(arr, 25)),
        "p75": float(np.percentile(arr, 75)),
        "min": float(np.min(arr)),
        "max": float(np.max(arr)),
    }


def _decimal_to_float(d: Decimal | None) -> float | None:
    """Convert Decimal to float for statistics, returning None for None."""
    if d is None:
        return None
    return float(d)


def _build_audit_entry(
    raw: dict[str, Any],
    nc: Any,  # NormalizedContract
) -> EsportsMarketAuditEntry:
    """Build an audit entry from a raw market dict and its NormalizedContract.

    Reads price/volume from raw dict. Reads contract_type/sport/game from
    the NormalizedContract produced by normalize_contract().
    """
    gaps: list[str] = []

    # ── Normalized gaps ──
    ct: str | None = getattr(nc, "contract_type", None)
    game: str | None = getattr(nc, "game", None)
    sport: str | None = getattr(nc, "sport", None)
    close_time_val = getattr(nc, "close_time", None)

    if ct is None or ct == ContractType.OTHER.value:
        gaps.append(MetadataGap.UNCLASSIFIED_CONTRACT_TYPE.value)

    if game is None:
        gaps.append(MetadataGap.UNCLASSIFIED_GAME.value)

    if sport is None:
        gaps.append(MetadataGap.UNCLASSIFIED_SPORT.value)

    # ── Price/volume gaps (from raw dict) ──
    from prediction_bot.data.schema import _parse_fp_quantity, _parse_price_dollars
    yes_bid = _parse_price_dollars(raw.get("yes_bid_dollars"))
    yes_ask = _parse_price_dollars(raw.get("yes_ask_dollars"))
    no_bid = _parse_price_dollars(raw.get("no_bid_dollars"))
    no_ask = _parse_price_dollars(raw.get("no_ask_dollars"))

    if yes_bid is None or yes_bid == Decimal("0"):
        gaps.append(MetadataGap.MISSING_BID.value)
    if yes_ask is None or yes_ask == Decimal("0"):
        gaps.append(MetadataGap.MISSING_ASK.value)

    close_time = close_time_val
    if close_time is None:
        gaps.append(MetadataGap.MISSING_CLOSE_TIME.value)

    volume = _parse_fp_quantity(raw.get("volume_fp"))
    if volume is None or volume == Decimal("0"):
        gaps.append(MetadataGap.ZERO_VOLUME.value)

    open_interest = _parse_fp_quantity(raw.get("open_interest_fp"))
    if open_interest is None or open_interest == Decimal("0"):
        gaps.append(MetadataGap.ZERO_OPEN_INTEREST.value)

    # ── Spread ──
    spread = None
    if yes_bid is not None and yes_ask is not None:
        spread = yes_ask - yes_bid

    return EsportsMarketAuditEntry(
        title=raw.get("title", ""),
        ticker=raw.get("ticker", ""),
        event_ticker=raw.get("event_ticker", ""),
        yes_sub_title=raw.get("yes_sub_title"),
        no_sub_title=raw.get("no_sub_title"),
        contract_type=ct,
        sport=sport,
        game=game,
        estimated_game=game,  # deprecated alias
        category=raw.get("category"),
        close_time=close_time,
        volume=volume,
        open_interest=open_interest,
        yes_bid=yes_bid,
        yes_ask=yes_ask,
        no_bid=no_bid,
        no_ask=no_ask,
        spread=spread,
        last_price=_parse_price_dollars(raw.get("last_price_dollars")),
        bid_size=_parse_fp_quantity(raw.get("yes_bid_size_fp")),
        ask_size=_parse_fp_quantity(raw.get("yes_ask_size_fp")),
        liquidity=_parse_price_dollars(raw.get("liquidity_dollars")),
        status=raw.get("status"),
        metadata_gaps=gaps,
    )


def run_audit(
    client: KalshiClient | None = None,
    output_dir: Path | None = None,
) -> FeasibilityReport:
    """Run the full sports market audit using normalize_contract().

    Pipeline:
      Kalshi API → raw markets → normalize_contract() → audit entries → report

    Args:
        client: A KalshiClient instance. If None, one is created.
        output_dir: Directory for output files. Defaults to artifacts/ dir.

    Returns:
        A FeasibilityReport with summary statistics and raw entries.
    """
    if output_dir is None:
        output_dir = artifacts_dir()
    output_dir.mkdir(parents=True, exist_ok=True)

    own_client = client is None
    if own_client:
        client = KalshiClient()

    try:
        # ── Fetch ──────────────────────────────────────────────
        logger.info("Fetching open markets from Kalshi (excluding multi-event parlays)...")
        raw_markets = client.get_markets_paginated(
            status="open", max_pages=5, mve_filter="exclude",
        )
        logger.info("Fetched %d raw markets.", len(raw_markets))

        # ── Normalize every market ─────────────────────────────
        entries: list[EsportsMarketAuditEntry] = []
        for raw in raw_markets:
            try:
                nc = normalize_contract(raw)
                entries.append(_build_audit_entry(raw, nc))
            except Exception:
                logger.debug(
                    "Skipping unparseable market: %s",
                    raw.get("ticker", "unknown"),
                )
                continue

        logger.info("Normalized %d entries.", len(entries))

        # ── Filter to esports only ─────────────────────────────
        esports_entries: list[EsportsMarketAuditEntry] = [
            e for e in entries
            if is_esports_market(
                ticker=e.ticker,
                title=e.title,
            )
        ]

        logger.info(
            "Esports markets: %d (non-esports filtered: %d).",
            len(esports_entries),
            len(entries) - len(esports_entries),
        )

        # ── Statistics ─────────────────────────────────────────
        spread_values = [
            _decimal_to_float(e.spread) for e in esports_entries if e.spread is not None
        ]
        volume_values = [
            _decimal_to_float(e.volume) for e in esports_entries if e.volume is not None
        ]
        oi_values = [
            _decimal_to_float(e.open_interest)
            for e in esports_entries if e.open_interest is not None
        ]

        # Markets by game
        by_game: dict[str, int] = {}
        for e in esports_entries:
            g = e.game or "unclassified"
            by_game[g] = by_game.get(g, 0) + 1

        # Markets by contract type
        by_contract_type: dict[str, int] = {}
        for e in esports_entries:
            ct = e.contract_type or "unclassified"
            by_contract_type[ct] = by_contract_type.get(ct, 0) + 1

        # Markets by sport
        by_sport: dict[str, int] = {}
        for e in esports_entries:
            s = e.sport or "unclassified"
            by_sport[s] = by_sport.get(s, 0) + 1

        # Legacy: markets by category (old classify_market_type)
        by_category: dict[str, int] = {}
        for e in esports_entries:
            by_category[e.contract_type or "other"] = (
                by_category.get(e.contract_type or "other", 0) + 1
            )

        # Gap counts
        gap_counts: dict[str, int] = {}
        for e in esports_entries:
            for gap in e.metadata_gaps:
                gap_counts[gap] = gap_counts.get(gap, 0) + 1

        missing_meta = sum(1 for e in esports_entries if e.metadata_gaps)

        ambiguous = [
            e.title for e in esports_entries if e.contract_type is None
        ]

        report = FeasibilityReport(
            total_markets=len(raw_markets),
            total_sports_markets=len(esports_entries),
            total_esports_markets=sum(
                1 for e in esports_entries if e.sport == "esports"
            ),
            markets_by_game=by_game,
            markets_by_contract_type=by_contract_type,
            markets_by_sport=by_sport,
            markets_by_category=by_category,
            markets_with_missing_metadata=missing_meta,
            gap_counts=gap_counts,
            spread_stats=_compute_stats(spread_values),
            volume_stats=_compute_stats(volume_values),
            open_interest_stats=_compute_stats(oi_values),
            markets_with_ambiguous_title=ambiguous,
            raw_entries=esports_entries,
        )

        # ── Write output files ─────────────────────────────────
        _write_csv_report(esports_entries, output_dir / "esports_markets.csv")
        _write_json_report(report, output_dir / "esports_markets.json")
        _write_normalization_markdown(report, output_dir / "normalization_report.md")

        logger.info("Reports written to %s", output_dir)
        return report

    finally:
        if own_client and client is not None:
            client.close()


def _write_csv_report(entries: list[EsportsMarketAuditEntry], path: Path) -> None:
    """Write audit entries to CSV."""
    fieldnames = [
        "title", "ticker", "event_ticker", "yes_sub_title", "no_sub_title",
        "contract_type", "sport", "game",
        "estimated_game", "category",
        "close_time", "volume", "open_interest",
        "yes_bid", "yes_ask", "no_bid", "no_ask",
        "spread", "last_price", "bid_size", "ask_size", "liquidity",
        "status", "metadata_gaps", "snapshot_at",
    ]
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for entry in entries:
            row = entry.model_dump(mode="json")
            row["metadata_gaps"] = "|".join(entry.metadata_gaps)
            row["snapshot_at"] = entry.snapshot_at.isoformat()
            row["close_time"] = entry.close_time.isoformat() if entry.close_time else ""
            writer.writerow(row)
    logger.info("CSV report: %s (%d rows)", path, len(entries))


def _write_json_report(report: FeasibilityReport, path: Path) -> None:
    """Write the full feasibility report as JSON."""
    data = report.model_dump(mode="json")
    with open(path, "w") as f:
        json.dump(data, f, indent=2, default=str)
    logger.info("JSON report: %s", path)


def _write_normalization_markdown(report: FeasibilityReport, path: Path) -> None:
    """Write a human-readable normalization report in markdown."""

    lines: list[str] = []
    lines.append("# Kalshi Market Normalization Report")
    lines.append(f"\nGenerated: {report.generated_at.isoformat()}\n")

    lines.append("## Summary\n")
    lines.append(f"- Total markets fetched: {report.total_markets}")
    lines.append(f"- Sports markets: {report.total_sports_markets}")
    lines.append(f"- Esports markets: {report.total_esports_markets}")
    lines.append(f"- Markets with metadata gaps: {report.markets_with_missing_metadata}")
    lines.append(f"- Unclassified (ambiguous) markets: {len(report.markets_with_ambiguous_title)}")

    if report.gap_counts:
        lines.append("\n### Metadata Gap Breakdown\n")
        for gap_name, count in sorted(report.gap_counts.items(), key=lambda x: -x[1]):
            lines.append(f"- {gap_name}: {count}")

    lines.append("\n## Markets by Contract Type\n")
    for ct, count in sorted(report.markets_by_contract_type.items(), key=lambda x: -x[1]):
        lines.append(f"- {ct}: {count}")

    lines.append("\n## Markets by Sport\n")
    for sport, count in sorted(report.markets_by_sport.items(), key=lambda x: -x[1]):
        lines.append(f"- {sport}: {count}")

    lines.append("\n## Markets by Game\n")
    for game, count in sorted(report.markets_by_game.items(), key=lambda x: -x[1]):
        lines.append(f"- {game}: {count}")

    lines.append("\n## Spread Statistics\n")
    ss = report.spread_stats
    lines.append(f"- Count: {ss.get('count', 0)}")
    lines.append(f"- Mean: {ss.get('mean', 0):.4f}")
    lines.append(f"- Median: {ss.get('median', 0):.4f}")
    lines.append(f"- 25th percentile: {ss.get('p25', 0):.4f}")
    lines.append(f"- 75th percentile: {ss.get('p75', 0):.4f}")
    lines.append(f"- Min: {ss.get('min', 0):.4f}")
    lines.append(f"- Max: {ss.get('max', 0):.4f}")

    if report.markets_with_ambiguous_title:
        lines.append("\n## Markets with Unclassified Contract Types\n")
        for title in report.markets_with_ambiguous_title[:30]:
            lines.append(f"- {title}")
        if len(report.markets_with_ambiguous_title) > 30:
            lines.append(
                f"\n... and {len(report.markets_with_ambiguous_title) - 30} more.",
            )

    lines.append("\n## Limitations\n")
    lines.append(
        "- Uses normalize_contract() combining ticker prefix, rules_primary, and title."
    )
    lines.append(
        "- Non-sports markets (weather, commodities, politics) are filtered by is_esports_market()."
    )
    lines.append(
        "- Contract type classification is driven by ticker prefix (100% coverage for known)."
    )

    with open(path, "w") as f:
        f.write("\n".join(lines))
    logger.info("Normalization markdown: %s", path)


def main() -> None:
    """CLI entry point for the sports market audit."""
    _setup_logging()
    logger.info("Starting Kalshi sports market audit...")

    try:
        report = run_audit()
        logger.info(
            "Audit complete. %d sports markets found.",
            report.total_sports_markets,
        )

        # Print a brief summary to stdout
        print("\nAudit complete.")
        print(f"  Total markets:       {report.total_markets}")
        print(f"  Sports markets:      {report.total_sports_markets}")
        print(f"  Esports markets:     {report.total_esports_markets}")
        print(f"  By contract type:    {report.markets_by_contract_type}")
        print(f"  By sport:            {report.markets_by_sport}")
        print(f"  By game:             {report.markets_by_game}")
        if report.gap_counts:
            print(f"  Metadata gaps:       {report.gap_counts}")
        print("\nOutput files:")
        artifacts = artifacts_dir()
        for f in sorted(artifacts.glob("*")):
            if f.is_file():
                print(f"  {f}")
    except Exception:
        logger.exception("Audit failed with an error.")
        sys.exit(1)


if __name__ == "__main__":
    main()
