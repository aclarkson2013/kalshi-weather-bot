"""E2E smoke tests — full request lifecycle through the real FastAPI app.

These tests exercise the real middleware stack, real auth path, and real
database queries. Only external APIs (Kalshi) are mocked.

Run:  python -m pytest tests/e2e/ -x -v --tb=short
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from backend.common.middleware import SecurityHeadersMiddleware

from .conftest import (
    seed_logs,
    seed_pending_trades,
    seed_predictions,
    seed_trades,
)

pytestmark = pytest.mark.e2e


# ─── Health & Readiness ───


class TestHealthAndReadiness:
    """Verify liveness, readiness, and metrics endpoints."""

    async def test_health_returns_ok(self, authed_client: AsyncClient) -> None:
        """GET /health returns 200 with version string."""
        resp = await authed_client.get("/health")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "ok"
        assert "version" in body

    async def test_ready_returns_checks(self, authed_client: AsyncClient) -> None:
        """GET /ready returns a response with checks dict (may be degraded in test)."""
        resp = await authed_client.get("/ready")
        body = resp.json()
        # The endpoint may return 200 or 503 in test env (no real Postgres/Redis)
        assert resp.status_code in (200, 503)
        assert "checks" in body
        assert "database" in body["checks"]

    async def test_metrics_returns_prometheus_format(self, authed_client: AsyncClient) -> None:
        """GET /metrics/ returns Prometheus text format."""
        resp = await authed_client.get("/metrics/")
        assert resp.status_code == 200
        # Prometheus text format contains metric names
        text = resp.text
        assert "http_requests_total" in text or "boz_" in text or "python_" in text


# ─── Middleware Integration ───


class TestMiddlewareIntegration:
    """Verify middleware stack runs on real requests."""

    async def test_request_id_header_present(self, authed_client: AsyncClient) -> None:
        """Every response includes X-Request-ID."""
        resp = await authed_client.get("/health")
        assert "X-Request-ID" in resp.headers
        assert len(resp.headers["X-Request-ID"]) > 0

    async def test_request_id_is_unique(self, authed_client: AsyncClient) -> None:
        """Two requests get different X-Request-ID values."""
        r1 = await authed_client.get("/health")
        r2 = await authed_client.get("/health")
        assert r1.headers["X-Request-ID"] != r2.headers["X-Request-ID"]

    async def test_security_headers_present(self, authed_client: AsyncClient) -> None:
        """All 7 OWASP security headers are present."""
        resp = await authed_client.get("/health")
        for header_name in SecurityHeadersMiddleware.HEADERS:
            assert header_name in resp.headers, f"Missing header: {header_name}"

    async def test_security_header_values_correct(self, authed_client: AsyncClient) -> None:
        """Security header values match the middleware's HEADERS dict."""
        resp = await authed_client.get("/health")
        for header_name, expected_value in SecurityHeadersMiddleware.HEADERS.items():
            assert resp.headers[header_name] == expected_value


# ─── Auth Flow ───


class TestAuthFlow:
    """Verify the real authentication path."""

    async def test_unauthenticated_dashboard_returns_401(self, bare_client: AsyncClient) -> None:
        """GET /api/dashboard with no user in DB returns 401."""
        resp = await bare_client.get("/api/dashboard")
        assert resp.status_code == 401

    async def test_unauthenticated_settings_returns_401(self, bare_client: AsyncClient) -> None:
        """GET /api/settings with no user in DB returns 401."""
        resp = await bare_client.get("/api/settings")
        assert resp.status_code == 401

    async def test_unauthenticated_trades_returns_401(self, bare_client: AsyncClient) -> None:
        """GET /api/trades with no user in DB returns 401."""
        resp = await bare_client.get("/api/trades")
        assert resp.status_code == 401

    async def test_authenticated_after_user_created(self, authed_client: AsyncClient) -> None:
        """GET /api/settings succeeds when user exists in DB (real auth path)."""
        resp = await authed_client.get("/api/settings")
        assert resp.status_code == 200


# ─── Dashboard ───


class TestDashboard:
    """Verify the dashboard endpoint returns structured data."""

    async def test_dashboard_returns_structured_data(self, authed_client: AsyncClient) -> None:
        """GET /api/dashboard returns expected top-level keys."""
        resp = await authed_client.get("/api/dashboard")
        assert resp.status_code == 200
        body = resp.json()
        assert "balance_cents" in body
        assert "today_pnl_cents" in body
        assert "active_positions" in body
        assert "recent_trades" in body
        assert "predictions" in body

    async def test_dashboard_includes_predictions(
        self, authed_client: AsyncClient, e2e_db, e2e_user
    ) -> None:
        """Dashboard includes predictions when data is seeded."""
        await seed_predictions(e2e_db)
        resp = await authed_client.get("/api/dashboard")
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["predictions"]) > 0

    async def test_dashboard_includes_recent_trades(
        self, authed_client: AsyncClient, e2e_db, e2e_user
    ) -> None:
        """Dashboard includes recent trades when data is seeded."""
        await seed_trades(e2e_db, e2e_user.id, include_settled=True)
        resp = await authed_client.get("/api/dashboard")
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["recent_trades"]) > 0


# ─── Settings ───


class TestSettings:
    """Verify settings CRUD through the real auth path."""

    async def test_get_settings_returns_defaults(self, authed_client: AsyncClient) -> None:
        """GET /api/settings returns all expected fields."""
        resp = await authed_client.get("/api/settings")
        assert resp.status_code == 200
        body = resp.json()
        assert "trading_mode" in body
        assert "max_trade_size_cents" in body
        assert "daily_loss_limit_cents" in body
        assert "active_cities" in body
        assert "notifications_enabled" in body

    async def test_patch_settings_updates_trading_mode(self, authed_client: AsyncClient) -> None:
        """PATCH /api/settings updates trading_mode."""
        resp = await authed_client.patch("/api/settings", json={"trading_mode": "auto"})
        assert resp.status_code == 200
        assert resp.json()["trading_mode"] == "auto"

    async def test_patch_settings_updates_risk_limits(self, authed_client: AsyncClient) -> None:
        """PATCH /api/settings updates max_trade_size_cents."""
        resp = await authed_client.patch("/api/settings", json={"max_trade_size_cents": 200})
        assert resp.status_code == 200
        assert resp.json()["max_trade_size_cents"] == 200

    async def test_get_settings_reflects_patch(self, authed_client: AsyncClient) -> None:
        """PATCH then GET returns the updated values."""
        await authed_client.patch(
            "/api/settings", json={"trading_mode": "auto", "max_trade_size_cents": 300}
        )
        resp = await authed_client.get("/api/settings")
        assert resp.status_code == 200
        body = resp.json()
        assert body["trading_mode"] == "auto"
        assert body["max_trade_size_cents"] == 300


# ─── Markets ───


class TestMarkets:
    """Verify the markets endpoint returns prediction data."""

    async def test_markets_returns_predictions(
        self, authed_client: AsyncClient, e2e_db, e2e_user
    ) -> None:
        """GET /api/markets returns predictions when data exists."""
        await seed_predictions(e2e_db)
        resp = await authed_client.get("/api/markets")
        assert resp.status_code == 200
        body = resp.json()
        assert isinstance(body, list)
        assert len(body) > 0

    async def test_markets_filter_by_city(
        self, authed_client: AsyncClient, e2e_db, e2e_user
    ) -> None:
        """GET /api/markets?city=NYC returns only NYC predictions."""
        await seed_predictions(e2e_db)
        resp = await authed_client.get("/api/markets", params={"city": "NYC"})
        assert resp.status_code == 200
        body = resp.json()
        assert isinstance(body, list)
        for pred in body:
            assert pred["city"] == "NYC"


# ─── Trades ───


class TestTrades:
    """Verify the trades endpoint with pagination and filtering."""

    async def test_trades_empty_initially(self, authed_client: AsyncClient) -> None:
        """GET /api/trades returns empty list with zero total."""
        resp = await authed_client.get("/api/trades")
        assert resp.status_code == 200
        body = resp.json()
        assert body["trades"] == []
        assert body["total"] == 0

    async def test_trades_with_data(self, authed_client: AsyncClient, e2e_db, e2e_user) -> None:
        """GET /api/trades returns non-empty list after seeding."""
        await seed_trades(e2e_db, e2e_user.id)
        resp = await authed_client.get("/api/trades")
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["trades"]) > 0
        assert body["total"] > 0

    async def test_trades_filter_by_city(
        self, authed_client: AsyncClient, e2e_db, e2e_user
    ) -> None:
        """GET /api/trades?city=NYC returns only NYC trades."""
        await seed_trades(e2e_db, e2e_user.id)
        resp = await authed_client.get("/api/trades", params={"city": "NYC"})
        assert resp.status_code == 200
        body = resp.json()
        for trade in body["trades"]:
            assert trade["city"] == "NYC"


# ─── Trade Queue ───


class TestTradeQueue:
    """Verify the trade queue endpoints."""

    async def test_queue_empty_initially(self, authed_client: AsyncClient) -> None:
        """GET /api/queue returns empty list when no pending trades."""
        resp = await authed_client.get("/api/queue")
        assert resp.status_code == 200
        body = resp.json()
        assert isinstance(body, list)
        assert len(body) == 0

    async def test_queue_with_pending_trades(
        self, authed_client: AsyncClient, e2e_db, e2e_user
    ) -> None:
        """GET /api/queue returns pending trades after seeding."""
        await seed_pending_trades(e2e_db, e2e_user.id)
        resp = await authed_client.get("/api/queue")
        assert resp.status_code == 200
        body = resp.json()
        assert len(body) > 0

    async def test_queue_reject_trade(self, authed_client: AsyncClient, e2e_db, e2e_user) -> None:
        """POST /api/queue/{id}/reject returns 204."""
        pending = await seed_pending_trades(e2e_db, e2e_user.id, count=1)
        trade_id = pending[0].id
        resp = await authed_client.post(f"/api/queue/{trade_id}/reject")
        assert resp.status_code == 204

    async def test_queue_reject_nonexistent_returns_404(self, authed_client: AsyncClient) -> None:
        """POST /api/queue/nonexistent/reject returns 404."""
        resp = await authed_client.post("/api/queue/nonexistent-id/reject")
        assert resp.status_code == 404


# ─── Logs ───


class TestLogs:
    """Verify the logs endpoint with filtering."""

    async def test_logs_returns_entries(self, authed_client: AsyncClient, e2e_db, e2e_user) -> None:
        """GET /api/logs returns log entries after seeding."""
        await seed_logs(e2e_db)
        resp = await authed_client.get("/api/logs")
        assert resp.status_code == 200
        body = resp.json()
        assert isinstance(body, list)
        assert len(body) > 0

    async def test_logs_filter_by_module(
        self, authed_client: AsyncClient, e2e_db, e2e_user
    ) -> None:
        """GET /api/logs?module=TRADING returns only TRADING entries."""
        await seed_logs(e2e_db)
        resp = await authed_client.get("/api/logs", params={"module": "TRADING"})
        assert resp.status_code == 200
        body = resp.json()
        for entry in body:
            assert entry["module"] == "TRADING"

    async def test_logs_filter_by_level(self, authed_client: AsyncClient, e2e_db, e2e_user) -> None:
        """GET /api/logs?level=ERROR returns only ERROR entries."""
        await seed_logs(e2e_db)
        resp = await authed_client.get("/api/logs", params={"level": "ERROR"})
        assert resp.status_code == 200
        body = resp.json()
        for entry in body:
            assert entry["level"] == "ERROR"


# ─── Performance ───


class TestPerformance:
    """Verify the performance analytics endpoint."""

    async def test_performance_empty(self, authed_client: AsyncClient) -> None:
        """GET /api/performance with no trades returns zero totals."""
        resp = await authed_client.get("/api/performance")
        assert resp.status_code == 200
        body = resp.json()
        assert body["total_trades"] == 0
        assert body["wins"] == 0
        assert body["losses"] == 0

    async def test_performance_with_settled_trades(
        self, authed_client: AsyncClient, e2e_db, e2e_user
    ) -> None:
        """GET /api/performance with WON/LOST trades returns non-zero values."""
        await seed_trades(e2e_db, e2e_user.id, include_settled=True)
        resp = await authed_client.get("/api/performance")
        assert resp.status_code == 200
        body = resp.json()
        assert body["total_trades"] > 0
        assert body["wins"] + body["losses"] == body["total_trades"]
        assert "total_pnl_cents" in body


# ─── Error Handling ───


class TestErrorHandling:
    """Verify error responses are structured and include request IDs."""

    async def test_404_for_unknown_route(self, authed_client: AsyncClient) -> None:
        """GET /api/nonexistent returns 404."""
        resp = await authed_client.get("/api/nonexistent")
        assert resp.status_code == 404

    async def test_error_response_has_request_id_header(self, authed_client: AsyncClient) -> None:
        """Error responses still include the X-Request-ID header."""
        resp = await authed_client.get("/api/nonexistent")
        assert "X-Request-ID" in resp.headers

    async def test_401_includes_detail(self, bare_client: AsyncClient) -> None:
        """401 responses include a detail message."""
        resp = await bare_client.get("/api/settings")
        assert resp.status_code == 401
        body = resp.json()
        assert "detail" in body
