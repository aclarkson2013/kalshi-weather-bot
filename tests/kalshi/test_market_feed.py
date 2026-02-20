"""Unit tests for the Kalshi WebSocket market feed consumer.

Tests the MarketFeedConsumer class and market_feed_consumer() entry point.
All external dependencies (WebSocket, Redis, database) are mocked.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.kalshi.market_feed import (
    MarketFeedConsumer,
    market_feed_consumer,
)

# ─── Fixtures ───


@pytest.fixture
def mock_redis() -> AsyncMock:
    """Create a mock async Redis client."""
    redis = AsyncMock()
    pipe = MagicMock()
    pipe.execute = AsyncMock(return_value=[])
    pipe.set = MagicMock()
    pipe.get = MagicMock()
    redis.pipeline = MagicMock(return_value=pipe)
    return redis


@pytest.fixture
def consumer(mock_redis: AsyncMock) -> MarketFeedConsumer:
    """Create a MarketFeedConsumer with a mock Redis client."""
    return MarketFeedConsumer(redis_client=mock_redis)


@pytest.fixture
def mock_auth() -> MagicMock:
    """Create a mock KalshiAuth instance."""
    auth = MagicMock()
    auth.api_key_id = "test-key-id"
    auth.sign_request.return_value = {"KALSHI-ACCESS-KEY": "test"}
    return auth


@pytest.fixture
def mock_ws() -> AsyncMock:
    """Create a mock KalshiWebSocket instance."""
    ws = AsyncMock()
    ws.connect = AsyncMock()
    ws.subscribe_ticker = AsyncMock()
    ws.close = AsyncMock()
    ws.listen = MagicMock()
    return ws


# ─── Tests: Initialization ───


class TestMarketFeedConsumerInit:
    """Tests for MarketFeedConsumer initialization."""

    def test_creates_with_redis(self, mock_redis: AsyncMock) -> None:
        """Consumer stores the provided Redis client."""
        consumer = MarketFeedConsumer(redis_client=mock_redis)
        assert consumer._redis is mock_redis

    def test_creates_without_redis(self) -> None:
        """Consumer starts with None Redis, creates it later."""
        consumer = MarketFeedConsumer()
        assert consumer._redis is None

    def test_initial_state(self, consumer: MarketFeedConsumer) -> None:
        """Consumer starts in non-running state with empty subscriptions."""
        assert consumer._running is False
        assert consumer._ws is None
        assert len(consumer._subscribed_tickers) == 0
        assert len(consumer._ticker_to_bracket) == 0


# ─── Tests: Auth ───


class TestGetAuth:
    """Tests for _get_auth credential loading.

    _get_auth() uses lazy imports inside the function body, so we must
    patch at the source module (not backend.kalshi.market_feed).
    get_task_session() is awaited and returns a session object directly.
    """

    async def test_returns_none_when_no_user(self, consumer: MarketFeedConsumer) -> None:
        """Returns None if no user is configured in the database."""
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        with patch(
            "backend.common.database.get_task_session",
            return_value=mock_session,
        ):
            auth = await consumer._get_auth()

        assert auth is None

    async def test_returns_none_on_db_error(self, consumer: MarketFeedConsumer) -> None:
        """Returns None if database query fails."""
        mock_session = AsyncMock()
        mock_session.execute.side_effect = Exception("DB unavailable")

        with patch(
            "backend.common.database.get_task_session",
            return_value=mock_session,
        ):
            auth = await consumer._get_auth()

        assert auth is None

    async def test_returns_auth_with_valid_user(self, consumer: MarketFeedConsumer) -> None:
        """Returns KalshiAuth when user has credentials configured."""
        mock_user = MagicMock()
        mock_user.kalshi_key_id = "test-key-id"
        mock_user.encrypted_private_key = b"encrypted-pem"

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_user
        mock_session.execute.return_value = mock_result

        with (
            patch(
                "backend.common.database.get_task_session",
                return_value=mock_session,
            ),
            patch(
                "backend.common.encryption.decrypt_api_key",
                return_value="-----BEGIN RSA PRIVATE KEY-----\nfake\n-----END RSA PRIVATE KEY-----",
            ),
            patch("backend.kalshi.auth.KalshiAuth") as mock_auth_cls,
        ):
            mock_auth_cls.return_value = MagicMock()

            auth = await consumer._get_auth()

        assert auth is not None
        mock_auth_cls.assert_called_once()


# ─── Tests: Message Processing ───


class TestProcessMessage:
    """Tests for _process_message routing."""

    @patch("backend.kalshi.market_feed.KALSHI_WS_MESSAGES_TOTAL")
    async def test_ticker_message_increments_metric(
        self, mock_counter: MagicMock, consumer: MarketFeedConsumer
    ) -> None:
        """Ticker messages increment the ticker channel counter."""
        consumer._ticker_to_bracket = {}
        msg = {"type": "ticker", "msg": {"market_ticker": "unknown"}}

        await consumer._process_message(msg)

        mock_counter.labels.assert_called_with(channel="ticker")
        mock_counter.labels.return_value.inc.assert_called_once()

    @patch("backend.kalshi.market_feed.KALSHI_WS_MESSAGES_TOTAL")
    async def test_orderbook_delta_increments_metric(
        self, mock_counter: MagicMock, consumer: MarketFeedConsumer
    ) -> None:
        """Orderbook delta messages increment the correct counter."""
        msg = {"type": "orderbook_delta", "msg": {}}

        await consumer._process_message(msg)

        mock_counter.labels.assert_called_with(channel="orderbook_delta")

    @patch("backend.kalshi.market_feed.KALSHI_WS_MESSAGES_TOTAL")
    async def test_unknown_message_increments_other(
        self, mock_counter: MagicMock, consumer: MarketFeedConsumer
    ) -> None:
        """Unknown message types increment the 'other' counter."""
        msg = {"type": "subscription_confirmed", "msg": {}}

        await consumer._process_message(msg)

        mock_counter.labels.assert_called_with(channel="other")

    async def test_error_message_logs_warning(self, consumer: MarketFeedConsumer) -> None:
        """Error messages are logged as warnings."""
        msg = {"type": "error", "msg": "something failed"}

        with patch("backend.kalshi.market_feed.logger") as mock_logger:
            await consumer._process_message(msg)

        mock_logger.warning.assert_called_once()


# ─── Tests: Ticker Update Handling ───


class TestHandleTickerUpdate:
    """Tests for _handle_ticker_update cache + event logic."""

    async def test_ignores_unknown_ticker(
        self, consumer: MarketFeedConsumer, mock_redis: AsyncMock
    ) -> None:
        """Ignores updates for tickers not in the subscription map."""
        consumer._ticker_to_bracket = {}
        msg = {"type": "ticker", "msg": {"market_ticker": "UNKNOWN-T50"}}

        await consumer._handle_ticker_update(msg)

        # No cache write should occur
        mock_redis.publish.assert_not_awaited()

    async def test_caches_price_on_known_ticker(
        self, consumer: MarketFeedConsumer, mock_redis: AsyncMock
    ) -> None:
        """Updates Redis cache when a known ticker updates."""
        consumer._ticker_to_bracket = {
            "KXHIGHNY-26FEB19-T52": {
                "city": "NYC",
                "date_str": "260219",
                "label": "51-52F",
            }
        }
        # Cache miss — returns [None, None]
        pipe = mock_redis.pipeline.return_value
        pipe.execute.return_value = [None, None]

        msg = {
            "type": "ticker",
            "msg": {
                "market_ticker": "KXHIGHNY-26FEB19-T52",
                "yes_price": 45,
            },
        }

        with patch("backend.kalshi.market_feed.set_city_prices") as mock_set:
            await consumer._handle_ticker_update(msg)

            mock_set.assert_awaited_once()
            call_args = mock_set.call_args
            assert call_args.args[1] == "NYC"  # city
            assert call_args.args[2] == "260219"  # date_str

    async def test_publishes_event_on_update(
        self, consumer: MarketFeedConsumer, mock_redis: AsyncMock
    ) -> None:
        """Publishes a market.price_update event to Redis pub/sub."""
        consumer._ticker_to_bracket = {
            "KXHIGHNY-26FEB19-T52": {
                "city": "NYC",
                "date_str": "260219",
                "label": "51-52F",
            }
        }
        pipe = mock_redis.pipeline.return_value
        pipe.execute.return_value = [None, None]

        msg = {
            "type": "ticker",
            "msg": {
                "market_ticker": "KXHIGHNY-26FEB19-T52",
                "yes_price": 45,
            },
        }

        with patch("backend.kalshi.market_feed.set_city_prices"):
            await consumer._handle_ticker_update(msg)

        mock_redis.publish.assert_awaited_once()
        published_data = mock_redis.publish.call_args.args[1]
        import json

        event = json.loads(published_data)
        assert event["type"] == "market.price_update"
        assert event["data"]["city"] == "NYC"
        assert event["data"]["yes_price"] == 45

    async def test_handles_cache_error_gracefully(
        self, consumer: MarketFeedConsumer, mock_redis: AsyncMock
    ) -> None:
        """Logs warning and continues on cache write failure."""
        consumer._ticker_to_bracket = {
            "KXHIGHNY-26FEB19-T52": {
                "city": "NYC",
                "date_str": "260219",
                "label": "51-52F",
            }
        }

        with (
            patch(
                "backend.kalshi.market_feed.get_city_prices",
                side_effect=Exception("Redis down"),
            ),
            patch("backend.kalshi.market_feed.logger") as mock_logger,
        ):
            msg = {
                "type": "ticker",
                "msg": {
                    "market_ticker": "KXHIGHNY-26FEB19-T52",
                    "yes_price": 45,
                },
            }
            await consumer._handle_ticker_update(msg)

        mock_logger.warning.assert_called_once()

    async def test_ignores_empty_market_ticker(
        self, consumer: MarketFeedConsumer, mock_redis: AsyncMock
    ) -> None:
        """Ignores messages with empty market_ticker."""
        msg = {"type": "ticker", "msg": {"market_ticker": ""}}

        await consumer._handle_ticker_update(msg)

        mock_redis.publish.assert_not_awaited()

    async def test_uses_last_price_fallback(
        self, consumer: MarketFeedConsumer, mock_redis: AsyncMock
    ) -> None:
        """Falls back to last_price if yes_price is not available."""
        consumer._ticker_to_bracket = {
            "KXHIGHNY-26FEB19-T52": {
                "city": "NYC",
                "date_str": "260219",
                "label": "51-52F",
            }
        }
        pipe = mock_redis.pipeline.return_value
        pipe.execute.return_value = [None, None]

        msg = {
            "type": "ticker",
            "msg": {
                "market_ticker": "KXHIGHNY-26FEB19-T52",
                "last_price": 38,
            },
        }

        with patch("backend.kalshi.market_feed.set_city_prices") as mock_set:
            await consumer._handle_ticker_update(msg)

            # Should have cached with last_price=38
            call_args = mock_set.call_args
            prices = call_args.args[3]
            assert prices.get("51-52F") == 38


# ─── Tests: Stop ───


class TestStop:
    """Tests for stop() cleanup."""

    async def test_stop_closes_websocket(
        self, consumer: MarketFeedConsumer, mock_redis: AsyncMock
    ) -> None:
        """stop() closes the WebSocket connection."""
        mock_ws = AsyncMock()
        consumer._ws = mock_ws
        consumer._running = True

        await consumer.stop()

        mock_ws.close.assert_awaited_once()
        assert consumer._ws is None

    async def test_stop_clears_subscriptions(
        self, consumer: MarketFeedConsumer, mock_redis: AsyncMock
    ) -> None:
        """stop() clears the subscription tracking sets."""
        consumer._subscribed_tickers = {"T1", "T2"}
        consumer._running = True

        await consumer.stop()

        assert len(consumer._subscribed_tickers) == 0

    async def test_stop_sets_feed_disconnected(
        self, consumer: MarketFeedConsumer, mock_redis: AsyncMock
    ) -> None:
        """stop() marks the feed as disconnected in Redis."""
        consumer._running = True

        with patch("backend.kalshi.market_feed.set_feed_status") as mock_status:
            await consumer.stop()

        mock_status.assert_awaited()


# ─── Tests: Subscribe Active Markets ───


class TestSubscribeActiveMarkets:
    """Tests for _subscribe_active_markets."""

    async def test_subscribes_to_discovered_tickers(self, consumer: MarketFeedConsumer) -> None:
        """Subscribes to all tickers returned by _get_active_tickers."""
        mock_ws = AsyncMock()
        consumer._ws = mock_ws

        with patch.object(
            consumer,
            "_get_active_tickers",
            return_value={"KXHIGHNY-T50", "KXHIGHNY-T52"},
        ):
            await consumer._subscribe_active_markets()

        assert mock_ws.subscribe_ticker.await_count == 2
        assert len(consumer._subscribed_tickers) == 2

    async def test_skips_already_subscribed(self, consumer: MarketFeedConsumer) -> None:
        """Doesn't re-subscribe to tickers that are already subscribed."""
        mock_ws = AsyncMock()
        consumer._ws = mock_ws
        consumer._subscribed_tickers = {"KXHIGHNY-T50"}

        with patch.object(
            consumer,
            "_get_active_tickers",
            return_value={"KXHIGHNY-T50", "KXHIGHNY-T52"},
        ):
            await consumer._subscribe_active_markets()

        # Only subscribe to the new one
        assert mock_ws.subscribe_ticker.await_count == 1


# ─── Tests: Refresh Subscriptions ───


class TestRefreshSubscriptions:
    """Tests for _refresh_subscriptions."""

    async def test_subscribes_new_and_removes_expired(self, consumer: MarketFeedConsumer) -> None:
        """Refreshes: subscribes new tickers, removes expired ones."""
        mock_ws = AsyncMock()
        consumer._ws = mock_ws
        consumer._subscribed_tickers = {"OLD-T50", "KEEP-T52"}
        consumer._ticker_to_bracket = {"OLD-T50": {}, "KEEP-T52": {}}

        with patch.object(
            consumer,
            "_get_active_tickers",
            return_value={"KEEP-T52", "NEW-T54"},
        ):
            await consumer._refresh_subscriptions()

        # OLD-T50 removed, NEW-T54 added
        assert "OLD-T50" not in consumer._subscribed_tickers
        assert "NEW-T54" in consumer._subscribed_tickers
        assert "KEEP-T52" in consumer._subscribed_tickers


# ─── Tests: Metrics ───


class TestMetrics:
    """Tests for Prometheus metric instrumentation."""

    @patch("backend.kalshi.market_feed.KALSHI_WS_CONNECTED")
    @patch("backend.kalshi.market_feed.set_feed_status")
    async def test_stop_sets_connected_gauge_to_zero(
        self,
        mock_feed_status: AsyncMock,
        mock_gauge: MagicMock,
        consumer: MarketFeedConsumer,
        mock_redis: AsyncMock,
    ) -> None:
        """stop() sets the connected gauge to 0."""
        consumer._running = True

        await consumer.stop()

        mock_gauge.set.assert_called_with(0)


# ─── Tests: Top-Level Entry Point ───


class TestMarketFeedConsumerEntryPoint:
    """Tests for the market_feed_consumer() function."""

    async def test_calls_start_and_stop(self) -> None:
        """market_feed_consumer() calls start() then stop()."""
        with patch("backend.kalshi.market_feed.MarketFeedConsumer") as mock_cls:
            mock_instance = AsyncMock()
            mock_cls.return_value = mock_instance
            mock_instance.start = AsyncMock()
            mock_instance.stop = AsyncMock()

            await market_feed_consumer()

            mock_instance.start.assert_awaited_once()
            mock_instance.stop.assert_awaited_once()

    async def test_handles_cancelled_error(self) -> None:
        """market_feed_consumer() handles CancelledError gracefully."""
        with patch("backend.kalshi.market_feed.MarketFeedConsumer") as mock_cls:
            mock_instance = AsyncMock()
            mock_cls.return_value = mock_instance
            mock_instance.start = AsyncMock(side_effect=asyncio.CancelledError)
            mock_instance.stop = AsyncMock()

            await market_feed_consumer()

            mock_instance.stop.assert_awaited_once()
