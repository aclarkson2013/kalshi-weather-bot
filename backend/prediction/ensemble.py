"""Weighted ensemble forecast from multiple weather sources + confidence assessment.

Combines NWS, ECMWF, GFS, ICON, and GEM forecasts into a single best-estimate
temperature, with spread and confidence metrics.

Usage:
    from backend.prediction.ensemble import calculate_ensemble_forecast, assess_confidence

    temp, spread, sources = calculate_ensemble_forecast(forecasts)
    confidence = assess_confidence(spread, error_std, len(sources), data_age)
"""

from __future__ import annotations

from backend.common.logging import get_logger
from backend.common.schemas import WeatherData

logger = get_logger("MODEL")

# Default weights -- can be overridden per-city in config.
# These should be tuned based on historical accuracy.
# ECMWF generally gets higher weight -- it is the most accurate model globally.
DEFAULT_MODEL_WEIGHTS: dict[str, float] = {
    "NWS": 0.35,
    "Open-Meteo:ECMWF": 0.30,
    "Open-Meteo:GFS": 0.20,
    "Open-Meteo:ICON": 0.10,
    "Open-Meteo:GEM": 0.05,
}


def calculate_ensemble_forecast(
    forecasts: list[WeatherData],
    weights: dict[str, float] | None = None,
) -> tuple[float, float, list[str]]:
    """Calculate weighted ensemble forecast from multiple sources.

    Args:
        forecasts: List of WeatherData from different sources for the same city/date.
        weights: Optional custom weight dict {source: weight}. Uses defaults if None.

    Returns:
        Tuple of (ensemble_temp_f, forecast_spread_f, source_names):
        - ensemble_temp_f: weighted average temperature in Fahrenheit.
        - forecast_spread_f: max - min across all sources (spread indicator).
        - source_names: list of sources that contributed.

    Raises:
        ValueError: If forecasts list is empty or all weights are zero.
    """
    weights = weights or DEFAULT_MODEL_WEIGHTS

    if not forecasts:
        raise ValueError("No forecasts provided for ensemble calculation")

    weighted_sum = 0.0
    weight_total = 0.0
    temps: list[float] = []
    sources: list[str] = []

    for fc in forecasts:
        w = weights.get(fc.source, 0.05)  # default small weight for unknown sources
        weighted_sum += fc.forecast_high_f * w
        weight_total += w
        temps.append(fc.forecast_high_f)
        sources.append(fc.source)

    if weight_total == 0:
        raise ValueError("All weights are zero")

    ensemble_temp = weighted_sum / weight_total
    spread = max(temps) - min(temps)

    logger.info(
        "Ensemble calculated",
        extra={
            "data": {
                "ensemble_f": round(ensemble_temp, 1),
                "spread_f": round(spread, 1),
                "sources": sources,
                "individual_temps": [round(t, 1) for t in temps],
            }
        },
    )

    return ensemble_temp, spread, sources


def assess_confidence(
    forecast_spread_f: float,
    error_std_f: float,
    num_sources: int,
    data_age_minutes: float,
) -> str:
    """Assess prediction confidence level.

    Uses a scoring system that weighs model agreement most heavily,
    followed by historical accuracy, data source count, and freshness.

    Args:
        forecast_spread_f: Max minus min temperature across all sources (F).
        error_std_f: Historical forecast error standard deviation (F).
        num_sources: Number of weather forecast sources that contributed.
        data_age_minutes: Age of the oldest forecast data in minutes.

    Returns:
        One of "high", "medium", or "low" (lowercase to match schema).
    """
    score = 0

    # Model agreement (most important factor, max 3 points)
    if forecast_spread_f <= 1.0:
        score += 3  # very tight agreement
    elif forecast_spread_f <= 2.0:
        score += 2
    elif forecast_spread_f <= 3.0:
        score += 1
    # spread > 3 = no points

    # Historical accuracy (max 2 points)
    if error_std_f <= 2.0:
        score += 2  # city/season with good forecast accuracy
    elif error_std_f <= 3.0:
        score += 1

    # Data sources available (max 1 point)
    if num_sources >= 4:
        score += 1

    # Data freshness (max 1 point, min -1)
    if data_age_minutes <= 60:
        score += 1
    elif data_age_minutes > 120:
        score -= 1  # penalty for stale data

    if score >= 5:
        return "high"
    elif score >= 3:
        return "medium"
    else:
        return "low"
