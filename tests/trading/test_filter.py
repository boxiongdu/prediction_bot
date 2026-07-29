"""Tests for trading scanner and filter modules."""

from __future__ import annotations

from prediction_bot.trading.filter import filter_market

# ──────────────────────────────────────────────────────────────────────
# Sample KXLOLGAME market dicts for testing (from real Kalshi data)
# ──────────────────────────────────────────────────────────────────────

_KXLOLGAME_TIER2 = {
    "ticker": "KXLOLGAME-26JUL291330PHXDIA-PHX",
    "event_ticker": "KXLOLGAME-26JUL291330PHXDIA",
    "title": (
        "Will Team Phoenix win the Team Phoenix vs. "
        "DIA Ozarox Esports League of Legends match?"
    ),
    "subtitle": "TCL 2026",
    "yes_sub_title": "Team Phoenix",
    "no_sub_title": "DIA Ozarox Esports",
    "category": "Esports",
    "rules_primary": (
        "If Team Phoenix wins the TCL 2026: Team Phoenix vs. "
        "DIA Ozarox Esports League of Legends match, then the "
        "market resolves to Yes."
    ),
}

_KXLOLGAME_TIER1 = {
    "ticker": "KXLOLGAME-26JUL310500BLGWE-BLG",
    "event_ticker": "KXLOLGAME-26JUL310500BLGWE",
    "title": (
        "Will Bilibili Gaming win the Bilibili Gaming vs. "
        "Team WE League of Legends match?"
    ),
    "subtitle": "LPL 2026",
    "yes_sub_title": "Bilibili Gaming",
    "no_sub_title": "Team WE",
    "category": "Esports",
    "rules_primary": (
        "If Bilibili Gaming wins the LPL 2026: Bilibili Gaming vs. "
        "Team WE League of Legends match, then the market resolves to Yes."
    ),
}

# Non-esports market (should fail stage 1 — uses non-KXLOL ticker)
_NOT_ESPORTS = {
    "ticker": "KXWEATHER-26JUL010000XXXX-XX",
    "event_ticker": "KXWEATHER-26JUL010000XXXX",
    "title": "Will it rain tomorrow?",
    "subtitle": None,
    "category": "Weather",
    "rules_primary": "If it rains tomorrow, the market resolves to Yes.",
}


class TestFilterMarket:
    """Tests for filter_market() with KXLOLGAME series."""

    def test_tier1_passed(self) -> None:
        result = filter_market(_KXLOLGAME_TIER1, tier1_only=True)
        assert result.passed is True
        assert result.contract_type == "match_winner"
        assert result.league_tier == "tier1"
        assert result.game == "league-of-legends"
        assert len(result.team_a) > 0
        assert len(result.team_b) > 0

    def test_tier2_rejected_when_tier1_only(self) -> None:
        result = filter_market(_KXLOLGAME_TIER2, tier1_only=True)
        assert result.passed is False
        assert result.reject_reason == "minor_league"
        assert result.contract_type == "match_winner"
        assert result.league_tier == "tier2_or_lower"

    def test_tier2_passed_when_tier1_disabled(self) -> None:
        result = filter_market(_KXLOLGAME_TIER2, tier1_only=False)
        assert result.passed is True
        assert result.contract_type == "match_winner"

    def test_not_esports_rejected(self) -> None:
        result = filter_market(_NOT_ESPORTS, tier1_only=True)
        assert result.passed is False
        assert result.reject_reason == "not_esports"


class TestFilterMarkets:
    """Tests for filter_markets() batch function."""

    def test_batch_filter(self) -> None:
        from prediction_bot.trading.filter import filter_markets

        markets = [
            _KXLOLGAME_TIER1,
            _KXLOLGAME_TIER2,
            _NOT_ESPORTS,
        ]

        results = filter_markets(
            markets,
            tier1_only=True,
            scan_id="test",
            query_params="series_ticker=KXLOLGAME",
        )

        assert len(results) == 1
        assert results[0].ticker == _KXLOLGAME_TIER1["ticker"]

    def test_all_pass_without_tier1(self) -> None:
        from prediction_bot.trading.filter import filter_markets

        markets = [_KXLOLGAME_TIER1, _KXLOLGAME_TIER2]
        results = filter_markets(
            markets,
            tier1_only=False,
            scan_id="test",
            query_params="series_ticker=KXLOLGAME",
        )
        assert len(results) == 2


class TestDiscoveryLedger:
    """Tests for DiscoveryLedger."""

    def test_record_and_summary(self, tmp_path) -> None:
        from prediction_bot.trading.scanner import DiscoveryLedger

        db = str(tmp_path / "test_discovery.db")
        ledger = DiscoveryLedger(db)

        ledger.record(
            _KXLOLGAME_TIER1,
            scan_id="test",
            query_params="series_ticker=KXLOLGAME",
            filter_status="passed",
            contract_type="match_winner",
            game="league-of-legends",
            tournament="LPL 2026",
            league_tier="tier1",
        )

        ledger.record(
            _KXLOLGAME_TIER2,
            scan_id="test",
            query_params="series_ticker=KXLOLGAME",
            filter_status="rejected",
            reject_reason="minor_league",
            contract_type="match_winner",
            game="league-of-legends",
            tournament="TCL 2026",
            league_tier="tier2_or_lower",
        )

        summary = ledger.summary("test")
        assert summary["total"] == 2
        assert summary["passed"] == 1
        assert summary["rejected"] == 1
        assert "minor_league" in summary["rejection_reasons"]
