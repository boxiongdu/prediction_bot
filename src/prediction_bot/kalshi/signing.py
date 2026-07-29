"""Kalshi RSA-PSS request signing.

Provides the cryptographic signing core required for authenticated
Kalshi API requests. Never logs keys, signatures, or private-key contents.

The sign_request function is a verbatim implementation of Kalshi's
prescribed signing algorithm. Do not alter the RSA-PSS parameters.
"""

from __future__ import annotations

import base64
import time
from pathlib import Path
from urllib.parse import urlparse

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa


def sign_request(
    private_key: rsa.RSAPrivateKey,
    timestamp: str,
    method: str,
    path: str,
) -> str:
    """Sign a Kalshi API request using RSA-PSS.

    Verbatim implementation of the Kalshi-provided signing algorithm.
    Do not alter the RSA-PSS parameters.

    Args:
        private_key: An RSA private key loaded with load_pem_private_key.
        timestamp: Millisecond Unix timestamp as a string.
        method: Uppercase HTTP method (GET, POST, etc.).
        path: Full request path including /trade-api/v2. May include
            query parameters; they are stripped before signing.

    Returns:
        Base64-encoded RSA-PSS signature string.
    """
    # Strip query parameters from path before signing
    path_without_query = path.split("?")[0]

    # Create the message to sign
    message = f"{timestamp}{method}{path_without_query}".encode()

    # Sign with RSA-PSS
    signature = private_key.sign(
        message,
        padding.PSS(
            mgf=padding.MGF1(hashes.SHA256()),
            salt_length=padding.PSS.DIGEST_LENGTH,
        ),
        hashes.SHA256(),
    )

    # Return base64 encoded
    return base64.b64encode(signature).decode("utf-8")


def load_private_key(source: str | Path | bytes) -> rsa.RSAPrivateKey:
    """Load an RSA private key from a PEM file path or raw PEM bytes.

    Args:
        source: Path to a PEM file, or raw PEM bytes.

    Returns:
        An RSAPrivateKey ready for use with sign_request.
    """
    if isinstance(source, bytes):
        pem_data = source
    elif isinstance(source, Path):
        pem_data = source.read_bytes()
    elif isinstance(source, str):
        if source.strip().startswith("-----BEGIN"):
            pem_data = source.encode("utf-8")
        else:
            pem_data = Path(source).read_bytes()
    else:
        raise TypeError(f"Expected str, Path, or bytes, got {type(source).__name__}")

    private_key = serialization.load_pem_private_key(pem_data, password=None)
    if not isinstance(private_key, rsa.RSAPrivateKey):
        raise TypeError(f"Expected RSA private key, got {type(private_key).__name__}")
    return private_key


def build_signing_path(base_url: str, endpoint: str) -> str:
    """Build the path to sign from a base URL and endpoint.

    Constructs the complete URL, then extracts urlparse(complete_url).path.
    This is the ONLY correct way to build the signing path — it must
    match exactly what Kalshi expects.

    Query parameters are excluded because sign_request strips them.

    Args:
        base_url: Kalshi API base URL (e.g. https://external-api.kalshi.com/trade-api/v2).
        endpoint: Request endpoint (e.g. /markets or /markets/TICKER/order_book).

    Returns:
        Signed path string (/trade-api/v2/markets), no query params.
    """
    # Build the complete URL to extract the exact path
    complete_url = base_url.rstrip("/") + endpoint
    parsed = urlparse(complete_url)
    return parsed.path


def generate_auth_headers(
    key_id: str,
    private_key: rsa.RSAPrivateKey,
    method: str,
    path: str,
) -> dict[str, str]:
    """Generate Kalshi RSA authentication headers for a single request.

    Args:
        key_id: Kalshi access key ID (starts with 'KK-').
        private_key: RSA private key from load_private_key.
        method: HTTP method (will be uppercased).
        path: Signed path from build_signing_path, including /trade-api/v2.

    Returns:
        Dict with headers: KALSHI-ACCESS-KEY, KALSHI-ACCESS-TIMESTAMP,
        KALSHI-ACCESS-SIGNATURE.
    """
    timestamp_ms = str(int(time.time() * 1000))
    method_upper = method.upper()
    signature = sign_request(private_key, timestamp_ms, method_upper, path)

    return {
        "KALSHI-ACCESS-KEY": key_id,
        "KALSHI-ACCESS-TIMESTAMP": timestamp_ms,
        "KALSHI-ACCESS-SIGNATURE": signature,
    }


# ---------------------------------------------------------------------------
# Backward-compatible alias for existing callers
# ---------------------------------------------------------------------------

def _build_signing_path(base_url: str, path: str, params: dict | None = None) -> str:
    """Deprecated alias — use build_signing_path(base_url, endpoint) instead.

    Kept for backward compatibility with existing callers that pass params.
    Query parameters are ignored (sign_request strips them anyway).
    """
    return build_signing_path(base_url, path)
