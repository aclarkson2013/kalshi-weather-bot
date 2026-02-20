"""Redis cache for Kalshi market prices received via WebSocket feed.

Provides async helper functions to store and retrieve market prices
so the trading cycle can read cached prices instantly rather than
making REST API calls. Celery workers and FastAPI share the Redis
cache across processes.

Redis key layout:
    kalshi:prices:{city}:{YYMMDD}  → JSON dict of bracket_label → price_cents
    kalshi:tickers:{city}:{YYMMDD} → JSON dict of bracket_label → ticker_string
    kalshi:feed:status             → "1" (connected) or "0" (disconnected)
"""

from __future__ import annotations

import json

import redis.asyncio as aioredis

from backend.common.config import get_settings
from backend.common.logging import get_logger

logger = get_logger("MARKET")


async def get_redis_client() -> aioredis.Redis:
    """Create an async Redis client from application settings.

    Returns:
        An async Redis client connected to the configured redis_url.
    """
    settings = get_settings()
    return aioredis.from_url(settings.redis_url, decode_responses=True)


async def set_city_prices(
    redis: aioredis.Redis,
    city: str,
    date_str: str,
    prices: dict[str, int],
    tickers: dict[str, str],
    ttl: int | None = None,
) -> None:
    """Store market prices and tickers for a city+date in Redis.

    Args:
        redis: Async Redis client.
        city: City code (e.g., "NYC", "CHI", "MIA", "AUS").
        date_str: Date string in YYMMDD format.
        prices: Mapping of bracket_label → price in cents.
        tickers: Mapping of bracket_label → market ticker string.
        ttl: Cache TTL in seconds. Defaults to settings.kalshi_ws_cache_ttl_seconds.
    """
    if ttl is None:
        settings = get_settings()
        ttl = settings.kalshi_ws_cache_ttl_seconds

    price_key = f"kalshi:prices:{city}:{date_str}"
    ticker_key = f"kalshi:tickers:{city}:{date_str}"

    pipe = redis.pipeline()
    pipe.set(price_key, json.dumps(prices), ex=ttl)
    pipe.set(ticker_key, json.dumps(tickers), ex=max(ttl, 300))
    await pipe.execute()

    logger.debug(
        "Cached market prices",
        extra={"data": {"city": city, "date": date_str, "bracket_count": len(prices)}},
    )


async def get_city_prices(
    redis: aioredis.Redis,
    city: str,
    date_str: str,
) -> tuple[dict[str, int], dict[str, str]] | None:
    """Retrieve cached market prices and tickers for a city+date.

    Returns:
        Tuple of (prices, tickers) dicts if both are cached, or None on miss.
    """
    price_key = f"kalshi:prices:{city}:{date_str}"
    ticker_key = f"kalshi:tickers:{city}:{date_str}"

    pipe = redis.pipeline()
    pipe.get(price_key)
    pipe.get(ticker_key)
    price_raw, ticker_raw = await pipe.execute()

    if price_raw is None or ticker_raw is None:
        return None

    prices: dict[str, int] = json.loads(price_raw)
    tickers: dict[str, str] = json.loads(ticker_raw)
    return prices, tickers


async def set_feed_status(redis: aioredis.Redis, *, connected: bool) -> None:
    """Store the WebSocket feed connection status in Redis.

    Args:
        redis: Async Redis client.
        connected: True if the feed is connected, False otherwise.
    """
    await redis.set("kalshi:feed:status", "1" if connected else "0")


async def get_feed_status(redis: aioredis.Redis) -> bool:
    """Check whether the WebSocket feed is currently connected.

    Returns:
        True if the feed is connected, False otherwise (including key missing).
    """
    val = await redis.get("kalshi:feed:status")
    return val == "1"
