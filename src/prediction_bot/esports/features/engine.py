"""
Temporal-safe feature generation for League of Legends esports prediction.

Every feature is computed using ONLY data from matches with date < target_date.
Post-game columns from the target match are NEVER used.

Feature groups:
  1. Elo & strength ratings
  2. Recent performance (win rates, kill ratios, gold ratios)
  3. Early game (gold/xp/cs diffs at 10/15 min)
  4. Objective control (dragon, herald, baron, tower rates)
  5. Game pace & style (duration, kills per minute)
  6. Roster stability & experience
  7. Tournament context
  8. Patch effects
"""
from __future__ import annotations

import logging
from typing import Any

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────────
# Internal stateful feature computer
# ──────────────────────────────────────────────────────────────────────


class FeatureStore:
    """Accumulates per-team statistics chronologically.

    Call update() after each match to add its data to the store.
    Call compute_features() before each match to get pre-match features.
    """

    def __init__(self) -> None:
        # Per-team rolling windows: list of recent match stat dicts
        self._team_history: dict[str, list[dict[str, float]]] = {}
        # Elo ratings
        self._elo: dict[str, float] = {}
        # Champion pool tracking
        self._champ_pool: dict[str, dict[str, int]] = {}
        # Roster tracking
        self._roster_history: dict[str, list[set[str]]] = {}

    def compute_features(
        self,
        team_name: str,
        lookback: int = 20,
    ) -> dict[str, float]:
        """Compute all pre-match features for a team."""
        history = self._team_history.get(team_name, [])
        recent = history[-lookback:] if len(history) > lookback else history
        n = len(recent)

        feats: dict[str, float] = {}

        # ── Elo ──────────────────────────────────────────
        feats["elo"] = self._elo.get(team_name, 1500.0)

        # ── Win rate ─────────────────────────────────────
        if n > 0:
            wins = sum(1 for h in recent if h.get("win", 0) == 1)
            feats["win_rate"] = wins / n
            feats["games_played"] = float(n)
        else:
            feats["win_rate"] = 0.5
            feats["games_played"] = 0.0

        # ── Recent form streaks ──────────────────────────
        feats["win_streak"] = 0.0
        feats["loss_streak"] = 0.0
        for h in reversed(recent):
            if h.get("win", 0) == 1:
                feats["win_streak"] += 1
            else:
                break
        for h in reversed(recent):
            if h.get("win", 0) == 0:
                feats["loss_streak"] += 1
            else:
                break

        # ── Weighted recent form ─────────────────────────
        if n >= 5:
            weights = np.exp(np.linspace(0, 1, min(n, 10)))
            weights = weights / weights.sum()
            w_wins = sum(
                w * h.get("win", 0)
                for w, h in zip(
                    weights[-len(recent):],
                    recent[-len(weights):],
                    strict=False,
                )
            )
            feats["weighted_win_rate"] = float(w_wins)
        else:
            feats["weighted_win_rate"] = feats["win_rate"]

        # ── Kill/death ratios ────────────────────────────
        kills = [h.get("kills", 0) for h in recent]
        deaths = [h.get("deaths", 0) for h in recent]
        if n > 0:
            avg_k = np.mean(kills)
            avg_d = np.mean(deaths)
            feats["avg_kills"] = float(avg_k)
            feats["avg_deaths"] = float(avg_d)
            feats["kda_ratio"] = float(avg_k / avg_d) if avg_d > 0 else float(avg_k)
            feats["kill_diff"] = float(avg_k - avg_d)
        else:
            feats["avg_kills"] = 0.0
            feats["avg_deaths"] = 0.0
            feats["kda_ratio"] = 1.0
            feats["kill_diff"] = 0.0

        # ── Game pace ────────────────────────────────────
        durations = [h.get("duration", 1800) for h in recent if h.get("duration", 0) > 0]
        if durations:
            feats["avg_duration"] = float(np.mean(durations))
        else:
            feats["avg_duration"] = 1800.0

        # ── Early game (gold/xp/cs at 15 min) ────────────
        gd15 = [h.get("golddiffat15", 0) for h in recent if h.get("golddiffat15") is not None]
        xd15 = [h.get("xpdiffat15", 0) for h in recent if h.get("xpdiffat15") is not None]
        cd15 = [h.get("csdiffat15", 0) for h in recent if h.get("csdiffat15") is not None]
        feats["avg_golddiff15"] = float(np.mean(gd15)) if gd15 else 0.0
        feats["avg_xpdiff15"] = float(np.mean(xd15)) if xd15 else 0.0
        feats["avg_csdiff15"] = float(np.mean(cd15)) if cd15 else 0.0

        # ── Objective control rates ──────────────────────
        obj_feats = [
            ("firstdragon", "first_dragon_rate"),
            ("firstherald", "first_herald_rate"),
            ("firstbaron", "first_baron_rate"),
            ("firsttower", "first_tower_rate"),
        ]
        for src, dst in obj_feats:
            vals = [h.get(src, 0) for h in recent]
            feats[dst] = float(np.mean(vals)) if vals else 0.0

        # Dragon control ratio
        dragons = [h.get("dragons", 0) for h in recent]
        opp_dragons = [h.get("opp_dragons", 0) for h in recent]
        if dragons and sum(dragons) + sum(opp_dragons) > 0:
            feats["dragon_control"] = float(
                sum(dragons) / (sum(dragons) + sum(opp_dragons))
            )
        else:
            feats["dragon_control"] = 0.5

        # Baron control
        barons = [h.get("barons", 0) for h in recent]
        opp_barons = [h.get("opp_barons", 0) for h in recent]
        b_total = sum(barons) + sum(opp_barons)
        feats["baron_control"] = float(sum(barons) / b_total) if b_total > 0 else 0.5

        # Tower differential
        towers = [h.get("towers", 0) for h in recent]
        opp_towers = [h.get("opp_towers", 0) for h in recent]
        if towers:
            feats["avg_tower_diff"] = float(np.mean(
                [t - o for t, o in zip(towers, opp_towers, strict=False)]
            ))
        else:
            feats["avg_tower_diff"] = 0.0

        # ── Champion pool diversity ──────────────────────
        champs = self._champ_pool.get(team_name, {})
        total_picks = sum(champs.values())
        if total_picks > 0:
            feats["champ_pool_size"] = float(len(champs))
            # Normalized entropy of champion picks (higher = more diverse)
            probs = np.array(list(champs.values())) / total_picks
            entropy = -np.sum(probs * np.log(probs + 1e-9))
            feats["champ_diversity"] = float(entropy / np.log(max(len(champs), 2)))
        else:
            feats["champ_pool_size"] = 0.0
            feats["champ_diversity"] = 0.0

        # ── Roster stability ─────────────────────────────
        rosters = self._roster_history.get(team_name, [])
        if len(rosters) >= 2:
            # Fraction of consecutive games with same roster
            same = sum(
                1 for i in range(1, min(len(rosters), 20))
                if rosters[-i] == rosters[-i - 1]
            )
            feats["roster_stability"] = float(
                same / max(min(len(rosters) - 1, 20), 1)
            )
        else:
            feats["roster_stability"] = 1.0

        # Roster size (unique players seen recently)
        recent_players: set[str] = set()
        for r in rosters[-20:]:
            recent_players.update(r)
        feats["roster_size"] = float(len(recent_players))

        return feats

    def update(
        self,
        team_name: str,
        match_stats: dict[str, float],
        players: set[str],
        champions: list[str],
        elo: float,
    ) -> None:
        """Update the feature store with a completed match."""
        if team_name not in self._team_history:
            self._team_history[team_name] = []
        self._team_history[team_name].append(match_stats)

        # Keep bounded history
        if len(self._team_history[team_name]) > 100:
            self._team_history[team_name] = self._team_history[team_name][-100:]

        self._elo[team_name] = elo

        if team_name not in self._champ_pool:
            self._champ_pool[team_name] = {}
        for champ in champions:
            self._champ_pool[team_name][champ] = (
                self._champ_pool[team_name].get(champ, 0) + 1
            )

        if team_name not in self._roster_history:
            self._roster_history[team_name] = []
        self._roster_history[team_name].append(players)
        if len(self._roster_history[team_name]) > 50:
            self._roster_history[team_name] = self._roster_history[team_name][-50:]


# ──────────────────────────────────────────────────────────────────────
# Main feature generation loop
# ──────────────────────────────────────────────────────────────────────


def generate_all_features(
    matches_df: pd.DataFrame,
    elo_k: float = 32.0,
    elo_home: float = 30.0,
) -> pd.DataFrame:
    """Generate all pre-match features for every match in chronological order.

    Process:
      1. For each match, compute features for both teams BEFORE the match
      2. Compute Elo and base probability
      3. Record the match outcome
      4. Update the feature store with the match result (for future matches)

    This ensures ZERO data leakage — features for match N only use data
    from matches 0..N-1.
    """
    store = FeatureStore()
    elo_ratings: dict[str, float] = {}

    rows: list[dict[str, Any]] = []

    for _, match in matches_df.iterrows():
        team_a = match["team_blue"]
        team_b = match["team_red"]
        is_playoffs = bool(match.get("playoffs", 0))
        league = match.get("league", "")
        patch = str(match.get("patch", ""))

        # ── Compute pre-match features ──────────────────
        feats_a = store.compute_features(team_a)
        feats_b = store.compute_features(team_b)

        # ── Elo computation ─────────────────────────────
        ea = elo_ratings.get(team_a, 1500.0)
        eb = elo_ratings.get(team_b, 1500.0)

        expected_a = 1.0 / (1.0 + 10 ** ((eb - (ea + elo_home)) / 400.0))

        # ── Build feature row ───────────────────────────
        row: dict[str, Any] = {
            "date": match["date"],
            "league": league,
            "patch": patch,
            "playoffs": int(is_playoffs),
            "team_a": team_a,
            "team_b": team_b,
            "blue_wins": int(match["blue_wins"]),
            "elo_prob": round(float(expected_a), 4),
        }

        # Add Elo features
        row["elo_a"] = ea
        row["elo_b"] = eb
        row["elo_diff"] = round(float((ea + elo_home) - eb), 1)

        # Add all team features as differences (a - b)
        skip_a = {"elo"}  # already handled
        for key in feats_a:
            if key in skip_a:
                continue
            va = feats_a.get(key, 0.0)
            vb = feats_b.get(key, 0.0)
            row[f"{key}_a"] = round(float(va), 4)
            row[f"{key}_b"] = round(float(vb), 4)
            row[f"{key}_diff"] = round(float(va - vb), 4)

        # ── Tournament context ───────────────────────────
        row["is_international"] = int(
            league in {"MSI", "WLDs", "EWC", "FST"}
        )

        # ── Patch features ───────────────────────────────
        row["patch_num"] = _parse_patch(patch)

        rows.append(row)

        # ── Update Elo ──────────────────────────────────
        delta = elo_k * (match["blue_wins"] - expected_a)
        elo_ratings[team_a] = ea + delta
        elo_ratings[team_b] = eb - delta

        # ── Update feature store ────────────────────────
        for team, stats, elo in [
            (team_a, _extract_match_stats(match, "blue"), ea + delta),
            (team_b, _extract_match_stats(match, "red"), eb - delta),
        ]:
            store.update(
                team_name=team,
                match_stats=stats["stats"],
                players=stats["players"],
                champions=stats["champions"],
                elo=elo,
            )

    result = pd.DataFrame(rows)
    return result


def _extract_match_stats(
    match: pd.Series, side: str
) -> dict[str, Any]:
    """Extract post-match stats from a match row for future feature computation.

    These stats are recorded AFTER the match and used only for FUTURE
    feature lookups — never for the current match's features.
    """
    if side == "blue":
        kills = match.get("blue_kills", 0)
        deaths = match.get("blue_deaths", 0)
        won = match["blue_wins"]
    else:
        kills = match.get("red_kills", 0)
        deaths = match.get("red_deaths", 0)
        won = 1 - match["blue_wins"]

    return {
        "stats": {
            "win": won,
            "kills": kills,
            "deaths": deaths,
            "duration": match.get("gamelength", 1800),
            # Early game — only available if match data includes it
            "golddiffat15": match.get("blue_golddiffat15", 0) if side == "blue"
            else -match.get("blue_golddiffat15", 0),
            "xpdiffat15": match.get("blue_xpdiffat15", 0) if side == "blue"
            else -match.get("blue_xpdiffat15", 0),
            "csdiffat15": match.get("blue_csdiffat15", 0) if side == "blue"
            else -match.get("blue_csdiffat15", 0),
            # Objectives
            "firstdragon": match.get("blue_firstdragon", 0) if side == "blue"
            else 1 - match.get("blue_firstdragon", 0),
            "firstherald": match.get("blue_firstherald", 0) if side == "blue"
            else 1 - match.get("blue_firstherald", 0),
            "firstbaron": match.get("blue_firstbaron", 0) if side == "blue"
            else 1 - match.get("blue_firstbaron", 0),
            "firsttower": match.get("blue_firsttower", 0) if side == "blue"
            else 1 - match.get("blue_firsttower", 0),
            "dragons": match.get("blue_dragons", 0) if side == "blue"
            else match.get("red_dragons", 0),
            "opp_dragons": match.get("red_dragons", 0) if side == "blue"
            else match.get("blue_dragons", 0),
            "barons": match.get("blue_barons", 0) if side == "blue"
            else match.get("red_barons", 0),
            "opp_barons": match.get("red_barons", 0) if side == "blue"
            else match.get("blue_barons", 0),
            "towers": match.get("blue_towers", 0) if side == "blue"
            else match.get("red_towers", 0),
            "opp_towers": match.get("red_towers", 0) if side == "blue"
            else match.get("blue_towers", 0),
        },
        "players": set(),  # Can't extract from match-level data
        "champions": [],   # Can't extract from match-level data
    }


def _parse_patch(patch_str: str) -> float:
    """Parse patch string like '16.10' into numeric."""
    try:
        parts = patch_str.split(".")
        return float(parts[0]) + float(parts[1]) / 100
    except (ValueError, IndexError):
        return 0.0
