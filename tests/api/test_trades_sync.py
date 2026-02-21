"""Tests for POST /api/trades/sync -- Kalshi portfolio sync endpoint."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio


async def test_sync_returns_sync_result(
    client: AsyncClient,
    mock_kalshi: AsyncMock,
) -> None:
    """POST /api/trades/sync returns a SyncResult JSON response."""
    mock_kalshi.get_orders.return_value = []

    response = await client.post("/api/trades/sync")
    assert response.status_code == 200

    data = response.json()
    assert "synced_count" in data
    assert "skipped_count" in data
    assert "failed_count" in data
    assert "errors" in data
    assert "synced_at" in data
    assert data["synced_count"] == 0
    assert data["skipped_count"] == 0


async def test_sync_requires_auth(unauthed_client: AsyncClient) -> None:
    """POST /api/trades/sync returns 401 when not authenticated."""
    response = await unauthed_client.post("/api/trades/sync")
    assert response.status_code == 401


async def test_sync_publishes_websocket_event(
    client: AsyncClient,
    mock_kalshi: AsyncMock,
) -> None:
    """POST /api/trades/sync publishes trade.synced when synced_count > 0."""
    # Mock sync_portfolio to return a result with synced trades
    mock_result = MagicMock()
    mock_result.synced_count = 3
    mock_result.skipped_count = 1
    mock_result.failed_count = 0
    mock_result.errors = []
    mock_result.synced_at = datetime.now(UTC)
    # Make it JSON-serializable by providing a model_dump method
    mock_result.model_dump.return_value = {
        "synced_count": 3,
        "skipped_count": 1,
        "failed_count": 0,
        "errors": [],
        "synced_at": datetime.now(UTC).isoformat(),
    }

    with (
        patch(
            "backend.trading.sync.sync_portfolio",
            new_callable=AsyncMock,
            return_value=mock_result,
        ),
        patch(
            "backend.api.trades.publish_event",
            new_callable=AsyncMock,
        ) as mock_publish,
    ):
        response = await client.post("/api/trades/sync")
        assert response.status_code == 200
        mock_publish.assert_called_once_with("trade.synced", {"synced_count": 3})


async def test_sync_no_event_when_zero_synced(
    client: AsyncClient,
    mock_kalshi: AsyncMock,
) -> None:
    """POST /api/trades/sync does NOT publish event when synced_count is 0."""
    mock_kalshi.get_orders.return_value = []

    with patch(
        "backend.api.trades.publish_event",
        new_callable=AsyncMock,
    ) as mock_publish:
        response = await client.post("/api/trades/sync")
        assert response.status_code == 200
        mock_publish.assert_not_called()


async def test_sync_handles_kalshi_error(
    client: AsyncClient,
    mock_kalshi: AsyncMock,
) -> None:
    """POST /api/trades/sync handles Kalshi auth errors gracefully."""
    mock_kalshi.get_orders.side_effect = Exception("Auth failed")

    response = await client.post("/api/trades/sync")
    # sync_portfolio catches this and returns SyncResult with error
    assert response.status_code == 200
    data = response.json()
    assert data["failed_count"] == 1
    assert len(data["errors"]) == 1
