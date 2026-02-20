"""XGBoost model training pipeline (Celery task).

Queries historical forecast-vs-settlement data from the database, engineers
features, trains an XGBoost model, validates it, and saves to disk.

Run manually:
    from backend.prediction.train_xgb import train_xgb_model
    train_xgb_model.apply()

Scheduled: Sunday 3 AM ET via Celery Beat (see celery_app.py).
"""

from __future__ import annotations

import time

import numpy as np
from asgiref.sync import async_to_sync
from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.celery_app import celery_app
from backend.common.config import get_settings
from backend.common.logging import get_logger
from backend.common.metrics import XGB_TRAINING_DURATION_SECONDS
from backend.common.models import Settlement, WeatherForecast
from backend.prediction.features import (
    KNOWN_SOURCES,
    NUM_FEATURES,
    extract_training_row,
)
from backend.prediction.xgb_model import XGBModelManager

logger = get_logger("MODEL")


async def _fetch_training_data(session: AsyncSession) -> list[dict]:
    """Fetch pivoted training data from the database.

    Returns one row per (city, forecast_date) with per-source columns.
    Each row is a dict with keys: city, forecast_date, actual_high_f,
    nws_high, ecmwf_high, gfs_high, icon_high, nws_low, humidity_pct,
    wind_speed_mph, cloud_cover_pct.
    """
    # Pivot query: one row per (city, date) with per-source forecast columns.
    stmt = (
        select(
            WeatherForecast.city,
            WeatherForecast.forecast_date,
            Settlement.actual_high_f,
            # Per-source high temperatures.
            func.max(
                case(
                    (WeatherForecast.source == "NWS", WeatherForecast.forecast_high_f),
                    else_=None,
                )
            ).label("nws_high"),
            func.max(
                case(
                    (
                        WeatherForecast.source == "Open-Meteo:ECMWF",
                        WeatherForecast.forecast_high_f,
                    ),
                    else_=None,
                )
            ).label("ecmwf_high"),
            func.max(
                case(
                    (
                        WeatherForecast.source == "Open-Meteo:GFS",
                        WeatherForecast.forecast_high_f,
                    ),
                    else_=None,
                )
            ).label("gfs_high"),
            func.max(
                case(
                    (
                        WeatherForecast.source == "Open-Meteo:ICON",
                        WeatherForecast.forecast_high_f,
                    ),
                    else_=None,
                )
            ).label("icon_high"),
            # NWS low temp.
            func.max(
                case(
                    (WeatherForecast.source == "NWS", WeatherForecast.forecast_low_f),
                    else_=None,
                )
            ).label("nws_low"),
            # NWS weather variables.
            func.max(
                case(
                    (WeatherForecast.source == "NWS", WeatherForecast.humidity_pct),
                    else_=None,
                )
            ).label("humidity_pct"),
            func.max(
                case(
                    (WeatherForecast.source == "NWS", WeatherForecast.wind_speed_mph),
                    else_=None,
                )
            ).label("wind_speed_mph"),
            func.max(
                case(
                    (WeatherForecast.source == "NWS", WeatherForecast.cloud_cover_pct),
                    else_=None,
                )
            ).label("cloud_cover_pct"),
        )
        .join(
            Settlement,
            (WeatherForecast.city == Settlement.city)
            & (WeatherForecast.forecast_date == Settlement.settlement_date),
        )
        .where(Settlement.actual_high_f.isnot(None))
        .group_by(
            WeatherForecast.city,
            WeatherForecast.forecast_date,
            Settlement.actual_high_f,
        )
        .order_by(WeatherForecast.forecast_date)
    )

    result = await session.execute(stmt)
    rows = result.all()

    return [
        {
            "city": row.city,
            "forecast_date": row.forecast_date,
            "actual_high_f": row.actual_high_f,
            "nws_high": row.nws_high,
            "ecmwf_high": row.ecmwf_high,
            "gfs_high": row.gfs_high,
            "icon_high": row.icon_high,
            "nws_low": row.nws_low,
            "humidity_pct": row.humidity_pct,
            "wind_speed_mph": row.wind_speed_mph,
            "cloud_cover_pct": row.cloud_cover_pct,
        }
        for row in rows
    ]


def _rows_to_arrays(rows: list[dict]) -> tuple[np.ndarray, np.ndarray]:
    """Convert training rows to X (features) and y (targets) arrays.

    Args:
        rows: List of dicts from _fetch_training_data().

    Returns:
        (X, y) where X has shape (n_rows, NUM_FEATURES) and y has shape (n_rows,).
    """
    x_list: list[np.ndarray] = []
    y_list: list[float] = []

    for row in rows:
        city_str = row["city"]
        # Handle both string and enum city values.
        if hasattr(city_str, "value"):
            city_str = city_str.value

        fd = row["forecast_date"]
        month = fd.month if hasattr(fd, "month") else 1
        day_of_year = fd.timetuple().tm_yday if hasattr(fd, "timetuple") else 1

        source_highs: dict[str, float] = {}
        source_lows: dict[str, float] = {}
        for src, key in zip(
            KNOWN_SOURCES, ["nws_high", "ecmwf_high", "gfs_high", "icon_high"], strict=True
        ):
            val = row.get(key)
            if val is not None:
                source_highs[src] = float(val)

        nws_low = row.get("nws_low")
        if nws_low is not None:
            source_lows["NWS"] = float(nws_low)

        nws_vars = {
            "humidity_pct": row.get("humidity_pct"),
            "wind_speed_mph": row.get("wind_speed_mph"),
            "cloud_cover_pct": row.get("cloud_cover_pct"),
        }

        features = extract_training_row(
            source_highs=source_highs,
            source_lows=source_lows,
            nws_vars=nws_vars,
            city=city_str,
            month=month,
            day_of_year=day_of_year,
        )

        x_list.append(features)
        y_list.append(float(row["actual_high_f"]))

    return np.array(x_list, dtype=np.float32), np.array(y_list, dtype=np.float32)


async def _train_async() -> dict:
    """Async training logic — fetches data and trains model.

    Returns:
        Training metrics dict, or dict with status="skipped" if insufficient data.
    """
    from backend.common.database import async_session

    settings = get_settings()

    async with async_session() as session:
        rows = await _fetch_training_data(session)

    if len(rows) < settings.xgb_min_training_samples:
        logger.info(
            "Insufficient training data for XGBoost",
            extra={
                "data": {
                    "row_count": len(rows),
                    "min_required": settings.xgb_min_training_samples,
                }
            },
        )
        return {"status": "skipped", "reason": "insufficient_data", "row_count": len(rows)}

    X, y = _rows_to_arrays(rows)

    if X.shape[1] != NUM_FEATURES:
        logger.error(
            "Feature count mismatch in training data",
            extra={"data": {"expected": NUM_FEATURES, "got": X.shape[1]}},
        )
        return {"status": "error", "reason": "feature_mismatch"}

    # Chronological split — respect time series ordering.
    split_idx = int(len(X) * 0.8)
    x_train, x_test = X[:split_idx], X[split_idx:]
    y_train, y_test = y[:split_idx], y[split_idx:]

    manager = XGBModelManager(model_dir=settings.xgb_model_dir)

    metrics = manager.train(x_train, y_train, x_test, y_test)

    if metrics.get("accepted"):
        manager.save()

        importance = manager.get_feature_importance()
        if importance:
            logger.info(
                "XGBoost feature importance",
                extra={"data": importance},
            )

    return metrics


@celery_app.task(
    bind=True,
    name="backend.prediction.train_xgb.train_xgb_model",
    soft_time_limit=300,
    time_limit=360,
)
def train_xgb_model(self) -> dict:  # noqa: ANN001
    """Celery task: Train XGBoost model on historical forecast vs. settlement data.

    Scheduled weekly via Celery Beat. Can also be run manually:
        train_xgb_model.apply()
    """
    start = time.monotonic()

    try:
        result = async_to_sync(_train_async)()

        duration = time.monotonic() - start
        XGB_TRAINING_DURATION_SECONDS.observe(duration)

        logger.info(
            "XGBoost training task completed",
            extra={"data": {"duration_s": round(duration, 1), "result": result}},
        )

        return result

    except Exception as e:
        duration = time.monotonic() - start
        XGB_TRAINING_DURATION_SECONDS.observe(duration)

        logger.error(
            "XGBoost training task failed",
            extra={"data": {"error": str(e), "duration_s": round(duration, 1)}},
        )
        raise
