"""NWS station configuration for all Kalshi weather market cities.

Each city maps to a specific NWS observation station, forecast office,
and timezone. These are the EXACT stations Kalshi uses for settlement.

CRITICAL: Kalshi settles on LOCAL STANDARD TIME (LST), not daylight
saving time. Use the fixed UTC offsets here, NOT the tz-aware ZoneInfo,
when computing settlement dates.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta, timezone
from zoneinfo import ZoneInfo


@dataclass
class StationConfig:
    """Configuration for a single NWS observation station.

    Attributes:
        city: Kalshi city code (NYC, CHI, MIA, AUS).
        station_id: NWS station identifier (e.g., KNYC).
        station_name: Human-readable station name.
        lat: Station latitude in decimal degrees.
        lon: Station longitude in decimal degrees.
        nws_office: NWS forecast office code (e.g., OKX).
        timezone: IANA timezone for the station (used for Open-Meteo requests).
        standard_utc_offset: UTC offset for LOCAL STANDARD TIME (ignoring DST).
            This is what Kalshi uses for settlement.
        grid: Cached NWS grid coordinates after first lookup. Dict with keys
            'office', 'x', 'y'. None until populated by get_grid_coordinates().
    """

    city: str
    station_id: str
    station_name: str
    lat: float
    lon: float
    nws_office: str
    timezone: ZoneInfo
    standard_utc_offset: int
    grid: dict | None = field(default=None)


# ─── Station Configurations ───
# These are the EXACT stations and coordinates Kalshi uses for settlement.

STATION_CONFIGS: dict[str, StationConfig] = {
    "NYC": StationConfig(
        city="NYC",
        station_id="KNYC",
        station_name="Central Park",
        lat=40.7828,
        lon=-73.9653,
        nws_office="OKX",
        timezone=ZoneInfo("America/New_York"),
        standard_utc_offset=-5,
    ),
    "CHI": StationConfig(
        city="CHI",
        station_id="KMDW",
        station_name="Midway",
        lat=41.7868,
        lon=-87.7522,
        nws_office="LOT",
        timezone=ZoneInfo("America/Chicago"),
        standard_utc_offset=-6,
    ),
    "MIA": StationConfig(
        city="MIA",
        station_id="KMIA",
        station_name="Miami Intl",
        lat=25.7959,
        lon=-80.2870,
        nws_office="MFL",
        timezone=ZoneInfo("America/New_York"),
        standard_utc_offset=-5,
    ),
    "AUS": StationConfig(
        city="AUS",
        station_id="KAUS",
        station_name="Bergstrom",
        lat=30.1945,
        lon=-97.6699,
        nws_office="EWX",
        timezone=ZoneInfo("America/Chicago"),
        standard_utc_offset=-6,
    ),
}

VALID_CITIES: list[str] = list(STATION_CONFIGS.keys())


# ─── Timezone Helpers ───


def get_standard_time_now(city: str) -> datetime:
    """Get the current time in a city's LOCAL STANDARD TIME.

    Kalshi settles weather markets using local standard time,
    ignoring daylight saving time. This means during DST months,
    the settlement "day" does NOT shift with wall-clock time.

    Args:
        city: Kalshi city code (NYC, CHI, MIA, AUS).

    Returns:
        Timezone-aware datetime in the city's standard time.

    Raises:
        KeyError: If city is not a valid city code.
    """
    config = STATION_CONFIGS[city]
    standard_tz = timezone(timedelta(hours=config.standard_utc_offset))
    return datetime.now(UTC).astimezone(standard_tz)


def get_settlement_date(city: str) -> str:
    """Get today's settlement date in YYYY-MM-DD format.

    Uses local standard time (not DST) to determine which calendar
    day is "today" for Kalshi settlement purposes.

    Args:
        city: Kalshi city code (NYC, CHI, MIA, AUS).

    Returns:
        Date string in YYYY-MM-DD format.
    """
    return get_standard_time_now(city).strftime("%Y-%m-%d")


def is_forecast_for_today(forecast_date: str, city: str) -> bool:
    """Check if a forecast date matches today's settlement date.

    Args:
        forecast_date: Date string in YYYY-MM-DD format.
        city: Kalshi city code.

    Returns:
        True if the forecast date matches today's settlement date.
    """
    return forecast_date == get_settlement_date(city)


# ─── Temperature Conversion ───


def celsius_to_fahrenheit(c: float) -> float:
    """Convert Celsius to Fahrenheit.

    Args:
        c: Temperature in degrees Celsius.

    Returns:
        Temperature in degrees Fahrenheit, rounded to 1 decimal place.
    """
    return round((c * 9 / 5) + 32, 1)


def fahrenheit_to_celsius(f: float) -> float:
    """Convert Fahrenheit to Celsius.

    Args:
        f: Temperature in degrees Fahrenheit.

    Returns:
        Temperature in degrees Celsius, rounded to 1 decimal place.
    """
    return round((f - 32) * 5 / 9, 1)
