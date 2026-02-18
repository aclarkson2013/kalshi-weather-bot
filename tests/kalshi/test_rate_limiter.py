"""Tests for the token bucket rate limiter.

Verifies initialization, token counting, and that acquire() works
correctly under default and custom configurations.
"""

from __future__ import annotations

import pytest

from backend.kalshi.rate_limiter import TokenBucketRateLimiter


class TestTokenBucketRateLimiter:
    """Tests for TokenBucketRateLimiter."""

    def test_initializes_with_correct_defaults(self) -> None:
        """TokenBucketRateLimiter initializes with rate=10.0 and burst=10."""
        limiter = TokenBucketRateLimiter()
        assert limiter.rate == 10.0
        assert limiter.burst == 10

    def test_initial_tokens_equals_burst(self) -> None:
        """Initial token count equals the burst value."""
        limiter = TokenBucketRateLimiter(rate=5.0, burst=7)
        assert limiter.tokens == 7.0

    @pytest.mark.asyncio
    async def test_acquire_does_not_raise(self) -> None:
        """A single acquire() call does not raise when tokens are available."""
        limiter = TokenBucketRateLimiter(rate=10.0, burst=10)
        await limiter.acquire()  # Should not raise

    def test_custom_rate_and_burst(self) -> None:
        """TokenBucketRateLimiter accepts custom rate and burst values."""
        limiter = TokenBucketRateLimiter(rate=5.0, burst=20)
        assert limiter.rate == 5.0
        assert limiter.burst == 20
        assert limiter.tokens == 20.0

    @pytest.mark.asyncio
    async def test_tokens_do_not_exceed_burst_after_time_passes(self) -> None:
        """Tokens are capped at burst even after significant time elapses.

        After consuming a token and waiting, refill should not exceed burst.
        """
        limiter = TokenBucketRateLimiter(rate=10.0, burst=5)

        # Consume one token
        await limiter.acquire()

        # Simulate time passing by adjusting last_refill far into the past
        limiter.last_refill -= 100.0  # 100 seconds ago

        # Acquire again — tokens should refill but cap at burst
        await limiter.acquire()

        # After refill and consuming 1 token, tokens should be at most burst - 1
        assert limiter.tokens <= limiter.burst
