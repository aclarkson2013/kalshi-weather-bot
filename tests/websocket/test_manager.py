"""Tests for the WebSocket ConnectionManager."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from backend.websocket.manager import ConnectionManager


@pytest.fixture
def mgr() -> ConnectionManager:
    """Create a fresh ConnectionManager for each test."""
    return ConnectionManager()


def make_mock_ws() -> AsyncMock:
    """Create a mock WebSocket with accept, send_text, and close methods."""
    ws = AsyncMock()
    ws.accept = AsyncMock()
    ws.send_text = AsyncMock()
    ws.close = AsyncMock()
    return ws


class TestConnectionManager:
    """Tests for ConnectionManager connect/disconnect/broadcast."""

    @pytest.mark.asyncio
    async def test_connect_accepts_websocket(self, mgr: ConnectionManager):
        """connect() calls websocket.accept()."""
        ws = make_mock_ws()
        await mgr.connect(ws)
        ws.accept.assert_called_once()

    @pytest.mark.asyncio
    async def test_connect_adds_to_connections(self, mgr: ConnectionManager):
        """connect() adds the websocket to the internal set."""
        ws = make_mock_ws()
        await mgr.connect(ws)
        assert mgr.active_count == 1

    @pytest.mark.asyncio
    async def test_connect_multiple(self, mgr: ConnectionManager):
        """Multiple websockets can be connected simultaneously."""
        ws1 = make_mock_ws()
        ws2 = make_mock_ws()
        await mgr.connect(ws1)
        await mgr.connect(ws2)
        assert mgr.active_count == 2

    @pytest.mark.asyncio
    async def test_disconnect_removes_websocket(self, mgr: ConnectionManager):
        """disconnect() removes the websocket from the set."""
        ws = make_mock_ws()
        await mgr.connect(ws)
        mgr.disconnect(ws)
        assert mgr.active_count == 0

    @pytest.mark.asyncio
    async def test_disconnect_nonexistent_is_safe(self, mgr: ConnectionManager):
        """disconnect() on a non-tracked websocket does not raise."""
        ws = make_mock_ws()
        mgr.disconnect(ws)  # Should not raise
        assert mgr.active_count == 0

    @pytest.mark.asyncio
    async def test_broadcast_sends_to_all(self, mgr: ConnectionManager):
        """broadcast() sends the message to all connected websockets."""
        ws1 = make_mock_ws()
        ws2 = make_mock_ws()
        await mgr.connect(ws1)
        await mgr.connect(ws2)

        await mgr.broadcast('{"type": "trade.executed"}')

        ws1.send_text.assert_called_once_with('{"type": "trade.executed"}')
        ws2.send_text.assert_called_once_with('{"type": "trade.executed"}')

    @pytest.mark.asyncio
    async def test_broadcast_removes_dead_connections(self, mgr: ConnectionManager):
        """broadcast() removes websockets that fail on send."""
        ws_good = make_mock_ws()
        ws_dead = make_mock_ws()
        ws_dead.send_text = AsyncMock(side_effect=RuntimeError("Connection closed"))

        await mgr.connect(ws_good)
        await mgr.connect(ws_dead)
        assert mgr.active_count == 2

        await mgr.broadcast('{"type": "test"}')

        assert mgr.active_count == 1
        ws_good.send_text.assert_called_once()

    @pytest.mark.asyncio
    async def test_broadcast_empty_connections(self, mgr: ConnectionManager):
        """broadcast() with no connections does not raise."""
        await mgr.broadcast('{"type": "test"}')  # Should not raise

    @pytest.mark.asyncio
    async def test_active_count_property(self, mgr: ConnectionManager):
        """active_count reflects the current connection count."""
        assert mgr.active_count == 0
        ws = make_mock_ws()
        await mgr.connect(ws)
        assert mgr.active_count == 1
        mgr.disconnect(ws)
        assert mgr.active_count == 0

    @pytest.mark.asyncio
    async def test_broadcast_increments_metrics(self, mgr: ConnectionManager):
        """broadcast() increments WS_MESSAGES_SENT_TOTAL per message sent."""
        ws = make_mock_ws()
        await mgr.connect(ws)

        with patch("backend.websocket.manager.WS_MESSAGES_SENT_TOTAL") as mock_counter:
            mock_labels = mock_counter.labels.return_value
            await mgr.broadcast('{"type": "trade.executed"}')
            mock_counter.labels.assert_called_with(event_type="trade.executed")
            mock_labels.inc.assert_called_once()

    @pytest.mark.asyncio
    async def test_connect_increments_gauge(self, mgr: ConnectionManager):
        """connect() increments WS_CONNECTIONS_ACTIVE gauge."""
        ws = make_mock_ws()
        with patch("backend.websocket.manager.WS_CONNECTIONS_ACTIVE") as mock_gauge:
            await mgr.connect(ws)
            mock_gauge.inc.assert_called_once()

    @pytest.mark.asyncio
    async def test_disconnect_decrements_gauge(self, mgr: ConnectionManager):
        """disconnect() decrements WS_CONNECTIONS_ACTIVE gauge."""
        ws = make_mock_ws()
        await mgr.connect(ws)
        with patch("backend.websocket.manager.WS_CONNECTIONS_ACTIVE") as mock_gauge:
            mgr.disconnect(ws)
            mock_gauge.dec.assert_called_once()
