"""Tests for Phase 22 query optimizations.

Verifies that the batched dashboard prediction query and
SQL-aggregated performance endpoint work correctly.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from backend.common.models import TradeStatus
from tests.api.conftest import make_prediction, make_trade

pytestmark = pytest.mark.asyncio


# ─── Dashboard Batched Predictions ───


class TestDashboardBatchedPredictions:
    """Verify the dashboard prediction query fetches all cities in one query."""

    async def test_all_active_cities_returned(self, client: AsyncClient, db: AsyncSession) -> None:
        """Predictions for all 4 active cities returned in one response."""
        for city in ["NYC", "CHI", "MIA", "AUS"]:
            db.add(make_prediction(city=city))
        await db.flush()

        response = await client.get("/api/dashboard")
        assert response.status_code == 200
        data = response.json()
        cities = {p["city"] for p in data["predictions"]}
        assert cities == {"NYC", "CHI", "MIA", "AUS"}

    async def test_latest_prediction_per_city(self, client: AsyncClient, db: AsyncSession) -> None:
        """When multiple predictions exist, only the most recent per city is returned."""
        old = make_prediction(city="NYC")
        old.generated_at = datetime(2026, 1, 1, tzinfo=UTC)
        new = make_prediction(city="NYC")
        new.generated_at = datetime(2026, 2, 15, tzinfo=UTC)
        db.add(old)
        db.add(new)
        await db.flush()

        response = await client.get("/api/dashboard")
        data = response.json()
        nyc_preds = [p for p in data["predictions"] if p["city"] == "NYC"]
        assert len(nyc_preds) == 1

    async def test_no_predictions_returns_empty(self, client: AsyncClient) -> None:
        """No predictions in DB returns empty list."""
        response = await client.get("/api/dashboard")
        assert response.status_code == 200
        assert response.json()["predictions"] == []


# ─── Performance SQL Aggregation ───


class TestPerformanceSQLAggregation:
    """Verify the performance endpoint uses SQL aggregation correctly."""

    async def test_many_trades_aggregated(self, client: AsyncClient, db: AsyncSession) -> None:
        """Performance endpoint handles 50 trades with correct aggregation."""
        for i in range(50):
            status = TradeStatus.WON if i % 2 == 0 else TradeStatus.LOST
            pnl = 50 if status == TradeStatus.WON else -25
            trade = make_trade(
                user_id="test-user-001",
                city=["NYC", "CHI", "MIA", "AUS"][i % 4],
                status=status,
                pnl_cents=pnl,
                trade_date=date(2026, 1, 1) + timedelta(days=i),
                settled_at=datetime(2026, 1, 2, tzinfo=UTC) + timedelta(days=i),
            )
            db.add(trade)
        await db.flush()

        response = await client.get("/api/performance")
        assert response.status_code == 200
        data = response.json()
        assert data["total_trades"] == 50
        assert data["wins"] == 25
        assert data["losses"] == 25
        # 25 wins * 50 + 25 losses * -25 = 1250 - 625 = 625
        assert data["total_pnl_cents"] == 625
        assert data["best_trade_pnl_cents"] == 50
        assert data["worst_trade_pnl_cents"] == -25
        assert len(data["pnl_by_city"]) == 4
        assert len(data["cumulative_pnl"]) == 50
        assert len(data["accuracy_over_time"]) == 50

    async def test_same_day_trades_aggregated(self, client: AsyncClient, db: AsyncSession) -> None:
        """Multiple trades on the same day are aggregated into a single daily entry."""
        for _i in range(5):
            trade = make_trade(
                user_id="test-user-001",
                city="NYC",
                status=TradeStatus.WON,
                pnl_cents=10,
                trade_date=date(2026, 3, 1),
                settled_at=datetime(2026, 3, 2, tzinfo=UTC),
            )
            db.add(trade)
        await db.flush()

        response = await client.get("/api/performance")
        assert response.status_code == 200
        data = response.json()
        assert data["total_trades"] == 5
        assert data["total_pnl_cents"] == 50
        # All on the same day → 1 cumulative PnL point
        assert len(data["cumulative_pnl"]) == 1
        assert data["cumulative_pnl"][0]["cumulative_pnl"] == 50
        # Accuracy: 5/5 = 1.0
        assert len(data["accuracy_over_time"]) == 1
        assert data["accuracy_over_time"][0]["accuracy"] == 1.0

    async def test_accuracy_mixed_day(self, client: AsyncClient, db: AsyncSession) -> None:
        """Daily accuracy is correct when a day has both wins and losses."""
        # 2 wins + 1 loss on same day
        for status, pnl in [
            (TradeStatus.WON, 30),
            (TradeStatus.WON, 40),
            (TradeStatus.LOST, -20),
        ]:
            trade = make_trade(
                user_id="test-user-001",
                status=status,
                pnl_cents=pnl,
                trade_date=date(2026, 4, 1),
                settled_at=datetime(2026, 4, 2, tzinfo=UTC),
            )
            db.add(trade)
        await db.flush()

        response = await client.get("/api/performance")
        data = response.json()
        assert data["total_trades"] == 3
        assert data["wins"] == 2
        assert data["losses"] == 1
        assert data["accuracy_over_time"][0]["accuracy"] == round(2 / 3, 4)
