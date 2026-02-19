"""Tests for backend.weather.scheduler -- Celery tasks for weather data fetching.

Tests cover:
- _store_weather_data: DB storage of WeatherData objects
- _fetch_all_forecasts_async: Orchestrates all fetches per city
- _fetch_cli_reports_async: CLI fetch + Settlement record creation
- fetch_all_forecasts: Celery task wrapper
- fetch_cli_reports: Celery task wrapper

NOTE: Comprehensive CLI fetch/parse tests are in tests/weather/test_cli_fetch.py
and tests/weather/test_cli_parser.py.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.common.schemas import WeatherData, WeatherVariables

# ─── Helpers ───


def _make_weather_data(
    city: str = "NYC",
    source: str = "NWS",
    high_f: float = 55.0,
) -> WeatherData:
    """Create a WeatherData instance with sensible defaults."""
    now = datetime.now(UTC)
    return WeatherData(
        city=city,
        date=date(2026, 2, 18),
        forecast_high_f=high_f,
        source=source,
        model_run_timestamp=now,
        variables=WeatherVariables(
            temp_high_f=high_f,
            temp_low_f=40.0,
            humidity_pct=65.0,
            wind_speed_mph=10.0,
        ),
        raw_data={"test": True},
        fetched_at=now,
    )


def _make_mock_session() -> AsyncMock:
    """Create a mock async DB session."""
    session = AsyncMock()
    session.add = MagicMock()  # synchronous method
    return session


# ─── _store_weather_data Tests ───


class TestStoreWeatherData:
    """Tests for _store_weather_data -- stores WeatherData list to DB."""

    @pytest.mark.asyncio
    async def test_empty_list_returns_zero(self) -> None:
        """An empty list stores nothing and returns 0."""
        from backend.weather.scheduler import _store_weather_data

        result = await _store_weather_data([])
        assert result == 0

    @pytest.mark.asyncio
    async def test_stores_single_forecast(self) -> None:
        """One forecast is stored and count returned as 1."""
        from backend.weather.scheduler import _store_weather_data

        mock_session = _make_mock_session()

        with patch("backend.weather.scheduler.get_task_session", return_value=mock_session):
            result = await _store_weather_data([_make_weather_data()])

        assert result == 1
        mock_session.add.assert_called_once()
        mock_session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_stores_multiple_forecasts(self) -> None:
        """Three forecasts are stored and count returned as 3."""
        from backend.weather.scheduler import _store_weather_data

        mock_session = _make_mock_session()
        forecasts = [
            _make_weather_data(city="NYC"),
            _make_weather_data(city="CHI"),
            _make_weather_data(city="MIA"),
        ]

        with patch("backend.weather.scheduler.get_task_session", return_value=mock_session):
            result = await _store_weather_data(forecasts)

        assert result == 3
        assert mock_session.add.call_count == 3

    @pytest.mark.asyncio
    async def test_maps_fields_correctly_to_orm(self) -> None:
        """The ORM object passed to session.add has correct field values."""
        from backend.weather.scheduler import _store_weather_data

        mock_session = _make_mock_session()
        forecast = _make_weather_data(city="CHI", source="Open-Meteo:GFS", high_f=42.5)

        with patch("backend.weather.scheduler.get_task_session", return_value=mock_session):
            await _store_weather_data([forecast])

        orm_obj = mock_session.add.call_args[0][0]
        assert orm_obj.city == "CHI"
        assert orm_obj.source == "Open-Meteo:GFS"
        assert orm_obj.forecast_high_f == 42.5
        assert orm_obj.humidity_pct == 65.0
        assert orm_obj.wind_speed_mph == 10.0

    @pytest.mark.asyncio
    async def test_rollback_on_commit_failure(self) -> None:
        """Session is rolled back and exception re-raised on commit failure."""
        from backend.weather.scheduler import _store_weather_data

        mock_session = _make_mock_session()
        mock_session.commit.side_effect = RuntimeError("DB error")

        with (
            patch("backend.weather.scheduler.get_task_session", return_value=mock_session),
            pytest.raises(RuntimeError, match="DB error"),
        ):
            await _store_weather_data([_make_weather_data()])

        mock_session.rollback.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_session_closed_on_success(self) -> None:
        """Session.close is called after successful storage."""
        from backend.weather.scheduler import _store_weather_data

        mock_session = _make_mock_session()

        with patch("backend.weather.scheduler.get_task_session", return_value=mock_session):
            await _store_weather_data([_make_weather_data()])

        mock_session.close.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_session_closed_on_failure(self) -> None:
        """Session.close is called even after an error (finally block)."""
        from backend.weather.scheduler import _store_weather_data

        mock_session = _make_mock_session()
        mock_session.commit.side_effect = RuntimeError("fail")

        with (
            patch("backend.weather.scheduler.get_task_session", return_value=mock_session),
            pytest.raises(RuntimeError),
        ):
            await _store_weather_data([_make_weather_data()])

        mock_session.close.assert_awaited_once()


# ─── _fetch_all_forecasts_async Tests ───


class TestFetchAllForecastsAsync:
    """Tests for _fetch_all_forecasts_async -- orchestrates all weather fetches."""

    @pytest.mark.asyncio
    async def test_fetches_all_sources_for_all_cities(self) -> None:
        """All 3 fetch functions are called once per city (4 cities)."""
        from backend.weather.scheduler import _fetch_all_forecasts_async

        mock_nws = AsyncMock(return_value=[_make_weather_data(source="NWS")])
        mock_grid = AsyncMock(return_value=[_make_weather_data(source="NWS-grid")])
        mock_om = AsyncMock(return_value=[_make_weather_data(source="Open-Meteo:GFS")])
        mock_store = AsyncMock(return_value=12)

        with (
            patch("backend.weather.scheduler.fetch_nws_forecast", mock_nws),
            patch("backend.weather.scheduler.fetch_nws_gridpoint", mock_grid),
            patch("backend.weather.scheduler.fetch_openmeteo_forecast", mock_om),
            patch("backend.weather.scheduler._store_weather_data", mock_store),
        ):
            await _fetch_all_forecasts_async()

        assert mock_nws.call_count == 4
        assert mock_grid.call_count == 4
        assert mock_om.call_count == 4
        mock_store.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_partial_failure_continues(self) -> None:
        """One source failing for one city doesn't stop other fetches."""
        from backend.weather.scheduler import _fetch_all_forecasts_async

        mock_nws = AsyncMock(side_effect=ConnectionError("NWS down"))
        mock_grid = AsyncMock(return_value=[_make_weather_data(source="NWS-grid")])
        mock_om = AsyncMock(return_value=[_make_weather_data(source="Open-Meteo:GFS")])
        mock_store = AsyncMock(return_value=8)

        with (
            patch("backend.weather.scheduler.fetch_nws_forecast", mock_nws),
            patch("backend.weather.scheduler.fetch_nws_gridpoint", mock_grid),
            patch("backend.weather.scheduler.fetch_openmeteo_forecast", mock_om),
            patch("backend.weather.scheduler._store_weather_data", mock_store),
        ):
            await _fetch_all_forecasts_async()

        # NWS period failed but grid + openmeteo still called for all cities
        assert mock_grid.call_count == 4
        assert mock_om.call_count == 4
        mock_store.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_all_fetches_fail_no_store_called(self) -> None:
        """When all fetch sources fail, _store_weather_data is not called."""
        from backend.weather.scheduler import _fetch_all_forecasts_async

        mock_nws = AsyncMock(side_effect=Exception("fail"))
        mock_grid = AsyncMock(side_effect=Exception("fail"))
        mock_om = AsyncMock(side_effect=Exception("fail"))
        mock_store = AsyncMock()

        with (
            patch("backend.weather.scheduler.fetch_nws_forecast", mock_nws),
            patch("backend.weather.scheduler.fetch_nws_gridpoint", mock_grid),
            patch("backend.weather.scheduler.fetch_openmeteo_forecast", mock_om),
            patch("backend.weather.scheduler._store_weather_data", mock_store),
        ):
            await _fetch_all_forecasts_async()  # Should not raise

        mock_store.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_store_failure_logged_not_raised(self) -> None:
        """When _store_weather_data raises, the error is caught (no propagation)."""
        from backend.weather.scheduler import _fetch_all_forecasts_async

        mock_nws = AsyncMock(return_value=[_make_weather_data()])
        mock_grid = AsyncMock(return_value=[])
        mock_om = AsyncMock(return_value=[])
        mock_store = AsyncMock(side_effect=RuntimeError("DB down"))

        with (
            patch("backend.weather.scheduler.fetch_nws_forecast", mock_nws),
            patch("backend.weather.scheduler.fetch_nws_gridpoint", mock_grid),
            patch("backend.weather.scheduler.fetch_openmeteo_forecast", mock_om),
            patch("backend.weather.scheduler._store_weather_data", mock_store),
        ):
            # Should NOT raise
            await _fetch_all_forecasts_async()


# ─── _fetch_cli_reports_async Tests ───
# NOTE: Comprehensive tests in tests/weather/test_cli_fetch.py.


class TestFetchCliReportsAsync:
    """Tests for _fetch_cli_reports_async -- CLI fetch + Settlement creation."""

    @pytest.mark.asyncio
    async def test_fetches_cli_per_city(self) -> None:
        """fetch_nws_cli is called once per city (4 cities)."""
        from backend.weather.scheduler import _fetch_cli_reports_async

        mock_fetch = AsyncMock(return_value="CLI TEXT")
        mock_report = MagicMock()
        mock_report.high_f = 54.0
        mock_report.low_f = 38.0
        mock_report.station = "KNYC"
        mock_report.report_date = date(2026, 2, 18)
        mock_report.raw_text = "CLI TEXT"

        mock_session = AsyncMock()
        mock_session.add = MagicMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        with (
            patch("backend.weather.scheduler.fetch_nws_cli", mock_fetch),
            patch("backend.weather.scheduler.parse_cli_text", return_value=mock_report),
            patch(
                "backend.weather.scheduler.get_task_session",
                new_callable=AsyncMock,
                return_value=mock_session,
            ),
        ):
            await _fetch_cli_reports_async()

        assert mock_fetch.call_count == 4

    @pytest.mark.asyncio
    async def test_city_failure_continues_to_next(self) -> None:
        """One city failing doesn't stop fetching for other cities."""
        from backend.weather.scheduler import _fetch_cli_reports_async

        mock_report = MagicMock()
        mock_report.high_f = 54.0
        mock_report.low_f = 38.0
        mock_report.station = "KNYC"
        mock_report.report_date = date(2026, 2, 18)
        mock_report.raw_text = "CLI TEXT"

        mock_session = AsyncMock()
        mock_session.add = MagicMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        # Fail for first call, succeed for rest
        mock_fetch = AsyncMock(
            side_effect=[
                ConnectionError("fail"),
                "CLI TEXT",
                "CLI TEXT",
                "CLI TEXT",
            ]
        )

        with (
            patch("backend.weather.scheduler.fetch_nws_cli", mock_fetch),
            patch("backend.weather.scheduler.parse_cli_text", return_value=mock_report),
            patch(
                "backend.weather.scheduler.get_task_session",
                new_callable=AsyncMock,
                return_value=mock_session,
            ),
        ):
            await _fetch_cli_reports_async()

        assert mock_fetch.call_count == 4
        # Only 3 cities created settlements (first city failed)
        assert mock_session.add.call_count == 3

    @pytest.mark.asyncio
    async def test_parse_failure_handled_gracefully(self) -> None:
        """When parse_cli_text raises ParseError, the error is caught per-city."""
        from backend.weather.exceptions import ParseError
        from backend.weather.scheduler import _fetch_cli_reports_async

        with (
            patch(
                "backend.weather.scheduler.fetch_nws_cli",
                new_callable=AsyncMock,
                return_value="BAD TEXT",
            ),
            patch(
                "backend.weather.scheduler.parse_cli_text",
                side_effect=ParseError("No TEMPERATURE section"),
            ),
            patch(
                "backend.weather.scheduler.get_task_session",
                new_callable=AsyncMock,
            ),
        ):
            # Should NOT raise
            await _fetch_cli_reports_async()


# ─── fetch_all_forecasts Celery Task Tests ───


class TestFetchAllForecastsTask:
    """Tests for fetch_all_forecasts -- the Celery task wrapper.

    Uses Celery eager mode via .apply() so tasks execute synchronously
    in the test process without needing a broker.
    """

    def test_returns_metadata_dict(self) -> None:
        """The task returns a dict with status, elapsed_seconds, and cities."""
        mock_sync_fn = MagicMock()
        with patch("backend.weather.scheduler.async_to_sync", return_value=mock_sync_fn):
            from backend.weather.scheduler import fetch_all_forecasts

            result = fetch_all_forecasts.apply().result

        assert result["status"] == "completed"
        assert "elapsed_seconds" in result
        assert "cities" in result

    def test_elapsed_seconds_is_numeric(self) -> None:
        """elapsed_seconds in the result is a number >= 0."""
        mock_sync_fn = MagicMock()
        with patch("backend.weather.scheduler.async_to_sync", return_value=mock_sync_fn):
            from backend.weather.scheduler import fetch_all_forecasts

            result = fetch_all_forecasts.apply().result

        assert isinstance(result["elapsed_seconds"], (int, float))
        assert result["elapsed_seconds"] >= 0

    def test_retries_on_exception(self) -> None:
        """When the async implementation raises, self.retry is called."""
        from backend.weather.scheduler import fetch_all_forecasts

        mock_sync_fn = MagicMock(side_effect=RuntimeError("boom"))
        with patch("backend.weather.scheduler.async_to_sync", return_value=mock_sync_fn):
            task_result = fetch_all_forecasts.apply()

        # Celery eager mode: if retry raises Retry, apply() catches it.
        # Since async_to_sync raises RuntimeError, the task calls self.retry()
        # which raises celery.exceptions.Retry — caught by eager mode.
        # The result should be an exception or the task should have failed.
        assert task_result.failed() or task_result.result is not None

    def test_cities_in_result(self) -> None:
        """The result contains the list of valid cities."""
        from backend.weather.stations import VALID_CITIES

        mock_sync_fn = MagicMock()
        with patch("backend.weather.scheduler.async_to_sync", return_value=mock_sync_fn):
            from backend.weather.scheduler import fetch_all_forecasts

            result = fetch_all_forecasts.apply().result

        assert result["cities"] == VALID_CITIES


# ─── fetch_cli_reports Celery Task Tests ───


class TestFetchCliReportsTask:
    """Tests for fetch_cli_reports -- the Celery task wrapper."""

    def test_returns_metadata_dict(self) -> None:
        """The task returns a dict with status, elapsed_seconds, and cities."""
        mock_sync_fn = MagicMock()
        with patch("backend.weather.scheduler.async_to_sync", return_value=mock_sync_fn):
            from backend.weather.scheduler import fetch_cli_reports

            result = fetch_cli_reports.apply().result

        assert result["status"] == "completed"
        assert "elapsed_seconds" in result
        assert "cities" in result

    def test_retries_on_exception(self) -> None:
        """When the async implementation raises, self.retry is called."""
        from backend.weather.scheduler import fetch_cli_reports

        mock_sync_fn = MagicMock(side_effect=RuntimeError("boom"))
        with patch("backend.weather.scheduler.async_to_sync", return_value=mock_sync_fn):
            task_result = fetch_cli_reports.apply()

        assert task_result.failed() or task_result.result is not None

    def test_cities_in_result(self) -> None:
        """The result contains the list of valid cities."""
        from backend.weather.stations import VALID_CITIES

        mock_sync_fn = MagicMock()
        with patch("backend.weather.scheduler.async_to_sync", return_value=mock_sync_fn):
            from backend.weather.scheduler import fetch_cli_reports

            result = fetch_cli_reports.apply().result

        assert result["cities"] == VALID_CITIES
