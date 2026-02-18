"""Tests for weather data normalization.

This is the most important test file for the weather module. It validates
that raw API responses from NWS (forecast and gridpoint) and Open-Meteo
are correctly transformed into WeatherData schema objects, with proper
unit conversions and error handling.

CRITICAL: NWS gridpoint data is in Celsius/km/h/Pa and must be converted
to Fahrenheit/mph/mb. These conversions are explicitly tested.
"""

from __future__ import annotations

from datetime import date

import pytest

from backend.common.schemas import WeatherData
from backend.weather.exceptions import ParseError
from backend.weather.normalizer import (
    _parse_nws_wind_speed,
    _safe_float_at,
    normalize_nws_forecast,
    normalize_nws_gridpoint,
    normalize_openmeteo,
)

# ─── NWS Forecast Normalizer Tests ───


class TestNormalizeNwsForecast:
    """Test normalization of NWS 12-hour period forecasts."""

    def test_extracts_daytime_periods_only(
        self,
        sample_nws_forecast_response,
    ):
        """Only isDaytime=True periods are extracted; nighttime is skipped."""
        results = normalize_nws_forecast("NYC", sample_nws_forecast_response)
        # Fixture has 2 daytime and 2 nighttime periods
        assert len(results) == 2
        for wd in results:
            assert isinstance(wd, WeatherData)

    def test_temperatures_used_directly_fahrenheit(
        self,
        sample_nws_forecast_response,
    ):
        """NWS forecast temps are already in Fahrenheit, no conversion needed."""
        results = normalize_nws_forecast("NYC", sample_nws_forecast_response)
        wd = results[0]
        # First daytime period has temperature=55
        assert wd.forecast_high_f == 55.0
        assert wd.variables.temp_high_f == 55.0

    def test_source_is_nws(self, sample_nws_forecast_response):
        """Source label must be 'NWS' for period forecasts."""
        results = normalize_nws_forecast("NYC", sample_nws_forecast_response)
        assert all(r.source == "NWS" for r in results)

    def test_date_parsed_from_start_time(
        self,
        sample_nws_forecast_response,
    ):
        """Forecast date is parsed from the startTime field."""
        results = normalize_nws_forecast("NYC", sample_nws_forecast_response)
        assert results[0].date == date(2026, 2, 17)
        assert results[1].date == date(2026, 2, 18)

    def test_raises_parse_error_for_missing_properties_periods(self):
        """Response missing properties.periods raises ParseError."""
        with pytest.raises(ParseError):
            normalize_nws_forecast("NYC", {})

        with pytest.raises(ParseError):
            normalize_nws_forecast("NYC", {"properties": {}})

        with pytest.raises(ParseError):
            normalize_nws_forecast("NYC", None)

    def test_empty_periods_returns_empty_list(self):
        """Empty periods list returns an empty result."""
        response = {"properties": {"periods": []}}
        results = normalize_nws_forecast("NYC", response)
        assert results == []

    def test_wind_speed_parsed_from_range(
        self,
        sample_nws_forecast_response,
    ):
        """Wind speed '10 to 15 mph' extracts the max value 15.0."""
        results = normalize_nws_forecast("NYC", sample_nws_forecast_response)
        assert results[0].variables.wind_speed_mph == 15.0


# ─── NWS Gridpoint Normalizer Tests ───


class TestNormalizeNwsGridpoint:
    """Test normalization of NWS raw gridpoint data.

    CRITICAL: All temperature values are in Celsius, wind in km/h,
    pressure in Pa. These must be converted.
    """

    def test_converts_celsius_to_fahrenheit(
        self,
        sample_nws_gridpoint_response,
    ):
        """Gridpoint temps in Celsius MUST be converted to Fahrenheit.

        12.8 C = (12.8 * 9/5) + 32 = 55.04 F -> rounds to 55.0
        """
        results = normalize_nws_gridpoint("NYC", sample_nws_gridpoint_response)
        assert len(results) >= 1
        wd = results[0]
        assert wd.forecast_high_f == pytest.approx(55.0, abs=0.1)
        assert wd.variables.temp_high_f == pytest.approx(55.0, abs=0.1)

    def test_converts_wind_kmh_to_mph(
        self,
        sample_nws_gridpoint_response,
    ):
        """Wind speed must be converted from km/h to mph (* 0.621371).

        24.1 km/h * 0.621371 = 14.97 mph -> rounds to 15.0
        """
        results = normalize_nws_gridpoint("NYC", sample_nws_gridpoint_response)
        wd = results[0]
        assert wd.variables.wind_speed_mph == pytest.approx(15.0, abs=0.1)

    def test_converts_pressure_pa_to_mb(
        self,
        sample_nws_gridpoint_response,
    ):
        """Pressure must be converted from Pa to mb (hPa) by dividing by 100.

        101325 Pa / 100 = 1013.25 mb -> rounds to 1013.2
        """
        results = normalize_nws_gridpoint("NYC", sample_nws_gridpoint_response)
        wd = results[0]
        assert wd.variables.pressure_mb == pytest.approx(1013.2, abs=0.2)

    def test_source_is_nws_gridpoint(
        self,
        sample_nws_gridpoint_response,
    ):
        """Source label must be 'NWS:gridpoint'."""
        results = normalize_nws_gridpoint("NYC", sample_nws_gridpoint_response)
        assert all(r.source == "NWS:gridpoint" for r in results)

    def test_min_temperature_converted(
        self,
        sample_nws_gridpoint_response,
    ):
        """Min temperature (Celsius) should also be converted to Fahrenheit.

        3.5 C = (3.5 * 9/5) + 32 = 38.3 F
        """
        results = normalize_nws_gridpoint("NYC", sample_nws_gridpoint_response)
        wd = results[0]
        assert wd.variables.temp_low_f == pytest.approx(38.3, abs=0.1)

    def test_dewpoint_converted_celsius_to_fahrenheit(
        self,
        sample_nws_gridpoint_response,
    ):
        """Dewpoint must be converted from Celsius to Fahrenheit.

        1.5 C = (1.5 * 9/5) + 32 = 34.7 F
        """
        results = normalize_nws_gridpoint("NYC", sample_nws_gridpoint_response)
        wd = results[0]
        assert wd.variables.dew_point_f == pytest.approx(34.7, abs=0.1)

    def test_raises_parse_error_for_missing_properties(self):
        """Response without 'properties' raises ParseError."""
        with pytest.raises(ParseError):
            normalize_nws_gridpoint("NYC", {})

        with pytest.raises(ParseError):
            normalize_nws_gridpoint("NYC", None)

    def test_empty_max_temperature_returns_empty(self):
        """Empty maxTemperature values list returns empty result."""
        response = {"properties": {"maxTemperature": {"values": []}}}
        results = normalize_nws_gridpoint("NYC", response)
        assert results == []

    def test_missing_max_temperature_returns_empty(self):
        """Missing maxTemperature key entirely returns empty result."""
        response = {"properties": {}}
        results = normalize_nws_gridpoint("NYC", response)
        assert results == []

    def test_multiple_days_produced(
        self,
        sample_nws_gridpoint_response,
    ):
        """Fixture has 2 days of maxTemperature data; both should be returned."""
        results = normalize_nws_gridpoint("NYC", sample_nws_gridpoint_response)
        assert len(results) == 2
        assert results[0].date == date(2026, 2, 17)
        assert results[1].date == date(2026, 2, 18)


# ─── Open-Meteo Normalizer Tests ───


class TestNormalizeOpenmeteo:
    """Test normalization of Open-Meteo daily forecast data."""

    def test_creates_weather_data_with_correct_source(self):
        """WeatherData source matches the passed-in source_label."""
        model_daily = {
            "time": ["2026-02-17"],
            "temperature_2m_max": [55.2],
            "temperature_2m_min": [38.5],
        }
        results = normalize_openmeteo("NYC", "Open-Meteo:GFS", model_daily, {})
        assert len(results) == 1
        assert results[0].source == "Open-Meteo:GFS"

    def test_temperatures_used_directly_no_conversion(self):
        """Open-Meteo Fahrenheit data is used without conversion."""
        model_daily = {
            "time": ["2026-02-17", "2026-02-18"],
            "temperature_2m_max": [55.2, 52.1],
            "temperature_2m_min": [38.5, 35.2],
        }
        results = normalize_openmeteo("NYC", "Open-Meteo:ECMWF", model_daily, {})
        assert results[0].forecast_high_f == 55.2
        assert results[0].variables.temp_high_f == 55.2
        assert results[0].variables.temp_low_f == 38.5
        assert results[1].forecast_high_f == 52.1

    def test_raises_parse_error_for_missing_time_array(self):
        """model_daily without 'time' key raises ParseError."""
        bad_daily = {
            "temperature_2m_max": [55.2],
            "temperature_2m_min": [38.5],
        }
        with pytest.raises(ParseError):
            normalize_openmeteo("NYC", "Open-Meteo:GFS", bad_daily, {})

    def test_none_model_daily_raises_parse_error(self):
        """None model_daily raises ParseError."""
        with pytest.raises(ParseError):
            normalize_openmeteo("NYC", "Open-Meteo:GFS", None, {})

    def test_missing_temp_max_skips_entry(self):
        """Missing temperature_2m_max for an entry skips it gracefully."""
        daily = {
            "time": ["2026-02-17"],
            # No temperature_2m_max
        }
        results = normalize_openmeteo("NYC", "Open-Meteo:GFS", daily, {})
        assert results == []

    def test_city_propagated(self):
        """City code is passed through to all WeatherData entries."""
        model_daily = {
            "time": ["2026-02-17"],
            "temperature_2m_max": [85.0],
            "temperature_2m_min": [72.0],
        }
        results = normalize_openmeteo("MIA", "Open-Meteo:ICON", model_daily, {})
        assert all(r.city == "MIA" for r in results)


# ─── Wind Speed Parsing Tests ───


class TestParseNwsWindSpeed:
    """Test NWS wind speed string parsing."""

    def test_single_value(self):
        """'10 mph' extracts 10.0."""
        assert _parse_nws_wind_speed("10 mph") == 10.0

    def test_range_format_extracts_max(self):
        """'10 to 15 mph' extracts the maximum: 15.0."""
        assert _parse_nws_wind_speed("10 to 15 mph") == 15.0

    def test_empty_string_returns_none(self):
        """Empty string returns None."""
        assert _parse_nws_wind_speed("") is None


# ─── _safe_float_at Tests ───


class TestSafeFloatAt:
    """Test safe index-based float extraction."""

    def test_valid_index(self):
        """Returns float value at valid index."""
        assert _safe_float_at([1.0, 2.0, 3.0], 1) == 2.0

    def test_out_of_range_index_returns_none(self):
        """Out-of-range index returns None."""
        assert _safe_float_at([1.0], 5) is None

    def test_none_value_at_index_returns_none(self):
        """None value in the list at target index returns None."""
        assert _safe_float_at([1.0, None, 3.0], 1) is None

    def test_empty_list_returns_none(self):
        """Empty list returns None for any index."""
        assert _safe_float_at([], 0) is None
