"""Per-source forecast accuracy analysis.

Compares weather forecast sources (NWS, Open-Meteo:GFS, etc.) against actual
NWS CLI settlement data. Computes MAE, RMSE, and bias per source. Also provides
forecast error trend data for charting.

Usage:
    from backend.prediction.accuracy import get_source_accuracy, get_forecast_error_trend

    sources = await get_source_accuracy("NYC", db_session=db)
    trend = await get_forecast_error_trend("NYC", "NWS", db_session=db)
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.response_schemas import (
    ForecastErrorPoint,
    ForecastErrorTrend,
    SourceAccuracy,
)
from backend.common.logging import get_logger
from backend.common.models import Settlement, WeatherForecast

logger = get_logger("MODEL")


async def get_source_accuracy(
    city: str,
    db_session: AsyncSession,
    lookback_days: int = 90,
) -> list[SourceAccuracy]:
    """Compute per-source forecast accuracy metrics for a city.

    Joins WeatherForecast with Settlement on (city, forecast_date == settlement_date)
    and aggregates MAE, RMSE, and bias per weather source.

    Args:
        city: City code ("NYC", "CHI", "MIA", "AUS").
        db_session: SQLAlchemy async session.
        lookback_days: Number of days to look back.

    Returns:
        List of SourceAccuracy, one per weather source with data.
    """
    cutoff = datetime.utcnow() - timedelta(days=lookback_days)

    # SQL aggregation: MAE, RMSE components, bias per source
    error_expr = Settlement.actual_high_f - WeatherForecast.forecast_high_f
    stmt = (
        select(
            WeatherForecast.source,
            func.count().label("cnt"),
            func.avg(func.abs(error_expr)).label("mae"),
            func.avg(error_expr * error_expr).label("mse"),
            func.avg(error_expr).label("bias"),
        )
        .join(
            Settlement,
            (WeatherForecast.city == Settlement.city)
            & (WeatherForecast.forecast_date == Settlement.settlement_date),
        )
        .where(
            WeatherForecast.city == city,
            Settlement.actual_high_f.isnot(None),
            WeatherForecast.forecast_date >= cutoff,
        )
        .group_by(WeatherForecast.source)
        .order_by(WeatherForecast.source)
    )

    result = await db_session.execute(stmt)
    rows = result.all()

    sources: list[SourceAccuracy] = []
    for row in rows:
        rmse = math.sqrt(row.mse) if row.mse is not None else 0.0
        sources.append(
            SourceAccuracy(
                source=row.source,
                sample_count=row.cnt,
                mae_f=round(row.mae, 2),
                rmse_f=round(rmse, 2),
                bias_f=round(row.bias, 2),
            )
        )

    logger.info(
        "Source accuracy computed",
        extra={
            "data": {
                "city": city,
                "lookback_days": lookback_days,
                "sources_count": len(sources),
            }
        },
    )

    return sources


async def get_forecast_error_trend(
    city: str,
    source: str,
    db_session: AsyncSession,
    lookback_days: int = 90,
) -> ForecastErrorTrend:
    """Get forecast error trend data for charting.

    Returns individual (date, error) points and a 7-day rolling MAE.

    Args:
        city: City code ("NYC", "CHI", "MIA", "AUS").
        source: Weather source name (e.g., "NWS", "Open-Meteo:GFS").
        db_session: SQLAlchemy async session.
        lookback_days: Number of days to look back.

    Returns:
        ForecastErrorTrend with points and rolling MAE.
    """
    cutoff = datetime.utcnow() - timedelta(days=lookback_days)

    error_expr = Settlement.actual_high_f - WeatherForecast.forecast_high_f
    stmt = (
        select(
            func.date(WeatherForecast.forecast_date).label("fdate"),
            error_expr.label("error"),
        )
        .join(
            Settlement,
            (WeatherForecast.city == Settlement.city)
            & (WeatherForecast.forecast_date == Settlement.settlement_date),
        )
        .where(
            WeatherForecast.city == city,
            WeatherForecast.source == source,
            Settlement.actual_high_f.isnot(None),
            WeatherForecast.forecast_date >= cutoff,
        )
        .order_by(func.date(WeatherForecast.forecast_date).asc())
    )

    result = await db_session.execute(stmt)
    rows = result.all()

    points: list[ForecastErrorPoint] = []
    abs_errors: list[float] = []
    for row in rows:
        points.append(ForecastErrorPoint(date=str(row.fdate), error_f=round(row.error, 2)))
        abs_errors.append(abs(row.error))

    # 7-day rolling MAE: average of last 7 absolute errors (or all if fewer)
    rolling_mae: float | None = None
    if abs_errors:
        window = abs_errors[-7:]
        rolling_mae = round(sum(window) / len(window), 2)

    logger.info(
        "Forecast error trend computed",
        extra={
            "data": {
                "city": city,
                "source": source,
                "points_count": len(points),
                "rolling_mae": rolling_mae,
            }
        },
    )

    return ForecastErrorTrend(
        city=city,
        source=source,
        points=points,
        rolling_mae=rolling_mae,
    )
