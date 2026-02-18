"""Shared fixtures for weather module tests.

Provides realistic mock API response dicts for NWS and Open-Meteo endpoints,
matching the actual JSON structures returned by those APIs.
"""

from __future__ import annotations

import pytest

# ─── NWS Period Forecast Response ───


@pytest.fixture
def sample_nws_forecast_response() -> dict:
    """A dict mimicking NWS /gridpoints/{o}/{x},{y}/forecast response.

    Includes both daytime and nighttime periods for two consecutive days.
    Temperatures are in Fahrenheit (as NWS period forecasts always are).
    """
    return {
        "properties": {
            "periods": [
                {
                    "number": 1,
                    "name": "Today",
                    "startTime": "2026-02-17T06:00:00-05:00",
                    "endTime": "2026-02-17T18:00:00-05:00",
                    "isDaytime": True,
                    "temperature": 55,
                    "temperatureUnit": "F",
                    "windSpeed": "10 to 15 mph",
                    "windDirection": "NW",
                    "shortForecast": "Partly Cloudy",
                    "detailedForecast": "Partly cloudy, with a high near 55.",
                },
                {
                    "number": 2,
                    "name": "Tonight",
                    "startTime": "2026-02-17T18:00:00-05:00",
                    "endTime": "2026-02-18T06:00:00-05:00",
                    "isDaytime": False,
                    "temperature": 38,
                    "temperatureUnit": "F",
                    "windSpeed": "5 mph",
                    "windDirection": "N",
                    "shortForecast": "Clear",
                    "detailedForecast": "Clear, with a low around 38.",
                },
                {
                    "number": 3,
                    "name": "Wednesday",
                    "startTime": "2026-02-18T06:00:00-05:00",
                    "endTime": "2026-02-18T18:00:00-05:00",
                    "isDaytime": True,
                    "temperature": 60,
                    "temperatureUnit": "F",
                    "windSpeed": "8 mph",
                    "windDirection": "S",
                    "shortForecast": "Sunny",
                    "detailedForecast": "Sunny, with a high near 60.",
                },
                {
                    "number": 4,
                    "name": "Wednesday Night",
                    "startTime": "2026-02-18T18:00:00-05:00",
                    "endTime": "2026-02-19T06:00:00-05:00",
                    "isDaytime": False,
                    "temperature": 42,
                    "temperatureUnit": "F",
                    "windSpeed": "5 to 10 mph",
                    "windDirection": "SW",
                    "shortForecast": "Mostly Clear",
                    "detailedForecast": "Mostly clear, with a low around 42.",
                },
            ]
        }
    }


# ─── NWS Raw Gridpoint Response ───


@pytest.fixture
def sample_nws_gridpoint_response() -> dict:
    """A dict mimicking NWS /gridpoints/{o}/{x},{y} response.

    CRITICAL: All temperature values (maxTemperature, minTemperature, dewpoint)
    are in CELSIUS. Wind speed is in km/h. Pressure is in Pa.
    These MUST be converted before use.

    Contains data for two days (2026-02-17 and 2026-02-18).
    """
    return {
        "properties": {
            "maxTemperature": {
                "values": [
                    {
                        "validTime": "2026-02-17T11:00:00+00:00/PT12H",
                        "value": 12.8,  # 55.04 F
                    },
                    {
                        "validTime": "2026-02-18T11:00:00+00:00/PT12H",
                        "value": 15.6,  # 60.08 F
                    },
                ]
            },
            "minTemperature": {
                "values": [
                    {
                        "validTime": "2026-02-17T00:00:00+00:00/PT12H",
                        "value": 3.5,  # 38.3 F
                    },
                    {
                        "validTime": "2026-02-18T00:00:00+00:00/PT12H",
                        "value": 5.0,  # 41.0 F
                    },
                ]
            },
            "relativeHumidity": {
                "values": [
                    {
                        "validTime": "2026-02-17T06:00:00+00:00/PT6H",
                        "value": 75,
                    },
                    {
                        "validTime": "2026-02-18T06:00:00+00:00/PT6H",
                        "value": 68,
                    },
                ]
            },
            "windSpeed": {
                "values": [
                    {
                        "validTime": "2026-02-17T12:00:00+00:00/PT6H",
                        "value": 24.1,  # km/h -> ~14.97 mph
                    },
                    {
                        "validTime": "2026-02-18T12:00:00+00:00/PT6H",
                        "value": 16.1,  # km/h -> ~10.0 mph
                    },
                ]
            },
            "windGust": {
                "values": [
                    {
                        "validTime": "2026-02-17T12:00:00+00:00/PT6H",
                        "value": 40.2,  # km/h -> ~24.97 mph
                    },
                    {
                        "validTime": "2026-02-18T12:00:00+00:00/PT6H",
                        "value": 32.2,  # km/h -> ~20.0 mph
                    },
                ]
            },
            "dewpoint": {
                "values": [
                    {
                        "validTime": "2026-02-17T06:00:00+00:00/PT6H",
                        "value": 1.5,  # C -> 34.7 F
                    },
                    {
                        "validTime": "2026-02-18T06:00:00+00:00/PT6H",
                        "value": 3.0,  # C -> 37.4 F
                    },
                ]
            },
            "pressure": {
                "values": [
                    {
                        "validTime": "2026-02-17T06:00:00+00:00/PT6H",
                        "value": 101325,  # Pa -> 1013.25 mb (hPa)
                    },
                    {
                        "validTime": "2026-02-18T06:00:00+00:00/PT6H",
                        "value": 101000,  # Pa -> 1010.0 mb
                    },
                ]
            },
        }
    }


# ─── NWS Points Response ───


@pytest.fixture
def sample_nws_points_response() -> dict:
    """A dict mimicking NWS /points/{lat},{lon} response.

    Returns grid coordinate information for NYC (Central Park).
    """
    return {
        "properties": {
            "gridId": "OKX",
            "gridX": 33,
            "gridY": 37,
            "forecast": "https://api.weather.gov/gridpoints/OKX/33,37/forecast",
            "forecastHourly": "https://api.weather.gov/gridpoints/OKX/33,37/forecast/hourly",
            "forecastGridData": "https://api.weather.gov/gridpoints/OKX/33,37",
        }
    }


# ─── Open-Meteo Multi-Model Response ───


@pytest.fixture
def sample_openmeteo_response() -> dict:
    """A dict mimicking Open-Meteo multi-model forecast response.

    Contains daily data for two models (gfs_seamless and ecmwf_ifs025) nested
    under their model name keys, plus a suffix-keyed variant in the "daily"
    block for icon_seamless.

    All temperatures are in Fahrenheit (requested via temperature_unit=fahrenheit).
    Wind speeds are in mph (requested via windspeed_unit=mph).
    """
    return {
        "latitude": 40.78,
        "longitude": -73.97,
        "timezone": "America/New_York",
        "timezone_abbreviation": "EST",
        "daily_units": {
            "temperature_2m_max": "\u00b0F",
            "temperature_2m_min": "\u00b0F",
            "windspeed_10m_max": "mp/h",
        },
        # Model 1: GFS - nested under model name
        "gfs_seamless": {
            "daily": {
                "time": ["2026-02-17", "2026-02-18", "2026-02-19"],
                "temperature_2m_max": [55.2, 52.1, 58.3],
                "temperature_2m_min": [38.5, 35.2, 40.1],
                "windspeed_10m_max": [15.5, 12.3, 18.7],
                "windgusts_10m_max": [25.0, 20.0, 30.0],
                "relative_humidity_2m_max": [75, 68, 72],
                "cloudcover_mean": [45, 20, 60],
                "dewpoint_2m_min": [32.5, 28.1, 35.0],
                "surface_pressure_mean": [1013.2, 1010.5, 1015.0],
            }
        },
        # Model 2: ECMWF - nested under model name
        "ecmwf_ifs025": {
            "daily": {
                "time": ["2026-02-17", "2026-02-18", "2026-02-19"],
                "temperature_2m_max": [54.8, 51.5, 57.9],
                "temperature_2m_min": [37.9, 34.8, 39.5],
                "windspeed_10m_max": [14.2, 11.8, 17.5],
                "windgusts_10m_max": [23.5, 18.5, 28.0],
                "relative_humidity_2m_max": [73, 66, 70],
                "cloudcover_mean": [50, 25, 55],
                "dewpoint_2m_min": [31.8, 27.5, 34.2],
                "surface_pressure_mean": [1013.5, 1011.0, 1015.3],
            }
        },
        # Model 3: ICON - uses suffix-keyed format in shared "daily" block
        "daily": {
            "time": ["2026-02-17", "2026-02-18", "2026-02-19"],
            "temperature_2m_max_icon_seamless": [56.0, 53.2, 59.1],
            "temperature_2m_min_icon_seamless": [39.0, 36.0, 41.0],
            "windspeed_10m_max_icon_seamless": [16.0, 13.0, 19.5],
            "windgusts_10m_max_icon_seamless": [26.0, 21.0, 31.0],
            "relative_humidity_2m_max_icon_seamless": [77, 70, 74],
            "cloudcover_mean_icon_seamless": [40, 18, 58],
            "dewpoint_2m_min_icon_seamless": [33.0, 29.0, 36.0],
            "surface_pressure_mean_icon_seamless": [1012.8, 1010.0, 1014.8],
        },
    }
