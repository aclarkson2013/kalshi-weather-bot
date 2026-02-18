"""Tests for SQLAlchemy ORM models with async test database."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from backend.common.models import (
    CityEnum,
    DailyRiskState,
    LogEntry,
    Settlement,
    Trade,
    TradeStatus,
    User,
    WeatherForecast,
)


class TestCityEnum:
    """Test CityEnum values."""

    def test_four_cities(self):
        """All four expected cities are defined."""
        assert CityEnum.NYC.value == "NYC"
        assert CityEnum.CHI.value == "CHI"
        assert CityEnum.MIA.value == "MIA"
        assert CityEnum.AUS.value == "AUS"

    def test_enum_count(self):
        """Exactly 4 cities."""
        assert len(CityEnum) == 4


class TestTradeStatus:
    """Test TradeStatus values."""

    def test_all_statuses(self):
        """All expected trade statuses are defined."""
        statuses = {s.value for s in TradeStatus}
        assert statuses == {"OPEN", "WON", "LOST", "CANCELED"}


class TestUserModel:
    """Test User ORM model."""

    @pytest.mark.asyncio
    async def test_create_user(self, db):
        """Create and query a User record."""
        user = User(
            id=str(uuid4()),
            kalshi_key_id="test-key-id",
            encrypted_private_key="encrypted-data-here",
        )
        db.add(user)
        await db.flush()

        # Query it back
        from sqlalchemy import select

        result = await db.execute(select(User).where(User.id == user.id))
        fetched = result.scalar_one()
        assert fetched.kalshi_key_id == "test-key-id"
        assert fetched.trading_mode == "manual"  # default
        assert fetched.max_trade_size_cents == 100  # default


class TestWeatherForecastModel:
    """Test WeatherForecast ORM model."""

    @pytest.mark.asyncio
    async def test_create_forecast(self, db):
        """Create and query a WeatherForecast record."""
        forecast = WeatherForecast(
            city=CityEnum.NYC,
            forecast_date=datetime(2025, 2, 15, tzinfo=UTC),
            source="NWS",
            forecast_high_f=56.0,
            forecast_low_f=38.0,
        )
        db.add(forecast)
        await db.flush()

        from sqlalchemy import select

        result = await db.execute(select(WeatherForecast).where(WeatherForecast.source == "NWS"))
        fetched = result.scalar_one()
        assert fetched.forecast_high_f == 56.0
        assert fetched.city == CityEnum.NYC


class TestTradeModel:
    """Test Trade ORM model."""

    @pytest.mark.asyncio
    async def test_create_trade(self, db):
        """Create a Trade record with a User foreign key."""
        user_id = str(uuid4())
        user = User(
            id=user_id,
            kalshi_key_id="key-123",
            encrypted_private_key="encrypted",
        )
        db.add(user)
        await db.flush()

        trade = Trade(
            id=str(uuid4()),
            user_id=user_id,
            city=CityEnum.NYC,
            trade_date=datetime(2025, 2, 15, tzinfo=UTC),
            market_ticker="KXHIGHNY-25FEB15-B3",
            bracket_label="55-56°F",
            side="yes",
            price_cents=22,
            quantity=1,
            model_probability=0.30,
            market_probability=0.22,
            ev_at_entry=0.05,
            confidence="medium",
        )
        db.add(trade)
        await db.flush()

        from sqlalchemy import select

        result = await db.execute(select(Trade).where(Trade.user_id == user_id))
        fetched = result.scalar_one()
        assert fetched.bracket_label == "55-56°F"
        assert fetched.price_cents == 22
        assert fetched.status == TradeStatus.OPEN  # default


class TestSettlementModel:
    """Test Settlement ORM model."""

    @pytest.mark.asyncio
    async def test_create_settlement(self, db):
        """Create a Settlement record."""
        settlement = Settlement(
            city=CityEnum.NYC,
            settlement_date=datetime(2025, 2, 15, tzinfo=UTC),
            actual_high_f=56.0,
            source="NWS_CLI",
        )
        db.add(settlement)
        await db.flush()

        from sqlalchemy import select

        result = await db.execute(select(Settlement))
        fetched = result.scalar_one()
        assert fetched.actual_high_f == 56.0


class TestDailyRiskStateModel:
    """Test DailyRiskState ORM model."""

    @pytest.mark.asyncio
    async def test_create_risk_state(self, db):
        """Create a DailyRiskState record."""
        user_id = str(uuid4())
        user = User(
            id=user_id,
            kalshi_key_id="key-456",
            encrypted_private_key="encrypted",
        )
        db.add(user)
        await db.flush()

        state = DailyRiskState(
            user_id=user_id,
            trading_day=datetime(2025, 2, 15, tzinfo=UTC),
            total_loss_cents=250,
            total_exposure_cents=500,
            consecutive_losses=2,
        )
        db.add(state)
        await db.flush()

        from sqlalchemy import select

        result = await db.execute(select(DailyRiskState))
        fetched = result.scalar_one()
        assert fetched.total_loss_cents == 250
        assert fetched.consecutive_losses == 2


class TestLogEntryModel:
    """Test LogEntry ORM model."""

    @pytest.mark.asyncio
    async def test_create_log_entry(self, db):
        """Create a LogEntry record."""
        entry = LogEntry(
            level="INFO",
            module_tag="TRADING",
            message="Trade placed",
            data={"city": "NYC", "ev": 0.05},
        )
        db.add(entry)
        await db.flush()

        from sqlalchemy import select

        result = await db.execute(select(LogEntry))
        fetched = result.scalar_one()
        assert fetched.module_tag == "TRADING"
        assert fetched.data["city"] == "NYC"
