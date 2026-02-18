"""Tests for the trades API endpoint."""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from backend.common.models import TradeStatus
from tests.api.conftest import make_trade

pytestmark = pytest.mark.asyncio


async def test_trades_empty(client: AsyncClient) -> None:
    """GET /api/trades returns empty page when no trades exist."""
    response = await client.get("/api/trades")
    assert response.status_code == 200
    data = response.json()
    assert data["trades"] == []
    assert data["total"] == 0
    assert data["page"] == 1


async def test_trades_pagination(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    """GET /api/trades supports pagination."""
    # Add 25 trades to exceed default page size (20)
    for _ in range(25):
        trade = make_trade(user_id="test-user-001", status=TradeStatus.OPEN)
        db.add(trade)
    await db.flush()

    # First page
    response = await client.get("/api/trades", params={"page": 1})
    assert response.status_code == 200
    data = response.json()
    assert len(data["trades"]) == 20
    assert data["total"] == 25
    assert data["page"] == 1

    # Second page
    response = await client.get("/api/trades", params={"page": 2})
    data = response.json()
    assert len(data["trades"]) == 5
    assert data["total"] == 25
    assert data["page"] == 2


async def test_trades_city_filter(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    """GET /api/trades?city=NYC filters by city."""
    nyc_trade = make_trade(user_id="test-user-001", city="NYC")
    chi_trade = make_trade(user_id="test-user-001", city="CHI")
    db.add(nyc_trade)
    db.add(chi_trade)
    await db.flush()

    response = await client.get("/api/trades", params={"city": "NYC"})
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert data["trades"][0]["city"] == "NYC"


async def test_trades_status_filter(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    """GET /api/trades?status=WON filters by status."""
    open_trade = make_trade(user_id="test-user-001", status=TradeStatus.OPEN)
    won_trade = make_trade(user_id="test-user-001", status=TradeStatus.WON, pnl_cents=50)
    db.add(open_trade)
    db.add(won_trade)
    await db.flush()

    response = await client.get("/api/trades", params={"status": "WON"})
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert data["trades"][0]["status"] == "WON"


async def test_trades_unauthenticated(unauthed_client: AsyncClient) -> None:
    """GET /api/trades returns 401 when not authenticated."""
    response = await unauthed_client.get("/api/trades")
    assert response.status_code == 401
