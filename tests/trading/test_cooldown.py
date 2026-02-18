"""Tests for backend.trading.cooldown -- CooldownManager per-loss and consecutive-loss logic.

Cooldown state is stored in DailyRiskState with:
- cooldown_until: DateTime when the current cooldown expires
- consecutive_losses: Running count of consecutive losses today

Two cooldown types:
1. Per-loss: pause for N minutes after each loss
2. Consecutive-loss: pause for rest of day after N consecutive losses
"""

from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from zoneinfo import ZoneInfo

import pytest

from backend.common.models import DailyRiskState
from backend.common.schemas import UserSettings
from backend.trading.cooldown import CooldownManager

ET = ZoneInfo("America/New_York")


def _make_cm(
    user_settings: UserSettings,
    state: DailyRiskState | None = None,
) -> CooldownManager:
    """Create a CooldownManager with a mocked DB session.

    Args:
        user_settings: Trading settings.
        state: The DailyRiskState the DB should return (None means no row).
    """
    mock_db = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = state
    mock_db.execute.return_value = mock_result
    return CooldownManager(settings=user_settings, db=mock_db, user_id="test-user")


class TestIsCooldownActive:
    """Tests for is_cooldown_active -- checking current cooldown status."""

    @pytest.mark.asyncio
    async def test_no_cooldown_when_no_state(self, user_settings: UserSettings) -> None:
        """No DailyRiskState row means no cooldown."""
        cm = _make_cm(user_settings, state=None)
        with patch("backend.trading.cooldown.CooldownManager._get_daily_state", return_value=None):
            is_active, reason = await cm.is_cooldown_active()
        assert is_active is False
        assert reason == ""

    @pytest.mark.asyncio
    async def test_no_cooldown_when_expired(self, user_settings: UserSettings) -> None:
        """cooldown_until in the past means cooldown has expired."""
        mock_state = MagicMock(spec=DailyRiskState)
        mock_state.cooldown_until = datetime.now(ET) - timedelta(minutes=10)
        mock_state.consecutive_losses = 1

        cm = _make_cm(user_settings, state=mock_state)
        with patch.object(cm, "_get_daily_state", return_value=mock_state):
            is_active, reason = await cm.is_cooldown_active()
        assert is_active is False

    @pytest.mark.asyncio
    async def test_per_loss_cooldown_active(self, user_settings: UserSettings) -> None:
        """cooldown_until in the future means per-loss cooldown is active."""
        future = datetime.now(ET) + timedelta(minutes=30)
        mock_state = MagicMock(spec=DailyRiskState)
        mock_state.cooldown_until = future
        mock_state.consecutive_losses = 1

        cm = _make_cm(user_settings, state=mock_state)
        with patch.object(cm, "_get_daily_state", return_value=mock_state):
            is_active, reason = await cm.is_cooldown_active()
        assert is_active is True
        assert "cooldown" in reason.lower() or "Per-loss" in reason


class TestOnTradeLoss:
    """Tests for on_trade_loss -- updating cooldown state after a loss."""

    @pytest.mark.asyncio
    async def test_on_trade_loss_sets_cooldown(self, user_settings: UserSettings) -> None:
        """After a loss, cooldown_until is set to now + cooldown_per_loss_minutes."""
        mock_state = MagicMock(spec=DailyRiskState)
        mock_state.cooldown_until = None
        mock_state.consecutive_losses = 0

        cm = _make_cm(user_settings, state=mock_state)
        with patch.object(cm, "_get_or_create_daily_state", return_value=mock_state):
            await cm.on_trade_loss()

        # cooldown_until should now be set (not None)
        assert mock_state.cooldown_until is not None

    @pytest.mark.asyncio
    async def test_on_trade_loss_increments_consecutive(self, user_settings: UserSettings) -> None:
        """consecutive_losses increases by 1 after a loss."""
        mock_state = MagicMock(spec=DailyRiskState)
        mock_state.cooldown_until = None
        mock_state.consecutive_losses = 1

        cm = _make_cm(user_settings, state=mock_state)
        with patch.object(cm, "_get_or_create_daily_state", return_value=mock_state):
            await cm.on_trade_loss()

        assert mock_state.consecutive_losses == 2

    @pytest.mark.asyncio
    async def test_consecutive_limit_triggers_rest_of_day(
        self, user_settings: UserSettings
    ) -> None:
        """When consecutive_losses >= limit, cooldown_until is set to end of day."""
        # consecutive_loss_limit = 3 (default). Set consecutive_losses to 2,
        # so after the loss it becomes 3 and triggers rest-of-day.
        mock_state = MagicMock(spec=DailyRiskState)
        mock_state.cooldown_until = None
        mock_state.consecutive_losses = 2

        cm = _make_cm(user_settings, state=mock_state)
        with patch.object(cm, "_get_or_create_daily_state", return_value=mock_state):
            await cm.on_trade_loss()

        assert mock_state.consecutive_losses == 3
        # cooldown_until should be near end-of-day (23:59:59 ET)
        assert mock_state.cooldown_until is not None
        if hasattr(mock_state.cooldown_until, "hour"):
            assert mock_state.cooldown_until.hour == 23
            assert mock_state.cooldown_until.minute == 59

    @pytest.mark.asyncio
    async def test_cooldown_disabled_when_zero_minutes(self, user_settings: UserSettings) -> None:
        """When cooldown_per_loss_minutes = 0, no per-loss cooldown is set."""
        settings = user_settings.model_copy(update={"cooldown_per_loss_minutes": 0})
        mock_state = MagicMock(spec=DailyRiskState)
        mock_state.cooldown_until = None
        mock_state.consecutive_losses = 0

        cm = _make_cm(settings, state=mock_state)
        with patch.object(cm, "_get_or_create_daily_state", return_value=mock_state):
            await cm.on_trade_loss()

        # consecutive_losses still increments
        assert mock_state.consecutive_losses == 1
        # But since we are below the consecutive limit (3) and per-loss is disabled,
        # cooldown_until should remain None (no per-loss cooldown was set).
        # NOTE: The code sets cooldown_until only if cooldown_per_loss_minutes > 0.
        # After incrementing, consecutive_losses = 1 < 3 so no rest-of-day either.
        assert mock_state.cooldown_until is None

    @pytest.mark.asyncio
    async def test_consecutive_limit_disabled_when_zero(self, user_settings: UserSettings) -> None:
        """When consecutive_loss_limit = 0, rest-of-day is never triggered."""
        settings = user_settings.model_copy(
            update={"consecutive_loss_limit": 0, "cooldown_per_loss_minutes": 0}
        )
        mock_state = MagicMock(spec=DailyRiskState)
        mock_state.cooldown_until = None
        mock_state.consecutive_losses = 10  # Way past any limit

        cm = _make_cm(settings, state=mock_state)
        with patch.object(cm, "_get_or_create_daily_state", return_value=mock_state):
            await cm.on_trade_loss()

        # consecutive_losses increments
        assert mock_state.consecutive_losses == 11
        # But rest-of-day NOT triggered because limit is 0 (disabled)
        assert mock_state.cooldown_until is None


class TestOnTradeWin:
    """Tests for on_trade_win -- resetting consecutive loss counter."""

    @pytest.mark.asyncio
    async def test_on_trade_win_resets_consecutive(self, user_settings: UserSettings) -> None:
        """After a win, consecutive_losses resets to 0."""
        mock_state = MagicMock(spec=DailyRiskState)
        mock_state.cooldown_until = None
        mock_state.consecutive_losses = 2

        cm = _make_cm(user_settings, state=mock_state)
        with patch.object(cm, "_get_or_create_daily_state", return_value=mock_state):
            await cm.on_trade_win()

        assert mock_state.consecutive_losses == 0
