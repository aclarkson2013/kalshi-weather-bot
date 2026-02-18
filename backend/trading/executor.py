"""Trade execution orchestrator -- places orders on Kalshi and records them.

Handles the full lifecycle of executing a trade signal:
1. Build a validated OrderRequest from the TradeSignal
2. Place the order via KalshiClient
3. Handle the response (filled, partial fill, rejection)
4. Create a Trade ORM record in the database
5. Return a TradeRecord schema

CRITICAL: All prices are in CENTS (integers). The Trade ORM model stores
price_cents as an integer, NOT a float.

Usage:
    from backend.trading.executor import execute_trade

    trade_record = await execute_trade(
        signal=signal,
        kalshi_client=client,
        db=session,
        user_id="u123",
    )
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession

from backend.common.exceptions import InvalidOrderError
from backend.common.logging import get_logger
from backend.common.models import Trade, TradeStatus
from backend.common.schemas import TradeRecord, TradeSignal
from backend.kalshi.models import OrderRequest

logger = get_logger("ORDER")
ET = ZoneInfo("America/New_York")


async def execute_trade(
    signal: TradeSignal,
    kalshi_client: object,
    db: AsyncSession,
    user_id: str,
) -> TradeRecord:
    """Execute a trade on Kalshi and record it in the database.

    Steps:
    1. Build OrderRequest from the signal (validated at construction)
    2. Place order via kalshi_client.place_order()
    3. Handle response: check status, partial fills
    4. Create Trade ORM record
    5. Return TradeRecord schema

    Args:
        signal: The trade signal to execute.
        kalshi_client: An authenticated KalshiClient instance.
        db: Async database session.
        user_id: The user ID placing the trade.

    Returns:
        A TradeRecord representing the executed trade.

    Raises:
        InvalidOrderError: If the order is rejected by Kalshi.
        Exception: If the Kalshi API call fails for any reason.
    """
    # Build the order
    order = OrderRequest(
        ticker=signal.market_ticker,
        action="buy",
        side=signal.side,
        type="limit",
        count=signal.quantity,
        yes_price=signal.price_cents,
    )

    logger.info(
        "Placing order",
        extra={
            "data": {
                "ticker": signal.market_ticker,
                "side": signal.side,
                "price_cents": signal.price_cents,
                "quantity": signal.quantity,
            }
        },
    )

    # Place the order
    try:
        response = await kalshi_client.place_order(order)
    except Exception as exc:
        logger.error(
            "Order placement failed",
            extra={
                "data": {
                    "ticker": signal.market_ticker,
                    "error": str(exc),
                    "side": signal.side,
                    "price_cents": signal.price_cents,
                }
            },
        )
        raise

    # Extract order details from response
    order_id = response.order_id
    filled_count = response.count
    order_status = response.status

    # Check for cancellation
    if order_status == "canceled":
        logger.warning(
            "Order was canceled by exchange",
            extra={"data": {"order_id": order_id}},
        )
        raise InvalidOrderError(
            "Order canceled by exchange",
            context={
                "order_id": order_id,
                "ticker": signal.market_ticker,
            },
        )

    # Log partial fills
    if order_status == "resting":
        logger.info(
            "Order resting (not yet filled)",
            extra={
                "data": {
                    "order_id": order_id,
                    "ticker": signal.market_ticker,
                    "count": filled_count,
                }
            },
        )

    # Record the trade in the database
    trade_id = str(uuid4())
    now = datetime.now(UTC)

    trade = Trade(
        id=trade_id,
        user_id=user_id,
        kalshi_order_id=order_id,
        city=signal.city,
        trade_date=now,
        market_ticker=signal.market_ticker,
        bracket_label=signal.bracket,
        side=signal.side,
        price_cents=signal.price_cents,
        quantity=filled_count,
        model_probability=signal.model_probability,
        market_probability=signal.market_probability,
        ev_at_entry=signal.ev,
        confidence=signal.confidence,
        status=TradeStatus.OPEN,
        created_at=now,
    )

    db.add(trade)
    await db.flush()

    logger.info(
        "Trade executed and recorded",
        extra={
            "data": {
                "trade_id": trade_id,
                "order_id": order_id,
                "city": signal.city,
                "bracket": signal.bracket,
                "side": signal.side,
                "price_cents": signal.price_cents,
                "quantity": filled_count,
                "ev": signal.ev,
            }
        },
    )

    return TradeRecord(
        id=trade_id,
        kalshi_order_id=order_id,
        city=signal.city,
        date=now.date(),
        bracket_label=signal.bracket,
        side=signal.side,
        price_cents=signal.price_cents,
        quantity=filled_count,
        model_probability=signal.model_probability,
        market_probability=signal.market_probability,
        ev_at_entry=signal.ev,
        confidence=signal.confidence,
        status="OPEN",
        settlement_temp_f=None,
        settlement_source=None,
        pnl_cents=None,
        created_at=now,
        settled_at=None,
    )
