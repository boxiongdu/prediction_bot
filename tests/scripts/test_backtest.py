"""Tests for Phase 2 backtesting pipeline.

Verifies: settlement-stripping, packet generation, prediction storage
without outcome contamination, and outcome revelation + evaluation.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from prediction_bot.agents.evaluation import EvaluationReport
from prediction_bot.agents.schema import (
    ContractType,
    Sport,
    normalize_contract,
)
from prediction_bot.scripts.backtest import (
    _strip_settlement,
    build_prediction_packets,
    settle_and_evaluate,
    store_predictions,
)
from prediction_bot.storage import PredictionStore

# ── Fixtures: realistic settled esports markets ──

_SETTLED_LOL_MATCH = {
    "ticker": "KXLOLGAME-26JUL301330BWSU-SU",
    "event_ticker": "KXLOLGAME-26JUL301330BWSU",
    "title": "Will SU Esports win the Bushido Wildcats vs. SU Esports League of Legends match?",
    "yes_sub_title": "SU Esports",
    "no_sub_title": "SU Esports",
    "rules_primary": (
        "If SU Esports wins the TCL 2026: Bushido Wildcats vs. SU Esports "
        "League of Legends match originally scheduled for Jul 30, 2026 at "
        "1:30 PM EDT, then the market resolves to Yes."
    ),
    "result": "yes",                    # <-- settlement: YES side won
    "settlement_value_dollars": "1.0000",
    "settlement_ts": "2026-07-31T00:00:00Z",
    "settlement_timer_seconds": 30,
    "close_time": "2026-08-01T17:30:00Z",
    "status": "finalized",
}

_SETTLED_CS2_MATCH = {
    "ticker": "KXCS2GAME-26JUL281430OLDFOR-OLD",
    "event_ticker": "KXCS2GAME-26JUL281430OLDFOR",
    "title": "Will OLDBOYS- win the OLDBOYS- vs. Fortress CS2 match?",
    "yes_sub_title": "OLDBOYS-",
    "no_sub_title": "OLDBOYS-",
    "rules_primary": (
        "If OLDBOYS- wins the ESEA Advanced Europe 2026: OLDBOYS- vs. "
        "Fortress CS2 match, then the market resolves to Yes."
    ),
    "result": "no",                     # <-- settlement: NO (Fortress won)
    "settlement_value_dollars": "0.0000",
    "settlement_ts": "2026-07-31T00:00:00Z",
    "settlement_timer_seconds": 30,
    "close_time": "2026-07-30T18:30:00Z",
    "status": "finalized",
}

_SETTLED_VALORANT_MATCH = {
    "ticker": "KXVALORANTGAME-26JUL282100BBB2GAME-BBB",
    "event_ticker": "KXVALORANTGAME-26JUL282100BBB2GAME",
    "title": "Will Contra win the Contra vs. 2GAME Esports Valorant match?",
    "yes_sub_title": "Contra",
    "no_sub_title": "Contra",
    "rules_primary": (
        "If Contra wins the VCL Americas: Contra vs. 2GAME Esports "
        "Valorant match, then the market resolves to Yes."
    ),
    "result": "no",
    "settlement_value_dollars": "0.0000",
    "settlement_ts": "2026-07-31T00:00:00Z",
    "close_time": "2026-07-31T01:00:00Z",
    "status": "finalized",
}


class TestStripSettlement:
    """Settlement fields are scrubbed before prediction packets."""

    def test_removes_result(self) -> None:
        clean = _strip_settlement(_SETTLED_LOL_MATCH)
        assert "result" not in clean

    def test_removes_settlement_value(self) -> None:
        clean = _strip_settlement(_SETTLED_LOL_MATCH)
        assert "settlement_value_dollars" not in clean

    def test_removes_settlement_ts(self) -> None:
        clean = _strip_settlement(_SETTLED_LOL_MATCH)
        assert "settlement_ts" not in clean

    def test_removes_yes_sub_title(self) -> None:
        clean = _strip_settlement(_SETTLED_LOL_MATCH)
        assert "yes_sub_title" not in clean

    def test_removes_no_sub_title(self) -> None:
        clean = _strip_settlement(_SETTLED_LOL_MATCH)
        assert "no_sub_title" not in clean

    def test_preserves_ticker(self) -> None:
        clean = _strip_settlement(_SETTLED_LOL_MATCH)
        assert clean["ticker"] == "KXLOLGAME-26JUL301330BWSU-SU"

    def test_preserves_rules_primary(self) -> None:
        clean = _strip_settlement(_SETTLED_LOL_MATCH)
        assert "rules_primary" in clean

    def test_does_not_mutate_original(self) -> None:
        original = dict(_SETTLED_LOL_MATCH)
        _strip_settlement(original)
        assert "result" in original  # original unchanged


class TestBuildPredictionPackets:
    """Packets contain no settlement info and have required fields."""

    def test_packet_has_no_settlement_leak(self) -> None:
        """Research prompt does not contain settlement outcomes."""
        with tempfile.TemporaryDirectory() as tmp:
            packets = build_prediction_packets(
                [_SETTLED_LOL_MATCH], output_dir=Path(tmp),
            )
            assert len(packets) == 1
            pkt = packets[0]
            # Check the prompt text doesn't contain settlement-indicating words
            prompt = pkt.get("research_prompt", "")
            assert "settlement_value" not in prompt.lower()
            assert "settlement_ts" not in prompt.lower()
            assert "result: yes" not in prompt.lower()
            assert "result: no" not in prompt.lower()
            # The packet dict itself has no raw settlement fields
            assert "result" not in pkt  # top-level key
            assert "settlement_value_dollars" not in pkt

    def test_packet_includes_game(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            packets = build_prediction_packets(
                [_SETTLED_LOL_MATCH], output_dir=Path(tmp),
            )
            assert packets[0]["game"] == "league-of-legends"

    def test_packet_includes_participants(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            packets = build_prediction_packets(
                [_SETTLED_LOL_MATCH], output_dir=Path(tmp),
            )
            assert "Bushido Wildcats" in packets[0]["participants"]
            assert "SU Esports" in packets[0]["participants"]

    def test_packet_includes_contract_type(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            packets = build_prediction_packets(
                [_SETTLED_LOL_MATCH], output_dir=Path(tmp),
            )
            assert packets[0]["contract_type"] == ContractType.MATCH_WINNER.value

    def test_packet_has_research_prompt(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            packets = build_prediction_packets(
                [_SETTLED_LOL_MATCH], output_dir=Path(tmp),
            )
            prompt = packets[0]["research_prompt"]
            assert "esports analyst" in prompt.lower()
            assert "Bushido Wildcats" in prompt

    def test_multiple_markets(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            packets = build_prediction_packets(
                [_SETTLED_LOL_MATCH, _SETTLED_CS2_MATCH],
                output_dir=Path(tmp),
            )
            assert len(packets) == 2
            games = {p["game"] for p in packets}
            assert "league-of-legends" in games
            assert "cs2" in games


class TestStorePredictionsWithoutOutcome:
    """Predictions are stored in the DB WITHOUT outcome data."""

    def test_stored_prediction_has_no_outcome(self) -> None:
        store = PredictionStore()
        markets = [_SETTLED_LOL_MATCH]
        predictions = [{
            "event_id": "KXLOLGAME-26JUL301330BWSU",
            "predicted_winner": "SU Esports",
            "team_a_probability": 0.65,
            "team_b_probability": 0.35,
            "confidence": "medium",
            "abstain": False,
            "reasoning_summary": "SU Esports is stronger.",
        }]
        stored = store_predictions(markets, predictions)
        assert stored == 1

        # Verify: actual_result is NULL
        records = list(store.iter_all())
        assert len(records) >= 1
        # Find our record
        our = [r for r in records if r.event_id == "KXLOLGAME-26JUL301330BWSU"]
        assert len(our) >= 1
        assert our[0].actual_result is None
        assert our[0].correct_prediction is None


class TestSettleAndEvaluate:
    """Outcome revelation updates DB and produces calibration report."""

    def test_settle_updates_outcome(self) -> None:
        # First: store a prediction
        store = PredictionStore()
        markets = [_SETTLED_LOL_MATCH]
        predictions = [{
            "event_id": "KXLOLGAME-26JUL301330BWSU",
            "predicted_winner": "SU Esports",
            "team_a_probability": 0.65,
            "team_b_probability": 0.35,
            "confidence": "medium",
            "abstain": False,
            "reasoning_summary": "Test prediction.",
        }]
        store_predictions(markets, predictions)

        # Now settle
        settle_and_evaluate(markets)

        # Verify outcome was recorded
        records = list(store.iter_settled())
        our = [r for r in records if r.event_id == "KXLOLGAME-26JUL301330BWSU"]
        assert len(our) >= 1
        assert our[0].actual_result == "yes"
        # SU Esports = team_a, predicted SU Esports, result=yes → correct
        assert our[0].correct_prediction is True

    def test_incorrect_prediction_detected(self) -> None:
        store = PredictionStore()
        markets = [_SETTLED_CS2_MATCH]
        predictions = [{
            "event_id": "KXCS2GAME-26JUL281430OLDFOR",
            "predicted_winner": "OLDBOYS-",
            "team_a_probability": 0.60,
            "team_b_probability": 0.40,
            "confidence": "medium",
            "abstain": False,
            "reasoning_summary": "OLDBOYS- is favoured.",
        }]
        store_predictions(markets, predictions)

        settle_and_evaluate(markets)

        records = list(store.iter_settled())
        our = [r for r in records if r.event_id == "KXCS2GAME-26JUL281430OLDFOR"]
        assert len(our) >= 1
        assert our[0].actual_result == "no"
        # Predicted OLDBOYS- (=team_a), result=no → team_b won → incorrect
        assert our[0].correct_prediction is False

    def test_calibration_report_has_required_fields(self) -> None:
        PredictionStore()
        markets = [_SETTLED_LOL_MATCH, _SETTLED_CS2_MATCH, _SETTLED_VALORANT_MATCH]
        predictions = [
            {
                "event_id": "KXLOLGAME-26JUL301330BWSU",
                "predicted_winner": "SU Esports",
                "team_a_probability": 0.65, "team_b_probability": 0.35,
                "confidence": "medium", "abstain": False,
                "reasoning_summary": ".",
            },
            {
                "event_id": "KXCS2GAME-26JUL281430OLDFOR",
                "predicted_winner": "OLDBOYS-",
                "team_a_probability": 0.60, "team_b_probability": 0.40,
                "confidence": "medium", "abstain": False,
                "reasoning_summary": ".",
            },
            {
                "event_id": "KXVALORANTGAME-26JUL282100BBB2GAME",
                "predicted_winner": "Contra",
                "team_a_probability": 0.55, "team_b_probability": 0.45,
                "confidence": "low", "abstain": False,
                "reasoning_summary": ".",
            },
        ]
        store_predictions(markets, predictions)

        with tempfile.TemporaryDirectory() as tmp:
            report = settle_and_evaluate(markets, output_dir=Path(tmp))

        assert isinstance(report, EvaluationReport)
        assert report.total_settled >= 2
        assert report.brier_score is not None
        assert 0.0 <= report.overall_accuracy <= 1.0


class TestNormalizeFromSettled:
    """Settled markets normalize correctly even after stripping."""

    def test_settled_lol_normalizes(self) -> None:
        nc = normalize_contract(_SETTLED_LOL_MATCH)
        assert nc.contract_type == ContractType.MATCH_WINNER.value
        assert nc.sport == Sport.ESPORTS.value
        assert nc.game == "league-of-legends"
        assert nc.participants == ["Bushido Wildcats", "SU Esports"]

    def test_settled_cs2_normalizes(self) -> None:
        nc = normalize_contract(_SETTLED_CS2_MATCH)
        assert nc.contract_type == ContractType.MATCH_WINNER.value
        assert nc.sport == Sport.ESPORTS.value
        assert nc.game == "cs2"
