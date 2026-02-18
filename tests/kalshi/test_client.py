"""Tests for the main KalshiClient — REST API wrapper with auth and error handling.

Uses unittest.mock to mock httpx.AsyncClient.request and verify that
the client correctly handles various HTTP status codes, converts
responses to models, and maps errors to specific exception types.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from backend.kalshi.client import DEMO_BASE_URL, PROD_BASE_URL, KalshiClient
from backend.kalshi.exceptions import (
    KalshiApiError,
    KalshiAuthError,
    KalshiConnectionError,
    KalshiOrderRejectedError,
    KalshiRateLimitError,
)
from backend.kalshi.models import OrderRequest


def _make_response(
    status_code: int,
    json_data: dict | None = None,
    headers: dict | None = None,
) -> MagicMock:
    """Create a mock httpx.Response with the given status code and JSON body."""
    response = MagicMock(spec=httpx.Response)
    response.status_code = status_code
    response.json.return_value = json_data or {}
    response.text = str(json_data or {})
    response.headers = headers or {}
    return response


class TestKalshiClientInit:
    """Tests for KalshiClient initialization."""

    def test_initializes_with_demo_true_uses_demo_url(self, rsa_key_pair) -> None:
        """KalshiClient with demo=True uses DEMO_BASE_URL."""
        client = KalshiClient(
            api_key_id=rsa_key_pair["api_key_id"],
            private_key_pem=rsa_key_pair["private_key_pem"],
            demo=True,
        )
        assert client.base_url == DEMO_BASE_URL

    def test_initializes_with_demo_false_uses_prod_url(self, rsa_key_pair) -> None:
        """KalshiClient with demo=False uses PROD_BASE_URL."""
        client = KalshiClient(
            api_key_id=rsa_key_pair["api_key_id"],
            private_key_pem=rsa_key_pair["private_key_pem"],
            demo=False,
        )
        assert client.base_url == PROD_BASE_URL


class TestKalshiClientRequest:
    """Tests for KalshiClient._request error mapping."""

    @pytest.fixture
    def client(self, rsa_key_pair):
        """Create a KalshiClient with mocked rate limiter for testing."""
        c = KalshiClient(
            api_key_id=rsa_key_pair["api_key_id"],
            private_key_pem=rsa_key_pair["private_key_pem"],
            demo=True,
        )
        # Mock rate limiter to avoid async timing issues in tests
        c.rate_limiter.acquire = AsyncMock()
        return c

    @pytest.mark.asyncio
    async def test_raises_kalshi_auth_error_on_401(self, client) -> None:
        """_request raises KalshiAuthError on 401 response."""
        mock_response = _make_response(401)
        client.client.request = AsyncMock(return_value=mock_response)

        with pytest.raises(KalshiAuthError, match="Authentication failed"):
            await client._request("GET", "/portfolio/balance")

    @pytest.mark.asyncio
    async def test_raises_kalshi_rate_limit_error_on_429(self, client) -> None:
        """_request raises KalshiRateLimitError on 429 response."""
        mock_response = _make_response(
            429,
            headers={"Retry-After": "5"},
        )
        client.client.request = AsyncMock(return_value=mock_response)

        with pytest.raises(KalshiRateLimitError, match="Rate limit exceeded"):
            await client._request("GET", "/markets")

    @pytest.mark.asyncio
    async def test_raises_kalshi_order_rejected_on_400_for_orders(self, client) -> None:
        """_request raises KalshiOrderRejectedError on 400 for order endpoints."""
        mock_response = _make_response(
            400,
            json_data={"message": "Insufficient balance"},
        )
        client.client.request = AsyncMock(return_value=mock_response)

        with pytest.raises(KalshiOrderRejectedError, match="Insufficient balance"):
            await client._request("POST", "/portfolio/orders")

    @pytest.mark.asyncio
    async def test_raises_kalshi_api_error_on_other_4xx_5xx(self, client) -> None:
        """_request raises KalshiApiError on non-401/429/400 error codes."""
        mock_response = _make_response(
            500,
            json_data={"message": "Internal Server Error"},
        )
        client.client.request = AsyncMock(return_value=mock_response)

        with pytest.raises(KalshiApiError, match="Internal Server Error"):
            await client._request("GET", "/events")

    @pytest.mark.asyncio
    async def test_raises_kalshi_connection_error_on_network_error(self, client) -> None:
        """_request raises KalshiConnectionError on httpx.RequestError."""
        client.client.request = AsyncMock(
            side_effect=httpx.ConnectError("Connection refused"),
        )

        with pytest.raises(KalshiConnectionError, match="Network error"):
            await client._request("GET", "/events")


class TestKalshiClientMethods:
    """Tests for specific KalshiClient business methods."""

    @pytest.fixture
    def client(self, rsa_key_pair):
        """Create a KalshiClient with mocked internals."""
        c = KalshiClient(
            api_key_id=rsa_key_pair["api_key_id"],
            private_key_pem=rsa_key_pair["private_key_pem"],
            demo=True,
        )
        c.rate_limiter.acquire = AsyncMock()
        return c

    @pytest.mark.asyncio
    async def test_get_balance_converts_cents_to_dollars(self, client) -> None:
        """get_balance converts API balance (cents) to dollars."""
        mock_response = _make_response(200, json_data={"balance": 50000})
        client.client.request = AsyncMock(return_value=mock_response)

        balance = await client.get_balance()
        assert balance == 500.0

    @pytest.mark.asyncio
    async def test_close_calls_aclose(self, client) -> None:
        """close() calls the underlying httpx client's aclose()."""
        client.client.aclose = AsyncMock()

        await client.close()
        client.client.aclose.assert_called_once()

    @pytest.mark.asyncio
    async def test_place_order_calls_validate_for_submission(self, client) -> None:
        """place_order calls validate_for_submission before sending the request."""
        order = OrderRequest(
            ticker="KXHIGHNY-26FEB18-T52",
            action="buy",
            side="yes",
            type="limit",
            count=1,
            yes_price=22,
        )

        mock_response = _make_response(
            200,
            json_data={
                "order": {
                    "order_id": "abc-123",
                    "ticker": "KXHIGHNY-26FEB18-T52",
                    "action": "buy",
                    "side": "yes",
                    "type": "limit",
                    "count": 1,
                    "yes_price": 22,
                    "status": "resting",
                    "created_time": "2026-02-17T10:05:00Z",
                }
            },
        )
        client.client.request = AsyncMock(return_value=mock_response)

        response = await client.place_order(order)
        assert response.order_id == "abc-123"
        assert response.status == "resting"

    @pytest.mark.asyncio
    async def test_place_order_rejects_empty_ticker(self, client) -> None:
        """place_order raises ValueError for empty ticker via validate_for_submission."""
        order = OrderRequest(
            ticker="   ",
            action="buy",
            side="yes",
            type="limit",
            count=1,
            yes_price=22,
        )

        with pytest.raises(ValueError, match="ticker"):
            await client.place_order(order)
