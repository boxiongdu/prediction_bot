"""
Recent form computation for esports teams.

Computes weighted performance metrics from past games with temporal
decay — recent games weighted higher. Strictly uses only data from
before the target match date to prevent leakage.
"""
from __future__ import annotations

import logging
from datetime import datetime

logger = logging.getLogger(__name__)


def compute_team_form(
    dataset,
    team_name: str,
    before_date: datetime | str,
    lookback_games: int = 20,
    temporal_weights: tuple[float, ...] = (0.4, 0.3, 0.2, 0.1),
) -> dict:
    """Compute recent form metrics for a team.

    Examines the last N games before before_date. Applies temporal
    weighting — most recent games weighted highest.

    Args:
        dataset: OracleElixirDataset instance.
        team_name: Team name.
        before_date: Cutoff date.
        lookback_games: Number of recent games to analyze.
        temporal_weights: Weights for game recency buckets (newest first).
            Default: (0.4, 0.3, 0.2, 0.1) — 4 buckets of 5 games each.

    Returns:
        Dict with form metrics:
            win_rate: overall win rate in lookback window
            weighted_win_rate: temporally-weighted win rate
            recent_wins: wins in last 5 games
            recent_losses: losses in last 5 games
            win_streak: current win streak
            loss_streak: current loss streak
            avg_game_count: average games per series (proxy for competitiveness)
            games_analyzed: total games included
    """
    rows = dataset.get_team_games_before(team_name, before_date)

    if len(rows) == 0:
        return {
            "win_rate": 0.0,
            "weighted_win_rate": 0.0,
            "recent_wins": 0,
            "recent_losses": 0,
            "win_streak": 0,
            "loss_streak": 0,
            "avg_game_count": 0.0,
            "games_analyzed": 0,
        }

    # Get game-level results sorted by date descending
    gameids_sorted = sorted(
        rows["gameid"].unique(),
        key=lambda gid: rows[rows["gameid"] == gid]["date"].max(),
        reverse=True,
    )

    results: list[int] = []
    for gid in gameids_sorted[:lookback_games]:
        game_rows = rows[rows["gameid"] == gid]
        # A team wins the game if ANY of their rows have result=1
        won = (game_rows["result"] == 1).any()
        results.append(1 if won else 0)

    if not results:
        return {
            "win_rate": 0.0,
            "weighted_win_rate": 0.0,
            "recent_wins": 0,
            "recent_losses": 0,
            "win_streak": 0,
            "loss_streak": 0,
            "avg_game_count": 0.0,
            "games_analyzed": 0,
        }

    # Overall win rate
    win_rate = sum(results) / len(results)

    # Temporal-weighted win rate
    bucket_size = max(1, len(results) // len(temporal_weights))
    weighted_sum = 0.0
    weight_total = 0.0
    for i in range(len(temporal_weights)):
        start = i * bucket_size
        end = start + bucket_size
        bucket_results = results[start:end]
        if bucket_results:
            bucket_win_rate = sum(bucket_results) / len(bucket_results)
            w = temporal_weights[i]
            weighted_sum += bucket_win_rate * w
            weight_total += w

    weighted_win_rate = weighted_sum / weight_total if weight_total > 0 else win_rate

    # Recent 5
    recent_5 = results[:5]
    recent_wins = sum(recent_5)
    recent_losses = len(recent_5) - recent_wins

    # Streaks
    win_streak = 0
    for r in results:
        if r == 1:
            win_streak += 1
        else:
            break

    loss_streak = 0
    for r in results:
        if r == 0:
            loss_streak += 1
        else:
            break

    # Average games per series (proxy for how competitive matches are)
    series_games = []
    for _gid in gameids_sorted[:lookback_games]:
        # Count games in this series (approximate by matching gameid prefix)
        series_games.append(1)  # simplified — each gameid is one game
    avg_games = sum(series_games) / len(series_games) if series_games else 0.0

    return {
        "win_rate": round(win_rate, 3),
        "weighted_win_rate": round(weighted_win_rate, 3),
        "recent_wins": recent_wins,
        "recent_losses": recent_losses,
        "win_streak": win_streak,
        "loss_streak": loss_streak,
        "avg_game_count": round(avg_games, 1),
        "games_analyzed": len(results),
    }


def compute_side_performance(
    dataset,
    team_name: str,
    before_date: datetime | str,
) -> dict:
    """Compute win rates by side (blue/red) for a team.

    Args:
        dataset: OracleElixirDataset instance.
        team_name: Team name.
        before_date: Cutoff date.

    Returns:
        Dict with blue_win_rate, red_win_rate, blue_games, red_games.
    """
    rows = dataset.get_team_games_before(team_name, before_date)

    if len(rows) == 0:
        return {"blue_win_rate": 0.0, "red_win_rate": 0.0, "blue_games": 0, "red_games": 0}

    blue_games = 0
    blue_wins = 0
    red_games = 0
    red_wins = 0

    for gid in rows["gameid"].unique():
        game_rows = rows[rows["gameid"] == gid]
        side = game_rows["side"].iloc[0] if "side" in game_rows.columns else "Blue"
        won = (game_rows["result"] == 1).any()

        if str(side).lower() == "blue":
            blue_games += 1
            if won:
                blue_wins += 1
        else:
            red_games += 1
            if won:
                red_wins += 1

    return {
        "blue_win_rate": round(blue_wins / blue_games, 3) if blue_games > 0 else 0.0,
        "red_win_rate": round(red_wins / red_games, 3) if red_games > 0 else 0.0,
        "blue_games": blue_games,
        "red_games": red_games,
    }
