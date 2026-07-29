"""First live order submission — Bilibili Gaming vs JD Gaming."""
import json
import logging
import os
import sys

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("first-live-order")

# ── Trade details ──────────────────────────────────────────
TICKER = "KXLOLGAME-26AUG010700BLGJDG-BLG"
MATCH = "Bilibili Gaming vs JD Gaming"
TEAM = "Bilibili Gaming"
PROB = 0.786
PRICE = 0.74
SIZE = 1  # 1 contract only

# ── Validate market ────────────────────────────────────────
import requests

logger.info("Step 1: Validating market %s", TICKER)
resp = requests.get(
    f"https://external-api.kalshi.com/trade-api/v2/markets/{TICKER}",
    timeout=30,
)
resp.raise_for_status()
market = resp.json().get("market", resp.json())

status = market.get("status", "")
ask = float(market.get("yes_ask_dollars", 0))
bid = float(market.get("yes_bid_dollars", 0))
ask_size = float(market.get("yes_ask_size_fp", 0))
yes_sub = market.get("yes_sub_title", "")

assert status in ("open", "active"), f"Market status: {status}"
assert ask > 0, f"No ask price: {ask}"
assert ask_size >= SIZE, f"Insufficient size: {ask_size} < {SIZE}"
assert TEAM.lower() in (yes_sub or "").lower(), f"Side mismatch: {yes_sub}"

logger.info("Market valid ✓  status=%s ask=$%.4f bid=$%.4f size=%.0f", status, ask, bid, ask_size)

# ── Order proposal ─────────────────────────────────────────
proposal = {
    "ticker": TICKER,
    "match": MATCH,
    "selected_team": TEAM,
    "side": "bid",
    "model_probability": PROB,
    "market_price": PRICE,
    "edge": round(PROB - PRICE, 4),
    "quantity": SIZE,
    "strategy_version": "0.62-0.85",
}
logger.info("Order proposal:\n%s", json.dumps(proposal, indent=2))

# ── Confirm ────────────────────────────────────────────────
live = os.environ.get("ENABLE_LIVE_TRADING", "false").lower() in ("true", "1", "yes")
if not live:
    logger.error("ENABLE_LIVE_TRADING=false — cannot submit real order.")
    logger.info("To submit: export ENABLE_LIVE_TRADING=true")
    sys.exit(1)

confirm = input(
    f"\nSubmit 1 contract for {TEAM} to win vs {MATCH.split(' vs ')[1]} "
    f"at ${PRICE:.2f}? [type 'yes' to confirm]: "
)
if confirm.strip().lower() != "yes":
    logger.info("User cancelled.")
    sys.exit(0)

# ── Submit order ───────────────────────────────────────────
import uuid
from datetime import datetime, timezone
from urllib.parse import urlparse

from prediction_bot.config.settings import get_settings
from prediction_bot.kalshi.signing import load_private_key, sign_request

settings = get_settings()
key_id = settings.kalshi_key_id
private_key = load_private_key(settings.kalshi_private_key_path)
base = settings.kalshi_base_url
path = "/portfolio/events/orders"

ts = str(int(datetime.now(timezone.utc).timestamp() * 1000))
sign_path = urlparse(base + path).path
signature = sign_request(private_key, ts, "POST", sign_path)

client_order_id = str(uuid.uuid4())
order_payload = {
    "ticker": TICKER,
    "side": "bid",
    "count": str(SIZE),
    "price": f"{PRICE:.4f}",
    "time_in_force": "good_till_canceled",
    "self_trade_prevention_type": "taker_at_cross",
    "client_order_id": client_order_id,
}

logger.info("Submitting order...")
logger.info("Payload: %s", json.dumps({k: v for k, v in order_payload.items() if k != "client_order_id"}, indent=2))

resp = requests.post(
    base + path,
    headers={
        "KALSHI-ACCESS-KEY": key_id,
        "KALSHI-ACCESS-SIGNATURE": signature,
        "KALSHI-ACCESS-TIMESTAMP": ts,
        "Content-Type": "application/json",
    },
    json=order_payload,
    timeout=30,
)

logger.info("Response: HTTP %d", resp.status_code)

if resp.status_code == 201:
    data = resp.json()
    order = data.get("order", data)
    logger.info("ORDER ACCEPTED!")
    logger.info("  Order ID:     %s", order.get("order_id"))
    logger.info("  Client ID:    %s", client_order_id)
    logger.info("  Status:       %s", order.get("status"))
    logger.info("  Remaining:    %s", order.get("remaining_count"))
    logger.info("  Price:        %s", order.get("price"))

    # Write ledger entry
    from pathlib import Path
    ledger = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "order_id": str(order.get("order_id", "")),
        "client_order_id": client_order_id,
        "ticker": TICKER,
        "match": MATCH,
        "team": TEAM,
        "side": "bid",
        "model_probability": PROB,
        "price": PRICE,
        "quantity": SIZE,
        "strategy_version": "0.62-0.85",
        "status": order.get("status", "accepted"),
        "remaining_count": order.get("remaining_count", 0),
        "response": order,
    }
    Path("data/live_orders.jsonl").parent.mkdir(parents=True, exist_ok=True)
    with open("data/live_orders.jsonl", "a") as f:
        f.write(json.dumps(ledger) + "\n")
    logger.info("Ledger saved to data/live_orders.jsonl")

else:
    logger.error("ORDER FAILED: %s", resp.text[:500])
    sys.exit(1)
