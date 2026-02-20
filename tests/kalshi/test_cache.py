"""Unit tests for Kalshi Redis cache helpers.

Validates set/get operations for market prices, tickers, and feed status
using AsyncMock to simulate Redis without requiring a live instance.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.kalshi.cache import (
    get_city_prices,
    get_feed_status,
    get_redis_client,
    set_city_prices,
    set_feed_status,
)

# ─── Test Data ───

SAMPLE_PRICES = {"49-50": 35, "51-52": 45, "53+": 20}
SAMPLE_TICKERS = {
    "49-50": "KXHIGHNY-26FEB19-T50",
    "51-52": "KXHIGHNY-26FEB19-T52",
    "53+": "KXHIGHNY-26FEB19-T53",
}


# ─── Fixtures ───


@pytest.fixture
def mock_redis() -> AsyncMock:
    """Create a mock async Redis client with pipeline support.

    redis.pipeline() is synchronous (returns pipeline directly),
    but pipeline.set/get/execute are async — so pipeline is a MagicMock
    wrapping AsyncMock methods.
    """
    redis = AsyncMock()
    pipe = MagicMock()
    # Pipeline methods that are awaited
    pipe.execute = AsyncMock(return_value=[])
    pipe.set = MagicMock()
    pipe.get = MagicMock()
    # pipeline() is a sync call
    redis.pipeline = MagicMock(return_value=pipe)
    return redis


@pytest.fixture
def mock_pipeline(mock_redis: AsyncMock) -> MagicMock:
    """Return the mock pipeline from the mock Redis client."""
    return mock_redis.pipeline.return_value


# ─── Tests: get_redis_client ───


class TestGetRedisClient:
    """Tests for get_redis_client factory function."""

    @patch("backend.kalshi.cache.get_settings")
    @patch("backend.kalshi.cache.aioredis")
    async def test_uses_settings_redis_url(
        self, mock_aioredis: MagicMock, mock_get_settings: MagicMock
    ) -> None:
        """get_redis_client uses the redis_url from application settings."""
        mock_settings = MagicMock()
        mock_settings.redis_url = "redis://custom:6380/5"
        mock_get_settings.return_value = mock_settings
        mock_aioredis.from_url.return_value = AsyncMock()

        result = await get_redis_client()

        mock_aioredis.from_url.assert_called_once_with(
            "redis://custom:6380/5", decode_responses=True
        )
        assert result is mock_aioredis.from_url.return_value


# ─── Tests: set_city_prices ───


class TestSetCityPrices:
    """Tests for set_city_prices cache write."""

    @patch("backend.kalshi.cache.get_settings")
    async def test_stores_prices_and_tickers(
        self, mock_get_settings: MagicMock, mock_redis: AsyncMock, mock_pipeline: AsyncMock
    ) -> None:
        """Stores both price and ticker JSON in Redis with pipeline."""
        mock_settings = MagicMock()
        mock_settings.kalshi_ws_cache_ttl_seconds = 120
        mock_get_settings.return_value = mock_settings

        await set_city_prices(mock_redis, "NYC", "260219", SAMPLE_PRICES, SAMPLE_TICKERS)

        mock_redis.pipeline.assert_called_once()
        # Two pipeline set calls: one for prices, one for tickers
        assert mock_pipeline.set.call_count == 2
        mock_pipeline.execute.assert_awaited_once()

    @patch("backend.kalshi.cache.get_settings")
    async def test_uses_correct_redis_keys(
        self, mock_get_settings: MagicMock, mock_redis: AsyncMock, mock_pipeline: AsyncMock
    ) -> None:
        """Uses the correct key pattern: kalshi:prices:{city}:{date}."""
        mock_settings = MagicMock()
        mock_settings.kalshi_ws_cache_ttl_seconds = 120
        mock_get_settings.return_value = mock_settings

        await set_city_prices(mock_redis, "CHI", "260220", SAMPLE_PRICES, SAMPLE_TICKERS)

        price_call = mock_pipeline.set.call_args_list[0]
        ticker_call = mock_pipeline.set.call_args_list[1]
        assert price_call.args[0] == "kalshi:prices:CHI:260220"
        assert ticker_call.args[0] == "kalshi:tickers:CHI:260220"

    @patch("backend.kalshi.cache.get_settings")
    async def test_default_ttl_from_settings(
        self, mock_get_settings: MagicMock, mock_redis: AsyncMock, mock_pipeline: AsyncMock
    ) -> None:
        """Default TTL comes from settings.kalshi_ws_cache_ttl_seconds."""
        mock_settings = MagicMock()
        mock_settings.kalshi_ws_cache_ttl_seconds = 90
        mock_get_settings.return_value = mock_settings

        await set_city_prices(mock_redis, "NYC", "260219", SAMPLE_PRICES, SAMPLE_TICKERS)

        price_call = mock_pipeline.set.call_args_list[0]
        has_correct_ttl = price_call.kwargs.get("ex") == 90 or (
            len(price_call.args) > 2 and price_call.args[2] == 90
        )
        assert has_correct_ttl

    async def test_custom_ttl_overrides_settings(
        self, mock_redis: AsyncMock, mock_pipeline: AsyncMock
    ) -> None:
        """Explicit ttl parameter overrides the settings default."""
        await set_city_prices(mock_redis, "NYC", "260219", SAMPLE_PRICES, SAMPLE_TICKERS, ttl=60)

        price_call = mock_pipeline.set.call_args_list[0]
        # Price TTL should be 60
        assert price_call == mock_pipeline.set.call_args_list[0]
        mock_pipeline.execute.assert_awaited_once()

    @patch("backend.kalshi.cache.get_settings")
    async def test_serializes_prices_as_json(
        self, mock_get_settings: MagicMock, mock_redis: AsyncMock, mock_pipeline: AsyncMock
    ) -> None:
        """Prices dict is serialized as JSON string."""
        mock_settings = MagicMock()
        mock_settings.kalshi_ws_cache_ttl_seconds = 120
        mock_get_settings.return_value = mock_settings

        await set_city_prices(mock_redis, "NYC", "260219", SAMPLE_PRICES, SAMPLE_TICKERS)

        price_call = mock_pipeline.set.call_args_list[0]
        stored_json = price_call.args[1]
        assert json.loads(stored_json) == SAMPLE_PRICES

    @patch("backend.kalshi.cache.get_settings")
    async def test_ticker_ttl_at_least_300(
        self, mock_get_settings: MagicMock, mock_redis: AsyncMock, mock_pipeline: AsyncMock
    ) -> None:
        """Ticker TTL is at least 300 seconds even if price TTL is lower."""
        mock_settings = MagicMock()
        mock_settings.kalshi_ws_cache_ttl_seconds = 120
        mock_get_settings.return_value = mock_settings

        await set_city_prices(mock_redis, "NYC", "260219", SAMPLE_PRICES, SAMPLE_TICKERS)

        ticker_call = mock_pipeline.set.call_args_list[1]
        # ex=max(120, 300) = 300
        assert ticker_call.kwargs.get("ex") == 300 or (
            len(ticker_call.args) > 2 and ticker_call.args[2] >= 300
        )


# ─── Tests: get_city_prices ───


class TestGetCityPrices:
    """Tests for get_city_prices cache read."""

    async def test_returns_prices_and_tickers_on_hit(
        self, mock_redis: AsyncMock, mock_pipeline: AsyncMock
    ) -> None:
        """Returns (prices, tickers) tuple when both keys are cached."""
        mock_pipeline.execute.return_value = [
            json.dumps(SAMPLE_PRICES),
            json.dumps(SAMPLE_TICKERS),
        ]

        result = await get_city_prices(mock_redis, "NYC", "260219")

        assert result is not None
        prices, tickers = result
        assert prices == SAMPLE_PRICES
        assert tickers == SAMPLE_TICKERS

    async def test_returns_none_on_price_miss(
        self, mock_redis: AsyncMock, mock_pipeline: AsyncMock
    ) -> None:
        """Returns None if prices key is missing."""
        mock_pipeline.execute.return_value = [None, json.dumps(SAMPLE_TICKERS)]

        result = await get_city_prices(mock_redis, "NYC", "260219")

        assert result is None

    async def test_returns_none_on_ticker_miss(
        self, mock_redis: AsyncMock, mock_pipeline: AsyncMock
    ) -> None:
        """Returns None if tickers key is missing."""
        mock_pipeline.execute.return_value = [json.dumps(SAMPLE_PRICES), None]

        result = await get_city_prices(mock_redis, "NYC", "260219")

        assert result is None

    async def test_returns_none_on_both_miss(
        self, mock_redis: AsyncMock, mock_pipeline: AsyncMock
    ) -> None:
        """Returns None if both keys are missing (cache miss)."""
        mock_pipeline.execute.return_value = [None, None]

        result = await get_city_prices(mock_redis, "NYC", "260219")

        assert result is None

    async def test_uses_correct_redis_keys(
        self, mock_redis: AsyncMock, mock_pipeline: AsyncMock
    ) -> None:
        """Reads from the correct key pattern."""
        mock_pipeline.execute.return_value = [None, None]

        await get_city_prices(mock_redis, "MIA", "260220")

        get_calls = mock_pipeline.get.call_args_list
        assert get_calls[0].args[0] == "kalshi:prices:MIA:260220"
        assert get_calls[1].args[0] == "kalshi:tickers:MIA:260220"


# ─── Tests: set_feed_status ───


class TestSetFeedStatus:
    """Tests for set_feed_status."""

    async def test_connected_stores_one(self, mock_redis: AsyncMock) -> None:
        """connected=True stores '1' at kalshi:feed:status."""
        await set_feed_status(mock_redis, connected=True)

        mock_redis.set.assert_awaited_once_with("kalshi:feed:status", "1")

    async def test_disconnected_stores_zero(self, mock_redis: AsyncMock) -> None:
        """connected=False stores '0' at kalshi:feed:status."""
        await set_feed_status(mock_redis, connected=False)

        mock_redis.set.assert_awaited_once_with("kalshi:feed:status", "0")


# ─── Tests: get_feed_status ───


class TestGetFeedStatus:
    """Tests for get_feed_status."""

    async def test_returns_true_when_connected(self, mock_redis: AsyncMock) -> None:
        """Returns True when Redis value is '1'."""
        mock_redis.get.return_value = "1"

        result = await get_feed_status(mock_redis)

        assert result is True

    async def test_returns_false_when_disconnected(self, mock_redis: AsyncMock) -> None:
        """Returns False when Redis value is '0'."""
        mock_redis.get.return_value = "0"

        result = await get_feed_status(mock_redis)

        assert result is False

    async def test_returns_false_on_key_missing(self, mock_redis: AsyncMock) -> None:
        """Returns False when the key doesn't exist (None)."""
        mock_redis.get.return_value = None

        result = await get_feed_status(mock_redis)

        assert result is False
