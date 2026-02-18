"""Trade queue endpoints for manual mode approval and rejection.

In manual trading mode, trade signals are queued as PendingTradeModel
records. Users approve or reject them from the PWA dashboard.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps import (
    get_current_user,
    get_kalshi_client,
    pending_to_schema,
)
from backend.common.database import get_db
from backend.common.logging import get_logger
from backend.common.models import PendingTradeModel, PendingTradeStatus, User
from backend.common.schemas import PendingTrade, TradeRecord, TradeSignal
from backend.kalshi.client import KalshiClient
from backend.trading.executor import execute_trade
from backend.trading.trade_queue import approve_trade, reject_trade

logger = get_logger("API")

router = APIRouter()


@router.get("", response_model=list[PendingTrade])
async def get_pending_trades(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[PendingTrade]:
    """Fetch all pending trades awaiting user approval.

    Args:
        user: The authenticated user.
        db: Async database session.

    Returns:
        List of PendingTrade schemas with status PENDING.
    """
    result = await db.execute(
        select(PendingTradeModel)
        .where(
            PendingTradeModel.user_id == user.id,
            PendingTradeModel.status == PendingTradeStatus.PENDING,
        )
        .order_by(PendingTradeModel.created_at.desc())
    )
    pending = result.scalars().all()

    logger.info(
        "Pending trades fetched",
        extra={"data": {"count": len(pending), "user_id": user.id}},
    )

    return [pending_to_schema(p) for p in pending]


@router.post("/{trade_id}/approve", response_model=TradeRecord)
async def approve_pending_trade(
    trade_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    kalshi: KalshiClient = Depends(get_kalshi_client),
) -> TradeRecord:
    """Approve a pending trade and execute it on Kalshi.

    Validates the trade exists and is PENDING, marks it APPROVED,
    then builds a TradeSignal and executes it via the trading executor.

    Args:
        trade_id: The pending trade ID to approve.
        user: The authenticated user.
        db: Async database session.
        kalshi: Authenticated Kalshi client.

    Returns:
        The executed TradeRecord.

    Raises:
        HTTPException: 404 if trade not found or not in PENDING state.
    """
    try:
        pending_model = await approve_trade(trade_id, db)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    # Build a TradeSignal from the approved pending trade
    city = pending_model.city.value if hasattr(pending_model.city, "value") else pending_model.city
    signal = TradeSignal(
        city=city,
        bracket=pending_model.bracket_label,
        side=pending_model.side,
        price_cents=pending_model.price_cents,
        quantity=pending_model.quantity,
        model_probability=pending_model.model_probability,
        market_probability=pending_model.market_probability,
        ev=pending_model.ev,
        confidence=pending_model.confidence,
        market_ticker=pending_model.market_ticker,
        reasoning=pending_model.reasoning or "",
    )

    # Execute the trade on Kalshi
    trade_record = await execute_trade(
        signal=signal,
        kalshi_client=kalshi,
        db=db,
        user_id=user.id,
    )

    # Mark the pending trade as EXECUTED
    pending_model.status = PendingTradeStatus.EXECUTED
    await db.commit()

    logger.info(
        "Pending trade approved and executed",
        extra={
            "data": {
                "trade_id": trade_id,
                "executed_trade_id": trade_record.id,
            }
        },
    )

    return trade_record


@router.post("/{trade_id}/reject", status_code=204)
async def reject_pending_trade(
    trade_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Reject a pending trade.

    Marks the trade as REJECTED so it will not be executed.

    Args:
        trade_id: The pending trade ID to reject.
        user: The authenticated user.
        db: Async database session.

    Raises:
        HTTPException: 404 if trade not found or not in PENDING state.
    """
    try:
        await reject_trade(trade_id, db)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    await db.commit()

    logger.info(
        "Pending trade rejected",
        extra={"data": {"trade_id": trade_id}},
    )
