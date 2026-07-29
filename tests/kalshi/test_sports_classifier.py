"""Tests for sports-vs-non-sports market classification."""

from __future__ import annotations

from prediction_bot.kalshi.discovery import (
    is_sports_market,
    split_markets_sports_non_sports,
)


class TestIsSportsMarket:
    """Primary: ticker-prefix classification."""

    def test_mlb_player_prop(self) -> None:
        assert is_sports_market(
            ticker="KXMLBKS-26JUL281945CHCSTL-CHCCREA53-7",
            title="Colin Rea: 7+ strikeouts?",
        ) is True

    def test_npb_game(self) -> None:
        assert is_sports_market(
            ticker="KXNPBGAME-26JUL310500ORISAI-SAI",
            title="Orix Buffaloes vs Saitama Seibu Lions winner?",
        ) is True

    def test_kbo_spread(self) -> None:
        assert is_sports_market(
            ticker="KXKBOSPREAD-26JUL310530SSGKIW-SSG3",
            title="Will the SSG Landers win by over 2.5 runs?",
        ) is True

    def test_lmb_game(self) -> None:
        assert is_sports_market(
            ticker="KXLMBGAME-26JUL312235ADMTDT-TDT",
            title="Acereros de Monclova vs Toros de Tijuana winner?",
        ) is True

    def test_euro_soccer_spread(self) -> None:
        assert is_sports_market(
            ticker="KXEKSTRAKLASASPREAD-26JUL31MOTJAG-MOT3",
            title="Motor Lublin wins by more than 2.5 goals?",
        ) is True

    def test_conmebol_totals(self) -> None:
        assert is_sports_market(
            ticker="KXCONMEBOLSUDTOTAL-26JUL30OHFBOC-6",
            title="Will over 5.5 goals be scored?",
        ) is True

    def test_tennis_itf_match(self) -> None:
        assert is_sports_market(
            ticker="KXITFMATCH-26JUL28OLIVER-VER",
            title="Will Martin Antonio Vergara win?",
        ) is True

    def test_tennis_atp_games_total(self) -> None:
        assert is_sports_market(
            ticker="KXATPGTOTAL-26JUL28KOUWIN-28",
            title="Moise Kouame vs Edward Winter: Total Games",
        ) is True

    def test_wnba_game(self) -> None:
        assert is_sports_market(
            ticker="KXWNBAGAME-26JUL30NYLV-NY",
            title="New York vs Las Vegas: New York wins?",
        ) is True

    def test_tbt_basketball(self) -> None:
        assert is_sports_market(
            ticker="KXTBTGAME-26JUL282100THEHEA-THE",
            title="The Mecca vs Team Heartfire: The Mecca wins",
        ) is True

    def test_lol_match_winner(self) -> None:
        assert is_sports_market(
            ticker="KXLOLGAME-26JUL301330BWSU-SU",
            title="Will SU Esports win?",
        ) is True

    def test_cs2_match_winner(self) -> None:
        assert is_sports_market(
            ticker="KXCS2GAME-26JUL281430OLDFOR-OLD",
            title="Will OLDBOYS- win?",
        ) is True

    def test_dota2_map(self) -> None:
        assert is_sports_market(
            ticker="KXDOTA2MAP-26JUL310400PLATRES-2-RES",
            title="Will Team Resilience win map 2?",
        ) is True

    def test_valorant_game(self) -> None:
        assert is_sports_market(
            ticker="KXVALORANTGAME-26JUL282100BBB2GAME-BBB",
            title="Will Contra win?",
        ) is True

    # ── Non-sports ────────────────────────────────────────────

    def test_commodities_gold(self) -> None:
        assert is_sports_market(
            ticker="KXGOLDH-26JUL2808-T4057.99",
            title="Will GOLD close above 4057.99?",
        ) is False

    def test_commodities_silver(self) -> None:
        assert is_sports_market(
            ticker="KXSILVERD-26JUL2920-T62.75",
            title="Will silver close above 62.75?",
        ) is False

    def test_weather_temp(self) -> None:
        assert is_sports_market(
            ticker="KXTEMPCHIH-26JUL2807-T75.99",
            title="Will the temp in Chicago be above 75.99?",
        ) is False

    def test_weather_rain(self) -> None:
        assert is_sports_market(
            ticker="KXRAIN-26JUL29-SF",
            title="Will it rain in San Francisco?",
        ) is False

    def test_politics_trump(self) -> None:
        assert is_sports_market(
            ticker="KXTRUMPMENTIONB-26JUL28-Z",
            title="What will Donald Trump say?",
        ) is False

    def test_rotten_tomatoes(self) -> None:
        assert is_sports_market(
            ticker="KXRT-26AUG10-T55",
            title="Ice Cream Man Rotten Tomatoes score?",
        ) is False

    def test_energy_natgas(self) -> None:
        assert is_sports_market(
            ticker="KXNATGASD-26JUL2920-T3.145",
            title="Will natural gas close above 3.145?",
        ) is False

    # ── Fallback: unknown ticker, text classification works ────

    def test_unknown_prefix_but_sports_text(self) -> None:
        """Even with an unknown ticker prefix, soccer keywords trigger True."""
        assert is_sports_market(
            ticker="KXUNKNOWN-01",
            title="",
            rules_primary="If Chelsea wins the professional soccer game, then resolves to Yes.",
        ) is True

    def test_unknown_prefix_non_sports_text(self) -> None:
        assert is_sports_market(
            ticker="KXUNKNOWN-02",
            title="Will the Fed raise rates?",
            rules_primary="",
        ) is False

    def test_empty_ticker_text_fallback(self) -> None:
        assert is_sports_market(
            ticker="",
            title="",
            rules_primary="If over 8.5 goals are scored in the professional soccer game...",
        ) is True

    def test_subtitle_fallback(self) -> None:
        assert is_sports_market(
            ticker="KXUNKNOWN-03",
            title="Will this team win?",
            subtitle="League of Legends match",
        ) is True

    def test_yes_sub_title_fallback(self) -> None:
        assert is_sports_market(
            ticker="KXUNKNOWN-04",
            title="Generic outcome?",
            yes_sub_title="T1 wins the LCK match",
        ) is True


class TestSplitMarketsSportsNonSports:
    def test_all_sports(self) -> None:
        sports, non = split_markets_sports_non_sports([
            {"ticker": "KXLOLGAME-01", "title": "T1 wins"},
            {"ticker": "KXMLBKS-01", "title": "Strikeouts?"},
            {"ticker": "KXCLUBFTOTAL-01", "title": "Over 2.5 goals?"},
        ])
        assert len(sports) == 3
        assert len(non) == 0

    def test_all_non_sports(self) -> None:
        sports, non = split_markets_sports_non_sports([
            {"ticker": "KXGOLDH-01", "title": "Gold price?"},
            {"ticker": "KXTEMPCHIH-01", "title": "Chicago temp?"},
            {"ticker": "KXRT-01", "title": "Rotten Tomatoes?"},
        ])
        assert len(sports) == 0
        assert len(non) == 3

    def test_mixed(self) -> None:
        sports, non = split_markets_sports_non_sports([
            {"ticker": "KXLOLGAME-01", "title": "T1 wins"},
            {"ticker": "KXGOLDH-01", "title": "Gold price?"},
            {"ticker": "KXMLBKS-01", "title": "Strikeouts?"},
            {"ticker": "KXTEMPCHIH-01", "title": "Chicago temp?"},
        ])
        assert len(sports) == 2
        assert len(non) == 2

    def test_empty_list(self) -> None:
        sports, non = split_markets_sports_non_sports([])
        assert sports == []
        assert non == []

    def test_preserves_all_fields(self) -> None:
        m = {
            "ticker": "KXLOLGAME-01",
            "title": "T1 wins",
            "rules_primary": "If T1 wins...",
            "extra_field": 42,
        }
        sports, non = split_markets_sports_non_sports([m])
        assert len(sports) == 1
        assert sports[0]["extra_field"] == 42
        assert sports[0]["rules_primary"] == "If T1 wins..."
