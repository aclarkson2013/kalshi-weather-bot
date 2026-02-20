"""WebSocket streaming for real-time event push to connected browsers.

Bridges Celery worker events (trades, settlements, predictions) to the
frontend via Redis pub/sub and FastAPI WebSocket connections.

Architecture:
    Celery task -> publish_event_sync() -> Redis "boz:events" channel
    -> redis_subscriber() background task -> ConnectionManager.broadcast()
    -> connected WebSocket clients -> SWR mutate() -> UI update
"""
