"""Tests for backend.prediction.accuracy — per-source forecast accuracy metrics."""

from __future__ import annotations

import math
from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.prediction.accuracy import get_forecast_error_trend, get_source_accuracy

pytestmark = pytest.mark.asyncio


# ─── Helpers ───


def _mock_session_with_rows(rows: list) -> AsyncMock:
    """Create a mock DB session returning the given rows from execute()."""
    session = AsyncMock()
    mock_result = MagicMock()
    mock_result.all.return_value = rows
    session.execute.return_value = mock_result
    return session


def _make_source_row(source: str, cnt: int, mae: float, mse: float, bias: float):
    """Create a mock row matching the source accuracy SQL query shape."""
    row = MagicMock()
    row.source = source
    row.cnt = cnt
    row.mae = mae
    row.mse = mse
    row.bias = bias
    return row


def _make_trend_row(fdate: str, error: float):
    """Create a mock row matching the error trend SQL query shape."""
    row = MagicMock()
    row.fdate = fdate
    row.error = error
    return row


# ─── get_source_accuracy Tests ───


class TestGetSourceAccuracy:
    """Tests for per-source accuracy computation."""

    async def test_empty_data_returns_empty_list(self) -> None:
        """No forecast/settlement data → empty list."""
        session = _mock_session_with_rows([])
        result = await get_source_accuracy("NYC", session)
        assert result == []

    async def test_single_source(self) -> None:
        """Single source with known MAE, RMSE, bias."""
        rows = [_make_source_row("NWS", 30, 2.5, 8.0, -0.3)]
        session = _mock_session_with_rows(rows)
        result = await get_source_accuracy("NYC", session)
        assert len(result) == 1
        s = result[0]
        assert s.source == "NWS"
        assert s.sample_count == 30
        assert s.mae_f == 2.5
        assert s.rmse_f == round(math.sqrt(8.0), 2)
        assert s.bias_f == -0.3

    async def test_multiple_sources(self) -> None:
        """Multiple sources are all returned and ordered."""
        rows = [
            _make_source_row("NWS", 50, 2.0, 6.0, -0.5),
            _make_source_row("Open-Meteo:GFS", 45, 2.3, 7.0, 0.2),
            _make_source_row("Open-Meteo:ECMWF", 48, 1.8, 5.0, -0.1),
        ]
        session = _mock_session_with_rows(rows)
        result = await get_source_accuracy("NYC", session)
        assert len(result) == 3
        assert [s.source for s in result] == ["NWS", "Open-Meteo:GFS", "Open-Meteo:ECMWF"]

    async def test_rmse_calculation(self) -> None:
        """RMSE is sqrt of MSE."""
        # MSE = 4.0 → RMSE = 2.0
        rows = [_make_source_row("NWS", 10, 1.5, 4.0, 0.0)]
        session = _mock_session_with_rows(rows)
        result = await get_source_accuracy("NYC", session)
        assert result[0].rmse_f == 2.0

    async def test_zero_mse(self) -> None:
        """Perfect predictions → MSE=0 → RMSE=0."""
        rows = [_make_source_row("NWS", 10, 0.0, 0.0, 0.0)]
        session = _mock_session_with_rows(rows)
        result = await get_source_accuracy("NYC", session)
        assert result[0].rmse_f == 0.0
        assert result[0].mae_f == 0.0
        assert result[0].bias_f == 0.0

    async def test_none_mse_fallback(self) -> None:
        """None MSE (shouldn't happen in practice) → RMSE=0.0."""
        rows = [_make_source_row("NWS", 1, 0.0, None, 0.0)]
        session = _mock_session_with_rows(rows)
        result = await get_source_accuracy("NYC", session)
        assert result[0].rmse_f == 0.0

    async def test_negative_bias(self) -> None:
        """Negative bias means forecasts tend to overpredict."""
        rows = [_make_source_row("NWS", 20, 3.0, 12.0, -2.5)]
        session = _mock_session_with_rows(rows)
        result = await get_source_accuracy("NYC", session)
        assert result[0].bias_f == -2.5

    async def test_positive_bias(self) -> None:
        """Positive bias means forecasts tend to underpredict."""
        rows = [_make_source_row("NWS", 20, 3.0, 12.0, 1.8)]
        session = _mock_session_with_rows(rows)
        result = await get_source_accuracy("NYC", session)
        assert result[0].bias_f == 1.8

    async def test_rounding(self) -> None:
        """MAE, RMSE, bias are rounded to 2 decimal places."""
        # MAE = 2.456, MSE = 7.891 → RMSE = 2.80911..., bias = -0.123
        rows = [_make_source_row("NWS", 10, 2.456, 7.891, -0.123)]
        session = _mock_session_with_rows(rows)
        result = await get_source_accuracy("NYC", session)
        assert result[0].mae_f == 2.46
        assert result[0].rmse_f == 2.81
        assert result[0].bias_f == -0.12

    async def test_large_errors(self) -> None:
        """Handles large forecast errors gracefully."""
        rows = [_make_source_row("NWS", 5, 15.0, 300.0, 10.0)]
        session = _mock_session_with_rows(rows)
        result = await get_source_accuracy("NYC", session)
        assert result[0].mae_f == 15.0
        assert result[0].rmse_f == round(math.sqrt(300.0), 2)

    async def test_different_cities(self) -> None:
        """Each city query passes the city argument to the SQL."""
        rows = [_make_source_row("NWS", 10, 2.0, 5.0, 0.0)]
        for city in ("NYC", "CHI", "MIA", "AUS"):
            session = _mock_session_with_rows(rows)
            result = await get_source_accuracy(city, session)
            assert len(result) == 1

    async def test_lookback_days_parameter(self) -> None:
        """Custom lookback_days is passed through (verify no crash)."""
        session = _mock_session_with_rows([])
        result = await get_source_accuracy("NYC", session, lookback_days=30)
        assert result == []


# ─── get_forecast_error_trend Tests ───


class TestGetForecastErrorTrend:
    """Tests for forecast error trend computation."""

    async def test_empty_data(self) -> None:
        """No data → empty points, None rolling MAE."""
        session = _mock_session_with_rows([])
        result = await get_forecast_error_trend("NYC", "NWS", session)
        assert result.city == "NYC"
        assert result.source == "NWS"
        assert result.points == []
        assert result.rolling_mae is None

    async def test_single_point(self) -> None:
        """Single data point → one point, rolling MAE equals its abs error."""
        rows = [_make_trend_row("2026-02-10", 2.5)]
        session = _mock_session_with_rows(rows)
        result = await get_forecast_error_trend("NYC", "NWS", session)
        assert len(result.points) == 1
        assert result.points[0].date == "2026-02-10"
        assert result.points[0].error_f == 2.5
        assert result.rolling_mae == 2.5

    async def test_multiple_points_ordered(self) -> None:
        """Multiple points are returned in order."""
        rows = [
            _make_trend_row("2026-02-08", -1.0),
            _make_trend_row("2026-02-09", 2.0),
            _make_trend_row("2026-02-10", -3.0),
        ]
        session = _mock_session_with_rows(rows)
        result = await get_forecast_error_trend("NYC", "NWS", session)
        assert len(result.points) == 3
        dates = [p.date for p in result.points]
        assert dates == ["2026-02-08", "2026-02-09", "2026-02-10"]

    async def test_rolling_mae_fewer_than_7(self) -> None:
        """With fewer than 7 points, rolling MAE uses all available points."""
        rows = [
            _make_trend_row("2026-02-08", 1.0),
            _make_trend_row("2026-02-09", -3.0),
            _make_trend_row("2026-02-10", 5.0),
        ]
        session = _mock_session_with_rows(rows)
        result = await get_forecast_error_trend("NYC", "NWS", session)
        # abs errors: 1, 3, 5 → mean = 3.0
        assert result.rolling_mae == 3.0

    async def test_rolling_mae_more_than_7(self) -> None:
        """With more than 7 points, rolling MAE uses only the last 7."""
        rows = [_make_trend_row(f"2026-02-{i:02d}", float(i)) for i in range(1, 11)]
        session = _mock_session_with_rows(rows)
        result = await get_forecast_error_trend("NYC", "NWS", session)
        # Last 7 points: errors 4,5,6,7,8,9,10 → abs = same → mean = 7.0
        assert result.rolling_mae == 7.0

    async def test_negative_errors(self) -> None:
        """Negative errors (actual < forecast) are preserved in points."""
        rows = [_make_trend_row("2026-02-10", -4.5)]
        session = _mock_session_with_rows(rows)
        result = await get_forecast_error_trend("NYC", "NWS", session)
        assert result.points[0].error_f == -4.5
        # Rolling MAE uses abs value
        assert result.rolling_mae == 4.5

    async def test_error_rounding(self) -> None:
        """Error values are rounded to 2 decimal places."""
        rows = [_make_trend_row("2026-02-10", 2.456)]
        session = _mock_session_with_rows(rows)
        result = await get_forecast_error_trend("NYC", "NWS", session)
        assert result.points[0].error_f == 2.46

    async def test_rolling_mae_rounding(self) -> None:
        """Rolling MAE is rounded to 2 decimal places."""
        rows = [
            _make_trend_row("2026-02-08", 1.0),
            _make_trend_row("2026-02-09", 2.0),
            _make_trend_row("2026-02-10", 3.0),
        ]
        session = _mock_session_with_rows(rows)
        result = await get_forecast_error_trend("NYC", "NWS", session)
        # abs errors: 1, 2, 3 → mean = 2.0
        assert result.rolling_mae == 2.0

    async def test_zero_errors(self) -> None:
        """All-zero errors → rolling MAE = 0.0."""
        rows = [_make_trend_row(f"2026-02-{i:02d}", 0.0) for i in range(1, 4)]
        session = _mock_session_with_rows(rows)
        result = await get_forecast_error_trend("NYC", "NWS", session)
        assert result.rolling_mae == 0.0

    async def test_city_and_source_in_result(self) -> None:
        """City and source are echoed back in the result."""
        session = _mock_session_with_rows([])
        result = await get_forecast_error_trend("CHI", "Open-Meteo:GFS", session)
        assert result.city == "CHI"
        assert result.source == "Open-Meteo:GFS"

    async def test_lookback_days_parameter(self) -> None:
        """Custom lookback_days is accepted without error."""
        session = _mock_session_with_rows([])
        result = await get_forecast_error_trend("NYC", "NWS", session, lookback_days=30)
        assert result.points == []
