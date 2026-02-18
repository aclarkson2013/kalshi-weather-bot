"""Trading test fixtures -- shared mocks and sample data for all trading tests."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.common.schemas import (
    TradeSignal,
    UserSettings,
)


@pytest.fixture
def user_settings() -> UserSettings:
    """UserSettings schema with safe defaults for testing."""
    return UserSettings(
        trading_mode="manual",
        max_trade_size_cents=100,
        daily_loss_limit_cents=1000,
        max_daily_exposure_cents=2500,
        min_ev_threshold=0.05,
        cooldown_per_loss_minutes=60,
        consecutive_loss_limit=3,
        active_cities=["NYC", "CHI", "MIA", "AUS"],
        notifications_enabled=True,
    )


@pytest.fixture
def sample_signal() -> TradeSignal:
    """TradeSignal with reasonable values for a +EV YES trade."""
    return TradeSignal(
        city="NYC",
        bracket="55-56\u00b0F",
        side="yes",
        price_cents=22,
        quantity=1,
        model_probability=0.30,
        market_probability=0.22,
        ev=0.05,
        confidence="medium",
        market_ticker="KXHIGHNY-26FEB18-B3",
        reasoning="test",
    )


@pytest.fixture
def mock_db() -> AsyncMock:
    """AsyncMock for a SQLAlchemy async session.

    Provides sensible defaults: execute returns a MagicMock whose
    scalar() returns 0 and scalar_one_or_none() returns None.
    """
    db = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar.return_value = 0
    mock_result.scalar_one_or_none.return_value = None
    mock_result.scalars.return_value.all.return_value = []
    db.execute.return_value = mock_result
    return db


@pytest.fixture
def mock_kalshi_client() -> AsyncMock:
    """AsyncMock for a Kalshi client with place_order returning an OrderResponse mock."""
    mock_response = MagicMock()
    mock_response.order_id = "order-123"
    mock_response.count = 1
    mock_response.status = "filled"

    client = AsyncMock()
    client.place_order.return_value = mock_response
    return client
