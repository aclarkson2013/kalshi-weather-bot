"""Tests for backend.prediction.calibration — calibration stub (Phase 2).

The calibration module is currently a stub that returns
``status="insufficient_data"`` with zeroed metrics.  These tests
lock in that contract so a future implementation cannot silently
change the return shape.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from backend.prediction.calibration import check_calibration


class TestCheckCalibration:
    """Tests for the Phase-2 calibration stub."""

    @pytest.mark.asyncio
    async def test_returns_insufficient_data(self) -> None:
        """The stub must report status as 'insufficient_data'."""
        result = await check_calibration("NYC", db_session=AsyncMock())
        assert result["status"] == "insufficient_data"

    @pytest.mark.asyncio
    async def test_returns_correct_city(self) -> None:
        """The returned dict echoes back the requested city."""
        for city in ("NYC", "CHI", "MIA", "AUS"):
            result = await check_calibration(city, db_session=AsyncMock())
            assert result["city"] == city

    @pytest.mark.asyncio
    async def test_returns_zero_sample_count(self) -> None:
        """Because there is no data, sample_count should be 0."""
        result = await check_calibration("NYC", db_session=AsyncMock())
        assert result["sample_count"] == 0
