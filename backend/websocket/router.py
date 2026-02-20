"""FastAPI WebSocket endpoint for real-time event streaming.

Provides a WebSocket endpoint at /ws that accepts connections,
tracks them in the ConnectionManager, and keeps the connection
alive until the client disconnects.

The actual event delivery happens through the Redis subscriber
background task, which calls manager.broadcast() when events
are published to the boz:events channel.

Usage:
    # In backend/main.py:
    from backend.websocket.router import router as ws_router
    app.include_router(ws_router)
"""

from __future__ import annotations

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from backend.common.logging import get_logger
from backend.websocket.manager import manager

logger = get_logger("SYSTEM")

router = APIRouter()


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    """WebSocket endpoint for real-time event streaming.

    Accepts a WebSocket connection, adds it to the ConnectionManager,
    and enters a receive loop to keep the connection alive. The loop
    handles keepalive pings from the client.

    Events are delivered via ConnectionManager.broadcast(), triggered
    by the Redis subscriber background task.

    Args:
        websocket: The incoming WebSocket connection.
    """
    await manager.connect(websocket)
    try:
        while True:
            # Wait for client messages (keepalive pings)
            # This keeps the connection open; actual events are pushed
            # via manager.broadcast() from the Redis subscriber
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)
