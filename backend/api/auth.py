"""Authentication endpoints for Kalshi API key management.

Handles key validation during onboarding and account disconnection.
Private keys are encrypted at rest using AES-256 (Fernet).
"""

from __future__ import annotations

from uuid import uuid4

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps import get_current_user
from backend.api.response_schemas import (
    AuthStatusResponse,
    AuthValidateRequest,
    AuthValidateResponse,
)
from backend.common.database import get_db
from backend.common.encryption import encrypt_api_key
from backend.common.logging import get_logger
from backend.common.models import User
from backend.kalshi.client import KalshiClient
from backend.kalshi.exceptions import KalshiAuthError

logger = get_logger("AUTH")

router = APIRouter()


@router.post("/validate", response_model=AuthValidateResponse)
async def validate_keys(
    request: AuthValidateRequest,
    db: AsyncSession = Depends(get_db),
) -> AuthValidateResponse:
    """Validate Kalshi API keys during onboarding.

    Creates a temporary KalshiClient, calls get_balance() to verify the
    credentials work. If valid, encrypts the private key and creates or
    updates the User record in the database.

    Args:
        request: Contains key_id and private_key to validate.
        db: Async database session.

    Returns:
        AuthValidateResponse with valid=True and current balance in cents.

    Raises:
        KalshiAuthError: Re-raised if credentials are invalid (handled by
            the exception handler in main.py, returns 401).
    """
    # Create a temporary client to test the credentials
    client = KalshiClient(
        api_key_id=request.key_id,
        private_key_pem=request.private_key,
        demo=request.demo_mode,
    )
    try:
        # get_balance() returns dollars; raises KalshiAuthError on 401
        balance_dollars = await client.get_balance()
    except KalshiAuthError:
        logger.warning(
            "Key validation failed",
            extra={"data": {"key_id_prefix": request.key_id[:8] + "..."}},
        )
        raise
    finally:
        await client.close()

    balance_cents = int(balance_dollars * 100)

    # Encrypt the private key for storage
    encrypted_key = encrypt_api_key(request.private_key)

    # Check if a user already exists (single-user system)
    result = await db.execute(select(User).limit(1))
    user = result.scalar_one_or_none()

    if user is None:
        # Create new user record
        user = User(
            id=str(uuid4()),
            kalshi_key_id=request.key_id,
            encrypted_private_key=encrypted_key,
            demo_mode=request.demo_mode,
        )
        db.add(user)
        logger.info(
            "New user created during onboarding",
            extra={"data": {"user_id": user.id, "demo_mode": request.demo_mode}},
        )
    else:
        # Update existing user credentials
        user.kalshi_key_id = request.key_id
        user.encrypted_private_key = encrypted_key
        user.demo_mode = request.demo_mode
        logger.info(
            "User credentials updated",
            extra={"data": {"user_id": user.id, "demo_mode": request.demo_mode}},
        )

    await db.commit()

    return AuthValidateResponse(
        valid=True,
        balance_cents=balance_cents,
        demo_mode=user.demo_mode if user.demo_mode is not None else True,
    )


@router.get("/status", response_model=AuthStatusResponse)
async def auth_status(
    user: User = Depends(get_current_user),
) -> AuthStatusResponse:
    """Check current authentication status.

    Returns the user's authentication state, demo mode flag, and a
    truncated key ID prefix for display purposes.

    Args:
        user: The authenticated user from dependency injection.

    Returns:
        AuthStatusResponse with authentication details.
    """
    demo = user.demo_mode if user.demo_mode is not None else True
    key_id = user.kalshi_key_id
    key_prefix = key_id[:8] + "..." if len(key_id) > 8 else key_id

    return AuthStatusResponse(
        authenticated=True,
        user_id=user.id,
        demo_mode=demo,
        key_id_prefix=key_prefix,
    )


@router.post("/disconnect", status_code=204)
async def disconnect(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Disconnect Kalshi account by deleting user credentials.

    Removes the user record from the database, effectively logging out.

    Args:
        user: The authenticated user to disconnect.
        db: Async database session.
    """
    logger.info(
        "User disconnecting account",
        extra={"data": {"user_id": user.id}},
    )
    await db.delete(user)
    await db.commit()
