"""Tests for prediction evaluation."""

from __future__ import annotations

from prediction_bot.agents.evaluation import (
    CalibrationBin,
    ConfidenceBreakdown,
    EvaluationReport,
    evaluate_predictions,
    format_evaluation_report,
)
from prediction_bot.storage import PredictionRecord

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_record(
    event_id: str = "evt-1",
    team_a: str = "T1",
    team_b: str = "Gen.G",
    predicted_winner: str = "T1",
    prob_a: float = 0.62,
    confidence: str = "medium",
    actual_result: str | None = "T1",
    correct: bool | None = True,
    abstain: bool = False,
) -> PredictionRecord:
    return PredictionRecord(
        id=abs(hash(event_id)) % 10000,
        event_id=event_id,
        team_a=team_a,
        team_b=team_b,
        predicted_winner=predicted_winner,
        team_a_probability=prob_a,
        team_b_probability=1.0 - prob_a,
        confidence=confidence,
        abstain=abstain,
        reasoning_summary="...",
        actual_result=actual_result,
        correct_prediction=correct,
    )


# ---------------------------------------------------------------------------
# ConfidenceBreakdown
# ---------------------------------------------------------------------------

class TestConfidenceBreakdown:
    def test_empty(self) -> None:
        cb = ConfidenceBreakdown(confidence="high")
        cb.compute()
        assert cb.accuracy == 0.0

    def test_all_correct(self) -> None:
        cb = ConfidenceBreakdown(confidence="high", total=10, correct=10)
        cb.compute()
        assert cb.accuracy == 1.0

    def test_half_correct(self) -> None:
        cb = ConfidenceBreakdown(confidence="medium", total=4, correct=2)
        cb.compute()
        assert cb.accuracy == 0.5


# ---------------------------------------------------------------------------
# CalibrationBin
# ---------------------------------------------------------------------------

class TestCalibrationBin:
    def test_empty(self) -> None:
        cb = CalibrationBin(bin_label="0.5–0.6", bin_low=0.5, bin_high=0.6)
        cb.compute()
        assert cb.observed_rate == 0.0

    def test_perfect_calibration(self) -> None:
        cb = CalibrationBin(
            bin_label="0.6–0.7", bin_low=0.6, bin_high=0.7,
            count=10, correct=6, expected_correct=6.5,
        )
        cb.compute()
        assert cb.observed_rate == 0.6


# ---------------------------------------------------------------------------
# EvaluationReport
# ---------------------------------------------------------------------------

class TestEvaluationReport:
    def test_empty(self) -> None:
        report = EvaluationReport()
        report.compute_derived()
        assert report.overall_accuracy == 0.0

    def test_compute_derived(self) -> None:
        report = EvaluationReport(
            total_settled=10,
            total_correct=8,
        )
        report.compute_derived()
        assert report.overall_accuracy == 0.8


# ---------------------------------------------------------------------------
# evaluate_predictions
# ---------------------------------------------------------------------------


class TestEvaluatePredictions:
    def test_no_records(self) -> None:
        report = evaluate_predictions([])
        assert report.total_predictions == 0
        assert report.overall_accuracy == 0.0

    def test_only_abstentions(self) -> None:
        records = [
            _make_record(abstain=True, actual_result=None, correct=None),
            _make_record(event_id="evt-2", abstain=True, actual_result=None, correct=None),
        ]
        report = evaluate_predictions(records)
        assert report.total_abstentions == 2
        assert report.total_settled == 0

    def test_all_correct(self) -> None:
        records = [_make_record(event_id=f"evt-{i}") for i in range(5)]
        report = evaluate_predictions(records)
        assert report.total_settled == 5
        assert report.total_correct == 5
        assert report.overall_accuracy == 1.0
        # Brier score: each prediction is 62%, all correct → (0.62 - 1)^2 = 0.1444
        assert report.brier_score == pytest.approx(0.1444, abs=0.001)

    def test_all_wrong(self) -> None:
        records = [
            _make_record(
                event_id=f"evt-{i}",
                predicted_winner="T1",
                actual_result="Gen.G",
                correct=False,
            )
            for i in range(5)
        ]
        report = evaluate_predictions(records)
        assert report.overall_accuracy == 0.0
        # Brier: (0.62 - 0)^2 = 0.3844 each
        assert report.brier_score == pytest.approx(0.3844, abs=0.001)

    def test_mixed_accuracy(self) -> None:
        records = [
            _make_record(event_id="e1", predicted_winner="T1", actual_result="T1", correct=True),
            _make_record(event_id="e2", predicted_winner="T1", actual_result="Gen.G", correct=False),
        ]
        report = evaluate_predictions(records)
        assert report.overall_accuracy == 0.5

    def test_confidence_breakdown(self) -> None:
        records = [
            _make_record(event_id="e1", confidence="high", correct=True),
            _make_record(event_id="e2", confidence="high", correct=True),
            _make_record(event_id="e3", confidence="high", correct=False),
            _make_record(event_id="e4", confidence="medium", correct=True),
            _make_record(event_id="e5", confidence="medium", correct=False),
            _make_record(event_id="e6", confidence="low", correct=False),
        ]
        report = evaluate_predictions(records)

        # High: 3 total, 2 correct = 67%
        high = [cb for cb in report.confidence_breakdowns if cb.confidence == "high"]
        assert len(high) == 1
        assert high[0].total == 3
        assert high[0].correct == 2
        assert high[0].accuracy == pytest.approx(2 / 3)

        # Medium: 2 total, 1 correct = 50%
        med = [cb for cb in report.confidence_breakdowns if cb.confidence == "medium"]
        assert len(med) == 1
        assert med[0].total == 2
        assert med[0].correct == 1

        # Low: 1 total, 0 correct = 0%
        low = [cb for cb in report.confidence_breakdowns if cb.confidence == "low"]
        assert len(low) == 1
        assert low[0].total == 1
        assert low[0].correct == 0

    def test_calibration_bins(self) -> None:
        """Predictions at different probability levels should land in different bins."""
        records = [
            _make_record(event_id="e1", prob_a=0.95, correct=True),
            _make_record(event_id="e2", prob_a=0.85, correct=True),
            _make_record(event_id="e3", prob_a=0.75, correct=True),
            _make_record(event_id="e4", prob_a=0.65, correct=True),
            _make_record(event_id="e5", prob_a=0.55, correct=True),
        ]
        report = evaluate_predictions(records)
        assert len(report.calibration_bins) >= 5  # each goes to different bin

    def test_fair_coin_analysis(self) -> None:
        records = [
            _make_record(event_id="e1", prob_a=0.50, correct=True),
            _make_record(event_id="e2", prob_a=0.50, correct=False),
            _make_record(event_id="e3", prob_a=0.52, correct=True),
            _make_record(event_id="e4", prob_a=0.48, correct=False),
        ]
        report = evaluate_predictions(records)
        assert report.fair_coin_count == 4
        assert report.fair_coin_correct == 2
        assert report.fair_coin_accuracy == 0.5

    def test_brier_score_perfect(self) -> None:
        records = [
            _make_record(event_id=f"e{i}", prob_a=1.0, correct=True)
            for i in range(3)
        ]
        report = evaluate_predictions(records)
        assert report.brier_score == 0.0

    def test_brier_score_worst(self) -> None:
        records = [
            _make_record(event_id=f"e{i}", prob_a=1.0, correct=False)
            for i in range(3)
        ]
        report = evaluate_predictions(records)
        assert report.brier_score == 1.0

    def test_unsettled_ignored(self) -> None:
        records = [
            _make_record(event_id="e1", actual_result="T1", correct=True),
            _make_record(event_id="e2", actual_result=None, correct=None),
        ]
        report = evaluate_predictions(records)
        assert report.total_settled == 1

    def test_ignores_abstentions_in_accuracy(self) -> None:
        records = [
            _make_record(event_id="e1", correct=True),
            _make_record(event_id="e2", abstain=True, actual_result=None, correct=None),
        ]
        report = evaluate_predictions(records)
        assert report.total_settled == 1
        assert report.total_abstentions == 1
        assert report.overall_accuracy == 1.0


# ---------------------------------------------------------------------------
# format_evaluation_report
# ---------------------------------------------------------------------------

import pytest  # noqa: E402


class TestFormatEvaluationReport:
    def test_format_empty(self) -> None:
        report = EvaluationReport()
        text = format_evaluation_report(report)
        assert "Total predictions" in text
        assert "0" in text

    def test_format_with_data(self) -> None:
        records = [
            _make_record(event_id="e1", confidence="high", correct=True),
            _make_record(event_id="e2", confidence="medium", correct=False),
        ]
        report = evaluate_predictions(records)
        text = format_evaluation_report(report)
        assert "50.0%" in text
        assert "HIGH" in text
        assert "Brier" in text
