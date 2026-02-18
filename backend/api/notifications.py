"""Web push notification subscription endpoint.

Stores the user's push subscription (from the browser's Push API)
so the backend can send trade alerts and settlement notifications.
"""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps import get_current_user
from backend.common.database import get_db
from backend.common.logging import get_logger
from backend.common.models import User

logger = get_logger("API")

router = APIRouter()


class PushSubscriptionRequest(BaseModel):
    """Browser Push API subscription object.

    Contains the endpoint URL, expiration time, and encryption keys
    needed to send push notifications to the user's browser.
    """

    endpoint: str
    expiration_time: int | None = Field(default=None, alias="expirationTime")
    keys: dict[str, str]

    model_config = {"populate_by_name": True}


@router.post("/subscribe", status_code=204)
async def subscribe_push(
    subscription: PushSubscriptionRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Store a web push subscription for the authenticated user.

    The frontend calls this after obtaining a PushSubscription from
    the browser's Push API. The subscription JSON is stored on the
    User record for later use by the notification service.

    Args:
        subscription: The browser's push subscription object.
        user: The authenticated user.
        db: Async database session.
    """
    user.push_subscription = json.dumps(subscription.model_dump())
    await db.commit()

    logger.info(
        "Push subscription stored",
        extra={
            "data": {
                "user_id": user.id,
                "endpoint_prefix": subscription.endpoint[:50] + "...",
            }
        },
    )
