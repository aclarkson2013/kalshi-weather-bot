"""Trade history endpoint with pagination, filters, and portfolio sync.

Provides paginated access to the user's trade history with optional
filtering by city and status, plus a sync endpoint to reconcile
with Kalshi's actual portfolio.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps import get_current_user, get_kalshi_client, trade_to_record
from backend.api.response_schemas import TradesPage
from backend.common.database import get_db
from backend.common.logging import get_logger
from backend.common.models import Trade, User
from backend.common.schemas import CityCode, SyncResult
from backend.websocket.events import publish_event

logger = get_logger("API")

router = APIRouter()

TRADES_PER_PAGE = 20


@router.get("", response_model=TradesPage)
async def get_trades(
    city: CityCode | None = None,
    status: str | None = None,
    page: int = 1,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TradesPage:
    """Fetch paginated trade history with optional filters.

    Args:
        city: Optional city code filter (NYC, CHI, MIA, AUS).
        status: Optional status filter (OPEN, WON, LOST, CANCELED).
        page: Page number (1-indexed, defaults to 1).
        user: The authenticated user.
        db: Async database session.

    Returns:
        TradesPage with the filtered/paginated trades, total count, and page.
    """
    # Base query filtered by user
    base_query = select(Trade).where(Trade.user_id == user.id)
    count_query = select(func.count(Trade.id)).where(Trade.user_id == user.id)

    # Apply optional filters
    if city is not None:
        base_query = base_query.where(Trade.city == city)
        count_query = count_query.where(Trade.city == city)

    if status is not None:
        base_query = base_query.where(Trade.status == status)
        count_query = count_query.where(Trade.status == status)

    # Get total count
    total_result = await db.execute(count_query)
    total = int(total_result.scalar())

    # Apply ordering and pagination
    offset = (page - 1) * TRADES_PER_PAGE
    paginated_query = (
        base_query.order_by(Trade.created_at.desc()).offset(offset).limit(TRADES_PER_PAGE)
    )

    result = await db.execute(paginated_query)
    trades = [trade_to_record(t) for t in result.scalars().all()]

    logger.info(
        "Trades fetched",
        extra={
            "data": {
                "city": city,
                "status": status,
                "page": page,
                "returned": len(trades),
                "total": total,
            }
        },
    )

    return TradesPage(trades=trades, total=total, page=page)


@router.post("/sync", response_model=SyncResult)
async def sync_trades(
    user: User = Depends(get_current_user),
    kalshi_client=Depends(get_kalshi_client),
    db: AsyncSession = Depends(get_db),
) -> SyncResult:
    """Sync app trade records with actual Kalshi portfolio.

    Fetches all filled orders from Kalshi and creates Trade records
    for any orders not already tracked by the app.
    """
    from backend.trading.sync import sync_portfolio

    try:
        result = await sync_portfolio(kalshi_client, db, user.id)
    except Exception as exc:
        logger.error(
            "Portfolio sync failed",
            extra={"data": {"error": str(exc)}},
        )
        raise HTTPException(status_code=500, detail=f"Sync failed: {exc}") from exc

    if result.synced_count > 0:
        await publish_event("trade.synced", {"synced_count": result.synced_count})

    logger.info(
        "Portfolio sync via API",
        extra={
            "data": {
                "synced": result.synced_count,
                "skipped": result.skipped_count,
                "failed": result.failed_count,
            }
        },
    )

    return result
