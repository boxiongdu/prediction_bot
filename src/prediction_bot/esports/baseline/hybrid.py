"""
Hybrid prediction system: statistical baseline + Hermes review.

Model A: Elo/logistic regression base probability
Model B: Base probability + Hermes review adjustment (±10%)

Hermes reviews each prediction and adjusts based on:
  - Known roster changes (2024→2025→2026 transitions)
  - Tournament / playoff context
  - Recent trajectory divergence from Elo
  - Upset-prone matchups
"""
from __future__ import annotations

import json
import logging
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────────
# Known roster / trajectory adjustments (2026 season context)
# ──────────────────────────────────────────────────────────────────────

# Teams with significant roster upgrades in 2026 vs 2025
ROSTER_UPGRADES_2026: dict[str, float] = {
    # Gen.G added Ruler (world-class ADC) — stronger in 2026
    "Gen.G": +0.03,
    # Hanwha Life upgraded roster significantly
    "Hanwha Life Esports": +0.03,
    # KT Rolster rebuilt with strong pieces
    "KT Rolster": +0.02,
    # Dplus Kia — ShowMaker still elite, roster stabilized
    "Dplus Kia": +0.02,
    # Top Esports (LPL) upgraded jungle
    "Top Esports": +0.02,
}

# Teams with significant roster downgrades or instability
ROSTER_DOWNGRADES_2026: dict[str, float] = {
    # T1 lost Zeus (top), replaced with Doran — slight downgrade
    "T1": -0.02,
    # DRX / Kiwoom DRX — rebuilding
    "Kiwoom DRX": -0.02,
    "DRX": -0.02,
    # Nongshim RedForce — consistently lower tier
    "Nongshim RedForce": -0.02,
    # FearX — bottom tier
    "FearX": -0.02,
    # BRO — bottom tier
    "BRO": -0.02,
    # DN SOOPers — bottom/mid tier
    "DN SOOPers": -0.02,
}

# Teams with high variance / upset potential
HIGH_VARIANCE_TEAMS: set[str] = {
    "KT Rolster",      # Can beat anyone or lose to anyone
    "Dplus Kia",       # High ceiling, inconsistent
    "Fnatic",          # Historically volatile
    "MAD Lions KOI",   # Volatile
    "Cloud9",          # NA volatility
    "100 Thieves",     # NA volatility
}

# Tournament context multipliers
# Playoff matches have higher stakes — favorites perform closer to expectation
PLAYOFF_ADJUSTMENT = 0.015  # Slightly favor the favorite in playoffs


def hermes_review_prediction(packet: dict[str, Any]) -> dict[str, Any]:
    """Review a statistical prediction and produce an adjustment.

    Hermes acts as a reviewer, not a predictor. It adjusts the base
    probability by -10% to +10% based on domain knowledge.

    Returns a dict with the adjustment, adjusted probability, and reasoning.
    """
    base = packet["base_probability"]
    team_a = packet["team_a"]
    team_b = packet["team_b"]
    league = packet.get("league", "")
    playoffs = packet.get("playoffs", 0)
    elo_diff = packet.get("elo_diff", 0)

    adjustment = 0.0
    reasons: list[str] = []
    risk_flags: list[str] = []

    # ── Roster adjustments ────────────────────────────────
    a_up = ROSTER_UPGRADES_2026.get(team_a, 0)
    a_down = ROSTER_DOWNGRADES_2026.get(team_a, 0)
    b_up = ROSTER_UPGRADES_2026.get(team_b, 0)
    b_down = ROSTER_DOWNGRADES_2026.get(team_b, 0)

    if a_up:
        adjustment += a_up
        reasons.append(f"{team_a} roster upgrade (+{a_up:.0%})")
    if a_down:
        adjustment += a_down
        reasons.append(f"{team_a} roster downgrade ({a_down:.0%})")
    if b_up:
        adjustment -= b_up  # Opponent stronger → reduce team_a probability
        reasons.append(f"{team_b} roster upgrade (-{b_up:.0%})")
    if b_down:
        adjustment -= b_down  # Opponent weaker → increase
        reasons.append(f"{team_b} roster downgrade (+{-b_down:.0%})")

    # ── Tournament context ────────────────────────────────
    if playoffs:
        # In playoffs, the stronger team (by Elo) tends to perform
        if elo_diff > 50:
            adjustment += PLAYOFF_ADJUSTMENT
            reasons.append(f"playoff favorite boost (+{PLAYOFF_ADJUSTMENT:.1%})")
        elif elo_diff < -50:
            adjustment -= PLAYOFF_ADJUSTMENT
            reasons.append(f"playoff favorite boost (-{PLAYOFF_ADJUSTMENT:.1%})")

    # ── International tournament context ──────────────────
    international = {"MSI", "WLDs", "EWC", "FST"}
    if league in international and abs(elo_diff) > 100:
        # Slightly reduce favorite's edge in international play
        if elo_diff > 0:
            adjustment -= 0.01
            reasons.append("international tournament (reduced favorite edge)")
        else:
            adjustment += 0.01
            reasons.append("international tournament (reduced favorite edge)")
        risk_flags.append("international_tournament")

    # ── High variance teams ───────────────────────────────
    if team_a in HIGH_VARIANCE_TEAMS or team_b in HIGH_VARIANCE_TEAMS:
        risk_flags.append("high_variance_team")
        # Don't adjust probability, just flag

    # ── Extreme Elo differences ───────────────────────────
    if abs(elo_diff) > 200:
        risk_flags.append("large_elo_gap")
        # Slightly cap confidence: pull toward 0.5
        pull = 0.01 if abs(elo_diff) > 300 else 0.005
        if elo_diff > 0:
            adjustment -= pull
            reasons.append(f"large Elo gap ({elo_diff:.0f}) — slight regression")
        else:
            adjustment += pull
            reasons.append(f"large Elo gap ({elo_diff:.0f}) — slight regression")

    # ── New/unproven teams (Elo = 1500) ──────────────────
    if abs(packet.get("elo_a", 1500) - 1500) < 5 and abs(packet.get("elo_b", 1500) - 1500) < 5:
        risk_flags.append("unproven_teams")
        # Both at baseline Elo — high uncertainty, modest pull to center
        if base > 0.55:
            adjustment -= 0.02
            reasons.append("both teams unproven — increased uncertainty")
        elif base < 0.45:
            adjustment += 0.02
            reasons.append("both teams unproven — increased uncertainty")

    # ── Clamp adjustment to [-10%, +10%] ─────────────────
    adjustment = max(-0.10, min(0.10, adjustment))

    adjusted = base + adjustment
    adjusted = max(0.01, min(0.99, adjusted))  # Keep in valid range

    # ── Confidence assessment ─────────────────────────────
    if abs(adjustment) < 0.01:
        confidence = "high"  # Model and Hermes agree
    elif abs(adjustment) < 0.04:
        confidence = "medium"
    else:
        confidence = "low"  # Significant disagreement

    return {
        "base_probability": round(base, 4),
        "adjusted_probability": round(adjusted, 4),
        "adjustment": round(adjustment, 4),
        "confidence": confidence,
        "risk_flags": risk_flags,
        "reasons": reasons,
        "team_a": team_a,
        "team_b": team_b,
        "league": league,
        "playoffs": bool(playoffs),
    }


def run_hybrid_backtest(
    packets_path: str = "data/backtest/prediction_packets_2026.json",
) -> dict[str, Any]:
    """Run backtest comparing Model A (stats only) vs Model B (stats + Hermes).

    Returns evaluation dict with accuracy, Brier, calibration for both.
    """
    with open(packets_path) as f:
        packets = json.load(f)

    y_true = np.array([1 if p["actual_winner"] == "team_a" else 0 for p in packets])

    # Model A: base probabilities
    base_probs = np.array([p["base_probability"] for p in packets])
    base_acc = np.mean((base_probs >= 0.5) == y_true)
    base_brier = np.mean((base_probs - y_true) ** 2)

    # Model B: Hermes-adjusted probabilities
    reviews = []
    adjusted_probs = []
    for p in packets:
        review = hermes_review_prediction(p)
        reviews.append(review)
        adjusted_probs.append(review["adjusted_probability"])

    adj_probs = np.array(adjusted_probs)
    adj_acc = np.mean((adj_probs >= 0.5) == y_true)
    adj_brier = np.mean((adj_probs - y_true) ** 2)

    # Calibration bins
    def calibration_bins(probs: np.ndarray, y: np.ndarray) -> list[dict]:
        bins_def = [(0.50, 0.55), (0.55, 0.60), (0.60, 0.65), (0.65, 0.70),
                    (0.70, 0.75), (0.75, 0.80), (0.80, 0.85), (0.85, 1.0)]
        bins = []
        for lo, hi in bins_def:
            mask = (probs >= lo) & (probs < hi)
            n = mask.sum()
            obs = y[mask].mean() if n > 0 else 0.0
            bins.append({
                "bin": f"{lo:.2f}-{hi:.2f}",
                "count": int(n),
                "expected": round((lo + hi) / 2, 3),
                "observed": round(float(obs), 3),
            })
        return bins

    # Adjustment distribution
    adjustments = np.array([r["adjustment"] for r in reviews])
    confidence_dist = {}
    for r in reviews:
        c = r["confidence"]
        confidence_dist[c] = confidence_dist.get(c, 0) + 1

    # Risk flag frequency
    risk_counts: dict[str, int] = {}
    for r in reviews:
        for flag in r["risk_flags"]:
            risk_counts[flag] = risk_counts.get(flag, 0) + 1

    return {
        "n": len(packets),
        "model_a": {
            "name": "Logistic Regression (stats only)",
            "accuracy": round(float(base_acc), 4),
            "brier": round(float(base_brier), 4),
            "calibration": calibration_bins(base_probs, y_true),
        },
        "model_b": {
            "name": "Logistic Regression + Hermes Review",
            "accuracy": round(float(adj_acc), 4),
            "brier": round(float(adj_brier), 4),
            "calibration": calibration_bins(adj_probs, y_true),
        },
        "hermes_stats": {
            "mean_adjustment": round(float(np.mean(np.abs(adjustments))), 4),
            "max_adjustment": round(float(np.max(np.abs(adjustments))), 4),
            "adjustments_made": int(np.sum(np.abs(adjustments) > 0.001)),
            "confidence_distribution": confidence_dist,
            "risk_flags": risk_counts,
        },
        "reviews": reviews[:20],  # first 20 for inspection
    }


def format_hybrid_report(results: dict[str, Any]) -> str:
    """Format the hybrid backtest results."""
    lines = [
        "=" * 72,
        "  HYBRID PREDICTION BACKTEST",
        "  Statistical Baseline vs Statistical + Hermes Review",
        "=" * 72,
        "",
        f"Test matches: {results['n']} (2026 Tier 1 LoL)",
        "",
        f"{'Model':<40s} {'Accuracy':>9s} {'Brier':>7s}",
        f"{'-'*40} {'-'*9} {'-'*7}",
    ]

    for key in ["model_a", "model_b"]:
        m = results[key]
        lines.append(
            f"{m['name']:<40s} {m['accuracy']:>8.2%} {m['brier']:>7.4f}"
        )

    lines.append("")
    lines.append("--- Hermes Review Statistics ---")
    hs = results["hermes_stats"]
    lines.append(f"  Adjustments made: {hs['adjustments_made']}/{results['n']}")
    lines.append(f"  Mean |adjustment|: {hs['mean_adjustment']:.3%}")
    lines.append(f"  Max |adjustment|: {hs['max_adjustment']:.3%}")
    lines.append(f"  Confidence: {hs['confidence_distribution']}")
    lines.append(f"  Risk flags: {hs.get('risk_flags', {})}")

    # Calibration
    for key, label in [("model_a", "Stats Only"), ("model_b", "Stats + Hermes")]:
        lines.append(f"\n--- {label} Calibration ---")
        for b in results[key]["calibration"]:
            bar = "█" * min(int(b["observed"] * 40), 40) if b["count"] > 0 else ""
            lines.append(
                f"  {b['bin']:12s} n={b['count']:4d}  "
                f"exp={b['expected']:.3f}  obs={b['observed']:.3f}  {bar}"
            )

    return "\n".join(lines)
