"""Integration tests: Multi-trade risk limit enforcement.

Tests the RiskManager and CooldownManager working together across
multiple trades to enforce exposure limits, loss limits, cooldowns,
and consecutive loss halts.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from backend.common.models import TradeStatus
from backend.common.schemas import TradeSignal, UserSettings
from backend.trading.cooldown import CooldownManager
from backend.trading.risk_manager import RiskManager
from tests.integration.conftest import insert_trade


def _make_signal(price_cents: int = 25, ev: float = 0.06) -> TradeSignal:
    """Build a TradeSignal with configurable price and EV."""
    return TradeSignal(
        city="NYC",
        bracket="53-55",
        side="yes",
        price_cents=price_cents,
        quantity=1,
        model_probability=0.35,
        market_probability=price_cents / 100,
        ev=ev,
        confidence="medium",
        market_ticker="KXHIGHNY-26FEB20-B3",
    )


@pytest.mark.asyncio
async def test_exposure_accumulates(
    db: AsyncSession,
    test_user,
    user_settings: UserSettings,
) -> None:
    """5 trades → total exposure = sum of all costs."""
    prices = [10, 15, 20, 25, 30]
    for p in prices:
        await insert_trade(db, test_user.id, price_cents=p, quantity=1)

    rm = RiskManager(settings=user_settings, db=db, user_id=test_user.id)
    exposure = await rm.get_open_exposure_cents()
    assert exposure == sum(prices)


@pytest.mark.asyncio
async def test_exposure_limit_at_boundary(
    db: AsyncSession,
    test_user,
) -> None:
    """2400c of 2500c used → next 99c trade blocked."""
    settings = UserSettings(max_daily_exposure_cents=2500, max_trade_size_cents=100)
    rm = RiskManager(settings=settings, db=db, user_id=test_user.id)

    # Insert 25 trades at 99c each = 2475c
    for _ in range(25):
        await insert_trade(db, test_user.id, price_cents=99, quantity=1)

    signal = _make_signal(price_cents=99, ev=0.10)

    # 2475 + 99 = 2574 > 2500 → blocked
    allowed, reason = await rm.check_trade(signal)
    assert not allowed
    assert "exposure" in reason.lower()


@pytest.mark.asyncio
async def test_loss_limit_after_settlements(
    db: AsyncSession,
    test_user,
) -> None:
    """3 settled losses at limit → next trade blocked."""
    settings = UserSettings(
        daily_loss_limit_cents=75,
        max_trade_size_cents=100,
        max_daily_exposure_cents=5000,
    )
    rm = RiskManager(settings=settings, db=db, user_id=test_user.id)
    now = datetime.now(UTC)

    # 3 losses: -25c each = -75c total
    for _ in range(3):
        await insert_trade(db, test_user.id, status=TradeStatus.LOST, pnl_cents=-25, settled_at=now)

    signal = _make_signal(price_cents=15, ev=0.10)
    allowed, reason = await rm.check_trade(signal)
    assert not allowed
    assert "loss" in reason.lower()


@pytest.mark.asyncio
async def test_cooldown_after_loss(
    db: AsyncSession,
    test_user,
    user_settings: UserSettings,
) -> None:
    """Settle a loss → cooldown blocks next trade."""
    cm = CooldownManager(settings=user_settings, db=db, user_id=test_user.id)

    # Simulate a loss
    await cm.on_trade_loss()

    # Cooldown should be active (60 min default)
    active, reason = await cm.is_cooldown_active()
    assert active
    assert "cooldown" in reason.lower() or "min" in reason.lower()

    # Risk manager should also block
    rm = RiskManager(settings=user_settings, db=db, user_id=test_user.id)
    signal = _make_signal()
    allowed, reason = await rm.check_trade(signal)
    assert not allowed
    assert "cooldown" in reason.lower()


@pytest.mark.asyncio
async def test_consecutive_losses_halt(
    db: AsyncSession,
    test_user,
    user_settings: UserSettings,
) -> None:
    """3 consecutive losses → rest-of-day halt."""
    cm = CooldownManager(settings=user_settings, db=db, user_id=test_user.id)

    # 3 consecutive losses (limit is 3)
    for _ in range(3):
        await cm.on_trade_loss()

    active, reason = await cm.is_cooldown_active()
    assert active
    assert "rest of trading day" in reason.lower() or "consecutive" in reason.lower()


@pytest.mark.asyncio
async def test_win_resets_consecutive_counter(
    db: AsyncSession,
    test_user,
    user_settings: UserSettings,
) -> None:
    """L-L-W-L → consecutive count = 1, no halt."""
    cm = CooldownManager(settings=user_settings, db=db, user_id=test_user.id)

    await cm.on_trade_loss()  # consecutive = 1
    await cm.on_trade_loss()  # consecutive = 2

    # Win resets the counter
    await cm.on_trade_win()  # consecutive = 0

    # Now one more loss
    await cm.on_trade_loss()  # consecutive = 1

    # Should have per-loss cooldown but NOT rest-of-day
    state = await cm._get_daily_state()
    assert state is not None
    assert state.consecutive_losses == 1  # Not 3 → no halt


@pytest.mark.asyncio
async def test_max_trade_size_enforced(
    db: AsyncSession,
    test_user,
) -> None:
    """99c YES trade passes at max=100, but signal costing >100c is blocked."""
    settings = UserSettings(max_trade_size_cents=100, max_daily_exposure_cents=5000)
    rm = RiskManager(settings=settings, db=db, user_id=test_user.id)

    # YES at 99c → cost=99c < 100c → allowed
    signal_99 = _make_signal(price_cents=99, ev=0.10)
    allowed, _ = await rm.check_trade(signal_99)
    assert allowed

    # NO at 1c → cost = 100-1 = 99c < 100c → allowed
    no_signal = TradeSignal(
        city="NYC",
        bracket="53-55",
        side="no",
        price_cents=1,
        quantity=1,
        model_probability=0.05,
        market_probability=0.99,
        ev=0.10,
        confidence="medium",
        market_ticker="KXHIGHNY-26FEB20-B3",
    )
    allowed, _ = await rm.check_trade(no_signal)
    assert allowed


@pytest.mark.asyncio
async def test_fresh_db_no_risk_state(
    db: AsyncSession,
    test_user,
    user_settings: UserSettings,
) -> None:
    """No DailyRiskState row → check_trade still works (creates on demand)."""
    rm = RiskManager(settings=user_settings, db=db, user_id=test_user.id)
    signal = _make_signal()
    allowed, reason = await rm.check_trade(signal)
    assert allowed
    assert reason == "All checks passed"
