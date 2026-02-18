"""Performance metrics endpoint.

Provides aggregated trading performance data including win rate,
P&L charts, per-city breakdowns, and accuracy over time.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime

from fastapi import APIRouter, Depends
from sqlalchemy import select
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


@router.get("", response_model=PerformanceData)
async def get_performance(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PerformanceData:
    """Fetch aggregated performance metrics for the analytics dashboard.

    Calculates total trades, wins, losses, win rate, total P&L,
    best/worst trades, cumulative P&L over time, P&L by city,
    and accuracy (win rate) over time.

    Args:
        user: The authenticated user.
        db: Async database session.

    Returns:
        PerformanceData with all computed metrics.
    """
    # Query all settled trades (WON or LOST)
    result = await db.execute(
        select(Trade)
        .where(
            Trade.user_id == user.id,
            Trade.status.in_([TradeStatus.WON, TradeStatus.LOST]),
        )
        .order_by(Trade.trade_date.asc())
    )
    settled_trades = result.scalars().all()

    # Handle empty case
    if not settled_trades:
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

    # Calculate basic stats
    wins = sum(1 for t in settled_trades if t.status == TradeStatus.WON)
    losses = sum(1 for t in settled_trades if t.status == TradeStatus.LOST)
    total_trades = wins + losses
    win_rate = wins / total_trades if total_trades > 0 else 0.0

    pnl_values = [t.pnl_cents or 0 for t in settled_trades]
    total_pnl_cents = sum(pnl_values)
    best_trade_pnl_cents = max(pnl_values) if pnl_values else 0
    worst_trade_pnl_cents = min(pnl_values) if pnl_values else 0

    # Cumulative P&L by date
    daily_pnl: dict[str, int] = defaultdict(int)
    for trade in settled_trades:
        trade_date = trade.trade_date
        if isinstance(trade_date, datetime):
            trade_date = trade_date.date()
        date_str = str(trade_date)
        daily_pnl[date_str] += trade.pnl_cents or 0

    cumulative = 0
    cumulative_pnl: list[CumulativePnlPoint] = []
    for date_str in sorted(daily_pnl.keys()):
        cumulative += daily_pnl[date_str]
        cumulative_pnl.append(CumulativePnlPoint(date=date_str, cumulative_pnl=cumulative))

    # P&L by city
    pnl_by_city: dict[str, int] = defaultdict(int)
    for trade in settled_trades:
        city = trade.city.value if hasattr(trade.city, "value") else trade.city
        pnl_by_city[city] += trade.pnl_cents or 0

    # Accuracy over time (daily win rate)
    daily_wins: dict[str, int] = defaultdict(int)
    daily_total: dict[str, int] = defaultdict(int)
    for trade in settled_trades:
        trade_date = trade.trade_date
        if isinstance(trade_date, datetime):
            trade_date = trade_date.date()
        date_str = str(trade_date)
        daily_total[date_str] += 1
        if trade.status == TradeStatus.WON:
            daily_wins[date_str] += 1

    accuracy_over_time: list[AccuracyPoint] = []
    for date_str in sorted(daily_total.keys()):
        day_total = daily_total[date_str]
        day_wins = daily_wins[date_str]
        accuracy = day_wins / day_total if day_total > 0 else 0.0
        accuracy_over_time.append(AccuracyPoint(date=date_str, accuracy=round(accuracy, 4)))

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
        pnl_by_city=dict(pnl_by_city),
        accuracy_over_time=accuracy_over_time,
    )
