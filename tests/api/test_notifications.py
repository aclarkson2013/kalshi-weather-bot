"""Tests for the notifications API endpoint."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio


async def test_subscribe_push(client: AsyncClient) -> None:
    """POST /api/notifications/subscribe stores push subscription and returns 204."""
    subscription = {
        "endpoint": "https://fcm.googleapis.com/fcm/send/test-endpoint-123",
        "expirationTime": None,
        "keys": {
            "p256dh": "test-p256dh-key",
            "auth": "test-auth-key",
        },
    }

    response = await client.post(
        "/api/notifications/subscribe",
        json=subscription,
    )
    assert response.status_code == 204


async def test_subscribe_push_minimal(client: AsyncClient) -> None:
    """POST /api/notifications/subscribe works with minimal subscription data."""
    subscription = {
        "endpoint": "https://push.example.com/send/abc",
        "keys": {"p256dh": "key1", "auth": "key2"},
    }

    response = await client.post(
        "/api/notifications/subscribe",
        json=subscription,
    )
    assert response.status_code == 204


async def test_subscribe_push_unauthenticated(unauthed_client: AsyncClient) -> None:
    """POST /api/notifications/subscribe returns 401 when not authenticated."""
    subscription = {
        "endpoint": "https://push.example.com/send/abc",
        "keys": {"p256dh": "key1", "auth": "key2"},
    }

    response = await unauthed_client.post(
        "/api/notifications/subscribe",
        json=subscription,
    )
    assert response.status_code == 401
