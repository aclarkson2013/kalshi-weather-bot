"""Tests for health and readiness endpoints.

The /health endpoint is a simple liveness probe (process is running).
The /ready endpoint verifies database and Redis connectivity.
"""

from __future__ import annotations

import contextlib
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from backend.main import app


@pytest.fixture
async def bare_client() -> AsyncClient:
    """Client with no dependency overrides — tests /health and /ready directly."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@contextlib.asynccontextmanager
async def _mock_connect():
    """Async context manager that simulates a successful DB connection."""
    mock_conn = AsyncMock()
    yield mock_conn


def _healthy_engine() -> MagicMock:
    """Engine mock whose .connect() returns a working async context manager."""
    engine = MagicMock()
    engine.connect = _mock_connect
    return engine


def _healthy_redis() -> AsyncMock:
    """Redis mock that responds to ping."""
    r = AsyncMock()
    r.ping = AsyncMock(return_value=True)
    r.aclose = AsyncMock()
    return r


# ─── Liveness Probe ───


class TestHealthEndpoint:
    @pytest.mark.asyncio
    async def test_health_returns_200(self, bare_client: AsyncClient):
        resp = await bare_client.get("/health")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_health_includes_status_and_version(self, bare_client: AsyncClient):
        resp = await bare_client.get("/health")
        body = resp.json()
        assert body["status"] == "ok"
        assert body["version"] == "0.1.0"


# ─── Readiness Probe ───


class TestReadinessEndpoint:
    @pytest.mark.asyncio
    async def test_ready_200_when_all_healthy(self, bare_client: AsyncClient):
        with (
            patch(
                "backend.common.database._get_engine",
                return_value=_healthy_engine(),
            ),
            patch("redis.asyncio.from_url", return_value=_healthy_redis()),
        ):
            resp = await bare_client.get("/ready")

        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "ok"
        assert body["checks"]["database"] == "ok"
        assert body["checks"]["redis"] == "ok"

    @pytest.mark.asyncio
    async def test_ready_503_when_db_down(self, bare_client: AsyncClient):
        bad_engine = MagicMock()
        bad_engine.connect.side_effect = ConnectionRefusedError("db down")

        with (
            patch(
                "backend.common.database._get_engine",
                return_value=bad_engine,
            ),
            patch("redis.asyncio.from_url", return_value=_healthy_redis()),
        ):
            resp = await bare_client.get("/ready")

        assert resp.status_code == 503
        body = resp.json()
        assert body["status"] == "degraded"
        assert "error" in body["checks"]["database"]

    @pytest.mark.asyncio
    async def test_ready_503_when_redis_down(self, bare_client: AsyncClient):
        with (
            patch(
                "backend.common.database._get_engine",
                return_value=_healthy_engine(),
            ),
            patch(
                "redis.asyncio.from_url",
                side_effect=ConnectionRefusedError("redis down"),
            ),
        ):
            resp = await bare_client.get("/ready")

        assert resp.status_code == 503
        body = resp.json()
        assert body["status"] == "degraded"
        assert body["checks"]["database"] == "ok"
        assert "error" in body["checks"]["redis"]

    @pytest.mark.asyncio
    async def test_ready_503_when_both_down(self, bare_client: AsyncClient):
        bad_engine = MagicMock()
        bad_engine.connect.side_effect = ConnectionRefusedError("db down")

        with (
            patch(
                "backend.common.database._get_engine",
                return_value=bad_engine,
            ),
            patch(
                "redis.asyncio.from_url",
                side_effect=ConnectionRefusedError("redis down"),
            ),
        ):
            resp = await bare_client.get("/ready")

        assert resp.status_code == 503
        body = resp.json()
        assert body["status"] == "degraded"
        assert "error" in body["checks"]["database"]
        assert "error" in body["checks"]["redis"]

    @pytest.mark.asyncio
    async def test_ready_includes_version(self, bare_client: AsyncClient):
        with (
            patch(
                "backend.common.database._get_engine",
                return_value=_healthy_engine(),
            ),
            patch("redis.asyncio.from_url", return_value=_healthy_redis()),
        ):
            resp = await bare_client.get("/ready")

        body = resp.json()
        assert body["version"] == "0.1.0"
