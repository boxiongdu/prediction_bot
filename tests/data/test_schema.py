"""Tests for core data schemas."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest
from pydantic import ValidationError

from prediction_bot.data.schema import (
    EsportsMarketAuditEntry,
    FeasibilityReport,
    KalshiMarket,
    KalshiOrderBookSnapshot,
    MarketSide,
    MatchConfidence,
    MatchFormat,
    MatchResult,
    MetadataGap,
    ModelPrediction,
    PaperTradeDecision,
    PlayerRole,
    Roster,
    Team,
    Tournament,
    TournamentTier,
)


class TestTeam:
    def test_minimal_team(self) -> None:
        team = Team(team_id="t1", name="T1")
        assert team.team_id == "t1"
        assert team.name == "T1"
        assert team.aliases == []

    def test_team_with_aliases(self) -> None:
        team = Team(team_id="t1", name="T1", aliases=["SKT", "SK Telecom"])
        assert len(team.aliases) == 2

    def test_team_missing_id_raises(self) -> None:
        with pytest.raises(ValidationError):
            Team(name="No ID")  # type: ignore[arg-type]


class TestMatchResult:
    def test_valid_match(self, sample_match_data: dict) -> None:
        match = MatchResult(**sample_match_data)
        assert match.winner == "t1"
        assert match.format == MatchFormat.BO3

    def test_winner_must_be_participant(self, sample_match_data: dict) -> None:
        sample_match_data["winner"] = "dk"
        with pytest.raises(ValidationError, match="must be one of the participating teams"):
            MatchResult(**sample_match_data)

    def test_winner_null_for_unplayed(self, sample_match_data: dict) -> None:
        sample_match_data["winner"] = None
        match = MatchResult(**sample_match_data)
        assert match.winner is None

    def test_cancelled_flag(self, sample_match_data: dict) -> None:
        sample_match_data["cancelled"] = True
        match = MatchResult(**sample_match_data)
        assert match.cancelled is True


class TestRoster:
    def test_valid_roster(self) -> None:
        roster = Roster(
            team_id="t1",
            players=["faker", "oner", "gumayusi"],
            effective_from=datetime(2025, 1, 1, tzinfo=timezone.utc),
        )
        assert len(roster.players) == 3

    def test_effective_to_after_from(self) -> None:
        with pytest.raises(ValidationError, match="effective_to must be after effective_from"):
            Roster(
                team_id="t1",
                effective_from=datetime(2025, 1, 10, tzinfo=timezone.utc),
                effective_to=datetime(2025, 1, 1, tzinfo=timezone.utc),
            )


class TestModelPrediction:
    def test_valid_prediction(self) -> None:
        pred = ModelPrediction(match_id="m1", model_version="v1.0", prob_team_a=0.62, prob_team_b=0.38)
        assert pred.prob_team_a == 0.62

    def test_prob_must_sum_to_one(self) -> None:
        with pytest.raises(ValidationError, match="sum to approximately 1.0"):
            ModelPrediction(match_id="m1", model_version="v1", prob_team_a=0.6, prob_team_b=0.5)

    def test_prob_range_enforced(self) -> None:
        with pytest.raises(ValidationError):
            ModelPrediction(match_id="m1", model_version="v1", prob_team_a=1.5, prob_team_b=-0.5)

    def test_ood_flag_default_false(self) -> None:
        pred = ModelPrediction(match_id="m1", model_version="v1", prob_team_a=0.5, prob_team_b=0.5)
        assert pred.is_ood is False


# ---------------------------------------------------------------------------
# KalshiMarket — new API format tests
# ---------------------------------------------------------------------------

class TestKalshiMarketNewApi:
    """Test parsing of the current Kalshi API response format."""

    def test_parse_full_new_api_market(self, sample_kalshi_market_raw_new_api: dict) -> None:
        """Direct construction from new API fields (used by client.parse_market)."""
        market = KalshiMarket(
            ticker=sample_kalshi_market_raw_new_api["ticker"],
            event_ticker=sample_kalshi_market_raw_new_api["event_ticker"],
            title=sample_kalshi_market_raw_new_api["title"],
            subtitle=sample_kalshi_market_raw_new_api.get("subtitle"),
            yes_sub_title=sample_kalshi_market_raw_new_api.get("yes_sub_title"),
            no_sub_title=sample_kalshi_market_raw_new_api.get("no_sub_title"),
            yes_bid=Decimal("0.5600"),
            yes_ask=Decimal("0.5900"),
            no_bid=Decimal("0.4000"),
            no_ask=Decimal("0.4300"),
            volume=Decimal("100.00"),
            volume_24h=Decimal("12.00"),
            open_interest=Decimal("40.00"),
            yes_bid_size=Decimal("10.00"),
            yes_ask_size=Decimal("25.00"),
            last_price=Decimal("0.5600"),
            liquidity=Decimal("500.00"),
        )
        assert market.ticker == "LOL-T1-25"
        assert market.yes_sub_title == "T1 wins the match"
        assert market.no_sub_title == "T1 does not win the match"

    def test_yes_bid_parses_correctly(self) -> None:
        """yes_bid_dollars '0.5600' → Decimal('0.5600')."""
        market = KalshiMarket(
            ticker="T", event_ticker="E", title="Test",
            yes_bid=Decimal("0.5600"),
        )
        assert market.yes_bid == Decimal("0.5600")

    def test_yes_ask_parses_correctly(self) -> None:
        """yes_ask_dollars '0.5900' → Decimal('0.5900')."""
        market = KalshiMarket(
            ticker="T", event_ticker="E", title="Test",
            yes_ask=Decimal("0.5900"),
        )
        assert market.yes_ask == Decimal("0.5900")

    def test_spread_equals_decimal(self) -> None:
        """spread = yes_ask - yes_bid = Decimal('0.0300')."""
        market = KalshiMarket(
            ticker="T", event_ticker="E", title="Test",
            yes_bid=Decimal("0.5600"),
            yes_ask=Decimal("0.5900"),
        )
        assert market.spread == Decimal("0.0300")

    def test_sizes_are_quantities_not_probabilities(self) -> None:
        """yes_bid_size_fp and yes_ask_size_fp are Decimal quantities."""
        market = KalshiMarket(
            ticker="T", event_ticker="E", title="Test",
            yes_bid_size=Decimal("10.00"),
            yes_ask_size=Decimal("25.00"),
        )
        assert market.yes_bid_size == Decimal("10.00")
        assert market.yes_ask_size == Decimal("25.00")

    def test_volume_and_open_interest_are_quantities(self) -> None:
        """volume_fp and open_interest_fp are Decimal quantities."""
        market = KalshiMarket(
            ticker="T", event_ticker="E", title="Test",
            volume=Decimal("100.00"),
            open_interest=Decimal("40.00"),
        )
        assert market.volume == Decimal("100.00")
        assert market.open_interest == Decimal("40.00")

    def test_decimal_precision_preserved(self) -> None:
        """Four decimal places are preserved."""
        market = KalshiMarket(
            ticker="T", event_ticker="E", title="Test",
            yes_bid=Decimal("0.1234"),
            yes_ask=Decimal("0.5678"),
        )
        assert market.spread == Decimal("0.4444")

    def test_midpoint(self) -> None:
        market = KalshiMarket(
            ticker="T", event_ticker="E", title="Test",
            yes_bid=Decimal("0.5600"),
            yes_ask=Decimal("0.5900"),
        )
        assert market.midpoint == Decimal("0.5750")


class TestKalshiMarketMinimal:
    def test_parse_minimal_market(self) -> None:
        market = KalshiMarket(ticker="TEST-01", event_ticker="EVT-01", title="Will X win?")
        assert market.ticker == "TEST-01"
        assert market.yes_bid is None

    def test_missing_optional_fields(self) -> None:
        market = KalshiMarket(ticker="T", event_ticker="E", title="Test", volume=None, open_interest=None)
        assert market.volume is None
        assert market.open_interest is None


# ---------------------------------------------------------------------------
# KalshiOrderBookSnapshot — Decimal-aware
# ---------------------------------------------------------------------------

class TestKalshiOrderBookSnapshot:
    def test_executable_price_yes(self) -> None:
        snap = KalshiOrderBookSnapshot(
            market_ticker="T",
            best_bid=Decimal("0.55"),
            best_ask=Decimal("0.58"),
            bid_depth=Decimal("100"),
            ask_depth=Decimal("80"),
        )
        assert snap.executable_price_yes() == Decimal("0.58")
        assert snap.executable_price_no() == Decimal("0.45")  # 1 - 0.55

    def test_executable_price_no_missing_bid(self) -> None:
        snap = KalshiOrderBookSnapshot(market_ticker="T", best_ask=Decimal("0.58"), ask_depth=Decimal("80"))
        assert snap.executable_price_no() is None

    def test_executable_price_yes_missing_ask(self) -> None:
        snap = KalshiOrderBookSnapshot(market_ticker="T", best_bid=Decimal("0.55"), bid_depth=Decimal("100"))
        assert snap.executable_price_yes() is None

    def test_missing_both_sides(self) -> None:
        snap = KalshiOrderBookSnapshot(market_ticker="T")
        assert snap.executable_price_yes() is None
        assert snap.executable_price_no() is None
        assert snap.spread is None
        assert snap.midpoint is None

    def test_derived_fields_computed(self) -> None:
        snap = KalshiOrderBookSnapshot(market_ticker="T", best_bid=Decimal("0.50"), best_ask=Decimal("0.60"))
        assert snap.spread == Decimal("0.10")
        assert snap.midpoint == Decimal("0.55")

    def test_executable_price_for_side(self) -> None:
        snap = KalshiOrderBookSnapshot(market_ticker="T", best_bid=Decimal("0.55"), best_ask=Decimal("0.58"))
        assert snap.executable_price_for_side(MarketSide.YES) == Decimal("0.58")
        assert snap.executable_price_for_side(MarketSide.NO) == Decimal("0.45")


class TestPaperTradeDecision:
    def test_valid_decision(self) -> None:
        from prediction_bot.data.schema import DecisionStatus
        decision = PaperTradeDecision(
            match_id="m1", market_ticker="TICKER", side=MarketSide.YES, entry_price=0.58,
            quantity=10, notional=5.8, decision=DecisionStatus.APPROVE,
            p_model=0.65, p_conservative=0.62, raw_edge=0.04, net_edge=0.02,
        )
        assert decision.quantity == 10

    def test_entry_price_must_be_positive(self) -> None:
        from prediction_bot.data.schema import DecisionStatus
        with pytest.raises(ValidationError):
            PaperTradeDecision(
                match_id="m1", market_ticker="T", side=MarketSide.YES, entry_price=0,
                quantity=1, notional=0, decision=DecisionStatus.APPROVE,
                p_model=0.5, p_conservative=0.5, raw_edge=0.0, net_edge=0.0,
            )

    def test_quantity_must_be_positive(self) -> None:
        from prediction_bot.data.schema import DecisionStatus
        with pytest.raises(ValidationError):
            PaperTradeDecision(
                match_id="m1", market_ticker="T", side=MarketSide.YES, entry_price=0.5,
                quantity=0, notional=0, decision=DecisionStatus.APPROVE,
                p_model=0.5, p_conservative=0.5, raw_edge=0.0, net_edge=0.0,
            )


class TestFeasibilityReport:
    def test_empty_report(self) -> None:
        report = FeasibilityReport()
        assert report.total_markets == 0
        assert report.gap_counts == {}

    def test_report_with_data(self) -> None:
        entries = [
            EsportsMarketAuditEntry(
                title="T1 vs GenG", ticker="LOL-T1-01", event_ticker="LOL-01",
                estimated_game="league-of-legends", yes_bid=Decimal("0.56"),
                yes_ask=Decimal("0.59"), spread=Decimal("0.03"),
            ),
        ]
        report = FeasibilityReport(
            total_markets=100, total_esports_markets=1,
            markets_by_game={"league-of-legends": 1},
            gap_counts={"unclassified_game": 0},
            raw_entries=entries,
        )
        assert report.total_esports_markets == 1

    def test_metadata_gap_enum(self) -> None:
        assert MetadataGap.UNCLASSIFIED_GAME.value == "unclassified_game"
        assert MetadataGap.MISSING_BID.value == "missing_bid"
        assert MetadataGap.MISSING_ASK.value == "missing_ask"
        assert MetadataGap.ZERO_VOLUME.value == "zero_volume"
        assert MetadataGap.ZERO_OPEN_INTEREST.value == "zero_open_interest"


class TestEnums:
    def test_tournament_tiers(self) -> None:
        assert TournamentTier.S.value == "S"
        assert TournamentTier.A.value == "A"

    def test_match_format(self) -> None:
        assert MatchFormat.BO1.value == "BO1"
        assert MatchFormat.BO5.value == "BO5"

    def test_player_role(self) -> None:
        assert PlayerRole.TOP.value == "top"
        assert PlayerRole.MID.value == "mid"

    def test_market_side(self) -> None:
        assert MarketSide.YES.value == "yes"
        assert MarketSide.NO.value == "no"

    def test_match_confidence(self) -> None:
        assert MatchConfidence.HIGH.value == "HIGH"
        assert MatchConfidence.NONE.value == "NONE"
