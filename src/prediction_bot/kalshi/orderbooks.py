"""
Kalshi order book fetcher — typed wrapper around the Kalshi API.

Returns full market depth for fill simulation.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class OrderBookLevel:
    """A single price level in the order book."""
    price: float
    size: float  # number of contracts available


@dataclass
class OrderBook:
    """Complete snapshot of a Kalshi market's order book."""
    ticker: str
    captured_at: str
    yes_bids: list[OrderBookLevel] = field(default_factory=list)
    yes_asks: list[OrderBookLevel] = field(default_factory=list)
    no_bids: list[OrderBookLevel] = field(default_factory=list)
    no_asks: list[OrderBookLevel] = field(default_factory=list)
    last_price: float | None = None

    @property
    def best_bid(self) -> float | None:
        if self.yes_bids:
            return self.yes_bids[0].price
        return None

    @property
    def best_ask(self) -> float | None:
        if self.yes_asks:
            return self.yes_asks[0].price
        return None

    @property
    def spread(self) -> float | None:
        if self.best_bid is not None and self.best_ask is not None:
            return self.best_ask - self.best_bid
        return None

    @property
    def bid_depth(self) -> float:
        return sum(level.size for level in self.yes_bids)

    @property
    def ask_depth(self) -> float:
        return sum(level.size for level in self.yes_asks)

    @property
    def is_empty(self) -> bool:
        return not self.yes_bids and not self.yes_asks


def fetch_order_book(
    ticker: str,
    client=None,
    depth: int = 10,
) -> OrderBook:
    """Fetch and parse the order book for a Kalshi market.

    Args:
        ticker: Kalshi market ticker.
        client: Optional KalshiClient. Creates one if None.
        depth: Order book depth to request.

    Returns:
        Parsed OrderBook with all price levels.
    """
    from prediction_bot.kalshi.client import KalshiClient

    if client is None:
        client = KalshiClient()
        own_client = True
    else:
        own_client = False

    try:
        raw = client.get_order_book(ticker, depth=depth)
        ob_data = raw.get("order_book", raw)

        def _parse_levels(data: list[dict]) -> list[OrderBookLevel]:
            return [
                OrderBookLevel(
                    price=float(level.get("price", 0)),
                    size=float(level.get("count", 0)),
                )
                for level in (data or [])
                if level.get("count", 0) > 0
            ]

        ob = OrderBook(
            ticker=ticker,
            captured_at=datetime.now(timezone.utc).isoformat(),
            yes_bids=_parse_levels(ob_data.get("yes_bids", [])),
            yes_asks=_parse_levels(ob_data.get("yes_asks", [])),
            no_bids=_parse_levels(ob_data.get("no_bids", [])),
            no_asks=_parse_levels(ob_data.get("no_asks", [])),
            last_price=(
                float(raw.get("last_price"))
                if raw.get("last_price") is not None
                else None
            ),
        )

        logger.debug(
            "OB %s: bid=%.4f(%d) ask=%.4f(%d) spread=%.4f",
            ticker,
            ob.best_bid or 0, len(ob.yes_bids),
            ob.best_ask or 0, len(ob.yes_asks),
            ob.spread or 0,
        )
        return ob

    finally:
        if own_client:
            client.close()


def fetch_order_books(
    tickers: list[str],
    client=None,
    depth: int = 10,
) -> dict[str, OrderBook]:
    """Fetch order books for multiple tickers.

    Uses a shared client for efficiency. Returns dict of ticker → OrderBook.
    """
    from prediction_bot.kalshi.client import KalshiClient

    if client is None:
        client = KalshiClient()
        own_client = True
    else:
        own_client = False

    result: dict[str, OrderBook] = {}
    try:
        for ticker in tickers:
            try:
                result[ticker] = fetch_order_book(ticker, client=client, depth=depth)
            except Exception as e:
                logger.warning("Failed to fetch OB for %s: %s", ticker, e)
                result[ticker] = OrderBook(
                    ticker=ticker,
                    captured_at=datetime.now(timezone.utc).isoformat(),
                )
    finally:
        if own_client:
            client.close()

    return result
