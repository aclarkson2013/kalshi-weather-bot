"""Data normalization — converts raw API responses into WeatherData schema.

Each external source (NWS period forecast, NWS gridpoint, Open-Meteo)
returns data in a different structure and sometimes in different units.
This module normalizes everything into the standard WeatherData schema
defined in backend.common.schemas.

Temperature conversion rules:
  - NWS period forecast: Fahrenheit (use directly)
  - NWS gridpoint data:  Celsius (MUST convert to Fahrenheit!)
  - Open-Meteo with temperature_unit=fahrenheit: Fahrenheit (use directly)
"""

from __future__ import annotations

from datetime import UTC, date, datetime

from backend.common.logging import get_logger
from backend.common.schemas import WeatherData, WeatherVariables
from backend.weather.exceptions import ParseError
from backend.weather.stations import celsius_to_fahrenheit

logger = get_logger("WEATHER")


# ─── NWS Period Forecast Normalizer ───


def normalize_nws_forecast(
    city: str,
    raw_response: dict,
) -> list[WeatherData]:
    """Normalize NWS 12-hour period forecast response into WeatherData list.

    Extracts daytime periods (isDaytime=True) from the forecast and
    creates a WeatherData object for each. The period forecast returns
    temperatures in Fahrenheit, so no conversion is needed.

    Args:
        city: Kalshi city code (NYC, CHI, MIA, AUS).
        raw_response: Full JSON response from the NWS forecast endpoint.

    Returns:
        List of WeatherData objects, one per daytime forecast period.

    Raises:
        ParseError: If the response structure is unexpected.
    """
    try:
        periods = raw_response["properties"]["periods"]
    except (KeyError, TypeError) as exc:
        raise ParseError(f"NWS forecast response missing properties.periods for {city}") from exc

    results: list[WeatherData] = []
    now = datetime.now(UTC)

    for period in periods:
        # Only extract daytime periods (which contain high temperatures)
        if not period.get("isDaytime", False):
            continue

        try:
            start_time_str = period["startTime"]
            start_time = datetime.fromisoformat(start_time_str)
            forecast_date = start_time.date()

            temperature = float(period["temperature"])
            temp_unit = period.get("temperatureUnit", "F")

            # NWS period forecasts should always be Fahrenheit,
            # but handle Celsius just in case
            if temp_unit == "C":
                temperature = celsius_to_fahrenheit(temperature)

            # Parse wind speed — NWS returns strings like "10 to 15 mph"
            wind_speed = _parse_nws_wind_speed(period.get("windSpeed", ""))

            variables = WeatherVariables(
                temp_high_f=temperature,
                temp_low_f=None,  # Period forecast only gives high for daytime
                humidity_pct=None,
                wind_speed_mph=wind_speed,
                wind_gust_mph=None,
                cloud_cover_pct=None,
                dew_point_f=None,
                pressure_mb=None,
            )

            weather_data = WeatherData(
                city=city,
                date=forecast_date,
                forecast_high_f=temperature,
                source="NWS",
                model_run_timestamp=now,
                variables=variables,
                raw_data={"period": period},
                fetched_at=now,
            )
            results.append(weather_data)

        except (KeyError, TypeError, ValueError) as exc:
            logger.warning(
                "Skipping malformed NWS forecast period",
                extra={
                    "data": {
                        "city": city,
                        "period_name": period.get("name", "unknown"),
                        "error": str(exc),
                    }
                },
            )
            continue

    return results


# ─── NWS Gridpoint Normalizer ───


def normalize_nws_gridpoint(
    city: str,
    raw_response: dict,
) -> list[WeatherData]:
    """Normalize NWS raw gridpoint data into WeatherData list.

    CRITICAL: All temperature values in raw gridpoint data are in CELSIUS.
    They MUST be converted to Fahrenheit before storage.

    The gridpoint endpoint provides more granular data than the period
    forecast, including humidity, wind, dewpoint, and pressure.

    Args:
        city: Kalshi city code (NYC, CHI, MIA, AUS).
        raw_response: Full JSON response from the NWS gridpoint endpoint.

    Returns:
        List of WeatherData objects, one per forecast day.

    Raises:
        ParseError: If the response structure is unexpected.
    """
    try:
        properties = raw_response["properties"]
    except (KeyError, TypeError) as exc:
        raise ParseError(f"NWS gridpoint response missing properties for {city}") from exc

    # Extract max temperature values (in Celsius!)
    max_temps = _extract_gridpoint_values(properties, "maxTemperature")
    if not max_temps:
        logger.warning(
            "No maxTemperature data in NWS gridpoint response",
            extra={"data": {"city": city}},
        )
        return []

    # Extract supplementary variables
    min_temps = _extract_gridpoint_values(properties, "minTemperature")
    humidity_values = _extract_gridpoint_values(properties, "relativeHumidity")
    wind_values = _extract_gridpoint_values(properties, "windSpeed")
    gust_values = _extract_gridpoint_values(properties, "windGust")
    dewpoint_values = _extract_gridpoint_values(properties, "dewpoint")
    pressure_values = _extract_gridpoint_values(properties, "pressure")

    # Build date-indexed lookup for supplementary variables
    min_temp_by_date = _values_by_date(min_temps)
    humidity_by_date = _values_by_date(humidity_values)
    wind_by_date = _values_by_date(wind_values)
    gust_by_date = _values_by_date(gust_values)
    dewpoint_by_date = _values_by_date(dewpoint_values)
    pressure_by_date = _values_by_date(pressure_values)

    results: list[WeatherData] = []
    now = datetime.now(UTC)

    for entry in max_temps:
        try:
            valid_time_str = entry["validTime"].split("/")[0]
            valid_time = datetime.fromisoformat(valid_time_str)
            forecast_date = valid_time.date()

            # CRITICAL: Convert from Celsius to Fahrenheit
            temp_c = float(entry["value"])
            temp_high_f = celsius_to_fahrenheit(temp_c)

            # Get supplementary data for this date
            min_temp_c = min_temp_by_date.get(forecast_date)
            temp_low_f = celsius_to_fahrenheit(min_temp_c) if min_temp_c is not None else None

            # Dewpoint is also in Celsius
            dewpoint_c = dewpoint_by_date.get(forecast_date)
            dewpoint_f = celsius_to_fahrenheit(dewpoint_c) if dewpoint_c is not None else None

            # Wind speed from gridpoint is in km/h — convert to mph
            wind_kmh = wind_by_date.get(forecast_date)
            wind_mph = round(wind_kmh * 0.621371, 1) if wind_kmh is not None else None

            gust_kmh = gust_by_date.get(forecast_date)
            gust_mph = round(gust_kmh * 0.621371, 1) if gust_kmh is not None else None

            # Pressure from gridpoint is in Pa — convert to mb (hPa)
            pressure_pa = pressure_by_date.get(forecast_date)
            pressure_mb = round(pressure_pa / 100.0, 1) if pressure_pa is not None else None

            variables = WeatherVariables(
                temp_high_f=temp_high_f,
                temp_low_f=temp_low_f,
                humidity_pct=humidity_by_date.get(forecast_date),
                wind_speed_mph=wind_mph,
                wind_gust_mph=gust_mph,
                cloud_cover_pct=None,  # Not in gridpoint data
                dew_point_f=dewpoint_f,
                pressure_mb=pressure_mb,
            )

            weather_data = WeatherData(
                city=city,
                date=forecast_date,
                forecast_high_f=temp_high_f,
                source="NWS:gridpoint",
                model_run_timestamp=now,
                variables=variables,
                raw_data={
                    "maxTemperature_entry": entry,
                    "validTime": valid_time_str,
                },
                fetched_at=now,
            )
            results.append(weather_data)

        except (KeyError, TypeError, ValueError) as exc:
            logger.warning(
                "Skipping malformed NWS gridpoint entry",
                extra={
                    "data": {
                        "city": city,
                        "entry": str(entry)[:200],
                        "error": str(exc),
                    }
                },
            )
            continue

    return results


# ─── Open-Meteo Normalizer ───


def normalize_openmeteo(
    city: str,
    source_label: str,
    model_daily: dict,
    raw_response: dict,
) -> list[WeatherData]:
    """Normalize Open-Meteo per-model daily data into WeatherData list.

    Open-Meteo data requested with temperature_unit=fahrenheit is already
    in Fahrenheit, so NO conversion is needed.

    Args:
        city: Kalshi city code (NYC, CHI, MIA, AUS).
        source_label: Source identifier (e.g., "Open-Meteo:GFS").
        model_daily: Dict with 'time' and variable arrays for one model.
        raw_response: Full API response (stored in raw_data for audit).

    Returns:
        List of WeatherData objects, one per forecast day.

    Raises:
        ParseError: If the daily data structure is unexpected.
    """
    try:
        dates = model_daily["time"]
    except (KeyError, TypeError) as exc:
        raise ParseError(f"Open-Meteo daily data missing 'time' array for {city}") from exc

    # Extract temperature arrays (already in Fahrenheit)
    temp_max = model_daily.get("temperature_2m_max", [])
    temp_min = model_daily.get("temperature_2m_min", [])

    # Extract additional variables
    wind_max = model_daily.get("windspeed_10m_max", [])
    gust_max = model_daily.get("windgusts_10m_max", [])
    humidity_max = model_daily.get("relative_humidity_2m_max", [])
    cloud_mean = model_daily.get("cloudcover_mean", [])
    dewpoint_min = model_daily.get("dewpoint_2m_min", [])
    pressure_mean = model_daily.get("surface_pressure_mean", [])

    results: list[WeatherData] = []
    now = datetime.now(UTC)

    for i, date_str in enumerate(dates):
        try:
            forecast_date = date.fromisoformat(date_str)

            # Get high temperature (required)
            high_f = _safe_float_at(temp_max, i)
            if high_f is None:
                logger.warning(
                    "Missing temp_max in Open-Meteo response",
                    extra={
                        "data": {
                            "city": city,
                            "source": source_label,
                            "date": date_str,
                        }
                    },
                )
                continue

            # Get optional variables
            low_f = _safe_float_at(temp_min, i)
            wind_mph = _safe_float_at(wind_max, i)
            gust_mph = _safe_float_at(gust_max, i)
            humidity = _safe_float_at(humidity_max, i)
            cloud_cover = _safe_float_at(cloud_mean, i)
            dewpoint = _safe_float_at(dewpoint_min, i)
            pressure = _safe_float_at(pressure_mean, i)

            variables = WeatherVariables(
                temp_high_f=high_f,
                temp_low_f=low_f,
                humidity_pct=humidity,
                wind_speed_mph=wind_mph,
                wind_gust_mph=gust_mph,
                cloud_cover_pct=cloud_cover,
                dew_point_f=dewpoint,
                pressure_mb=pressure,
            )

            weather_data = WeatherData(
                city=city,
                date=forecast_date,
                forecast_high_f=high_f,
                source=source_label,
                model_run_timestamp=now,
                variables=variables,
                raw_data={
                    "model_daily_index": i,
                    "date": date_str,
                    "source": source_label,
                },
                fetched_at=now,
            )
            results.append(weather_data)

        except (ValueError, TypeError) as exc:
            logger.warning(
                "Skipping malformed Open-Meteo daily entry",
                extra={
                    "data": {
                        "city": city,
                        "source": source_label,
                        "index": i,
                        "error": str(exc),
                    }
                },
            )
            continue

    return results


# ─── Internal Helpers ───


def _parse_nws_wind_speed(wind_str: str) -> float | None:
    """Parse NWS wind speed string into a numeric value.

    NWS returns wind speed as strings like "10 mph", "10 to 15 mph",
    or "5 to 10 mph". We extract the maximum value from the range.

    Args:
        wind_str: Wind speed string from NWS.

    Returns:
        Maximum wind speed in mph, or None if parsing fails.
    """
    if not wind_str:
        return None

    # Remove "mph" and extra whitespace
    cleaned = wind_str.lower().replace("mph", "").strip()

    # Handle range format: "10 to 15"
    if " to " in cleaned:
        parts = cleaned.split(" to ")
        try:
            return float(parts[-1].strip())
        except (ValueError, IndexError):
            return None

    # Handle single value: "10"
    try:
        return float(cleaned)
    except ValueError:
        return None


def _extract_gridpoint_values(
    properties: dict,
    variable_name: str,
) -> list[dict]:
    """Extract value entries from a NWS gridpoint property.

    Args:
        properties: The 'properties' dict from the gridpoint response.
        variable_name: The NWS variable name (e.g., 'maxTemperature').

    Returns:
        List of value entry dicts with 'validTime' and 'value' keys.
        Empty list if the variable is not present.
    """
    variable_data = properties.get(variable_name, {})
    if not isinstance(variable_data, dict):
        return []
    return variable_data.get("values", [])


def _values_by_date(
    values: list[dict],
) -> dict[date, float]:
    """Index gridpoint values by date for easy lookup.

    Takes the FIRST value encountered for each date (typically the
    daily maximum or minimum).

    Args:
        values: List of NWS gridpoint value entries.

    Returns:
        Dict mapping dates to float values.
    """
    result: dict[date, float] = {}
    for entry in values:
        try:
            valid_time_str = entry["validTime"].split("/")[0]
            valid_time = datetime.fromisoformat(valid_time_str)
            entry_date = valid_time.date()
            # Take the first value for each date
            if entry_date not in result:
                result[entry_date] = float(entry["value"])
        except (KeyError, TypeError, ValueError):
            continue
    return result


def _safe_float_at(
    values: list,
    index: int,
) -> float | None:
    """Safely extract a float from a list at a given index.

    Args:
        values: List of values (may contain None).
        index: Index to extract from.

    Returns:
        Float value, or None if index is out of range or value is None.
    """
    if not values or index >= len(values):
        return None
    value = values[index]
    if value is None:
        return None
    try:
        return float(value)
    except (ValueError, TypeError):
        return None
