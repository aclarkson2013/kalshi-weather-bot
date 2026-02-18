"""Tests for Kalshi RSA authentication and request signing.

Uses the rsa_key_pair fixture from conftest.py to generate a fresh
RSA key pair. Verifies that KalshiAuth correctly loads keys, signs
requests, and produces valid authentication headers.
"""

from __future__ import annotations

import base64

import pytest

from backend.kalshi.auth import KalshiAuth
from backend.kalshi.exceptions import KalshiAuthError


class TestKalshiAuthInit:
    """Tests for KalshiAuth initialization."""

    def test_initializes_with_valid_rsa_key(self, rsa_key_pair) -> None:
        """KalshiAuth initializes successfully with a valid PEM key from fixture."""
        auth = KalshiAuth(
            api_key_id=rsa_key_pair["api_key_id"],
            private_key_pem=rsa_key_pair["private_key_pem"],
        )
        assert auth.api_key_id == rsa_key_pair["api_key_id"]
        assert auth.private_key is not None

    def test_raises_kalshi_auth_error_for_invalid_pem(self) -> None:
        """KalshiAuth raises KalshiAuthError for invalid PEM data."""
        with pytest.raises(KalshiAuthError, match="Invalid RSA private key"):
            KalshiAuth(
                api_key_id="test-key-12345678",
                private_key_pem="this-is-not-a-valid-pem-key",
            )


class TestSignRequest:
    """Tests for KalshiAuth.sign_request header generation."""

    def test_returns_all_4_required_headers(self, kalshi_auth) -> None:
        """sign_request returns all 4 required Kalshi auth headers."""
        headers = kalshi_auth.sign_request("GET", "/trade-api/v2/portfolio/balance")

        assert "KALSHI-ACCESS-KEY" in headers
        assert "KALSHI-ACCESS-SIGNATURE" in headers
        assert "KALSHI-ACCESS-TIMESTAMP" in headers
        assert "Content-Type" in headers
        assert headers["Content-Type"] == "application/json"

    def test_signature_is_base64_encoded(self, kalshi_auth) -> None:
        """KALSHI-ACCESS-SIGNATURE is valid base64-encoded data."""
        headers = kalshi_auth.sign_request("GET", "/trade-api/v2/markets")

        sig = headers["KALSHI-ACCESS-SIGNATURE"]
        decoded = base64.b64decode(sig)
        assert len(decoded) > 0

    def test_timestamp_is_in_milliseconds(self, kalshi_auth) -> None:
        """KALSHI-ACCESS-TIMESTAMP is greater than 1_000_000_000_000 (milliseconds)."""
        headers = kalshi_auth.sign_request("GET", "/trade-api/v2/markets")

        ts = int(headers["KALSHI-ACCESS-TIMESTAMP"])
        assert ts > 1_000_000_000_000, (
            f"Timestamp {ts} should be in milliseconds (> 1_000_000_000_000)"
        )

    def test_method_is_uppercased_in_signing_string(self, kalshi_auth) -> None:
        """Lowercase and uppercase method produce identical signatures (uppercased internally)."""
        ts = 1700000000000
        path = "/trade-api/v2/markets"

        headers_lower = kalshi_auth.sign_request("get", path, timestamp_ms=ts)
        headers_upper = kalshi_auth.sign_request("GET", path, timestamp_ms=ts)

        assert headers_lower["KALSHI-ACCESS-SIGNATURE"] == headers_upper["KALSHI-ACCESS-SIGNATURE"]

    def test_with_explicit_timestamp_ms_uses_that_value(self, kalshi_auth) -> None:
        """Providing timestamp_ms uses that exact value in the header."""
        custom_ts = 1700000000000
        headers = kalshi_auth.sign_request("GET", "/trade-api/v2/markets", timestamp_ms=custom_ts)

        assert headers["KALSHI-ACCESS-TIMESTAMP"] == str(custom_ts)

    def test_different_paths_produce_different_signatures(self, kalshi_auth) -> None:
        """Same method on different paths produces different signatures."""
        ts = 1700000000000

        headers_a = kalshi_auth.sign_request("GET", "/trade-api/v2/markets", timestamp_ms=ts)
        headers_b = kalshi_auth.sign_request("GET", "/trade-api/v2/events", timestamp_ms=ts)

        assert headers_a["KALSHI-ACCESS-SIGNATURE"] != headers_b["KALSHI-ACCESS-SIGNATURE"]
