"""Async rate limiter for external API calls.

Uses a simple token-bucket approach to enforce per-second call limits.
Module-level instances are provided for NWS and Open-Meteo APIs.

Usage:
    from backend.weather.rate_limiter import nws_limiter

    async def make_nws_call():
        await nws_limiter.acquire()
        # ... make the API call ...
"""

from __future__ import annotations

import asyncio
import time


class RateLimiter:
    """Async rate limiter using a simple token bucket approach.

    Ensures that calls are spaced out to respect API rate limits.
    Thread-safe within a single asyncio event loop via asyncio.Lock.

    Args:
        calls_per_second: Maximum number of calls allowed per second.
    """

    def __init__(self, calls_per_second: float = 1.0) -> None:
        self.calls_per_second = calls_per_second
        self.min_interval = 1.0 / calls_per_second
        self.last_call: float = 0.0
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        """Wait until a request is allowed under the rate limit.

        Blocks the caller if the minimum interval since the last call
        has not yet elapsed. Uses asyncio.sleep for non-blocking waits.
        """
        async with self._lock:
            now = time.monotonic()
            wait_time = self.min_interval - (now - self.last_call)
            if wait_time > 0:
                await asyncio.sleep(wait_time)
            self.last_call = time.monotonic()


# ─── Module-Level Instances ───

# NWS asks for no more than 1 request per second
nws_limiter = RateLimiter(calls_per_second=1.0)

# Open-Meteo is more lenient with rate limits
openmeteo_limiter = RateLimiter(calls_per_second=5.0)
