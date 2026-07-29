"""Tests for Kalshi read-only client.

Uses mocked HTTP responses (pytest-httpx) — no real API calls.
"""

from __future__ import annotations

from decimal import Decimal

import httpx
import pytest
from pytest_httpx import HTTPXMock

from prediction_bot.kalshi.client import KalshiClient


class TestKalshiClientInit:
    def test_default_init(self) -> None:
        client = KalshiClient()
        assert client._base_url == KalshiClient.BASE_URL
        client.close()

    def test_custom_params(self) -> None:
        client = KalshiClient(
            api_key="test-key", base_url="https://custom.example.com/v2",
            timeout=10, max_retries=2,
        )
        assert client._api_key == "test-key"
        assert client._base_url == "https://custom.example.com/v2"
        client.close()

    def test_context_manager(self, httpx_mock: HTTPXMock) -> None:
        httpx_mock.add_response(
            method="GET",
            url="https://external-api.kalshi.com/trade-api/v2/markets?status=open&limit=500",
            json={"markets": [], "cursor": None},
        )
        with KalshiClient() as client:
            assert client._client is None
            client.get_markets()
            assert client._client is not None
        assert client._client is None


class TestGetMarkets:
    def test_get_markets_success(self, httpx_mock: HTTPXMock) -> None:
        httpx_mock.add_response(
            method="GET",
            url="https://external-api.kalshi.com/trade-api/v2/markets?status=open&limit=500",
            json={"markets": [{"ticker": "TEST-01", "event_ticker": "EVT-01", "title": "Test Market", "status": "open"}], "cursor": None},  # noqa: E501
        )
        with KalshiClient() as client:
            result = client.get_markets()
            assert len(result["markets"]) == 1
            assert result["markets"][0]["ticker"] == "TEST-01"

    def test_get_markets_with_filters(self, httpx_mock: HTTPXMock) -> None:
        httpx_mock.add_response(
            method="GET",
            url="https://external-api.kalshi.com/trade-api/v2/markets?status=open&limit=100&event_ticker=EVT-02&series_ticker=SER-01",
            json={"markets": [], "cursor": None},
        )
        with KalshiClient() as client:
            result = client.get_markets(
                status="open", limit=100, event_ticker="EVT-02", series_ticker="SER-01",
            )
            assert result["markets"] == []

    def test_get_markets_http_error(self, httpx_mock: HTTPXMock) -> None:
        httpx_mock.add_response(
            method="GET",
            url="https://external-api.kalshi.com/trade-api/v2/markets?status=open&limit=500",
            status_code=500,
        )
        with KalshiClient(max_retries=1) as client, pytest.raises(httpx.HTTPStatusError):
            client.get_markets()

    def test_get_markets_retry_on_timeout(self, httpx_mock: HTTPXMock) -> None:
        httpx_mock.add_exception(httpx.TimeoutException("timeout"))
        httpx_mock.add_response(
            method="GET",
            url="https://external-api.kalshi.com/trade-api/v2/markets?status=open&limit=500",
            json={"markets": [{"ticker": "RETRY-01", "event_ticker": "E", "title": "After retry"}], "cursor": None},  # noqa: E501
        )
        with KalshiClient(max_retries=3) as client:
            result = client.get_markets()
            assert len(result["markets"]) == 1


class TestGetMarketsPaginated:
    def test_single_page(self, httpx_mock: HTTPXMock) -> None:
        httpx_mock.add_response(
            method="GET",
            url="https://external-api.kalshi.com/trade-api/v2/markets?status=open&limit=500",
            json={"markets": [{"ticker": "M1", "event_ticker": "E", "title": "M1"}], "cursor": None},  # noqa: E501
        )
        with KalshiClient() as client:
            assert len(client.get_markets_paginated(max_pages=3)) == 1

    def test_multi_page(self, httpx_mock: HTTPXMock) -> None:
        httpx_mock.add_response(
            method="GET",
            url="https://external-api.kalshi.com/trade-api/v2/markets?status=open&limit=500",
            json={"markets": [{"ticker": "M1", "event_ticker": "E", "title": "M1"}], "cursor": "page2"},  # noqa: E501
        )
        httpx_mock.add_response(
            method="GET",
            url="https://external-api.kalshi.com/trade-api/v2/markets?status=open&limit=500&cursor=page2",
            json={"markets": [{"ticker": "M2", "event_ticker": "E", "title": "M2"}], "cursor": None},  # noqa: E501
        )
        with KalshiClient() as client:
            markets = client.get_markets_paginated(max_pages=3)
            assert len(markets) == 2


class TestGetOrderBook:
    def test_get_order_book_success(self, httpx_mock: HTTPXMock) -> None:
        httpx_mock.add_response(
            method="GET",
            url="https://external-api.kalshi.com/trade-api/v2/markets/TEST-01/order_book?depth=10",
            json={"order_book": {"yes_bids": [{"price": "55", "count": "100"}], "yes_asks": [{"price": "58", "count": "80"}]}},  # noqa: E501
        )
        with KalshiClient() as client:
            ob = client.get_order_book("TEST-01").get("order_book", {})
            assert len(ob.get("yes_bids", [])) == 1

    def test_get_order_book_snapshot(self, httpx_mock: HTTPXMock) -> None:
        httpx_mock.add_response(
            method="GET",
            url="https://external-api.kalshi.com/trade-api/v2/markets/TEST-01/order_book?depth=10",
            json={"order_book": {"yes_bids": [{"price": "55", "count": "100"}], "yes_asks": [{"price": "58", "count": "80"}]}, "last_price": "56"},  # noqa: E501
        )
        with KalshiClient() as client:
            snap = client.get_order_book_snapshot("TEST-01")
            assert snap.market_ticker == "TEST-01"
            assert snap.best_bid == Decimal("55")
            assert snap.best_ask == Decimal("58")

    def test_get_order_book_empty(self, httpx_mock: HTTPXMock) -> None:
        httpx_mock.add_response(
            method="GET",
            url="https://external-api.kalshi.com/trade-api/v2/markets/EMPTY/order_book?depth=10",
            json={"order_book": {}},
        )
        with KalshiClient() as client:
            snap = client.get_order_book_snapshot("EMPTY")
            assert snap.best_bid is None
            assert snap.best_ask is None


# ---------------------------------------------------------------------------
# parse_market — new API format
# ---------------------------------------------------------------------------

class TestParseMarketNewApi:
    """Test parse_market with current Kalshi *_dollars and *_fp fields."""

    def test_new_api_prices(self, sample_kalshi_market_raw_new_api: dict) -> None:
        """yes_bid_dollars='0.5600' parses to Decimal('0.5600')."""
        with KalshiClient() as client:
            market = client.parse_market(sample_kalshi_market_raw_new_api)
        assert market.yes_bid == Decimal("0.5600")
        assert market.yes_ask == Decimal("0.5900")
        assert market.no_bid == Decimal("0.4000")
        assert market.no_ask == Decimal("0.4300")

    def test_new_api_spread(self, sample_kalshi_market_raw_new_api: dict) -> None:
        with KalshiClient() as client:
            market = client.parse_market(sample_kalshi_market_raw_new_api)
        assert market.spread == Decimal("0.0300")

    def test_new_api_quantities(self, sample_kalshi_market_raw_new_api: dict) -> None:
        with KalshiClient() as client:
            market = client.parse_market(sample_kalshi_market_raw_new_api)
        assert market.volume == Decimal("100.00")
        assert market.open_interest == Decimal("40.00")
        assert market.yes_bid_size == Decimal("10.00")
        assert market.yes_ask_size == Decimal("25.00")

    def test_new_api_subtitles(self, sample_kalshi_market_raw_new_api: dict) -> None:
        with KalshiClient() as client:
            market = client.parse_market(sample_kalshi_market_raw_new_api)
        assert market.yes_sub_title == "T1 wins the match"
        assert market.no_sub_title == "T1 does not win the match"


class TestParseMarketOldApi:
    """Test parse_market backward compatibility with old cent-based fields."""

    def test_old_api_cent_prices(self, sample_kalshi_market_raw_old_api: dict) -> None:
        """Old yes_bid=56 (cents) → Decimal('0.56') after division by 100."""
        with KalshiClient() as client:
            market = client.parse_market(sample_kalshi_market_raw_old_api)
        assert market.yes_bid == Decimal("0.56")
        assert market.yes_ask == Decimal("0.59")
        assert market.last_price == Decimal("0.56")

    def test_old_api_volume(self, sample_kalshi_market_raw_old_api: dict) -> None:
        with KalshiClient() as client:
            market = client.parse_market(sample_kalshi_market_raw_old_api)
        assert market.volume == Decimal("12000")
        assert market.open_interest == Decimal("5000")

    def test_old_api_no_subtitles(self, sample_kalshi_market_raw_old_api: dict) -> None:
        with KalshiClient() as client:
            market = client.parse_market(sample_kalshi_market_raw_old_api)
        assert market.yes_sub_title is None


class TestParseMarketEdgeCases:
    def test_minimal_market(self) -> None:
        raw = {"ticker": "MIN", "event_ticker": "E", "title": "Minimal"}
        with KalshiClient() as client:
            market = client.parse_market(raw)
        assert market.ticker == "MIN"
        assert market.volume is None

    def test_malformed_market(self) -> None:
        with KalshiClient() as client:
            market = client.parse_market({})
        assert market.ticker == ""

    def test_price_in_0_1_range_not_divided(self) -> None:
        """A yes_bid already in 0-1 range is NOT divided by 100."""
        with KalshiClient() as client:
            market = client.parse_market(
                {"ticker": "T", "event_ticker": "E", "title": "X", "yes_bid": 0.56},
            )
        assert market.yes_bid == Decimal("0.56")  # not 0.0056

    def test_new_api_takes_precedence(self) -> None:
        """yes_bid_dollars takes precedence over yes_bid."""
        raw = {
            "ticker": "T", "event_ticker": "E", "title": "X",
            "yes_bid_dollars": "0.42",  # new
            "yes_bid": 99,               # old (would be 0.99)
        }
        with KalshiClient() as client:
            market = client.parse_market(raw)
        assert market.yes_bid == Decimal("0.42")  # new field wins


class TestGetEvents:
    def test_get_events_success(self, httpx_mock: HTTPXMock) -> None:
        httpx_mock.add_response(
            method="GET",
            url="https://external-api.kalshi.com/trade-api/v2/events?status=open&limit=100",
            json={"events": [{"ticker": "EVT-01", "title": "Test Event"}], "cursor": None},
        )
        with KalshiClient() as client:
            assert len(client.get_events()["events"]) == 1
