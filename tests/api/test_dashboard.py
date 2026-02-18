"""Tests for the dashboard API endpoint."""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from backend.common.models import TradeStatus
from tests.api.conftest import make_prediction, make_trade

pytestmark = pytest.mark.asyncio


async def test_dashboard_empty_state(client: AsyncClient) -> None:
    """GET /api/dashboard returns default data when no trades or predictions exist."""
    response = await client.get("/api/dashboard")
    assert response.status_code == 200
    data = response.json()
    assert data["balance_cents"] == 50000  # $500 from mock_kalshi
    assert data["today_pnl_cents"] == 0
    assert data["active_positions"] == []
    assert data["recent_trades"] == []
    assert data["next_market_launch"] is not None


async def test_dashboard_with_trades_and_predictions(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    """GET /api/dashboard includes open positions and predictions."""
    # Add an open trade
    trade = make_trade(user_id="test-user-001", status=TradeStatus.OPEN)
    db.add(trade)

    # Add a prediction for NYC
    pred = make_prediction(city="NYC")
    db.add(pred)
    await db.flush()

    response = await client.get("/api/dashboard")
    assert response.status_code == 200
    data = response.json()
    assert data["balance_cents"] == 50000
    assert len(data["active_positions"]) == 1
    assert len(data["predictions"]) >= 1


async def test_dashboard_today_pnl(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    """GET /api/dashboard calculates today's P&L from settled trades."""
    # Add a winning trade settled today
    trade = make_trade(
        user_id="test-user-001",
        status=TradeStatus.WON,
        pnl_cents=75,
        trade_date=date.today(),
        settled_at=datetime.now(UTC),
    )
    db.add(trade)
    await db.flush()

    response = await client.get("/api/dashboard")
    assert response.status_code == 200
    data = response.json()
    assert data["today_pnl_cents"] == 75


async def test_dashboard_unauthenticated(unauthed_client: AsyncClient) -> None:
    """GET /api/dashboard returns 401 when not authenticated."""
    response = await unauthed_client.get("/api/dashboard")
    assert response.status_code == 401
