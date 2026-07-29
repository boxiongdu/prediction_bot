"""Tests for ticker prefix parser — the #1 determinant of contract_type and game."""

from __future__ import annotations

from prediction_bot.agents.schema import (
    ContractType,
    Sport,
    parse_ticker,
)


class TestParseTicker:
    """parse_ticker() extracts contract_type, sport, game from ticker prefix."""

    # ── Esports ──

    def test_lol_game(self) -> None:
        r = parse_ticker("KXLOLGAME-26JUL301330BWSU-SU")
        assert r["contract_type"] == ContractType.MATCH_WINNER.value
        assert r["sport"] == Sport.ESPORTS.value
        assert r["game"] == "league-of-legends"

    def test_lol_map(self) -> None:
        r = parse_ticker("KXLOLMAP-26JUL281430AZREMR-2-MR")
        assert r["contract_type"] == ContractType.MAP_WINNER.value
        assert r["sport"] == Sport.ESPORTS.value
        assert r["game"] == "league-of-legends"

    def test_lol_total_maps(self) -> None:
        r = parse_ticker("KXLOLTOTALMAPS-26JUL310500MVKTSW-3")
        assert r["contract_type"] == ContractType.TOTAL_MAPS.value
        assert r["sport"] == Sport.ESPORTS.value
        assert r["game"] == "league-of-legends"

    def test_cs2_game(self) -> None:
        r = parse_ticker("KXCS2GAME-26JUL281430OLDFOR-OLD")
        assert r["contract_type"] == ContractType.MATCH_WINNER.value
        assert r["sport"] == Sport.ESPORTS.value
        assert r["game"] == "cs2"

    def test_dota2_game(self) -> None:
        r = parse_ticker("KXDOTA2GAME-26JUL310400AMAVG-VG")
        assert r["contract_type"] == ContractType.MATCH_WINNER.value
        assert r["sport"] == Sport.ESPORTS.value
        assert r["game"] == "dota2"

    def test_dota2_map(self) -> None:
        r = parse_ticker("KXDOTA2MAP-26JUL310400PLATRES-2-RES")
        assert r["contract_type"] == ContractType.MAP_WINNER.value
        assert r["sport"] == Sport.ESPORTS.value
        assert r["game"] == "dota2"

    def test_valorant_game(self) -> None:
        r = parse_ticker("KXVALORANTGAME-26JUL282100BBB2GAME-BBB")
        assert r["contract_type"] == ContractType.MATCH_WINNER.value
        assert r["sport"] == Sport.ESPORTS.value
        assert r["game"] == "valorant"

    def test_valorant_map(self) -> None:
        r = parse_ticker("KXVALORANTMAP-26JUL282100BBB2GAME-2-BBB")
        assert r["contract_type"] == ContractType.MAP_WINNER.value
        assert r["sport"] == Sport.ESPORTS.value
        assert r["game"] == "valorant"

    # ── Baseball — MLB ──

    def test_mlb_strikeouts(self) -> None:
        r = parse_ticker("KXMLBKS-26JUL281945CHCSTL-CHCCREA53-7")
        assert r["contract_type"] == ContractType.PLAYER_PROP.value
        assert r["sport"] == Sport.BASEBALL.value
        assert r["game"] is None

    def test_mlb_rbi(self) -> None:
        r = parse_ticker("KXMLBRBI-26JUL282210SEALAD-SEARAROZARENA56-2")
        assert r["contract_type"] == ContractType.PLAYER_PROP.value
        assert r["sport"] == Sport.BASEBALL.value

    def test_mlb_home_runs(self) -> None:
        r = parse_ticker("KXMLBHR-26JUL282210SEALAD-SEARAROZARENA56-2")
        assert r["contract_type"] == ContractType.PLAYER_PROP.value
        assert r["sport"] == Sport.BASEBALL.value

    def test_mlb_hits(self) -> None:
        r = parse_ticker("KXMLBHIT-26JUL282210SEALAD-SEARAROZARENA56-4")
        assert r["contract_type"] == ContractType.PLAYER_PROP.value

    def test_mlb_total_bases(self) -> None:
        r = parse_ticker("KXMLBTB-26JUL282210SEALAD-SEARAROZARENA56-6")
        assert r["contract_type"] == ContractType.PLAYER_PROP.value

    def test_mlb_game(self) -> None:
        r = parse_ticker("KXMLBGAME-26JUL302210SEALAD-SEA")
        assert r["contract_type"] == ContractType.MATCH_WINNER.value
        assert r["sport"] == Sport.BASEBALL.value

    def test_mlb_team_total(self) -> None:
        r = parse_ticker("KXMLBTEAMTOTAL-26JUL281945CHCSTL-STL8")
        assert r["contract_type"] == ContractType.TOTAL_RUNS.value

    def test_mlb_spread(self) -> None:
        r = parse_ticker("KXMLBSPREAD-26JUL281945CHCSTL-STL4")
        assert r["contract_type"] == ContractType.SPREAD.value

    # ── Baseball — NPB/KBO/LMB ──

    def test_npb_game(self) -> None:
        r = parse_ticker("KXNPBGAME-26JUL310500ORISAI-SAI")
        assert r["contract_type"] == ContractType.MATCH_WINNER.value
        assert r["sport"] == Sport.BASEBALL.value

    def test_kbo_game(self) -> None:
        r = parse_ticker("KXKBOGAME-26JUL310530SSGKIW-SSG")
        assert r["contract_type"] == ContractType.MATCH_WINNER.value

    def test_lmb_game(self) -> None:
        r = parse_ticker("KXLMBGAME-26JUL312235ADMTDT-TDT")
        assert r["contract_type"] == ContractType.MATCH_WINNER.value

    # ── Soccer ──

    def test_clubf_game(self) -> None:
        r = parse_ticker("KXCLUBFGAME-26JUL30SWEENN-TIE")
        assert r["contract_type"] == ContractType.MATCH_WINNER.value
        assert r["sport"] == Sport.SOCCER.value

    def test_clubf_total(self) -> None:
        r = parse_ticker("KXCLUBFTOTAL-26JUL28CFCWES-10")
        assert r["contract_type"] == ContractType.TOTAL_GOALS.value
        assert r["sport"] == Sport.SOCCER.value

    def test_clubf_spread(self) -> None:
        r = parse_ticker("KXCLUBFSPREAD-26JUL28CFCWES-CFC5")
        assert r["contract_type"] == ContractType.SPREAD.value

    def test_clubf_btts(self) -> None:
        r = parse_ticker("KXCLUBFBTTS-26JUL31SOUWIG-BTTS")
        assert r["contract_type"] == ContractType.BTTS.value

    def test_conmebol_totals(self) -> None:
        r = parse_ticker("KXCONMEBOLSUDTOTAL-26JUL30OHFBOC-6")
        assert r["contract_type"] == ContractType.TOTAL_GOALS.value

    # ── Tennis ──

    def test_itf_match(self) -> None:
        r = parse_ticker("KXITFMATCH-26JUL28OLIVER-VER")
        assert r["contract_type"] == ContractType.MATCH_WINNER.value
        assert r["sport"] == Sport.TENNIS.value
        assert r["game"] is None

    def test_atp_set_winner(self) -> None:
        r = parse_ticker("KXATPSETWINNER-26JUL28KWONGEA-2-KWON")
        assert r["contract_type"] == ContractType.SET_WINNER.value
        assert r["sport"] == Sport.TENNIS.value

    def test_atp_game_spread(self) -> None:
        r = parse_ticker("KXATPGSPREAD-26JUL28KOUWIN-WIN2")
        assert r["contract_type"] == ContractType.TOTAL_GAMES.value

    def test_wta_tournament(self) -> None:
        r = parse_ticker("KXWTA-26WASHIN-SAM")
        assert r["contract_type"] == ContractType.TOURNAMENT_WINNER.value
        assert r["sport"] == Sport.TENNIS.value

    # ── Basketball ──

    def test_wnba_game(self) -> None:
        r = parse_ticker("KXWNBAGAME-26JUL30NYLV-NY")
        assert r["contract_type"] == ContractType.MATCH_WINNER.value
        assert r["sport"] == Sport.BASKETBALL.value

    # ── Edge cases ──

    def test_empty_ticker(self) -> None:
        r = parse_ticker("")
        assert r["contract_type"] is None
        assert r["sport"] is None
        assert r["game"] is None

    def test_unknown_prefix(self) -> None:
        r = parse_ticker("KXUNKNOWNPREFIX-01-02")
        assert r["contract_type"] is None
        assert r["sport"] is None
        assert r["game"] is None
