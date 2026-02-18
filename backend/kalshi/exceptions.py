"""Kalshi-specific exceptions with structured context and automatic secret filtering.

All Kalshi API errors are subclasses of KalshiError. Each exception carries
an optional context dict for debugging, with automatic filtering of keys
that look like they might contain secrets (api keys, private keys, etc.).

Usage:
    from backend.kalshi.exceptions import KalshiAuthError, KalshiOrderRejectedError

    raise KalshiAuthError(
        "Authentication failed",
        context={"path": "/trade-api/v2/portfolio/balance"},
    )
"""

from __future__ import annotations


class KalshiError(Exception):
    """Base exception for all Kalshi API errors.

    Carries structured context for debugging while automatically
    filtering out keys that might contain secrets.

    Args:
        message: Human-readable error description.
        context: Optional dict of structured data for logging/debugging.
    """

    def __init__(self, message: str, context: dict | None = None) -> None:
        self.context = context or {}
        super().__init__(message)

    def __str__(self) -> str:
        base = super().__str__()
        if self.context:
            safe_ctx = {
                k: v
                for k, v in self.context.items()
                if "key" not in k.lower() and "secret" not in k.lower()
            }
            return f"{base} | context={safe_ctx}"
        return base


class KalshiAuthError(KalshiError):
    """Invalid API keys, expired signature, or 401 response from Kalshi."""


class KalshiRateLimitError(KalshiError):
    """Rate limit exceeded (429 response). Check context for retry_after."""


class KalshiOrderRejectedError(KalshiError):
    """Order rejected by Kalshi (insufficient balance, market closed, etc.)."""


class KalshiApiError(KalshiError):
    """Generic API error with status code and response details."""


class KalshiConnectionError(KalshiError):
    """Network issues, timeout, or WebSocket disconnect."""
