"""
Esports prediction baselines — Elo, Pythagorean, and logistic regression models.

All models use strict chronological ordering to prevent data leakage.
Training: 2024–2025 matches.  Testing: 2026 matches.

Models:
  1. Random baseline — always predicts 50% / blue side wins
  2. Elo — rolling Elo ratings with K-factor tuning
  3. Pythagorean — win expectancy from kill/gold ratios
  4. Logistic regression — combined features
"""
from __future__ import annotations

import logging
from typing import Any

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss
from sklearn.preprocessing import StandardScaler

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────────
# Data loading
# ──────────────────────────────────────────────────────────────────────


def load_matches(path: str = "data/tier1_matches.parquet") -> pd.DataFrame:
    """Load pre-computed match-level dataset."""
    df = pd.read_parquet(path)
    df = df.sort_values("date").reset_index(drop=True)
    return df


# ──────────────────────────────────────────────────────────────────────
# 1. Random baseline
# ──────────────────────────────────────────────────────────────────────


def random_predictions(df: pd.DataFrame) -> np.ndarray:
    """Always predict 50% win probability for blue side."""
    return np.full(len(df), 0.50)


def blue_side_baseline(df: pd.DataFrame) -> np.ndarray:
    """Always predict blue side wins (53.3% base rate)."""
    return np.full(len(df), 0.533)


# ──────────────────────────────────────────────────────────────────────
# 2. Elo model
# ──────────────────────────────────────────────────────────────────────


def compute_elo_ratings(
    df: pd.DataFrame,
    initial_elo: float = 1500.0,
    k_factor: float = 32.0,
    home_advantage: float = 30.0,  # blue side advantage in Elo points
) -> pd.DataFrame:
    """Compute rolling Elo ratings chronologically.

    Updates Elo after each match. Blue side gets a small home advantage.
    Returns the input DataFrame with added columns:
        elo_blue, elo_red, elo_prob_blue (win probability for blue side).
    """
    elos: dict[str, float] = {}
    elo_probs: list[float] = []
    elo_blues: list[float] = []
    elo_reds: list[float] = []

    for _, row in df.iterrows():
        team_b = row["team_blue"]
        team_r = row["team_red"]

        eb = elos.get(team_b, initial_elo)
        er = elos.get(team_r, initial_elo)

        elo_blues.append(eb)
        elo_reds.append(er)

        # Win probability for blue (with home advantage)
        expected_blue = 1.0 / (1.0 + 10 ** ((er - (eb + home_advantage)) / 400.0))
        elo_probs.append(expected_blue)

        # Update ratings
        actual_blue = row["blue_wins"]
        delta = k_factor * (actual_blue - expected_blue)
        elos[team_b] = eb + delta
        elos[team_r] = er - delta

    result = df.copy()
    result["elo_blue"] = elo_blues
    result["elo_red"] = elo_reds
    result["elo_prob_blue"] = elo_probs
    return result


def tune_elo_k(
    train_df: pd.DataFrame,
    k_values: list[int] | None = None,
) -> dict[str, Any]:
    """Find the best K-factor by minimizing Brier score on training data."""
    if k_values is None:
        k_values = [8, 16, 24, 32, 40, 48, 56, 64]

    best_k = 32
    best_brier = float("inf")
    results = {}

    for k in k_values:
        rated = compute_elo_ratings(train_df, k_factor=k)
        brier = brier_score_loss(rated["blue_wins"], rated["elo_prob_blue"])
        results[k] = brier
        if brier < best_brier:
            best_brier = brier
            best_k = k

    return {"best_k": best_k, "best_brier": best_brier, "all": results}


# ──────────────────────────────────────────────────────────────────────
# 3. Pythagorean model
# ──────────────────────────────────────────────────────────────────────


def compute_team_pythag_stats(
    df: pd.DataFrame,
    lookback_days: int | None = None,
    lookback_games: int = 20,
) -> pd.DataFrame:
    """Compute rolling Pythagorean win expectancy from past performance.

    Uses a kill-based Pythagorean formula:
        win% = kills^exp / (kills^exp + deaths^exp)

    Looks back at recent games to compute rolling averages for each team.
    """
    # Store rolling team stats
    team_stats: dict[str, dict[str, list[float]]] = {}
    pyth_probs: list[float] = []
    pyth_blues: list[float] = []
    pyth_reds: list[float] = []

    for _, row in df.iterrows():
        team_b = row["team_blue"]
        team_r = row["team_red"]
        match_date = row["date"]

        def get_pyth(team: str) -> float | None:
            stats = team_stats.get(team)
            if not stats or len(stats["kills"]) < 5:
                return None
            kills = np.mean(stats["kills"])
            deaths = np.mean(stats["deaths"])
            if kills + deaths == 0:
                return None
            exp = 2.0  # Pythagorean exponent for LoL
            return kills**exp / (kills**exp + deaths**exp)

        pb = get_pyth(team_b)
        pr = get_pyth(team_r)

        pyth_blues.append(pb)
        pyth_reds.append(pr)

        if pb is not None and pr is not None:
            # Log5 formula: P(A beats B) = (A*(1-B)) / (A*(1-B) + B*(1-A))
            prob_blue = (pb * (1 - pr)) / (pb * (1 - pr) + pr * (1 - pb) + 1e-9)
        elif pb is not None:
            prob_blue = pb
        elif pr is not None:
            prob_blue = 1 - pr
        else:
            prob_blue = 0.50

        pyth_probs.append(prob_blue)

        # Update team stats after computing probability (no leakage)
        for team, kills, deaths in [
            (team_b, row["blue_kills"], row["blue_deaths"]),
            (team_r, row["red_kills"], row["red_deaths"]),
        ]:
            if team not in team_stats:
                team_stats[team] = {"kills": [], "deaths": [], "dates": []}
            ts = team_stats[team]
            ts["kills"].append(kills)
            ts["deaths"].append(deaths)
            ts["dates"].append(match_date)
            # Trim to lookback
            if len(ts["kills"]) > lookback_games:
                ts["kills"] = ts["kills"][-lookback_games:]
                ts["deaths"] = ts["deaths"][-lookback_games:]

    result = df.copy()
    result["pyth_blue"] = pyth_blues
    result["pyth_red"] = pyth_reds
    result["pyth_prob_blue"] = pyth_probs
    return result


# ──────────────────────────────────────────────────────────────────────
# 4. Logistic regression model
# ──────────────────────────────────────────────────────────────────────


def build_features(df: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
    """Build feature matrix for logistic regression.

    Features:
        elo_diff: normalized Elo difference (blue - red)
        pyth_diff: Pythagorean win expectancy difference
        blue_form_diff: difference in rolling win rates
        is_playoffs: 1 if playoff match
        league_encoded: one-hot encoded league (for major context)
    """
    features: list[np.ndarray] = []

    # Elo difference
    elo_diff = (df["elo_blue"].values - df["elo_red"].values) / 400.0
    features.append(elo_diff.reshape(-1, 1))

    # Pythagorean difference
    if "pyth_prob_blue" in df.columns:
        pyth_diff = df["pyth_prob_blue"].values - 0.5
        features.append(pyth_diff.reshape(-1, 1))

    # Playoff flag
    features.append(df["playoffs"].values.reshape(-1, 1))

    # Recent form: rolling win rate difference
    # Compute on the fly using past matches
    team_wins: dict[str, list[int]] = {}
    form_diffs: list[float] = []
    for _, row in df.iterrows():
        b, r = row["team_blue"], row["team_red"]
        b_wr = np.mean(team_wins.get(b, [0.5])) if team_wins.get(b) else 0.5
        r_wr = np.mean(team_wins.get(r, [0.5])) if team_wins.get(r) else 0.5
        form_diffs.append(b_wr - r_wr)
        # Update after computing (no leakage)
        for team, won in [(b, row["blue_wins"]), (r, 1 - row["blue_wins"])]:
            if team not in team_wins:
                team_wins[team] = []
            team_wins[team].append(won)
            if len(team_wins[team]) > 10:
                team_wins[team] = team_wins[team][-10:]

    features.append(np.array(form_diffs).reshape(-1, 1))

    x_matrix = np.hstack(features)
    y = df["blue_wins"].values

    return x_matrix, y


def train_logistic_model(
    train_df: pd.DataFrame,
    c_reg: float = 1.0,
) -> tuple[LogisticRegression, StandardScaler]:
    """Train logistic regression on 2024-2025 data."""
    x_train, y_train = build_features(train_df)

    scaler = StandardScaler()
    x_scaled = scaler.fit_transform(x_train)

    model = LogisticRegression(C=c_reg, max_iter=1000, random_state=42)
    model.fit(x_scaled, y_train)

    train_prob = model.predict_proba(x_scaled)[:, 1]
    train_brier = brier_score_loss(y_train, train_prob)
    train_acc = np.mean((train_prob >= 0.5) == y_train)

    logger.info(
        "LR trained: acc=%.3f, brier=%.4f, coefs=%s",
        train_acc,
        train_brier,
        model.coef_[0].tolist(),
    )

    return model, scaler


def predict_logistic(
    test_df: pd.DataFrame,
    model: LogisticRegression,
    scaler: StandardScaler,
) -> np.ndarray:
    """Predict win probabilities for blue side."""
    x_test, _ = build_features(test_df)
    x_scaled = scaler.transform(x_test)
    return model.predict_proba(x_scaled)[:, 1]


# ──────────────────────────────────────────────────────────────────────
# 5. Evaluation
# ──────────────────────────────────────────────────────────────────────


def evaluate_predictions(
    y_true: np.ndarray,
    y_prob: np.ndarray,
    label: str = "",
) -> dict[str, Any]:
    """Compute accuracy, Brier score, and calibration bins."""
    y_pred = (y_prob >= 0.5).astype(int)
    acc = np.mean(y_pred == y_true)
    brier = brier_score_loss(y_true, y_prob)

    # Calibration bins
    bins = [(0.50, 0.55), (0.55, 0.60), (0.60, 0.65), (0.65, 0.70),
            (0.70, 0.75), (0.75, 0.80), (0.80, 0.85), (0.85, 1.0)]
    cal_bins = []
    for lo, hi in bins:
        mask = (y_prob >= lo) & (y_prob < hi)
        n = mask.sum()
        obs = y_true[mask].mean() if n > 0 else 0.0
        cal_bins.append({
            "bin": f"{lo:.2f}-{hi:.2f}",
            "count": int(n),
            "expected": (lo + hi) / 2,
            "observed": round(float(obs), 3),
        })

    # Sharpe-like: excess over 50% baseline
    excess = acc - 0.533

    return {
        "model": label,
        "n": len(y_true),
        "accuracy": round(float(acc), 4),
        "brier_score": round(float(brier), 4),
        "excess_over_blue_base": round(float(excess), 4),
        "calibration_bins": cal_bins,
    }


def run_full_evaluation() -> dict[str, Any]:
    """Run the complete baseline evaluation pipeline.

    Returns a dict with results for each model.
    """
    df = load_matches()

    # Chronological split
    train = df[df["year"].isin([2024, 2025])].copy()
    test = df[df["year"] == 2026].copy()

    logger.info(
        "Split: train=%d (2024-25), test=%d (2026)",
        len(train), len(test),
    )

    results: dict[str, Any] = {}

    # ── Elo ─────────────────────────────────────────────
    logger.info("Tuning Elo K-factor...")
    tune = tune_elo_k(train)
    best_k = tune["best_k"]
    logger.info("Best K=%d (Brier=%.4f)", best_k, tune["best_brier"])

    # Compute Elo on combined data to get correct running state for test
    combined = pd.concat([train, test], ignore_index=True)
    combined_rated = compute_elo_ratings(combined, k_factor=best_k)
    elo_test_probs = combined_rated["elo_prob_blue"].values[-len(test):]

    results["elo"] = evaluate_predictions(
        test["blue_wins"].values, elo_test_probs, "Elo",
    )

    # ── Pythagorean ────────────────────────────────────
    logger.info("Computing Pythagorean model...")
    combined_pyth = compute_team_pythag_stats(combined)
    pyth_test_probs = combined_pyth["pyth_prob_blue"].values[-len(test):]
    results["pythagorean"] = evaluate_predictions(
        test["blue_wins"].values, pyth_test_probs, "Pythagorean",
    )

    # ── Logistic Regression ────────────────────────────
    logger.info("Training logistic regression...")
    # Need Elo and Pyth features on combined data
    train_feat = combined_rated.iloc[:len(train)].copy()
    test_feat = combined_rated.iloc[len(train):].copy()
    # Add pyth probs
    train_feat["pyth_prob_blue"] = combined_pyth["pyth_prob_blue"].values[:len(train)]
    test_feat["pyth_prob_blue"] = combined_pyth["pyth_prob_blue"].values[len(train):]

    model, scaler = train_logistic_model(train_feat)
    lr_probs = predict_logistic(test_feat, model, scaler)
    results["logistic_regression"] = evaluate_predictions(
        test["blue_wins"].values, lr_probs, "Logistic Regression",
    )

    # ── Baselines ──────────────────────────────────────
    results["random_50"] = evaluate_predictions(
        test["blue_wins"].values,
        random_predictions(test),
        "Random (50%)",
    )
    results["blue_side_only"] = evaluate_predictions(
        test["blue_wins"].values,
        blue_side_baseline(test),
        "Blue Side Only (53.3%)",
    )

    return results


def format_results_table(results: dict[str, Any]) -> str:
    """Format evaluation results as a readable table."""
    lines = [
        "=" * 72,
        "  ESPORTS PREDICTION BASELINE EVALUATION",
        "=" * 72,
        "",
        f"{'Model':<25s} {'N':>6s} {'Accuracy':>9s} {'Brier':>7s} {'vs Blue':>8s}",
        f"{'-'*25} {'-'*6} {'-'*9} {'-'*7} {'-'*8}",
    ]

    order = ["Random (50%)", "Blue Side Only (53.3%)", "Elo",
             "Pythagorean", "Logistic Regression"]

    for name in order:
        if name not in results:
            for _k, v in results.items():
                if v["model"] == name:
                    results[name] = v
                    break

    for name in order:
        r = results.get(name)
        if r is None:
            continue
        lines.append(
            f"{r['model']:<25s} {r['n']:>6d} "
            f"{r['accuracy']:>8.2%} {r['brier_score']:>7.4f} "
            f"{r['excess_over_blue_base']:>+7.2%}"
        )

    lines.append("")
    lines.append("Train: 2024–2025 | Test: 2026 (chronological split)")
    lines.append("Blue side base rate: 53.3%")

    return "\n".join(lines)
