"""RSA request signing for Kalshi API authentication.

Kalshi requires each API request to be signed with an RSA private key
using PKCS1v15 + SHA-256. This module handles key loading and header
generation for authenticated requests.

SECURITY:
- Private keys are NEVER logged, printed, or included in error messages.
- Keys are stored AES-256 encrypted at rest and decrypted only in-memory.
- The KalshiAuth instance holds the loaded key object, not the raw PEM.

Usage:
    from backend.kalshi.auth import KalshiAuth

    auth = KalshiAuth(api_key_id="abc123", private_key_pem=decrypted_pem)
    headers = auth.sign_request("GET", "/trade-api/v2/portfolio/balance")
    # headers = {
    #     "KALSHI-ACCESS-KEY": "abc123",
    #     "KALSHI-ACCESS-SIGNATURE": "base64...",
    #     "KALSHI-ACCESS-TIMESTAMP": "1708012345678",
    #     "Content-Type": "application/json",
    # }
"""

from __future__ import annotations

import base64
import time

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding

from backend.common.logging import get_logger
from backend.kalshi.exceptions import KalshiAuthError

logger = get_logger("AUTH")


class KalshiAuth:
    """RSA-based request signer for the Kalshi API.

    Loads a PEM-encoded RSA private key and signs API requests using
    PKCS1v15 + SHA-256. The signing string format is:
        str(timestamp_ms) + HTTP_METHOD + path

    Args:
        api_key_id: Kalshi API key identifier.
        private_key_pem: RSA private key in PEM format (decrypted plaintext).
    """

    def __init__(self, api_key_id: str, private_key_pem: str) -> None:
        self.api_key_id = api_key_id
        try:
            self.private_key = serialization.load_pem_private_key(
                private_key_pem.encode(),
                password=None,
            )
        except (ValueError, TypeError) as exc:
            logger.error("Failed to load RSA private key")
            raise KalshiAuthError(
                "Invalid RSA private key format",
                context={"error_type": type(exc).__name__},
            ) from exc
        logger.info("Auth initialized", extra={"data": {"key_id_prefix": api_key_id[:8] + "..."}})

    def sign_request(
        self,
        method: str,
        path: str,
        timestamp_ms: int | None = None,
    ) -> dict[str, str]:
        """Generate authentication headers for a Kalshi API request.

        The signing string is: str(timestamp_ms) + method.upper() + path
        Signed with PKCS1v15 + SHA-256 and base64-encoded.

        CRITICAL: The path must include the /trade-api/v2 prefix
        (e.g., "/trade-api/v2/markets", NOT "/markets").

        CRITICAL: Timestamps are in MILLISECONDS (int(time.time() * 1000)).

        Args:
            method: HTTP method (GET, POST, DELETE).
            path: Full request path starting with /trade-api/
                  (e.g., "/trade-api/v2/markets" or "/trade-api/ws/v2").
            timestamp_ms: Unix timestamp in milliseconds. Auto-generated if None.

        Returns:
            Dict of headers to include in the request:
            - KALSHI-ACCESS-KEY
            - KALSHI-ACCESS-SIGNATURE
            - KALSHI-ACCESS-TIMESTAMP
            - Content-Type
        """
        ts = timestamp_ms or int(time.time() * 1000)
        ts_str = str(ts)

        # Signing string: timestamp + METHOD + path
        message = ts_str + method.upper() + path

        signature = self.private_key.sign(
            message.encode(),
            padding.PKCS1v15(),
            hashes.SHA256(),
        )

        sig_b64 = base64.b64encode(signature).decode()

        return {
            "KALSHI-ACCESS-KEY": self.api_key_id,
            "KALSHI-ACCESS-SIGNATURE": sig_b64,
            "KALSHI-ACCESS-TIMESTAMP": ts_str,
            "Content-Type": "application/json",
        }
