"""Prediction settlement evaluation.

Compares predictions against actual results to produce:
- Overall accuracy
- Accuracy by confidence level
- Abstention count
- Calibration table (binned probabilities vs observed outcomes)
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

from prediction_bot.storage import PredictionRecord

# ---------------------------------------------------------------------------
# Evaluation results
# ---------------------------------------------------------------------------


@dataclass
class ConfidenceBreakdown:
    """Accuracy breakdown for a single confidence level."""

    confidence: str
    total: int = 0
    correct: int = 0
    incorrect: int = 0
    accuracy: float = 0.0

    def compute(self) -> None:
        if self.total > 0:
            self.accuracy = self.correct / self.total


@dataclass
class CalibrationBin:
    """A probability bin for calibration analysis."""

    bin_label: str  # e.g. "0.5–0.6"
    bin_low: float
    bin_high: float
    count: int = 0
    correct: int = 0
    expected_correct: float = 0.0
    observed_rate: float = 0.0

    def compute(self) -> None:
        if self.count > 0:
            self.observed_rate = self.correct / self.count


@dataclass
class EvaluationReport:
    """Complete settlement evaluation report."""

    total_predictions: int = 0
    total_settled: int = 0
    total_abstentions: int = 0
    total_correct: int = 0
    overall_accuracy: float = 0.0

    confidence_breakdowns: list[ConfidenceBreakdown] = field(default_factory=list)
    calibration_bins: list[CalibrationBin] = field(default_factory=list)

    # Fair coins: predictions with 0.45–0.55 probability (near 50/50)
    fair_coin_count: int = 0
    fair_coin_correct: int = 0
    fair_coin_accuracy: float = 0.0

    # Brier score (lower is better, range 0–1)
    brier_score: float | None = None

    def compute_derived(self) -> None:
        """Compute derived statistics after populating breakdowns."""
        if self.total_settled > 0:
            self.overall_accuracy = self.total_correct / self.total_settled

        for cb in self.confidence_breakdowns:
            cb.compute()

        for cb in self.calibration_bins:
            cb.compute()

        if self.fair_coin_count > 0:
            self.fair_coin_accuracy = self.fair_coin_correct / self.fair_coin_count


# ---------------------------------------------------------------------------
# Evaluator
# ---------------------------------------------------------------------------


# Probability bins for calibration
DEFAULT_CALIBRATION_BINS: list[tuple[str, float, float]] = [
    ("0.0–0.1", 0.0, 0.1),
    ("0.1–0.2", 0.1, 0.2),
    ("0.2–0.3", 0.2, 0.3),
    ("0.3–0.4", 0.3, 0.4),
    ("0.4–0.5", 0.4, 0.5),
    ("0.5–0.6", 0.5, 0.6),
    ("0.6–0.7", 0.6, 0.7),
    ("0.7–0.8", 0.7, 0.8),
    ("0.8–0.9", 0.8, 0.9),
    ("0.9–1.0", 0.9, 1.0),
]


def evaluate_predictions(
    records: Sequence[PredictionRecord],
    bins: list[tuple[str, float, float]] | None = None,
) -> EvaluationReport:
    """Evaluate a set of settled predictions.

    Only records with actual_result set are evaluated. Abstentions are counted
    but excluded from accuracy calculations.

    Args:
        records: A sequence of PredictionRecord objects.
        bins: Optional custom calibration bin definitions.

    Returns:
        An EvaluationReport with all computed statistics.
    """
    if bins is None:
        bins = DEFAULT_CALIBRATION_BINS

    report = EvaluationReport()
    report.total_predictions = len(records)

    # Separate into settled, unsettled, abstained
    settled: list[PredictionRecord] = []
    abstained: list[PredictionRecord] = []
    for r in records:
        if r.abstain:
            abstained.append(r)
        elif r.actual_result is not None:
            settled.append(r)

    report.total_settled = len(settled)
    report.total_abstentions = len(abstained)

    if not settled:
        return report

    # --- Accuracy by confidence ---
    conf_groups: dict[str, ConfidenceBreakdown] = {}
    for r in settled:
        c = r.confidence.lower()
        if c not in conf_groups:
            conf_groups[c] = ConfidenceBreakdown(confidence=c)
        conf_groups[c].total += 1
        if r.correct_prediction:
            conf_groups[c].correct += 1
            report.total_correct += 1
        else:
            conf_groups[c].incorrect += 1

    # Order: high, medium, low
    for level in ("high", "medium", "low"):
        if level in conf_groups:
            report.confidence_breakdowns.append(conf_groups[level])
    for level, cb in sorted(conf_groups.items()):
        if level not in ("high", "medium", "low"):
            report.confidence_breakdowns.append(cb)

    # --- Calibration table ---
    bin_map: dict[str, CalibrationBin] = {}
    for label, low, high in bins:
        bin_map[label] = CalibrationBin(bin_label=label, bin_low=low, bin_high=high)

    for r in settled:
        # Use the higher of the two probabilities as the "predicted probability"
        pred_prob = max(r.team_a_probability, r.team_b_probability)

        # Find the right bin
        for label, low, high in bins:
            if low <= pred_prob <= high:
                cb = bin_map[label]
                cb.count += 1
                cb.expected_correct += pred_prob
                if r.correct_prediction:
                    cb.correct += 1
                break

    report.calibration_bins = [
        bin_map[label]
        for label, _, _ in bins
        if bin_map[label].count > 0
    ]

    # --- Fair coin analysis ---
    for r in settled:
        pred_prob = max(r.team_a_probability, r.team_b_probability)
        if 0.45 <= pred_prob <= 0.55:
            report.fair_coin_count += 1
            if r.correct_prediction:
                report.fair_coin_correct += 1

    # --- Brier score ---
    if settled:
        brier_sum = 0.0
        for r in settled:
            # Brier = (p - o)^2 where p is probability of predicted winner, o is 1 if correct
            pred_prob = max(r.team_a_probability, r.team_b_probability)
            outcome = 1.0 if r.correct_prediction else 0.0
            brier_sum += (pred_prob - outcome) ** 2
        report.brier_score = brier_sum / len(settled)

    report.compute_derived()
    return report


def evaluate_store(
    store,  # PredictionStore
) -> EvaluationReport:
    """Evaluate all settled predictions in a PredictionStore."""
    records = list(store.iter_settled())
    return evaluate_predictions(records)


# ---------------------------------------------------------------------------
# Formatting
# ---------------------------------------------------------------------------


def format_evaluation_report(report: EvaluationReport) -> str:
    """Format an EvaluationReport as a human-readable string."""
    lines: list[str] = []
    lines.append("=" * 60)
    lines.append("  PREDICTION EVALUATION REPORT")
    lines.append("=" * 60)
    lines.append("")
    lines.append(f"  Total predictions:       {report.total_predictions}")
    lines.append(f"  Settled predictions:     {report.total_settled}")
    lines.append(f"  Abstentions:             {report.total_abstentions}")
    lines.append(f"  Correct predictions:     {report.total_correct}")
    lines.append(f"  Overall accuracy:        {report.overall_accuracy:.1%}")
    lines.append("")

    if report.brier_score is not None:
        lines.append(f"  Brier score:             {report.brier_score:.4f}  (0=perfect, 1=worst)")
        lines.append("")

    # Confidence breakdown
    if report.confidence_breakdowns:
        lines.append("-" * 60)
        lines.append("  ACCURACY BY CONFIDENCE")
        lines.append("-" * 60)
        lines.append(f"  {'Confidence':<12} {'Total':>6} {'Correct':>8} {'Accuracy':>10}")
        lines.append(f"  {'-'*12} {'-'*6} {'-'*8} {'-'*10}")
        for cb in report.confidence_breakdowns:
            lines.append(
                f"  {cb.confidence.upper():<12} {cb.total:>6} "
                f"{cb.correct:>8} {cb.accuracy:>9.1%}"
            )
        lines.append("")

    # Calibration
    if report.calibration_bins:
        lines.append("-" * 60)
        lines.append("  CALIBRATION TABLE")
        lines.append("-" * 60)
        lines.append(
            f"  {'Bin':<10} {'Count':>6} {'Correct':>8} "
            f"{'Expected':>9} {'Observed':>9}"
        )
        lines.append(f"  {'-'*10} {'-'*6} {'-'*8} {'-'*9} {'-'*9}")
        for cb in report.calibration_bins:
            expected_rate = cb.expected_correct / cb.count if cb.count else 0.0
            lines.append(
                f"  {cb.bin_label:<10} {cb.count:>6} "
                f"{cb.correct:>8} {expected_rate:>8.1%} {cb.observed_rate:>8.1%}"
            )
        lines.append("")

    # Fair coin
    if report.fair_coin_count > 0:
        lines.append("-" * 60)
        lines.append("  FAIR COIN ANALYSIS (predictions near 50%)")
        lines.append("-" * 60)
        lines.append(f"  Count:   {report.fair_coin_count}")
        lines.append(f"  Correct: {report.fair_coin_correct}")
        lines.append(f"  Rate:    {report.fair_coin_accuracy:.1%}")
        lines.append("")

    lines.append("=" * 60)
    return "\n".join(lines)
