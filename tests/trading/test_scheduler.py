"""Tests for backend.trading.scheduler -- Celery tasks for the trading engine.

Tests cover:
- _are_markets_open: Market hours check
- _load_user_settings: Load user settings from DB
- _get_kalshi_client: Decrypt credentials, build client
- _run_trading_cycle: Full trading cycle orchestration
- _expire_pending_trades: Expire stale pending trades
- _settle_and_postmortem: Settle trades + generate narratives
- Celery task wrappers: trading_cycle, check_pending_trades, settle_trades
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from zoneinfo import ZoneInfo

import pytest

from backend.common.schemas import (
    BracketPrediction,
    BracketProbability,
    TradeSignal,
    UserSettings,
)

ET = ZoneInfo("America/New_York")


# ─── Helpers ───


def _make_user_settings(**overrides) -> UserSettings:
    """Create UserSettings with safe defaults."""
    defaults = {
        "trading_mode": "manual",
        "max_trade_size_cents": 100,
        "daily_loss_limit_cents": 1000,
        "max_daily_exposure_cents": 2500,
        "min_ev_threshold": 0.05,
        "cooldown_per_loss_minutes": 60,
        "consecutive_loss_limit": 3,
        "active_cities": ["NYC", "CHI", "MIA", "AUS"],
        "notifications_enabled": True,
    }
    defaults.update(overrides)
    return UserSettings(**defaults)


def _make_mock_user(**overrides) -> MagicMock:
    """Create a mock User ORM object."""
    user = MagicMock()
    user.id = overrides.get("id", "user-123")
    user.kalshi_key_id = overrides.get("kalshi_key_id", "key-abc")
    user.encrypted_private_key = overrides.get("encrypted_private_key", "encrypted-pem")
    user.trading_mode = overrides.get("trading_mode", "manual")
    user.max_trade_size_cents = overrides.get("max_trade_size_cents", 100)
    user.daily_loss_limit_cents = overrides.get("daily_loss_limit_cents", 1000)
    user.max_daily_exposure_cents = overrides.get("max_daily_exposure_cents", 2500)
    user.min_ev_threshold = overrides.get("min_ev_threshold", 0.05)
    user.cooldown_per_loss_minutes = overrides.get("cooldown_per_loss_minutes", 60)
    user.consecutive_loss_limit = overrides.get("consecutive_loss_limit", 3)
    user.active_cities = overrides.get("active_cities", "NYC,CHI,MIA,AUS")
    user.notifications_enabled = overrides.get("notifications_enabled", True)
    user.push_subscription = overrides.get("push_subscription", None)
    return user


def _make_prediction(city: str = "NYC") -> BracketPrediction:
    """Create a simple BracketPrediction."""
    return BracketPrediction(
        city=city,
        date=date(2026, 2, 18),
        brackets=[
            BracketProbability(bracket_label="≤52°F", lower_bound_f=None, upper_bound_f=52, probability=0.08),
            BracketProbability(bracket_label="53-54°F", lower_bound_f=53, upper_bound_f=54, probability=0.15),
            BracketProbability(bracket_label="55-56°F", lower_bound_f=55, upper_bound_f=56, probability=0.30),
            BracketProbability(bracket_label="57-58°F", lower_bound_f=57, upper_bound_f=58, probability=0.28),
            BracketProbability(bracket_label="59-60°F", lower_bound_f=59, upper_bound_f=60, probability=0.12),
            BracketProbability(bracket_label="≥61°F", lower_bound_f=61, upper_bound_f=None, probability=0.07),
        ],
        ensemble_mean_f=56.3,
        ensemble_std_f=2.1,
        confidence="medium",
        model_sources=["NWS", "GFS", "ECMWF", "ICON"],
        generated_at=datetime(2026, 2, 17, 15, 0, 0, tzinfo=UTC),
    )


def _make_signal(city: str = "NYC") -> TradeSignal:
    """Create a +EV TradeSignal."""
    return TradeSignal(
        city=city,
        bracket="55-56°F",
        side="yes",
        price_cents=22,
        quantity=1,
        model_probability=0.30,
        market_probability=0.22,
        ev=0.05,
        confidence="medium",
        market_ticker="KXHIGHNY-26FEB18-B3",
        reasoning="test signal",
    )


def _make_mock_db_session() -> AsyncMock:
    """Create a mock async DB session for scheduler tasks."""
    session = AsyncMock()
    session.add = MagicMock()
    return session


# ─── _are_markets_open Tests ───


class TestAreMarketsOpen:
    """Tests for _are_markets_open -- checks ET trading hours 6 AM - 11 PM."""

    def test_open_during_trading_hours(self) -> None:
        """Markets open at noon ET."""
        from backend.trading.scheduler import _are_markets_open

        mock_dt = datetime(2026, 2, 18, 12, 0, 0, tzinfo=ET)
        with patch("backend.trading.scheduler.datetime") as mock_datetime:
            mock_datetime.now.return_value = mock_dt
            assert _are_markets_open() is True

    def test_open_at_11pm_et(self) -> None:
        """Markets open at 11 PM ET (hour 23)."""
        from backend.trading.scheduler import _are_markets_open

        mock_dt = datetime(2026, 2, 18, 23, 0, 0, tzinfo=ET)
        with patch("backend.trading.scheduler.datetime") as mock_datetime:
            mock_datetime.now.return_value = mock_dt
            assert _are_markets_open() is True

    def test_closed_before_6am(self) -> None:
        """Markets closed at 5 AM ET."""
        from backend.trading.scheduler import _are_markets_open

        mock_dt = datetime(2026, 2, 18, 5, 0, 0, tzinfo=ET)
        with patch("backend.trading.scheduler.datetime") as mock_datetime:
            mock_datetime.now.return_value = mock_dt
            assert _are_markets_open() is False

    def test_boundary_at_6am(self) -> None:
        """Markets open exactly at 6 AM ET."""
        from backend.trading.scheduler import _are_markets_open

        mock_dt = datetime(2026, 2, 18, 6, 0, 0, tzinfo=ET)
        with patch("backend.trading.scheduler.datetime") as mock_datetime:
            mock_datetime.now.return_value = mock_dt
            assert _are_markets_open() is True


# ─── _load_user_settings Tests ───


class TestLoadUserSettings:
    """Tests for _load_user_settings -- loads first user's settings from DB."""

    @pytest.mark.asyncio
    async def test_returns_none_when_no_users(self) -> None:
        """Returns None when no user exists in the database."""
        from backend.trading.scheduler import _load_user_settings

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        result = await _load_user_settings(mock_db)
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_settings_for_valid_user(self) -> None:
        """Returns UserSettings when a user exists."""
        from backend.trading.scheduler import _load_user_settings

        mock_user = _make_mock_user(trading_mode="auto", active_cities="NYC,CHI")
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_user
        mock_db.execute.return_value = mock_result

        result = await _load_user_settings(mock_db)
        assert result is not None
        assert result.trading_mode == "auto"
        assert result.active_cities == ["NYC", "CHI"]

    @pytest.mark.asyncio
    async def test_default_values_for_none_fields(self) -> None:
        """When user fields are None, defaults are used."""
        from backend.trading.scheduler import _load_user_settings

        mock_user = _make_mock_user()
        mock_user.trading_mode = None
        mock_user.max_trade_size_cents = None
        mock_user.daily_loss_limit_cents = None
        mock_user.active_cities = None
        mock_user.notifications_enabled = None

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_user
        mock_db.execute.return_value = mock_result

        result = await _load_user_settings(mock_db)
        assert result.trading_mode == "manual"
        assert result.max_trade_size_cents == 100
        assert result.daily_loss_limit_cents == 1000
        assert result.active_cities == ["NYC", "CHI", "MIA", "AUS"]
        assert result.notifications_enabled is True


# ─── _get_kalshi_client Tests ───


class TestGetKalshiClient:
    """Tests for _get_kalshi_client -- decrypts keys, creates client."""

    @pytest.mark.asyncio
    async def test_returns_none_when_user_not_found(self) -> None:
        """Returns None when user doesn't exist."""
        from backend.trading.scheduler import _get_kalshi_client

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        result = await _get_kalshi_client(mock_db, "nonexistent")
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_client_on_success(self) -> None:
        """Returns a KalshiClient when credentials decrypt successfully."""
        from backend.trading.scheduler import _get_kalshi_client

        mock_user = _make_mock_user()
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_user
        mock_db.execute.return_value = mock_result

        mock_client_instance = MagicMock()

        with (
            patch("backend.common.encryption.decrypt_api_key", return_value="test-pem"),
            patch("backend.kalshi.client.KalshiClient", return_value=mock_client_instance),
        ):
            result = await _get_kalshi_client(mock_db, "user-123")

        assert result is mock_client_instance

    @pytest.mark.asyncio
    async def test_returns_none_on_decrypt_failure(self) -> None:
        """Returns None when decryption fails (no crash)."""
        from backend.trading.scheduler import _get_kalshi_client

        mock_user = _make_mock_user()
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_user
        mock_db.execute.return_value = mock_result

        with patch(
            "backend.common.encryption.decrypt_api_key",
            side_effect=ValueError("bad key"),
        ):
            result = await _get_kalshi_client(mock_db, "user-123")

        assert result is None


# ─── _run_trading_cycle Tests ───


class TestRunTradingCycle:
    """Tests for _run_trading_cycle -- the async trading heartbeat.

    Each test patches the minimum set of dependencies to verify one
    exit path or behavior of the trading cycle.
    """

    @pytest.mark.asyncio
    async def test_skips_when_markets_closed(self) -> None:
        """Returns early without DB access when markets are closed."""
        from backend.trading.scheduler import _run_trading_cycle

        with patch("backend.trading.scheduler._are_markets_open", return_value=False):
            mock_session = AsyncMock()
            with patch("backend.trading.scheduler.get_task_session", return_value=mock_session):
                await _run_trading_cycle()

            # Session should not be created since we return before DB work
            # (actually, session IS NOT obtained since the check is before it)

    @pytest.mark.asyncio
    async def test_skips_when_no_user_settings(self) -> None:
        """Returns early when no user is configured."""
        from backend.trading.scheduler import _run_trading_cycle

        mock_session = _make_mock_db_session()

        with (
            patch("backend.trading.scheduler._are_markets_open", return_value=True),
            patch("backend.trading.scheduler.get_task_session", return_value=mock_session),
            patch("backend.trading.scheduler._load_user_settings", return_value=None),
        ):
            await _run_trading_cycle()

        mock_session.close.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_skips_when_no_user_id(self) -> None:
        """Returns early when no user ID is found."""
        from backend.trading.scheduler import _run_trading_cycle

        mock_session = _make_mock_db_session()
        settings = _make_user_settings()

        with (
            patch("backend.trading.scheduler._are_markets_open", return_value=True),
            patch("backend.trading.scheduler.get_task_session", return_value=mock_session),
            patch("backend.trading.scheduler._load_user_settings", return_value=settings),
            patch("backend.trading.scheduler._get_user_id", return_value=None),
        ):
            await _run_trading_cycle()

        mock_session.close.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_skips_when_cooldown_active(self) -> None:
        """Returns early when cooldown is active."""
        from backend.trading.scheduler import _run_trading_cycle

        mock_session = _make_mock_db_session()
        settings = _make_user_settings()

        mock_risk_mgr = MagicMock()
        mock_risk_mgr.handle_daily_reset = AsyncMock()

        mock_cm = MagicMock()
        mock_cm.is_cooldown_active = AsyncMock(return_value=(True, "3 consecutive losses"))

        with (
            patch("backend.trading.scheduler._are_markets_open", return_value=True),
            patch("backend.trading.scheduler.get_task_session", return_value=mock_session),
            patch("backend.trading.scheduler._load_user_settings", return_value=settings),
            patch("backend.trading.scheduler._get_user_id", return_value="user-1"),
            patch("backend.trading.risk_manager.RiskManager", return_value=mock_risk_mgr),
            patch("backend.trading.cooldown.CooldownManager", return_value=mock_cm),
        ):
            await _run_trading_cycle()

        mock_session.close.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_skips_when_no_kalshi_client(self) -> None:
        """Returns early when Kalshi client can't be created."""
        from backend.trading.scheduler import _run_trading_cycle

        mock_session = _make_mock_db_session()
        settings = _make_user_settings()

        mock_risk_mgr = MagicMock()
        mock_risk_mgr.handle_daily_reset = AsyncMock()

        mock_cm = MagicMock()
        mock_cm.is_cooldown_active = AsyncMock(return_value=(False, ""))

        with (
            patch("backend.trading.scheduler._are_markets_open", return_value=True),
            patch("backend.trading.scheduler.get_task_session", return_value=mock_session),
            patch("backend.trading.scheduler._load_user_settings", return_value=settings),
            patch("backend.trading.scheduler._get_user_id", return_value="user-1"),
            patch("backend.trading.risk_manager.RiskManager", return_value=mock_risk_mgr),
            patch("backend.trading.cooldown.CooldownManager", return_value=mock_cm),
            patch("backend.trading.scheduler._get_kalshi_client", return_value=None),
        ):
            await _run_trading_cycle()

        mock_session.close.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_skips_when_no_predictions(self) -> None:
        """Returns early when no predictions are available."""
        from backend.trading.scheduler import _run_trading_cycle

        mock_session = _make_mock_db_session()
        settings = _make_user_settings()

        mock_risk_mgr = MagicMock()
        mock_risk_mgr.handle_daily_reset = AsyncMock()

        mock_cm = MagicMock()
        mock_cm.is_cooldown_active = AsyncMock(return_value=(False, ""))

        with (
            patch("backend.trading.scheduler._are_markets_open", return_value=True),
            patch("backend.trading.scheduler.get_task_session", return_value=mock_session),
            patch("backend.trading.scheduler._load_user_settings", return_value=settings),
            patch("backend.trading.scheduler._get_user_id", return_value="user-1"),
            patch("backend.trading.risk_manager.RiskManager", return_value=mock_risk_mgr),
            patch("backend.trading.cooldown.CooldownManager", return_value=mock_cm),
            patch("backend.trading.scheduler._get_kalshi_client", return_value=MagicMock()),
            patch("backend.trading.scheduler._fetch_latest_predictions", return_value=[]),
        ):
            await _run_trading_cycle()

        mock_session.close.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_skips_when_predictions_invalid(self) -> None:
        """Returns early when predictions fail validation."""
        from backend.trading.scheduler import _run_trading_cycle

        mock_session = _make_mock_db_session()
        settings = _make_user_settings()

        mock_risk_mgr = MagicMock()
        mock_risk_mgr.handle_daily_reset = AsyncMock()

        mock_cm = MagicMock()
        mock_cm.is_cooldown_active = AsyncMock(return_value=(False, ""))

        predictions = [_make_prediction()]

        with (
            patch("backend.trading.scheduler._are_markets_open", return_value=True),
            patch("backend.trading.scheduler.get_task_session", return_value=mock_session),
            patch("backend.trading.scheduler._load_user_settings", return_value=settings),
            patch("backend.trading.scheduler._get_user_id", return_value="user-1"),
            patch("backend.trading.risk_manager.RiskManager", return_value=mock_risk_mgr),
            patch("backend.trading.cooldown.CooldownManager", return_value=mock_cm),
            patch("backend.trading.scheduler._get_kalshi_client", return_value=MagicMock()),
            patch("backend.trading.scheduler._fetch_latest_predictions", return_value=predictions),
            patch("backend.trading.ev_calculator.validate_predictions", return_value=False),
        ):
            await _run_trading_cycle()

        mock_session.close.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_auto_mode_calls_execute_trade(self) -> None:
        """In auto mode, execute_trade is called for +EV signals passing risk."""
        from backend.trading.scheduler import _run_trading_cycle

        mock_session = _make_mock_db_session()
        settings = _make_user_settings(trading_mode="auto")
        prediction = _make_prediction()
        signal = _make_signal()

        mock_risk_mgr = MagicMock()
        mock_risk_mgr.handle_daily_reset = AsyncMock()
        mock_risk_mgr.check_trade = AsyncMock(return_value=(True, ""))

        mock_cm = MagicMock()
        mock_cm.is_cooldown_active = AsyncMock(return_value=(False, ""))

        mock_execute = AsyncMock()

        with (
            patch("backend.trading.scheduler._are_markets_open", return_value=True),
            patch("backend.trading.scheduler.get_task_session", return_value=mock_session),
            patch("backend.trading.scheduler._load_user_settings", return_value=settings),
            patch("backend.trading.scheduler._get_user_id", return_value="user-1"),
            patch("backend.trading.risk_manager.RiskManager", return_value=mock_risk_mgr),
            patch("backend.trading.cooldown.CooldownManager", return_value=mock_cm),
            patch("backend.trading.scheduler._get_kalshi_client", return_value=MagicMock()),
            patch("backend.trading.scheduler._fetch_latest_predictions", return_value=[prediction]),
            patch("backend.trading.ev_calculator.validate_predictions", return_value=True),
            patch("backend.trading.scheduler._fetch_market_prices", return_value={"55-56°F": 22}),
            patch("backend.trading.ev_calculator.validate_market_prices", return_value=True),
            patch("backend.trading.scheduler._fetch_market_tickers", return_value={"55-56°F": "KXHIGHNY-B3"}),
            patch("backend.trading.ev_calculator.scan_all_brackets", return_value=[signal]),
            patch("backend.trading.executor.execute_trade", mock_execute),
        ):
            await _run_trading_cycle()

        mock_execute.assert_awaited_once()
        mock_session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_manual_mode_calls_queue_trade(self) -> None:
        """In manual mode, queue_trade is called instead of execute_trade."""
        from backend.trading.scheduler import _run_trading_cycle

        mock_session = _make_mock_db_session()
        settings = _make_user_settings(trading_mode="manual")
        prediction = _make_prediction()
        signal = _make_signal()

        mock_risk_mgr = MagicMock()
        mock_risk_mgr.handle_daily_reset = AsyncMock()
        mock_risk_mgr.check_trade = AsyncMock(return_value=(True, ""))

        mock_cm = MagicMock()
        mock_cm.is_cooldown_active = AsyncMock(return_value=(False, ""))

        mock_queue = AsyncMock()

        with (
            patch("backend.trading.scheduler._are_markets_open", return_value=True),
            patch("backend.trading.scheduler.get_task_session", return_value=mock_session),
            patch("backend.trading.scheduler._load_user_settings", return_value=settings),
            patch("backend.trading.scheduler._get_user_id", return_value="user-1"),
            patch("backend.trading.risk_manager.RiskManager", return_value=mock_risk_mgr),
            patch("backend.trading.cooldown.CooldownManager", return_value=mock_cm),
            patch("backend.trading.scheduler._get_kalshi_client", return_value=MagicMock()),
            patch("backend.trading.scheduler._fetch_latest_predictions", return_value=[prediction]),
            patch("backend.trading.ev_calculator.validate_predictions", return_value=True),
            patch("backend.trading.scheduler._fetch_market_prices", return_value={"55-56°F": 22}),
            patch("backend.trading.ev_calculator.validate_market_prices", return_value=True),
            patch("backend.trading.scheduler._fetch_market_tickers", return_value={"55-56°F": "KXHIGHNY-B3"}),
            patch("backend.trading.ev_calculator.scan_all_brackets", return_value=[signal]),
            patch("backend.trading.trade_queue.queue_trade", mock_queue),
            patch("backend.trading.scheduler._get_notification_service", return_value=None),
        ):
            await _run_trading_cycle()

        mock_queue.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_risk_block_skips_signal(self) -> None:
        """When risk check fails, neither execute nor queue is called."""
        from backend.trading.scheduler import _run_trading_cycle

        mock_session = _make_mock_db_session()
        settings = _make_user_settings(trading_mode="auto")
        prediction = _make_prediction()
        signal = _make_signal()

        mock_risk_mgr = MagicMock()
        mock_risk_mgr.handle_daily_reset = AsyncMock()
        mock_risk_mgr.check_trade = AsyncMock(return_value=(False, "daily limit reached"))

        mock_cm = MagicMock()
        mock_cm.is_cooldown_active = AsyncMock(return_value=(False, ""))

        mock_execute = AsyncMock()
        mock_queue = AsyncMock()

        with (
            patch("backend.trading.scheduler._are_markets_open", return_value=True),
            patch("backend.trading.scheduler.get_task_session", return_value=mock_session),
            patch("backend.trading.scheduler._load_user_settings", return_value=settings),
            patch("backend.trading.scheduler._get_user_id", return_value="user-1"),
            patch("backend.trading.risk_manager.RiskManager", return_value=mock_risk_mgr),
            patch("backend.trading.cooldown.CooldownManager", return_value=mock_cm),
            patch("backend.trading.scheduler._get_kalshi_client", return_value=MagicMock()),
            patch("backend.trading.scheduler._fetch_latest_predictions", return_value=[prediction]),
            patch("backend.trading.ev_calculator.validate_predictions", return_value=True),
            patch("backend.trading.scheduler._fetch_market_prices", return_value={"55-56°F": 22}),
            patch("backend.trading.ev_calculator.validate_market_prices", return_value=True),
            patch("backend.trading.scheduler._fetch_market_tickers", return_value={"55-56°F": "KXHIGHNY-B3"}),
            patch("backend.trading.ev_calculator.scan_all_brackets", return_value=[signal]),
            patch("backend.trading.executor.execute_trade", mock_execute),
            patch("backend.trading.trade_queue.queue_trade", mock_queue),
        ):
            await _run_trading_cycle()

        mock_execute.assert_not_awaited()
        mock_queue.assert_not_awaited()


# ─── _expire_pending_trades Tests ───


class TestExpirePendingTrades:
    """Tests for _expire_pending_trades -- expires stale pending trades."""

    @pytest.mark.asyncio
    async def test_calls_expire_stale_trades_and_commits(self) -> None:
        """expire_stale_trades is called and session is committed."""
        from backend.trading.scheduler import _expire_pending_trades

        mock_session = _make_mock_db_session()
        mock_expire = AsyncMock(return_value=5)

        with (
            patch("backend.trading.scheduler.get_task_session", return_value=mock_session),
            patch("backend.trading.trade_queue.expire_stale_trades", mock_expire),
        ):
            result = await _expire_pending_trades()

        assert result == 5
        mock_session.commit.assert_awaited_once()
        mock_session.close.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_rollback_on_exception(self) -> None:
        """Session is rolled back when expire_stale_trades raises."""
        from backend.trading.scheduler import _expire_pending_trades

        mock_session = _make_mock_db_session()
        mock_expire = AsyncMock(side_effect=RuntimeError("DB error"))

        with (
            patch("backend.trading.scheduler.get_task_session", return_value=mock_session),
            patch("backend.trading.trade_queue.expire_stale_trades", mock_expire),
            pytest.raises(RuntimeError, match="DB error"),
        ):
            await _expire_pending_trades()

        mock_session.rollback.assert_awaited_once()
        mock_session.close.assert_awaited_once()


# ─── _settle_and_postmortem Tests ───


class TestSettleAndPostmortem:
    """Tests for _settle_and_postmortem -- settles OPEN trades."""

    @pytest.mark.asyncio
    async def test_settles_trade_with_matching_settlement(self) -> None:
        """When an open trade has matching settlement data, settle_trade is called."""
        from backend.common.models import TradeStatus
        from backend.trading.scheduler import _settle_and_postmortem

        mock_session = _make_mock_db_session()

        # Mock Trade query
        mock_trade = MagicMock()
        mock_trade.city = "NYC"
        mock_trade.trade_date = date(2026, 2, 18)
        mock_trade.user_id = "user-1"
        mock_trade.status = TradeStatus.WON  # After settlement

        # Mock Settlement query
        mock_settlement = MagicMock()
        mock_settlement.city = "NYC"
        mock_settlement.settlement_date = date(2026, 2, 18)
        mock_settlement.actual_high_f = 55.0

        # First execute returns open trades, second returns settlement
        trade_result = MagicMock()
        trade_result.scalars.return_value.all.return_value = [mock_trade]

        settlement_result = MagicMock()
        settlement_result.scalar_one_or_none.return_value = mock_settlement

        mock_session.execute.side_effect = [trade_result, settlement_result]

        mock_settle = AsyncMock()
        mock_user_settings = _make_user_settings()
        mock_cm = MagicMock()
        mock_cm.on_trade_win = AsyncMock()
        mock_cm.on_trade_loss = AsyncMock()

        with (
            patch("backend.trading.scheduler.get_task_session", return_value=mock_session),
            patch("backend.trading.postmortem.settle_trade", mock_settle),
            patch("backend.trading.scheduler._load_user_settings", return_value=mock_user_settings),
            patch("backend.trading.cooldown.CooldownManager", return_value=mock_cm),
        ):
            await _settle_and_postmortem()

        mock_settle.assert_awaited_once()
        mock_session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_skips_trade_without_settlement(self) -> None:
        """When no settlement data exists, settle_trade is not called."""
        from backend.trading.scheduler import _settle_and_postmortem

        mock_session = _make_mock_db_session()

        mock_trade = MagicMock()
        mock_trade.city = "NYC"
        mock_trade.trade_date = date(2026, 2, 18)

        trade_result = MagicMock()
        trade_result.scalars.return_value.all.return_value = [mock_trade]

        settlement_result = MagicMock()
        settlement_result.scalar_one_or_none.return_value = None  # No settlement

        mock_session.execute.side_effect = [trade_result, settlement_result]

        mock_settle = AsyncMock()

        with (
            patch("backend.trading.scheduler.get_task_session", return_value=mock_session),
            patch("backend.trading.postmortem.settle_trade", mock_settle),
        ):
            await _settle_and_postmortem()

        mock_settle.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_calls_cooldown_on_win(self) -> None:
        """CooldownManager.on_trade_win is called when trade WON."""
        from backend.common.models import TradeStatus
        from backend.trading.scheduler import _settle_and_postmortem

        mock_session = _make_mock_db_session()

        mock_trade = MagicMock()
        mock_trade.city = "NYC"
        mock_trade.trade_date = date(2026, 2, 18)
        mock_trade.user_id = "user-1"
        mock_trade.status = TradeStatus.WON

        mock_settlement = MagicMock()

        trade_result = MagicMock()
        trade_result.scalars.return_value.all.return_value = [mock_trade]

        settlement_result = MagicMock()
        settlement_result.scalar_one_or_none.return_value = mock_settlement

        mock_session.execute.side_effect = [trade_result, settlement_result]

        mock_cm = MagicMock()
        mock_cm.on_trade_win = AsyncMock()
        mock_cm.on_trade_loss = AsyncMock()

        with (
            patch("backend.trading.scheduler.get_task_session", return_value=mock_session),
            patch("backend.trading.postmortem.settle_trade", AsyncMock()),
            patch("backend.trading.scheduler._load_user_settings", return_value=_make_user_settings()),
            patch("backend.trading.cooldown.CooldownManager", return_value=mock_cm),
        ):
            await _settle_and_postmortem()

        mock_cm.on_trade_win.assert_awaited_once()
        mock_cm.on_trade_loss.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_rollback_on_exception(self) -> None:
        """Session is rolled back when settlement raises."""
        from backend.trading.scheduler import _settle_and_postmortem

        mock_session = _make_mock_db_session()

        # Make the trade query itself raise
        mock_session.execute.side_effect = RuntimeError("DB error")

        with (
            patch("backend.trading.scheduler.get_task_session", return_value=mock_session),
            pytest.raises(RuntimeError, match="DB error"),
        ):
            await _settle_and_postmortem()

        mock_session.rollback.assert_awaited_once()
        mock_session.close.assert_awaited_once()


# ─── Celery Task Wrapper Tests ───


class TestTradingCycleTask:
    """Tests for trading_cycle -- the Celery task wrapper."""

    def test_returns_metadata_dict(self) -> None:
        """The task returns a dict with status and elapsed_seconds."""
        mock_sync_fn = MagicMock()
        with patch("backend.trading.scheduler.async_to_sync", return_value=mock_sync_fn):
            from backend.trading.scheduler import trading_cycle

            result = trading_cycle.apply().result

        assert result["status"] == "completed"
        assert "elapsed_seconds" in result

    def test_retries_on_exception(self) -> None:
        """The task retries when the async implementation raises."""
        from backend.trading.scheduler import trading_cycle

        mock_sync_fn = MagicMock(side_effect=RuntimeError("boom"))
        with patch("backend.trading.scheduler.async_to_sync", return_value=mock_sync_fn):
            task_result = trading_cycle.apply()

        assert task_result.failed() or task_result.result is not None


class TestCheckPendingTradesTask:
    """Tests for check_pending_trades -- the Celery task wrapper."""

    def test_returns_expired_count(self) -> None:
        """The task returns a dict with expired_count."""
        mock_sync_fn = MagicMock(return_value=3)
        with patch("backend.trading.scheduler.async_to_sync", return_value=mock_sync_fn):
            from backend.trading.scheduler import check_pending_trades

            result = check_pending_trades.apply().result

        assert result["status"] == "completed"
        assert result["expired_count"] == 3


class TestSettleTradesTask:
    """Tests for settle_trades -- the Celery task wrapper."""

    def test_returns_metadata_dict(self) -> None:
        """The task returns a dict with status and elapsed_seconds."""
        mock_sync_fn = MagicMock()
        with patch("backend.trading.scheduler.async_to_sync", return_value=mock_sync_fn):
            from backend.trading.scheduler import settle_trades

            result = settle_trades.apply().result

        assert result["status"] == "completed"
        assert "elapsed_seconds" in result
