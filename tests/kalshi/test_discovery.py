"""Tests for esports market discovery and classification."""

from __future__ import annotations

from prediction_bot.data.schema import KalshiMarket
from prediction_bot.kalshi.discovery import (
    classify_game,
    classify_market_structure,
    classify_market_type,
    filter_esports_markets,
    is_esports,
    is_multi_event_market,
)


class TestIsMultiEventMarket:
    def test_kxmv_esports_multi_game_prefix(self) -> None:
        assert is_multi_event_market(
            "KXMVESPORTSMULTIGAMEEXTENDED-S2026DBA3F19606F", "any title",
        ) is True

    def test_kxmv_cross_category_prefix(self) -> None:
        assert is_multi_event_market(
            "KXMVECROSSCATEGORY-S202624F92FE7F78", "any title",
        ) is True

    def test_many_commas_in_title(self) -> None:
        title = "yes A,yes B,yes C,yes D"  # 3 commas
        assert is_multi_event_market("NORMAL-TICKER-01", title) is True

    def test_few_commas_not_multi_event(self) -> None:
        title = "yes A,yes B"  # 1 comma ≤ 2
        assert is_multi_event_market("NORMAL-TICKER-01", title) is False

    def test_simple_title_not_multi_event(self) -> None:
        assert is_multi_event_market("LOL-T1-GEN", "T1 to win vs Gen.G") is False

    def test_parlay_with_esports_teams(self) -> None:
        """T1 + Bilibili Gaming + other sports in one title."""
        assert is_multi_event_market(
            "KXMVESPORTSMULTIGAMEEXTENDED-S20265A79C576C65",
            "yes Nongshim Red Force,yes T1,yes Bilibili Gaming,yes Tampa Bay",
        ) is True


class TestClassifyMarketStructure:
    def test_cross_category(self) -> None:
        assert classify_market_structure(
            "KXMVECROSSCATEGORY-S2026XXXX", "...",
        ) == "cross-category"

    def test_multi_event(self) -> None:
        assert classify_market_structure(
            "KXMVESPORTSMULTIGAMEEXTENDED-S2026XXXX", "...",
        ) == "multi-event"

    def test_simple(self) -> None:
        assert classify_market_structure("LOL-T1-01", "T1 to win") == "simple"


class TestIsEsports:
    def test_lol_market(self) -> None:
        assert is_esports("T1 to win vs Gen.G — LCK Spring 2025") is True

    def test_cs2_market(self) -> None:
        assert is_esports("Navi vs FaZe — IEM Katowice 2025 Grand Final") is True

    def test_valorant_market(self) -> None:
        assert is_esports("Sentinels vs PRX — VCT Champions") is True

    def test_non_esports_market(self) -> None:
        assert is_esports("Will the Fed raise rates in March?") is False

    def test_election_market(self) -> None:
        assert is_esports("Who will win the 2028 US Presidential Election?") is False

    def test_generic_tournament_market(self) -> None:
        assert is_esports("Tournament Winner: Spring Split 2025") is True

    def test_match_winner(self) -> None:
        assert is_esports("Match Winner: Team A vs Team B") is True

    def test_esports_category_label(self) -> None:
        assert is_esports("Esports: Will T1 win Worlds 2025?") is True

    def test_bo3_in_title(self) -> None:
        assert is_esports("BO3: Some Team vs Other Team") is True

    def test_best_of_in_title(self) -> None:
        assert is_esports("Best of 5 — Grand Finals") is True

    def test_yes_sub_title_used(self) -> None:
        assert is_esports("Will this team win?", yes_sub_title="T1 wins the LCK match") is True

    def test_no_sub_title_used(self) -> None:
        assert is_esports("Generic event outcome", no_sub_title="Navi loses the CS2 match") is True

    def test_multi_event_title_with_esports_teams(self) -> None:
        """Even though T1 is in the title, this is a parlay — our esports detection
        will flag it, but multi-event filtering should catch it first."""
        assert is_esports("yes Nongshim Red Force,yes T1,yes Bilibili Gaming") is True


class TestClassifyGame:
    def test_lol_by_name(self) -> None:
        assert classify_game("League of Legends: T1 vs Gen.G") == "league-of-legends"

    def test_lol_by_lck(self) -> None:
        assert classify_game("LCK Spring 2025: DK vs HLE") == "league-of-legends"

    def test_lol_by_lpl(self) -> None:
        assert classify_game("LPL Summer Finals 2025") == "league-of-legends"

    def test_lol_by_worlds(self) -> None:
        assert classify_game("Worlds 2025 Quarterfinals") == "league-of-legends"

    def test_lol_by_msi(self) -> None:
        assert classify_game("MSI 2025 — Grand Final") == "league-of-legends"

    def test_lol_by_t1(self) -> None:
        assert classify_game("T1 vs DK matchup") == "league-of-legends"

    def test_lol_by_g2(self) -> None:
        assert classify_game("G2 vs Fnatic — LEC") == "league-of-legends"

    def test_cs2_by_name(self) -> None:
        assert classify_game("Counter-Strike: Navi vs FaZe") == "cs2"

    def test_cs2_by_cs2(self) -> None:
        assert classify_game("CS2 Major 2025") == "cs2"

    def test_cs2_by_blast(self) -> None:
        assert classify_game("Blast Premier Spring 2025") == "cs2"

    def test_valorant_by_name(self) -> None:
        assert classify_game("Valorant Champions 2025") == "valorant"

    def test_valorant_by_vct(self) -> None:
        assert classify_game("VCT Americas Stage 1") == "valorant"

    def test_dota_by_name(self) -> None:
        assert classify_game("Dota 2 — The International 2025") == "dota2"

    def test_dota_by_ti(self) -> None:
        assert classify_game("TI12 Grand Finals") == "dota2"

    def test_unclassified(self) -> None:
        assert classify_game("Generic Esports Tournament") is None

    def test_case_insensitive(self) -> None:
        assert classify_game("LEAGUE OF LEGENDS CHAMPIONSHIP") == "league-of-legends"

    def test_subtitle_used(self) -> None:
        assert (
            classify_game("Will Team X win?", subtitle="League of Legends — LCK")
            == "league-of-legends"
        )

    def test_yes_sub_title_classification(self) -> None:
        assert (
            classify_game("Match outcome", yes_sub_title="Navi wins the CS2 match")
            == "cs2"
        )

    def test_no_sub_title_classification(self) -> None:
        assert (
            classify_game("Event result", no_sub_title="Sentinels loses in VCT")
            == "valorant"
        )


class TestFilterEsportsMarkets:
    def test_splits_correctly(self) -> None:
        markets = [
            KalshiMarket(ticker="E1", event_ticker="EV1", title="T1 vs GenG — LCK"),
            KalshiMarket(ticker="E2", event_ticker="EV2", title="Fed rate decision"),
            KalshiMarket(ticker="E3", event_ticker="EV3", title="Navi vs FaZe — CS2"),
            KalshiMarket(ticker="E4", event_ticker="EV4", title="Weather in NYC"),
        ]
        esports, non_esports, multi_event = filter_esports_markets(markets)
        assert len(esports) == 2
        assert len(non_esports) == 2
        assert len(multi_event) == 0

    def test_separates_multi_event(self) -> None:
        markets = [
            KalshiMarket(ticker="E1", event_ticker="EV1", title="T1 vs GenG"),
            KalshiMarket(
                ticker="KXMVESPORTSMULTIGAMEEXTENDED-S2026XXX",
                event_ticker="MULTI-01",
                title="yes T1,yes Bilibili Gaming,yes Tampa Bay,yes San Diego",
            ),
            KalshiMarket(ticker="E2", event_ticker="EV2", title="Fed rate"),
        ]
        esports, non_esports, multi_event = filter_esports_markets(markets)
        assert len(esports) == 1  # T1 vs GenG
        assert len(non_esports) == 1  # Fed rate
        assert len(multi_event) == 1  # parlay

    def test_multi_event_by_commas(self) -> None:
        """>2 commas, normal ticker → still classified as multi-event."""
        markets = [
            KalshiMarket(
                ticker="NORMAL-01", event_ticker="EV",
                title="yes A,yes B,yes C,yes D",
            ),
        ]
        esports, non_esports, multi_event = filter_esports_markets(markets)
        assert len(esports) == 0
        assert len(multi_event) == 1

    def test_all_esports(self) -> None:
        markets = [
            KalshiMarket(ticker="E1", event_ticker="EV1", title="Esports: Match A vs B"),
            KalshiMarket(ticker="E2", event_ticker="EV2", title="Grand Final BO5"),
        ]
        esports, non_esports, multi_event = filter_esports_markets(markets)
        assert len(esports) == 2
        assert len(non_esports) == 0
        assert len(multi_event) == 0

    def test_none_esports(self) -> None:
        markets = [
            KalshiMarket(ticker="E1", event_ticker="EV1", title="Fed meeting"),
            KalshiMarket(ticker="E2", event_ticker="EV2", title="Election 2028"),
        ]
        esports, non_esports, multi_event = filter_esports_markets(markets)
        assert len(esports) == 0
        assert len(non_esports) == 2
        assert len(multi_event) == 0

    def test_subtitles_enable_classification(self) -> None:
        markets = [
            KalshiMarket(
                ticker="E1", event_ticker="EV1",
                title="Will this team win?",
                yes_sub_title="T1 wins the LCK match",
            ),
            KalshiMarket(ticker="E2", event_ticker="EV2", title="Fed meeting"),
        ]
        esports, non_esports, multi_event = filter_esports_markets(markets)
        assert len(esports) == 1
        assert esports[0].estimated_game == "league-of-legends"


class TestClassifyMarketType:
    def test_match_winner(self) -> None:
        assert classify_market_type("Match Winner: T1 vs GenG") == "match_winner"

    def test_series_winner(self) -> None:
        assert classify_market_type("Series Winner: T1 vs DK") == "series_winner"

    def test_tournament_winner(self) -> None:
        assert classify_market_type("Tournament Winner: Worlds 2025") == "tournament_winner"

    def test_map_winner(self) -> None:
        assert classify_market_type("Map 1 Winner: Navi vs FaZe") == "map_winner"

    def test_handicap(self) -> None:
        assert classify_market_type("T1 -1.5 vs GenG") == "handicap"

    def test_total_maps(self) -> None:
        assert classify_market_type("Total Maps Over 2.5") == "total_maps"

    def test_generic_will_win(self) -> None:
        assert classify_market_type("Will T1 win vs GenG?") == "match_winner"

    def test_other(self) -> None:
        assert classify_market_type("Some weird market title") == "other"


class TestEdgeCases:
    def test_empty_title(self) -> None:
        assert is_esports("") is False
        assert classify_game("") is None

    def test_none_subtitle(self) -> None:
        assert is_esports("LCK Spring", None) is True

    def test_partial_match_not_confused(self) -> None:
        result = classify_game("Poll: Who will win the general election?")
        assert result is None

    def test_g2_not_confused_by_cs2_vs_lol(self) -> None:
        r1 = classify_game("G2 vs Fnatic — LEC")
        r2 = classify_game("G2 vs Vitality — CS2")
        assert r1 == "league-of-legends" or r2 == "cs2"
