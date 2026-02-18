"""Tests for backend.trading.risk_manager -- RiskManager risk checks.

All monetary values are in CENTS (integers).
Risk checks run in order: cooldown, trade size, exposure, loss, EV threshold.
"""

from __future__ import annotations

from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.common.schemas import TradeSignal, UserSettings
from backend.trading.risk_manager import RiskManager, get_trading_day, is_new_trading_day


@pytest.fixture
def _no_cooldown():
    """Patch CooldownManager so cooldown is always inactive."""
    with patch("backend.trading.cooldown.CooldownManager") as mock_cm_cls:
        mock_cm = AsyncMock()
        mock_cm.is_cooldown_active.return_value = (False, "")
        mock_cm_cls.return_value = mock_cm
        yield mock_cm_cls


@pytest.fixture
def _active_cooldown():
    """Patch CooldownManager so cooldown is active."""
    with patch("backend.trading.cooldown.CooldownManager") as mock_cm_cls:
        mock_cm = AsyncMock()
        mock_cm.is_cooldown_active.return_value = (True, "Per-loss cooldown: 45 min remaining")
        mock_cm_cls.return_value = mock_cm
        yield mock_cm_cls


def _make_risk_manager(
    user_settings: UserSettings,
    daily_pnl_cents: int = 0,
    open_exposure_cents: int = 0,
) -> RiskManager:
    """Create a RiskManager with controlled DB return values.

    The mock DB execute returns different values depending on the query.
    We set up scalar() to return controlled values for pnl and exposure queries.
    """
    mock_db = AsyncMock()

    # We need separate return values for the two DB calls (pnl and exposure).
    # The risk manager calls execute twice -- first for pnl, then for exposure.
    # But check_trade calls get_open_exposure_cents and get_daily_pnl_cents
    # separately, each calling db.execute.
    mock_result_exposure = MagicMock()
    mock_result_exposure.scalar.return_value = open_exposure_cents

    mock_result_pnl = MagicMock()
    mock_result_pnl.scalar.return_value = daily_pnl_cents

    # Use side_effect to return different results for sequential calls.
    # check_trade order: cooldown (patched), then exposure, then pnl.
    mock_db.execute.side_effect = [mock_result_exposure, mock_result_pnl]

    return RiskManager(settings=user_settings, db=mock_db, user_id="test-user")


class TestCheckTrade:
    """Test the full risk check pipeline."""

    @pytest.mark.asyncio
    @pytest.mark.usefixtures("_no_cooldown")
    async def test_trade_passes_all_checks(
        self, user_settings: UserSettings, sample_signal: TradeSignal
    ) -> None:
        """A signal within all limits passes."""
        rm = _make_risk_manager(user_settings, daily_pnl_cents=0, open_exposure_cents=0)
        allowed, reason = await rm.check_trade(sample_signal)
        assert allowed is True
        assert reason == "All checks passed"

    @pytest.mark.asyncio
    @pytest.mark.usefixtures("_no_cooldown")
    async def test_blocked_by_trade_size(self, user_settings: UserSettings) -> None:
        """Trade cost exceeding max_trade_size_cents is blocked.
        max_trade_size_cents = 100. A YES at 101c costs 101c > 100c.
        """
        # Use a NO side to make cost = 100 - price. price=1 -> cost=99. OK.
        # Use YES side with price > max
        # But price_cents must be 1-99 for TradeSignal. So we lower the limit.
        settings = user_settings.model_copy(update={"max_trade_size_cents": 20})
        signal = TradeSignal(
            city="NYC",
            bracket="55-56F",
            side="yes",
            price_cents=22,  # cost = 22c > 20c limit
            quantity=1,
            model_probability=0.40,
            market_probability=0.22,
            ev=0.07,
            confidence="medium",
            market_ticker="KXHIGHNY-26FEB18-B3",
            reasoning="test",
        )
        rm = _make_risk_manager(settings)
        allowed, reason = await rm.check_trade(signal)
        assert allowed is False
        assert "max" in reason.lower() or "exceeds" in reason.lower()

    @pytest.mark.asyncio
    @pytest.mark.usefixtures("_no_cooldown")
    async def test_blocked_at_exact_trade_size_limit(self, user_settings: UserSettings) -> None:
        """Trade cost exactly 1 cent over the limit is blocked.
        max = 100c. YES at 99c costs 99c (allowed). Build a NO side to trigger.
        """
        # max_trade_size = 50, NO side: cost = 100 - price.
        # price = 49 -> cost = 51 > 50 -> blocked
        settings = user_settings.model_copy(update={"max_trade_size_cents": 50})
        signal = TradeSignal(
            city="NYC",
            bracket="55-56F",
            side="no",
            price_cents=49,  # NO cost = 100 - 49 = 51c > 50c
            quantity=1,
            model_probability=0.40,
            market_probability=0.49,
            ev=0.06,
            confidence="medium",
            market_ticker="KXHIGHNY-26FEB18-B3",
            reasoning="test",
        )
        rm = _make_risk_manager(settings)
        allowed, reason = await rm.check_trade(signal)
        assert allowed is False

    @pytest.mark.asyncio
    @pytest.mark.usefixtures("_no_cooldown")
    async def test_allowed_at_exact_trade_size(self, user_settings: UserSettings) -> None:
        """Trade cost exactly at the limit is allowed.
        max = 50, YES at 50c costs 50c = 50c limit -> allowed.
        """
        settings = user_settings.model_copy(update={"max_trade_size_cents": 50})
        signal = TradeSignal(
            city="NYC",
            bracket="55-56F",
            side="yes",
            price_cents=50,  # YES cost = 50c = 50c limit
            quantity=1,
            model_probability=0.70,
            market_probability=0.50,
            ev=0.07,
            confidence="medium",
            market_ticker="KXHIGHNY-26FEB18-B3",
            reasoning="test",
        )
        rm = _make_risk_manager(settings, daily_pnl_cents=0, open_exposure_cents=0)
        allowed, reason = await rm.check_trade(signal)
        assert allowed is True

    @pytest.mark.asyncio
    @pytest.mark.usefixtures("_no_cooldown")
    async def test_blocked_by_daily_exposure(
        self, user_settings: UserSettings, sample_signal: TradeSignal
    ) -> None:
        """When current_exposure + cost > max_daily_exposure -> blocked."""
        # max_daily_exposure = 2500c. Open exposure = 2490c, trade cost = 22c.
        # 2490 + 22 = 2512 > 2500 -> blocked
        rm = _make_risk_manager(user_settings, open_exposure_cents=2490)
        allowed, reason = await rm.check_trade(sample_signal)
        assert allowed is False
        assert "exposure" in reason.lower()

    @pytest.mark.asyncio
    @pytest.mark.usefixtures("_no_cooldown")
    async def test_blocked_by_daily_loss(
        self, user_settings: UserSettings, sample_signal: TradeSignal
    ) -> None:
        """When daily PnL <= -daily_loss_limit -> blocked."""
        # daily_loss_limit = 1000c. PnL = -1000c -> blocked.
        rm = _make_risk_manager(user_settings, daily_pnl_cents=-1000, open_exposure_cents=0)
        allowed, reason = await rm.check_trade(sample_signal)
        assert allowed is False
        assert "loss" in reason.lower()

    @pytest.mark.asyncio
    @pytest.mark.usefixtures("_no_cooldown")
    async def test_blocked_by_low_ev(self, user_settings: UserSettings) -> None:
        """Signal EV below min_ev_threshold is blocked."""
        signal = TradeSignal(
            city="NYC",
            bracket="55-56F",
            side="yes",
            price_cents=22,
            quantity=1,
            model_probability=0.30,
            market_probability=0.22,
            ev=0.01,  # below 0.05 threshold
            confidence="medium",
            market_ticker="KXHIGHNY-26FEB18-B3",
            reasoning="test",
        )
        rm = _make_risk_manager(user_settings, daily_pnl_cents=0, open_exposure_cents=0)
        allowed, reason = await rm.check_trade(signal)
        assert allowed is False
        assert "EV" in reason or "threshold" in reason.lower()

    @pytest.mark.asyncio
    async def test_blocked_by_cooldown(
        self,
        user_settings: UserSettings,
        sample_signal: TradeSignal,
        _active_cooldown: None,
    ) -> None:
        """When cooldown is active, trade is blocked."""
        rm = _make_risk_manager(user_settings)
        allowed, reason = await rm.check_trade(sample_signal)
        assert allowed is False
        assert "cooldown" in reason.lower()

    @pytest.mark.asyncio
    @pytest.mark.usefixtures("_no_cooldown")
    async def test_no_side_cost_calculation(self, user_settings: UserSettings) -> None:
        """NO side cost = 100 - price_cents."""
        # NO at price=20 -> cost = 80c.
        # max_trade_size = 100c, so 80c < 100c -> allowed if EV is fine.
        signal = TradeSignal(
            city="NYC",
            bracket="55-56F",
            side="no",
            price_cents=20,  # NO cost = 80c
            quantity=1,
            model_probability=0.10,
            market_probability=0.20,
            ev=0.06,
            confidence="medium",
            market_ticker="KXHIGHNY-26FEB18-B3",
            reasoning="test",
        )
        rm = _make_risk_manager(user_settings, daily_pnl_cents=0, open_exposure_cents=0)
        allowed, reason = await rm.check_trade(signal)
        assert allowed is True


class TestGetTradingDay:
    """Test the get_trading_day helper function."""

    def test_get_trading_day_returns_date(self) -> None:
        """get_trading_day returns a date object."""
        result = get_trading_day()
        assert isinstance(result, date)


class TestIsNewTradingDay:
    """Test the is_new_trading_day helper function."""

    def test_is_new_trading_day(self) -> None:
        """Today > yesterday returns True."""
        yesterday = date(2020, 1, 1)
        assert is_new_trading_day(yesterday) is True

    def test_same_day_returns_false(self) -> None:
        """Same day returns False."""
        today = get_trading_day()
        assert is_new_trading_day(today) is False
