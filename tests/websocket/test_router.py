"""Tests for the WebSocket router endpoint.

Uses a minimal FastAPI app (not the full main.app) to avoid triggering
the Redis subscriber lifespan that requires a real Redis connection.
"""

from __future__ import annotations

from unittest.mock import patch

from fastapi import FastAPI
from starlette.testclient import TestClient

from backend.websocket.manager import ConnectionManager
from backend.websocket.router import router as ws_router


def _make_test_app() -> FastAPI:
    """Create a minimal FastAPI app with just the WebSocket route."""
    test_app = FastAPI()
    test_app.include_router(ws_router)
    return test_app


class TestWebSocketRouter:
    """Tests for the /ws WebSocket endpoint."""

    def test_websocket_connect_and_disconnect(self):
        """WebSocket endpoint accepts connections and handles disconnect."""
        test_mgr = ConnectionManager()
        test_app = _make_test_app()

        with patch("backend.websocket.router.manager", test_mgr):
            client = TestClient(test_app)
            with client.websocket_connect("/ws"):
                assert test_mgr.active_count == 1

            # After context exit, disconnect is called
            assert test_mgr.active_count == 0

    def test_websocket_client_can_send_keepalive(self):
        """Client can send keepalive messages through the websocket."""
        test_mgr = ConnectionManager()
        test_app = _make_test_app()

        with patch("backend.websocket.router.manager", test_mgr):
            client = TestClient(test_app)
            with client.websocket_connect("/ws") as ws:
                # Send a keepalive ping from client
                ws.send_text("ping")

    def test_multiple_sequential_connections(self):
        """Multiple sequential WebSocket connections work correctly."""
        test_mgr = ConnectionManager()
        test_app = _make_test_app()

        with patch("backend.websocket.router.manager", test_mgr):
            client = TestClient(test_app)

            with client.websocket_connect("/ws"):
                assert test_mgr.active_count == 1

            assert test_mgr.active_count == 0

            with client.websocket_connect("/ws"):
                assert test_mgr.active_count == 1

            assert test_mgr.active_count == 0

    def test_websocket_endpoint_path(self):
        """WebSocket endpoint is accessible at /ws path."""
        test_mgr = ConnectionManager()
        test_app = _make_test_app()

        with patch("backend.websocket.router.manager", test_mgr):
            client = TestClient(test_app)
            # Should not raise — /ws path exists
            with client.websocket_connect("/ws"):
                assert test_mgr.active_count == 1
