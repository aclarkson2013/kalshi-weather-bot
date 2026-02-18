"""Log viewer endpoint.

Provides filtered access to structured log entries stored in the
database, supporting module, level, and timestamp filters.
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps import get_current_user
from backend.api.response_schemas import LogEntryResponse
from backend.common.database import get_db
from backend.common.logging import get_logger
from backend.common.models import LogEntry, User

logger = get_logger("API")

router = APIRouter()

MAX_LOG_ENTRIES = 200


@router.get("", response_model=list[LogEntryResponse])
async def get_logs(
    module: str | None = None,
    level: str | None = None,
    after: datetime | None = None,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[LogEntryResponse]:
    """Fetch structured log entries with optional filters.

    Args:
        module: Optional module tag filter (e.g., TRADING, ORDER, RISK).
        level: Optional log level filter (e.g., INFO, ERROR, WARNING).
        after: Optional timestamp filter -- only logs after this time.
        user: The authenticated user (required for access control).
        db: Async database session.

    Returns:
        List of LogEntryResponse objects, ordered by timestamp descending,
        limited to MAX_LOG_ENTRIES.
    """
    query = select(LogEntry)

    # Apply optional filters
    if module is not None:
        query = query.where(LogEntry.module_tag == module)

    if level is not None:
        query = query.where(LogEntry.level == level)

    if after is not None:
        query = query.where(LogEntry.timestamp > after)

    # Order by newest first, limit results
    query = query.order_by(LogEntry.timestamp.desc()).limit(MAX_LOG_ENTRIES)

    result = await db.execute(query)
    entries = result.scalars().all()

    logger.info(
        "Logs fetched",
        extra={
            "data": {
                "module_filter": module,
                "level_filter": level,
                "after_filter": str(after) if after else None,
                "returned": len(entries),
            }
        },
    )

    return [
        LogEntryResponse(
            id=entry.id,
            timestamp=entry.timestamp,
            level=entry.level,
            module=entry.module_tag,
            message=entry.message,
            data=entry.data,
        )
        for entry in entries
    ]
