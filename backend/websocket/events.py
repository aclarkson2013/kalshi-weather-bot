"""WebSocket event models and Redis publish functions.

Provides a Pydantic event model and publish functions for emitting
real-time events from Celery tasks (sync context) or async code.
Events are published to the Redis "boz:events" pub/sub channel.

Usage from Celery tasks:
    from backend.websocket.events import publish_event_sync

    publish_event_sync("trade.executed", {"city": "NYC", "trade_id": "abc"})

Usage from async code:
    from backend.websocket.events import publish_event

    await publish_event("trade.settled", {"city": "NYC", "pnl_cents": 25})
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import redis.asyncio as aioredis
from asgiref.sync import async_to_sync
from pydantic import BaseModel

from backend.common.config import get_settings
from backend.common.logging import get_logger

logger = get_logger("SYSTEM")

# Redis channel name for WebSocket events
EVENTS_CHANNEL = "boz:events"


class WebSocketEvent(BaseModel):
    """A real-time event pushed to connected WebSocket clients.

    Attributes:
        type: Event type identifier (e.g., "trade.executed", "trade.settled").
        timestamp: UTC timestamp of when the event was created.
        data: Event-specific payload dict.
    """

    type: str
    timestamp: datetime
    data: dict[str, Any]


async def publish_event(event_type: str, data: dict[str, Any]) -> None:
    """Publish a WebSocket event to the Redis boz:events channel.

    Creates a WebSocketEvent with the current UTC timestamp, serializes
    it to JSON, and publishes to the Redis pub/sub channel.

    Args:
        event_type: Event type string (e.g., "trade.executed").
        data: Event-specific payload dict.
    """
    event = WebSocketEvent(
        type=event_type,
        timestamp=datetime.now(UTC),
        data=data,
    )

    settings = get_settings()
    r = aioredis.from_url(settings.redis_url)
    try:
        await r.publish(EVENTS_CHANNEL, event.model_dump_json())
    finally:
        await r.aclose()


def publish_event_sync(event_type: str, data: dict[str, Any]) -> None:
    """Synchronous wrapper for publish_event, safe for Celery tasks.

    Catches all exceptions so a Redis failure never crashes a trading
    cycle or settlement task. Logs warnings on failure.

    Args:
        event_type: Event type string (e.g., "trade.executed").
        data: Event-specific payload dict.
    """
    try:
        async_to_sync(publish_event)(event_type, data)
    except Exception as exc:
        logger.warning(
            "Failed to publish WebSocket event",
            extra={
                "data": {
                    "event_type": event_type,
                    "error": str(exc),
                }
            },
        )
