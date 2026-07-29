"""Tests for order reconciliation."""

from __future__ import annotations

from prediction_bot.trading.order_reconciler import (
    OrderSnapshot,
    OrderState,
    fetch_order,
)


# ── Mock Kalshi order responses ──────────────────────────────

MOCK_EXECUTED = {
    "order": {
        "order_id": "fd74499e-b4cf-4804-b6e8-5812442716fa",
        "ticker": "KXLOLGAME-26AUG010700BLGJDG-BLG",
        "status": "executed",
        "side": "yes",
        "type": "limit",
        "yes_price_dollars": 0.74,
        "initial_count_fp": 1.0,
        "fill_count_fp": 1.0,
        "remaining_count_fp": 0.0,
        "taker_fill_cost_dollars": 0.74,
        "taker_fees_dollars": 0.0135,
        "client_order_id": "df9f0fb8-619c-4632-ad2e-59074214668c",
        "created_time": "2026-07-29T07:01:30.619109Z",
        "last_update_time": "2026-07-29T07:01:30.619109Z",
    },
}

MOCK_OPEN = {
    "order": {
        "order_id": "test-open-001",
        "ticker": "KXLOLGAME-TEST",
        "status": "resting",
        "side": "yes",
        "type": "limit",
        "yes_price_dollars": 0.50,
        "initial_count_fp": 5.0,
        "fill_count_fp": 0.0,
        "remaining_count_fp": 5.0,
        "taker_fill_cost_dollars": 0.0,
        "taker_fees_dollars": 0.0,
        "client_order_id": "client-001",
        "created_time": "2026-01-01T00:00:00Z",
        "last_update_time": "2026-01-01T00:00:00Z",
    },
}

MOCK_PARTIAL = {
    "order": {
        "order_id": "test-partial-001",
        "ticker": "KXLOLGAME-TEST",
        "status": "partially_filled",
        "side": "yes",
        "type": "limit",
        "yes_price_dollars": 0.60,
        "initial_count_fp": 10.0,
        "fill_count_fp": 3.0,
        "remaining_count_fp": 7.0,
        "taker_fill_cost_dollars": 1.80,
        "taker_fees_dollars": 0.03,
        "client_order_id": "client-002",
        "created_time": "2026-01-01T00:00:00Z",
        "last_update_time": "2026-01-01T00:00:00Z",
    },
}

MOCK_CANCELLED = {
    "order": {
        "order_id": "test-cancel-001",
        "ticker": "KXLOLGAME-TEST",
        "status": "cancelled",
        "side": "yes",
        "type": "limit",
        "yes_price_dollars": 0.55,
        "initial_count_fp": 1.0,
        "fill_count_fp": 0.0,
        "remaining_count_fp": 1.0,
        "taker_fill_cost_dollars": 0.0,
        "taker_fees_dollars": 0.0,
        "client_order_id": "client-003",
        "created_time": "2026-01-01T00:00:00Z",
        "last_update_time": "2026-01-01T00:00:00Z",
    },
}


class TestOrderState:
    """Order state parsing tests."""

    def test_executed(self) -> None:
        assert OrderState.from_kalshi("executed") == OrderState.EXECUTED
        assert OrderState.from_kalshi("filled") == OrderState.FILLED

    def test_open(self) -> None:
        assert OrderState.from_kalshi("resting") == OrderState.OPEN
        assert OrderState.from_kalshi("open") == OrderState.OPEN

    def test_partial(self) -> None:
        assert OrderState.from_kalshi("partially_filled") == OrderState.PARTIALLY_FILLED

    def test_cancelled(self) -> None:
        assert OrderState.from_kalshi("cancelled") == OrderState.CANCELLED
        assert OrderState.from_kalshi("canceled") == OrderState.CANCELLED

    def test_unknown(self) -> None:
        assert OrderState.from_kalshi("garbage") == OrderState.UNKNOWN


class TestOrderSnapshot:
    """Order snapshot parsing tests."""

    def test_parse_executed(self) -> None:
        snap = OrderSnapshot.from_api_response(MOCK_EXECUTED)
        assert snap.order_id == "fd74499e-b4cf-4804-b6e8-5812442716fa"
        assert snap.ticker == "KXLOLGAME-26AUG010700BLGJDG-BLG"
        assert snap.state == OrderState.EXECUTED
        assert snap.price == 0.74
        assert snap.filled_count == 1.0
        assert snap.remaining_count == 0.0
        assert snap.is_filled
        assert snap.is_terminal
        assert not snap.is_open
        assert snap.fill_rate == 1.0

    def test_parse_open(self) -> None:
        snap = OrderSnapshot.from_api_response(MOCK_OPEN)
        assert snap.state == OrderState.OPEN
        assert snap.filled_count == 0.0
        assert snap.remaining_count == 5.0
        assert not snap.is_filled
        assert snap.is_open
        assert not snap.is_terminal
        assert snap.fill_rate == 0.0

    def test_parse_partial(self) -> None:
        snap = OrderSnapshot.from_api_response(MOCK_PARTIAL)
        assert snap.state == OrderState.PARTIALLY_FILLED
        assert snap.filled_count == 3.0
        assert snap.remaining_count == 7.0
        assert snap.fill_rate == 0.3
        assert snap.is_open
        assert not snap.is_terminal

    def test_parse_cancelled(self) -> None:
        snap = OrderSnapshot.from_api_response(MOCK_CANCELLED)
        assert snap.state == OrderState.CANCELLED
        assert snap.is_terminal
        assert not snap.is_filled
