"""Tests for WebSocket event models and Redis publish functions."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.websocket.events import (
    EVENTS_CHANNEL,
    WebSocketEvent,
    publish_event,
    publish_event_sync,
)

# ─── WebSocketEvent Model Tests ───


class TestWebSocketEvent:
    """Tests for the WebSocketEvent Pydantic model."""

    def test_event_construction(self):
        """Event can be constructed with type, timestamp, and data."""
        ts = datetime.now(UTC)
        event = WebSocketEvent(type="trade.executed", timestamp=ts, data={"city": "NYC"})
        assert event.type == "trade.executed"
        assert event.timestamp == ts
        assert event.data == {"city": "NYC"}

    def test_event_json_serialization(self):
        """Event serializes to JSON with all fields."""
        ts = datetime(2024, 1, 15, 12, 0, 0, tzinfo=UTC)
        event = WebSocketEvent(type="trade.settled", timestamp=ts, data={"pnl_cents": 25})
        json_str = event.model_dump_json()
        parsed = json.loads(json_str)
        assert parsed["type"] == "trade.settled"
        assert parsed["data"]["pnl_cents"] == 25
        assert "timestamp" in parsed

    def test_event_json_round_trip(self):
        """Event survives JSON serialization and deserialization."""
        ts = datetime.now(UTC)
        original = WebSocketEvent(
            type="trade.queued",
            timestamp=ts,
            data={"city": "CHI", "bracket": "55-56"},
        )
        json_str = original.model_dump_json()
        restored = WebSocketEvent.model_validate_json(json_str)
        assert restored.type == original.type
        assert restored.data == original.data

    def test_event_empty_data(self):
        """Event works with empty data dict."""
        event = WebSocketEvent(type="dashboard.update", timestamp=datetime.now(UTC), data={})
        assert event.data == {}

    def test_event_nested_data(self):
        """Event handles nested data structures."""
        data = {"trade": {"id": "abc", "city": "NYC"}, "count": 3}
        event = WebSocketEvent(type="trade.executed", timestamp=datetime.now(UTC), data=data)
        assert event.data["trade"]["id"] == "abc"

    def test_all_event_types(self):
        """All expected event types can be constructed."""
        event_types = [
            "trade.executed",
            "trade.queued",
            "trade.settled",
            "trade.expired",
            "dashboard.update",
            "prediction.updated",
        ]
        for et in event_types:
            event = WebSocketEvent(type=et, timestamp=datetime.now(UTC), data={})
            assert event.type == et


# ─── publish_event Tests ───


class TestPublishEvent:
    """Tests for the async publish_event function."""

    @pytest.mark.asyncio
    async def test_publishes_to_redis_channel(self):
        """publish_event publishes JSON to the boz:events Redis channel."""
        mock_redis = AsyncMock()
        mock_redis.publish = AsyncMock()
        mock_redis.aclose = AsyncMock()

        with patch("backend.websocket.events.aioredis") as mock_aioredis:
            mock_aioredis.from_url.return_value = mock_redis
            await publish_event("trade.executed", {"city": "NYC"})

        mock_redis.publish.assert_called_once()
        channel, payload = mock_redis.publish.call_args[0]
        assert channel == EVENTS_CHANNEL
        parsed = json.loads(payload)
        assert parsed["type"] == "trade.executed"
        assert parsed["data"]["city"] == "NYC"

    @pytest.mark.asyncio
    async def test_closes_redis_connection(self):
        """publish_event always closes the Redis connection."""
        mock_redis = AsyncMock()
        mock_redis.publish = AsyncMock()
        mock_redis.aclose = AsyncMock()

        with patch("backend.websocket.events.aioredis") as mock_aioredis:
            mock_aioredis.from_url.return_value = mock_redis
            await publish_event("trade.settled", {"pnl": 50})

        mock_redis.aclose.assert_called_once()

    @pytest.mark.asyncio
    async def test_closes_redis_on_publish_error(self):
        """publish_event closes Redis even if publish raises."""
        mock_redis = AsyncMock()
        mock_redis.publish = AsyncMock(side_effect=ConnectionError("Redis down"))
        mock_redis.aclose = AsyncMock()

        with (
            patch("backend.websocket.events.aioredis") as mock_aioredis,
            pytest.raises(ConnectionError),
        ):
            mock_aioredis.from_url.return_value = mock_redis
            await publish_event("trade.executed", {})

        mock_redis.aclose.assert_called_once()

    @pytest.mark.asyncio
    async def test_event_has_utc_timestamp(self):
        """Published event includes a UTC timestamp."""
        mock_redis = AsyncMock()
        mock_redis.publish = AsyncMock()
        mock_redis.aclose = AsyncMock()

        with patch("backend.websocket.events.aioredis") as mock_aioredis:
            mock_aioredis.from_url.return_value = mock_redis
            await publish_event("trade.queued", {})

        _, payload = mock_redis.publish.call_args[0]
        parsed = json.loads(payload)
        # Timestamp should be parseable and recent
        ts = datetime.fromisoformat(parsed["timestamp"])
        assert ts.tzinfo is not None or "Z" in parsed["timestamp"]


# ─── publish_event_sync Tests ───


class TestPublishEventSync:
    """Tests for the synchronous publish_event_sync wrapper."""

    def test_calls_publish_event(self):
        """publish_event_sync calls the async publish_event under the hood."""
        with patch("backend.websocket.events.async_to_sync") as mock_ats:
            mock_sync_fn = MagicMock()
            mock_ats.return_value = mock_sync_fn

            publish_event_sync("trade.executed", {"city": "NYC"})

            mock_ats.assert_called_once_with(publish_event)
            mock_sync_fn.assert_called_once_with("trade.executed", {"city": "NYC"})

    def test_catches_redis_errors(self):
        """publish_event_sync does not raise on Redis failure."""
        with patch("backend.websocket.events.async_to_sync") as mock_ats:
            mock_ats.return_value = MagicMock(side_effect=ConnectionError("Redis down"))

            # Should NOT raise
            publish_event_sync("trade.executed", {"city": "NYC"})

    def test_logs_warning_on_failure(self):
        """publish_event_sync logs a warning when publish fails."""
        with (
            patch("backend.websocket.events.async_to_sync") as mock_ats,
            patch("backend.websocket.events.logger") as mock_logger,
        ):
            mock_ats.return_value = MagicMock(side_effect=RuntimeError("fail"))

            publish_event_sync("trade.settled", {"id": "abc"})

            mock_logger.warning.assert_called_once()
            call_args = mock_logger.warning.call_args
            assert "Failed to publish WebSocket event" in call_args[0][0]
