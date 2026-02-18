"""API test fixtures — httpx.AsyncClient, dependency overrides, test data factories.

Provides an async test client that exercises the full FastAPI app (with
dependency injection overridden to use a dedicated test database and mock Kalshi).

NOTE: API tests use their own database engine (separate from the root conftest)
because endpoint handlers call db.commit(), which interferes with the root
conftest's rollback-based isolation strategy.
"""

from __future__ import annotations

import contextlib
from datetime import UTC, date, datetime, timedelta
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.api.deps import get_current_user, get_kalshi_client
from backend.common.database import get_db
from backend.common.encryption import encrypt_api_key
from backend.common.models import (
    Base,
    CityEnum,
    LogEntry,
    PendingTradeModel,
    PendingTradeStatus,
    Prediction,
    Trade,
    TradeStatus,
    User,
)
from backend.main import app

# ─── API-Test-Specific Database Engine ───


@pytest_asyncio.fixture(scope="session")
async def api_engine():
    """Create a separate in-memory SQLite engine for API tests.

    API endpoint handlers call db.commit(), which would break the rollback
    strategy used by the root conftest. This engine is independent.
    """
    engine = create_async_engine("sqlite+aiosqlite://", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture
async def db(api_engine):
    """Provide a fresh database session per API test.

    Uses the API-specific engine. Data is cleaned up via table truncation
    after each test to ensure isolation despite endpoint commits.
    """
    session_factory = async_sessionmaker(
        bind=api_engine, class_=AsyncSession, expire_on_commit=False
    )
    async with session_factory() as session:
        yield session
        # Clean up all tables after each test (endpoints commit data).
        # Roll back first to clear any pending error state from failed flushes.
        with contextlib.suppress(Exception):
            await session.rollback()
        for table in reversed(Base.metadata.sorted_tables):
            await session.execute(table.delete())
        await session.commit()


# ─── Mock Kalshi Client ───


@pytest.fixture
def mock_kalshi() -> AsyncMock:
    """Create a mock KalshiClient with default return values."""
    mock = AsyncMock()
    mock.get_balance.return_value = 500.0  # $500 = 50000 cents
    mock.close.return_value = None
    return mock


# ─── Test User Factory ───


def make_user(user_id: str | None = None) -> User:
    """Create a User ORM model with encrypted test credentials."""
    return User(
        id=user_id or str(uuid4()),
        kalshi_key_id="test-key-id-12345",
        encrypted_private_key=encrypt_api_key("test-private-key-pem"),
        trading_mode="manual",
        max_trade_size_cents=100,
        daily_loss_limit_cents=1000,
        max_daily_exposure_cents=2500,
        min_ev_threshold=0.05,
        cooldown_per_loss_minutes=60,
        consecutive_loss_limit=3,
        active_cities="NYC,CHI,MIA,AUS",
        notifications_enabled=True,
    )


# ─── Test Trade Factory ───


def make_trade(
    user_id: str,
    city: str = "NYC",
    status: TradeStatus = TradeStatus.OPEN,
    pnl_cents: int | None = None,
    trade_date: date | None = None,
    settled_at: datetime | None = None,
) -> Trade:
    """Create a Trade ORM model with realistic defaults."""
    return Trade(
        id=str(uuid4()),
        user_id=user_id,
        kalshi_order_id=f"order-{uuid4().hex[:8]}",
        city=CityEnum(city),
        trade_date=trade_date or date.today(),
        market_ticker=f"KXHIGH{city}-26FEB18-B3",
        bracket_label="55-56°F",
        side="yes",
        price_cents=25,
        quantity=1,
        model_probability=0.30,
        market_probability=0.25,
        ev_at_entry=0.05,
        confidence="medium",
        status=status,
        pnl_cents=pnl_cents,
        settled_at=settled_at,
    )


# ─── Test Prediction Factory ───


def make_prediction(city: str = "NYC") -> Prediction:
    """Create a Prediction ORM model with 6 test brackets."""
    brackets = [
        {"bracket_label": "≤52°F", "lower_bound_f": None, "upper_bound_f": 52, "probability": 0.08},
        {"bracket_label": "53-54°F", "lower_bound_f": 53, "upper_bound_f": 54, "probability": 0.15},
        {"bracket_label": "55-56°F", "lower_bound_f": 55, "upper_bound_f": 56, "probability": 0.30},
        {"bracket_label": "57-58°F", "lower_bound_f": 57, "upper_bound_f": 58, "probability": 0.28},
        {"bracket_label": "59-60°F", "lower_bound_f": 59, "upper_bound_f": 60, "probability": 0.12},
        {"bracket_label": "≥61°F", "lower_bound_f": 61, "upper_bound_f": None, "probability": 0.07},
    ]
    return Prediction(
        city=CityEnum(city),
        prediction_date=datetime.now(UTC),
        brackets_json=brackets,  # JSON column — pass native Python list, not json.dumps()
        ensemble_mean_f=56.3,
        ensemble_std_f=2.1,
        confidence="medium",
        model_sources="NWS,GFS,ECMWF,ICON",
        generated_at=datetime.now(UTC),
    )


# ─── Test Pending Trade Factory ───


def make_pending_trade(
    user_id: str,
    status: PendingTradeStatus = PendingTradeStatus.PENDING,
) -> PendingTradeModel:
    """Create a PendingTradeModel ORM with realistic defaults."""
    return PendingTradeModel(
        id=str(uuid4()),
        user_id=user_id,
        city=CityEnum.NYC,
        bracket_label="55-56°F",
        market_ticker="KXHIGHNY-26FEB18-B3",
        side="yes",
        price_cents=22,
        quantity=1,
        model_probability=0.30,
        market_probability=0.22,
        ev=0.05,
        confidence="medium",
        reasoning="Model sees 30% vs market 22%",
        status=status,
        expires_at=datetime.now(UTC) + timedelta(hours=2),
    )


# ─── Test Log Entry Factory ───


def make_log_entry(
    module_tag: str = "TRADING",
    level: str = "INFO",
    message: str = "Test log entry",
    data: dict | None = None,
) -> LogEntry:
    """Create a LogEntry ORM model."""
    return LogEntry(
        module_tag=module_tag,
        level=level,
        message=message,
        data=data or {"key": "value"},
    )


# ─── Async Test Client ───


@pytest_asyncio.fixture
async def client(db: AsyncSession, mock_kalshi: AsyncMock) -> AsyncClient:
    """Provide an httpx.AsyncClient wired to the test FastAPI app.

    Overrides the database, user, and Kalshi client dependencies
    so that tests use the in-memory test DB and mock Kalshi.
    """
    # Create a test user and add to the session
    user = make_user(user_id="test-user-001")
    db.add(user)
    await db.commit()

    # Override dependencies
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_kalshi_client] = lambda: mock_kalshi

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    # Clean up overrides
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def unauthed_client(db: AsyncSession) -> AsyncClient:
    """Provide an httpx.AsyncClient with NO user in the database.

    For testing 401 responses when no user has been onboarded yet.
    """

    async def _no_user():
        raise __import__("fastapi").HTTPException(
            status_code=401, detail="Not authenticated — complete onboarding first"
        )

    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = _no_user
    app.dependency_overrides.pop(get_kalshi_client, None)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()
