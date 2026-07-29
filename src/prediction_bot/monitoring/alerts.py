"""
Real-time alert notifications for the trading system.

Read-only — publishes events, never affects trade execution.

Supports: console (always), Discord webhook, Telegram bot.
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from typing import Any

from prediction_bot.monitoring.templates import alert_message

logger = logging.getLogger(__name__)

NOTIFICATION_ENABLED = os.environ.get("NOTIFICATION_ENABLED", "false").lower() in (
    "true", "1", "yes",
)
NOTIFICATION_CHANNEL = os.environ.get("NOTIFICATION_CHANNEL", "telegram").lower()

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL", "")


class AlertManager:
    """Routes alerts to configured notification channels.

    Usage:
        alerts = AlertManager()
        alerts.send({"type": "order_filled", "ticker": "...", ...})
    """

    def __init__(self) -> None:
        self._enabled = NOTIFICATION_ENABLED
        self._channel = NOTIFICATION_CHANNEL
        self._sent_count = 0

        if not self._enabled:
            logger.info("Alerts: disabled (NOTIFICATION_ENABLED=false)")
        else:
            logger.info("Alerts: enabled, channel=%s", self._channel)

    @property
    def sent_count(self) -> int:
        return self._sent_count

    def send(self, event: dict[str, Any]) -> None:
        """Send an alert through all configured channels."""
        event.setdefault("timestamp", datetime.now(timezone.utc).isoformat())
        msg = alert_message(event)

        # Console always logs
        logger.info("ALERT: %s", msg.replace("\n", " | "))

        if not self._enabled:
            return

        self._sent_count += 1

        if self._channel == "telegram" and TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID:
            self._send_telegram(msg)
        elif self._channel == "discord" and DISCORD_WEBHOOK_URL:
            self._send_discord({"content": f"```\n{msg}\n```"})
        elif self._channel == "discord_webhooks" and DISCORD_WEBHOOK_URL:
            self._send_discord({"content": f"```\n{msg}\n```"})

    # ── Alert factory methods ────────────────────────────────

    def order_submitted(
        self, ticker: str, side: str, count: int, price: float, order_id: str,
    ) -> None:
        self.send({
            "type": "order_submitted",
            "ticker": ticker,
            "side": side,
            "count": count,
            "price": price,
            "order_id": order_id,
        })

    def order_filled(
        self, ticker: str, filled: int, count: int,
        fill_price: float, cost: float, order_id: str,
    ) -> None:
        self.send({
            "type": "order_filled",
            "ticker": ticker,
            "filled": filled,
            "count": count,
            "fill_price": fill_price,
            "cost": cost,
            "order_id": order_id,
        })

    def order_rejected(self, ticker: str, reason: str) -> None:
        self.send({
            "type": "order_rejected",
            "ticker": ticker,
            "reason": reason,
        })

    def risk_limit(self, limit_name: str, current: float, maximum: float) -> None:
        self.send({
            "type": "risk_limit",
            "limit": limit_name,
            "current": str(current),
            "max": str(maximum),
        })

    def api_error(self, endpoint: str, error: str) -> None:
        self.send({
            "type": "api_error",
            "endpoint": endpoint,
            "error": error,
        })

    # ── Channel backends ────────────────────────────────────

    def _send_telegram(self, text: str) -> None:
        try:
            import requests
            url = (
                f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"
                f"/sendMessage"
            )
            payload = {
                "chat_id": TELEGRAM_CHAT_ID,
                "text": text,
                "parse_mode": "Markdown",
            }
            resp = requests.post(url, json=payload, timeout=10)
            if resp.status_code != 200:
                logger.warning(
                    "Telegram send failed: HTTP %d — %s",
                    resp.status_code, resp.text[:200],
                )
        except Exception as e:
            logger.warning("Telegram send error: %s", e)

    def _send_discord(self, payload: dict[str, Any]) -> None:
        try:
            import requests
            resp = requests.post(
                DISCORD_WEBHOOK_URL, json=payload, timeout=10,
            )
            if resp.status_code not in (200, 204):
                logger.warning(
                    "Discord send failed: HTTP %d", resp.status_code,
                )
        except Exception as e:
            logger.warning("Discord send error: %s", e)
