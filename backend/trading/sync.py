"""Kalshi portfolio sync — reconciles app Trade records with actual Kalshi orders.

Fetches filled orders from Kalshi and creates Trade records for any that the app
doesn't already know about. These "synced" trades have model_probability=0.0 and
ev_at_entry=0.0 since they were placed outside the bot's prediction pipeline.

Usage:
    from backend.trading.sync import sync_portfolio

    result = await sync_portfolio(kalshi_client, db, user_id)
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.common.logging import get_logger
from backend.common.metrics import PORTFOLIO_SYNC_TOTAL, PORTFOLIO_SYNC_TRADES_CREATED
from backend.common.models import Trade, TradeStatus
from backend.common.schemas import SyncResult
from backend.kalshi.markets import SERIES_TO_CITY, parse_bracket_from_market
from backend.kalshi.models import OrderResponse

logger = get_logger("TRADING")


def _parse_city_from_ticker(ticker: str) -> str | None:
    """Extract city code from a Kalshi market ticker.

    Args:
        ticker: Market ticker like "KXHIGHNY-26FEB22-T38".

    Returns:
        City code like "NYC", or None if not a weather ticker.
    """
    # Ticker format: {series}-{date}-{bracket}
    # Series is the part before the first dash: KXHIGHNY, KXHIGHMIA, etc.
    parts = ticker.split("-")
    if len(parts) < 2:
        return None

    series = parts[0]
    return SERIES_TO_CITY.get(series)


async def _order_already_tracked(
    db: AsyncSession,
    user_id: str,
    order_id: str,
) -> bool:
    """Check if a Kalshi order is already tracked in the app's Trade table."""
    result = await db.execute(
        select(Trade.id).where(Trade.user_id == user_id, Trade.kalshi_order_id == order_id).limit(1)
    )
    return result.scalar_one_or_none() is not None


async def _create_synced_trade(
    db: AsyncSession,
    user_id: str,
    order: OrderResponse,
    city: str,
    bracket_label: str,
) -> Trade:
    """Create a new Trade record from a Kalshi filled order.

    Synced trades use sentinel values for model-specific fields since they
    were placed outside the bot's prediction pipeline.
    """
    trade = Trade(
        id=str(uuid4()),
        user_id=user_id,
        kalshi_order_id=order.order_id,
        city=city,
        trade_date=order.created_time,
        market_ticker=order.ticker,
        bracket_label=bracket_label,
        side=order.side,
        price_cents=order.yes_price,
        quantity=order.fill_count,
        model_probability=0.0,
        market_probability=order.yes_price / 100.0,
        ev_at_entry=0.0,
        confidence="low",
        status=TradeStatus.OPEN,
        created_at=order.created_time,
    )
    db.add(trade)
    return trade


async def sync_portfolio(
    kalshi_client: object,
    db: AsyncSession,
    user_id: str,
) -> SyncResult:
    """Sync app trade records with actual Kalshi filled orders.

    Fetches all executed orders from Kalshi, checks each against the
    database, and creates Trade records for any that are not yet tracked.

    Args:
        kalshi_client: Authenticated KalshiClient instance.
        db: Async database session.
        user_id: The user ID to sync for.

    Returns:
        SyncResult with counts of created, skipped, and failed trades.
    """
    synced = 0
    skipped = 0
    failed = 0
    errors: list[str] = []

    try:
        orders: list[OrderResponse] = await kalshi_client.get_orders(status="executed")
    except Exception as exc:
        logger.warning(
            "Portfolio sync: failed to fetch orders from Kalshi",
            extra={"data": {"error": str(exc)}},
        )
        PORTFOLIO_SYNC_TOTAL.labels(outcome="error").inc()
        return SyncResult(
            synced_count=0,
            skipped_count=0,
            failed_count=1,
            errors=[f"Failed to fetch orders: {exc}"],
            synced_at=datetime.now(UTC),
        )

    if not orders:
        PORTFOLIO_SYNC_TOTAL.labels(outcome="success").inc()
        return SyncResult(synced_at=datetime.now(UTC))

    # Cache market details to avoid redundant API calls
    market_cache: dict[str, dict] = {}

    for order in orders:
        try:
            # Only sync filled orders with actual contracts
            if order.fill_count <= 0:
                skipped += 1
                continue

            # Parse city from ticker
            city = _parse_city_from_ticker(order.ticker)
            if city is None:
                skipped += 1
                continue

            # Check if already tracked
            if await _order_already_tracked(db, user_id, order.order_id):
                skipped += 1
                continue

            # Fetch market details for bracket label (cached per ticker)
            if order.ticker not in market_cache:
                try:
                    market = await kalshi_client.get_market(order.ticker)
                    market_cache[order.ticker] = parse_bracket_from_market(
                        {
                            "floor_strike": market.floor_strike,
                            "cap_strike": market.cap_strike,
                            "ticker": market.ticker,
                        }
                    )
                except Exception as market_exc:
                    logger.warning(
                        "Portfolio sync: failed to fetch market details",
                        extra={
                            "data": {
                                "ticker": order.ticker,
                                "error": str(market_exc),
                            }
                        },
                    )
                    # Use ticker suffix as fallback label
                    market_cache[order.ticker] = {"label": order.ticker.split("-")[-1]}

            bracket_label = market_cache[order.ticker]["label"]

            # Create the trade record
            await _create_synced_trade(db, user_id, order, city, bracket_label)
            synced += 1
            PORTFOLIO_SYNC_TRADES_CREATED.inc()

        except Exception as exc:
            failed += 1
            errors.append(f"Order {order.order_id}: {exc}")
            logger.warning(
                "Portfolio sync: failed to process order",
                extra={
                    "data": {
                        "order_id": order.order_id,
                        "ticker": order.ticker,
                        "error": str(exc),
                    }
                },
            )

    await db.commit()

    outcome = "success" if failed == 0 else "partial"
    PORTFOLIO_SYNC_TOTAL.labels(outcome=outcome).inc()

    logger.info(
        "Portfolio sync completed",
        extra={
            "data": {
                "synced": synced,
                "skipped": skipped,
                "failed": failed,
            }
        },
    )

    return SyncResult(
        synced_count=synced,
        skipped_count=skipped,
        failed_count=failed,
        errors=errors,
        synced_at=datetime.now(UTC),
    )
