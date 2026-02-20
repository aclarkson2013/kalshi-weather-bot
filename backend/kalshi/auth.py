"""Request signing for Kalshi API authentication.

Kalshi API uses RSA key pairs with RSA-PSS signing (SHA-256).
This module also supports EC (Elliptic Curve) keys as a fallback,
though Kalshi's official documentation only references RSA keys.

Signing algorithm (per Kalshi docs + official SDK):
- RSA keys: RSA-PSS with MGF1(SHA-256), salt_length=DIGEST_LENGTH
- EC keys: ECDSA with SHA-256 (unofficial, may not be supported)

IMPORTANT: Query parameters MUST be stripped from the path before signing.
The signing path is everything before the '?' character.

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
from cryptography.hazmat.primitives.asymmetric import ec, padding
from cryptography.hazmat.primitives.asymmetric.ec import EllipticCurvePrivateKey
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPrivateKey

from backend.common.logging import get_logger
from backend.kalshi.exceptions import KalshiAuthError

logger = get_logger("AUTH")


class KalshiAuth:
    """Request signer for the Kalshi API (supports RSA and EC keys).

    Loads a PEM-encoded private key (RSA or EC) and signs API requests.
    - RSA keys: signed with RSA-PSS + MGF1(SHA-256) (per Kalshi official SDK)
    - EC keys: signed with ECDSA + SHA-256 (unofficial fallback)

    The signing string format is:
        str(timestamp_ms) + HTTP_METHOD + path_without_query_params

    Args:
        api_key_id: Kalshi API key identifier.
        private_key_pem: Private key in PEM format (decrypted plaintext).
    """

    def __init__(self, api_key_id: str, private_key_pem: str) -> None:
        self.api_key_id = api_key_id
        try:
            self.private_key = serialization.load_pem_private_key(
                private_key_pem.encode(),
                password=None,
            )
        except (ValueError, TypeError) as exc:
            logger.error("Failed to load private key")
            raise KalshiAuthError(
                "Invalid private key format",
                context={"error_type": type(exc).__name__},
            ) from exc

        # Detect key type for signing
        if isinstance(self.private_key, RSAPrivateKey):
            self._key_type = "RSA"
        elif isinstance(self.private_key, EllipticCurvePrivateKey):
            self._key_type = "EC"
            logger.warning(
                "EC key detected — Kalshi docs only reference RSA keys. "
                "EC signing may not be supported by the Kalshi API. "
                "If authentication fails, regenerate an RSA key pair at kalshi.com.",
                extra={"data": {"key_id_prefix": api_key_id[:8] + "..."}},
            )
        else:
            raise KalshiAuthError(
                "Unsupported key type (expected RSA or EC)",
                context={"key_type": type(self.private_key).__name__},
            )

        logger.info(
            "Auth initialized",
            extra={"data": {"key_id_prefix": api_key_id[:8] + "...", "key_type": self._key_type}},
        )

    def sign_request(
        self,
        method: str,
        path: str,
        timestamp_ms: int | None = None,
    ) -> dict[str, str]:
        """Generate authentication headers for a Kalshi API request.

        The signing string is: str(timestamp_ms) + method.upper() + path
        Signed with the appropriate algorithm for the key type and base64-encoded.

        CRITICAL: The path must include the /trade-api/v2 prefix
        (e.g., "/trade-api/v2/markets", NOT "/markets").

        CRITICAL: Timestamps are in MILLISECONDS (int(time.time() * 1000)).

        CRITICAL: Query parameters are stripped before signing
        (e.g., "/trade-api/v2/events?limit=5" signs as "/trade-api/v2/events").

        Args:
            method: HTTP method (GET, POST, DELETE).
            path: Full request path starting with /trade-api/
                  (e.g., "/trade-api/v2/markets" or "/trade-api/ws/v2").
                  Query parameters are automatically stripped before signing.
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

        # Strip query parameters from path before signing (per Kalshi docs)
        signing_path = path.split("?")[0]

        # Signing string: timestamp + METHOD + path (no query params)
        message = ts_str + method.upper() + signing_path

        if self._key_type == "RSA":
            # RSA-PSS signing (per Kalshi official SDK)
            signature = self.private_key.sign(
                message.encode(),
                padding.PSS(
                    mgf=padding.MGF1(hashes.SHA256()),
                    salt_length=padding.PSS.DIGEST_LENGTH,
                ),
                hashes.SHA256(),
            )
        else:
            # EC (ECDSA) — unofficial fallback
            signature = self.private_key.sign(
                message.encode(),
                ec.ECDSA(hashes.SHA256()),
            )

        sig_b64 = base64.b64encode(signature).decode()

        return {
            "KALSHI-ACCESS-KEY": self.api_key_id,
            "KALSHI-ACCESS-SIGNATURE": sig_b64,
            "KALSHI-ACCESS-TIMESTAMP": ts_str,
            "Content-Type": "application/json",
        }
