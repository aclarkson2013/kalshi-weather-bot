"""Tests for authentication API endpoints."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from backend.kalshi.exceptions import KalshiAuthError

pytestmark = pytest.mark.asyncio


async def test_validate_keys_success(client: AsyncClient, db: AsyncSession) -> None:
    """POST /api/auth/validate with valid keys creates user and returns balance."""
    mock_client_instance = AsyncMock()
    mock_client_instance.get_balance.return_value = 500.0  # $500
    mock_client_instance.close.return_value = None

    with patch("backend.api.auth.KalshiClient", return_value=mock_client_instance):
        response = await client.post(
            "/api/auth/validate",
            json={"key_id": "new-key-id", "private_key": "new-private-key"},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["valid"] is True
    assert data["balance_cents"] == 50000


async def test_validate_keys_invalid_credentials(client: AsyncClient) -> None:
    """POST /api/auth/validate with bad keys returns 401."""
    mock_client_instance = AsyncMock()
    mock_client_instance.get_balance.side_effect = KalshiAuthError(
        "Authentication failed", context={"status": 401}
    )
    mock_client_instance.close.return_value = None

    with patch("backend.api.auth.KalshiClient", return_value=mock_client_instance):
        response = await client.post(
            "/api/auth/validate",
            json={"key_id": "bad-key", "private_key": "bad-pem"},
        )

    assert response.status_code == 401
    assert "KalshiAuthError" in response.json()["error"]


async def test_validate_keys_updates_existing_user(client: AsyncClient, db: AsyncSession) -> None:
    """POST /api/auth/validate updates credentials when user already exists."""
    mock_client_instance = AsyncMock()
    mock_client_instance.get_balance.return_value = 250.0
    mock_client_instance.close.return_value = None

    with patch("backend.api.auth.KalshiClient", return_value=mock_client_instance):
        response = await client.post(
            "/api/auth/validate",
            json={"key_id": "updated-key-id", "private_key": "updated-pem"},
        )

    assert response.status_code == 200
    assert response.json()["balance_cents"] == 25000


async def test_disconnect_success(client: AsyncClient) -> None:
    """POST /api/auth/disconnect returns 204 for authenticated user."""
    response = await client.post("/api/auth/disconnect")
    assert response.status_code == 204


async def test_disconnect_unauthenticated(unauthed_client: AsyncClient) -> None:
    """POST /api/auth/disconnect returns 401 when not authenticated."""
    response = await unauthed_client.post("/api/auth/disconnect")
    assert response.status_code == 401
