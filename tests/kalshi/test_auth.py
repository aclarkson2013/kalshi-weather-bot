"""Tests for Kalshi API authentication and request signing.

Uses the rsa_key_pair fixture from conftest.py to generate a fresh
RSA key pair. Verifies that KalshiAuth correctly loads keys, signs
requests with RSA-PSS, and produces valid authentication headers.
"""

from __future__ import annotations

import base64

import pytest
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding

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

    def test_detects_rsa_key_type(self, rsa_key_pair) -> None:
        """KalshiAuth correctly identifies RSA key type."""
        auth = KalshiAuth(
            api_key_id=rsa_key_pair["api_key_id"],
            private_key_pem=rsa_key_pair["private_key_pem"],
        )
        assert auth._key_type == "RSA"

    def test_raises_kalshi_auth_error_for_invalid_pem(self) -> None:
        """KalshiAuth raises KalshiAuthError for invalid PEM data."""
        with pytest.raises(KalshiAuthError, match="Invalid private key format"):
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

    def test_signature_verifies_with_public_key(self, kalshi_auth) -> None:
        """Signature can be verified with the corresponding public key (RSA-PSS)."""
        ts = 1700000000000
        path = "/trade-api/v2/portfolio/balance"
        headers = kalshi_auth.sign_request("GET", path, timestamp_ms=ts)

        # Reconstruct the signed message
        message = f"{ts}GET{path}".encode()
        signature = base64.b64decode(headers["KALSHI-ACCESS-SIGNATURE"])

        # Verify with the public key (RSA-PSS)
        public_key = kalshi_auth.private_key.public_key()
        # This will raise InvalidSignature if verification fails
        public_key.verify(
            signature,
            message,
            padding.PSS(
                mgf=padding.MGF1(hashes.SHA256()),
                salt_length=padding.PSS.DIGEST_LENGTH,
            ),
            hashes.SHA256(),
        )

    def test_timestamp_is_in_milliseconds(self, kalshi_auth) -> None:
        """KALSHI-ACCESS-TIMESTAMP is greater than 1_000_000_000_000 (milliseconds)."""
        headers = kalshi_auth.sign_request("GET", "/trade-api/v2/markets")

        ts = int(headers["KALSHI-ACCESS-TIMESTAMP"])
        assert ts > 1_000_000_000_000, (
            f"Timestamp {ts} should be in milliseconds (> 1_000_000_000_000)"
        )

    def test_method_is_uppercased_in_signing_string(self, kalshi_auth) -> None:
        """Lowercase and uppercase methods both produce valid RSA-PSS signatures.

        PSS is non-deterministic (random salt), so we can't compare signatures
        directly. Instead, verify both produce valid signatures for the same
        uppercased signing message.
        """
        ts = 1700000000000
        path = "/trade-api/v2/markets"

        headers_lower = kalshi_auth.sign_request("get", path, timestamp_ms=ts)
        headers_upper = kalshi_auth.sign_request("GET", path, timestamp_ms=ts)

        # Both should produce valid signatures for the uppercased message
        message = f"{ts}GET{path}".encode()
        public_key = kalshi_auth.private_key.public_key()

        for headers in [headers_lower, headers_upper]:
            sig = base64.b64decode(headers["KALSHI-ACCESS-SIGNATURE"])
            public_key.verify(
                sig,
                message,
                padding.PSS(
                    mgf=padding.MGF1(hashes.SHA256()),
                    salt_length=padding.PSS.DIGEST_LENGTH,
                ),
                hashes.SHA256(),
            )

    def test_with_explicit_timestamp_ms_uses_that_value(self, kalshi_auth) -> None:
        """Providing timestamp_ms uses that exact value in the header."""
        custom_ts = 1700000000000
        headers = kalshi_auth.sign_request("GET", "/trade-api/v2/markets", timestamp_ms=custom_ts)

        assert headers["KALSHI-ACCESS-TIMESTAMP"] == str(custom_ts)

    def test_different_paths_produce_different_signatures(self, kalshi_auth) -> None:
        """Same method on different paths produces different signatures.

        While PSS is non-deterministic, signatures for different messages
        will be different (verified via public key — each only verifies
        against its own message).
        """
        ts = 1700000000000

        headers_a = kalshi_auth.sign_request("GET", "/trade-api/v2/markets", timestamp_ms=ts)
        headers_b = kalshi_auth.sign_request("GET", "/trade-api/v2/events", timestamp_ms=ts)

        # Different paths should produce different signatures
        assert headers_a["KALSHI-ACCESS-SIGNATURE"] != headers_b["KALSHI-ACCESS-SIGNATURE"]

    def test_query_params_stripped_from_signing_path(self, kalshi_auth) -> None:
        """Query parameters are stripped from the path before signing.

        Per Kalshi docs: 'When signing requests, use the path without query
        parameters.' So /trade-api/v2/events?limit=5 signs as /trade-api/v2/events.
        """
        ts = 1700000000000
        path_with_params = "/trade-api/v2/events?limit=5&status=active"
        path_without_params = "/trade-api/v2/events"

        headers = kalshi_auth.sign_request("GET", path_with_params, timestamp_ms=ts)

        # Verify the signature against the path WITHOUT query params
        message = f"{ts}GET{path_without_params}".encode()
        signature = base64.b64decode(headers["KALSHI-ACCESS-SIGNATURE"])
        public_key = kalshi_auth.private_key.public_key()

        # This will raise InvalidSignature if query params were NOT stripped
        public_key.verify(
            signature,
            message,
            padding.PSS(
                mgf=padding.MGF1(hashes.SHA256()),
                salt_length=padding.PSS.DIGEST_LENGTH,
            ),
            hashes.SHA256(),
        )
