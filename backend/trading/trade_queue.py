"""Trade approval queue for manual trading mode.

When the user's trading_mode is "manual", trade signals are not executed
immediately. Instead, they are queued as PendingTradeModel records in the
database. The user can then approve, reject, or let them expire from the
PWA dashboard.

State machine:
    PENDING -> APPROVED  (user taps approve)
    PENDING -> REJECTED  (user taps reject)
    PENDING -> EXPIRED   (TTL exceeded, auto-expired)
    APPROVED -> trade is executed via executor.py

The default TTL for pending trades is 30 minutes.

Usage:
    from backend.trading.trade_queue import queue_trade, approve_trade

    pending = await queue_trade(signal, db, user_id, market_ticker)
    approved = await approve_trade(pending.id, db)
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.common.logging import get_logger
from backend.common.models import PendingTradeModel, PendingTradeStatus
from backend.common.schemas import PendingTrade, TradeSignal

logger = get_logger("TRADING")

PENDING_TRADE_TTL_MINUTES = 30


async def queue_trade(
    signal: TradeSignal,
    db: AsyncSession,
    user_id: str,
    market_ticker: str,
    notification_service: object | None = None,
) -> PendingTrade:
    """Queue a trade for manual user approval.

    Creates a PendingTradeModel in the database and optionally sends a
    push notification. The trade will auto-expire after PENDING_TRADE_TTL_MINUTES.

    Args:
        signal: The trade signal to queue.
        db: Async database session.
        user_id: The user ID who owns this pending trade.
        market_ticker: The Kalshi market ticker string.
        notification_service: Optional NotificationService for push notifications.

    Returns:
        A PendingTrade schema object representing the queued trade.
    """
    now = datetime.now(UTC)
    trade_id = str(uuid4())
    expires_at = now + timedelta(minutes=PENDING_TRADE_TTL_MINUTES)

    # Create the ORM record
    pending_model = PendingTradeModel(
        id=trade_id,
        user_id=user_id,
        city=signal.city,
        bracket_label=signal.bracket,
        market_ticker=market_ticker,
        side=signal.side,
        price_cents=signal.price_cents,
        quantity=signal.quantity,
        model_probability=signal.model_probability,
        market_probability=signal.market_probability,
        ev=signal.ev,
        confidence=signal.confidence,
        reasoning=signal.reasoning,
        status=PendingTradeStatus.PENDING,
        created_at=now,
        expires_at=expires_at,
    )
    db.add(pending_model)
    await db.flush()

    # Send push notification if available
    if notification_service is not None:
        try:
            await notification_service.send(
                title=f"+EV Trade: {signal.city} {signal.bracket}",
                body=(
                    f"EV: +${signal.ev:.2f} | {signal.confidence} confidence | "
                    f"{signal.side.upper()} @ {signal.price_cents}c"
                ),
                data={"trade_id": trade_id},
            )
        except Exception as exc:
            logger.error(
                "Failed to send trade notification",
                extra={"data": {"trade_id": trade_id, "error": str(exc)}},
            )

    logger.info(
        "Trade queued for approval",
        extra={
            "data": {
                "trade_id": trade_id,
                "city": signal.city,
                "bracket": signal.bracket,
                "side": signal.side,
                "price_cents": signal.price_cents,
                "ev": signal.ev,
                "expires_at": str(expires_at),
            }
        },
    )

    # Return the Pydantic schema
    return PendingTrade(
        id=trade_id,
        city=signal.city,
        bracket=signal.bracket,
        side=signal.side,
        price_cents=signal.price_cents,
        quantity=signal.quantity,
        model_probability=signal.model_probability,
        market_probability=signal.market_probability,
        ev=signal.ev,
        confidence=signal.confidence,
        reasoning=signal.reasoning,
        status="PENDING",
        created_at=now,
        expires_at=expires_at,
        acted_at=None,
    )


async def approve_trade(
    trade_id: str,
    db: AsyncSession,
) -> PendingTradeModel:
    """Approve a pending trade for execution.

    Validates that the trade exists, is still PENDING, and has not expired.
    Sets the status to APPROVED and records the action timestamp.

    The caller is responsible for actually executing the trade via executor.py.

    Args:
        trade_id: The pending trade ID to approve.
        db: Async database session.

    Returns:
        The updated PendingTradeModel.

    Raises:
        ValueError: If the trade is not found, not PENDING, or expired.
    """
    result = await db.execute(select(PendingTradeModel).where(PendingTradeModel.id == trade_id))
    trade = result.scalar_one_or_none()

    if trade is None:
        msg = f"Trade {trade_id} not found"
        raise ValueError(msg)

    if trade.status != PendingTradeStatus.PENDING:
        msg = f"Trade {trade_id} is {trade.status.value}, not PENDING"
        raise ValueError(msg)

    # Check expiration
    now = datetime.now(UTC)
    if now > trade.expires_at:
        trade.status = PendingTradeStatus.EXPIRED
        trade.acted_at = now
        await db.flush()
        msg = f"Trade {trade_id} has expired"
        raise ValueError(msg)

    trade.status = PendingTradeStatus.APPROVED
    trade.acted_at = now
    await db.flush()

    logger.info(
        "Trade approved",
        extra={"data": {"trade_id": trade_id}},
    )
    return trade


async def reject_trade(
    trade_id: str,
    db: AsyncSession,
) -> PendingTradeModel:
    """Reject a pending trade.

    Sets the status to REJECTED and records the action timestamp.

    Args:
        trade_id: The pending trade ID to reject.
        db: Async database session.

    Returns:
        The updated PendingTradeModel.

    Raises:
        ValueError: If the trade is not found or not PENDING.
    """
    result = await db.execute(select(PendingTradeModel).where(PendingTradeModel.id == trade_id))
    trade = result.scalar_one_or_none()

    if trade is None:
        msg = f"Trade {trade_id} not found"
        raise ValueError(msg)

    if trade.status != PendingTradeStatus.PENDING:
        msg = f"Trade {trade_id} is {trade.status.value}, not PENDING"
        raise ValueError(msg)

    trade.status = PendingTradeStatus.REJECTED
    trade.acted_at = datetime.now(UTC)
    await db.flush()

    logger.info(
        "Trade rejected",
        extra={"data": {"trade_id": trade_id}},
    )
    return trade


async def expire_stale_trades(db: AsyncSession) -> int:
    """Expire all pending trades past their TTL.

    Finds all PendingTradeModel records with status PENDING and
    expires_at in the past, and updates them to EXPIRED.

    Args:
        db: Async database session.

    Returns:
        Number of trades expired.
    """
    now = datetime.now(UTC)

    result = await db.execute(
        update(PendingTradeModel)
        .where(
            PendingTradeModel.status == PendingTradeStatus.PENDING,
            PendingTradeModel.expires_at < now,
        )
        .values(
            status=PendingTradeStatus.EXPIRED,
            acted_at=now,
        )
    )
    await db.flush()

    count = result.rowcount
    if count > 0:
        logger.info(
            "Expired stale pending trades",
            extra={"data": {"count": count}},
        )
    return count
