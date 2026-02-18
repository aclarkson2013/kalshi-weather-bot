"""Tests for Kalshi-specific exception classes.

Verifies context storage, string formatting, secret filtering,
inheritance hierarchy, and that all exception classes are importable.
"""

from __future__ import annotations

from backend.kalshi.exceptions import (
    KalshiApiError,
    KalshiAuthError,
    KalshiConnectionError,
    KalshiError,
    KalshiOrderRejectedError,
    KalshiRateLimitError,
)


class TestKalshiError:
    """Tests for the KalshiError base exception."""

    def test_stores_context_dict(self) -> None:
        """KalshiError stores the provided context dict."""
        ctx = {"path": "/events", "status": 500}
        err = KalshiError("Something went wrong", context=ctx)

        assert err.context == ctx
        assert err.context["path"] == "/events"
        assert err.context["status"] == 500

    def test_str_includes_context(self) -> None:
        """__str__ includes the context dict when present."""
        err = KalshiError("API failure", context={"path": "/markets"})
        result = str(err)

        assert "API failure" in result
        assert "context=" in result
        assert "/markets" in result

    def test_filters_keys_containing_key_or_secret(self) -> None:
        """__str__ filters out context keys containing 'key' or 'secret'."""
        err = KalshiError(
            "Auth failed",
            context={
                "path": "/events",
                "api_key": "my-secret-key-value",
                "client_secret": "super-secret",
                "status": 401,
            },
        )
        result = str(err)

        # Filtered keys should NOT appear in string output
        assert "my-secret-key-value" not in result
        assert "super-secret" not in result
        # Safe keys SHOULD appear
        assert "/events" in result
        assert "401" in result

    def test_str_without_context(self) -> None:
        """__str__ returns just the message when no context is provided."""
        err = KalshiError("Simple error")
        result = str(err)

        assert result == "Simple error"
        assert "context=" not in result


class TestKalshiErrorSubclasses:
    """Tests for KalshiError subclasses and their inheritance."""

    def test_kalshi_auth_error_is_subclass(self) -> None:
        """KalshiAuthError is a subclass of KalshiError."""
        assert issubclass(KalshiAuthError, KalshiError)

        err = KalshiAuthError("Bad key", context={"status": 401})
        assert isinstance(err, KalshiError)
        assert isinstance(err, Exception)

    def test_kalshi_rate_limit_error_is_subclass(self) -> None:
        """KalshiRateLimitError is a subclass of KalshiError."""
        assert issubclass(KalshiRateLimitError, KalshiError)

        err = KalshiRateLimitError("Too fast", context={"retry_after": "5"})
        assert isinstance(err, KalshiError)

    def test_all_exception_classes_exist_and_importable(self) -> None:
        """All expected exception classes exist and are importable."""
        # These imports are at the top of the file, so this verifies they work
        assert KalshiError is not None
        assert KalshiAuthError is not None
        assert KalshiRateLimitError is not None
        assert KalshiOrderRejectedError is not None
        assert KalshiApiError is not None
        assert KalshiConnectionError is not None

        # Verify they are all exception subclasses
        for cls in [
            KalshiError,
            KalshiAuthError,
            KalshiRateLimitError,
            KalshiOrderRejectedError,
            KalshiApiError,
            KalshiConnectionError,
        ]:
            assert issubclass(cls, Exception)
