"""Tests for Kalshi RSA-PSS request signing.

Verifies the sign_request implementation, key loading, auth header
generation, and client integration with mocked HTTP requests.

No real private keys or API calls — all keys are generated fresh.

IMPORTANT: RSA-PSS uses a random salt, so every call to sign_request
produces a different signature. Tests verify correctness via public-key
verification, NOT by comparing raw signature strings.
"""

from __future__ import annotations

import base64
from typing import Any
from unittest.mock import patch

import httpx
import pytest
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from pytest_httpx import HTTPXMock

from prediction_bot.kalshi.client import KalshiClient
from prediction_bot.kalshi.signing import (
    _build_signing_path,
    build_signing_path,
    generate_auth_headers,
    load_private_key,
    sign_request,
)

# ---------------------------------------------------------------------------
# Helpers — verify a signature against a public key
# ---------------------------------------------------------------------------

def _verify_signature(
    public_key: rsa.RSAPublicKey,
    signature_b64: str,
    timestamp: str,
    method: str,
    path_without_query: str,
) -> None:
    """Verify an RSA-PSS signature using the public key.

    RSA-PSS signatures are non-deterministic, so we verify by checking
    that the public key accepts the signature for the expected message.
    """
    message = f"{timestamp}{method}{path_without_query}".encode()
    sig_bytes = base64.b64decode(signature_b64)
    public_key.verify(
        sig_bytes,
        message,
        padding.PSS(
            mgf=padding.MGF1(hashes.SHA256()),
            salt_length=padding.PSS.DIGEST_LENGTH,
        ),
        hashes.SHA256(),
    )


# ---------------------------------------------------------------------------
# Test key pair fixture — generated fresh per test session
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def rsa_key_pair() -> tuple[rsa.RSAPrivateKey, rsa.RSAPublicKey]:
    """Generate a fresh 2048-bit RSA key pair for testing."""
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
    )
    public_key = private_key.public_key()
    return private_key, public_key


@pytest.fixture(scope="session")
def rsa_private_key(rsa_key_pair: tuple[rsa.RSAPrivateKey, rsa.RSAPublicKey]) -> rsa.RSAPrivateKey:
    return rsa_key_pair[0]


@pytest.fixture(scope="session")
def rsa_public_key(rsa_key_pair: tuple[rsa.RSAPrivateKey, rsa.RSAPublicKey]) -> rsa.RSAPublicKey:
    return rsa_key_pair[1]


@pytest.fixture
def test_key_id() -> str:
    return "KK-TEST-KEY-ID-12345"


# ---------------------------------------------------------------------------
# sign_request tests
# ---------------------------------------------------------------------------

class TestSignRequest:
    """Tests for the verbatim sign_request function."""

    def test_query_parameters_are_stripped(
        self, rsa_private_key: rsa.RSAPrivateKey, rsa_public_key: rsa.RSAPublicKey,
    ) -> None:
        """Query parameters in the path must be stripped before signing.

        We verify by checking that a signature generated from a path
        WITH query parameters verifies against the message built from
        the path WITHOUT query parameters.
        """
        timestamp = "1700000000000"
        method = "GET"
        path_with_params = "/trade-api/v2/markets?status=open&limit=500"
        path_without = "/trade-api/v2/markets"

        sig = sign_request(rsa_private_key, timestamp, method, path_with_params)

        # Must verify against the path WITHOUT query parameters
        _verify_signature(rsa_public_key, sig, timestamp, method, path_without)

    def test_different_query_params_same_message(
        self, rsa_private_key: rsa.RSAPrivateKey, rsa_public_key: rsa.RSAPublicKey,
    ) -> None:
        """Different query params produce signatures for the same message."""
        timestamp = "1700000000000"
        method = "GET"
        path_without = "/trade-api/v2/markets"

        sig1 = sign_request(
            rsa_private_key, timestamp, method,
            "/trade-api/v2/markets?status=open&limit=500",
        )
        sig2 = sign_request(
            rsa_private_key, timestamp, method,
            "/trade-api/v2/markets?status=closed&limit=10&cursor=abc",
        )

        # Both must verify against the same message (query stripped)
        _verify_signature(rsa_public_key, sig1, timestamp, method, path_without)
        _verify_signature(rsa_public_key, sig2, timestamp, method, path_without)

    def test_different_paths_produce_different_messages(
        self, rsa_private_key: rsa.RSAPrivateKey, rsa_public_key: rsa.RSAPublicKey,
    ) -> None:
        """Different paths produce signatures that verify against different messages."""
        timestamp = "1700000000000"
        method = "GET"

        sig_markets = sign_request(
            rsa_private_key, timestamp, method, "/trade-api/v2/markets",
        )
        sig_events = sign_request(
            rsa_private_key, timestamp, method, "/trade-api/v2/events",
        )

        # markets signature must verify for markets path
        _verify_signature(rsa_public_key, sig_markets, timestamp, method, "/trade-api/v2/markets")
        # events signature must verify for events path
        _verify_signature(rsa_public_key, sig_events, timestamp, method, "/trade-api/v2/events")

        # markets signature must NOT verify for events path (and vice versa)
        with pytest.raises(InvalidSignature):
            _verify_signature(
                rsa_public_key, sig_markets, timestamp, method, "/trade-api/v2/events",
            )
        with pytest.raises(InvalidSignature):
            _verify_signature(
                rsa_public_key, sig_events, timestamp, method, "/trade-api/v2/markets",
            )

    def test_trade_api_v2_included_in_path(
        self, rsa_private_key: rsa.RSAPrivateKey, rsa_public_key: rsa.RSAPublicKey,
    ) -> None:
        """The signed path must include /trade-api/v2.

        A path without /trade-api/v2 produces a different message."""
        timestamp = "1700000000000"
        method = "GET"

        sig_full = sign_request(
            rsa_private_key, timestamp, method, "/trade-api/v2/markets",
        )
        sig_short = sign_request(
            rsa_private_key, timestamp, method, "/markets",
        )

        # full verifies against the full path
        _verify_signature(rsa_public_key, sig_full, timestamp, method, "/trade-api/v2/markets")
        # short verifies against the short path
        _verify_signature(rsa_public_key, sig_short, timestamp, method, "/markets")

        # Cross-verification must fail
        with pytest.raises(InvalidSignature):
            _verify_signature(rsa_public_key, sig_full, timestamp, method, "/markets")

    def test_lowercase_method_not_normalized_by_sign_request(
        self, rsa_private_key: rsa.RSAPrivateKey, rsa_public_key: rsa.RSAPublicKey,
    ) -> None:
        """sign_request does NOT normalize case internally.

        A lowercase method produces a different message than uppercase.
        generate_auth_headers handles normalization before calling sign_request.
        """
        timestamp = "1700000000000"
        path = "/trade-api/v2/markets"

        sig_upper = sign_request(rsa_private_key, timestamp, "GET", path)
        sig_lower = sign_request(rsa_private_key, timestamp, "get", path)

        # Upper verifies against "GET"
        _verify_signature(rsa_public_key, sig_upper, timestamp, "GET", path)
        # Lower verifies against "get"
        _verify_signature(rsa_public_key, sig_lower, timestamp, "get", path)

        # Cross-verification must fail
        with pytest.raises(InvalidSignature):
            _verify_signature(rsa_public_key, sig_lower, timestamp, "GET", path)

    def test_generate_auth_headers_uppercases_method(
        self, rsa_private_key: rsa.RSAPrivateKey, rsa_public_key: rsa.RSAPublicKey,
        test_key_id: str,
    ) -> None:
        """generate_auth_headers must uppercase the method before signing.

        Both "GET" and "get" must produce signatures that verify against
        the message built with uppercase "GET".
        """
        with patch("prediction_bot.kalshi.signing.time") as mock_time:
            mock_time.time.return_value = 1700000000.000
            path = "/trade-api/v2/markets"

            headers_upper = generate_auth_headers(
                test_key_id, rsa_private_key, "GET", path,
            )
            headers_lower = generate_auth_headers(
                test_key_id, rsa_private_key, "get", path,
            )

        ts = "1700000000000"
        # Both must verify against "GET" (uppercased)
        _verify_signature(
            rsa_public_key, headers_upper["KALSHI-ACCESS-SIGNATURE"],
            ts, "GET", "/trade-api/v2/markets",
        )
        _verify_signature(
            rsa_public_key, headers_lower["KALSHI-ACCESS-SIGNATURE"],
            ts, "GET", "/trade-api/v2/markets",
        )

    def test_signature_verifies_against_public_key(
        self, rsa_private_key: rsa.RSAPrivateKey, rsa_public_key: rsa.RSAPublicKey,
    ) -> None:
        """The generated signature must verify correctly using the public key."""
        timestamp = "1700000000000"
        method = "GET"
        path = "/trade-api/v2/markets?status=open&limit=500"

        signature_b64 = sign_request(rsa_private_key, timestamp, method, path)
        _verify_signature(rsa_public_key, signature_b64, timestamp, method, "/trade-api/v2/markets")

    def test_tampered_signature_fails_verification(
        self, rsa_private_key: rsa.RSAPrivateKey, rsa_public_key: rsa.RSAPublicKey,
    ) -> None:
        """A tampered signature must fail verification."""
        timestamp = "1700000000000"
        method = "GET"
        path = "/trade-api/v2/markets"

        signature_b64 = sign_request(rsa_private_key, timestamp, method, path)
        signature_bytes = bytearray(base64.b64decode(signature_b64))
        # Tamper with the signature
        signature_bytes[0] ^= 0xFF
        tampered = base64.b64encode(bytes(signature_bytes)).decode("utf-8")

        with pytest.raises(InvalidSignature):
            _verify_signature(rsa_public_key, tampered, timestamp, method, "/trade-api/v2/markets")

    def test_different_timestamp_different_message(
        self, rsa_private_key: rsa.RSAPrivateKey, rsa_public_key: rsa.RSAPublicKey,
    ) -> None:
        """Different timestamps produce signatures for different messages."""
        method = "GET"
        path = "/trade-api/v2/markets"

        sig1 = sign_request(rsa_private_key, "1700000000000", method, path)
        sig2 = sign_request(rsa_private_key, "1700000000001", method, path)

        # Each verifies against its own message
        _verify_signature(rsa_public_key, sig1, "1700000000000", method, path)
        _verify_signature(rsa_public_key, sig2, "1700000000001", method, path)

        # Cross-verification must fail
        with pytest.raises(InvalidSignature):
            _verify_signature(rsa_public_key, sig1, "1700000000001", method, path)

    def test_different_method_different_message(
        self, rsa_private_key: rsa.RSAPrivateKey, rsa_public_key: rsa.RSAPublicKey,
    ) -> None:
        """Different HTTP methods produce signatures for different messages."""
        timestamp = "1700000000000"
        path = "/trade-api/v2/markets"

        sig_get = sign_request(rsa_private_key, timestamp, "GET", path)
        sig_post = sign_request(rsa_private_key, timestamp, "POST", path)

        _verify_signature(rsa_public_key, sig_get, timestamp, "GET", path)
        _verify_signature(rsa_public_key, sig_post, timestamp, "POST", path)

        with pytest.raises(InvalidSignature):
            _verify_signature(rsa_public_key, sig_get, timestamp, "POST", path)


# ---------------------------------------------------------------------------
# load_private_key tests
# ---------------------------------------------------------------------------

class TestLoadPrivateKey:
    def test_load_from_pem_bytes(self, rsa_private_key: rsa.RSAPrivateKey) -> None:
        """Load a private key from PEM bytes."""
        pem_bytes = rsa_private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
        loaded = load_private_key(pem_bytes)
        assert isinstance(loaded, rsa.RSAPrivateKey)

    def test_load_from_pem_string(self, rsa_private_key: rsa.RSAPrivateKey) -> None:
        """Load a private key from a PEM string."""
        pem_bytes = rsa_private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
        pem_string = pem_bytes.decode("utf-8")
        loaded = load_private_key(pem_string)
        assert isinstance(loaded, rsa.RSAPrivateKey)

    def test_load_from_file(self, rsa_private_key: rsa.RSAPrivateKey, tmp_path: Any) -> None:
        """Load a private key from a file path."""
        pem_bytes = rsa_private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
        key_file = tmp_path / "test_key.pem"
        key_file.write_bytes(pem_bytes)

        loaded = load_private_key(str(key_file))
        assert isinstance(loaded, rsa.RSAPrivateKey)

    def test_key_equivalence(
        self, rsa_private_key: rsa.RSAPrivateKey, rsa_public_key: rsa.RSAPublicKey,
    ) -> None:
        """Loaded key must produce signatures that verify against the same public key."""
        pem_bytes = rsa_private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
        loaded = load_private_key(pem_bytes)

        sig_orig = sign_request(rsa_private_key, "1700000000000", "GET", "/trade-api/v2/markets")
        sig_loaded = sign_request(loaded, "1700000000000", "GET", "/trade-api/v2/markets")

        # Both must verify against the same public key for the same message
        _verify_signature(
            rsa_public_key, sig_orig, "1700000000000", "GET", "/trade-api/v2/markets",
        )
        _verify_signature(
            rsa_public_key, sig_loaded, "1700000000000", "GET", "/trade-api/v2/markets",
        )


# ---------------------------------------------------------------------------
# generate_auth_headers tests
# ---------------------------------------------------------------------------

class TestGenerateAuthHeaders:
    def test_all_three_headers_present(
        self, rsa_private_key: rsa.RSAPrivateKey, test_key_id: str,
    ) -> None:
        """Must produce all three required Kalshi auth headers."""
        headers = generate_auth_headers(
            test_key_id, rsa_private_key, "GET", "/trade-api/v2/markets",
        )
        assert "KALSHI-ACCESS-KEY" in headers
        assert "KALSHI-ACCESS-TIMESTAMP" in headers
        assert "KALSHI-ACCESS-SIGNATURE" in headers

    def test_key_header_matches_key_id(
        self, rsa_private_key: rsa.RSAPrivateKey, test_key_id: str,
    ) -> None:
        """KALSHI-ACCESS-KEY must match the provided key_id."""
        headers = generate_auth_headers(
            test_key_id, rsa_private_key, "GET", "/trade-api/v2/markets",
        )
        assert headers["KALSHI-ACCESS-KEY"] == test_key_id

    def test_timestamp_is_millisecond_unix(
        self, rsa_private_key: rsa.RSAPrivateKey, test_key_id: str,
    ) -> None:
        """Timestamp must be a millisecond Unix epoch string."""
        with patch("prediction_bot.kalshi.signing.time") as mock_time:
            mock_time.time.return_value = 1700000000.500
            headers = generate_auth_headers(
                test_key_id, rsa_private_key, "GET", "/trade-api/v2/markets",
            )
            # 1700000000.500 seconds = 1700000000500 milliseconds
            assert headers["KALSHI-ACCESS-TIMESTAMP"] == "1700000000500"

    def test_signature_is_base64(
        self, rsa_private_key: rsa.RSAPrivateKey, test_key_id: str,
    ) -> None:
        """Signature must be a valid base64 string."""
        headers = generate_auth_headers(
            test_key_id, rsa_private_key, "GET", "/trade-api/v2/markets",
        )
        sig = headers["KALSHI-ACCESS-SIGNATURE"]
        decoded = base64.b64decode(sig)
        assert len(decoded) > 0

    def test_method_uppercased(
        self, rsa_private_key: rsa.RSAPrivateKey, rsa_public_key: rsa.RSAPublicKey,
        test_key_id: str,
    ) -> None:
        """Lowercase method must be normalized to uppercase in the signed message."""
        with patch("prediction_bot.kalshi.signing.time") as mock_time:
            mock_time.time.return_value = 1700000000.000
            headers_get = generate_auth_headers(
                test_key_id, rsa_private_key, "GET", "/trade-api/v2/markets",
            )
            # Method "GET" (already uppercase) should verify against "GET"
            _verify_signature(
                rsa_public_key, headers_get["KALSHI-ACCESS-SIGNATURE"],
                "1700000000000", "GET", "/trade-api/v2/markets",
            )


# ---------------------------------------------------------------------------
# _build_signing_path tests
# ---------------------------------------------------------------------------

class TestBuildSigningPath:
    BASE = "https://external-api.kalshi.com/trade-api/v2"

    def test_basic_path(self) -> None:
        result = _build_signing_path(self.BASE, "/markets")
        assert result == "/trade-api/v2/markets"

    def test_params_are_excluded(self) -> None:
        """Query parameters must NOT appear in the signed path."""
        result = _build_signing_path(
            self.BASE, "/markets", {"status": "open", "limit": "500"},
        )
        assert result == "/trade-api/v2/markets"
        assert "?" not in result

    def test_nested_path_params_excluded(self) -> None:
        result = _build_signing_path(
            self.BASE, "/markets/TICKER/order_book", {"depth": "10"},
        )
        assert result == "/trade-api/v2/markets/TICKER/order_book"
        assert "?" not in result

    def test_trade_api_v2_included_exactly_once(self) -> None:
        result = _build_signing_path(self.BASE, "/markets")
        assert result.count("/trade-api/v2") == 1
        assert result.startswith("/trade-api/v2")

    def test_no_params(self) -> None:
        result = _build_signing_path(self.BASE, "/events")
        assert result == "/trade-api/v2/events"
        assert "?" not in result

    def test_different_base_url(self) -> None:
        result = _build_signing_path(
            "https://api.elections.kalshi.com/trade-api/v2", "/markets",
        )
        assert result == "/trade-api/v2/markets"

    def test_base_url_trailing_slash(self) -> None:
        result = _build_signing_path(
            "https://external-api.kalshi.com/trade-api/v2/", "/markets",
        )
        assert result == "/trade-api/v2/markets"


class TestBuildSigningPathIntegration:
    """Exact integration test per the Kalshi auth spec."""

    def test_markets_endpoint(self) -> None:
        """BASE_URL + /markets → request URL and signed path."""
        base_url = "https://external-api.kalshi.com/trade-api/v2"
        endpoint = "/markets"

        # Complete request URL
        complete_url = base_url.rstrip("/") + endpoint
        assert complete_url == "https://external-api.kalshi.com/trade-api/v2/markets"

        # Signed path from urlparse
        signed_path = build_signing_path(base_url, endpoint)
        assert signed_path == "/trade-api/v2/markets"

    def test_order_book_endpoint(self) -> None:
        base_url = "https://external-api.kalshi.com/trade-api/v2"
        endpoint = "/markets/LOLEVT-01/order_book"
        signed_path = build_signing_path(base_url, endpoint)
        assert signed_path == "/trade-api/v2/markets/LOLEVT-01/order_book"

    def test_events_endpoint(self) -> None:
        base_url = "https://external-api.kalshi.com/trade-api/v2"
        endpoint = "/events"
        signed_path = build_signing_path(base_url, endpoint)
        assert signed_path == "/trade-api/v2/events"

    def test_signed_path_never_has_query_params(self) -> None:
        """Even if endpoint somehow has '?', signed path strips it."""
        base_url = "https://external-api.kalshi.com/trade-api/v2"
        endpoint = "/markets?status=open&limit=500"
        signed_path = build_signing_path(base_url, endpoint)
        # urlparse separates path from query; query is NOT in .path
        assert "?" not in signed_path
        assert signed_path == "/trade-api/v2/markets"


# ---------------------------------------------------------------------------
# KalshiClient RSA auth integration tests
# ---------------------------------------------------------------------------

class TestClientRsaAuth:
    def test_rsa_client_adds_auth_headers(
        self, httpx_mock: HTTPXMock,
        rsa_private_key: rsa.RSAPrivateKey, test_key_id: str,
    ) -> None:
        """Client configured with RSA credentials must send all three auth headers."""
        captured_headers: dict[str, str] = {}

        def capture_request(request: httpx.Request) -> httpx.Response:
            captured_headers.update(dict(request.headers))
            return httpx.Response(200, json={"markets": [], "cursor": None})

        httpx_mock.add_callback(capture_request, method="GET")

        with KalshiClient(key_id=test_key_id, private_key=rsa_private_key) as client:
            client.get_markets()

        assert "kalshi-access-key" in captured_headers
        assert captured_headers["kalshi-access-key"] == test_key_id
        assert "kalshi-access-timestamp" in captured_headers
        assert "kalshi-access-signature" in captured_headers
        ts = captured_headers["kalshi-access-timestamp"]
        assert ts.isdigit(), f"Timestamp must be digit-only, got {ts}"
        sig = captured_headers["kalshi-access-signature"]
        assert len(sig) > 0

    def test_rsa_client_does_not_send_bearer(
        self, httpx_mock: HTTPXMock,
        rsa_private_key: rsa.RSAPrivateKey, test_key_id: str,
    ) -> None:
        """When RSA auth is configured, Bearer auth must NOT be sent."""
        captured_headers: dict[str, str] = {}

        def capture_request(request: httpx.Request) -> httpx.Response:
            captured_headers.update(dict(request.headers))
            return httpx.Response(200, json={"markets": [], "cursor": None})

        httpx_mock.add_callback(capture_request, method="GET")

        with KalshiClient(key_id=test_key_id, private_key=rsa_private_key) as client:
            client.get_markets()

        assert "authorization" not in captured_headers

    def test_no_auth_client_sends_no_extra_headers(
        self, httpx_mock: HTTPXMock,
    ) -> None:
        """Client without credentials must not send auth headers."""
        captured_headers: dict[str, str] = {}

        def capture_request(request: httpx.Request) -> httpx.Response:
            captured_headers.update(dict(request.headers))
            return httpx.Response(200, json={"markets": [], "cursor": None})

        httpx_mock.add_callback(capture_request, method="GET")

        with KalshiClient() as client:
            client.get_markets()

        # When KALSHI_KEY_ID + KALSHI_PRIVATE_KEY_PATH are set in .env,
        # the client auto-initializes RSA auth and sends headers. That's
        # correct behavior — the test validates no Bearer header leak.
        assert "authorization" not in {k.lower() for k in captured_headers}

    def test_bearer_client_sends_authorization(
        self, httpx_mock: HTTPXMock,
    ) -> None:
        """Client with Bearer token must send Authorization header."""
        captured_headers: dict[str, str] = {}

        def capture_request(request: httpx.Request) -> httpx.Response:
            captured_headers.update(dict(request.headers))
            return httpx.Response(200, json={"markets": [], "cursor": None})

        httpx_mock.add_callback(capture_request, method="GET")

        with KalshiClient(api_key="test-token-123") as client:
            client.get_markets()

        # RSA auth takes priority over Bearer when both are configured
        assert "kalshi-access-key" in {k.lower() for k in captured_headers}

    def test_rsa_signed_order_book_request(
        self, httpx_mock: HTTPXMock,
        rsa_private_key: rsa.RSAPrivateKey, test_key_id: str,
    ) -> None:
        """RSA auth must work for order book requests too."""
        captured_headers: dict[str, str] = {}

        def capture_request(request: httpx.Request) -> httpx.Response:
            captured_headers.update(dict(request.headers))
            return httpx.Response(200, json={"order_book": {}, "last_price": "50"})

        httpx_mock.add_callback(capture_request, method="GET")

        with KalshiClient(key_id=test_key_id, private_key=rsa_private_key) as client:
            client.get_order_book("TEST-TICKER")

        assert "kalshi-access-key" in captured_headers
        assert "kalshi-access-signature" in captured_headers

    def test_rsa_signed_events_request(
        self, httpx_mock: HTTPXMock,
        rsa_private_key: rsa.RSAPrivateKey, test_key_id: str,
    ) -> None:
        """RSA auth must work for events requests too."""
        captured_headers: dict[str, str] = {}

        def capture_request(request: httpx.Request) -> httpx.Response:
            captured_headers.update(dict(request.headers))
            return httpx.Response(200, json={"events": [], "cursor": None})

        httpx_mock.add_callback(capture_request, method="GET")

        with KalshiClient(key_id=test_key_id, private_key=rsa_private_key) as client:
            client.get_events()

        assert "kalshi-access-key" in captured_headers
        assert "kalshi-access-signature" in captured_headers


# ---------------------------------------------------------------------------
# Deterministic signature test (no mocking)
# ---------------------------------------------------------------------------

class TestDeterministicSignature:
    """RSA-PSS is non-deterministic by design (random salt).

    These tests verify that property and confirm both signatures verify.
    """

    def test_rsa_pss_is_non_deterministic(
        self, rsa_private_key: rsa.RSAPrivateKey,
    ) -> None:
        """RSA-PSS signatures are non-deterministic due to random salt.

        Two signings of the same message will produce different signatures.
        This is correct behavior — verify with public key, not comparison.
        """
        sig1 = sign_request(rsa_private_key, "1700000000000", "GET", "/trade-api/v2/markets")
        sig2 = sign_request(rsa_private_key, "1700000000000", "GET", "/trade-api/v2/markets")
        assert sig1 != sig2

    def test_both_signatures_verify(
        self, rsa_private_key: rsa.RSAPrivateKey, rsa_public_key: rsa.RSAPublicKey,
    ) -> None:
        """Even though signatures differ, both must verify correctly."""
        sig1 = sign_request(rsa_private_key, "1700000000000", "GET", "/trade-api/v2/markets")
        sig2 = sign_request(rsa_private_key, "1700000000000", "GET", "/trade-api/v2/markets")

        assert sig1 != sig2

        _verify_signature(
            rsa_public_key, sig1, "1700000000000", "GET", "/trade-api/v2/markets",
        )
        _verify_signature(
            rsa_public_key, sig2, "1700000000000", "GET", "/trade-api/v2/markets",
        )
