"""Integration test fixtures — shared across all integration test modules.

Provides pre-built weather data, bracket definitions, market prices/tickers,
user settings, and mock Kalshi client for cross-module integration tests.

Uses the root conftest's `db` fixture (begin + rollback) since integration
tests call flush() (not commit()), which is compatible with that strategy.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from backend.common.encryption import encrypt_api_key
from backend.common.models import CityEnum, Settlement, Trade, TradeStatus, User
from backend.common.schemas import (
    UserSettings,
    WeatherData,
    WeatherVariables,
)
from backend.kalshi.models import OrderResponse

# ─── Test User ───


@pytest_asyncio.fixture
async def test_user(db: AsyncSession) -> User:
    """Insert and return a User with encrypted test credentials."""
    user = User(
        id=f"integ-user-{uuid4().hex[:8]}",
        kalshi_key_id="test-key-id-12345",
        encrypted_private_key=encrypt_api_key("test-private-key-pem"),
        trading_mode="auto",
        max_trade_size_cents=100,
        daily_loss_limit_cents=1000,
        max_daily_exposure_cents=2500,
        min_ev_threshold=0.05,
        cooldown_per_loss_minutes=60,
        consecutive_loss_limit=3,
        active_cities="NYC,CHI,MIA,AUS",
        notifications_enabled=True,
    )
    db.add(user)
    await db.flush()
    return user


# ─── User Settings ───


@pytest.fixture
def user_settings() -> UserSettings:
    """Safe risk limits for integration tests."""
    return UserSettings(
        trading_mode="auto",
        max_trade_size_cents=100,
        daily_loss_limit_cents=1000,
        max_daily_exposure_cents=2500,
        min_ev_threshold=0.05,
        cooldown_per_loss_minutes=60,
        consecutive_loss_limit=3,
        active_cities=["NYC", "CHI", "MIA", "AUS"],
    )


# ─── Weather Data ───


@pytest.fixture
def sample_weather_data() -> list[WeatherData]:
    """5 WeatherData forecasts for NYC from different sources."""
    now = datetime.now(UTC)
    target = date(2026, 2, 20)
    return [
        WeatherData(
            city="NYC",
            date=target,
            forecast_high_f=55.0,
            source="NWS",
            model_run_timestamp=now,
            variables=WeatherVariables(temp_high_f=55.0, temp_low_f=38.0),
            raw_data={"source": "NWS"},
            fetched_at=now,
        ),
        WeatherData(
            city="NYC",
            date=target,
            forecast_high_f=53.0,
            source="Open-Meteo:ECMWF",
            model_run_timestamp=now,
            variables=WeatherVariables(temp_high_f=53.0, temp_low_f=37.0),
            raw_data={"source": "ECMWF"},
            fetched_at=now,
        ),
        WeatherData(
            city="NYC",
            date=target,
            forecast_high_f=54.0,
            source="Open-Meteo:GFS",
            model_run_timestamp=now,
            variables=WeatherVariables(temp_high_f=54.0, temp_low_f=37.5),
            raw_data={"source": "GFS"},
            fetched_at=now,
        ),
        WeatherData(
            city="NYC",
            date=target,
            forecast_high_f=55.0,
            source="Open-Meteo:ICON",
            model_run_timestamp=now,
            variables=WeatherVariables(temp_high_f=55.0, temp_low_f=38.0),
            raw_data={"source": "ICON"},
            fetched_at=now,
        ),
        WeatherData(
            city="NYC",
            date=target,
            forecast_high_f=54.0,
            source="Open-Meteo:GEM",
            model_run_timestamp=now,
            variables=WeatherVariables(temp_high_f=54.0, temp_low_f=37.0),
            raw_data={"source": "GEM"},
            fetched_at=now,
        ),
    ]


# ─── Bracket Definitions (Kalshi format) ───


@pytest.fixture
def sample_kalshi_brackets() -> list[dict]:
    """6 bracket definitions matching Kalshi format for ~54F ensemble."""
    return [
        {"lower_bound_f": None, "upper_bound_f": 51.0, "label": "<51"},
        {"lower_bound_f": 51.0, "upper_bound_f": 53.0, "label": "51-53"},
        {"lower_bound_f": 53.0, "upper_bound_f": 55.0, "label": "53-55"},
        {"lower_bound_f": 55.0, "upper_bound_f": 57.0, "label": "55-57"},
        {"lower_bound_f": 57.0, "upper_bound_f": 59.0, "label": "57-59"},
        {"lower_bound_f": 59.0, "upper_bound_f": None, "label": ">=59"},
    ]


# ─── Market Prices & Tickers ───


@pytest.fixture
def market_prices() -> dict[str, int]:
    """Market YES prices in cents, with 53-55 and 55-57 diverging from model.

    Model sees ~54F ensemble, so 53-55 bracket should have highest model prob.
    Market underprices 53-55 (15c vs ~35% model) → +EV YES.
    Market overprices 55-57 (50c vs ~25% model) → possible +EV NO.
    """
    return {
        "<51": 5,
        "51-53": 12,
        "53-55": 15,
        "55-57": 50,
        "57-59": 10,
        ">=59": 8,
    }


@pytest.fixture
def market_tickers() -> dict[str, str]:
    """Kalshi market ticker strings keyed by bracket label."""
    return {
        "<51": "KXHIGHNY-26FEB20-B1",
        "51-53": "KXHIGHNY-26FEB20-B2",
        "53-55": "KXHIGHNY-26FEB20-B3",
        "55-57": "KXHIGHNY-26FEB20-B4",
        "57-59": "KXHIGHNY-26FEB20-B5",
        ">=59": "KXHIGHNY-26FEB20-B6",
    }


# ─── Mock Kalshi Client ───


@pytest.fixture
def mock_kalshi_client() -> AsyncMock:
    """AsyncMock KalshiClient with place_order returning success."""
    mock = AsyncMock()
    mock.place_order.return_value = OrderResponse(
        order_id=f"order-{uuid4().hex[:8]}",
        ticker="KXHIGHNY-26FEB20-B3",
        action="buy",
        side="yes",
        type="limit",
        fill_count=1,
        initial_count=1,
        yes_price=22,
        status="executed",
        created_time=datetime.now(UTC),
    )
    mock.get_balance.return_value = 500.0
    mock.close.return_value = None
    return mock


# ─── Helper: Build a Trade in DB ───


async def insert_trade(
    db: AsyncSession,
    user_id: str,
    *,
    city: str = "NYC",
    bracket_label: str = "53-55",
    side: str = "yes",
    price_cents: int = 25,
    quantity: int = 1,
    status: TradeStatus = TradeStatus.OPEN,
    pnl_cents: int | None = None,
    settled_at: datetime | None = None,
    trade_date: datetime | None = None,
) -> Trade:
    """Insert a Trade ORM record and return it."""
    trade = Trade(
        id=str(uuid4()),
        user_id=user_id,
        kalshi_order_id=f"order-{uuid4().hex[:8]}",
        city=CityEnum(city),
        trade_date=trade_date or datetime.now(UTC),
        market_ticker=f"KXHIGH{city}-26FEB20-B3",
        bracket_label=bracket_label,
        side=side,
        price_cents=price_cents,
        quantity=quantity,
        model_probability=0.30,
        market_probability=0.22,
        ev_at_entry=0.05,
        confidence="medium",
        status=status,
        pnl_cents=pnl_cents,
        settled_at=settled_at,
    )
    db.add(trade)
    await db.flush()
    return trade


async def insert_settlement(
    db: AsyncSession,
    city: str = "NYC",
    actual_high_f: float = 54.0,
    settlement_date: datetime | None = None,
) -> Settlement:
    """Insert a Settlement ORM record and return it."""
    settlement = Settlement(
        city=CityEnum(city),
        settlement_date=settlement_date or datetime.now(UTC),
        actual_high_f=actual_high_f,
        source="NWS_CLI",
    )
    db.add(settlement)
    await db.flush()
    return settlement
