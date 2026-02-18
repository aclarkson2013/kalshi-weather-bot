"""Tests for the NWS API client.

Tests fetch_with_retry (success, retries, exhaustion, network errors),
get_grid_coordinates (parsing, caching), and URL builders.
Uses pytest-httpx for HTTP mocking and unittest.mock for rate limiter/sleep bypassing.

IMPORTANT: Grid caches in STATION_CONFIGS are reset between tests to avoid
cross-test pollution. The rate limiter and asyncio.sleep are bypassed so
tests run instantly.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import httpx
import pytest

from backend.weather.exceptions import FetchError, ParseError
from backend.weather.nws import (
    NWS_BASE_URL,
    build_forecast_url,
    build_gridpoint_url,
    fetch_with_retry,
    get_grid_coordinates,
)
from backend.weather.stations import STATION_CONFIGS

# ─── Fixtures ───


@pytest.fixture(autouse=True)
def _reset_grid_cache():
    """Reset all grid caches before each test to avoid cross-test pollution."""
    original_grids = {}
    for city, config in STATION_CONFIGS.items():
        original_grids[city] = config.grid
        config.grid = None
    yield
    # Restore original grids after test
    for city, grid in original_grids.items():
        STATION_CONFIGS[city].grid = grid


@pytest.fixture(autouse=True)
def _bypass_rate_limiter():
    """Bypass the NWS rate limiter so tests run instantly."""
    with patch(
        "backend.weather.nws.nws_limiter.acquire",
        new_callable=AsyncMock,
    ):
        yield


@pytest.fixture(autouse=True)
def _bypass_retry_sleep():
    """Bypass asyncio.sleep in retry logic so tests run instantly."""
    with patch("backend.weather.nws.asyncio.sleep", new_callable=AsyncMock):
        yield


# ─── fetch_with_retry Tests ───


class TestFetchWithRetry:
    """Test the generic HTTP fetch with retry logic."""

    @pytest.mark.asyncio
    async def test_success_on_first_attempt(self, httpx_mock):
        """Successful 200 response on first attempt returns parsed JSON."""
        httpx_mock.add_response(json={"key": "value"})
        result = await fetch_with_retry("https://api.weather.gov/test")
        assert result == {"key": "value"}

    @pytest.mark.asyncio
    async def test_retries_on_500_then_succeeds(self, httpx_mock):
        """HTTP 500 triggers retry; succeeds on second attempt."""
        httpx_mock.add_response(status_code=500)
        httpx_mock.add_response(json={"recovered": True})

        result = await fetch_with_retry(
            "https://api.weather.gov/test",
            max_retries=3,
        )
        assert result == {"recovered": True}

    @pytest.mark.asyncio
    async def test_raises_fetch_error_after_max_retries(self, httpx_mock):
        """Consecutive 500s exhaust retries and raise FetchError."""
        httpx_mock.add_response(status_code=500)
        httpx_mock.add_response(status_code=500)
        httpx_mock.add_response(status_code=500)

        with pytest.raises(FetchError, match="HTTP 500"):
            await fetch_with_retry(
                "https://api.weather.gov/test",
                max_retries=2,  # 3 total attempts
            )

    @pytest.mark.asyncio
    async def test_raises_fetch_error_on_network_error_after_retries(
        self,
        httpx_mock,
    ):
        """Network errors retry and eventually raise FetchError."""
        httpx_mock.add_exception(httpx.ConnectError("Connection refused"))
        httpx_mock.add_exception(httpx.ConnectError("Connection refused"))

        with pytest.raises(FetchError, match="Network error"):
            await fetch_with_retry(
                "https://api.weather.gov/test",
                max_retries=1,  # 2 total attempts
            )

    @pytest.mark.asyncio
    async def test_network_error_recovers_on_retry(self, httpx_mock):
        """Network error on first call, success on retry."""
        httpx_mock.add_exception(httpx.ConnectError("Connection refused"))
        httpx_mock.add_response(json={"ok": True})

        result = await fetch_with_retry(
            "https://api.weather.gov/test",
            max_retries=2,
        )
        assert result == {"ok": True}


# ─── get_grid_coordinates Tests ───


class TestGetGridCoordinates:
    """Test NWS grid coordinate lookup and caching."""

    @pytest.mark.asyncio
    async def test_parses_response_correctly(self, httpx_mock):
        """Correctly parses gridId, gridX, gridY from NWS points response."""
        httpx_mock.add_response(
            json={
                "properties": {
                    "gridId": "OKX",
                    "gridX": 33,
                    "gridY": 37,
                }
            }
        )

        grid = await get_grid_coordinates("NYC")
        assert grid["office"] == "OKX"
        assert grid["x"] == 33
        assert grid["y"] == 37

    @pytest.mark.asyncio
    async def test_caches_after_first_call(self, httpx_mock):
        """Second call for same city returns cached grid without HTTP call."""
        httpx_mock.add_response(
            json={
                "properties": {
                    "gridId": "OKX",
                    "gridX": 33,
                    "gridY": 37,
                }
            }
        )

        grid1 = await get_grid_coordinates("NYC")
        grid2 = await get_grid_coordinates("NYC")

        assert grid1 == grid2
        # Only one HTTP request should have been made
        assert len(httpx_mock.get_requests()) == 1

    @pytest.mark.asyncio
    async def test_invalid_response_raises_parse_error(self, httpx_mock):
        """Missing grid fields in response raises ParseError."""
        httpx_mock.add_response(json={"properties": {"someOtherField": "value"}})

        with pytest.raises(ParseError):
            await get_grid_coordinates("NYC")


# ─── URL Builder Tests ───


class TestBuildForecastUrl:
    """Test forecast URL construction."""

    @pytest.mark.asyncio
    async def test_returns_correct_url_format(self, httpx_mock):
        """Forecast URL contains grid office, x, y coordinates with /forecast."""
        httpx_mock.add_response(
            json={
                "properties": {
                    "gridId": "OKX",
                    "gridX": 33,
                    "gridY": 37,
                }
            }
        )

        url = await build_forecast_url("NYC")
        assert url == f"{NWS_BASE_URL}/gridpoints/OKX/33,37/forecast"


class TestBuildGridpointUrl:
    """Test gridpoint URL construction."""

    @pytest.mark.asyncio
    async def test_returns_correct_url_format(self, httpx_mock):
        """Gridpoint URL contains grid office, x, y without /forecast suffix."""
        httpx_mock.add_response(
            json={
                "properties": {
                    "gridId": "LOT",
                    "gridX": 76,
                    "gridY": 73,
                }
            }
        )

        url = await build_gridpoint_url("CHI")
        assert url == f"{NWS_BASE_URL}/gridpoints/LOT/76,73"
