"""
Order-book-based fill simulation.

Replaces the naive "fill at ask" with realistic multi-level execution:
  - Walks the order book from best price outward
  - Computes average fill price, slippage, partial fills
  - Returns unfilled quantity when depth is insufficient
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from prediction_bot.kalshi.orderbooks import OrderBook

logger = logging.getLogger(__name__)


@dataclass
class FillResult:
    """Result of simulating an order against the order book."""

    ticker: str
    side: str  # YES or NO
    requested_size: float
    filled_size: float
    unfilled_size: float
    average_price: float | None  # None if no fill
    total_cost: float  # filled_size × average_price
    slippage_bps: float  # basis points from best price
    levels_consumed: int  # how many OB levels were eaten
    is_partial: bool
    is_complete: bool
    notes: list[str] = field(default_factory=list)

    @property
    def fill_rate(self) -> float:
        if self.requested_size == 0:
            return 0.0
        return self.filled_size / self.requested_size


def simulate_fill(
    order_book: OrderBook,
    side: str,
    size: float,
    max_slippage_bps: float = 100.0,  # 1% max slippage
) -> FillResult:
    """Simulate filling an order against the Kalshi order book.

    Walks the order book levels from best price outward, consuming
    available size at each level until the order is filled or depth
    is exhausted.

    Args:
        order_book: Parsed Kalshi order book.
        side: 'YES' or 'NO'.
        size: Number of contracts to buy (in dollars of notional — each
              contract pays $1 if correct).
        max_slippage_bps: Maximum allowed slippage in basis points
              (100 = 1%). Orders beyond this are truncated.

    Returns:
        FillResult with fill details.
    """
    if order_book.is_empty:
        return FillResult(
            ticker=order_book.ticker,
            side=side,
            requested_size=size,
            filled_size=0.0,
            unfilled_size=size,
            average_price=None,
            total_cost=0.0,
            slippage_bps=0.0,
            levels_consumed=0,
            is_partial=True,
            is_complete=False,
            notes=["Order book is empty — no fill possible"],
        )

    # Select the right side of the book
    if side.upper() == "YES":
        levels = order_book.yes_asks  # buying YES = lifting asks
    else:
        levels = order_book.no_asks  # buying NO = lifting NO asks

    if not levels:
        return FillResult(
            ticker=order_book.ticker,
            side=side,
            requested_size=size,
            filled_size=0.0,
            unfilled_size=size,
            average_price=None,
            total_cost=0.0,
            slippage_bps=0.0,
            levels_consumed=0,
            is_partial=True,
            is_complete=False,
            notes=[f"No {side} asks available"],
        )

    best_price = levels[0].price
    max_price = best_price * (1 + max_slippage_bps / 10000)
    remaining = size
    total_cost = 0.0
    filled = 0.0
    levels_eaten = 0

    for level in levels:
        if remaining <= 0:
            break
        if level.price > max_price:
            break

        take = min(remaining, level.size)
        total_cost += take * level.price
        filled += take
        remaining -= take
        levels_eaten += 1

    if filled == 0:
        return FillResult(
            ticker=order_book.ticker,
            side=side,
            requested_size=size,
            filled_size=0.0,
            unfilled_size=size,
            average_price=None,
            total_cost=0.0,
            slippage_bps=0.0,
            levels_consumed=0,
            is_partial=True,
            is_complete=False,
            notes=[f"Best ask {best_price:.4f} exceeds max {max_price:.4f}"],
        )

    avg_price = total_cost / filled
    slippage = (avg_price - best_price) / best_price * 10000 if best_price > 0 else 0.0

    notes: list[str] = []
    if remaining > 0:
        notes.append(f"Partial fill: {remaining:.0f} unfilled (depth exhausted)")
    if levels_eaten > 1:
        notes.append(f"Walked {levels_eaten} levels, avg price {avg_price:.4f}")

    return FillResult(
        ticker=order_book.ticker,
        side=side,
        requested_size=size,
        filled_size=filled,
        unfilled_size=remaining,
        average_price=round(avg_price, 6),
        total_cost=round(total_cost, 2),
        slippage_bps=round(slippage, 1),
        levels_consumed=levels_eaten,
        is_partial=remaining > 0,
        is_complete=remaining <= 0,
        notes=notes,
    )
