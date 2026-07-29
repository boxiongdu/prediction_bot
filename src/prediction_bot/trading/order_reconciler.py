"""
Order reconciliation — fetch, parse, and track Kalshi order lifecycle.

States: SUBMITTED → OPEN → PARTIALLY_FILLED → FILLED | CANCELLED | REJECTED

Endpoint: GET /portfolio/orders/{order_id}
Response fields:
  - order_id, status, ticker, side, type
  - initial_count_fp, fill_count_fp, remaining_count_fp
  - yes_price_dollars, no_price_dollars
  - taker_fill_cost_dollars, taker_fees_dollars
  - created_time, last_update_time
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

ORDERS_PATH = "/portfolio/events/orders"
ORDER_STATUS_PATH = "/portfolio/orders"  # GET /portfolio/orders/{id}


class OrderState(str, Enum):
    SUBMITTED = "submitted"
    OPEN = "open"
    PARTIALLY_FILLED = "partially_filled"
    FILLED = "filled"
    EXECUTED = "executed"  # Kalshi uses "executed" for fully filled
    CANCELLED = "cancelled"
    REJECTED = "rejected"
    UNKNOWN = "unknown"

    @classmethod
    def from_kalshi(cls, status: str) -> OrderState:
        mapping = {
            "submitted": cls.SUBMITTED,
            "open": cls.OPEN,
            "resting": cls.OPEN,
            "partially_filled": cls.PARTIALLY_FILLED,
            "filled": cls.FILLED,
            "executed": cls.EXECUTED,
            "cancelled": cls.CANCELLED,
            "canceled": cls.CANCELLED,
            "rejected": cls.REJECTED,
        }
        return mapping.get(str(status).lower(), cls.UNKNOWN)


@dataclass
class OrderSnapshot:
    """Parsed order state from Kalshi API."""

    order_id: str
    ticker: str
    state: OrderState
    side: str  # yes / no
    type: str  # limit / market
    price: float  # yes_price_dollars
    initial_count: float
    filled_count: float
    remaining_count: float
    fill_cost: float  # taker_fill_cost_dollars
    fees: float  # taker_fees_dollars
    created_time: str
    last_update_time: str
    client_order_id: str = ""
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def is_filled(self) -> bool:
        return self.state in (OrderState.FILLED, OrderState.EXECUTED)

    @property
    def is_open(self) -> bool:
        return self.state in (OrderState.SUBMITTED, OrderState.OPEN, OrderState.PARTIALLY_FILLED)

    @property
    def is_terminal(self) -> bool:
        return self.state in (
            OrderState.FILLED, OrderState.EXECUTED,
            OrderState.CANCELLED, OrderState.REJECTED,
        )

    @property
    def fill_rate(self) -> float:
        if self.initial_count == 0:
            return 0.0
        return self.filled_count / self.initial_count

    @classmethod
    def from_api_response(cls, data: dict[str, Any]) -> OrderSnapshot:
        order = data.get("order", data)
        return cls(
            order_id=str(order.get("order_id", "")),
            ticker=str(order.get("ticker", "")),
            state=OrderState.from_kalshi(order.get("status", "")),
            side=str(order.get("side", "")),
            type=str(order.get("type", "")),
            price=float(order.get("yes_price_dollars", 0)),
            initial_count=float(order.get("initial_count_fp", 0)),
            filled_count=float(order.get("fill_count_fp", 0)),
            remaining_count=float(order.get("remaining_count_fp", 0)),
            fill_cost=float(order.get("taker_fill_cost_dollars", 0)),
            fees=float(order.get("taker_fees_dollars", 0)),
            created_time=str(order.get("created_time", "")),
            last_update_time=str(order.get("last_update_time", "")),
            client_order_id=str(order.get("client_order_id", "")),
            raw=order,
        )


def fetch_order(order_id: str) -> OrderSnapshot:
    """Fetch current order state from Kalshi.

    Requires KALSHI_KEY_ID + KALSHI_PRIVATE_KEY_PATH in settings.
    """
    from prediction_bot.config.settings import get_settings
    from prediction_bot.kalshi.signing import load_private_key, sign_request

    import requests

    settings = get_settings()
    key_id = settings.kalshi_key_id
    if not key_id:
        raise RuntimeError("KALSHI_KEY_ID not configured")

    private_key = load_private_key(settings.kalshi_private_key_path)
    base = settings.kalshi_base_url
    path = f"{ORDER_STATUS_PATH}/{order_id}"

    ts = str(int(datetime.now(timezone.utc).timestamp() * 1000))
    sign_path = urlparse(base + path).path
    signature = sign_request(private_key, ts, "GET", sign_path)

    logger.debug("GET %s%s", base, path)

    resp = requests.get(
        base + path,
        headers={
            "KALSHI-ACCESS-KEY": key_id,
            "KALSHI-ACCESS-SIGNATURE": signature,
            "KALSHI-ACCESS-TIMESTAMP": ts,
        },
        timeout=30,
    )
    resp.raise_for_status()
    return OrderSnapshot.from_api_response(resp.json())


def reconcile_order(order_id: str, ledger_path: str = "data/live_orders.jsonl") -> OrderSnapshot:
    """Fetch order status and update the ledger.

    Returns the parsed OrderSnapshot.
    """
    snapshot = fetch_order(order_id)

    ledger_file = Path(ledger_path)
    if ledger_file.exists():
        entries = []
        updated = False
        for line in ledger_file.read_text().strip().split("\n"):
            if not line.strip():
                continue
            entry = json.loads(line)
            if entry.get("order_id") == order_id:
                entry["status"] = snapshot.state.value
                entry["fill_count"] = snapshot.filled_count
                entry["remaining_count"] = snapshot.remaining_count
                entry["fill_cost"] = snapshot.fill_cost
                entry["fees"] = snapshot.fees
                entry["fill_rate"] = snapshot.fill_rate
                entry["last_update"] = snapshot.last_update_time
                entry["reconciled_at"] = datetime.now(timezone.utc).isoformat()
                updated = True
            entries.append(entry)

        if not updated:
            # Order not in ledger yet — add it
            entries.append({
                "order_id": snapshot.order_id,
                "ticker": snapshot.ticker,
                "side": snapshot.side,
                "price": snapshot.price,
                "initial_count": snapshot.initial_count,
                "filled_count": snapshot.filled_count,
                "remaining_count": snapshot.remaining_count,
                "fill_cost": snapshot.fill_cost,
                "fees": snapshot.fees,
                "fill_rate": snapshot.fill_rate,
                "status": snapshot.state.value,
                "created_time": snapshot.created_time,
                "last_update": snapshot.last_update_time,
                "reconciled_at": datetime.now(timezone.utc).isoformat(),
            })

        ledger_file.write_text("\n".join(json.dumps(e) for e in entries) + "\n")

    logger.info(
        "Order %s: state=%s filled=%.0f/%.0f cost=$%.4f fees=$%.6f",
        order_id, snapshot.state.value,
        snapshot.filled_count, snapshot.initial_count,
        snapshot.fill_cost, snapshot.fees,
    )

    return snapshot


def print_order_report(snapshot: OrderSnapshot) -> None:
    """Print a human-readable order status report."""
    print()
    print("=" * 50)
    print("  ORDER STATUS REPORT")
    print("=" * 50)
    print(f"  Order ID:      {snapshot.order_id}")
    print(f"  Ticker:        {snapshot.ticker}")
    print(f"  Side:          {snapshot.side}")
    print(f"  Type:          {snapshot.type}")
    print(f"  State:         {snapshot.state.value}")
    print(f"  Price:         ${snapshot.price:.4f}")
    print(f"  Filled:        {snapshot.filled_count:.0f}/{snapshot.initial_count:.0f}")
    print(f"  Remaining:     {snapshot.remaining_count:.0f}")
    print(f"  Fill cost:     ${snapshot.fill_cost:.4f}")
    print(f"  Fees:          ${snapshot.fees:.6f}")
    print(f"  Created:       {snapshot.created_time}")
    print(f"  Updated:       {snapshot.last_update_time}")

    if snapshot.is_filled:
        print()
        print(f"  ✓ FULLY FILLED at ${snapshot.price:.4f}")
    elif snapshot.is_open:
        print()
        print(f"  ○ STILL OPEN — {snapshot.remaining_count:.0f} contracts remaining")
    print()
