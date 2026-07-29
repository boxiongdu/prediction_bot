"""
Head-to-head matchup history for esports teams.

Computes historical matchup statistics between two teams using only
games played before a target date.
"""
from __future__ import annotations

import logging
from datetime import datetime

logger = logging.getLogger(__name__)


def compute_matchup_history(
    dataset,
    team_a: str,
    team_b: str,
    before_date: datetime | str,
) -> dict:
    """Compute head-to-head statistics for team_a vs team_b.

    Only uses games played strictly before before_date.

    Args:
        dataset: OracleElixirDataset instance.
        team_a: First team name.
        team_b: Second team name.
        before_date: Cutoff date.

    Returns:
        Dict with H2H stats:
            total_games: number of games played between these teams
            team_a_wins: wins for team_a
            team_b_wins: wins for team_b
            team_a_win_rate: team_a's win rate in H2H
            last_meeting_date: date of most recent meeting
            last_meeting_winner: who won the last meeting
            last_5_results: results of last 5 meetings (from team_a's perspective)
    """
    h2h_rows = dataset.get_matchup_history(team_a, team_b, before_date)

    if len(h2h_rows) == 0:
        return {
            "total_games": 0,
            "team_a_wins": 0,
            "team_b_wins": 0,
            "team_a_win_rate": 0.0,
            "last_meeting_date": None,
            "last_meeting_winner": None,
            "last_5_results": [],
        }

    # Get unique gameids sorted by date descending
    gameids = sorted(
        h2h_rows["gameid"].unique(),
        key=lambda gid: h2h_rows[h2h_rows["gameid"] == gid]["date"].max(),
        reverse=True,
    )

    a_wins = 0
    b_wins = 0
    last_5 = []

    for gid in gameids:
        game_rows = h2h_rows[h2h_rows["gameid"] == gid]
        a_rows = game_rows[game_rows["teamname"].str.lower() == team_a.lower()]
        b_rows = game_rows[game_rows["teamname"].str.lower() == team_b.lower()]

        a_won = (a_rows["result"] == 1).any() if len(a_rows) > 0 else False
        b_won = (b_rows["result"] == 1).any() if len(b_rows) > 0 else False

        if a_won:
            a_wins += 1
            if len(last_5) < 5:
                last_5.append("W")
        elif b_won:
            b_wins += 1
            if len(last_5) < 5:
                last_5.append("L")

    total = a_wins + b_wins
    win_rate = a_wins / total if total > 0 else 0.0

    # Last meeting
    last_gid = gameids[0] if gameids else None
    last_date = None
    last_winner = None
    if last_gid:
        last_rows = h2h_rows[h2h_rows["gameid"] == last_gid]
        last_date = str(last_rows["date"].max())
        a_last = last_rows[last_rows["teamname"].str.lower() == team_a.lower()]
        last_winner = (
            team_a
            if len(a_last) > 0 and (a_last["result"] == 1).any()
            else team_b
        )

    return {
        "total_games": total,
        "team_a_wins": a_wins,
        "team_b_wins": b_wins,
        "team_a_win_rate": round(win_rate, 3),
        "last_meeting_date": last_date,
        "last_meeting_winner": last_winner,
        "last_5_results": last_5,
    }


def compute_tournament_context(
    dataset,
    team_name: str,
    before_date: datetime | str,
    league: str | None = None,
) -> dict:
    """Compute tournament/league context for a team.

    Args:
        dataset: OracleElixirDataset instance.
        team_name: Team name.
        before_date: Cutoff date.
        league: Optional league filter. If None, uses all leagues.

    Returns:
        Dict with:
            split_win_rate: win rate in current split/season
            split_games_played: games played in current split
            playoff_games: playoff games played
            playoff_win_rate: playoff win rate
            games_vs_top_teams: games vs teams with >60% win rate
    """
    rows = dataset.get_team_games_before(team_name, before_date)

    if len(rows) == 0:
        return {
            "split_win_rate": 0.0,
            "split_games_played": 0,
            "playoff_games": 0,
            "playoff_win_rate": 0.0,
            "games_vs_top_teams": 0,
        }

    if league:
        rows = rows[rows["league"] == league]

    gameids = sorted(
        rows["gameid"].unique(),
        key=lambda gid: rows[rows["gameid"] == gid]["date"].max(),
        reverse=True,
    )

    wins = 0
    playoff_games = 0
    playoff_wins = 0

    for gid in gameids:
        game_rows = rows[rows["gameid"] == gid]
        won = (game_rows["result"] == 1).any()
        if won:
            wins += 1

        has_playoffs = "playoffs" in game_rows.columns
        is_playoff = (game_rows["playoffs"] == 1).any() if has_playoffs else False
        if is_playoff:
            playoff_games += 1
            if won:
                playoff_wins += 1

    total = len(gameids)
    split_win_rate = wins / total if total > 0 else 0.0
    playoff_win_rate = playoff_wins / playoff_games if playoff_games > 0 else 0.0

    return {
        "split_win_rate": round(split_win_rate, 3),
        "split_games_played": total,
        "playoff_games": playoff_games,
        "playoff_win_rate": round(playoff_win_rate, 3),
        "games_vs_top_teams": 0,  # Requires opponent win rate computation
    }
