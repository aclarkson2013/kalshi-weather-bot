"""WebSocket connection manager for broadcasting events to clients.

Maintains a set of active WebSocket connections and provides a
broadcast method that sends a message to all connected clients.
Dead connections are automatically cleaned up on send failure.

The module-level `manager` instance is a singleton shared across
the FastAPI application.

Usage:
    from backend.websocket.manager import manager

    await manager.connect(websocket)
    await manager.broadcast('{"type": "trade.executed", ...}')
    manager.disconnect(websocket)
"""

from __future__ import annotations

import json

from fastapi import WebSocket

from backend.common.logging import get_logger
from backend.common.metrics import (
    WS_CONNECTIONS_ACTIVE,
    WS_MESSAGES_SENT_TOTAL,
)

logger = get_logger("SYSTEM")


class ConnectionManager:
    """Manages active WebSocket connections and message broadcasting.

    Thread-safe for a single asyncio event loop (FastAPI's default).
    Supports multiple connections from the same user (e.g., multiple tabs).
    """

    def __init__(self) -> None:
        self._connections: set[WebSocket] = set()

    async def connect(self, websocket: WebSocket) -> None:
        """Accept a WebSocket connection and track it.

        Args:
            websocket: The FastAPI WebSocket to accept and track.
        """
        await websocket.accept()
        self._connections.add(websocket)
        WS_CONNECTIONS_ACTIVE.inc()
        logger.info(
            "WebSocket connected",
            extra={"data": {"active_connections": len(self._connections)}},
        )

    def disconnect(self, websocket: WebSocket) -> None:
        """Remove a WebSocket connection from tracking.

        Args:
            websocket: The WebSocket to remove.
        """
        self._connections.discard(websocket)
        WS_CONNECTIONS_ACTIVE.dec()
        logger.info(
            "WebSocket disconnected",
            extra={"data": {"active_connections": len(self._connections)}},
        )

    async def broadcast(self, message: str) -> None:
        """Send a message to all connected WebSocket clients.

        Catches send failures and removes dead connections. Increments
        the WS_MESSAGES_SENT_TOTAL counter per event type.

        Args:
            message: JSON string to broadcast.
        """
        # Extract event type for metrics
        event_type = "unknown"
        try:
            parsed = json.loads(message)
            event_type = parsed.get("type", "unknown")
        except (json.JSONDecodeError, AttributeError):
            pass

        dead: list[WebSocket] = []
        for ws in self._connections.copy():
            try:
                await ws.send_text(message)
                WS_MESSAGES_SENT_TOTAL.labels(event_type=event_type).inc()
            except Exception:
                dead.append(ws)

        for ws in dead:
            self.disconnect(ws)

    @property
    def active_count(self) -> int:
        """Return the number of active connections."""
        return len(self._connections)


# Module-level singleton
manager = ConnectionManager()
