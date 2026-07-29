"""Tests for Kalshi executable price parsing."""

from __future__ import annotations

from decimal import Decimal

from prediction_bot.data.schema import KalshiOrderBookSnapshot, MarketSide
from prediction_bot.kalshi.prices import (
    build_snapshot_from_raw,
    executable_price,
    executable_price_no,
    executable_price_yes,
    has_acceptable_spread,
    has_sufficient_depth,
    parse_yes_no_prices_from_raw,
    spread,
)


class TestParseYesNoPricesFromRaw:
    def test_standard_order_book(self, sample_order_book_raw: dict) -> None:
        yes_bid, yes_ask = parse_yes_no_prices_from_raw(sample_order_book_raw)
        assert yes_bid == 55.0
        assert yes_ask == 58.0

    def test_missing_yes_bids(self) -> None:
        raw = {"order_book": {"yes_asks": [{"price": "58", "count": "10"}]}}
        yes_bid, yes_ask = parse_yes_no_prices_from_raw(raw)
        assert yes_bid is None
        assert yes_ask == 58.0

    def test_missing_yes_asks(self) -> None:
        raw = {"order_book": {"yes_bids": [{"price": "55", "count": "10"}]}}
        yes_bid, yes_ask = parse_yes_no_prices_from_raw(raw)
        assert yes_bid == 55.0
        assert yes_ask is None

    def test_empty_order_book(self) -> None:
        yes_bid, yes_ask = parse_yes_no_prices_from_raw({"order_book": {}})
        assert yes_bid is None
        assert yes_ask is None

    def test_empty_bids_and_asks(self) -> None:
        yes_bid, yes_ask = parse_yes_no_prices_from_raw({"order_book": {"yes_bids": [], "yes_asks": []}})  # noqa: E501
        assert yes_bid is None
        assert yes_ask is None

    def test_flat_response_no_order_book_key(self) -> None:
        yes_bid, yes_ask = parse_yes_no_prices_from_raw({"yes_bids": [{"price": "60", "count": "10"}]})  # noqa: E501
        assert yes_bid == 60.0


class TestExecutablePrices:
    def test_yes_price_is_ask(self) -> None:
        snap = KalshiOrderBookSnapshot(market_ticker="T", best_ask=Decimal("0.62"))
        assert executable_price_yes(snap) == Decimal("0.62")

    def test_no_price_is_one_minus_bid(self) -> None:
        snap = KalshiOrderBookSnapshot(market_ticker="T", best_bid=Decimal("0.55"))
        assert executable_price_no(snap) == Decimal("0.45")

    def test_missing_ask_yes_returns_none(self) -> None:
        snap = KalshiOrderBookSnapshot(market_ticker="T", best_bid=Decimal("0.55"))
        assert executable_price_yes(snap) is None

    def test_missing_bid_no_returns_none(self) -> None:
        snap = KalshiOrderBookSnapshot(market_ticker="T", best_ask=Decimal("0.58"))
        assert executable_price_no(snap) is None

    def test_executable_price_dispatches(self) -> None:
        snap = KalshiOrderBookSnapshot(
            market_ticker="T", best_bid=Decimal("0.40"), best_ask=Decimal("0.45"),
        )  # noqa: E501
        assert executable_price(snap, MarketSide.YES) == Decimal("0.45")
        assert executable_price(snap, MarketSide.NO) == Decimal("0.60")

    def test_spread(self) -> None:
        snap = KalshiOrderBookSnapshot(
            market_ticker="T", best_bid=Decimal("0.50"), best_ask=Decimal("0.55"),
        )  # noqa: E501
        assert spread(snap) == Decimal("0.05")

    def test_spread_missing_bid(self) -> None:
        snap = KalshiOrderBookSnapshot(market_ticker="T", best_ask=Decimal("0.55"))
        assert spread(snap) is None


class TestDepthAndSpreadFilters:
    def test_sufficient_depth_yes(self) -> None:
        snap = KalshiOrderBookSnapshot(
            market_ticker="T", best_ask=Decimal("0.58"), ask_depth=Decimal("100"),
        )  # noqa: E501
        assert has_sufficient_depth(snap, MarketSide.YES, min_contracts=50) is True

    def test_insufficient_depth_yes(self) -> None:
        snap = KalshiOrderBookSnapshot(
            market_ticker="T", best_ask=Decimal("0.58"), ask_depth=Decimal("10"),
        )  # noqa: E501
        assert has_sufficient_depth(snap, MarketSide.YES, min_contracts=50) is False

    def test_sufficient_depth_no(self) -> None:
        snap = KalshiOrderBookSnapshot(
            market_ticker="T", best_bid=Decimal("0.55"), bid_depth=Decimal("200"),
        )  # noqa: E501
        assert has_sufficient_depth(snap, MarketSide.NO, min_contracts=50) is True

    def test_missing_depth(self) -> None:
        snap = KalshiOrderBookSnapshot(market_ticker="T", best_ask=Decimal("0.58"))
        assert has_sufficient_depth(snap, MarketSide.YES, min_contracts=50) is False

    def test_acceptable_spread(self) -> None:
        snap = KalshiOrderBookSnapshot(
            market_ticker="T", best_bid=Decimal("0.50"), best_ask=Decimal("0.53"),
        )  # noqa: E501
        assert has_acceptable_spread(snap, max_spread=Decimal("0.05")) is True

    def test_unacceptable_spread(self) -> None:
        snap = KalshiOrderBookSnapshot(
            market_ticker="T", best_bid=Decimal("0.50"), best_ask=Decimal("0.60"),
        )  # noqa: E501
        assert has_acceptable_spread(snap, max_spread=Decimal("0.05")) is False

    def test_missing_spread_not_acceptable(self) -> None:
        snap = KalshiOrderBookSnapshot(market_ticker="T", best_ask=Decimal("0.50"))
        assert has_acceptable_spread(snap, max_spread=Decimal("0.05")) is False


class TestBuildSnapshotFromRaw:
    def test_build_from_full_raw(self, sample_order_book_raw: dict) -> None:
        snap = build_snapshot_from_raw("TEST-TICKER", sample_order_book_raw)
        assert snap.market_ticker == "TEST-TICKER"
        assert snap.best_bid == Decimal("55.0")
        assert snap.best_ask == Decimal("58.0")
        assert snap.bid_depth == Decimal("100")
        assert snap.ask_depth == Decimal("80")
        assert snap.last_price == Decimal("56.0")

    def test_build_with_market_data(self) -> None:
        raw_ob = {"order_book": {"yes_bids": [{"price": "50", "count": "25"}], "yes_asks": []}}
        raw_mkt = {"last_price": "51"}
        snap = build_snapshot_from_raw("T", raw_ob, raw_mkt)
        assert snap.last_price == Decimal("51.0")

    def test_malformed_market_record(self) -> None:
        snap = build_snapshot_from_raw("T", {"order_book": {}})
        assert snap.best_bid is None
        assert snap.best_ask is None
        assert snap.bid_depth is None
        assert snap.ask_depth is None
