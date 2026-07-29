"""Tests for esports-only market filter."""

from __future__ import annotations

from prediction_bot.kalshi.discovery import (
    is_esports_market,
    split_markets_esports_excluded,
)


class TestIsEsportsMarket:
    """is_esports_market() returns True only for LOL/CS2/Dota2/Valorant."""

    # ── Included ──

    def test_kxlolmap_is_esports(self) -> None:
        assert is_esports_market(
            ticker="KXLOLMAP-26JUL281430AZREMR-2-MR",
            title="Will Mental Rush win map 2?",
        ) is True

    def test_kxlolgame_is_esports(self) -> None:
        assert is_esports_market(
            ticker="KXLOLGAME-26JUL301330BWSU-SU",
            title="Will SU Esports win?",
        ) is True

    def test_kxcs2game_is_esports(self) -> None:
        assert is_esports_market(
            ticker="KXCS2GAME-26JUL281430OLDFOR-OLD",
            title="Will OLDBOYS- win?",
        ) is True

    def test_kxdota2game_is_esports(self) -> None:
        assert is_esports_market(
            ticker="KXDOTA2GAME-26JUL310400AMAVG-VG",
            title="Will Vici Gaming win?",
        ) is True

    def test_kxdota2map_is_esports(self) -> None:
        assert is_esports_market(
            ticker="KXDOTA2MAP-26JUL310400PLATRES-2-RES",
            title="Will Team Resilience win map 2?",
        ) is True

    def test_kxvalorantgame_is_esports(self) -> None:
        assert is_esports_market(
            ticker="KXVALORANTGAME-26JUL282100BBB2GAME-BBB",
            title="Will Contra win?",
        ) is True

    # ── Excluded: traditional sports ──

    def test_soccer_spread_excluded(self) -> None:
        """KXCLUBFSPREAD → excluded (soccer, not esports)."""
        assert is_esports_market(
            ticker="KXCLUBFSPREAD-26JUL28CFCWES-CFC5",
            title="Chelsea wins by more than 4.5 goals?",
        ) is False

    def test_soccer_game_excluded(self) -> None:
        assert is_esports_market(
            ticker="KXCLUBFGAME-26JUL30SWEENN-TIE",
            title="Essen vs Ennepetal Winner?",
        ) is False

    def test_baseball_excluded(self) -> None:
        assert is_esports_market(
            ticker="KXMLBKS-26JUL281945CHCSTL-CHCCREA53-7",
            title="Colin Rea: 7+ strikeouts?",
        ) is False

    def test_tennis_excluded(self) -> None:
        assert is_esports_market(
            ticker="KXITFMATCH-26JUL28OLIVER-VER",
            title="Will Martin Vergara win?",
        ) is False

    def test_wta_tournament_excluded(self) -> None:
        """WTA tournament → excluded (tennis, not esports)."""
        assert is_esports_market(
            ticker="KXWTA-26WASHIN-SAM",
            title="Will Liudmila Samsonova win the WTA Washington?",
        ) is False

    def test_atp_excluded(self) -> None:
        assert is_esports_market(
            ticker="KXATPMATCH-26JUL28KWONGEA-KWON",
            title="Will Soonwoo Kwon win?",
        ) is False

    def test_basketball_excluded(self) -> None:
        assert is_esports_market(
            ticker="KXWNBAGAME-26JUL30NYLV-NY",
            title="New York vs Las Vegas: New York wins?",
        ) is False

    # ── Excluded: non-sports ──

    def test_weather_excluded(self) -> None:
        assert is_esports_market(
            ticker="KXTEMPCHIH-26JUL2807-T75.99",
            title="Will the temp in Chicago be above 75.99?",
        ) is False

    # ── Edge cases ──

    def test_empty_ticker(self) -> None:
        assert is_esports_market(
            ticker="",
            title="",
            rules_primary="",
        ) is False

    def test_unknown_ticker_but_esports_rules(self) -> None:
        """Unknown ticker prefix but rules_primary says League of Legends → True."""
        assert is_esports_market(
            ticker="KXUNKNOWN-01",
            title="",
            rules_primary="If T1 wins the LCK 2026: T1 vs Gen.G League of Legends match, then Yes.",
        ) is True


class TestSplitMarketsEsportsExcluded:
    """split_markets_esports_excluded() partitions correctly."""

    def test_all_esports(self) -> None:
        e, x = split_markets_esports_excluded([
            {"ticker": "KXLOLGAME-01", "title": "T1 wins"},
            {"ticker": "KXCS2GAME-01", "title": "Navi wins"},
            {"ticker": "KXDOTA2MAP-01", "title": "Resilience wins map 1"},
        ])
        assert len(e) == 3
        assert len(x) == 0

    def test_all_excluded(self) -> None:
        e, x = split_markets_esports_excluded([
            {"ticker": "KXCLUBFTOTAL-01", "title": "Over 2.5 goals?"},
            {"ticker": "KXMLBKS-01", "title": "Strikeouts?"},
            {"ticker": "KXGOLDH-01", "title": "Gold price?"},
        ])
        assert len(e) == 0
        assert len(x) == 3

    def test_mixed(self) -> None:
        e, x = split_markets_esports_excluded([
            {"ticker": "KXLOLMAP-01", "title": "map winner"},
            {"ticker": "KXCLUBFTOTAL-01", "title": "goals"},
            {"ticker": "KXVALORANTGAME-01", "title": "Contra"},
            {"ticker": "KXTEMPCHIH-01", "title": "temp"},
        ])
        assert len(e) == 2
        assert len(x) == 2
