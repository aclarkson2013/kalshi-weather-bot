"""Prediction-specific test fixtures.

Provides sample weather forecasts, bracket definitions, and mock
database sessions used across all prediction test modules.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.common.schemas import (
    WeatherData,
    WeatherVariables,
)

# ─── Sample Forecasts ───


@pytest.fixture
def sample_forecasts() -> list[WeatherData]:
    """List of WeatherData objects from multiple sources for NYC.

    Provides 5 forecasts from all default-weighted sources so the
    ensemble can exercise its full weighting logic.
    """
    now = datetime.now(UTC)
    base_date = date(2026, 2, 18)

    return [
        WeatherData(
            city="NYC",
            date=base_date,
            forecast_high_f=55.0,
            source="NWS",
            model_run_timestamp=now,
            variables=WeatherVariables(temp_high_f=55.0, temp_low_f=38.0),
            raw_data={"source": "NWS", "temp": 55.0},
            fetched_at=now,
        ),
        WeatherData(
            city="NYC",
            date=base_date,
            forecast_high_f=53.0,
            source="Open-Meteo:ECMWF",
            model_run_timestamp=now,
            variables=WeatherVariables(temp_high_f=53.0, temp_low_f=37.0),
            raw_data={"source": "ECMWF", "temp": 53.0},
            fetched_at=now,
        ),
        WeatherData(
            city="NYC",
            date=base_date,
            forecast_high_f=54.0,
            source="Open-Meteo:GFS",
            model_run_timestamp=now,
            variables=WeatherVariables(temp_high_f=54.0, temp_low_f=37.5),
            raw_data={"source": "GFS", "temp": 54.0},
            fetched_at=now,
        ),
        WeatherData(
            city="NYC",
            date=base_date,
            forecast_high_f=55.0,
            source="Open-Meteo:ICON",
            model_run_timestamp=now,
            variables=WeatherVariables(temp_high_f=55.0, temp_low_f=38.0),
            raw_data={"source": "ICON", "temp": 55.0},
            fetched_at=now,
        ),
        WeatherData(
            city="NYC",
            date=base_date,
            forecast_high_f=54.0,
            source="Open-Meteo:GEM",
            model_run_timestamp=now,
            variables=WeatherVariables(temp_high_f=54.0, temp_low_f=37.0),
            raw_data={"source": "GEM", "temp": 54.0},
            fetched_at=now,
        ),
    ]


# ─── Sample Brackets ───


@pytest.fixture
def sample_brackets() -> list[dict]:
    """Six bracket definitions in the format the prediction engine expects.

    Covers the range around 55F with 2-degree-wide middle brackets
    and unbounded edge brackets, matching Kalshi's typical structure.
    """
    return [
        {"lower_bound_f": None, "upper_bound_f": 51.0, "label": "<51"},
        {"lower_bound_f": 51.0, "upper_bound_f": 53.0, "label": "51-53"},
        {"lower_bound_f": 53.0, "upper_bound_f": 55.0, "label": "53-55"},
        {"lower_bound_f": 55.0, "upper_bound_f": 57.0, "label": "55-57"},
        {"lower_bound_f": 57.0, "upper_bound_f": 59.0, "label": "57-59"},
        {"lower_bound_f": 59.0, "upper_bound_f": None, "label": ">=59"},
    ]


# ─── Mock Database Session ───


@pytest.fixture
def mock_db_session() -> AsyncMock:
    """AsyncMock for a SQLAlchemy async session.

    Pre-configured so that ``session.execute()`` returns an empty
    result set by default.  Individual tests can override
    ``mock_db_session.execute.return_value`` as needed.
    """
    session = AsyncMock()
    mock_result = MagicMock()
    mock_result.all.return_value = []
    session.execute.return_value = mock_result
    return session
