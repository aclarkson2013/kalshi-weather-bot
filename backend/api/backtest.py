"""Backtest API endpoint — run historical simulations.

POST /api/backtest — accepts BacktestConfig, returns BacktestResult.
Uses stored predictions from the database or generates synthetic data.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps import get_current_user, prediction_to_schema
from backend.backtesting.engine import run_backtest
from backend.backtesting.exceptions import BacktestError, InsufficientDataError
from backend.backtesting.metrics import compute_metrics
from backend.backtesting.schemas import BacktestConfig, BacktestResult
from backend.common.database import get_db
from backend.common.logging import get_logger
from backend.common.models import Prediction, Settlement

router = APIRouter()
logger = get_logger("API")


@router.post("", response_model=BacktestResult)
async def run_backtest_endpoint(
    config: BacktestConfig,
    db: AsyncSession = Depends(get_db),
    _user=Depends(get_current_user),
) -> BacktestResult:
    """Run a backtest simulation with the given configuration.

    Loads historical predictions and settlements from the database.
    If insufficient data exists, generates synthetic data for the
    requested date range.

    Args:
        config: Backtest configuration.
        db: Database session.
        _user: Authenticated user (required but not used).

    Returns:
        BacktestResult with full simulation metrics.
    """
    # Load predictions from DB
    pred_query = select(Prediction).where(
        Prediction.prediction_date >= config.start_date,
        Prediction.prediction_date <= config.end_date,
    )
    pred_result = await db.execute(pred_query)
    db_predictions = list(pred_result.scalars().all())

    # Convert ORM → Pydantic
    predictions = [prediction_to_schema(p) for p in db_predictions]

    # Load settlement temps
    settle_query = select(Settlement).where(
        Settlement.settlement_date >= config.start_date,
        Settlement.settlement_date <= config.end_date,
    )
    settle_result = await db.execute(settle_query)
    db_settlements = list(settle_result.scalars().all())

    settlements = None
    if db_settlements:
        settlements = {}
        for s in db_settlements:
            city = s.city.value if hasattr(s.city, "value") else s.city
            settlements[(city, s.settlement_date)] = s.actual_high_f

    try:
        result = run_backtest(config, predictions, settlements)
        result = compute_metrics(result)
    except InsufficientDataError as exc:
        raise HTTPException(
            status_code=422,
            detail=f"Insufficient data for backtest: {exc}",
        ) from exc
    except BacktestError as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Backtest error: {exc}",
        ) from exc

    logger.info(
        "Backtest completed",
        extra={
            "data": {
                "total_trades": result.total_trades,
                "win_rate": result.win_rate,
                "roi_pct": result.roi_pct,
                "duration_seconds": result.duration_seconds,
            }
        },
    )

    return result
