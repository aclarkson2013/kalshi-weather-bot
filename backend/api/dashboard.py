"""Dashboard endpoint -- aggregates data from multiple sources.

Provides a single endpoint that combines balance, P&L, positions,
recent trades, predictions, and next market launch time.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps import (
    get_current_user,
    get_kalshi_client,
    prediction_to_schema,
    trade_to_record,
)
from backend.api.response_schemas import DashboardData
from backend.common.database import get_db
from backend.common.logging import get_logger
from backend.common.models import Prediction, Trade, TradeStatus, User
from backend.kalshi.client import KalshiClient

logger = get_logger("API")

ET = ZoneInfo("America/New_York")

router = APIRouter()


@router.get("", response_model=DashboardData)
async def get_dashboard(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    kalshi: KalshiClient = Depends(get_kalshi_client),
) -> DashboardData:
    """Fetch aggregated dashboard data for the frontend.

    Combines balance from Kalshi API, today's P&L from settled trades,
    active positions, recent trades, latest predictions per city, and
    the next market launch time.

    Args:
        user: The authenticated user.
        db: Async database session.
        kalshi: Authenticated Kalshi client.

    Returns:
        DashboardData with all aggregated fields.
    """
    # 1. Get balance from Kalshi (returns dollars, convert to cents)
    balance_dollars = await kalshi.get_balance()
    balance_cents = int(balance_dollars * 100)

    # 2. Calculate today's P&L in cents (ET timezone)
    today_et = datetime.now(ET).date()
    pnl_result = await db.execute(
        select(func.coalesce(func.sum(Trade.pnl_cents), 0)).where(
            Trade.user_id == user.id,
            Trade.settled_at.isnot(None),
            func.date(Trade.trade_date) == today_et,
        )
    )
    today_pnl_cents = int(pnl_result.scalar())

    # 3. Active (open) positions
    open_result = await db.execute(
        select(Trade).where(
            Trade.user_id == user.id,
            Trade.status == TradeStatus.OPEN,
        )
    )
    active_positions = [trade_to_record(t) for t in open_result.scalars().all()]

    # 4. Recent settled trades (last 10)
    recent_result = await db.execute(
        select(Trade)
        .where(
            Trade.user_id == user.id,
            Trade.settled_at.isnot(None),
        )
        .order_by(Trade.settled_at.desc())
        .limit(10)
    )
    recent_trades = [trade_to_record(t) for t in recent_result.scalars().all()]

    # 5. Latest predictions per active city
    active_cities_str = user.active_cities or "NYC,CHI,MIA,AUS"
    active_cities = [c.strip() for c in active_cities_str.split(",") if c.strip()]

    predictions = []
    for city in active_cities:
        pred_result = await db.execute(
            select(Prediction)
            .where(Prediction.city == city)
            .order_by(Prediction.generated_at.desc())
            .limit(1)
        )
        pred = pred_result.scalar_one_or_none()
        if pred is not None:
            predictions.append(prediction_to_schema(pred))

    # 6. Calculate next market launch time (10:00 AM ET)
    now_et = datetime.now(ET)
    today_launch = now_et.replace(hour=10, minute=0, second=0, microsecond=0)
    next_launch = today_launch if now_et < today_launch else today_launch + timedelta(days=1)
    next_market_launch = next_launch.isoformat()

    logger.info(
        "Dashboard data assembled",
        extra={
            "data": {
                "user_id": user.id,
                "balance_cents": balance_cents,
                "today_pnl_cents": today_pnl_cents,
                "active_positions": len(active_positions),
                "predictions": len(predictions),
            }
        },
    )

    return DashboardData(
        balance_cents=balance_cents,
        today_pnl_cents=today_pnl_cents,
        active_positions=active_positions,
        recent_trades=recent_trades,
        next_market_launch=next_market_launch,
        predictions=predictions,
    )
