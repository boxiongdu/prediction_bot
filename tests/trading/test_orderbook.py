"""Tests for order book simulation and fill engine."""

from __future__ import annotations

from prediction_bot.kalshi.orderbooks import OrderBook, OrderBookLevel
from prediction_bot.trading.orderbook import FillResult, simulate_fill
from prediction_bot.trading.executor import (
    DryRunExecutor,
    OrderProposal,
)


# ── Mock order books ──────────────────────────────────────────────

def _ob(yes_asks: list[tuple[float, float]]) -> OrderBook:
    """Build a minimal OrderBook for testing."""
    return OrderBook(
        ticker="TEST-01",
        captured_at="2026-01-01T00:00:00",
        yes_asks=[OrderBookLevel(price=p, size=s) for p, s in yes_asks],
    )


OB_DEEP = _ob([
    (0.50, 100.0),
    (0.502, 50.0),
    (0.505, 30.0),
    (0.508, 20.0),
])

OB_THIN = _ob([(0.50, 10.0)])

OB_EMPTY = _ob([])

OB_WIDE = _ob([(0.50, 5.0), (0.70, 100.0)])


class TestSimulateFill:
    """Tests for the order book fill simulator."""

    def test_full_fill_at_best(self) -> None:
        result = simulate_fill(OB_DEEP, "YES", 80.0)
        assert result.is_complete
        assert not result.is_partial
        assert result.filled_size == 80.0
        assert result.unfilled_size == 0.0
        assert result.average_price == 0.50
        assert result.levels_consumed == 1
        assert result.slippage_bps == 0.0

    def test_walks_multiple_levels(self) -> None:
        result = simulate_fill(OB_DEEP, "YES", 120.0)
        assert result.is_complete
        assert result.levels_consumed == 2
        # 100 @ 0.50 + 20 @ 0.502 = 120
        expected_avg = (100 * 0.50 + 20 * 0.502) / 120
        assert abs(result.average_price - expected_avg) < 0.001
        assert result.slippage_bps > 0

    def test_partial_fill_depth_exhausted(self) -> None:
        result = simulate_fill(OB_DEEP, "YES", 500.0)
        assert result.is_partial
        # All 3 levels within 1% slippage = 180, 4th at 0.508 exceeds cap
        assert result.filled_size == 180.0
        assert result.unfilled_size == 320.0

    def test_partial_fill_thin_book(self) -> None:
        result = simulate_fill(OB_THIN, "YES", 50.0)
        assert result.is_partial
        assert result.filled_size == 10.0
        assert result.unfilled_size == 40.0

    def test_empty_book_returns_no_liquidity(self) -> None:
        result = simulate_fill(OB_EMPTY, "YES", 100.0)
        assert result.filled_size == 0.0
        assert result.average_price is None

    def test_slippage_limit_truncates(self) -> None:
        # Wide spread: 0.50 → 0.70, max 100bps = 1% = 0.505 max
        result = simulate_fill(OB_WIDE, "YES", 50.0, max_slippage_bps=100.0)
        assert result.filled_size == 5.0  # only first level

    def test_no_side(self) -> None:
        result = simulate_fill(OB_DEEP, "NO", 100.0)
        assert result.filled_size == 0.0  # no NO asks in mock


class TestDryRunExecutorWithOB:
    """Tests for the executor with order book integration."""

    def test_fill_with_order_book(self, tmp_path) -> None:
        db = str(tmp_path / "test_exec.db")
        executor = DryRunExecutor(db)

        proposal = OrderProposal(
            ticker="TEST-01",
            event_ticker="TEST",
            side="YES",
            size=80.0,
            limit_price=0.60,
            model_prob=0.55,
            expected_edge=0.05,
            best_ask=0.50,
            best_bid=0.49,
            spread=0.01,
            ask_depth=200.0,
        )

        sim = executor.simulate_fill_against_book(proposal, order_book=OB_DEEP)
        assert sim.status in ("filled", "partial_fill")
        assert sim.fill_size is not None
        assert sim.fill_size > 0

    def test_fill_with_empty_book(self, tmp_path) -> None:
        db = str(tmp_path / "test_exec2.db")
        executor = DryRunExecutor(db)

        proposal = OrderProposal(
            ticker="TEST-01",
            event_ticker="TEST",
            side="YES",
            size=100.0,
            limit_price=0.60,
            model_prob=0.55,
            expected_edge=0.05,
            best_ask=0.55,
        )

        sim = executor.simulate_fill_against_book(proposal, order_book=OB_EMPTY)
        # Falls back to best_ask fill
        assert sim.status == "filled"
        assert sim.fill_price == 0.55
