"""Feature engineering for XGBoost temperature prediction model.

Pure module — no I/O, no database access. Extracts feature vectors from
weather forecast data for both prediction and training.

XGBoost handles NaN natively, so missing sources become NaN in the feature
vector rather than requiring imputation.

Usage:
    from backend.prediction.features import extract_features, FEATURE_NAMES

    features = extract_features(forecasts, city="NYC", target_date=date(2026, 2, 19))
"""

from __future__ import annotations

import math
from datetime import date

import numpy as np

from backend.common.schemas import WeatherData

# Sources in a fixed order for consistent feature columns.
KNOWN_SOURCES: list[str] = [
    "NWS",
    "Open-Meteo:ECMWF",
    "Open-Meteo:GFS",
    "Open-Meteo:ICON",
]

# City codes in a fixed order for one-hot encoding.
CITY_CODES: list[str] = ["NYC", "CHI", "MIA", "AUS"]

# Feature names matching the output order of extract_features / extract_training_row.
FEATURE_NAMES: list[str] = [
    # Per-source high temps (4)
    "nws_high_f",
    "ecmwf_high_f",
    "gfs_high_f",
    "icon_high_f",
    # Per-source low temps (4)
    "nws_low_f",
    "ecmwf_low_f",
    "gfs_low_f",
    "icon_low_f",
    # NWS weather variables (3)
    "humidity_pct",
    "wind_speed_mph",
    "cloud_cover_pct",
    # Ensemble stats (2)
    "spread_f",
    "source_count",
    # Temporal (4)
    "month",
    "day_of_year",
    "sin_month",
    "cos_month",
    # City one-hot (4)
    "city_nyc",
    "city_chi",
    "city_mia",
    "city_aus",
]

NUM_FEATURES: int = len(FEATURE_NAMES)


def extract_features(
    forecasts: list[WeatherData],
    city: str,
    target_date: date,
) -> np.ndarray:
    """Extract feature vector from weather forecasts for XGBoost prediction.

    Args:
        forecasts: Weather forecasts from multiple sources for one city/date.
        city: City code ("NYC", "CHI", "MIA", "AUS").
        target_date: The date being predicted.

    Returns:
        1-D numpy array of shape (NUM_FEATURES,) with NaN for missing data.
    """
    # Index forecasts by source for O(1) lookup.
    by_source: dict[str, WeatherData] = {fc.source: fc for fc in forecasts}

    # Per-source high temperatures.
    source_highs: dict[str, float] = {}
    source_lows: dict[str, float] = {}
    for src in KNOWN_SOURCES:
        fc = by_source.get(src)
        if fc is not None:
            source_highs[src] = fc.forecast_high_f
            if fc.variables and fc.variables.temp_low_f is not None:
                source_lows[src] = fc.variables.temp_low_f
        # Missing sources → NaN (handled by XGBoost natively)

    # NWS weather variables.
    nws_fc = by_source.get("NWS")
    nws_vars: dict[str, float | None] = {}
    if nws_fc and nws_fc.variables:
        nws_vars = {
            "humidity_pct": nws_fc.variables.humidity_pct,
            "wind_speed_mph": nws_fc.variables.wind_speed_mph,
            "cloud_cover_pct": nws_fc.variables.cloud_cover_pct,
        }

    return extract_training_row(
        source_highs=source_highs,
        source_lows=source_lows,
        nws_vars=nws_vars,
        city=city,
        month=target_date.month,
        day_of_year=target_date.timetuple().tm_yday,
    )


def extract_training_row(
    source_highs: dict[str, float],
    source_lows: dict[str, float],
    nws_vars: dict[str, float | None],
    city: str,
    month: int,
    day_of_year: int,
) -> np.ndarray:
    """Extract feature vector from pre-processed data (DB query or live forecasts).

    Args:
        source_highs: {source_name: forecast_high_f} for available sources.
        source_lows: {source_name: forecast_low_f} for available sources.
        nws_vars: {"humidity_pct": float|None, "wind_speed_mph": ..., "cloud_cover_pct": ...}
        city: City code.
        month: Month number (1-12).
        day_of_year: Day of year (1-366).

    Returns:
        1-D numpy array of shape (NUM_FEATURES,).
    """
    features: list[float] = []

    # Per-source highs (4 features).
    for src in KNOWN_SOURCES:
        features.append(source_highs.get(src, float("nan")))

    # Per-source lows (4 features).
    for src in KNOWN_SOURCES:
        features.append(source_lows.get(src, float("nan")))

    # NWS weather variables (3 features).
    for key in ("humidity_pct", "wind_speed_mph", "cloud_cover_pct"):
        val = nws_vars.get(key)
        features.append(val if val is not None else float("nan"))

    # Ensemble stats (2 features).
    highs = list(source_highs.values())
    if len(highs) >= 2:
        spread = max(highs) - min(highs)
    elif len(highs) == 1:
        spread = 0.0
    else:
        spread = float("nan")
    features.append(spread)
    features.append(float(len(highs)))

    # Temporal features (4 features).
    features.append(float(month))
    features.append(float(day_of_year))
    # Cyclical encoding: month → sin/cos (period = 12 months)
    features.append(math.sin(2 * math.pi * month / 12))
    features.append(math.cos(2 * math.pi * month / 12))

    # City one-hot encoding (4 features).
    for code in CITY_CODES:
        features.append(1.0 if city == code else 0.0)

    return np.array(features, dtype=np.float32)
