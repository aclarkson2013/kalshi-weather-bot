"""Tests for the settings API endpoints."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio


async def test_get_settings(client: AsyncClient) -> None:
    """GET /api/settings returns current user settings."""
    response = await client.get("/api/settings")
    assert response.status_code == 200
    data = response.json()
    assert data["trading_mode"] == "manual"
    assert data["max_trade_size_cents"] == 100
    assert data["daily_loss_limit_cents"] == 1000
    assert data["max_daily_exposure_cents"] == 2500
    assert data["min_ev_threshold"] == 0.05
    assert data["cooldown_per_loss_minutes"] == 60
    assert data["consecutive_loss_limit"] == 3
    assert set(data["active_cities"]) == {"NYC", "CHI", "MIA", "AUS"}
    assert data["notifications_enabled"] is True


async def test_patch_settings_partial(client: AsyncClient) -> None:
    """PATCH /api/settings updates only the provided fields."""
    response = await client.patch(
        "/api/settings",
        json={"trading_mode": "auto", "max_trade_size_cents": 200},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["trading_mode"] == "auto"
    assert data["max_trade_size_cents"] == 200
    # Unchanged fields remain the same
    assert data["daily_loss_limit_cents"] == 1000


async def test_patch_settings_active_cities(client: AsyncClient) -> None:
    """PATCH /api/settings can update active_cities list."""
    response = await client.patch(
        "/api/settings",
        json={"active_cities": ["NYC", "MIA"]},
    )
    assert response.status_code == 200
    data = response.json()
    assert set(data["active_cities"]) == {"NYC", "MIA"}


async def test_patch_settings_empty_body(client: AsyncClient) -> None:
    """PATCH /api/settings with empty body returns current settings unchanged."""
    # First get current settings
    get_resp = await client.get("/api/settings")
    original = get_resp.json()

    # Patch with empty body
    patch_resp = await client.patch("/api/settings", json={})
    assert patch_resp.status_code == 200
    patched = patch_resp.json()

    # trading_mode should be unchanged from previous tests or default
    assert patched["daily_loss_limit_cents"] == original["daily_loss_limit_cents"]


async def test_get_settings_unauthenticated(unauthed_client: AsyncClient) -> None:
    """GET /api/settings returns 401 when not authenticated."""
    response = await unauthed_client.get("/api/settings")
    assert response.status_code == 401
