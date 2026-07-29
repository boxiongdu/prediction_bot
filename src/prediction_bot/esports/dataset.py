"""
Oracle's Elixir dataset loader and query interface.

Loads 2024–2026 LoL match data CSVs. Provides temporal-safe queries
for pre-match feature generation — all queries enforce date < T
to prevent data leakage.
"""
from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path

import pandas as pd

logger = logging.getLogger(__name__)

# Default location — CSV files at project root
_DEFAULT_DATA_DIR = Path(__file__).resolve().parent.parent.parent.parent

# Columns that are always forbidden in pre-match features
POST_GAME_COLUMNS: frozenset[str] = frozenset({
    "result", "gamelength",
    "kills", "deaths", "assists",
    "teamkills", "teamdeaths",
    "doublekills", "triplekills", "quadrakills", "pentakills",
    "firstblood", "firstbloodkill", "firstbloodassist", "firstbloodvictim",
    "team kpm", "ckpm",
    "firstdragon", "dragons", "opp_dragons",
    "elementaldrakes", "opp_elementaldrakes",
    "infernals", "mountains", "clouds", "oceans", "chemtechs", "hextechs",
    "dragons (type unknown)", "elders", "opp_elders",
    "firstherald", "heralds", "opp_heralds",
    "void_grubs", "opp_void_grubs",
    "firstbaron", "barons", "opp_barons",
    "atakhans", "opp_atakhans",
    "firsttower", "towers", "opp_towers",
    "firstmidtower", "firsttothreetowers",
    "turretplates", "opp_turretplates",
    "inhibitors", "opp_inhibitors",
    "damagetochampions", "dpm", "damageshare",
    "damagetakenperminute", "damagemitigatedperminute",
    "damagetotowers",
    "wardsplaced", "wpm", "wardskilled", "wcpm",
    "controlwardsbought", "visionscore", "vspm",
    "totalgold", "earnedgold", "earned gpm", "earnedgoldshare",
    "goldspent", "gspd", "gpr",
    "total cs", "minionkills", "monsterkills",
    "monsterkillsownjungle", "monsterkillsenemyjungle", "cspm",
    "goldat10", "xpat10", "csat10",
    "opp_goldat10", "opp_xpat10", "opp_csat10",
    "golddiffat10", "xpdiffat10", "csdiffat10",
    "killsat10", "assistsat10", "deathsat10",
    "opp_killsat10", "opp_assistsat10", "opp_deathsat10",
    "goldat15", "xpat15", "csat15",
    "opp_goldat15", "opp_xpat15", "opp_csat15",
    "golddiffat15", "xpdiffat15", "csdiffat15",
    "killsat15", "assistsat15", "deathsat15",
    "opp_killsat15", "opp_assistsat15", "opp_deathsat15",
    "goldat20", "xpat20", "csat20",
    "opp_goldat20", "opp_xpat20", "opp_csat20",
    "golddiffat20", "xpdiffat20", "csdiffat20",
    "killsat20", "assistsat20", "deathsat20",
    "opp_killsat20", "opp_assistsat20", "opp_deathsat20",
    "goldat25", "xpat25", "csat25",
    "opp_goldat25", "opp_xpat25", "opp_csat25",
    "golddiffat25", "xpdiffat25", "csdiffat25",
    "killsat25", "assistsat25", "deathsat25",
    "opp_killsat25", "opp_assistsat25", "opp_deathsat25",
})

# Safe columns that can be used for pre-match features
SAFE_CONTEXT_COLUMNS: frozenset[str] = frozenset({
    "gameid", "date", "league", "year", "split", "playoffs",
    "game", "patch", "side", "teamname", "teamid",
    "playername", "playerid", "position",
    "participantid", "datacompleteness",
})

# Tier 1 major leagues
TIER1_LEAGUES: frozenset[str] = frozenset({
    "LCK", "LPL", "LEC", "LCS", "LTA", "LTA N", "LTA S",
    "LCP", "MSI", "WLDs", "EWC", "FST",
})


class OracleElixirDataset:
    """Loads and queries Oracle's Elixir LoL match data.

    All queries enforce temporal safety: only rows with date < target_date
    are returned for pre-match feature generation.
    """

    def __init__(self, data_dir: Path | None = None) -> None:
        self._data_dir = data_dir or _DEFAULT_DATA_DIR
        self._df: pd.DataFrame | None = None
        self._loaded = False

    @property
    def df(self) -> pd.DataFrame:
        """Return the combined DataFrame, loading on first access."""
        if not self._loaded:
            self._load_all()
        if self._df is None:
            raise RuntimeError("Dataset failed to load")
        return self._df

    def _load_all(self) -> None:
        """Load and combine all three year CSVs."""
        frames: list[pd.DataFrame] = []
        for year in [2024, 2025, 2026]:
            path = self._data_dir / (
                f"{year}_LoL_esports_match_data_from_OraclesElixir.csv"
            )
            if not path.exists():
                logger.warning("Missing dataset: %s", path)
                continue
            df = pd.read_csv(
                path,
                low_memory=False,
                parse_dates=["date"],
            )
            frames.append(df)
            logger.info("Loaded %s: %d rows, %d games", path.name, len(df), df["gameid"].nunique())

        if not frames:
            raise FileNotFoundError(f"No Oracle Elixir CSVs found in {self._data_dir}")

        self._df = pd.concat(frames, ignore_index=True)
        self._loaded = True
        logger.info(
            "Combined dataset: %d rows, %d games, %d teams, %d players",
            len(self._df),
            self._df["gameid"].nunique(),
            self._df["teamname"].nunique(),
            self._df["playername"].nunique(),
        )

    def get_team_games_before(
        self,
        team_name: str,
        before_date: datetime | str,
    ) -> pd.DataFrame:
        """Return all rows for a team's games strictly before before_date.

        Args:
            team_name: Team name as it appears in the dataset.
            before_date: Cutoff date. Only matches with date < before_date
                are returned.

        Returns:
            DataFrame with all player-rows for the team's past games.
        """
        if isinstance(before_date, str):
            before_date = pd.Timestamp(before_date)
        df = self.df
        mask = (df["teamname"].str.lower() == team_name.lower()) & (df["date"] < before_date)
        return df[mask].copy()

    def get_matchup_history(
        self,
        team_a: str,
        team_b: str,
        before_date: datetime | str,
    ) -> pd.DataFrame:
        """Return all games between team_a and team_b before before_date.

        Returns rows for BOTH teams, deduplicated by gameid.
        """
        if isinstance(before_date, str):
            before_date = pd.Timestamp(before_date)
        df = self.df

        # Find gameids where both teams played
        a_games = set(df[
            (df["teamname"].str.lower() == team_a.lower()) &
            (df["date"] < before_date)
        ]["gameid"].unique())

        b_games = set(df[
            (df["teamname"].str.lower() == team_b.lower()) &
            (df["date"] < before_date)
        ]["gameid"].unique())

        h2h_gameids = a_games & b_games
        return df[df["gameid"].isin(h2h_gameids)].copy()

    def get_team_game_summaries_before(
        self,
        team_name: str,
        before_date: datetime | str,
        min_games: int = 0,
    ) -> pd.DataFrame:
        """Return one row per game for a team (team-level aggregates) before date.

        Groups by gameid and returns team-level stats (win/loss, team kills, etc.)
        using only safe pre-match context columns.
        """
        rows = self.get_team_games_before(team_name, before_date)
        if len(rows) == 0:
            return pd.DataFrame()

        # Group by gameid, keeping first row's context columns
        game_cols = ["gameid", "date", "league", "split", "playoffs", "patch", "side"]
        available = [c for c in game_cols if c in rows.columns]

        summaries = rows.groupby("gameid").agg(
            **{
                **{c: ("first", c) for c in available},
                "players": ("playername", lambda x: sorted(x.unique())),
                "champions": ("champion", lambda x: sorted(x.unique())),
                "bans": ("ban1", "first"),  # bans are team-level, same for all rows
            }
        ).reset_index(drop=True)

        # Add result (win/loss) — safe to use since these are PAST games
        if "result" in rows.columns:
            win_rows = rows[rows["result"] == 1]
            if len(win_rows) > 0:
                summaries["win"] = 1
            else:
                summaries["win"] = 0

        # Sort by date
        if "date" in summaries.columns:
            summaries = summaries.sort_values("date", ascending=False)

        return summaries

    def get_player_history_before(
        self,
        player_name: str,
        before_date: datetime | str,
    ) -> pd.DataFrame:
        """Return all rows for a player before before_date."""
        if isinstance(before_date, str):
            before_date = pd.Timestamp(before_date)
        df = self.df
        mask = (df["playername"].str.lower() == player_name.lower()) & (df["date"] < before_date)
        return df[mask].copy()

    def get_league_games_before(
        self,
        league: str,
        before_date: datetime | str,
    ) -> pd.DataFrame:
        """Return all games in a league before before_date."""
        if isinstance(before_date, str):
            before_date = pd.Timestamp(before_date)
        df = self.df
        mask = (df["league"] == league) & (df["date"] < before_date)
        return df[mask].copy()

    def get_tier1_games_before(
        self,
        before_date: datetime | str,
    ) -> pd.DataFrame:
        """Return all Tier 1 league games before before_date."""
        if isinstance(before_date, str):
            before_date = pd.Timestamp(before_date)
        df = self.df
        mask = df["league"].isin(TIER1_LEAGUES) & (df["date"] < before_date)
        return df[mask].copy()


# Singleton instance
_dataset: OracleElixirDataset | None = None


def get_dataset(data_dir: Path | None = None) -> OracleElixirDataset:
    """Return the singleton OracleElixirDataset instance."""
    global _dataset
    if _dataset is None:
        _dataset = OracleElixirDataset(data_dir)
    return _dataset
