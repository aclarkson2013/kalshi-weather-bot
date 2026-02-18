"""Root test configuration — shared fixtures for all test modules.

IMPORTANT: Environment variables are set BEFORE any backend imports
so that config.py can load Settings without a .env file.
"""

from __future__ import annotations

import os

# Set required env vars before importing anything from backend
from cryptography.fernet import Fernet

_TEST_FERNET_KEY = Fernet.generate_key().decode()
os.environ.setdefault("ENCRYPTION_KEY", _TEST_FERNET_KEY)
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite://")  # In-memory SQLite
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/15")  # Test DB 15
os.environ.setdefault("CELERY_BROKER_URL", "redis://localhost:6379/15")
os.environ.setdefault("CELERY_RESULT_BACKEND", "redis://localhost:6379/15")
os.environ.setdefault("ENVIRONMENT", "testing")

# Now safe to import backend modules
from datetime import UTC, date, datetime

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.common.config import Settings, get_settings
from backend.common.models import Base
from backend.common.schemas import (
    BracketPrediction,
    BracketProbability,
    TradeSignal,
)

# ─── Clear cached settings so test env vars are used ───
get_settings.cache_clear()


# ─── Test Database ───


@pytest_asyncio.fixture(scope="session")
async def engine():
    """Create an async test database engine (session-scoped)."""
    test_engine = create_async_engine("sqlite+aiosqlite://", echo=False)

    # Create all tables
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield test_engine

    # Drop all tables
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

    await test_engine.dispose()


@pytest_asyncio.fixture
async def db(engine):
    """Provide a fresh database session per test with automatic rollback."""
    async_session = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    async with async_session() as session:
        # Start a nested transaction so we can roll back
        async with session.begin():
            yield session
            # Rollback ensures clean state between tests
            await session.rollback()


# ─── Test Settings ───


@pytest.fixture
def test_settings() -> Settings:
    """Create safe test settings (small limits, no real keys)."""
    return get_settings()


# ─── Sample Data Fixtures ───


@pytest.fixture
def sample_bracket_prediction() -> BracketPrediction:
    """A realistic BracketPrediction for NYC with 6 brackets summing to 1.0."""
    return BracketPrediction(
        city="NYC",
        date=date(2025, 2, 15),
        brackets=[
            BracketProbability(
                bracket_label="≤52°F",
                lower_bound_f=None,
                upper_bound_f=52,
                probability=0.08,
            ),
            BracketProbability(
                bracket_label="53-54°F",
                lower_bound_f=53,
                upper_bound_f=54,
                probability=0.15,
            ),
            BracketProbability(
                bracket_label="55-56°F",
                lower_bound_f=55,
                upper_bound_f=56,
                probability=0.30,
            ),
            BracketProbability(
                bracket_label="57-58°F",
                lower_bound_f=57,
                upper_bound_f=58,
                probability=0.28,
            ),
            BracketProbability(
                bracket_label="59-60°F",
                lower_bound_f=59,
                upper_bound_f=60,
                probability=0.12,
            ),
            BracketProbability(
                bracket_label="≥61°F",
                lower_bound_f=61,
                upper_bound_f=None,
                probability=0.07,
            ),
        ],
        ensemble_mean_f=56.3,
        ensemble_std_f=2.1,
        confidence="medium",
        model_sources=["NWS", "GFS", "ECMWF", "ICON"],
        generated_at=datetime(2025, 2, 14, 15, 0, 0, tzinfo=UTC),
    )


@pytest.fixture
def sample_trade_signal() -> TradeSignal:
    """A realistic +EV TradeSignal for NYC."""
    return TradeSignal(
        city="NYC",
        bracket="55-56°F",
        side="yes",
        price_cents=22,
        quantity=1,
        model_probability=0.30,
        market_probability=0.22,
        ev=0.05,
        confidence="medium",
        market_ticker="KXHIGHNY-25FEB15-B3",
        reasoning="Model sees 30% vs market 22% — 8% edge with 5 cent EV",
    )
