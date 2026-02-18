"""Tests for the logs API endpoint."""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.api.conftest import make_log_entry

pytestmark = pytest.mark.asyncio


async def test_logs_empty(client: AsyncClient) -> None:
    """GET /api/logs returns empty list when no log entries exist."""
    response = await client.get("/api/logs")
    assert response.status_code == 200
    assert response.json() == []


async def test_logs_returns_entries(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    """GET /api/logs returns log entries ordered by timestamp desc."""
    entry1 = make_log_entry(module_tag="TRADING", level="INFO", message="Trade placed")
    entry2 = make_log_entry(module_tag="ORDER", level="ERROR", message="Order failed")
    db.add(entry1)
    db.add(entry2)
    await db.flush()

    response = await client.get("/api/logs")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2


async def test_logs_module_filter(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    """GET /api/logs?module=TRADING filters by module tag."""
    trading_entry = make_log_entry(module_tag="TRADING", message="Trade placed")
    order_entry = make_log_entry(module_tag="ORDER", message="Order sent")
    db.add(trading_entry)
    db.add(order_entry)
    await db.flush()

    response = await client.get("/api/logs", params={"module": "TRADING"})
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["module"] == "TRADING"


async def test_logs_level_filter(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    """GET /api/logs?level=ERROR filters by log level."""
    info_entry = make_log_entry(level="INFO", message="Normal operation")
    error_entry = make_log_entry(level="ERROR", message="Something broke")
    db.add(info_entry)
    db.add(error_entry)
    await db.flush()

    response = await client.get("/api/logs", params={"level": "ERROR"})
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["level"] == "ERROR"


async def test_logs_after_filter(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    """GET /api/logs?after=<timestamp> filters by timestamp."""
    entry = make_log_entry(message="Recent log")
    db.add(entry)
    await db.flush()

    # Use a future date to get no results
    response = await client.get(
        "/api/logs",
        params={"after": "2099-01-01T00:00:00"},
    )
    assert response.status_code == 200
    assert response.json() == []


async def test_logs_unauthenticated(unauthed_client: AsyncClient) -> None:
    """GET /api/logs returns 401 when not authenticated."""
    response = await unauthed_client.get("/api/logs")
    assert response.status_code == 401
