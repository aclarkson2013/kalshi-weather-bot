"""Tests for PrometheusMiddleware and path normalization.

Uses a minimal FastAPI test app with httpx.AsyncClient, matching the
test pattern established in test_middleware.py.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from prometheus_client import make_asgi_app as make_metrics_app

from backend.common.metrics import (
    HTTP_REQUEST_DURATION_SECONDS,
    HTTP_REQUESTS_IN_PROGRESS,
    HTTP_REQUESTS_TOTAL,
)
from backend.common.middleware import PrometheusMiddleware, _normalize_path

# ─── Helpers ───


def _counter_value(counter, labels: dict) -> float:
    """Get the current value of a Counter with the given labels."""
    return counter.labels(**labels)._value.get()


def _histogram_count(histogram, labels: dict) -> int:
    """Get the observation count for a Histogram with the given labels."""
    return histogram.labels(**labels)._sum._value != 0  # noqa: SLF001


def _histogram_sum(histogram, labels: dict) -> float:
    """Get the observation sum for a Histogram with the given labels."""
    return histogram.labels(**labels)._sum.get()


# ─── Test App Factory ───


def _make_metrics_test_app() -> FastAPI:
    """Build a minimal FastAPI app with PrometheusMiddleware."""
    app = FastAPI()
    app.add_middleware(PrometheusMiddleware)

    @app.get("/api/ping")
    async def ping():
        return {"msg": "pong"}

    @app.get("/api/items/{item_id}")
    async def get_item(item_id: str):
        return {"item_id": item_id}

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    @app.get("/ready")
    async def ready():
        return {"status": "ok"}

    # Mount the real metrics ASGI app
    metrics_app = make_metrics_app()
    app.mount("/metrics", metrics_app)

    return app


@pytest.fixture
def test_app() -> FastAPI:
    return _make_metrics_test_app()


@pytest.fixture
async def client(test_app: FastAPI) -> AsyncClient:
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


# ─── Path Normalization Tests ───


class TestNormalizePath:
    def test_static_path_unchanged(self):
        assert _normalize_path("/api/trades") == "/api/trades"

    def test_numeric_id_replaced(self):
        assert _normalize_path("/api/trades/123") == "/api/trades/{id}"

    def test_uuid_replaced(self):
        assert (
            _normalize_path("/api/queue/550e8400-e29b-41d4-a716-446655440000") == "/api/queue/{id}"
        )

    def test_hex_id_replaced(self):
        assert _normalize_path("/api/queue/550e8400e29b41d4a716446655440000") == "/api/queue/{id}"

    def test_nested_dynamic_segments(self):
        assert _normalize_path("/api/queue/123/approve") == "/api/queue/{id}/approve"

    def test_root_path_unchanged(self):
        assert _normalize_path("/") == "/"

    def test_empty_path_handled(self):
        assert _normalize_path("") == ""


# ─── Request Counting Tests ───


class TestPrometheusMiddlewareRequestCounting:
    @pytest.mark.asyncio
    async def test_increments_request_counter(self, client: AsyncClient):
        """After a request, http_requests_total should increment."""
        before = _counter_value(
            HTTP_REQUESTS_TOTAL,
            {"method": "GET", "path_template": "/api/ping", "status_code": "200"},
        )
        resp = await client.get("/api/ping")
        assert resp.status_code == 200

        after = _counter_value(
            HTTP_REQUESTS_TOTAL,
            {"method": "GET", "path_template": "/api/ping", "status_code": "200"},
        )
        assert after - before == 1.0

    @pytest.mark.asyncio
    async def test_labels_include_method_path_status(self, client: AsyncClient):
        """Counter labels should match the request method, path, and status."""
        before = _counter_value(
            HTTP_REQUESTS_TOTAL,
            {"method": "GET", "path_template": "/api/ping", "status_code": "200"},
        )
        await client.get("/api/ping")
        after = _counter_value(
            HTTP_REQUESTS_TOTAL,
            {"method": "GET", "path_template": "/api/ping", "status_code": "200"},
        )
        assert after > before

    @pytest.mark.asyncio
    async def test_404_counted_correctly(self, client: AsyncClient):
        """A 404 response should be counted with status_code='404'."""
        before = _counter_value(
            HTTP_REQUESTS_TOTAL,
            {"method": "GET", "path_template": "/nonexistent", "status_code": "404"},
        )
        resp = await client.get("/nonexistent")
        assert resp.status_code == 404

        after = _counter_value(
            HTTP_REQUESTS_TOTAL,
            {"method": "GET", "path_template": "/nonexistent", "status_code": "404"},
        )
        assert after - before == 1.0

    @pytest.mark.asyncio
    async def test_dynamic_path_normalized_in_labels(self, client: AsyncClient):
        """Path '/api/items/abc123' should be labeled with the normalized path."""
        # /api/items/abc123 doesn't match numeric-only or UUID/hex patterns,
        # so it stays as-is. But /api/items/12345 would normalize.
        before = _counter_value(
            HTTP_REQUESTS_TOTAL,
            {"method": "GET", "path_template": "/api/items/{id}", "status_code": "200"},
        )
        resp = await client.get("/api/items/12345")
        assert resp.status_code == 200

        after = _counter_value(
            HTTP_REQUESTS_TOTAL,
            {"method": "GET", "path_template": "/api/items/{id}", "status_code": "200"},
        )
        assert after - before == 1.0


# ─── Duration Tests ───


class TestPrometheusMiddlewareDuration:
    @pytest.mark.asyncio
    async def test_duration_histogram_observed(self, client: AsyncClient):
        """After a request, the duration histogram should have an observation."""
        before_sum = _histogram_sum(
            HTTP_REQUEST_DURATION_SECONDS,
            {"method": "GET", "path_template": "/api/ping"},
        )
        await client.get("/api/ping")
        after_sum = _histogram_sum(
            HTTP_REQUEST_DURATION_SECONDS,
            {"method": "GET", "path_template": "/api/ping"},
        )
        assert after_sum > before_sum

    @pytest.mark.asyncio
    async def test_duration_is_positive(self, client: AsyncClient):
        """Observed duration should be > 0."""
        before_sum = _histogram_sum(
            HTTP_REQUEST_DURATION_SECONDS,
            {"method": "GET", "path_template": "/api/ping"},
        )
        await client.get("/api/ping")
        after_sum = _histogram_sum(
            HTTP_REQUEST_DURATION_SECONDS,
            {"method": "GET", "path_template": "/api/ping"},
        )
        delta = after_sum - before_sum
        assert delta > 0


# ─── In-Progress Gauge Tests ───


class TestPrometheusMiddlewareInProgress:
    @pytest.mark.asyncio
    async def test_in_progress_gauge_returns_to_zero(self, client: AsyncClient):
        """After request completes, in-progress gauge for the method returns to 0."""
        await client.get("/api/ping")
        value = HTTP_REQUESTS_IN_PROGRESS.labels(method="GET")._value.get()
        assert value == 0.0


# ─── Skip Path Tests ───


class TestPrometheusMiddlewareSkipPaths:
    @pytest.mark.asyncio
    async def test_health_not_counted(self, client: AsyncClient):
        """Requests to /health should not increment metrics."""
        before = _counter_value(
            HTTP_REQUESTS_TOTAL,
            {"method": "GET", "path_template": "/health", "status_code": "200"},
        )
        await client.get("/health")
        after = _counter_value(
            HTTP_REQUESTS_TOTAL,
            {"method": "GET", "path_template": "/health", "status_code": "200"},
        )
        assert after == before

    @pytest.mark.asyncio
    async def test_ready_not_counted(self, client: AsyncClient):
        """Requests to /ready should not increment metrics."""
        before = _counter_value(
            HTTP_REQUESTS_TOTAL,
            {"method": "GET", "path_template": "/ready", "status_code": "200"},
        )
        await client.get("/ready")
        after = _counter_value(
            HTTP_REQUESTS_TOTAL,
            {"method": "GET", "path_template": "/ready", "status_code": "200"},
        )
        assert after == before

    @pytest.mark.asyncio
    async def test_metrics_not_counted(self, client: AsyncClient):
        """Requests to /metrics should not instrument themselves."""
        before = _counter_value(
            HTTP_REQUESTS_TOTAL,
            {"method": "GET", "path_template": "/metrics", "status_code": "200"},
        )
        await client.get("/metrics")
        after = _counter_value(
            HTTP_REQUESTS_TOTAL,
            {"method": "GET", "path_template": "/metrics", "status_code": "200"},
        )
        assert after == before


# ─── Metrics Endpoint Integration ───


class TestMetricsEndpointIntegration:
    @pytest.mark.asyncio
    async def test_metrics_endpoint_returns_200(self, client: AsyncClient):
        """GET /metrics/ should return 200 with Prometheus text format.

        FastAPI's mount() redirects /metrics → /metrics/ (307), so we use
        the trailing slash directly.
        """
        resp = await client.get("/metrics/")
        assert resp.status_code == 200
        # Prometheus text format contains metric names
        body = resp.text
        assert "http_requests_total" in body or "app_info" in body
