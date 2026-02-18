"""Open-Meteo API client for multi-model weather forecasts.

Fetches forecasts from multiple numerical weather prediction models
(GFS, ECMWF IFS, ICON) via the Open-Meteo free API. All temperature
data is requested in Fahrenheit so no conversion is needed.

API docs: https://open-meteo.com/en/docs
"""

from __future__ import annotations

import asyncio

import httpx

from backend.common.logging import get_logger
from backend.common.schemas import WeatherData
from backend.weather.exceptions import FetchError
from backend.weather.normalizer import normalize_openmeteo
from backend.weather.rate_limiter import openmeteo_limiter
from backend.weather.stations import STATION_CONFIGS

logger = get_logger("WEATHER")

OPENMETEO_BASE_URL = "https://api.open-meteo.com/v1/forecast"

# Models to fetch — each provides an independent forecast
OPENMETEO_MODELS = ["gfs_seamless", "ecmwf_ifs025", "icon_seamless"]

# Map internal model names to human-readable source labels
MODEL_SOURCE_LABELS: dict[str, str] = {
    "gfs_seamless": "Open-Meteo:GFS",
    "ecmwf_ifs025": "Open-Meteo:ECMWF",
    "icon_seamless": "Open-Meteo:ICON",
}

# Daily variables to request from each model
DAILY_VARIABLES = [
    "temperature_2m_max",
    "temperature_2m_min",
    "windspeed_10m_max",
    "windgusts_10m_max",
    "relative_humidity_2m_max",
    "cloudcover_mean",
    "dewpoint_2m_min",
    "surface_pressure_mean",
]


async def _fetch_openmeteo_with_retry(
    params: dict,
    max_retries: int = 3,
) -> dict:
    """Fetch Open-Meteo API with retry and rate limiting.

    Creates a NEW httpx.AsyncClient per call to avoid connection pooling
    issues across Celery tasks.

    Args:
        params: Query parameters for the Open-Meteo API.
        max_retries: Maximum number of retries after initial attempt.

    Returns:
        Parsed JSON response as a dict.

    Raises:
        FetchError: If all retries are exhausted.
    """
    last_error: Exception | None = None

    for attempt in range(max_retries + 1):
        try:
            await openmeteo_limiter.acquire()
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(
                    OPENMETEO_BASE_URL,
                    params=params,
                )
                response.raise_for_status()
                return response.json()

        except httpx.HTTPStatusError as exc:
            last_error = exc
            status_code = exc.response.status_code

            if status_code >= 500 and attempt < max_retries:
                wait = 2**attempt
                logger.warning(
                    f"Open-Meteo returned {status_code}, retrying",
                    extra={
                        "data": {
                            "status_code": status_code,
                            "attempt": attempt + 1,
                            "wait_seconds": wait,
                        }
                    },
                )
                await asyncio.sleep(wait)
            else:
                logger.error(
                    "Open-Meteo HTTP error",
                    extra={
                        "data": {
                            "status_code": status_code,
                            "attempts": attempt + 1,
                        }
                    },
                )
                raise FetchError(
                    f"Open-Meteo HTTP {status_code} after {attempt + 1} attempts"
                ) from exc

        except httpx.RequestError as exc:
            last_error = exc

            if attempt < max_retries:
                wait = 2**attempt
                logger.warning(
                    "Open-Meteo network error, retrying",
                    extra={
                        "data": {
                            "error": str(exc),
                            "attempt": attempt + 1,
                            "wait_seconds": wait,
                        }
                    },
                )
                await asyncio.sleep(wait)
            else:
                logger.error(
                    "Open-Meteo network error, all retries exhausted",
                    extra={"data": {"error": str(exc)}},
                )
                raise FetchError(
                    f"Open-Meteo network error after {attempt + 1} attempts: {exc}"
                ) from exc

    raise FetchError("All Open-Meteo retries exhausted") from last_error


async def fetch_openmeteo_forecast(city: str) -> list[WeatherData]:
    """Fetch forecasts from Open-Meteo for all configured models.

    Makes a single API call requesting multiple models. Open-Meteo
    returns each model's data in separate keys within the response.
    Returns one WeatherData per model per forecast day.

    Temperature is requested in Fahrenheit (temperature_unit=fahrenheit)
    so NO conversion is needed.

    Args:
        city: Kalshi city code (NYC, CHI, MIA, AUS).

    Returns:
        List of WeatherData objects, one per model per day.
        With 3 models and 7 forecast days, returns up to 21 items.

    Raises:
        FetchError: If the API call fails after retries.
        ParseError: If the response structure is unexpected.
    """
    config = STATION_CONFIGS[city]

    params = {
        "latitude": config.lat,
        "longitude": config.lon,
        "daily": ",".join(DAILY_VARIABLES),
        "models": ",".join(OPENMETEO_MODELS),
        "temperature_unit": "fahrenheit",
        "windspeed_unit": "mph",
        "timezone": str(config.timezone),
        "forecast_days": 7,
    }

    logger.info(
        "Fetching Open-Meteo multi-model forecast",
        extra={
            "data": {
                "city": city,
                "models": OPENMETEO_MODELS,
                "lat": config.lat,
                "lon": config.lon,
            }
        },
    )

    raw_response = await _fetch_openmeteo_with_retry(params)

    # Parse each model's data from the response
    all_results: list[WeatherData] = []

    for model_name in OPENMETEO_MODELS:
        source_label = MODEL_SOURCE_LABELS.get(model_name, f"Open-Meteo:{model_name}")

        # Open-Meteo nests multi-model data under the model name
        # For single model: data is in "daily" directly
        # For multi-model: data may be in "daily" with model-prefixed keys,
        # or nested under model name
        try:
            model_daily = _extract_model_daily(raw_response, model_name)
        except (KeyError, TypeError):
            logger.warning(
                f"Model {model_name} missing from Open-Meteo response",
                extra={"data": {"city": city, "model": model_name}},
            )
            continue

        if model_daily is None:
            logger.warning(
                f"No daily data for model {model_name}",
                extra={"data": {"city": city, "model": model_name}},
            )
            continue

        try:
            model_results = normalize_openmeteo(city, source_label, model_daily, raw_response)
            all_results.extend(model_results)
        except Exception as exc:
            logger.warning(
                f"Failed to normalize Open-Meteo {model_name} data",
                extra={
                    "data": {
                        "city": city,
                        "model": model_name,
                        "error": str(exc),
                    }
                },
            )

    logger.info(
        "Parsed Open-Meteo forecasts",
        extra={
            "data": {
                "city": city,
                "total_forecasts": len(all_results),
                "models_parsed": len({r.source for r in all_results}),
            }
        },
    )

    return all_results


def _extract_model_daily(
    raw_response: dict,
    model_name: str,
) -> dict | None:
    """Extract daily forecast data for a specific model from the response.

    Open-Meteo multi-model responses have different structures depending
    on the number of models requested. This function handles both cases:
    1. Single model: data in raw_response["daily"]
    2. Multi-model: data in raw_response["daily"] with model-suffixed keys,
       OR nested under raw_response[model_name]["daily"]

    Args:
        raw_response: Full Open-Meteo API response.
        model_name: The model identifier (e.g., "gfs_seamless").

    Returns:
        Dict containing the daily forecast data for the model, or None
        if the model's data is not found.
    """
    # Case 1: Multi-model response where each model has its own top-level key
    if model_name in raw_response:
        model_data = raw_response[model_name]
        if isinstance(model_data, dict) and "daily" in model_data:
            return model_data["daily"]

    # Case 2: Single "daily" block with model-specific variable keys
    # Open-Meteo may prefix variables like "temperature_2m_max_gfs_seamless"
    daily = raw_response.get("daily")
    if daily is None:
        return None

    # Check if time array exists (required for any valid daily data)
    if "time" not in daily:
        return None

    # Look for model-specific keys (e.g., "temperature_2m_max_gfs_seamless")
    model_suffix = f"_{model_name}"
    model_keys = [k for k in daily if k.endswith(model_suffix)]

    if model_keys:
        # Remap model-specific keys to standard variable names
        result: dict = {"time": daily["time"]}
        for key in model_keys:
            # Strip the model suffix to get the standard variable name
            standard_key = key[: -len(model_suffix)]
            result[standard_key] = daily[key]
        return result

    # Case 3: Single model requested — data is directly in "daily"
    if len(OPENMETEO_MODELS) == 1:
        return daily

    # If we have multiple models but no model-specific keys, the data
    # might be in the generic daily block (fallback for single-model case)
    if "temperature_2m_max" in daily:
        return daily

    return None
