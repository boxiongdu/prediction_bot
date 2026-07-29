"""
Production safety guards — restart safety, dedup, market validation, risk limits.

All checks must pass before any order (paper or live) is submitted.
"""
from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────
# Kill switches
# ──────────────────────────────────────────────────────────────────────

ENABLE_LIVE_TRADING = os.environ.get("ENABLE_LIVE_TRADING", "false").lower() in (
    "true", "1", "yes",
)
AUTO_TRADING_ENABLED = os.environ.get("AUTO_TRADING_ENABLED", "false").lower() in (
    "true", "1", "yes",
)
LIVE_TRADING_MODE = os.environ.get("LIVE_TRADING_MODE", "APPROVAL").upper()

# ──────────────────────────────────────────────────────────────────────
# Risk limits — scaled by mode
# ──────────────────────────────────────────────────────────────────────

# Paper limits
MAX_POSITION_PER_TRADE = float(os.environ.get("MAX_POSITION_PER_TRADE", "100"))
MAX_TOTAL_OPEN_EXPOSURE = float(os.environ.get("MAX_TOTAL_OPEN_EXPOSURE", "500"))
MAX_DAILY_LOSS = float(os.environ.get("MAX_DAILY_LOSS", "100"))
MAX_TRADES_PER_DAY = int(os.environ.get("MAX_TRADES_PER_DAY", "10"))

# AUTO mode: ultra-conservative limits
if LIVE_TRADING_MODE == "AUTO":
    MAX_POSITION_PER_TRADE = float(os.environ.get("MAX_POSITION_PER_TRADE", "5"))
    MAX_TOTAL_OPEN_EXPOSURE = float(os.environ.get("MAX_TOTAL_OPEN_EXPOSURE", "50"))
    MAX_DAILY_LOSS = float(os.environ.get("MAX_DAILY_LOSS", "25"))
    MAX_TRADES_PER_DAY = int(os.environ.get("MAX_TRADES_PER_DAY", "10"))


@dataclass
class MarketValidation:
    """Result of pre-trade market validation."""
    ticker: str
    is_open: bool = False
    not_expired: bool = False
    has_price: bool = False
    has_liquidity: bool = False
    yes_ask: float | None = None
    errors: list[str] = field(default_factory=list)

    @property
    def valid(self) -> bool:
        return all([self.is_open, self.not_expired, self.has_price, self.has_liquidity])


@dataclass
class SafetyCheck:
    """Result of all pre-trade safety checks."""
    ticker: str
    passed: bool = False
    reason: str = ""
    market: MarketValidation | None = None
    duplicate: bool = False
    exceeds_position_limit: bool = False
    exceeds_daily_loss: bool = False
    exceeds_trade_count: bool = False
    exceeds_exposure: bool = False


class ProductionSafety:
    """Pre-trade safety checks for production paper/live trading."""

    def __init__(
        self,
        mode: str | None = None,
        checkpoint_path: str = "data/paper_trading_checkpoint.json",
        daily_state_path: str = "data/daily_trading_state.json",
    ) -> None:
        self.mode = mode or LIVE_TRADING_MODE
        self.checkpoint_path = Path(checkpoint_path)
        self.daily_state_path = Path(daily_state_path)
        self._executed_tickers: set[str] = set()
        self._daily_state = self._load_daily_state()
        self._load_checkpoint()

    @property
    def is_paper(self) -> bool:
        return self.mode == "PAPER"

    @property
    def is_approval(self) -> bool:
        return self.mode == "APPROVAL"

    @property
    def is_auto(self) -> bool:
        return self.mode == "AUTO"

    @property
    def can_submit_orders(self) -> bool:
        """True if orders can be submitted (APPROVAL or AUTO with live enabled)."""
        if self.is_paper:
            return False
        if self.is_auto and not ENABLE_LIVE_TRADING:
            return False
        if self.is_auto and not AUTO_TRADING_ENABLED:
            return False
        return True

    def check_balance(self, order_cost: float) -> tuple[bool, float]:
        """Check available Kalshi balance. Returns (sufficient, available_balance)."""
        try:
            import requests
            from prediction_bot.config.settings import get_settings
            from prediction_bot.kalshi.signing import load_private_key, sign_request
            from urllib.parse import urlparse

            s = get_settings()
            if not s.kalshi_key_id:
                return False, 0.0
            pk = load_private_key(s.kalshi_private_key_path)
            ts_str = str(int(__import__('time').time() * 1000))
            from datetime import datetime as dt_mod
            ts_str = str(int(dt_mod.now(timezone.utc).timestamp() * 1000))
            path = "/portfolio/balance"
            sp = urlparse(s.kalshi_base_url + path).path
            sig = sign_request(pk, ts_str, "GET", sp)
            resp = requests.get(
                s.kalshi_base_url + path,
                headers={
                    "KALSHI-ACCESS-KEY": s.kalshi_key_id,
                    "KALSHI-ACCESS-SIGNATURE": sig,
                    "KALSHI-ACCESS-TIMESTAMP": ts_str,
                },
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()
            balance = float(data.get("balance", data).get("balance", 0)) / 100.0
            return balance >= order_cost, balance
        except Exception:
            return True, 999.0  # If we can't check, don't block

    @property
    def daily_loss(self) -> float:
        return self._daily_state.get("daily_loss", 0.0)

    @property
    def daily_trades(self) -> int:
        return self._daily_state.get("daily_trades", 0)

    @property
    def open_exposure(self) -> float:
        return self._daily_state.get("open_exposure", 0.0)

    # ── Checkpoint / restart safety ────────────────────────────

    def _load_checkpoint(self) -> None:
        if self.checkpoint_path.exists():
            try:
                raw = json.loads(self.checkpoint_path.read_text())
                self._executed_tickers = set(raw.get("executed_tickers", []))
                logger.info(
                    "Loaded safety checkpoint: %d executed tickers",
                    len(self._executed_tickers),
                )
            except Exception as e:
                logger.warning("Failed to load checkpoint: %s", e)

    def _load_daily_state(self) -> dict[str, Any]:
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        if self.daily_state_path.exists():
            try:
                data = json.loads(self.daily_state_path.read_text())
                if data.get("date") == today:
                    return data
            except Exception:
                pass
        return {
            "date": today,
            "daily_loss": 0.0,
            "daily_trades": 0,
            "open_exposure": 0.0,
            "positions_opened": 0,
        }

    def _save_daily_state(self) -> None:
        self.daily_state_path.parent.mkdir(parents=True, exist_ok=True)
        self.daily_state_path.write_text(json.dumps(self._daily_state, indent=2))

    # ── Duplicate prevention ────────────────────────────────────

    def is_duplicate(self, ticker: str, side: str) -> bool:
        """Check if a ticker+side combination has already been traded."""
        key = f"{ticker}:{side}"
        return key in self._executed_tickers

    def mark_executed(self, ticker: str, side: str) -> None:
        """Mark a ticker+side as executed to prevent duplicates."""
        key = f"{ticker}:{side}"
        self._executed_tickers.add(key)

    # ── Market validation ───────────────────────────────────────

    def validate_market(self, ticker: str, raw_market: dict[str, Any] | None = None) -> MarketValidation:
        """Validate that a market is still tradeable.

        Checks: open, not expired, has price, has liquidity.
        """
        errors: list[str] = []

        if raw_market is None:
            # Fetch from Kalshi
            import requests
            try:
                resp = requests.get(
                    f"https://external-api.kalshi.com/trade-api/v2/markets/{ticker}",
                    timeout=30,
                )
                resp.raise_for_status()
                data = resp.json()
                raw_market = data.get("market", data)
            except Exception as e:
                return MarketValidation(
                    ticker=ticker,
                    errors=[f"API fetch failed: {e}"],
                )

        status = str(raw_market.get("status", "")).lower()
        is_open = status in ("open", "active")
        if not is_open:
            errors.append(f"Market status is '{status}', not 'open'/'active'")

        # Check expiry
        close_time = raw_market.get("close_time")
        not_expired = True
        if close_time:
            from datetime import datetime as dt
            try:
                ct = dt.fromisoformat(str(close_time).replace("Z", "+00:00"))
                if ct < dt.now(timezone.utc):
                    not_expired = False
                    errors.append("Market has expired")
            except (ValueError, TypeError):
                pass

        # Check price
        yes_ask = raw_market.get("yes_ask")
        if not yes_ask:
            # Try yes_ask_dollars
            from prediction_bot.data.schema import _parse_price_dollars
            yes_ask = _parse_price_dollars(raw_market.get("yes_ask_dollars"))
        has_price = yes_ask is not None and float(yes_ask) > 0
        if not has_price:
            errors.append("No valid YES ask price available")

        # Check liquidity (at least some contracts available)
        yes_ask_count = raw_market.get("yes_ask_count", 0) or raw_market.get(
            "yes_ask_size_fp", 0
        )
        has_liquidity = yes_ask_count and float(yes_ask_count) > 0
        if not has_liquidity:
            errors.append("No liquidity (yes_ask_count/yes_ask_size_fp = 0)")

        return MarketValidation(
            ticker=ticker,
            is_open=is_open,
            not_expired=not_expired,
            has_price=has_price,
            has_liquidity=has_liquidity,
            yes_ask=float(yes_ask) if yes_ask else None,
            errors=errors,
        )

    # ── Risk limits ─────────────────────────────────────────────

    def check_trade(
        self,
        ticker: str,
        side: str,
        size: float,
        raw_market: dict[str, Any] | None = None,
    ) -> SafetyCheck:
        """Run all safety checks before a trade.

        Returns SafetyCheck with passed=True only if ALL checks pass.
        """
        reasons: list[str] = []

        # 1. Duplicate prevention
        if self.is_duplicate(ticker, side):
            return SafetyCheck(
                ticker=ticker,
                reason="Duplicate — ticker+side already executed",
                duplicate=True,
            )

        # 2. Trade count limit
        if self.daily_trades >= MAX_TRADES_PER_DAY:
            return SafetyCheck(
                ticker=ticker,
                reason=f"Daily trade limit ({MAX_TRADES_PER_DAY}) reached",
                exceeds_trade_count=True,
            )

        # 3. Position size limit
        if size > MAX_POSITION_PER_TRADE:
            return SafetyCheck(
                ticker=ticker,
                reason=(
                    f"Position size ${size:.0f} exceeds max "
                    f"${MAX_POSITION_PER_TRADE:.0f}"
                ),
                exceeds_position_limit=True,
            )

        # 4. Open exposure limit
        if self.open_exposure + size > MAX_TOTAL_OPEN_EXPOSURE:
            return SafetyCheck(
                ticker=ticker,
                reason=(
                    f"Open exposure ${self.open_exposure + size:.0f} exceeds "
                    f"max ${MAX_TOTAL_OPEN_EXPOSURE:.0f}"
                ),
                exceeds_exposure=True,
            )

        # 5. Daily loss limit
        if self.daily_loss <= -MAX_DAILY_LOSS:
            return SafetyCheck(
                ticker=ticker,
                reason=(
                    f"Daily loss ${self.daily_loss:.0f} exceeds "
                    f"max ${MAX_DAILY_LOSS:.0f}"
                ),
                exceeds_daily_loss=True,
            )

        # 6. Market validation
        market = self.validate_market(ticker, raw_market)
        if not market.valid:
            return SafetyCheck(
                ticker=ticker,
                reason=f"Market invalid: {'; '.join(market.errors)}",
                market=market,
            )

        return SafetyCheck(
            ticker=ticker,
            passed=True,
            reason="All checks passed",
            market=market,
        )

    # ── State updates ──────────────────────────────────────────

    def record_trade(self, ticker: str, side: str, size: float) -> None:
        """Record a trade that passed all checks."""
        self.mark_executed(ticker, side)
        self._daily_state["daily_trades"] = self._daily_state.get("daily_trades", 0) + 1
        self._daily_state["open_exposure"] = self._daily_state.get("open_exposure", 0.0) + size
        self._daily_state["positions_opened"] = self._daily_state.get("positions_opened", 0) + 1
        self._save_daily_state()

    def record_pnl(self, pnl: float) -> None:
        """Record realized PnL from a settled position."""
        self._daily_state["daily_loss"] = self._daily_state.get("daily_loss", 0.0) + pnl
        self._daily_state["open_exposure"] = max(
            0.0, self._daily_state.get("open_exposure", 0.0) - abs(pnl),
        )
        self._save_daily_state()

    def reset_daily(self) -> None:
        """Reset daily state (call at midnight)."""
        self._daily_state = {
            "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            "daily_loss": 0.0,
            "daily_trades": 0,
            "open_exposure": 0.0,
            "positions_opened": 0,
        }
        self._save_daily_state()
