"""Forecast accuracy endpoints.

Provides per-source forecast accuracy metrics, calibration reports,
and error trend data for the analytics dashboard.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps import get_current_user
from backend.api.response_schemas import (
    CalibrationReport,
    ForecastErrorTrend,
    SourceAccuracy,
)
from backend.common.database import get_db
from backend.common.logging import get_logger
from backend.common.models import User
from backend.prediction.accuracy import get_forecast_error_trend, get_source_accuracy
from backend.prediction.calibration import check_calibration

logger = get_logger("API")

router = APIRouter()


@router.get("/sources", response_model=list[SourceAccuracy])
async def get_accuracy_sources(
    city: str = Query(default="NYC", description="City code"),
    lookback_days: int = Query(default=90, ge=1, le=365, description="Lookback period in days"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[SourceAccuracy]:
    """Get per-source forecast accuracy metrics (MAE, RMSE, bias).

    Compares each weather source's forecast_high_f against actual settlement
    temperatures over the lookback period.

    Args:
        city: City code ("NYC", "CHI", "MIA", "AUS").
        lookback_days: Number of days to look back.
        user: Authenticated user.
        db: Async database session.

    Returns:
        List of SourceAccuracy, one per weather source with data.
    """
    return await get_source_accuracy(city, db, lookback_days=lookback_days)


@router.get("/calibration", response_model=CalibrationReport)
async def get_calibration(
    city: str = Query(default="NYC", description="City code"),
    lookback_days: int = Query(default=90, ge=1, le=365, description="Lookback period in days"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CalibrationReport:
    """Get calibration report with Brier score and calibration buckets.

    Checks how well-calibrated bracket probability predictions have been
    by comparing predicted probabilities to actual outcomes.

    Args:
        city: City code ("NYC", "CHI", "MIA", "AUS").
        lookback_days: Number of days to look back.
        user: Authenticated user.
        db: Async database session.

    Returns:
        CalibrationReport with Brier score and calibration bucket data.
    """
    return await check_calibration(city, db, lookback_days=lookback_days)


@router.get("/trends", response_model=ForecastErrorTrend)
async def get_accuracy_trends(
    city: str = Query(default="NYC", description="City code"),
    source: str = Query(default="NWS", description="Weather source name"),
    lookback_days: int = Query(default=90, ge=1, le=365, description="Lookback period in days"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ForecastErrorTrend:
    """Get forecast error trend data for charting.

    Returns individual (date, error) points and a 7-day rolling MAE
    for a specific city and weather source.

    Args:
        city: City code ("NYC", "CHI", "MIA", "AUS").
        source: Weather source name (e.g., "NWS", "Open-Meteo:GFS").
        lookback_days: Number of days to look back.
        user: Authenticated user.
        db: Async database session.

    Returns:
        ForecastErrorTrend with data points and rolling MAE.
    """
    return await get_forecast_error_trend(city, source, db, lookback_days=lookback_days)
