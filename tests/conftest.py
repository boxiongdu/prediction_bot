"""Shared test fixtures."""

from __future__ import annotations

import pytest


@pytest.fixture
def sample_team_data() -> dict:
    return {
        "team_id": "t1",
        "name": "T1",
        "region": "LCK",
        "aliases": ["SK Telecom T1", "SKT T1"],
    }


@pytest.fixture
def sample_match_data() -> dict:
    from datetime import datetime, timezone

    return {
        "match_id": "lck-2025-spring-week1-t1-vs-gen",
        "tournament_id": "lck-spring-2025",
        "team_a_id": "t1",
        "team_b_id": "gen-g",
        "format": "BO3",
        "patch": "15.1",
        "scheduled_time": datetime(2025, 1, 15, 8, 0, tzinfo=timezone.utc),
        "winner": "t1",
        "cancelled": False,
    }


@pytest.fixture
def sample_order_book_raw() -> dict:
    return {
        "order_book": {
            "yes_bids": [{"price": "55", "count": "100"}],
            "yes_asks": [{"price": "58", "count": "80"}],
            "no_bids": [{"price": "40", "count": "50"}],
            "no_asks": [{"price": "43", "count": "60"}],
        },
        "last_price": "56",
    }


@pytest.fixture
def sample_kalshi_market_raw_new_api() -> dict:
    """Exact format from Kalshi API docs with *_dollars and *_fp fields."""
    return {
        "ticker": "LOL-T1-25",
        "event_ticker": "LOL-LCK-W1-25",
        "title": "T1 to win vs Gen.G — LCK Spring 2025 Week 1",
        "subtitle": "League of Legends",
        "yes_sub_title": "T1 wins the match",
        "no_sub_title": "T1 does not win the match",
        "category": "esports",
        "rules_primary": "This market resolves Yes if T1 wins the match.",
        "close_time": "2025-01-15T08:00:00Z",
        "open_interest_fp": "40.00",
        "volume_fp": "100.00",
        "volume_24h_fp": "12.00",
        "yes_bid_dollars": "0.5600",
        "yes_ask_dollars": "0.5900",
        "yes_bid_size_fp": "10.00",
        "yes_ask_size_fp": "25.00",
        "no_bid_dollars": "0.4000",
        "no_ask_dollars": "0.4300",
        "last_price_dollars": "0.5600",
        "liquidity_dollars": "500.00",
        "status": "open",
    }


@pytest.fixture
def sample_kalshi_market_raw_old_api() -> dict:
    """Old API format with cent-based integer fields (backward compatibility)."""
    return {
        "ticker": "OLD-T1-25",
        "event_ticker": "OLD-LCK-W1",
        "title": "T1 to win vs Gen.G",
        "subtitle": "League of Legends",
        "volume": 12000,
        "open_interest": 5000,
        "yes_bid": 56,
        "yes_ask": 59,
        "last_price": 56,
        "status": "open",
    }
