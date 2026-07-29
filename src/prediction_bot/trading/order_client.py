"""
Kalshi order client — official API format for live trading.

Endpoints:
  POST   /portfolio/events/orders       (create order)
  DELETE /portfolio/events/orders/{id}  (cancel order)

Order format follows Kalshi's official spec:
  - side: "bid" (buy) or "ask" (sell)
  - count: number of contracts
  - price: per-contract price in dollars
  - time_in_force: "good_till_canceled"
  - self_trade_prevention_type: "taker_at_cross"
  - client_order_id: UUID for dedup

Modes: PAPER (default: APPROVAL), supports APPROVAL and AUTO.
ENABLE_LIVE_TRADING=true required for actual API calls.
"""
from __future__ import annotations

import json
import logging
import os
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

ENABLE_LIVE_TRADING = os.environ.get("ENABLE_LIVE_TRADING", "false").lower() in (
    "true", "1", "yes",
)

BASE_URL = "https://external-api.kalshi.com/trade-api/v2"
ORDERS_PATH = "/portfolio/events/orders"


# ──────────────────────────────────────────────────────────────────────
# Trade proposal
# ──────────────────────────────────────────────────────────────────────


@dataclass
class TradeProposal:
    """A trade proposal for manual approval before execution."""

    ticker: str
    team: str
    opponent: str
    probability: float
    market_price: float | None
    edge: float | None
    size: float
    reason: str
    strategy_version: str = "0.62-0.85"
    timestamp: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "ticker": self.ticker,
            "team": self.team,
            "opponent": self.opponent,
            "probability": round(self.probability, 4),
            "market_price": (
                round(self.market_price, 4) if self.market_price else None
            ),
            "edge": round(self.edge, 4) if self.edge else None,
            "size": round(self.size, 2),
            "reason": self.reason,
            "strategy_version": self.strategy_version,
            "timestamp": self.timestamp or datetime.now(timezone.utc).isoformat(),
        }


# ──────────────────────────────────────────────────────────────────────
# Order result
# ──────────────────────────────────────────────────────────────────────


@dataclass
class OrderResult:
    """Result of a submitted/cancelled order."""

    status: str  # accepted, cancelled, failed, duplicate
    order_id: str
    client_order_id: str
    ticker: str
    side: str
    count: int
    price: float
    remaining_count: int = 0
    message: str = ""
    raw_response: dict[str, Any] = field(default_factory=dict)
    timestamp: str = ""


# ──────────────────────────────────────────────────────────────────────
# Kalshi order client
# ──────────────────────────────────────────────────────────────────────


class KalshiOrderClient:
    """Kalshi order submission client using official API format."""

    def __init__(self, mode: str | None = None) -> None:
        self.mode = (mode or os.environ.get("LIVE_TRADING_MODE", "APPROVAL")).upper()
        self._submitted: dict[str, str] = {}  # client_order_id → order_id
        self._failures: list[dict[str, Any]] = []

        if self.mode not in ("PAPER", "APPROVAL", "AUTO"):
            raise ValueError(f"Invalid mode: {self.mode}")

        logger.info(
            "KalshiOrderClient: mode=%s live_trading=%s",
            self.mode, ENABLE_LIVE_TRADING,
        )

    @property
    def is_paper(self) -> bool:
        return self.mode == "PAPER"

    @property
    def can_submit(self) -> bool:
        return ENABLE_LIVE_TRADING and self.mode in ("APPROVAL", "AUTO")

    @property
    def recent_failures(self) -> list[dict[str, Any]]:
        return self._failures[-10:]

    def _reconcile(self, order_id: str) -> None:
        """Fetch order status and update the execution ledger."""
        try:
            from prediction_bot.trading.order_reconciler import reconcile_order
            snap = reconcile_order(order_id)
            logger.info(
                "Reconciled %s: state=%s filled=%.0f/%.0f cost=$%.4f",
                order_id, snap.state.value,
                snap.filled_count, snap.initial_count, snap.fill_cost,
            )
        except Exception as e:
            logger.warning("Reconciliation failed for %s: %s", order_id, e)

    # ── Proposal generation ──────────────────────────────────────

    def propose(self, proposal: TradeProposal) -> TradeProposal:
        """Log and return a trade proposal for review."""
        proposal.timestamp = datetime.now(timezone.utc).isoformat()
        logger.info(
            "TRADE PROPOSAL:\n%s", json.dumps(proposal.to_dict(), indent=2),
        )
        return proposal

    def approve(self, proposal: TradeProposal) -> OrderResult:
        """Approve a proposal and submit the order.

        In APPROVAL mode: requires explicit call.
        In AUTO mode: submit directly.
        In PAPER mode: raises.
        """
        if self.mode == "PAPER":
            raise RuntimeError("Cannot submit in PAPER mode.")
        return self._submit(proposal)

    # ── Test order (single contract) ──────────────────────────────

    def test_order(
        self, ticker: str, price: float, require_confirm: bool = True,
    ) -> OrderResult:
        """Submit exactly 1 contract for API connectivity testing.

        Args:
            ticker: Kalshi market ticker.
            price: Per-contract price (e.g., 0.01 for 1 cent).
            require_confirm: If True, prints proposal and waits for input.

        Returns:
            OrderResult with order_id on success.
        """
        proposal = TradeProposal(
            ticker=ticker,
            team="TEST",
            opponent="TEST",
            probability=price,
            market_price=price,
            edge=0.0,
            size=1,
            reason="API connectivity test — 1 contract",
        )

        logger.info("API CONNECTIVITY TEST")
        logger.info(json.dumps(proposal.to_dict(), indent=2))

        if require_confirm:
            confirm = input(
                f"\nSubmit 1 contract for {ticker} at ${price:.2f}? "
                f"[yes/NO]: "
            )
            if confirm.strip().lower() not in ("yes", "y"):
                logger.info("Test cancelled by user.")
                return OrderResult(
                    status="cancelled",
                    order_id="",
                    client_order_id="",
                    ticker=ticker,
                    side="bid",
                    count=1,
                    price=price,
                    message="User cancelled test.",
                )

        return self._submit(proposal)

    def cancel_test_order(self, order_id: str) -> OrderResult:
        """Cancel a previously submitted test order."""
        return self._cancel(order_id)

    # ── Internal order submission ──────────────────────────────────

    def _submit(self, proposal: TradeProposal) -> OrderResult:
        """Submit an order to Kalshi using official API format."""
        timestamp = datetime.now(timezone.utc).isoformat()
        client_order_id = str(uuid.uuid4())

        order_data = {
            "ticker": proposal.ticker,
            "side": "bid",
            "count": str(int(proposal.size)),
            "price": f"{proposal.market_price or proposal.probability:.4f}",
            "time_in_force": "good_till_canceled",
            "self_trade_prevention_type": "taker_at_cross",
            "client_order_id": client_order_id,
        }

        logger.warning(
            "LIVE ORDER: ticker=%s side=bid count=%d price=%s client_id=%s",
            proposal.ticker,
            int(proposal.size),
            order_data["price"],
            client_order_id,
        )

        if not ENABLE_LIVE_TRADING:
            logger.info("SIMULATED (ENABLE_LIVE_TRADING=false)")
            return OrderResult(
                status="simulated",
                order_id=f"SIM-{client_order_id[:8]}",
                client_order_id=client_order_id,
                ticker=proposal.ticker,
                side="bid",
                count=int(proposal.size),
                price=float(order_data["price"]),
                message="Live trading disabled.",
                timestamp=timestamp,
            )

        # LIVE submission
        result = self._post_order(order_data)
        result.timestamp = timestamp

        if result.status == "accepted":
            self._submitted[client_order_id] = result.order_id
            logger.info(
                "ORDER ACCEPTED: id=%s client=%s ticker=%s",
                result.order_id, client_order_id, proposal.ticker,
            )
            # Reconcile immediately to get fill status
            self._reconcile(result.order_id)
        else:
            self._failures.append({
                "ticker": proposal.ticker,
                "client_order_id": client_order_id,
                "error": result.message,
                "timestamp": timestamp,
            })
            logger.error("ORDER FAILED: %s", result.message)

        return result

    def _post_order(self, order_data: dict[str, Any]) -> OrderResult:
        """POST to Kalshi orders endpoint with RSA signing."""
        import requests

        from prediction_bot.config.settings import get_settings
        from prediction_bot.kalshi.signing import (
            build_signing_path,
            load_private_key,
            sign_request,
        )

        settings = get_settings()
        key_id = settings.kalshi_key_id
        if not key_id:
            return OrderResult(
                status="failed",
                order_id="",
                client_order_id=order_data.get("client_order_id", ""),
                ticker=order_data.get("ticker", ""),
                side=order_data.get("side", "bid"),
                count=int(order_data.get("count", 0)),
                price=float(order_data.get("price", 0)),
                message="No Kalshi key ID configured. Set KALSHI_KEY_ID in .env.",
            )
        private_key_path = settings.kalshi_private_key_path
        if not private_key_path:
            return OrderResult(
                status="failed",
                order_id="",
                client_order_id=order_data.get("client_order_id", ""),
                ticker=order_data.get("ticker", ""),
                side=order_data.get("side", "bid"),
                count=int(order_data.get("count", 0)),
                price=float(order_data.get("price", 0)),
                message="No private key path configured. Set KALSHI_PRIVATE_KEY_PATH in .env.",
            )
        private_key = load_private_key(private_key_path)
        ts = str(int(datetime.now(timezone.utc).timestamp() * 1000))
        sign_path = build_signing_path(settings.kalshi_base_url, ORDERS_PATH)
        signature = sign_request(private_key, ts, "POST", sign_path)

        headers = {
            "KALSHI-ACCESS-KEY": key_id,
            "KALSHI-ACCESS-SIGNATURE": signature,
            "KALSHI-ACCESS-TIMESTAMP": ts,
            "Content-Type": "application/json",
        }

        logger.debug(
            "POST %s%s | method=POST path=%s headers_present=%s",
            settings.kalshi_base_url, ORDERS_PATH, sign_path,
            list(headers.keys()),
        )

        try:
            resp = requests.post(
                settings.kalshi_base_url + ORDERS_PATH,
                headers=headers, json=order_data, timeout=30,
            )
            if resp.status_code == 201:
                data = resp.json()
                order = data.get("order", data)
                return OrderResult(
                    status="accepted",
                    order_id=str(order.get("order_id", "")),
                    client_order_id=order_data["client_order_id"],
                    ticker=order_data["ticker"],
                    side=order_data["side"],
                    count=int(order_data["count"]),
                    price=float(order_data["price"]),
                    remaining_count=order.get("remaining_count", 0),
                    message="Order accepted.",
                    raw_response=order,
                )
            else:
                return OrderResult(
                    status="failed",
                    order_id="",
                    client_order_id=order_data.get("client_order_id", ""),
                    ticker=order_data.get("ticker", ""),
                    side=order_data.get("side", "bid"),
                    count=int(order_data.get("count", 0)),
                    price=float(order_data.get("price", 0)),
                    message=f"HTTP {resp.status_code}: {resp.text[:200]}",
                )
        except Exception as e:
            return OrderResult(
                status="failed",
                order_id="",
                client_order_id=order_data.get("client_order_id", ""),
                ticker=order_data.get("ticker", ""),
                side=order_data.get("side", "bid"),
                count=int(order_data.get("count", 0)),
                price=float(order_data.get("price", 0)),
                message=str(e),
            )

    def _cancel(self, order_id: str) -> OrderResult:
        """DELETE to cancel a Kalshi order."""
        import requests

        from prediction_bot.config.settings import get_settings
        from prediction_bot.kalshi.signing import (
            build_signing_path,
            load_private_key,
            sign_request,
        )

        cancel_path = f"{ORDERS_PATH}/{order_id}"
        settings = get_settings()
        key_id = settings.kalshi_key_id
        if not key_id:
            return OrderResult(
                status="cancel_failed",
                order_id=order_id,
                client_order_id="",
                ticker="",
                side="bid",
                count=0,
                price=0.0,
                message="No Kalshi key ID configured.",
            )
        private_key = load_private_key(settings.kalshi_private_key_path)
        ts = str(int(datetime.now(timezone.utc).timestamp() * 1000))
        sign_path = build_signing_path(settings.kalshi_base_url, cancel_path)
        signature = sign_request(private_key, ts, "DELETE", sign_path)

        headers = {
            "KALSHI-ACCESS-KEY": key_id,
            "KALSHI-ACCESS-SIGNATURE": signature,
            "KALSHI-ACCESS-TIMESTAMP": ts,
            "Content-Type": "application/json",
        }

        logger.warning("CANCEL ORDER: %s", order_id)

        if not ENABLE_LIVE_TRADING:
            return OrderResult(
                status="simulated_cancelled",
                order_id=order_id,
                client_order_id="",
                ticker="",
                side="bid",
                count=0,
                price=0.0,
                message="Live trading disabled — simulated cancel.",
            )

        try:
            resp = requests.delete(
                settings.kalshi_base_url + cancel_path,
                headers=headers, timeout=30,
            )
            if resp.status_code == 200:
                data = resp.json()
                logger.info("ORDER CANCELLED: %s", order_id)
                return OrderResult(
                    status="cancelled",
                    order_id=order_id,
                    client_order_id="",
                    ticker="",
                    side="bid",
                    count=0,
                    price=0.0,
                    message="Order cancelled.",
                    raw_response=data,
                )
            else:
                return OrderResult(
                    status="cancel_failed",
                    order_id=order_id,
                    client_order_id="",
                    ticker="",
                    side="bid",
                    count=0,
                    price=0.0,
                    message=f"HTTP {resp.status_code}: {resp.text[:200]}",
                )
        except Exception as e:
            return OrderResult(
                status="cancel_failed",
                order_id=order_id,
                client_order_id="",
                ticker="",
                side="bid",
                count=0,
                price=0.0,
                message=str(e),
            )


def generate_proposal(
    ticker: str,
    team_a: str,
    team_b: str,
    predicted_winner: str,
    prob: float,
    market_ask: float | None,
    size: float,
) -> TradeProposal:
    """Generate a formatted trade proposal for approval."""
    edge = prob - market_ask if market_ask else None
    return TradeProposal(
        ticker=ticker,
        team=predicted_winner,
        opponent=team_b if predicted_winner == team_a else team_a,
        probability=prob,
        market_price=market_ask,
        edge=edge,
        size=size,
        reason=(
            f"Model predicts {predicted_winner} at {prob:.1%} "
            f"(edge={edge:+.1%})" if edge else
            f"Model predicts {predicted_winner} at {prob:.1%}"
        ),
        timestamp=datetime.now(timezone.utc).isoformat(),
    )
