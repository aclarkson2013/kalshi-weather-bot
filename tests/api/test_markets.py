"""Tests for the markets API endpoint."""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.api.conftest import make_prediction

pytestmark = pytest.mark.asyncio


async def test_markets_empty(client: AsyncClient) -> None:
    """GET /api/markets returns empty list when no predictions exist."""
    response = await client.get("/api/markets")
    assert response.status_code == 200
    assert response.json() == []


async def test_markets_with_predictions(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    """GET /api/markets returns latest prediction per active city."""
    # Add predictions for two cities
    pred_nyc = make_prediction(city="NYC")
    pred_chi = make_prediction(city="CHI")
    db.add(pred_nyc)
    db.add(pred_chi)
    await db.flush()

    response = await client.get("/api/markets")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2
    cities = {p["city"] for p in data}
    assert "NYC" in cities
    assert "CHI" in cities


async def test_markets_city_filter(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    """GET /api/markets?city=NYC returns only NYC predictions."""
    pred_nyc = make_prediction(city="NYC")
    pred_chi = make_prediction(city="CHI")
    db.add(pred_nyc)
    db.add(pred_chi)
    await db.flush()

    response = await client.get("/api/markets", params={"city": "NYC"})
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["city"] == "NYC"


async def test_markets_city_filter_no_match(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    """GET /api/markets?city=MIA returns empty when no MIA predictions."""
    pred_nyc = make_prediction(city="NYC")
    db.add(pred_nyc)
    await db.flush()

    response = await client.get("/api/markets", params={"city": "MIA"})
    assert response.status_code == 200
    assert response.json() == []


async def test_markets_unauthenticated(unauthed_client: AsyncClient) -> None:
    """GET /api/markets returns 401 when not authenticated."""
    response = await unauthed_client.get("/api/markets")
    assert response.status_code == 401
