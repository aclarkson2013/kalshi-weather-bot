"""E2E smoke test fixtures — real auth path, real middleware stack.

Unlike tests/api/ which overrides get_current_user with a lambda, these
fixtures only override get_db (test DB) and get_kalshi_client (external API).
The real get_current_user dependency runs: select(User).limit(1), exercising
the actual authentication path.

NOTE: Uses its own SQLite engine (like tests/api/) because endpoint handlers
call db.commit(), which breaks the root conftest's rollback strategy.
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

from backend.api.deps import get_kalshi_client
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

# ─── E2E-Specific Database Engine ───


@pytest_asyncio.fixture(scope="session")
async def e2e_engine():
    """Create a separate in-memory SQLite engine for E2E tests.

    Endpoint handlers call db.commit(), which breaks the root conftest's
    rollback strategy. This engine is fully independent.
    """
    engine = create_async_engine("sqlite+aiosqlite://", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture
async def e2e_db(e2e_engine):
    """Provide a fresh database session per E2E test.

    Data is cleaned via table truncation after each test to ensure
    isolation despite endpoint commits.
    """
    session_factory = async_sessionmaker(
        bind=e2e_engine, class_=AsyncSession, expire_on_commit=False
    )
    async with session_factory() as session:
        yield session
        # Clean up all tables after each test
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


# ─── Factory Functions ───


def make_user(user_id: str | None = None, demo_mode: bool = True) -> User:
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
        demo_mode=demo_mode,
        notifications_enabled=True,
    )


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
        brackets_json=brackets,
        ensemble_mean_f=56.3,
        ensemble_std_f=2.1,
        confidence="medium",
        model_sources="NWS,GFS,ECMWF,ICON",
        generated_at=datetime.now(UTC),
    )


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


# ─── Seed Helpers ───


async def seed_predictions(db: AsyncSession, count: int = 2) -> list[Prediction]:
    """Insert sample predictions for NYC and CHI."""
    preds = []
    for city in ["NYC", "CHI"][:count]:
        pred = make_prediction(city=city)
        db.add(pred)
        preds.append(pred)
    await db.commit()
    return preds


async def seed_trades(db: AsyncSession, user_id: str, include_settled: bool = True) -> list[Trade]:
    """Insert a mix of trades (OPEN, WON, LOST)."""
    trades = [
        make_trade(user_id=user_id, city="NYC", status=TradeStatus.OPEN),
        make_trade(user_id=user_id, city="CHI", status=TradeStatus.OPEN),
    ]
    if include_settled:
        trades.extend(
            [
                make_trade(
                    user_id=user_id,
                    city="NYC",
                    status=TradeStatus.WON,
                    pnl_cents=75,
                    settled_at=datetime.now(UTC),
                ),
                make_trade(
                    user_id=user_id,
                    city="CHI",
                    status=TradeStatus.LOST,
                    pnl_cents=-25,
                    settled_at=datetime.now(UTC),
                ),
            ]
        )
    for trade in trades:
        db.add(trade)
    await db.commit()
    return trades


async def seed_pending_trades(
    db: AsyncSession, user_id: str, count: int = 2
) -> list[PendingTradeModel]:
    """Insert sample pending trades."""
    pending = []
    for _ in range(count):
        pt = make_pending_trade(user_id=user_id)
        db.add(pt)
        pending.append(pt)
    await db.commit()
    return pending


async def seed_logs(db: AsyncSession) -> list[LogEntry]:
    """Insert sample log entries with various modules and levels."""
    entries = [
        make_log_entry(module_tag="TRADING", level="INFO", message="Trade cycle started"),
        make_log_entry(module_tag="TRADING", level="ERROR", message="Order failed"),
        make_log_entry(module_tag="WEATHER", level="INFO", message="Forecast fetched"),
        make_log_entry(module_tag="WEATHER", level="WARN", message="NWS rate limit"),
        make_log_entry(module_tag="RISK", level="ERROR", message="Daily limit hit"),
    ]
    for entry in entries:
        db.add(entry)
    await db.commit()
    return entries


# ─── E2E Test Clients ───


@pytest_asyncio.fixture
async def e2e_user(e2e_db: AsyncSession) -> User:
    """Insert a test user into the E2E database.

    The real get_current_user dependency will find this user via
    select(User).limit(1).
    """
    user = make_user(user_id="e2e-test-user-001")
    e2e_db.add(user)
    await e2e_db.commit()
    return user


@pytest_asyncio.fixture
async def authed_client(
    e2e_db: AsyncSession, e2e_user: User, mock_kalshi: AsyncMock
) -> AsyncClient:
    """Provide an httpx.AsyncClient with real auth (user in DB).

    Only overrides get_db and get_kalshi_client.
    The real get_current_user runs: select(User).limit(1) — finds e2e_user.
    """
    app.dependency_overrides[get_db] = lambda: e2e_db
    app.dependency_overrides[get_kalshi_client] = lambda: mock_kalshi

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://e2e") as ac:
        yield ac

    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def bare_client(e2e_db: AsyncSession) -> AsyncClient:
    """Provide an httpx.AsyncClient with NO user in the database.

    Only overrides get_db (pointing at the empty E2E test DB).
    The real get_current_user will raise 401 because no User rows exist.
    """
    app.dependency_overrides[get_db] = lambda: e2e_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://e2e") as ac:
        yield ac

    app.dependency_overrides.clear()
