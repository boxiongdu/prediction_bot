"""
Trading strategy rules — separated concerns.

Prediction probability → Trade eligibility → Position sizing → Execution.

All parameters are explicit. No hidden state. Easy to backtest and tune.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


# ──────────────────────────────────────────────────────────────────────
# 1. Trade eligibility
# ──────────────────────────────────────────────────────────────────────


@dataclass
class EligibilityRule:
    """Determines whether a prediction qualifies for trading."""

    prob_lo: float = 0.60  # minimum model probability
    prob_hi: float = 0.85  # maximum model probability
    min_edge: float = 0.03  # minimum edge over market price
    require_hermes_approval: bool = True
    require_elo_coverage: bool = True  # both teams must have Elo history

    def check(
        self,
        prob: float,
        edge: float | None = None,
        hermes_approved: bool = True,
        both_known: bool = True,
    ) -> tuple[bool, str]:
        """Check if a prediction is eligible for trading.

        Returns (eligible, reason).
        """
        if prob < self.prob_lo:
            return False, f"prob {prob:.3f} < {self.prob_lo}"
        if prob > self.prob_hi:
            return False, f"prob {prob:.3f} > {self.prob_hi}"
        if edge is not None and edge < self.min_edge:
            return False, f"edge {edge:.1%} < {self.min_edge:.0%}"
        if self.require_hermes_approval and not hermes_approved:
            return False, "hermes rejected"
        if self.require_elo_coverage and not both_known:
            return False, "unknown team — no Elo history"
        return True, "eligible"


# ──────────────────────────────────────────────────────────────────────
# 2. Position sizing
# ──────────────────────────────────────────────────────────────────────


@dataclass
class SizingRule:
    """Determines trade size based on probability and bankroll."""

    method: str = "fixed"  # fixed, kelly_fraction
    fixed_size: float = 100.0  # dollars per trade (fixed method)
    kelly_fraction: float = 0.25  # fraction of full Kelly (kelly_fraction)
    max_position_pct: float = 0.10  # max % of bankroll per trade
    bankroll: float = 10000.0

    def compute_size(self, prob: float) -> float:
        """Compute position size for a given probability.

        Args:
            prob: Model probability for the side we're betting on.

        Returns:
            Position size in dollars.
        """
        if self.method == "fixed":
            return self.fixed_size

        if self.method == "kelly_fraction":
            # Full Kelly: f* = edge / odds
            # edge = 2*prob - 1 (edge over fair 50%)
            # For binary outcome with payout (1-prob)/prob:
            #   win: gain (1-prob), loss: lose prob
            #   Kelly = prob - (1-prob) / ((1-prob)/prob)
            #         = prob - prob * (1-prob) / (1-prob)
            #         = 2*prob - 1
            edge = 2.0 * prob - 1.0
            if edge <= 0:
                return 0.0
            kelly = edge * self.kelly_fraction
            size = kelly * self.bankroll
            return min(size, self.bankroll * self.max_position_pct)

        return self.fixed_size


# ──────────────────────────────────────────────────────────────────────
# 3. PnL calculation
# ──────────────────────────────────────────────────────────────────────


def compute_pnl(prob: float, correct: bool, size: float) -> float:
    """Compute PnL for a binary Kalshi contract.

    Buying YES at price=prob:
      - If correct (YES wins): gain size * (1 - prob)
      - If wrong (YES loses): lose size * prob
    """
    if correct:
        return size * (1.0 - prob)
    return -size * prob


# ──────────────────────────────────────────────────────────────────────
# 4. Strategy configuration (bundled)
# ──────────────────────────────────────────────────────────────────────


@dataclass
class StrategyConfig:
    """Complete strategy configuration."""

    eligibility: EligibilityRule = field(default_factory=EligibilityRule)
    sizing: SizingRule = field(default_factory=SizingRule)
    name: str = "default"

    def evaluate_trade(
        self,
        prob: float,
        edge: float | None = None,
        hermes_approved: bool = True,
        both_known: bool = True,
    ) -> dict[str, Any]:
        """Evaluate a trade end-to-end.

        Returns a dict with decision, size, and reasoning.
        """
        eligible, reason = self.eligibility.check(
            prob, edge, hermes_approved, both_known,
        )
        if not eligible:
            return {"trade": False, "size": 0.0, "reason": reason}

        size = self.sizing.compute_size(prob)
        if size <= 0:
            return {"trade": False, "size": 0.0, "reason": "zero size"}

        return {
            "trade": True,
            "size": size,
            "prob": prob,
            "edge": edge,
            "reason": "eligible",
        }


# ──────────────────────────────────────────────────────────────────────
# Pre-built configurations
# ──────────────────────────────────────────────────────────────────────

STRATEGY_DEFAULT = StrategyConfig(
    eligibility=EligibilityRule(prob_lo=0.60, prob_hi=0.85, min_edge=0.03),
    sizing=SizingRule(method="fixed", fixed_size=100.0),
    name="default-0.60-0.85",
)

STRATEGY_CONSERVATIVE = StrategyConfig(
    eligibility=EligibilityRule(prob_lo=0.62, prob_hi=0.82, min_edge=0.05),
    sizing=SizingRule(method="fixed", fixed_size=50.0),
    name="conservative-0.62-0.82",
)
