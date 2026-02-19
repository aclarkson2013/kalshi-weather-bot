"""Tests for auth status endpoint, demo mode integration, and full onboarding flow.

Tests cover:
- GET /api/auth/status — authentication status check
- POST /api/auth/validate — demo_mode parameter handling
- Demo mode wiring through settings and KalshiClient dependency
- Full onboarding flow: validate → status → settings → disconnect
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from backend.kalshi.exceptions import KalshiAuthError

pytestmark = pytest.mark.asyncio


# ─── TestAuthStatus ───


class TestAuthStatus:
    """Test GET /api/auth/status endpoint."""

    async def test_status_returns_authenticated(self, client: AsyncClient) -> None:
        """Authenticated user → 200 with authenticated=True."""
        response = await client.get("/api/auth/status")
        assert response.status_code == 200
        data = response.json()
        assert data["authenticated"] is True

    async def test_status_returns_user_id(self, client: AsyncClient) -> None:
        """Response includes the correct user_id."""
        response = await client.get("/api/auth/status")
        assert response.status_code == 200
        data = response.json()
        assert data["user_id"] == "test-user-001"

    async def test_status_returns_demo_mode(self, client: AsyncClient) -> None:
        """Response includes demo_mode field."""
        response = await client.get("/api/auth/status")
        assert response.status_code == 200
        data = response.json()
        assert "demo_mode" in data
        assert isinstance(data["demo_mode"], bool)

    async def test_status_returns_key_id_prefix(self, client: AsyncClient) -> None:
        """Key ID is truncated to first 8 chars + '...'."""
        response = await client.get("/api/auth/status")
        assert response.status_code == 200
        data = response.json()
        assert data["key_id_prefix"] == "test-key..."

    async def test_status_unauthenticated_returns_401(self, unauthed_client: AsyncClient) -> None:
        """No user in DB → 401."""
        response = await unauthed_client.get("/api/auth/status")
        assert response.status_code == 401


# ─── TestValidateWithDemoMode ───


class TestValidateWithDemoMode:
    """Test POST /api/auth/validate with demo_mode parameter."""

    async def test_validate_defaults_to_demo_mode(
        self, client: AsyncClient, db: AsyncSession
    ) -> None:
        """No demo_mode param → user.demo_mode=True (safe default)."""
        mock_client_instance = AsyncMock()
        mock_client_instance.get_balance.return_value = 500.0
        mock_client_instance.close.return_value = None

        with patch("backend.api.auth.KalshiClient", return_value=mock_client_instance):
            response = await client.post(
                "/api/auth/validate",
                json={"key_id": "new-key-id-default", "private_key": "new-pem"},
            )

        assert response.status_code == 200
        data = response.json()
        assert data["demo_mode"] is True

    async def test_validate_with_demo_false(self, client: AsyncClient, db: AsyncSession) -> None:
        """Explicit demo_mode=false → user.demo_mode=False."""
        mock_client_instance = AsyncMock()
        mock_client_instance.get_balance.return_value = 300.0
        mock_client_instance.close.return_value = None

        with patch("backend.api.auth.KalshiClient", return_value=mock_client_instance):
            response = await client.post(
                "/api/auth/validate",
                json={
                    "key_id": "prod-key-id-live",
                    "private_key": "prod-pem",
                    "demo_mode": False,
                },
            )

        assert response.status_code == 200
        data = response.json()
        assert data["demo_mode"] is False

    async def test_validate_passes_demo_to_test_client(
        self, client: AsyncClient, db: AsyncSession
    ) -> None:
        """KalshiClient is created with demo= matching the request's demo_mode."""
        mock_client_instance = AsyncMock()
        mock_client_instance.get_balance.return_value = 100.0
        mock_client_instance.close.return_value = None

        with patch("backend.api.auth.KalshiClient", return_value=mock_client_instance) as mock_cls:
            await client.post(
                "/api/auth/validate",
                json={
                    "key_id": "test-key-demo-check",
                    "private_key": "test-pem",
                    "demo_mode": True,
                },
            )

        # Verify KalshiClient was called with demo=True
        mock_cls.assert_called_once()
        call_kwargs = mock_cls.call_args
        assert call_kwargs.kwargs.get("demo") is True or call_kwargs[1].get("demo") is True

    async def test_validate_response_includes_balance(
        self, client: AsyncClient, db: AsyncSession
    ) -> None:
        """Response includes balance_cents from Kalshi API."""
        mock_client_instance = AsyncMock()
        mock_client_instance.get_balance.return_value = 750.50
        mock_client_instance.close.return_value = None

        with patch("backend.api.auth.KalshiClient", return_value=mock_client_instance):
            response = await client.post(
                "/api/auth/validate",
                json={"key_id": "balance-check", "private_key": "test-pem"},
            )

        assert response.status_code == 200
        data = response.json()
        assert data["balance_cents"] == 75050
        assert data["valid"] is True


# ─── TestDemoModeIntegration ───


class TestDemoModeIntegration:
    """Test demo_mode wiring across settings and dependencies."""

    async def test_settings_get_includes_demo_mode(self, client: AsyncClient) -> None:
        """GET /api/settings returns demo_mode field."""
        response = await client.get("/api/settings")
        assert response.status_code == 200
        data = response.json()
        assert "demo_mode" in data
        assert isinstance(data["demo_mode"], bool)

    async def test_settings_patch_updates_demo_mode(self, client: AsyncClient) -> None:
        """PATCH /api/settings with demo_mode updates the value."""
        response = await client.patch(
            "/api/settings",
            json={"demo_mode": False},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["demo_mode"] is False

    async def test_settings_patch_demo_mode_reflects_in_get(self, client: AsyncClient) -> None:
        """PATCH demo_mode=False → subsequent GET returns False."""
        await client.patch("/api/settings", json={"demo_mode": False})

        response = await client.get("/api/settings")
        assert response.status_code == 200
        assert response.json()["demo_mode"] is False

    async def test_default_demo_mode_is_true(self, client: AsyncClient) -> None:
        """New user starts with demo_mode=True (safe default)."""
        response = await client.get("/api/settings")
        assert response.status_code == 200
        assert response.json()["demo_mode"] is True


# ─── TestFullOnboardingFlow ───


class TestFullOnboardingFlow:
    """Test the complete onboarding flow end-to-end (with mocked Kalshi)."""

    async def test_fresh_system_returns_401(self, unauthed_client: AsyncClient) -> None:
        """No user in DB → dashboard, settings, and status all return 401."""
        for endpoint in ["/api/dashboard", "/api/settings", "/api/auth/status"]:
            response = await unauthed_client.get(endpoint)
            assert response.status_code == 401, f"{endpoint} should return 401"

    async def test_validate_then_status_works(self, client: AsyncClient, db: AsyncSession) -> None:
        """POST /validate → GET /status succeeds with correct data."""
        mock_client_instance = AsyncMock()
        mock_client_instance.get_balance.return_value = 500.0
        mock_client_instance.close.return_value = None

        with patch("backend.api.auth.KalshiClient", return_value=mock_client_instance):
            validate_resp = await client.post(
                "/api/auth/validate",
                json={"key_id": "onboard-key-12345", "private_key": "onboard-pem"},
            )

        assert validate_resp.status_code == 200
        assert validate_resp.json()["valid"] is True

        # Auth status should work now
        status_resp = await client.get("/api/auth/status")
        assert status_resp.status_code == 200
        assert status_resp.json()["authenticated"] is True

    async def test_validate_then_settings_works(
        self, client: AsyncClient, db: AsyncSession
    ) -> None:
        """POST /validate → GET /settings succeeds with defaults."""
        mock_client_instance = AsyncMock()
        mock_client_instance.get_balance.return_value = 200.0
        mock_client_instance.close.return_value = None

        with patch("backend.api.auth.KalshiClient", return_value=mock_client_instance):
            await client.post(
                "/api/auth/validate",
                json={"key_id": "settings-key-12345", "private_key": "settings-pem"},
            )

        settings_resp = await client.get("/api/settings")
        assert settings_resp.status_code == 200
        data = settings_resp.json()
        assert "trading_mode" in data
        assert "demo_mode" in data

    async def test_validate_invalid_credentials_returns_401(self, client: AsyncClient) -> None:
        """POST /validate with bad credentials → 401."""
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
