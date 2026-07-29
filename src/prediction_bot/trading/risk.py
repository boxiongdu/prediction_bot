"""
Risk controls — position limits, edge thresholds, liquidity, duplicate prevention.

All checks are applied BEFORE any trade (paper or live).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# Default risk parameters
DEFAULT_MAX_POSITION_SIZE = 100.0       # Max notional per trade
DEFAULT_MIN_EDGE_THRESHOLD = 0.03       # Minimum 3% edge
DEFAULT_MIN_LIQUIDITY = 10.0            # Minimum $10 in ask size
DEFAULT_MAX_TOTAL_EXPOSURE = 500.0      # Max total notional across all positions


@dataclass
class RiskCheck:
    """Result of a risk check."""
    passed: bool
    reason: str = ""
    risk_flags: list[str] = field(default_factory=list)


class RiskManager:
    """Pre-trade risk checks.

    Usage:
        rm = RiskManager()
        check = rm.check_trade(proposal)
        if not check.passed:
            logger.warning("Risk check failed: %s", check.reason)
    """

    def __init__(
        self,
        max_position_size: float = DEFAULT_MAX_POSITION_SIZE,
        min_edge_threshold: float = DEFAULT_MIN_EDGE_THRESHOLD,
        min_liquidity: float = DEFAULT_MIN_LIQUIDITY,
        max_total_exposure: float = DEFAULT_MAX_TOTAL_EXPOSURE,
    ) -> None:
        self.max_position_size = max_position_size
        self.min_edge_threshold = min_edge_threshold
        self.min_liquidity = min_liquidity
        self.max_total_exposure = max_total_exposure
        self._active_tickers: set[str] = set()

    def check_trade(
        self,
        ticker: str,
        side: str,
        size: float,
        edge: float,
        ask_size: float | None = None,
    ) -> RiskCheck:
        """Run all risk checks on a proposed trade.

        Returns RiskCheck with pass/fail and explanation.
        """
        flags: list[str] = []

        # ── Duplicate prevention ─────────────────────────
        key = f"{ticker}:{side}"
        if key in self._active_tickers:
            return RiskCheck(
                passed=False,
                reason=f"Duplicate order: {key} already has an active position",
                risk_flags=["duplicate"],
            )

        # ── Edge threshold ───────────────────────────────
        if edge < self.min_edge_threshold:
            return RiskCheck(
                passed=False,
                reason=(
                    f"Edge {edge:.1%} below minimum {self.min_edge_threshold:.0%}"
                ),
                risk_flags=["insufficient_edge"],
            )

        # ── Position size ────────────────────────────────
        if size > self.max_position_size:
            return RiskCheck(
                passed=False,
                reason=(
                    f"Position size ${size:.0f} exceeds max ${self.max_position_size:.0f}"
                ),
                risk_flags=["position_too_large"],
            )

        # ── Liquidity ────────────────────────────────────
        if ask_size is not None and ask_size < self.min_liquidity:
            flags.append("low_liquidity")
            # Don't reject, but flag

        # ── All checks passed ────────────────────────────
        self._active_tickers.add(key)
        return RiskCheck(passed=True, risk_flags=flags)

    def release_position(self, ticker: str, side: str) -> None:
        """Release a ticker from active positions (after settlement)."""
        key = f"{ticker}:{side}"
        self._active_tickers.discard(key)

    @property
    def active_positions(self) -> int:
        return len(self._active_tickers)
