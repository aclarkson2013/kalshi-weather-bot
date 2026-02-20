"""Redis pub/sub subscriber that bridges events to WebSocket clients.

Subscribes to the Redis "boz:events" channel and forwards each
message to the ConnectionManager for broadcasting to all connected
WebSocket clients. Handles Redis disconnection with exponential
backoff reconnection.

Started as an asyncio.Task during FastAPI app lifespan.

Usage:
    from backend.websocket.subscriber import redis_subscriber
    from backend.websocket.manager import manager

    task = asyncio.create_task(redis_subscriber(manager))
"""

from __future__ import annotations

import asyncio
import json

import redis.asyncio as aioredis

from backend.common.config import get_settings
from backend.common.logging import get_logger
from backend.common.metrics import WS_EVENTS_RECEIVED_TOTAL
from backend.websocket.events import EVENTS_CHANNEL
from backend.websocket.manager import ConnectionManager

logger = get_logger("SYSTEM")

MAX_BACKOFF_SECONDS = 30


async def redis_subscriber(mgr: ConnectionManager) -> None:
    """Subscribe to Redis boz:events and forward to WebSocket clients.

    Runs as a long-lived background task. On Redis disconnect, retries
    with exponential backoff up to MAX_BACKOFF_SECONDS.

    Args:
        mgr: The ConnectionManager to broadcast messages through.
    """
    attempt = 0

    while True:
        try:
            settings = get_settings()
            r = aioredis.from_url(settings.redis_url)
            pubsub = r.pubsub()
            await pubsub.subscribe(EVENTS_CHANNEL)

            logger.info(
                "Redis subscriber connected",
                extra={"data": {"channel": EVENTS_CHANNEL}},
            )
            attempt = 0  # Reset backoff on successful connect

            async for message in pubsub.listen():
                if message["type"] != "message":
                    continue

                data = message["data"]
                if isinstance(data, bytes):
                    data = data.decode("utf-8")

                # Increment metrics by event type
                try:
                    parsed = json.loads(data)
                    event_type = parsed.get("type", "unknown")
                    WS_EVENTS_RECEIVED_TOTAL.labels(event_type=event_type).inc()
                except (json.JSONDecodeError, AttributeError):
                    pass

                await mgr.broadcast(data)

        except asyncio.CancelledError:
            logger.info("Redis subscriber shutting down")
            break

        except Exception as exc:
            wait = min(2**attempt, MAX_BACKOFF_SECONDS)
            logger.warning(
                "Redis subscriber error, reconnecting",
                extra={
                    "data": {
                        "error": str(exc),
                        "attempt": attempt + 1,
                        "wait_seconds": wait,
                    }
                },
            )
            attempt += 1
            await asyncio.sleep(wait)
