"""Tests for the async rate limiter.

Validates timing behavior of the RateLimiter class and verifies
that module-level instances (nws_limiter, openmeteo_limiter) are
configured with correct rates.
"""

from __future__ import annotations

import pytest

from backend.weather.rate_limiter import RateLimiter, nws_limiter, openmeteo_limiter


class TestRateLimiterConfig:
    """Verify RateLimiter computes min_interval correctly."""

    def test_one_call_per_second_interval(self):
        """RateLimiter(1.0) has min_interval of 1.0 second."""
        limiter = RateLimiter(calls_per_second=1.0)
        assert limiter.min_interval == pytest.approx(1.0)

    def test_five_calls_per_second_interval(self):
        """RateLimiter(5.0) has min_interval of 0.2 seconds."""
        limiter = RateLimiter(calls_per_second=5.0)
        assert limiter.min_interval == pytest.approx(0.2)


class TestRateLimiterAcquire:
    """Verify acquire() works without errors."""

    @pytest.mark.asyncio
    async def test_acquire_does_not_raise(self):
        """A single acquire() call should not raise any exception."""
        limiter = RateLimiter(calls_per_second=10.0)
        # Should complete without error
        await limiter.acquire()

    @pytest.mark.asyncio
    async def test_first_call_returns_quickly(self):
        """The very first acquire() should return almost immediately."""
        import time

        limiter = RateLimiter(calls_per_second=1.0)
        start = time.monotonic()
        await limiter.acquire()
        elapsed = time.monotonic() - start
        assert elapsed < 0.1, f"First call waited {elapsed:.3f}s, expected near-instant"


class TestModuleLevelLimiters:
    """Verify that pre-configured module-level limiters have correct rates."""

    def test_nws_limiter_has_one_call_per_second(self):
        """nws_limiter should be configured at 1.0 calls per second."""
        assert isinstance(nws_limiter, RateLimiter)
        assert nws_limiter.calls_per_second == 1.0
        assert nws_limiter.min_interval == pytest.approx(1.0)

    def test_openmeteo_limiter_has_five_calls_per_second(self):
        """openmeteo_limiter should be configured at 5.0 calls per second."""
        assert isinstance(openmeteo_limiter, RateLimiter)
        assert openmeteo_limiter.calls_per_second == 5.0
        assert openmeteo_limiter.min_interval == pytest.approx(0.2)
