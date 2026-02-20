"""Performance metrics endpoint.

Provides aggregated trading performance data including win rate,
P&L charts, per-city breakdowns, and accuracy over time.

All aggregation is pushed to SQL for efficiency — no full trade
loading into Python memory.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps import get_current_user
from backend.api.response_schemas import (
    AccuracyPoint,
    CumulativePnlPoint,
    PerformanceData,
)
from backend.common.database import get_db
from backend.common.logging import get_logger
from backend.common.models import Trade, TradeStatus, User

logger = get_logger("API")

router = APIRouter()

# Reusable filter for settled trades
_SETTLED_STATUSES = [TradeStatus.WON, TradeStatus.LOST]


@router.get("", response_model=PerformanceData)
async def get_performance(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PerformanceData:
    """Fetch aggregated performance metrics for the analytics dashboard.

    Uses three focused SQL queries with aggregation instead of loading
    all trades into memory:
    1. Summary stats (count, wins, losses, total/best/worst PnL)
    2. Daily aggregation (cumulative PnL + accuracy over time)
    3. PnL by city

    Args:
        user: The authenticated user.
        db: Async database session.

    Returns:
        PerformanceData with all computed metrics.
    """
    # ── Query 1: Summary stats ──
    summary_result = await db.execute(
        select(
            func.count().label("total"),
            func.sum(case((Trade.status == TradeStatus.WON, 1), else_=0)).label("wins"),
            func.sum(case((Trade.status == TradeStatus.LOST, 1), else_=0)).label("losses"),
            func.coalesce(func.sum(Trade.pnl_cents), 0).label("total_pnl"),
            func.coalesce(func.max(Trade.pnl_cents), 0).label("best_pnl"),
            func.coalesce(func.min(Trade.pnl_cents), 0).label("worst_pnl"),
        ).where(
            Trade.user_id == user.id,
            Trade.status.in_(_SETTLED_STATUSES),
        )
    )
    row = summary_result.one()
    total_trades = row.total
    wins = row.wins
    losses = row.losses
    total_pnl_cents = row.total_pnl
    best_trade_pnl_cents = row.best_pnl
    worst_trade_pnl_cents = row.worst_pnl
    win_rate = wins / total_trades if total_trades > 0 else 0.0

    # Handle empty case
    if total_trades == 0:
        logger.info(
            "Performance data requested with no settled trades",
            extra={"data": {"user_id": user.id}},
        )
        return PerformanceData(
            total_trades=0,
            wins=0,
            losses=0,
            win_rate=0.0,
            total_pnl_cents=0,
            best_trade_pnl_cents=0,
            worst_trade_pnl_cents=0,
            cumulative_pnl=[],
            pnl_by_city={},
            accuracy_over_time=[],
        )

    # ── Query 2: Daily aggregation (cumulative PnL + accuracy) ──
    daily_result = await db.execute(
        select(
            func.date(Trade.trade_date).label("tdate"),
            func.coalesce(func.sum(Trade.pnl_cents), 0).label("day_pnl"),
            func.count().label("day_total"),
            func.sum(case((Trade.status == TradeStatus.WON, 1), else_=0)).label("day_wins"),
        )
        .where(
            Trade.user_id == user.id,
            Trade.status.in_(_SETTLED_STATUSES),
        )
        .group_by(func.date(Trade.trade_date))
        .order_by(func.date(Trade.trade_date).asc())
    )
    daily_rows = daily_result.all()

    cumulative = 0
    cumulative_pnl: list[CumulativePnlPoint] = []
    accuracy_over_time: list[AccuracyPoint] = []
    for drow in daily_rows:
        cumulative += drow.day_pnl
        date_str = str(drow.tdate)
        cumulative_pnl.append(CumulativePnlPoint(date=date_str, cumulative_pnl=cumulative))
        acc = drow.day_wins / drow.day_total if drow.day_total > 0 else 0.0
        accuracy_over_time.append(AccuracyPoint(date=date_str, accuracy=round(acc, 4)))

    # ── Query 3: PnL by city ──
    city_result = await db.execute(
        select(
            Trade.city,
            func.coalesce(func.sum(Trade.pnl_cents), 0).label("city_pnl"),
        )
        .where(
            Trade.user_id == user.id,
            Trade.status.in_(_SETTLED_STATUSES),
        )
        .group_by(Trade.city)
    )
    pnl_by_city: dict[str, int] = {}
    for crow in city_result.all():
        city_val = crow.city.value if hasattr(crow.city, "value") else crow.city
        pnl_by_city[city_val] = crow.city_pnl

    logger.info(
        "Performance data computed",
        extra={
            "data": {
                "user_id": user.id,
                "total_trades": total_trades,
                "win_rate": round(win_rate, 4),
                "total_pnl_cents": total_pnl_cents,
            }
        },
    )

    return PerformanceData(
        total_trades=total_trades,
        wins=wins,
        losses=losses,
        win_rate=round(win_rate, 4),
        total_pnl_cents=total_pnl_cents,
        best_trade_pnl_cents=best_trade_pnl_cents,
        worst_trade_pnl_cents=worst_trade_pnl_cents,
        cumulative_pnl=cumulative_pnl,
        pnl_by_city=pnl_by_city,
        accuracy_over_time=accuracy_over_time,
    )
