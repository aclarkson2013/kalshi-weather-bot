"""Token bucket rate limiter for Kalshi API requests.

Prevents exceeding Kalshi's rate limits by throttling outgoing requests.
Uses an async token bucket algorithm that allows short bursts while
maintaining a sustained request rate.

Usage:
    from backend.kalshi.rate_limiter import TokenBucketRateLimiter

    limiter = TokenBucketRateLimiter(rate=10.0, burst=10)
    await limiter.acquire()  # blocks until a token is available
    # ... make API request ...
"""

from __future__ import annotations

import asyncio
import time


class TokenBucketRateLimiter:
    """Token bucket rate limiter for async API requests.

    Tokens are added at a steady rate up to a maximum burst size.
    Each API call consumes one token. If no tokens are available,
    the caller is blocked until one becomes available.

    Args:
        rate: Tokens added per second (sustained request rate).
        burst: Maximum token count (allows short bursts above sustained rate).
    """

    def __init__(self, rate: float = 10.0, burst: int = 10) -> None:
        self.rate = rate
        self.burst = burst
        self.tokens: float = float(burst)
        self.last_refill: float = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        """Acquire a token, waiting if necessary.

        Blocks until a token is available. Call this before every API request
        to stay within Kalshi's rate limits.
        """
        async with self._lock:
            now = time.monotonic()
            elapsed = now - self.last_refill
            self.tokens = min(self.burst, self.tokens + elapsed * self.rate)
            self.last_refill = now

            if self.tokens < 1:
                wait = (1 - self.tokens) / self.rate
                await asyncio.sleep(wait)
                self.tokens = 0
            else:
                self.tokens -= 1
