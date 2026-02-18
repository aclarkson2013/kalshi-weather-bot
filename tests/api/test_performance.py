"""Tests for the performance API endpoint."""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from backend.common.models import TradeStatus
from tests.api.conftest import make_trade

pytestmark = pytest.mark.asyncio


async def test_performance_empty(client: AsyncClient) -> None:
    """GET /api/performance returns zeroed metrics when no settled trades exist."""
    response = await client.get("/api/performance")
    assert response.status_code == 200
    data = response.json()
    assert data["total_trades"] == 0
    assert data["wins"] == 0
    assert data["losses"] == 0
    assert data["win_rate"] == 0.0
    assert data["total_pnl_cents"] == 0
    assert data["cumulative_pnl"] == []
    assert data["pnl_by_city"] == {}
    assert data["accuracy_over_time"] == []


async def test_performance_with_trades(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    """GET /api/performance computes metrics from settled trades."""
    # Add won and lost trades
    win = make_trade(
        user_id="test-user-001",
        city="NYC",
        status=TradeStatus.WON,
        pnl_cents=75,
        trade_date=date(2026, 2, 15),
        settled_at=datetime(2026, 2, 16, 10, 0, tzinfo=UTC),
    )
    loss = make_trade(
        user_id="test-user-001",
        city="CHI",
        status=TradeStatus.LOST,
        pnl_cents=-25,
        trade_date=date(2026, 2, 16),
        settled_at=datetime(2026, 2, 17, 10, 0, tzinfo=UTC),
    )
    db.add(win)
    db.add(loss)
    await db.flush()

    response = await client.get("/api/performance")
    assert response.status_code == 200
    data = response.json()
    assert data["total_trades"] == 2
    assert data["wins"] == 1
    assert data["losses"] == 1
    assert data["win_rate"] == 0.5
    assert data["total_pnl_cents"] == 50  # 75 + (-25)
    assert data["best_trade_pnl_cents"] == 75
    assert data["worst_trade_pnl_cents"] == -25


async def test_performance_pnl_by_city(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    """GET /api/performance breaks down P&L by city."""
    nyc_trade = make_trade(
        user_id="test-user-001",
        city="NYC",
        status=TradeStatus.WON,
        pnl_cents=100,
        settled_at=datetime.now(UTC),
    )
    chi_trade = make_trade(
        user_id="test-user-001",
        city="CHI",
        status=TradeStatus.LOST,
        pnl_cents=-30,
        settled_at=datetime.now(UTC),
    )
    db.add(nyc_trade)
    db.add(chi_trade)
    await db.flush()

    response = await client.get("/api/performance")
    assert response.status_code == 200
    data = response.json()
    assert data["pnl_by_city"]["NYC"] == 100
    assert data["pnl_by_city"]["CHI"] == -30


async def test_performance_cumulative_pnl(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    """GET /api/performance returns cumulative P&L chart data."""
    trade1 = make_trade(
        user_id="test-user-001",
        status=TradeStatus.WON,
        pnl_cents=50,
        trade_date=date(2026, 1, 10),
        settled_at=datetime(2026, 1, 11, tzinfo=UTC),
    )
    trade2 = make_trade(
        user_id="test-user-001",
        status=TradeStatus.LOST,
        pnl_cents=-20,
        trade_date=date(2026, 1, 11),
        settled_at=datetime(2026, 1, 12, tzinfo=UTC),
    )
    db.add(trade1)
    db.add(trade2)
    await db.flush()

    response = await client.get("/api/performance")
    assert response.status_code == 200
    data = response.json()
    cpnl = data["cumulative_pnl"]
    assert len(cpnl) == 2
    # First point: 50
    assert cpnl[0]["cumulative_pnl"] == 50
    # Second point: 50 + (-20) = 30
    assert cpnl[1]["cumulative_pnl"] == 30


async def test_performance_unauthenticated(unauthed_client: AsyncClient) -> None:
    """GET /api/performance returns 401 when not authenticated."""
    response = await unauthed_client.get("/api/performance")
    assert response.status_code == 401
