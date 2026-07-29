"""Executable price extraction from Kalshi order books.

Executable prices are ASK for YES positions and (1 - BID) for NO positions.
Never use midpoint — it is not a price you can transact at.

All prices use Decimal for exact arithmetic.
"""

from __future__ import annotations

from decimal import Decimal

from prediction_bot.data.schema import KalshiOrderBookSnapshot, MarketSide


def executable_price_yes(snapshot: KalshiOrderBookSnapshot) -> Decimal | None:
    """Price to buy YES: the best ask.

    Returns None if there is no ask (no liquidity on the buy side).
    """
    return snapshot.best_ask


def executable_price_no(snapshot: KalshiOrderBookSnapshot) -> Decimal | None:
    """Price to buy NO: 1 - best_bid.

    Rationale: buying NO is equivalent to selling YES. The price you pay
    for NO is 1 minus the best bid for YES.

    Returns None if there is no bid (no liquidity on the sell side).
    """
    if snapshot.best_bid is not None:
        return Decimal("1") - snapshot.best_bid
    return None


def executable_price(
    snapshot: KalshiOrderBookSnapshot, side: MarketSide,
) -> Decimal | None:
    """Get the executable price for a given market side."""
    if side == MarketSide.YES:
        return executable_price_yes(snapshot)
    return executable_price_no(snapshot)


def spread(snapshot: KalshiOrderBookSnapshot) -> Decimal | None:
    """Compute the bid-ask spread, or None if either side is missing."""
    return snapshot.spread


def midpoint(snapshot: KalshiOrderBookSnapshot) -> Decimal | None:
    """Compute the midpoint price (FOR REFERENCE ONLY — not executable)."""
    return snapshot.midpoint


def has_sufficient_depth(
    snapshot: KalshiOrderBookSnapshot,
    side: MarketSide,
    min_contracts: int = 50,
) -> bool:
    """Check whether the relevant side has sufficient depth.

    Args:
        snapshot: The order book snapshot.
        side: Which side we want to trade (YES or NO).
        min_contracts: Minimum number of contracts needed at best price.

    Returns:
        True if depth >= min_contracts.
    """
    depth = snapshot.ask_depth if side == MarketSide.YES else snapshot.bid_depth

    if depth is None:
        return False
    return depth >= Decimal(str(min_contracts))


def has_acceptable_spread(
    snapshot: KalshiOrderBookSnapshot,
    max_spread: Decimal | float = Decimal("0.05"),
) -> bool:
    """Check whether the spread is within acceptable bounds.

    Returns True if the spread is not None and ≤ max_spread.
    A missing spread (no bid or no ask) is not acceptable.
    """
    if snapshot.spread is None:
        return False
    limit = Decimal(str(max_spread)) if not isinstance(max_spread, Decimal) else max_spread
    return snapshot.spread <= limit


def parse_yes_no_prices_from_raw(
    raw_order_book: dict,
) -> tuple[float | None, float | None]:
    """Extract YES bid/ask from a raw Kalshi order book response.

    Handles both the nested and flat response formats.

    Returns:
        Tuple of (yes_bid, yes_ask). Each is None if missing.
    """
    ob = raw_order_book.get("order_book", raw_order_book)

    yes_bid: float | None = None
    yes_ask: float | None = None

    yes_bids = ob.get("yes_bids", [])
    yes_asks = ob.get("yes_asks", [])

    if yes_bids:
        yes_bid = float(yes_bids[0].get("price", 0)) if yes_bids[0] else None

    if yes_asks:
        yes_ask = float(yes_asks[0].get("price", 0)) if yes_asks[0] else None

    return yes_bid, yes_ask


def build_snapshot_from_raw(
    ticker: str,
    raw_order_book: dict,
    raw_market: dict | None = None,
) -> KalshiOrderBookSnapshot:
    """Build a KalshiOrderBookSnapshot from raw API responses.

    Args:
        ticker: The market ticker.
        raw_order_book: Raw order book response.
        raw_market: Optional raw market response for last_price.

    Returns:
        Parsed snapshot with Decimal values.
    """
    from datetime import datetime, timezone

    yes_bid, yes_ask = parse_yes_no_prices_from_raw(raw_order_book)

    ob = raw_order_book.get("order_book", raw_order_book)
    yes_bids = ob.get("yes_bids", [])
    yes_asks = ob.get("yes_asks", [])

    bid_depth: Decimal | None = None
    ask_depth: Decimal | None = None

    if yes_bids and yes_bids[0]:
        bid_depth = Decimal(str(yes_bids[0].get("count", 0)))
    if yes_asks and yes_asks[0]:
        ask_depth = Decimal(str(yes_asks[0].get("count", 0)))

    last_price: Decimal | None = None
    if raw_market:
        raw_lp = raw_market.get("last_price")
        if raw_lp is not None:
            last_price = Decimal(str(raw_lp))

    # Also extract last_price from the top-level order book response
    if last_price is None:
        raw_last = raw_order_book.get("last_price")
        if raw_last is not None:
            last_price = Decimal(str(raw_last))

    return KalshiOrderBookSnapshot(
        market_ticker=ticker,
        captured_at=datetime.now(timezone.utc),
        best_bid=Decimal(str(yes_bid)) if yes_bid is not None else None,
        best_ask=Decimal(str(yes_ask)) if yes_ask is not None else None,
        bid_depth=bid_depth,
        ask_depth=ask_depth,
        last_price=last_price,
    )
