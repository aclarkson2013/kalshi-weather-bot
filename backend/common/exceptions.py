"""Custom exceptions for Boz Weather Trader.

All modules should raise these exceptions instead of generic ones.
The FastAPI exception handler in main.py catches BozBaseException
and returns structured JSON error responses.
"""

from __future__ import annotations


class BozBaseException(Exception):
    """Base exception for all Boz Weather Trader errors.

    Args:
        message: Human-readable error description.
        context: Optional dict of structured data for logging/debugging.
    """

    def __init__(self, message: str, context: dict | None = None) -> None:
        super().__init__(message)
        self.context = context or {}

    def __str__(self) -> str:
        if self.context:
            # Filter out anything that looks like a secret
            safe_context = {
                k: "[REDACTED]" if _is_secret_key(k) else v for k, v in self.context.items()
            }
            return f"{super().__str__()} | context={safe_context}"
        return super().__str__()


class StaleDataError(BozBaseException):
    """Weather data or predictions are too old to trade on."""


class RiskLimitError(BozBaseException):
    """A risk limit would be violated by this action."""


class CooldownActiveError(BozBaseException):
    """Trading is paused due to cooldown (per-loss or consecutive-loss)."""


class InsufficientBalanceError(BozBaseException):
    """Not enough Kalshi balance to place this trade."""


class InvalidOrderError(BozBaseException):
    """Order parameters are invalid (bad price, quantity, ticker, etc.)."""


class FetchError(BozBaseException):
    """Failed to fetch data from an external API (NWS, Open-Meteo, Kalshi)."""


class ParseError(BozBaseException):
    """Failed to parse response data from an external API."""


def _is_secret_key(key: str) -> bool:
    """Check if a dict key name suggests it contains secret data."""
    secret_words = {"key", "secret", "password", "token", "private", "pem", "credential"}
    key_lower = key.lower()
    return any(word in key_lower for word in secret_words)
