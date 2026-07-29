"""Read-only Kalshi API client.

No order submission. No real-money operations.
Implements public endpoints for market discovery, order book retrieval,
and market listing.

Authentication is optional — the client supports:
- Unauthenticated access (public endpoints).
- Bearer token (legacy API key).
- RSA-PSS signed requests (Kalshi recommended auth).

RSA private keys and signatures are never logged.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any
from urllib.parse import urlparse

import httpx
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from prediction_bot.config.settings import get_settings
from prediction_bot.data.schema import (
    KalshiMarket,
    KalshiOrderBookSnapshot,
)
from prediction_bot.kalshi.signing import (
    build_signing_path,
    generate_auth_headers,
    load_private_key,
)

logger = logging.getLogger(__name__)

# Kalshi API rate limit: approximately 100 requests per minute.
# We use a conservative internal rate limiter at the configured rate.
DEFAULT_CALLS_PER_SECOND = 5.0


class KalshiRateLimiter:
    """Simple token-bucket-style rate limiter."""

    def __init__(self, calls_per_second: float = DEFAULT_CALLS_PER_SECOND) -> None:
        self._min_interval = 1.0 / calls_per_second if calls_per_second > 0 else 0.0
        self._last_call: float = 0.0

    def wait(self) -> None:
        """Block until the next call is permitted."""
        now = time.monotonic()
        elapsed = now - self._last_call
        if elapsed < self._min_interval:
            time.sleep(self._min_interval - elapsed)
        self._last_call = time.monotonic()


class KalshiClient:
    """Read-only client for the Kalshi trading API.

    This client never submits orders. It only reads public market data.

    Auth priority: RSA signing > Bearer token > unauthenticated.
    """

    BASE_URL = "https://external-api.kalshi.com/trade-api/v2"

    def __init__(
        self,
        api_key: str | None = None,
        key_id: str | None = None,
        private_key: Any = None,
        base_url: str | None = None,
        timeout: int = 30,
        max_retries: int = 3,
        rate_limit_cps: float = DEFAULT_CALLS_PER_SECOND,
    ) -> None:
        settings = get_settings()
        self._api_key = api_key if api_key is not None else (settings.kalshi_api_key or None)
        self._base_url = base_url or settings.kalshi_base_url or self.BASE_URL
        self._timeout = timeout or settings.http_timeout
        self._max_retries = max_retries or settings.http_max_retries
        self._rate_limiter = KalshiRateLimiter(
            rate_limit_cps or settings.http_rate_limit_calls_per_second
        )
        self._client: httpx.Client | None = None

        # RSA signing credentials (optional)
        self._rsa_key_id: str | None = None
        self._rsa_private_key: Any = None

        if key_id and private_key is not None:
            self._rsa_key_id = key_id
            self._rsa_private_key = private_key
        elif settings.kalshi_key_id and settings.kalshi_private_key_path:
            self._rsa_key_id = settings.kalshi_key_id
            self._rsa_private_key = load_private_key(settings.kalshi_private_key_path)

    @property
    def _httpx_client(self) -> httpx.Client:
        if self._client is None:
            headers: dict[str, str] = {
                "Accept": "application/json",
                "User-Agent": "prediction-bot/0.1.0 (research; paper-only)",
            }
            if self._api_key and not self._rsa_private_key:
                headers["Authorization"] = f"Bearer {self._api_key}"
            self._client = httpx.Client(
                base_url=self._base_url,
                headers=headers,
                timeout=httpx.Timeout(self._timeout),
                http2=False,  # Kalshi API breaks with HTTP/2 on query params
            )
        return self._client

    def close(self) -> None:
        """Close the underlying HTTP client."""
        if self._client is not None:
            self._client.close()
            self._client = None

    def __enter__(self) -> KalshiClient:
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_auth_headers(self, method: str, path: str) -> dict[str, str]:
        """Build authentication headers for the current request.

        When RSA credentials are available, generates fresh KALSHI-ACCESS-*
        headers. The signed path is built from the complete request URL:
        urlparse(base_url + endpoint).path — no query parameters.

        Returns an empty dict when RSA auth is not configured.
        """
        if not self._rsa_key_id or self._rsa_private_key is None:
            return {}

        signed_path = build_signing_path(self._base_url, path)
        return generate_auth_headers(
            key_id=self._rsa_key_id,
            private_key=self._rsa_private_key,
            method=method,
            path=signed_path,
        )

    def _request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        """Make a rate-limited HTTP request with retries.

        RSA auth headers and debug logging are computed fresh on every
        attempt so that retries carry a new timestamp and signature.
        """
        self._rate_limiter.wait()

        # Build the complete URL for debug logging (not for signing —
        # signing uses urlparse(complete_url).path only)
        complete_url = self._base_url.rstrip("/") + path
        parsed = urlparse(complete_url)

        @retry(
            stop=stop_after_attempt(self._max_retries),
            wait=wait_exponential(multiplier=1, min=1, max=10),
            retry=retry_if_exception_type(
                (httpx.TimeoutException, httpx.NetworkError, httpx.RemoteProtocolError)
            ),
            reraise=True,
        )
        def _do_request() -> httpx.Response:
            # --- fresh auth headers on every attempt ---
            auth_headers = self._build_auth_headers(method, path)
            headers = dict(kwargs.get("headers", {}))
            if auth_headers:
                headers.update(auth_headers)

            # --- safe debug logging (no header values) ---
            signed_path = build_signing_path(self._base_url, path)
            logger.debug(
                "Kalshi request: %s %s (signed_path=%s, host=%s, "
                "has_key=%s, has_ts=%s, has_sig=%s)",
                method.upper(),
                complete_url,
                signed_path,
                parsed.hostname,
                bool(auth_headers.get("KALSHI-ACCESS-KEY") if auth_headers else False),
                bool(auth_headers.get("KALSHI-ACCESS-TIMESTAMP") if auth_headers else False),
                bool(auth_headers.get("KALSHI-ACCESS-SIGNATURE") if auth_headers else False),
            )

            try:
                response = self._httpx_client.request(
                    method, path, headers=headers, **{
                        k: v for k, v in kwargs.items() if k != "headers"
                    },
                )
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 429:
                    retry_after = e.response.headers.get("Retry-After")
                    wait_seconds = int(retry_after) if retry_after else 5
                    logger.warning("Rate limited (429). Waiting %ds.", wait_seconds)
                    time.sleep(wait_seconds)
                    raise
                if 400 <= e.response.status_code < 500:
                    logger.error(
                        "Client error %d for %s %s", e.response.status_code, method, path,
                    )
                    raise
                raise
            return response

        response = _do_request()
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError:
            logger.error(
                "HTTP %d from %s %s: %s",
                response.status_code, method, complete_url, response.text[:500],
            )
            raise
        return response

    def _parse_iso_datetime(self, value: str | None) -> datetime | None:
        """Parse an ISO 8601 datetime string into a timezone-aware UTC datetime.

        Returns None if the input is None or unparseable.
        """
        if not value:
            return None
        try:
            # Handle 'Z' suffix and timezone offsets
            normalized = value.replace("Z", "+00:00")
            dt = datetime.fromisoformat(normalized)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except (ValueError, TypeError):
            logger.debug("Could not parse datetime: %s", value)
            return None

    # ------------------------------------------------------------------
    # Public API: Markets
    # ------------------------------------------------------------------

    def get_markets(
        self,
        status: str = "open",
        limit: int = 500,
        cursor: str | None = None,
        event_ticker: str | None = None,
        series_ticker: str | None = None,
        max_close_ts: int | None = None,
        min_close_ts: int | None = None,
        mve_filter: str | None = None,
    ) -> dict[str, Any]:
        """Retrieve a list of markets.

        Args:
            status: Filter by market status (open, closed, settled).
            limit: Maximum number of markets to return per page.
            cursor: Pagination cursor for fetching next page.
            event_ticker: Filter to a specific event.
            series_ticker: Filter to a specific series.
            max_close_ts: Maximum close timestamp (Unix seconds).
            min_close_ts: Minimum close timestamp (Unix seconds).
            mve_filter: 'exclude' to remove multi-event (parlay) products.
                Use this to get only simple single-outcome markets.

        Returns:
            Raw API response dict with 'markets' and optional 'cursor' keys.
        """
        params: dict[str, Any] = {
            "status": status,
            "limit": limit,
        }
        if cursor:
            params["cursor"] = cursor
        if event_ticker:
            params["event_ticker"] = event_ticker
        if series_ticker:
            params["series_ticker"] = series_ticker
        if max_close_ts is not None:
            params["max_close_ts"] = max_close_ts
        if min_close_ts is not None:
            params["min_close_ts"] = min_close_ts
        if mve_filter is not None:
            params["mve_filter"] = mve_filter

        response = self._request("GET", "/markets", params=params)
        return response.json()

    def get_markets_paginated(
        self,
        status: str = "open",
        max_pages: int = 5,
        **kwargs: Any,
    ) -> list[dict[str, Any]]:
        """Retrieve markets across multiple pages.

        Args:
            status: Market status filter.
            max_pages: Maximum number of pages to fetch.
            **kwargs: Additional filters passed to get_markets.

        Returns:
            Flat list of market dicts from all pages.
        """
        all_markets: list[dict[str, Any]] = []
        cursor: str | None = None

        for _ in range(max_pages):
            page = self.get_markets(status=status, cursor=cursor, **kwargs)
            markets = page.get("markets", [])
            all_markets.extend(markets)
            cursor = page.get("cursor")
            if not cursor or not markets:
                break

        return all_markets

    def parse_market(self, raw: dict[str, Any]) -> KalshiMarket:
        """Convert a raw Kalshi market dict into a KalshiMarket schema.

        Prefer new API *_dollars fields (already in 0-1 probability space).
        Fall back to old cent-based fields, dividing by 100 when > 1.
        Prefer *_fp quantity fields, falling back to old integer fields.
        """
        from prediction_bot.data.schema import (
            _parse_fp_quantity,
            _parse_price_cents,
            _parse_price_dollars,
        )

        # Prices: prefer *_dollars, fall back to old cent fields
        yes_bid = _parse_price_dollars(raw.get("yes_bid_dollars"))
        if yes_bid is None:
            yes_bid = _parse_price_cents(raw.get("yes_bid"))

        yes_ask = _parse_price_dollars(raw.get("yes_ask_dollars"))
        if yes_ask is None:
            yes_ask = _parse_price_cents(raw.get("yes_ask"))

        no_bid = _parse_price_dollars(raw.get("no_bid_dollars"))
        if no_bid is None:
            no_bid = _parse_price_cents(raw.get("no_bid"))

        no_ask = _parse_price_dollars(raw.get("no_ask_dollars"))
        if no_ask is None:
            no_ask = _parse_price_cents(raw.get("no_ask"))

        last_price = _parse_price_dollars(raw.get("last_price_dollars"))
        if last_price is None:
            last_price = _parse_price_cents(raw.get("last_price"))

        # Quantities: prefer *_fp, fall back to old fields
        volume = _parse_fp_quantity(raw.get("volume_fp"))
        if volume is None:
            old_vol = raw.get("volume")
            volume = Decimal(str(old_vol)) if old_vol is not None else None

        volume_24h = _parse_fp_quantity(raw.get("volume_24h_fp"))

        open_interest = _parse_fp_quantity(raw.get("open_interest_fp"))
        if open_interest is None:
            old_oi = raw.get("open_interest")
            open_interest = Decimal(str(old_oi)) if old_oi is not None else None

        yes_bid_size = _parse_fp_quantity(raw.get("yes_bid_size_fp"))
        yes_ask_size = _parse_fp_quantity(raw.get("yes_ask_size_fp"))

        # Liquidity
        liquidity = _parse_price_dollars(raw.get("liquidity_dollars"))
        if liquidity is None:
            raw_liq = raw.get("liquidity")
            liquidity = Decimal(str(raw_liq)) if raw_liq is not None else None

        return KalshiMarket(
            ticker=raw.get("ticker", ""),
            event_ticker=raw.get("event_ticker", ""),
            title=raw.get("title", ""),
            subtitle=raw.get("subtitle"),
            yes_sub_title=raw.get("yes_sub_title"),
            no_sub_title=raw.get("no_sub_title"),
            category=raw.get("category"),
            rules_primary=raw.get("rules_primary"),
            close_time=self._parse_iso_datetime(raw.get("close_time")),
            status=raw.get("status"),
            yes_bid=yes_bid,
            yes_ask=yes_ask,
            no_bid=no_bid,
            no_ask=no_ask,
            last_price=last_price,
            volume=volume,
            volume_24h=volume_24h,
            open_interest=open_interest,
            yes_bid_size=yes_bid_size,
            yes_ask_size=yes_ask_size,
            liquidity=liquidity,
        )

    # ------------------------------------------------------------------
    # Public API: Order Book
    # ------------------------------------------------------------------

    def get_order_book(self, ticker: str, depth: int = 10) -> dict[str, Any]:
        """Retrieve the order book for a specific market.

        Args:
            ticker: The market ticker symbol.
            depth: Order book depth to retrieve.

        Returns:
            Raw API response dict with 'order_book' key.
        """
        response = self._request(
            "GET", f"/markets/{ticker}/order_book", params={"depth": str(depth)}
        )
        return response.json()

    def get_order_book_snapshot(self, ticker: str, depth: int = 10) -> KalshiOrderBookSnapshot:
        """Retrieve and parse the order book into a typed snapshot.

        Args:
            ticker: The market ticker symbol.
            depth: Order book depth.

        Returns:
            Parsed KalshiOrderBookSnapshot.
        """
        raw = self.get_order_book(ticker, depth=depth)
        ob = raw.get("order_book", raw)

        yes_bids = ob.get("yes_bids", [])
        yes_asks = ob.get("yes_asks", [])

        best_bid: Decimal | None = None
        best_ask: Decimal | None = None
        bid_depth: Decimal | None = None
        ask_depth: Decimal | None = None

        if yes_bids:
            best = yes_bids[0]
            best_bid = Decimal(str(best.get("price", 0)))
            bid_depth = Decimal(str(best.get("count", 0)))

        if yes_asks:
            best = yes_asks[0]
            best_ask = Decimal(str(best.get("price", 0)))
            ask_depth = Decimal(str(best.get("count", 0)))

        return KalshiOrderBookSnapshot(
            market_ticker=ticker,
            captured_at=datetime.now(timezone.utc),
            best_bid=best_bid,
            best_ask=best_ask,
            bid_depth=bid_depth,
            ask_depth=ask_depth,
            last_price=raw.get("last_price"),
        )

    # ------------------------------------------------------------------
    # Public API: Events
    # ------------------------------------------------------------------

    def get_events(
        self,
        status: str = "open",
        limit: int = 100,
        cursor: str | None = None,
        series_ticker: str | None = None,
    ) -> dict[str, Any]:
        """Retrieve a list of events.

        Args:
            status: Filter by event status.
            limit: Maximum number of events per page.
            cursor: Pagination cursor.
            series_ticker: Filter to a specific series.

        Returns:
            Raw API response dict with 'events' key.
        """
        params: dict[str, Any] = {
            "status": status,
            "limit": limit,
        }
        if cursor:
            params["cursor"] = cursor
        if series_ticker:
            params["series_ticker"] = series_ticker

        response = self._request("GET", "/events", params=params)
        return response.json()
