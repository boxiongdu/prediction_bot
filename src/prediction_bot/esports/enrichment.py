"""
Match enrichment pipeline — assembles pre-match context for Hermes predictions.

Combines dataset queries, form computation, roster identification, and
head-to-head history into a structured research packet. Every query is
temporally bounded to prevent data leakage.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

import pandas as pd

from prediction_bot.esports.dataset import OracleElixirDataset, get_dataset
from prediction_bot.esports.form import compute_side_performance, compute_team_form
from prediction_bot.esports.matchup import (
    compute_matchup_history,
    compute_tournament_context,
)
from prediction_bot.esports.roster import compare_rosters, get_team_roster_at

logger = logging.getLogger(__name__)


def generate_match_enrichment(
    team_a: str,
    team_b: str,
    match_date: datetime | str,
    league: str | None = None,
    dataset: OracleElixirDataset | None = None,
) -> dict[str, Any]:
    """Generate a complete pre-match enrichment packet.

    All features are computed using only data from before match_date.
    No post-game statistics or future data are included.
    """
    if dataset is None:
        dataset = get_dataset()

    if isinstance(match_date, str):
        match_date = pd.Timestamp(match_date)
    else:
        match_date = pd.Timestamp(match_date)
    match_date_str = str(match_date)

    form_a = compute_team_form(dataset, team_a, match_date)
    form_b = compute_team_form(dataset, team_b, match_date)

    side_a = compute_side_performance(dataset, team_a, match_date)
    side_b = compute_side_performance(dataset, team_b, match_date)

    h2h = compute_matchup_history(dataset, team_a, team_b, match_date)

    roster_a = get_team_roster_at(dataset, team_a, match_date)
    roster_b = get_team_roster_at(dataset, team_b, match_date)
    roster_comp = compare_rosters(roster_a, roster_b)

    tourney_a = compute_tournament_context(dataset, team_a, match_date, league)
    tourney_b = compute_tournament_context(dataset, team_b, match_date, league)

    return {
        "match_context": {
            "team_a": team_a,
            "team_b": team_b,
            "match_date": match_date_str,
            "league": league,
        },
        "team_a_form": form_a,
        "team_b_form": form_b,
        "team_a_side_performance": side_a,
        "team_b_side_performance": side_b,
        "head_to_head": h2h,
        "roster_comparison": roster_comp,
        "team_a_roster": roster_a,
        "team_b_roster": roster_b,
        "tournament_context_a": tourney_a,
        "tournament_context_b": tourney_b,
    }


def format_enrichment_for_hermes(enrichment: dict[str, Any]) -> str:
    """Format an enrichment packet as human-readable text for Hermes."""
    ctx = enrichment["match_context"]
    fa = enrichment["team_a_form"]
    fb = enrichment["team_b_form"]
    h2h = enrichment["head_to_head"]
    rc = enrichment["roster_comparison"]
    ra = enrichment["team_a_roster"]
    rb = enrichment["team_b_roster"]
    ta = enrichment["tournament_context_a"]
    tb = enrichment["tournament_context_b"]
    sa = enrichment["team_a_side_performance"]
    sb = enrichment["team_b_side_performance"]

    out: list[str] = []
    a, b = ctx["team_a"], ctx["team_b"]

    out.append("## Pre-Match Context")
    out.append(f"- **Match**: {a} vs {b}")
    out.append(f"- **Date**: {ctx['match_date']}")
    if ctx["league"]:
        out.append(f"- **League**: {ctx['league']}")

    out.append(f"\n### {a} Recent Form")
    out.append(
        f"- Win rate (last {fa.get('games_analyzed', 0)}g): "
        f"{fa.get('win_rate', 0):.0%}"
    )
    out.append(f"- Weighted win rate: {fa.get('weighted_win_rate', 0):.0%}")
    out.append(
        f"- Last 5: {fa.get('recent_wins', 0)}W-{fa.get('recent_losses', 0)}L"
    )
    streak_a = fa.get("win_streak", 0)
    direction = "win" if streak_a > 0 else "loss"
    count_a = streak_a if streak_a > 0 else fa.get("loss_streak", 0)
    out.append(f"- Current {direction} streak: {count_a}")
    out.append(
        f"- Blue side: {sa.get('blue_win_rate', 0):.0%} "
        f"({sa.get('blue_games', 0)} games)"
    )

    out.append(f"\n### {b} Recent Form")
    out.append(
        f"- Win rate (last {fb.get('games_analyzed', 0)}g): "
        f"{fb.get('win_rate', 0):.0%}"
    )
    out.append(f"- Weighted win rate: {fb.get('weighted_win_rate', 0):.0%}")
    out.append(
        f"- Last 5: {fb.get('recent_wins', 0)}W-{fb.get('recent_losses', 0)}L"
    )
    streak_b = fb.get("win_streak", 0)
    direction = "win" if streak_b > 0 else "loss"
    count_b = streak_b if streak_b > 0 else fb.get("loss_streak", 0)
    out.append(f"- Current {direction} streak: {count_b}")
    out.append(
        f"- Blue side: {sb.get('blue_win_rate', 0):.0%} "
        f"({sb.get('blue_games', 0)} games)"
    )

    out.append("\n### Head-to-Head History")
    if h2h.get("total_games", 0) > 0:
        out.append(f"- Total meetings: {h2h['total_games']}")
        out.append(
            f"- {a} wins: {h2h['team_a_wins']} "
            f"({h2h['team_a_win_rate']:.0%})"
        )
        out.append(f"- {b} wins: {h2h['team_b_wins']}")
        if h2h.get("last_5_results"):
            out.append(
                f"- Last 5 ({a} view): "
                f"{' '.join(h2h['last_5_results'])}"
            )
        if h2h.get("last_meeting_date"):
            out.append(
                f"- Last meeting: {h2h['last_meeting_date']} "
                f"(winner: {h2h.get('last_meeting_winner', 'unknown')})"
            )
    else:
        out.append("- No prior meetings found.")

    out.append("\n### Roster Information")
    for label, rdata in [
        (f"**{a}**", ra),
        (f"**{b}**", rb),
    ]:
        core = rdata.get("roster", {})
        if core:
            rstr = " / ".join(
                f"{p}: {n}" for p, n in sorted(core.items())
            )
            out.append(f"- {label}: {rstr}")
        out.append(
            f"  - Stability: {rdata.get('roster_stability', 0):.0%}"
        )
        out.append(
            f"  - Games together: "
            f"{rdata.get('total_games_with_roster', 0)}"
        )
        subs = rdata.get("substitutes", [])
        if subs:
            out.append(f"  - Substitutes: {', '.join(subs)}")

    out.append(
        f"- Roster stability: A={rc.get('team_a_stability', 0):.0%}, "
        f"B={rc.get('team_b_stability', 0):.0%}"
    )

    out.append("\n### Tournament Context")
    out.append(
        f"- {a} split: {ta.get('split_win_rate', 0):.0%} "
        f"({ta.get('split_games_played', 0)} games)"
    )
    out.append(
        f"- {b} split: {tb.get('split_win_rate', 0):.0%} "
        f"({tb.get('split_games_played', 0)} games)"
    )

    return "\n".join(out)


def generate_leakage_report(
    enrichment: dict[str, Any],
    target_match_result: dict | None = None,
) -> dict[str, Any]:
    """Verify that an enrichment packet contains no data leakage.

    Checks that no post-game columns from the forbidden set appear in
    the enrichment output.
    """
    from prediction_bot.esports.dataset import POST_GAME_COLUMNS

    def _flatten_keys(d: dict, prefix: str = "") -> list[str]:
        keys: list[str] = []
        for k, v in d.items():
            full_key = f"{prefix}.{k}" if prefix else k
            if isinstance(v, dict):
                keys.extend(_flatten_keys(v, full_key))
            else:
                keys.append(full_key)
        return keys

    all_keys = _flatten_keys(enrichment)
    leaked = [k for k in all_keys if k.split(".")[-1] in POST_GAME_COLUMNS]

    return {
        "passed": len(leaked) == 0,
        "leaked_keys": leaked,
        "total_keys_checked": len(all_keys),
    }
