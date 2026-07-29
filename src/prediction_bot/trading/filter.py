"""
Market filter — classifies KXLOL markets with rejection reasons.

Assumes input markets are already KXLOL (from scanner with series_ticker).
Filters: esports check → match_winner → Tier 1 tournament.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class FilterResult:
    """Result of filtering a single market."""
    ticker: str
    passed: bool
    reject_reason: str = ""
    contract_type: str = ""
    game: str = ""
    tournament: str = ""
    league_tier: str = ""
    team_a: str = ""
    team_b: str = ""


def filter_market(
    market: dict[str, Any],
    tier1_only: bool = True,
) -> FilterResult:
    """Apply filters to a single KXLOL market.

    Filter stages:
      1. Esports check — is_esports_market()
      2. Tier 1 check — is_major_esports_league()

    (Contract type check is NOT needed — scanner already fetches
    KXLOLGAME only, which are match/game-winner contracts.)

    Args:
        market: Raw Kalshi market dict (must be KXLOLGAME series).
        tier1_only: If True, require Tier 1 major league.

    Returns:
        FilterResult with pass/fail and rejection reason.
    """
    from prediction_bot.agents.schema import normalize_contract
    from prediction_bot.kalshi.discovery import is_esports_market, is_major_esports_league

    ticker = market.get("ticker", "")

    # Stage 1: Esports
    if not is_esports_market(
        ticker=ticker,
        title=market.get("title", ""),
        rules_primary=market.get("rules_primary", ""),
        subtitle=market.get("subtitle"),
        yes_sub_title=market.get("yes_sub_title"),
        no_sub_title=market.get("no_sub_title"),
    ):
        return FilterResult(
            ticker=ticker,
            passed=False,
            reject_reason="not_esports",
        )

    # Normalize
    nc = normalize_contract(market)
    ct = nc.contract_type or ""

    # Stage 2: Tier 1
    is_t1 = is_major_esports_league(
        ticker=ticker,
        title=market.get("title", ""),
        rules_primary=market.get("rules_primary", ""),
        subtitle=market.get("subtitle"),
    )
    league_tier = "tier1" if is_t1 else "tier2_or_lower"

    if tier1_only and not is_t1:
        return FilterResult(
            ticker=ticker,
            passed=False,
            reject_reason="minor_league",
            contract_type=ct,
            game=nc.game or "",
            tournament=nc.tournament or "",
            league_tier=league_tier,
        )

    participants = nc.participants or []
    return FilterResult(
        ticker=ticker,
        passed=True,
        contract_type=ct,
        game=nc.game or "",
        tournament=nc.tournament or "",
        league_tier=league_tier,
        team_a=participants[0] if len(participants) > 0 else "",
        team_b=participants[1] if len(participants) > 1 else "",
    )


def filter_markets(
    markets: list[dict[str, Any]],
    tier1_only: bool = True,
    discovery_db: str = "data/market_discovery.db",
    scan_id: str = "",
    query_params: str = "",
) -> list[FilterResult]:
    """Filter a batch of KXLOL markets and record results in discovery ledger.

    Args:
        markets: Raw KXLOL market dicts from scanner.
        tier1_only: Require Tier 1 leagues.
        discovery_db: Path to discovery DB for recording rejections.
        scan_id: Scan ID for discovery ledger.
        query_params: Query parameters used for the scan.

    Returns:
        List of FilterResults that passed all filters.
    """
    from prediction_bot.trading.scanner import DiscoveryLedger

    ledger = DiscoveryLedger(discovery_db)
    passed: list[FilterResult] = []
    rejected_counts: dict[str, int] = {}

    for m in markets:
        result = filter_market(m, tier1_only=tier1_only)

        ledger.record(
            m,
            scan_id=scan_id,
            query_params=query_params,
            filter_status="passed" if result.passed else "rejected",
            reject_reason=result.reject_reason,
            contract_type=result.contract_type,
            game=result.game,
            tournament=result.tournament,
            league_tier=result.league_tier,
        )

        if result.passed:
            passed.append(result)
        else:
            rejected_counts[result.reject_reason] = (
                rejected_counts.get(result.reject_reason, 0) + 1
            )

    logger.info(
        "Filter: %d passed, %d rejected. Reasons: %s",
        len(passed), len(markets) - len(passed), rejected_counts,
    )

    return passed
