"""Tests for prediction agent schemas.

Covers: NormalizedContract, UnderlyingEvent, PredictionRequest, PredictionResponse,
parse_rules_primary, normalize_contract, build_event.

Uses five real Kalshi market examples as reference.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from prediction_bot.agents.schema import (
    ContractType,
    NormalizedContract,
    PredictionConfidence,
    PredictionRequest,
    PredictionResponse,
    Sport,
    UnderlyingEvent,
    build_event,
    normalize_contract,
    parse_rules_primary,
    parse_title,  # noqa: E402
)

# ---------------------------------------------------------------------------
# Five reference market examples
# ---------------------------------------------------------------------------


@pytest.fixture
def example_soccer_totals() -> dict:
    """Example 1: Soccer total goals market."""
    return {
        "ticker": "KXCLUBFTOTAL-26JUL28CFCWES-9",
        "event_ticker": "KXCLUBFTOTAL-26JUL28CFCWES",
        "title": "Will over 8.5 goals be scored?",
        "yes_sub_title": "Over 8.5 goals scored",
        "no_sub_title": "Over 8.5 goals scored",
        "rules_primary": (
            "If over 8.5 goals are scored in the Chelsea vs Western Sydney Wanderers "
            "professional Club Friendlies soccer game originally scheduled for "
            "Jul 28, 2026 after 90 minutes plus stoppage time "
            "(does not include extra time or penalties), then the market resolves to Yes."
        ),
        "close_time": "2026-07-30T15:45:00Z",
    }


@pytest.fixture
def example_lol_map2_mr() -> dict:
    """Example 2: LOL map 2 winner — Mental Rush side."""
    return {
        "ticker": "KXLOLMAP-26JUL281430AZREMR-2-MR",
        "event_ticker": "KXLOLMAP-26JUL281430AZREMR-2",
        "title": "Will Mental Rush win map 2 in the AZ Rising Eterna vs. Mental Rush match?",
        "yes_sub_title": "Mental Rush",
        "no_sub_title": "Mental Rush",
        "rules_primary": (
            "If Mental Rush wins map 2 in the Equal eSports Cup 2026: "
            "AZ Rising Eterna vs. Mental Rush League of Legends match "
            "originally scheduled for Jul 28, 2026 at 2:30 PM EDT, "
            "then the market resolves to Yes."
        ),
        "close_time": "2026-07-30T18:30:00Z",
    }


@pytest.fixture
def example_lol_map2_azre() -> dict:
    """Example 3: LOL map 2 winner — AZ Rising Eterna side."""
    return {
        "ticker": "KXLOLMAP-26JUL281430AZREMR-2-AZRE",
        "event_ticker": "KXLOLMAP-26JUL281430AZREMR-2",
        "title": "Will AZ Rising Eterna win map 2 in the AZ Rising Eterna vs. Mental Rush match?",
        "yes_sub_title": "AZ Rising Eterna",
        "no_sub_title": "AZ Rising Eterna",
        "rules_primary": (
            "If AZ Rising Eterna wins map 2 in the Equal eSports Cup 2026: "
            "AZ Rising Eterna vs. Mental Rush League of Legends match "
            "originally scheduled for Jul 28, 2026 at 2:30 PM EDT, "
            "then the market resolves to Yes."
        ),
        "close_time": "2026-07-30T18:30:00Z",
    }


@pytest.fixture
def example_lol_map1_mr() -> dict:
    """Example 4: LOL map 1 winner — Mental Rush side."""
    return {
        "ticker": "KXLOLMAP-26JUL281430AZREMR-1-MR",
        "event_ticker": "KXLOLMAP-26JUL281430AZREMR-1",
        "title": "Will Mental Rush win map 1 in the AZ Rising Eterna vs. Mental Rush match?",
        "yes_sub_title": "Mental Rush",
        "no_sub_title": "Mental Rush",
        "rules_primary": (
            "If Mental Rush wins map 1 in the Equal eSports Cup 2026: "
            "AZ Rising Eterna vs. Mental Rush League of Legends match "
            "originally scheduled for Jul 28, 2026 at 2:30 PM EDT, "
            "then the market resolves to Yes."
        ),
        "close_time": "2026-07-30T18:30:00Z",
    }


@pytest.fixture
def example_lol_map1_azre() -> dict:
    """Example 5: LOL map 1 winner — AZ Rising Eterna side."""
    return {
        "ticker": "KXLOLMAP-26JUL281430AZREMR-1-AZRE",
        "event_ticker": "KXLOLMAP-26JUL281430AZREMR-1",
        "title": "Will AZ Rising Eterna win map 1 in the AZ Rising Eterna vs. Mental Rush match?",
        "yes_sub_title": "AZ Rising Eterna",
        "no_sub_title": "AZ Rising Eterna",
        "rules_primary": (
            "If AZ Rising Eterna wins map 1 in the Equal eSports Cup 2026: "
            "AZ Rising Eterna vs. Mental Rush League of Legends match "
            "originally scheduled for Jul 28, 2026 at 2:30 PM EDT, "
            "then the market resolves to Yes."
        ),
        "close_time": "2026-07-30T18:30:00Z",
    }


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class TestEnums:
    def test_prediction_confidence(self) -> None:
        assert PredictionConfidence.LOW.value == "low"
        assert PredictionConfidence.MEDIUM.value == "medium"
        assert PredictionConfidence.HIGH.value == "high"

    def test_contract_type(self) -> None:
        assert ContractType.MAP_WINNER.value == "map_winner"
        assert ContractType.MATCH_WINNER.value == "match_winner"
        assert ContractType.TOTAL_GOALS.value == "total_goals"
        assert ContractType.OTHER.value == "other"

    def test_sport(self) -> None:
        assert Sport.ESPORTS.value == "esports"
        assert Sport.SOCCER.value == "soccer"


# ---------------------------------------------------------------------------
# parse_rules_primary — unit tests
# ---------------------------------------------------------------------------


class TestParseRulesPrimary:
    def test_empty_string(self) -> None:
        result = parse_rules_primary("")
        assert result["yes_outcome"] is None
        assert result["sport"] is None

    def test_none(self) -> None:
        result = parse_rules_primary(None)  # type: ignore[arg-type]
        assert result["yes_outcome"] is None

    def test_lol_map_winner(self, example_lol_map2_mr: dict) -> None:
        result = parse_rules_primary(example_lol_map2_mr["rules_primary"])
        assert result["yes_outcome"] == "Mental Rush wins map 2"
        assert result["sport"] == "esports"
        assert result["game"] == "league-of-legends"
        assert result["tournament"] == "Equal eSports Cup 2026"
        assert result["participants"] == ["AZ Rising Eterna", "Mental Rush"]
        assert result["map_number"] == 2
        assert result["contract_type"] == "map_winner"

    def test_soccer_totals(self, example_soccer_totals: dict) -> None:
        result = parse_rules_primary(example_soccer_totals["rules_primary"])
        assert result["sport"] == "soccer"
        assert result["game"] is None  # not esports
        assert result["tournament"] == "Club Friendlies"
        assert result["participants"] == ["Chelsea", "Western Sydney Wanderers"]
        assert result["contract_type"] == "total_goals"
        assert result["threshold"] == 8.5

    def test_map_number_extraction(self) -> None:
        result = parse_rules_primary(
            "If T1 wins map 3 in the LCK 2025: T1 vs Gen.G "
            "League of Legends match, then the market resolves to Yes."
        )
        assert result["map_number"] == 3
        assert result["contract_type"] == "map_winner"

    def test_match_winner_classification(self) -> None:
        result = parse_rules_primary(
            "If T1 wins the match in the LCK 2025: T1 vs Gen.G "
            "League of Legends match, then the market resolves to Yes."
        )
        assert result["contract_type"] == "match_winner"

    def test_no_map_number_for_match_winner(self) -> None:
        result = parse_rules_primary(
            "If T1 wins the match in the LCK 2025: T1 vs Gen.G "
            "League of Legends match, then the market resolves to Yes."
        )
        assert result["map_number"] is None


# ---------------------------------------------------------------------------
# normalize_contract — integration tests
# ---------------------------------------------------------------------------


class TestNormalizeContract:
    def test_soccer_contract(self, example_soccer_totals: dict) -> None:
        c = normalize_contract(example_soccer_totals)
        assert c.ticker == "KXCLUBFTOTAL-26JUL28CFCWES-9"
        assert c.contract_type == ContractType.TOTAL_GOALS.value
        assert c.sport == Sport.SOCCER.value
        assert c.game is None
        assert c.tournament == "Club Friendlies"
        assert c.participants == ["Chelsea", "Western Sydney Wanderers"]
        assert c.threshold == 8.5

    def test_lol_map_winner_mr(self, example_lol_map2_mr: dict) -> None:
        c = normalize_contract(example_lol_map2_mr)
        assert c.contract_type == ContractType.MAP_WINNER.value
        assert c.sport == Sport.ESPORTS.value
        assert c.game == "league-of-legends"
        assert c.tournament == "Equal eSports Cup 2026"
        assert c.participants == ["AZ Rising Eterna", "Mental Rush"]
        assert c.map_number == 2
        assert "Mental Rush" in (c.yes_outcome or "")

    def test_lol_map_winner_azre(self, example_lol_map2_azre: dict) -> None:
        c = normalize_contract(example_lol_map2_azre)
        assert c.contract_type == ContractType.MAP_WINNER.value
        assert c.participants == ["AZ Rising Eterna", "Mental Rush"]
        assert "AZ Rising Eterna" in (c.yes_outcome or "")

    def test_lol_map1_mr(self, example_lol_map1_mr: dict) -> None:
        c = normalize_contract(example_lol_map1_mr)
        assert c.map_number == 1
        assert c.participants == ["AZ Rising Eterna", "Mental Rush"]

    def test_lol_map1_azre(self, example_lol_map1_azre: dict) -> None:
        c = normalize_contract(example_lol_map1_azre)
        assert c.map_number == 1
        assert c.participants == ["AZ Rising Eterna", "Mental Rush"]


# ---------------------------------------------------------------------------
# build_event
# ---------------------------------------------------------------------------


class TestBuildEvent:
    def test_build_from_lol_contracts(
        self,
        example_lol_map1_mr: dict,
        example_lol_map1_azre: dict,
        example_lol_map2_mr: dict,
        example_lol_map2_azre: dict,
    ) -> None:
        # Kalshi creates separate event_tickers per map.
        # Map 1 contracts share event_ticker; Map 2 contracts share a different one.
        map1_contracts = [
            normalize_contract(example_lol_map1_mr),
            normalize_contract(example_lol_map1_azre),
        ]
        event1 = build_event(map1_contracts)
        assert event1 is not None
        assert event1.event_id == "KXLOLMAP-26JUL281430AZREMR-1"
        assert event1.participants == ["AZ Rising Eterna", "Mental Rush"]
        assert "map_winner" in event1.contract_types

        map2_contracts = [
            normalize_contract(example_lol_map2_mr),
            normalize_contract(example_lol_map2_azre),
        ]
        event2 = build_event(map2_contracts)
        assert event2 is not None
        assert event2.event_id == "KXLOLMAP-26JUL281430AZREMR-2"
        assert event2.participants == ["AZ Rising Eterna", "Mental Rush"]
        assert "map_winner" in event2.contract_types

    def test_build_from_single_contract(self, example_soccer_totals: dict) -> None:
        c = normalize_contract(example_soccer_totals)
        event = build_event([c])
        assert event is not None
        assert event.participants == ["Chelsea", "Western Sydney Wanderers"]

    def test_build_empty_contracts(self) -> None:
        assert build_event([]) is None

    def test_conflicting_event_tickers(self) -> None:
        c1 = normalize_contract({
            "ticker": "A-1", "event_ticker": "EVT-A",
            "title": "test", "rules_primary": "If X wins, then resolves to Yes.",
        })
        c2 = normalize_contract({
            "ticker": "B-1", "event_ticker": "EVT-B",
            "title": "test", "rules_primary": "If Y wins, then resolves to Yes.",
        })
        with pytest.raises(ValueError, match="same event_ticker"):
            build_event([c1, c2])

    def test_team_a_team_b_properties(self) -> None:
        event = UnderlyingEvent(
            event_id="e",
            participants=["T1", "Gen.G"],
        )
        assert event.team_a == "T1"
        assert event.team_b == "Gen.G"

    def test_empty_participants(self) -> None:
        with pytest.raises(ValidationError):
            UnderlyingEvent(event_id="e", participants=["  ", ""])

    def test_single_participant(self) -> None:
        event = UnderlyingEvent(event_id="e", participants=["Solo Team"])
        assert event.team_a == "Solo Team"
        assert event.team_b == ""


# ---------------------------------------------------------------------------
# NormalizedContract — direct construction
# ---------------------------------------------------------------------------


class TestNormalizedContractDirect:
    def test_minimal(self) -> None:
        c = NormalizedContract(ticker="T", event_ticker="E")
        assert c.ticker == "T"
        assert c.contract_type == ContractType.OTHER.value

    def test_with_all_fields(self) -> None:
        c = NormalizedContract(
            ticker="T",
            event_ticker="E",
            contract_type=ContractType.MAP_WINNER.value,
            sport=Sport.ESPORTS.value,
            game="league-of-legends",
            yes_outcome="T1 wins map 1",
            tournament="LCK",
            participants=["T1", "Gen.G"],
            map_number=1,
        )
        assert c.map_number == 1
        assert c.participants == ["T1", "Gen.G"]


# ---------------------------------------------------------------------------
# PredictionRequest (new interface)
# ---------------------------------------------------------------------------


class TestPredictionRequest:
    def test_from_event(self) -> None:
        event = UnderlyingEvent(
            event_id="evt-1",
            game="league-of-legends",
            tournament="LCK Spring 2025",
            participants=["T1", "Gen.G"],
            contract_types=["map_winner", "match_winner"],
        )
        req = PredictionRequest(
            event_id=event.event_id,
            game=event.game,
            tournament=event.tournament,
            participants=event.participants,
            contract_types=event.contract_types,
        )
        assert req.team_a == "T1"
        assert req.team_b == "Gen.G"
        assert "map_winner" in req.contract_types

    def test_to_research_prompt(self) -> None:
        req = PredictionRequest(
            event_id="evt-1",
            game="league-of-legends",
            tournament="LCK Spring 2025",
            participants=["T1", "Gen.G"],
            contract_types=["match_winner"],
            start_time=datetime(2025, 1, 15, 8, 0, tzinfo=timezone.utc),
        )
        prompt = req.to_research_prompt()
        assert "T1" in prompt
        assert "Gen.G" in prompt
        assert "LCK Spring 2025" in prompt
        assert "esports analyst" in prompt.lower()


# ---------------------------------------------------------------------------
# PredictionResponse (unchanged core)
# ---------------------------------------------------------------------------


class TestPredictionResponseValid:
    def test_valid_prediction(self) -> None:
        resp = PredictionResponse(
            event_id="evt-1",
            predicted_winner="T1",
            team_a_probability=0.62,
            team_b_probability=0.38,
            confidence=PredictionConfidence.MEDIUM,
            reasoning_summary="T1 stronger.",
            key_factors=["roster"],
            risk_flags=["patch"],
        )
        assert resp.team_a_probability == 0.62
        assert resp.abstain is False

    def test_valid_abstain(self) -> None:
        resp = PredictionResponse(
            event_id="evt-1",
            predicted_winner="abstain",
            team_a_probability=0.5,
            team_b_probability=0.5,
            confidence=PredictionConfidence.LOW,
            abstain=True,
            reasoning_summary="No info.",
        )
        assert resp.abstain is True


class TestPredictionResponseInvalid:
    def test_probabilities_dont_sum(self) -> None:
        with pytest.raises(ValidationError, match="sum to approximately 1.0"):
            PredictionResponse(
                event_id="e", predicted_winner="T1",
                team_a_probability=0.6, team_b_probability=0.5,
                confidence="medium", reasoning_summary="...",
            )

    def test_probability_out_of_range(self) -> None:
        with pytest.raises(ValidationError):
            PredictionResponse(
                event_id="e", predicted_winner="T1",
                team_a_probability=1.5, team_b_probability=-0.5,
                confidence="medium", reasoning_summary="...",
            )

    def test_abstain_not_5050(self) -> None:
        with pytest.raises(ValidationError):
            PredictionResponse(
                event_id="e", predicted_winner="abstain",
                team_a_probability=0.6, team_b_probability=0.4,
                confidence="low", abstain=True, reasoning_summary="...",
            )

    def test_abstain_wrong_winner(self) -> None:
        with pytest.raises(ValidationError):
            PredictionResponse(
                event_id="e", predicted_winner="T1",
                team_a_probability=0.5, team_b_probability=0.5,
                confidence="low", abstain=True, reasoning_summary="...",
            )

    def test_not_abstain_winner_is_abstain(self) -> None:
        with pytest.raises(ValidationError):
            PredictionResponse(
                event_id="e", predicted_winner="abstain",
                team_a_probability=0.6, team_b_probability=0.4,
                confidence="medium", abstain=False, reasoning_summary="...",
            )


# ---------------------------------------------------------------------------
# Title parser — unit tests
# ---------------------------------------------------------------------------


class TestParseTitle:
    """parse_title() extracts contract_type, map_number, participants from titles."""

    def test_empty(self) -> None:
        result = parse_title("")
        assert result["contract_type"] is None
        assert result["map_number"] is None
        assert result["participants"] is None

    def test_map_winner_su_esports(self) -> None:
        """Will SU Esports win map 2 in the Bushido Wildcats vs. SU Esports match?"""
        result = parse_title(
            "Will SU Esports win map 2 in the Bushido Wildcats vs. SU Esports match?"
        )
        assert result["contract_type"] == "map_winner"
        assert result["map_number"] == 2
        assert result["participants"] == ["Bushido Wildcats", "SU Esports"]

    def test_map_winner_bushido_wildcats(self) -> None:
        """Will Bushido Wildcats win map 2 in the Bushido Wildcats vs. SU Esports match?"""
        result = parse_title(
            "Will Bushido Wildcats win map 2 in the Bushido Wildcats vs. SU Esports match?"
        )
        assert result["contract_type"] == "map_winner"
        assert result["map_number"] == 2
        assert result["participants"] == ["Bushido Wildcats", "SU Esports"]

    def test_map_winner_team_we(self) -> None:
        """Will Team WE win map 1 in the Bilibili Gaming vs. Team WE match?"""
        result = parse_title(
            "Will Team WE win map 1 in the Bilibili Gaming vs. Team WE match?"
        )
        assert result["contract_type"] == "map_winner"
        assert result["map_number"] == 1
        assert result["participants"] == ["Bilibili Gaming", "Team WE"]

    def test_map_winner_bilibili(self) -> None:
        """Will Bilibili Gaming win map 2 in the Bilibili Gaming vs. Team WE match?"""
        result = parse_title(
            "Will Bilibili Gaming win map 2 in the Bilibili Gaming vs. Team WE match?"
        )
        assert result["contract_type"] == "map_winner"
        assert result["map_number"] == 2
        assert result["participants"] == ["Bilibili Gaming", "Team WE"]

    def test_map_winner_no_period_after_vs(self) -> None:
        """vs without period: Will Contra win map 1 in the Contra vs 2GAME match?"""
        result = parse_title(
            "Will Contra win map 1 in the Contra vs 2GAME Esports match?"
        )
        assert result["contract_type"] == "map_winner"
        assert result["map_number"] == 1
        assert result["participants"] == ["Contra", "2GAME Esports"]

    def test_map_winner_dota2(self) -> None:
        """Will Team Resilience win map 2 in the PlayTime vs. Team Resilience match?"""
        result = parse_title(
            "Will Team Resilience win map 2 in the PlayTime vs. Team Resilience match?"
        )
        assert result["contract_type"] == "map_winner"
        assert result["map_number"] == 2
        assert result["participants"] == ["PlayTime", "Team Resilience"]

    def test_set_winner_tennis(self) -> None:
        """Will Soonwoo Kwon win set 2 in the Soonwoo Kwon vs Arthur Gea match"""
        result = parse_title(
            "Will Soonwoo Kwon win set 2 in the Soonwoo Kwon vs Arthur Gea match"
        )
        assert result["contract_type"] == "set_winner"
        assert result["map_number"] == 2
        assert result["participants"] == ["Soonwoo Kwon", "Arthur Gea"]

    def test_match_winner_esports(self) -> None:
        """Will SU Esports win the Bushido Wildcats vs. SU Esports League of Legends match?"""
        result = parse_title(
            "Will SU Esports win the Bushido Wildcats vs. SU Esports League of Legends match?"
        )
        assert result["contract_type"] == "match_winner"
        assert result["participants"] == ["Bushido Wildcats", "SU Esports"]

    def test_match_winner_tennis_colon(self) -> None:
        """Will Jay Friend win the Friend vs Church: Qualifying match?"""
        result = parse_title(
            "Will Jay Friend win the Friend vs Church: Qualifying match?"
        )
        assert result["contract_type"] == "match_winner"
        assert result["participants"] == ["Friend", "Church"]

    def test_return_none_for_unknown_title(self) -> None:
        """Unknown title patterns return None for all fields."""
        result = parse_title("Some completely unrecognizable title text")
        assert result["contract_type"] is None
        assert result["map_number"] is None
        assert result["participants"] is None


# ---------------------------------------------------------------------------
# Title fallback in normalize_contract — integration tests
# ---------------------------------------------------------------------------


class TestNormalizeContractTitleFallback:
    """normalize_contract() uses title as fallback when rules_primary is sparse."""

    def test_map_winner_from_title_only(self) -> None:
        """Empty rules_primary — contract_type + game come from ticker,
        participants from title."""
        from prediction_bot.agents.schema import normalize_contract

        c = normalize_contract({
            "ticker": "KXLOLMAP-01",
            "event_ticker": "KXLOLMAP-01-2",
            "title": "Will SU Esports win map 2 in the Bushido Wildcats vs. SU Esports match?",
            "rules_primary": "",
        })
        assert c.contract_type == "map_winner"
        assert c.map_number == 2
        assert c.participants == ["Bushido Wildcats", "SU Esports"]
        # Ticker prefix provides game/sport even without rules_primary
        assert c.game == "league-of-legends"
        assert c.sport == "esports"

    def test_rules_primary_wins_over_title(self) -> None:
        """rules_primary is authoritative; title only fills gaps."""
        from prediction_bot.agents.schema import normalize_contract

        c = normalize_contract({
            "ticker": "KXLOLMAP-01",
            "event_ticker": "KXLOLMAP-01-2",
            "title": "Will BAD TEAM win map 99?",
            "rules_primary": (
                "If SU Esports wins map 2 in the TCL 2026: Bushido Wildcats vs. SU Esports "
                "League of Legends match originally scheduled for Jul 30, 2026 at 1:30 PM EDT, "
                "then the market resolves to Yes."
            ),
        })
        # rules_primary values win, not the bad title data
        assert c.contract_type == "map_winner"
        assert c.map_number == 2  # from rules_primary, not 99
        assert c.participants == ["Bushido Wildcats", "SU Esports"]

    def test_contract_type_known_game_unknown(self) -> None:
        """Key principle: contract can be classified; game comes from ticker.
        When ticker prefix is unrecognised, game remains None — which is fine."""
        from prediction_bot.agents.schema import normalize_contract

        # Use an unknown ticker prefix so game is not provided by ticker
        c = normalize_contract({
            "ticker": "KXUNKNOWN-01",
            "event_ticker": "KXUNKNOWN-01-1",
            "title": "Will Team WE win map 1 in the Bilibili Gaming vs. Team WE match?",
            "rules_primary": "",
        })
        assert c.contract_type == "map_winner"
        assert c.map_number == 1
        assert c.game is None  # unknown ticker, but contract_type is still correct
        assert c.sport is None  # unknown ticker, but contract_type is still correct
