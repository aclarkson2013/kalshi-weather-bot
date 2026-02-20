"""Tests for the Redis pub/sub subscriber."""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.websocket.subscriber import redis_subscriber


class FakeAsyncIter:
    """Fake async iterator that yields messages then raises CancelledError.

    We raise CancelledError (not StopAsyncIteration) to break out of
    both the async for loop AND the subscriber's while True loop.
    """

    def __init__(self, messages: list[dict]):
        self._messages = messages
        self._index = 0

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self._index < len(self._messages):
            msg = self._messages[self._index]
            self._index += 1
            return msg
        # Simulate task cancellation to exit cleanly
        raise asyncio.CancelledError


@pytest.fixture
def mock_manager() -> MagicMock:
    """Create a mock ConnectionManager."""
    mgr = MagicMock()
    mgr.broadcast = AsyncMock()
    return mgr


def _make_redis_mock(messages: list[dict]) -> MagicMock:
    """Create a mock Redis client with pubsub that yields given messages.

    Note: redis.asyncio `pubsub()` is synchronous (returns PubSub object),
    but `subscribe()` is async. Use MagicMock for the redis client and
    pubsub object, with AsyncMock only for async methods.
    """
    mock_pubsub = MagicMock()
    mock_pubsub.subscribe = AsyncMock()
    mock_pubsub.listen.return_value = FakeAsyncIter(messages)

    mock_redis = MagicMock()
    mock_redis.pubsub.return_value = mock_pubsub
    return mock_redis


class TestRedisSubscriber:
    """Tests for the redis_subscriber background task.

    Each test patches aioredis.from_url to return a mock Redis client.
    The FakeAsyncIter yields test messages then raises CancelledError
    to exit the subscriber's infinite loop cleanly.
    """

    @pytest.mark.asyncio
    async def test_forwards_message_to_manager(self, mock_manager: MagicMock):
        """Subscriber forwards Redis messages to manager.broadcast()."""
        event_json = json.dumps({"type": "trade.executed", "data": {"city": "NYC"}})
        messages = [
            {"type": "subscribe", "data": None},
            {"type": "message", "data": event_json.encode()},
        ]
        mock_redis = _make_redis_mock(messages)

        with patch("backend.websocket.subscriber.aioredis.from_url", return_value=mock_redis):
            # CancelledError propagates from FakeAsyncIter -> subscriber breaks
            await redis_subscriber(mock_manager)

        mock_manager.broadcast.assert_called_once_with(event_json)

    @pytest.mark.asyncio
    async def test_ignores_non_message_types(self, mock_manager: MagicMock):
        """Subscriber skips non-message types (subscribe, unsubscribe)."""
        messages = [
            {"type": "subscribe", "data": None},
            {"type": "psubscribe", "data": None},
        ]
        mock_redis = _make_redis_mock(messages)

        with patch("backend.websocket.subscriber.aioredis.from_url", return_value=mock_redis):
            await redis_subscriber(mock_manager)

        mock_manager.broadcast.assert_not_called()

    @pytest.mark.asyncio
    async def test_decodes_bytes_to_string(self, mock_manager: MagicMock):
        """Subscriber decodes bytes data to UTF-8 string."""
        event_json = '{"type": "trade.settled"}'
        messages = [
            {"type": "message", "data": event_json.encode("utf-8")},
        ]
        mock_redis = _make_redis_mock(messages)

        with patch("backend.websocket.subscriber.aioredis.from_url", return_value=mock_redis):
            await redis_subscriber(mock_manager)

        mock_manager.broadcast.assert_called_once_with(event_json)

    @pytest.mark.asyncio
    async def test_handles_string_data(self, mock_manager: MagicMock):
        """Subscriber handles string data (not bytes) from Redis."""
        event_json = '{"type": "prediction.updated"}'
        messages = [
            {"type": "message", "data": event_json},
        ]
        mock_redis = _make_redis_mock(messages)

        with patch("backend.websocket.subscriber.aioredis.from_url", return_value=mock_redis):
            await redis_subscriber(mock_manager)

        mock_manager.broadcast.assert_called_once_with(event_json)

    @pytest.mark.asyncio
    async def test_increments_metrics(self, mock_manager: MagicMock):
        """Subscriber increments WS_EVENTS_RECEIVED_TOTAL on message."""
        event_json = json.dumps({"type": "trade.executed"})
        messages = [
            {"type": "message", "data": event_json.encode()},
        ]
        mock_redis = _make_redis_mock(messages)

        with (
            patch("backend.websocket.subscriber.aioredis.from_url", return_value=mock_redis),
            patch("backend.websocket.subscriber.WS_EVENTS_RECEIVED_TOTAL") as mock_counter,
        ):
            mock_labels = mock_counter.labels.return_value
            await redis_subscriber(mock_manager)

            mock_counter.labels.assert_called_with(event_type="trade.executed")
            mock_labels.inc.assert_called_once()

    @pytest.mark.asyncio
    async def test_broadcasts_malformed_json(self, mock_manager: MagicMock):
        """Subscriber still broadcasts malformed JSON (metric extraction fails gracefully)."""
        messages = [
            {"type": "message", "data": b"not-valid-json"},
        ]
        mock_redis = _make_redis_mock(messages)

        with patch("backend.websocket.subscriber.aioredis.from_url", return_value=mock_redis):
            await redis_subscriber(mock_manager)

        mock_manager.broadcast.assert_called_once_with("not-valid-json")
