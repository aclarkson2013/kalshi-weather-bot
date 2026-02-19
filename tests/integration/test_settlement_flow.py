"""Integration tests: Settlement and P&L calculation.

Tests settle_trade() determining wins/losses, calculating P&L including
fees, and generating post-mortem narratives.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from backend.common.models import (
    CityEnum,
    Settlement,
    Trade,
    TradeStatus,
    WeatherForecast,
)
from backend.trading.ev_calculator import estimate_fees
from backend.trading.postmortem import settle_trade


def _make_trade(
    user_id: str,
    *,
    bracket_label: str = "53-55",
    side: str = "yes",
    price_cents: int = 22,
    quantity: int = 1,
    trade_date: datetime | None = None,
) -> Trade:
    """Create a Trade ORM object (not yet added to DB)."""
    return Trade(
        id=str(uuid4()),
        user_id=user_id,
        kalshi_order_id=f"order-{uuid4().hex[:8]}",
        city=CityEnum.NYC,
        trade_date=trade_date or datetime.now(UTC),
        market_ticker="KXHIGHNY-26FEB20-B3",
        bracket_label=bracket_label,
        side=side,
        price_cents=price_cents,
        quantity=quantity,
        model_probability=0.30,
        market_probability=0.22,
        ev_at_entry=0.05,
        confidence="medium",
        status=TradeStatus.OPEN,
    )


def _make_settlement(
    actual_high_f: float = 54.0,
    settlement_date: datetime | None = None,
) -> Settlement:
    """Create a Settlement ORM object."""
    return Settlement(
        city=CityEnum.NYC,
        settlement_date=settlement_date or datetime.now(UTC),
        actual_high_f=actual_high_f,
        source="NWS_CLI",
    )


@pytest.mark.asyncio
async def test_winning_yes_trade(db: AsyncSession, test_user) -> None:
    """YES on 53-55, actual=54F → WON, P&L = payout - cost - fees."""
    trade = _make_trade(test_user.id, bracket_label="53-55", side="yes", price_cents=22)
    db.add(trade)

    settlement = _make_settlement(actual_high_f=54.0)
    db.add(settlement)
    await db.flush()

    await settle_trade(trade, settlement, db)

    assert trade.status == TradeStatus.WON
    # P&L: payout(100) - cost(22) - fees
    fees = estimate_fees(22, "yes")  # max(1, int((100-22) * 0.15)) = 11
    expected_pnl = 100 - 22 - fees
    assert trade.pnl_cents == expected_pnl
    assert trade.fees_cents == fees
    assert trade.settlement_temp_f == 54.0


@pytest.mark.asyncio
async def test_losing_yes_trade(db: AsyncSession, test_user) -> None:
    """YES on 53-55, actual=57F (outside bracket) → LOST, P&L = -cost."""
    trade = _make_trade(test_user.id, bracket_label="53-55", side="yes", price_cents=22)
    db.add(trade)

    settlement = _make_settlement(actual_high_f=57.0)
    db.add(settlement)
    await db.flush()

    await settle_trade(trade, settlement, db)

    assert trade.status == TradeStatus.LOST
    assert trade.pnl_cents == -22  # Lost the cost
    assert trade.fees_cents == 0


@pytest.mark.asyncio
async def test_winning_no_trade(db: AsyncSession, test_user) -> None:
    """NO on 53-55, actual=57F (outside bracket) → WON."""
    trade = _make_trade(test_user.id, bracket_label="53-55", side="no", price_cents=22)
    db.add(trade)

    settlement = _make_settlement(actual_high_f=57.0)
    db.add(settlement)
    await db.flush()

    await settle_trade(trade, settlement, db)

    assert trade.status == TradeStatus.WON
    # NO cost = 100 - 22 = 78c.  Payout = 100c.  Profit = 22c.
    fees = estimate_fees(22, "no")  # max(1, int(22 * 0.15)) = 3
    expected_pnl = 100 - (100 - 22) - fees  # 100 - 78 - 3 = 19
    assert trade.pnl_cents == expected_pnl
    assert trade.fees_cents == fees


@pytest.mark.asyncio
async def test_losing_no_trade(db: AsyncSession, test_user) -> None:
    """NO on 53-55, actual=54F (bracket hit) → LOST."""
    trade = _make_trade(test_user.id, bracket_label="53-55", side="no", price_cents=22)
    db.add(trade)

    settlement = _make_settlement(actual_high_f=54.0)
    db.add(settlement)
    await db.flush()

    await settle_trade(trade, settlement, db)

    assert trade.status == TradeStatus.LOST
    # NO cost = 100 - 22 = 78c.  Lost the cost.
    assert trade.pnl_cents == -(100 - 22)
    assert trade.fees_cents == 0


@pytest.mark.asyncio
async def test_generates_narrative(db: AsyncSession, test_user) -> None:
    """Settlement produces a non-empty postmortem narrative."""
    trade = _make_trade(test_user.id, bracket_label="53-55", side="yes", price_cents=22)
    db.add(trade)

    settlement = _make_settlement(actual_high_f=54.0)
    db.add(settlement)
    await db.flush()

    await settle_trade(trade, settlement, db)

    assert trade.postmortem_narrative is not None
    assert len(trade.postmortem_narrative) > 0
    assert "54" in trade.postmortem_narrative  # actual temp mentioned


@pytest.mark.asyncio
async def test_edge_bracket_bottom(db: AsyncSession, test_user) -> None:
    """Bottom bracket '<=51F' tested correctly with actual=50F → YES wins."""
    trade = _make_trade(test_user.id, bracket_label="<=51F", side="yes", price_cents=10)
    db.add(trade)

    settlement = _make_settlement(actual_high_f=50.0)
    db.add(settlement)
    await db.flush()

    await settle_trade(trade, settlement, db)
    assert trade.status == TradeStatus.WON


@pytest.mark.asyncio
async def test_narrative_includes_forecasts(db: AsyncSession, test_user) -> None:
    """Insert forecasts into DB → narrative mentions forecast accuracy."""
    now = datetime.now(UTC)
    trade = _make_trade(test_user.id, bracket_label="53-55", side="yes", price_cents=22)
    trade.trade_date = now
    db.add(trade)

    settlement = _make_settlement(actual_high_f=54.0, settlement_date=now)
    db.add(settlement)

    # Add weather forecasts that settle_trade can find
    for source, forecast_temp in [("NWS", 55.0), ("Open-Meteo:GFS", 53.0)]:
        fc = WeatherForecast(
            city=CityEnum.NYC,
            forecast_date=now,
            source=source,
            forecast_high_f=forecast_temp,
        )
        db.add(fc)

    await db.flush()

    await settle_trade(trade, settlement, db)

    assert trade.postmortem_narrative is not None
    assert "Forecast accuracy" in trade.postmortem_narrative
    assert "NWS" in trade.postmortem_narrative
