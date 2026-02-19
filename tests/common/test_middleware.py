"""Tests for production middleware — request ID, request logging, security headers.

Uses a minimal FastAPI test app to exercise each middleware class in isolation
and together, following the same httpx.AsyncClient + ASGITransport pattern
used in the existing API test suite.
"""

from __future__ import annotations

import re
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from backend.common.middleware import (
    RequestIdMiddleware,
    RequestLoggingMiddleware,
    SecurityHeadersMiddleware,
    request_id_var,
)

# ─── Test App Factory ───


def _make_app() -> FastAPI:
    """Build a minimal FastAPI app with all three middleware registered."""
    app = FastAPI()

    # Same order as production (last added = outermost = runs first)
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(RequestLoggingMiddleware)
    app.add_middleware(RequestIdMiddleware)

    @app.get("/ping")
    async def ping():
        return {"msg": "pong"}

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    @app.get("/ready")
    async def ready():
        return {"status": "ok"}

    @app.get("/rid")
    async def return_request_id():
        """Echo the ContextVar request ID back to the caller."""
        return {"request_id": request_id_var.get("")}

    return app


@pytest.fixture
def test_app() -> FastAPI:
    return _make_app()


@pytest.fixture
async def client(test_app: FastAPI) -> AsyncClient:
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


# ─── RequestIdMiddleware Tests ───


class TestRequestIdMiddleware:
    @pytest.mark.asyncio
    async def test_generates_uuid_when_no_header(self, client: AsyncClient):
        resp = await client.get("/ping")
        rid = resp.headers.get("x-request-id")
        assert rid is not None
        assert len(rid) == 32  # uuid4().hex is 32 hex chars

    @pytest.mark.asyncio
    async def test_preserves_provided_request_id(self, client: AsyncClient):
        custom_id = "my-trace-id-12345"
        resp = await client.get("/ping", headers={"X-Request-ID": custom_id})
        assert resp.headers["x-request-id"] == custom_id

    @pytest.mark.asyncio
    async def test_response_always_has_request_id_header(self, client: AsyncClient):
        resp = await client.get("/ping")
        assert "x-request-id" in resp.headers

    @pytest.mark.asyncio
    async def test_context_var_set_during_request(self, client: AsyncClient):
        custom_id = "ctx-var-test-abc"
        resp = await client.get("/rid", headers={"X-Request-ID": custom_id})
        data = resp.json()
        assert data["request_id"] == custom_id

    @pytest.mark.asyncio
    async def test_generated_id_is_hex(self, client: AsyncClient):
        resp = await client.get("/ping")
        rid = resp.headers["x-request-id"]
        assert re.fullmatch(r"[0-9a-f]{32}", rid)


# ─── RequestLoggingMiddleware Tests ───


class TestRequestLoggingMiddleware:
    @pytest.mark.asyncio
    async def test_logs_method_path_status(self, client: AsyncClient):
        with patch("backend.common.middleware.logger") as mock_logger:
            resp = await client.get("/ping")
            assert resp.status_code == 200

            mock_logger.info.assert_called_once()
            call_args = mock_logger.info.call_args
            log_msg = call_args[0][0]
            assert "GET" in log_msg
            assert "/ping" in log_msg
            assert "200" in log_msg

    @pytest.mark.asyncio
    async def test_log_data_includes_duration(self, client: AsyncClient):
        with patch("backend.common.middleware.logger") as mock_logger:
            await client.get("/ping")
            call_args = mock_logger.info.call_args
            data = call_args[1]["extra"]["data"]
            assert "duration_ms" in data
            assert data["duration_ms"] >= 0

    @pytest.mark.asyncio
    async def test_skips_health_endpoint(self, client: AsyncClient):
        with patch("backend.common.middleware.logger") as mock_logger:
            await client.get("/health")
            mock_logger.info.assert_not_called()

    @pytest.mark.asyncio
    async def test_skips_ready_endpoint(self, client: AsyncClient):
        with patch("backend.common.middleware.logger") as mock_logger:
            await client.get("/ready")
            mock_logger.info.assert_not_called()

    @pytest.mark.asyncio
    async def test_logs_404_status(self, client: AsyncClient):
        with patch("backend.common.middleware.logger") as mock_logger:
            resp = await client.get("/nonexistent")
            assert resp.status_code == 404

            call_args = mock_logger.info.call_args
            log_msg = call_args[0][0]
            assert "404" in log_msg


# ─── SecurityHeadersMiddleware Tests ───


class TestSecurityHeadersMiddleware:
    @pytest.mark.asyncio
    async def test_x_content_type_options(self, client: AsyncClient):
        resp = await client.get("/ping")
        assert resp.headers["x-content-type-options"] == "nosniff"

    @pytest.mark.asyncio
    async def test_x_frame_options(self, client: AsyncClient):
        resp = await client.get("/ping")
        assert resp.headers["x-frame-options"] == "DENY"

    @pytest.mark.asyncio
    async def test_strict_transport_security(self, client: AsyncClient):
        resp = await client.get("/ping")
        assert "max-age=31536000" in resp.headers["strict-transport-security"]

    @pytest.mark.asyncio
    async def test_referrer_policy(self, client: AsyncClient):
        resp = await client.get("/ping")
        assert resp.headers["referrer-policy"] == "strict-origin-when-cross-origin"

    @pytest.mark.asyncio
    async def test_permissions_policy(self, client: AsyncClient):
        resp = await client.get("/ping")
        assert "camera=()" in resp.headers["permissions-policy"]

    @pytest.mark.asyncio
    async def test_cache_control(self, client: AsyncClient):
        resp = await client.get("/ping")
        assert resp.headers["cache-control"] == "no-store"

    @pytest.mark.asyncio
    async def test_all_seven_headers_present(self, client: AsyncClient):
        resp = await client.get("/ping")
        expected = {
            "x-content-type-options",
            "x-frame-options",
            "x-xss-protection",
            "strict-transport-security",
            "referrer-policy",
            "permissions-policy",
            "cache-control",
        }
        for header in expected:
            assert header in resp.headers, f"Missing header: {header}"

    @pytest.mark.asyncio
    async def test_headers_present_on_health_endpoint(self, client: AsyncClient):
        resp = await client.get("/health")
        assert resp.headers["x-content-type-options"] == "nosniff"
        assert resp.headers["x-frame-options"] == "DENY"
