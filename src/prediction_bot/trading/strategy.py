"""
Trade strategy — prediction, Elo lookup, and Hermes review.

Shared between pipeline versions. No I/O — pure computation.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────────
# Team name normalization — Kalshi → Oracle Elixir
# ──────────────────────────────────────────────────────────────────────

# Kalshi sometimes uses slightly different names than Oracle's Elixir.
# This small mapping resolves the few Tier 1 mismatches.
_KALSHI_TO_ELIXIR: dict[str, str] = {
    "Dplus KIA": "Dplus Kia",
    "Nongshim Red Force": "Nongshim RedForce",
    "OKSavingsBank BRION": "HANJIN BRION",
}


def normalize_team_name(name: str) -> str:
    """Map a Kalshi team name to its Oracle Elixir equivalent."""
    return _KALSHI_TO_ELIXIR.get(name, name)


# ──────────────────────────────────────────────────────────────────────
# Team Elo lookup
# ──────────────────────────────────────────────────────────────────────


def build_team_elo_lookup(
    data_path: str = "data/tier1_matches_enriched.parquet",
) -> dict[str, float]:
    """Build team Elo ratings from all historical Oracle's Elixir data."""
    import pandas as pd

    mdf = pd.read_parquet(data_path)
    mdf = mdf.sort_values("date")

    elos: dict[str, float] = {}
    k = 32
    home = 30

    for _, row in mdf.iterrows():
        ta = row["team_blue"]
        tb = row["team_red"]
        ea = elos.get(ta, 1500.0)
        eb = elos.get(tb, 1500.0)
        expected = 1.0 / (1.0 + 10 ** ((eb - (ea + home)) / 400.0))
        delta = k * (row["blue_wins"] - expected)
        elos[ta] = ea + delta
        elos[tb] = eb - delta

    logger.info("Elo lookup: %d teams", len(elos))
    return elos


def predict_match(
    team_a: str,
    team_b: str,
    elo_lookup: dict[str, float],
) -> dict[str, Any]:
    """Win probability for team_a (blue side assumed)."""
    home_adv = 30
    ta = normalize_team_name(team_a)
    tb = normalize_team_name(team_b)
    ea = elo_lookup.get(ta, 1500.0)
    eb = elo_lookup.get(tb, 1500.0)
    elo_diff = (ea + home_adv) - eb
    prob = 1.0 / (1.0 + 10 ** (-elo_diff / 400.0))

    return {
        "probability": round(float(prob), 4),
        "elo_a": round(float(ea), 1),
        "elo_b": round(float(eb), 1),
        "elo_diff": round(float(elo_diff), 1),
        "model": "elo-k32-home30",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


# ──────────────────────────────────────────────────────────────────────
# Hermes risk review
# ──────────────────────────────────────────────────────────────────────

HIGH_RISK_TEAMS: set[str] = {
    "KT Rolster", "Dplus Kia", "DRX", "Kiwoom DRX",
    "Nongshim RedForce", "FearX", "HANJIN BRION", "DN SOOPers",
    "GIANTX", "SK Gaming", "Team Heretics", "Rogue",
    "Immortals", "Dignitas", "Shopify Rebellion",
}


def hermes_review(
    team_a: str,
    team_b: str,
    model_prob: float,
    elo_lookup: dict[str, float],
    market_yes_ask: float | None = None,
    tournament: str | None = None,
) -> dict[str, Any]:
    """Hermes risk review — APPROVE or REJECT."""
    reasons: list[str] = []
    risk_flags: list[str] = []
    reject = False

    # Normalize names for lookup
    ta = normalize_team_name(team_a)
    tb = normalize_team_name(team_b)

    # Unknown teams
    unknown_a = ta not in elo_lookup
    unknown_b = tb not in elo_lookup
    if unknown_a or unknown_b:
        reject = True
        unknown_list = []
        if unknown_a:
            unknown_list.append(team_a)
        if unknown_b:
            unknown_list.append(team_b)
        reasons.append(
            f"Unknown team(s): {', '.join(unknown_list)} — no historical data"
        )
        risk_flags.append("unknown_team")

    # Edge check
    if market_yes_ask is not None and market_yes_ask > 0:
        edge = model_prob - market_yes_ask
        if edge < 0:
            reject = True
            reasons.append(
                f"Negative edge ({edge:+.1%}): model={model_prob:.1%} vs "
                f"market={market_yes_ask:.1%}"
            )
            risk_flags.append("negative_edge")
        elif edge < 0.03:
            reasons.append(f"Thin edge ({edge:+.1%})")
            risk_flags.append("thin_edge")

    # High-variance teams
    if ta in HIGH_RISK_TEAMS or tb in HIGH_RISK_TEAMS:
        risk_flags.append("high_variance_team")

    # Extreme probabilities
    if model_prob > 0.85 or model_prob < 0.15:
        risk_flags.append("extreme_probability")

    # International
    if tournament and any(
        t in str(tournament).upper()
        for t in ["MSI", "WORLDS", "EWC", "FIRST STAND"]
    ):
        risk_flags.append("international_tournament")

    return {
        "decision": "REJECT" if reject else "APPROVE",
        "reasons": reasons,
        "risk_flags": risk_flags,
    }
