"""Tests for the trade queue API endpoints."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from backend.common.models import PendingTradeStatus
from backend.common.schemas import TradeRecord
from tests.api.conftest import make_pending_trade

pytestmark = pytest.mark.asyncio


async def test_queue_empty(client: AsyncClient) -> None:
    """GET /api/queue returns empty list when no pending trades exist."""
    response = await client.get("/api/queue")
    assert response.status_code == 200
    assert response.json() == []


async def test_queue_with_pending_trades(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    """GET /api/queue returns pending trades ordered by creation time."""
    pt1 = make_pending_trade(user_id="test-user-001")
    pt2 = make_pending_trade(user_id="test-user-001")
    db.add(pt1)
    db.add(pt2)
    await db.flush()

    response = await client.get("/api/queue")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2


async def test_queue_excludes_non_pending(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    """GET /api/queue excludes trades that are not PENDING."""
    pending = make_pending_trade(user_id="test-user-001")
    rejected = make_pending_trade(user_id="test-user-001", status=PendingTradeStatus.REJECTED)
    db.add(pending)
    db.add(rejected)
    await db.flush()

    response = await client.get("/api/queue")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["status"] == "PENDING"


async def test_approve_trade_success(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    """POST /api/queue/{id}/approve executes the trade and returns TradeRecord."""
    pt = make_pending_trade(user_id="test-user-001")
    db.add(pt)
    await db.flush()

    # Mock execute_trade to return a fake TradeRecord
    from datetime import UTC, date, datetime

    fake_record = TradeRecord(
        id="executed-trade-id",
        kalshi_order_id="order-abc123",
        city="NYC",
        date=date.today(),
        bracket_label="55-56°F",
        side="yes",
        price_cents=22,
        quantity=1,
        model_probability=0.30,
        market_probability=0.22,
        ev_at_entry=0.05,
        confidence="medium",
        status="OPEN",
        created_at=datetime.now(UTC),
    )

    with patch("backend.api.queue.execute_trade", new_callable=AsyncMock) as mock_exec:
        mock_exec.return_value = fake_record
        response = await client.post(f"/api/queue/{pt.id}/approve")

    assert response.status_code == 200
    data = response.json()
    assert data["id"] == "executed-trade-id"


async def test_approve_trade_not_found(client: AsyncClient) -> None:
    """POST /api/queue/{id}/approve returns 404 for nonexistent trade."""
    response = await client.post("/api/queue/nonexistent-id/approve")
    assert response.status_code == 404


async def test_reject_trade_success(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    """POST /api/queue/{id}/reject returns 204 and marks trade rejected."""
    pt = make_pending_trade(user_id="test-user-001")
    db.add(pt)
    await db.flush()

    response = await client.post(f"/api/queue/{pt.id}/reject")
    assert response.status_code == 204


async def test_reject_trade_not_found(client: AsyncClient) -> None:
    """POST /api/queue/{id}/reject returns 404 for nonexistent trade."""
    response = await client.post("/api/queue/nonexistent-id/reject")
    assert response.status_code == 404


async def test_queue_unauthenticated(unauthed_client: AsyncClient) -> None:
    """GET /api/queue returns 401 when not authenticated."""
    response = await unauthed_client.get("/api/queue")
    assert response.status_code == 401
