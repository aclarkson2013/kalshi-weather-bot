"""Integration tests: Signal → Risk Check → Execute → DB record.

Tests the full trading flow: a TradeSignal passes risk checks, gets
executed via mock Kalshi, and produces a Trade record in the database.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from unittest.mock import AsyncMock
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.common.models import Trade, TradeStatus
from backend.common.schemas import (
    TradeSignal,
    UserSettings,
)
from backend.prediction.pipeline import generate_prediction
from backend.trading.ev_calculator import scan_all_brackets
from backend.trading.executor import execute_trade
from backend.trading.risk_manager import RiskManager
from tests.integration.conftest import insert_trade


@pytest.fixture
def valid_signal() -> TradeSignal:
    """A +EV signal that should pass all risk checks."""
    return TradeSignal(
        city="NYC",
        bracket="53-55",
        side="yes",
        price_cents=15,
        quantity=1,
        model_probability=0.35,
        market_probability=0.15,
        ev=0.06,
        confidence="medium",
        market_ticker="KXHIGHNY-26FEB20-B3",
        reasoning="Model: 35% vs Market: 15%",
    )


@pytest.mark.asyncio
async def test_signal_passes_risk_and_executes(
    db: AsyncSession,
    test_user,
    user_settings: UserSettings,
    valid_signal: TradeSignal,
    mock_kalshi_client: AsyncMock,
) -> None:
    """Valid signal → passes risk → executes → Trade in DB with OPEN status."""
    rm = RiskManager(settings=user_settings, db=db, user_id=test_user.id)
    allowed, reason = await rm.check_trade(valid_signal)
    assert allowed, f"Risk check failed: {reason}"

    record = await execute_trade(valid_signal, mock_kalshi_client, db, test_user.id)
    assert record.status == "OPEN"
    assert record.city == "NYC"

    # Verify it landed in the DB
    result = await db.execute(select(Trade).where(Trade.id == record.id))
    trade = result.scalar_one()
    assert trade.status == TradeStatus.OPEN
    assert trade.price_cents == 15


@pytest.mark.asyncio
async def test_trade_record_fields_correct(
    db: AsyncSession,
    test_user,
    user_settings: UserSettings,
    valid_signal: TradeSignal,
    mock_kalshi_client: AsyncMock,
) -> None:
    """Trade record fields should match the input signal."""
    rm = RiskManager(settings=user_settings, db=db, user_id=test_user.id)
    allowed, _ = await rm.check_trade(valid_signal)
    assert allowed

    record = await execute_trade(valid_signal, mock_kalshi_client, db, test_user.id)

    result = await db.execute(select(Trade).where(Trade.id == record.id))
    trade = result.scalar_one()
    assert trade.side == "yes"
    assert trade.bracket_label == "53-55"
    assert trade.model_probability == 0.35
    assert trade.market_probability == 0.15
    assert trade.ev_at_entry == 0.06
    assert trade.confidence == "medium"
    assert trade.user_id == test_user.id


@pytest.mark.asyncio
async def test_trade_updates_exposure(
    db: AsyncSession,
    test_user,
    user_settings: UserSettings,
    valid_signal: TradeSignal,
    mock_kalshi_client: AsyncMock,
) -> None:
    """After executing a trade, open exposure increases."""
    rm = RiskManager(settings=user_settings, db=db, user_id=test_user.id)

    exposure_before = await rm.get_open_exposure_cents()
    assert exposure_before == 0

    allowed, _ = await rm.check_trade(valid_signal)
    assert allowed
    await execute_trade(valid_signal, mock_kalshi_client, db, test_user.id)

    exposure_after = await rm.get_open_exposure_cents()
    assert exposure_after == 15  # YES at 15c


@pytest.mark.asyncio
async def test_multiple_trades_accumulate(
    db: AsyncSession,
    test_user,
    user_settings: UserSettings,
    mock_kalshi_client: AsyncMock,
) -> None:
    """3 trades → exposure = sum of costs."""
    rm = RiskManager(settings=user_settings, db=db, user_id=test_user.id)
    prices = [15, 20, 25]
    for price in prices:
        signal = TradeSignal(
            city="NYC",
            bracket="53-55",
            side="yes",
            price_cents=price,
            quantity=1,
            model_probability=0.35,
            market_probability=price / 100,
            ev=0.06,
            confidence="medium",
            market_ticker="KXHIGHNY-26FEB20-B3",
        )
        allowed, reason = await rm.check_trade(signal)
        assert allowed, f"Trade at {price}c blocked: {reason}"
        await execute_trade(signal, mock_kalshi_client, db, test_user.id)

    exposure = await rm.get_open_exposure_cents()
    assert exposure == sum(prices)


@pytest.mark.asyncio
async def test_exposure_limit_blocks(
    db: AsyncSession,
    test_user,
    mock_kalshi_client: AsyncMock,
) -> None:
    """At exposure limit → next trade blocked."""
    # Use tight settings: 50c max exposure
    tight_settings = UserSettings(max_daily_exposure_cents=50, max_trade_size_cents=100)
    rm = RiskManager(settings=tight_settings, db=db, user_id=test_user.id)

    # Insert trades totaling 50c exposure
    await insert_trade(db, test_user.id, price_cents=25, quantity=1)
    await insert_trade(db, test_user.id, price_cents=25, quantity=1)

    signal = TradeSignal(
        city="NYC",
        bracket="53-55",
        side="yes",
        price_cents=10,
        quantity=1,
        model_probability=0.35,
        market_probability=0.10,
        ev=0.10,
        confidence="medium",
        market_ticker="KXHIGHNY-26FEB20-B3",
    )
    allowed, reason = await rm.check_trade(signal)
    assert not allowed
    assert "exposure" in reason.lower()


@pytest.mark.asyncio
async def test_loss_limit_blocks(
    db: AsyncSession,
    test_user,
    mock_kalshi_client: AsyncMock,
) -> None:
    """Settled losses at limit → next trade blocked."""
    tight_settings = UserSettings(
        daily_loss_limit_cents=50,
        max_trade_size_cents=100,
        max_daily_exposure_cents=2500,
    )
    rm = RiskManager(settings=tight_settings, db=db, user_id=test_user.id)

    # Insert settled losing trades totaling -50c P&L
    # trade_date must match get_trading_day() which uses ET.  Near midnight UTC,
    # datetime.now(UTC).date() can differ from the ET date → query misses trades.
    now = datetime.now(UTC)
    trading_day = datetime.now(ZoneInfo("America/New_York")).date()
    trade_dt = datetime(trading_day.year, trading_day.month, trading_day.day, 12, 0, 0, tzinfo=UTC)
    await insert_trade(
        db,
        test_user.id,
        status=TradeStatus.LOST,
        pnl_cents=-25,
        settled_at=now,
        trade_date=trade_dt,
    )
    await insert_trade(
        db,
        test_user.id,
        status=TradeStatus.LOST,
        pnl_cents=-25,
        settled_at=now,
        trade_date=trade_dt,
    )

    signal = TradeSignal(
        city="NYC",
        bracket="53-55",
        side="yes",
        price_cents=15,
        quantity=1,
        model_probability=0.35,
        market_probability=0.15,
        ev=0.06,
        confidence="medium",
        market_ticker="KXHIGHNY-26FEB20-B3",
    )
    allowed, reason = await rm.check_trade(signal)
    assert not allowed
    assert "loss" in reason.lower()


@pytest.mark.asyncio
async def test_ev_below_threshold_blocked(
    db: AsyncSession,
    test_user,
    user_settings: UserSettings,
) -> None:
    """Low EV signal → blocked by risk manager."""
    rm = RiskManager(settings=user_settings, db=db, user_id=test_user.id)
    weak_signal = TradeSignal(
        city="NYC",
        bracket="53-55",
        side="yes",
        price_cents=33,
        quantity=1,
        model_probability=0.35,
        market_probability=0.33,
        ev=0.01,  # Below 0.05 threshold
        confidence="medium",
        market_ticker="KXHIGHNY-26FEB20-B3",
    )
    allowed, reason = await rm.check_trade(weak_signal)
    assert not allowed
    assert "EV" in reason


@pytest.mark.asyncio
async def test_end_to_end_prediction_to_db(
    db: AsyncSession,
    test_user,
    user_settings: UserSettings,
    sample_weather_data,
    sample_kalshi_brackets,
    market_prices,
    market_tickers,
    mock_kalshi_client: AsyncMock,
) -> None:
    """Full pipeline: generate_prediction → scan → risk → execute → DB."""
    # Step 1: Generate prediction
    pred = await generate_prediction(
        city="NYC",
        target_date=date(2026, 2, 20),
        forecasts=sample_weather_data,
        kalshi_brackets=sample_kalshi_brackets,
        db_session=db,
    )
    assert len(pred.brackets) == 6

    # Step 2: Scan for signals (use low threshold to get at least one)
    signals = scan_all_brackets(pred, market_prices, market_tickers, min_ev_threshold=0.01)

    if not signals:
        pytest.skip("No +EV signals found — market prices too aligned with model")

    # Step 3: Risk check + execute first signal
    rm = RiskManager(settings=user_settings, db=db, user_id=test_user.id)
    signal = signals[0]
    allowed, reason = await rm.check_trade(signal)
    assert allowed, f"Risk blocked: {reason}"

    record = await execute_trade(signal, mock_kalshi_client, db, test_user.id)

    # Step 4: Verify in DB
    result = await db.execute(select(Trade).where(Trade.id == record.id))
    trade = result.scalar_one()
    assert trade.status == TradeStatus.OPEN
    assert trade.city.value == "NYC"
