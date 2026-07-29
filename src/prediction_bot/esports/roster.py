"""
Roster identification and tracking for League of Legends teams.

Identifies a team's active roster at a given point in time by examining
which players appeared in recent games. Distinguishes between organization
name (e.g., "T1") and current roster (e.g., "Zeus/Oner/Faker/Gumayusi/Keria").
"""
from __future__ import annotations

import logging
from collections import defaultdict
from datetime import datetime

logger = logging.getLogger(__name__)


def get_team_roster_at(
    dataset,
    team_name: str,
    at_date: datetime | str,
    lookback_games: int = 20,
) -> dict:
    """Identify a team's active roster at a specific date.

    Examines the last N games before at_date to find the most frequently
    appearing 5 players by position. Handles substitute players by
    returning the core roster plus substitute information.

    Args:
        dataset: OracleElixirDataset instance.
        team_name: Team name as it appears in the dataset.
        at_date: The date to check the roster at.
        lookback_games: Number of recent games to examine.

    Returns:
        Dict with:
            roster: {position: player_name} for the 5 core positions
            substitutes: list of player names seen outside core 5
            roster_stability: fraction of games where core 5 played together
            last_roster_change: date of most recent roster change (approx)
            total_games_with_roster: how many games this roster has played
    """
    rows = dataset.get_team_games_before(team_name, at_date)

    if len(rows) == 0:
        return {
            "roster": {},
            "substitutes": [],
            "roster_stability": 0.0,
            "last_roster_change": None,
            "total_games_with_roster": 0,
        }

    # Get recent game IDs (sorted by date descending)
    recent_dates = sorted(rows["date"].unique(), reverse=True)
    recent_gameids: list[str] = []
    seen_dates: set[str] = set()
    for d in recent_dates:
        gameids_at_date = rows[rows["date"] == d]["gameid"].unique()
        for gid in gameids_at_date:
            if gid not in seen_dates:
                recent_gameids.append(gid)
                seen_dates.add(gid)
        if len(recent_gameids) >= lookback_games:
            break

    recent_rows = rows[rows["gameid"].isin(recent_gameids)]

    # For each position, find the most common player in recent games
    roster: dict[str, str] = {}
    position_counts: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))

    for _, row in recent_rows.iterrows():
        pos = row.get("position", "")
        player = str(row.get("playername", ""))
        if pos and player:
            position_counts[pos][player] += 1

    for pos in ["top", "jng", "mid", "bot", "sup"]:
        if pos in position_counts and position_counts[pos]:
            most_common = max(position_counts[pos], key=lambda k: position_counts[pos][k])
            roster[pos] = most_common

    # Identify substitutes (players who appear but not in core 5)
    core_players = set(roster.values())
    all_players = {str(p) for p in recent_rows["playername"].unique() if isinstance(p, str)}
    substitutes = sorted(all_players - core_players)

    # Compute roster stability: what fraction of games had the full core 5?
    games_with_full_roster = 0
    for gid in recent_gameids:
        game_players = set(recent_rows[recent_rows["gameid"] == gid]["playername"].unique())
        if core_players.issubset(game_players):
            games_with_full_roster += 1

    stability = games_with_full_roster / len(recent_gameids) if recent_gameids else 0.0

    # Estimate last roster change date
    # Find the most recent game where the roster wasn't the core 5
    last_change = None
    for gid in recent_gameids:
        game_players = set(recent_rows[recent_rows["gameid"] == gid]["playername"].unique())
        if not core_players.issubset(game_players):
            game_date = recent_rows[recent_rows["gameid"] == gid]["date"].iloc[0]
            last_change = str(game_date)
            break

    # Count total games with this roster (all time, not just recent)
    all_rows = rows
    total = 0
    for gid in all_rows["gameid"].unique():
        game_players = set(all_rows[all_rows["gameid"] == gid]["playername"].unique())
        if core_players.issubset(game_players):
            total += 1

    return {
        "roster": roster,
        "substitutes": substitutes,
        "roster_stability": round(stability, 2),
        "last_roster_change": last_change,
        "total_games_with_roster": total,
    }


def compare_rosters(
    roster_a: dict,
    roster_b: dict,
) -> dict:
    """Compare two rosters and return a summary of differences.

    Args:
        roster_a: Roster dict from get_team_roster_at for team A.
        roster_b: Roster dict from get_team_roster_at for team B.

    Returns:
        Dict with roster comparison metrics.
    """
    return {
        "team_a_stability": roster_a.get("roster_stability", 0),
        "team_b_stability": roster_b.get("roster_stability", 0),
        "team_a_games_together": roster_a.get("total_games_with_roster", 0),
        "team_b_games_together": roster_b.get("total_games_with_roster", 0),
        "team_a_has_substitutes": len(roster_a.get("substitutes", [])) > 0,
        "team_b_has_substitutes": len(roster_b.get("substitutes", [])) > 0,
    }
