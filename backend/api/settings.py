"""User settings endpoints.

Provides read and partial-update access to the user's trading
configuration, risk limits, and notification preferences.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps import get_current_user, user_to_settings
from backend.api.response_schemas import SettingsUpdate
from backend.common.database import get_db
from backend.common.logging import get_logger
from backend.common.models import User
from backend.common.schemas import UserSettings

logger = get_logger("API")

router = APIRouter()


@router.get("", response_model=UserSettings)
async def get_settings_endpoint(
    user: User = Depends(get_current_user),
) -> UserSettings:
    """Fetch the current user settings.

    Args:
        user: The authenticated user.

    Returns:
        UserSettings schema with all current configuration values.
    """
    return user_to_settings(user)


@router.patch("", response_model=UserSettings)
async def update_settings(
    updates: SettingsUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> UserSettings:
    """Partially update user settings.

    Only fields included in the request body (non-None) are updated.
    The active_cities list is stored as a comma-separated string.

    Args:
        updates: Partial settings update with only changed fields.
        user: The authenticated user.
        db: Async database session.

    Returns:
        The full updated UserSettings schema.
    """
    # Get only the fields that were explicitly provided (non-None)
    update_data = updates.model_dump(exclude_none=True)

    for field_name, value in update_data.items():
        if field_name == "active_cities":
            # Convert list of city codes to comma-separated string
            user.active_cities = ",".join(value)
        else:
            setattr(user, field_name, value)

    await db.commit()

    logger.info(
        "User settings updated",
        extra={
            "data": {
                "user_id": user.id,
                "updated_fields": list(update_data.keys()),
            }
        },
    )

    return user_to_settings(user)
