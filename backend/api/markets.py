"""Markets endpoint -- latest bracket predictions per city.

Returns the most recent BracketPrediction for each city,
optionally filtered to a single city.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps import get_current_user, prediction_to_schema
from backend.common.database import get_db
from backend.common.logging import get_logger
from backend.common.models import Prediction, User
from backend.common.schemas import BracketPrediction, CityCode

logger = get_logger("API")

router = APIRouter()


@router.get("", response_model=list[BracketPrediction])
async def get_markets(
    city: CityCode | None = None,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[BracketPrediction]:
    """Fetch the latest bracket predictions, optionally filtered by city.

    Returns the most recent Prediction per city. If a city filter is
    provided, only that city's prediction is returned.

    Args:
        city: Optional city code to filter by (NYC, CHI, MIA, AUS).
        user: The authenticated user.
        db: Async database session.

    Returns:
        List of BracketPrediction schemas, one per city.
    """
    if city is not None:
        # Fetch latest prediction for the specified city
        result = await db.execute(
            select(Prediction)
            .where(Prediction.city == city)
            .order_by(Prediction.generated_at.desc())
            .limit(1)
        )
        pred = result.scalar_one_or_none()
        if pred is None:
            return []
        return [prediction_to_schema(pred)]

    # Fetch latest prediction per city from active cities
    active_cities_str = user.active_cities or "NYC,CHI,MIA,AUS"
    active_cities = [c.strip() for c in active_cities_str.split(",") if c.strip()]

    predictions = []
    for c in active_cities:
        result = await db.execute(
            select(Prediction)
            .where(Prediction.city == c)
            .order_by(Prediction.generated_at.desc())
            .limit(1)
        )
        pred = result.scalar_one_or_none()
        if pred is not None:
            predictions.append(prediction_to_schema(pred))

    logger.info(
        "Markets data fetched",
        extra={
            "data": {
                "city_filter": city,
                "predictions_returned": len(predictions),
            }
        },
    )

    return predictions
