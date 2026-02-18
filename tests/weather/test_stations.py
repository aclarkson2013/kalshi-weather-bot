"""Tests for station configuration and helper functions.

Validates that all 4 Kalshi cities have correct station metadata,
temperature conversions are accurate, and timezone helpers return
expected formats.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from backend.weather.stations import (
    STATION_CONFIGS,
    VALID_CITIES,
    StationConfig,
    celsius_to_fahrenheit,
    fahrenheit_to_celsius,
    get_settlement_date,
    get_standard_time_now,
    is_forecast_for_today,
)

# ─── Station Configuration Tests ───


class TestStationConfigs:
    """Verify station configuration for all 4 Kalshi cities."""

    def test_all_four_cities_present(self):
        """STATION_CONFIGS must contain exactly NYC, CHI, MIA, AUS."""
        assert set(STATION_CONFIGS.keys()) == {"NYC", "CHI", "MIA", "AUS"}

    def test_valid_cities_matches_station_configs_keys(self):
        """VALID_CITIES must contain the same cities as STATION_CONFIGS keys."""
        assert set(VALID_CITIES) == set(STATION_CONFIGS.keys())
        assert len(VALID_CITIES) == 4

    def test_station_config_has_correct_fields(self):
        """Every StationConfig should have all required fields with correct types."""
        for city, config in STATION_CONFIGS.items():
            assert isinstance(config, StationConfig), f"{city} config is not a StationConfig"
            assert isinstance(config.city, str)
            assert isinstance(config.station_id, str)
            assert isinstance(config.lat, float)
            assert isinstance(config.lon, float)
            assert isinstance(config.nws_office, str)
            assert isinstance(config.timezone, ZoneInfo)
            assert isinstance(config.standard_utc_offset, int)

    def test_nyc_station_id_is_knyc(self):
        """NYC station_id must be KNYC (Central Park)."""
        assert STATION_CONFIGS["NYC"].station_id == "KNYC"
        assert STATION_CONFIGS["NYC"].city == "NYC"
        assert STATION_CONFIGS["NYC"].nws_office == "OKX"
        assert STATION_CONFIGS["NYC"].lat == pytest.approx(40.7828, abs=0.001)
        assert STATION_CONFIGS["NYC"].lon == pytest.approx(-73.9653, abs=0.001)
        assert STATION_CONFIGS["NYC"].standard_utc_offset == -5

    def test_chi_station_id_is_kmdw(self):
        """CHI station_id must be KMDW (Midway)."""
        assert STATION_CONFIGS["CHI"].station_id == "KMDW"
        assert STATION_CONFIGS["CHI"].city == "CHI"
        assert STATION_CONFIGS["CHI"].nws_office == "LOT"
        assert STATION_CONFIGS["CHI"].lat == pytest.approx(41.7868, abs=0.001)
        assert STATION_CONFIGS["CHI"].lon == pytest.approx(-87.7522, abs=0.001)
        assert STATION_CONFIGS["CHI"].standard_utc_offset == -6

    def test_mia_station_id_is_kmia(self):
        """MIA station_id must be KMIA (Miami International)."""
        assert STATION_CONFIGS["MIA"].station_id == "KMIA"
        assert STATION_CONFIGS["MIA"].city == "MIA"
        assert STATION_CONFIGS["MIA"].nws_office == "MFL"
        assert STATION_CONFIGS["MIA"].lat == pytest.approx(25.7959, abs=0.001)
        assert STATION_CONFIGS["MIA"].lon == pytest.approx(-80.2870, abs=0.001)
        assert STATION_CONFIGS["MIA"].standard_utc_offset == -5

    def test_aus_station_id_is_kaus(self):
        """AUS station_id must be KAUS (Bergstrom)."""
        assert STATION_CONFIGS["AUS"].station_id == "KAUS"
        assert STATION_CONFIGS["AUS"].city == "AUS"
        assert STATION_CONFIGS["AUS"].nws_office == "EWX"
        assert STATION_CONFIGS["AUS"].lat == pytest.approx(30.1945, abs=0.001)
        assert STATION_CONFIGS["AUS"].lon == pytest.approx(-97.6699, abs=0.001)
        assert STATION_CONFIGS["AUS"].standard_utc_offset == -6

    def test_grid_defaults_to_none(self):
        """Grid cache should default to None before first lookup."""
        config = StationConfig(
            city="TEST",
            station_id="KTEST",
            station_name="Test Station",
            lat=0.0,
            lon=0.0,
            nws_office="TST",
            timezone=ZoneInfo("UTC"),
            standard_utc_offset=0,
        )
        assert config.grid is None


# ─── Temperature Conversion Tests ───


class TestTemperatureConversions:
    """Verify Celsius/Fahrenheit conversion accuracy."""

    def test_celsius_to_fahrenheit_freezing(self):
        """0 degrees C equals 32 degrees F."""
        assert celsius_to_fahrenheit(0) == 32.0

    def test_celsius_to_fahrenheit_boiling(self):
        """100 degrees C equals 212 degrees F."""
        assert celsius_to_fahrenheit(100) == 212.0

    def test_celsius_to_fahrenheit_body_temp(self):
        """37 degrees C is approximately 98.6 degrees F."""
        assert celsius_to_fahrenheit(37) == pytest.approx(98.6, abs=0.1)

    def test_fahrenheit_to_celsius_freezing(self):
        """32 degrees F equals 0 degrees C."""
        assert fahrenheit_to_celsius(32) == 0.0

    def test_fahrenheit_to_celsius_boiling(self):
        """212 degrees F equals 100 degrees C."""
        assert fahrenheit_to_celsius(212) == 100.0

    def test_celsius_to_fahrenheit_negative_40(self):
        """-40 is the same in both scales."""
        assert celsius_to_fahrenheit(-40) == -40.0

    def test_celsius_to_fahrenheit_rounds_to_one_decimal(self):
        """Result should be rounded to 1 decimal place."""
        # 12.8 * 9/5 + 32 = 55.04 -> rounds to 55.0
        result = celsius_to_fahrenheit(12.8)
        assert result == 55.0

    def test_fahrenheit_to_celsius_rounds_to_one_decimal(self):
        """Result should be rounded to 1 decimal place."""
        # (55 - 32) * 5/9 = 12.7777... -> rounds to 12.8
        result = fahrenheit_to_celsius(55)
        assert result == 12.8


# ─── Timezone Helper Tests ───


class TestGetStandardTimeNow:
    """Verify get_standard_time_now returns timezone-aware datetimes."""

    def test_returns_timezone_aware_datetime(self):
        """Must return a timezone-aware datetime (not naive)."""
        result = get_standard_time_now("NYC")
        assert isinstance(result, datetime)
        assert result.tzinfo is not None
        assert result.utcoffset() is not None

    def test_nyc_offset_is_utc_minus_5(self):
        """NYC standard time has UTC offset -5 hours."""
        result = get_standard_time_now("NYC")
        assert result.utcoffset() == timedelta(hours=-5)

    def test_chi_offset_is_utc_minus_6(self):
        """CHI standard time has UTC offset -6 hours."""
        result = get_standard_time_now("CHI")
        assert result.utcoffset() == timedelta(hours=-6)

    def test_invalid_city_raises_key_error(self):
        """Invalid city code must raise KeyError."""
        with pytest.raises(KeyError):
            get_standard_time_now("INVALID")


class TestGetSettlementDate:
    """Verify get_settlement_date returns correct YYYY-MM-DD format."""

    def test_settlement_date_format(self):
        """Settlement date must match YYYY-MM-DD pattern."""
        for city in VALID_CITIES:
            result = get_settlement_date(city)
            assert re.match(r"^\d{4}-\d{2}-\d{2}$", result), (
                f"Settlement date for {city} has wrong format: {result}"
            )

    def test_settlement_date_is_valid_date(self):
        """Settlement date must parse as a valid date."""
        for city in VALID_CITIES:
            result = get_settlement_date(city)
            parsed = datetime.strptime(result, "%Y-%m-%d")
            assert parsed is not None


class TestIsForecastForToday:
    """Verify is_forecast_for_today returns bool."""

    def test_returns_bool(self):
        """Must return a boolean value."""
        today = get_settlement_date("NYC")
        result = is_forecast_for_today(today, "NYC")
        assert isinstance(result, bool)

    def test_matching_date_returns_true(self):
        """Today's settlement date should match itself."""
        today = get_settlement_date("NYC")
        assert is_forecast_for_today(today, "NYC") is True

    def test_different_date_returns_false(self):
        """A clearly different date should not match today."""
        assert is_forecast_for_today("2000-01-01", "NYC") is False
