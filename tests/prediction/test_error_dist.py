"""Tests for backend.prediction.error_dist — season detection and error std.

Covers ``get_season`` (4 tests) and ``calculate_error_std`` (6 tests)
including fallback behaviour when the database has insufficient data
or raises an error.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.prediction.error_dist import (
    FALLBACK_ERROR_STD,
    calculate_error_std,
    get_season,
)

# ═══════════════════════════════════════════════════════════════
# get_season
# ═══════════════════════════════════════════════════════════════


class TestGetSeason:
    """Validate the month → season mapping."""

    def test_winter_months(self) -> None:
        for month in (12, 1, 2):
            assert get_season(month) == "winter", f"month={month}"

    def test_spring_months(self) -> None:
        for month in (3, 4, 5):
            assert get_season(month) == "spring", f"month={month}"

    def test_summer_months(self) -> None:
        for month in (6, 7, 8):
            assert get_season(month) == "summer", f"month={month}"

    def test_fall_months(self) -> None:
        for month in (9, 10, 11):
            assert get_season(month) == "fall", f"month={month}"


# ═══════════════════════════════════════════════════════════════
# calculate_error_std
# ═══════════════════════════════════════════════════════════════


class TestCalculateErrorStd:
    """Tests for the async error-std calculation with mocked DB."""

    @pytest.mark.asyncio
    async def test_fallback_on_insufficient_data(self) -> None:
        """When the DB returns fewer than 30 rows, the fallback is used."""
        mock_session = AsyncMock()
        mock_result = MagicMock()
        # Return only 5 rows (< 30 minimum)
        mock_result.all.return_value = [(55.0, 56.0)] * 5
        mock_session.execute.return_value = mock_result

        std = await calculate_error_std("NYC", month=1, db_session=mock_session)

        # Should use the NYC/winter fallback
        assert std == pytest.approx(FALLBACK_ERROR_STD["NYC"]["winter"])

    @pytest.mark.asyncio
    async def test_fallback_on_db_error(self) -> None:
        """When the DB query raises an exception, the fallback is used."""
        mock_session = AsyncMock()
        mock_session.execute.side_effect = RuntimeError("DB connection lost")

        std = await calculate_error_std("NYC", month=7, db_session=mock_session)

        # Should use the NYC/summer fallback
        assert std == pytest.approx(FALLBACK_ERROR_STD["NYC"]["summer"])

    def test_fallback_values_exist_for_all_cities(self) -> None:
        """Every supported city has fallback values for all 4 seasons."""
        for city in ("NYC", "CHI", "MIA", "AUS"):
            assert city in FALLBACK_ERROR_STD
            for season in ("winter", "spring", "summer", "fall"):
                assert season in FALLBACK_ERROR_STD[city], f"{city}/{season}"

    def test_fallback_values_are_positive(self) -> None:
        """All fallback std values must be > 0."""
        for city, seasons in FALLBACK_ERROR_STD.items():
            for season, value in seasons.items():
                assert value > 0, f"Fallback for {city}/{season} must be positive"

    @pytest.mark.asyncio
    async def test_unknown_city_gets_default(self) -> None:
        """An unrecognized city code falls back to the 2.5 default."""
        mock_session = AsyncMock()
        mock_session.execute.side_effect = RuntimeError("DB not available")

        std = await calculate_error_std("XYZ", month=3, db_session=mock_session)
        assert std == pytest.approx(2.5)

    @pytest.mark.asyncio
    async def test_returns_positive_float(self) -> None:
        """The return value is always a positive float."""
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.all.return_value = []
        mock_session.execute.return_value = mock_result

        for city in ("NYC", "CHI", "MIA", "AUS"):
            for month in range(1, 13):
                std = await calculate_error_std(city, month=month, db_session=mock_session)
                assert isinstance(std, float)
                assert std > 0

    @pytest.mark.asyncio
    async def test_sufficient_data_uses_calculated_std(self) -> None:
        """When >= 30 samples exist, the calculated std dev is returned."""
        mock_session = AsyncMock()
        mock_result = MagicMock()
        # 30 rows where actual - forecast = 1.0 for every row → std = 0
        # Use slight variation so sample std is small but non-zero
        rows = [(55.0, 56.0)] * 15 + [(55.0, 57.0)] * 15
        mock_result.all.return_value = rows
        mock_session.execute.return_value = mock_result

        std = await calculate_error_std("NYC", month=1, db_session=mock_session)

        # The errors are [1.0]*15 + [2.0]*15 → mean=1.5, sample std ≈ 0.509
        # This should NOT equal the NYC/winter fallback of 3.0
        assert std != pytest.approx(FALLBACK_ERROR_STD["NYC"]["winter"])
        assert std > 0

    @pytest.mark.asyncio
    async def test_calculated_std_matches_numpy(self) -> None:
        """Verify the calculated value matches numpy's sample std (ddof=1)."""
        import numpy as np

        errors_data = [(50.0, 52.0), (50.0, 53.0), (50.0, 51.0)] * 10  # 30 rows
        errors = [actual - forecast for forecast, actual in errors_data]
        expected_std = float(np.std(errors, ddof=1))

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.all.return_value = errors_data
        mock_session.execute.return_value = mock_result

        std = await calculate_error_std("NYC", month=1, db_session=mock_session)

        assert std == pytest.approx(expected_std, abs=1e-9)
