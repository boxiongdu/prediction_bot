"""Tests for monitoring system."""

from __future__ import annotations

from prediction_bot.monitoring.templates import alert_message, daily_report, weekly_report
from prediction_bot.monitoring.alerts import AlertManager


class TestTemplates:
    """Report template tests."""

    def test_daily_report_renders(self) -> None:
        data = {
            "date": "2026-07-29",
            "mode": "APPROVAL",
            "signals": {"markets_scanned": 200, "tier1_matches": 48,
                        "qualified_trades": 3, "trades_submitted": 1},
            "performance": {"open_positions": 1, "settled_positions": 1,
                           "wins": 1, "losses": 0, "win_rate": 1.0,
                           "realized_pnl": 0.26, "roi": 0.35},
            "risk": {"current_exposure": 0.74, "max_drawdown": 0.0,
                    "daily_loss": 0.0},
            "calibration": {},
        }
        result = daily_report(data)
        assert "2026-07-29" in result
        assert "APPROVAL" in result
        assert "Scanned:" in result
        assert "$+0.26" in result

    def test_weekly_report_renders(self) -> None:
        data = {
            "week": "2026-W31",
            "mode": "APPROVAL",
            "live": {"trades": 1, "win_rate": 1.0, "roi": 0.35,
                    "sharpe": 0.0, "max_dd": 0.0},
            "backtest": {"trades": 82, "win_rate": 0.79, "roi": 0.045,
                        "sharpe": 1.0, "pnl_lo": -200, "pnl_hi": 600,
                        "sharpe_lo": 0.5, "sharpe_hi": 1.5, "max_dd": -429},
        }
        result = weekly_report(data)
        assert "2026-W31" in result
        assert "APPROVAL" in result
        assert "Trades" in result
        assert "Backtest" in result

    def test_alert_order_submitted(self) -> None:
        event = {
            "type": "order_submitted",
            "ticker": "KXLOLGAME-TEST",
            "side": "bid",
            "count": 1,
            "price": 0.74,
            "order_id": "test-123",
            "timestamp": "2026-01-01T00:00:00",
        }
        msg = alert_message(event)
        assert "ORDER SUBMITTED" in msg
        assert "KXLOLGAME-TEST" in msg
        assert "test-123" in msg

    def test_alert_order_filled(self) -> None:
        event = {
            "type": "order_filled",
            "ticker": "KXLOLGAME-TEST",
            "filled": 1,
            "count": 1,
            "fill_price": 0.74,
            "cost": 0.74,
            "order_id": "test-123",
        }
        msg = alert_message(event)
        assert "ORDER FILLED" in msg
        assert "$0.7400" in msg

    def test_alert_order_rejected(self) -> None:
        event = {"type": "order_rejected", "ticker": "TEST", "reason": "no liquidity"}
        msg = alert_message(event)
        assert "ORDER REJECTED" in msg
        assert "no liquidity" in msg

    def test_alert_risk_limit(self) -> None:
        event = {"type": "risk_limit", "limit": "daily_loss", "current": "-55", "max": "50"}
        msg = alert_message(event)
        assert "RISK LIMIT" in msg
        assert "daily_loss" in msg

    def test_alert_api_error(self) -> None:
        event = {"type": "api_error", "endpoint": "/portfolio/orders", "error": "timeout"}
        msg = alert_message(event)
        assert "API ERROR" in msg
        assert "timeout" in msg


class TestAlertManager:
    """Alert manager tests."""

    def test_disabled_by_default(self) -> None:
        alerts = AlertManager()
        assert alerts.sent_count == 0
        # Should not raise
        alerts.send({"type": "test"})

    def test_factory_methods(self) -> None:
        alerts = AlertManager()
        alerts.order_submitted("T", "bid", 1, 0.74, "id-1")
        alerts.order_filled("T", 1, 1, 0.74, 0.74, "id-1")
        alerts.order_rejected("T", "test")
        alerts.risk_limit("exposure", 120, 100)
        alerts.api_error("/test", "err")
        assert alerts.sent_count == 0  # disabled, but logged
