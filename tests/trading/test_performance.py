"""Tests for Phase 22 performance optimizations.

Tests cover:
- Multi-contract trade cost in risk manager
- Trading cycle step metrics exist
- User model lazy loading is 'select' not 'selectin'
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.common.models import User
from backend.common.schemas import TradeSignal, UserSettings
from backend.trading.risk_manager import RiskManager


# ---------------------------------------------------------------------------
# TestMultiContractCost
# ---------------------------------------------------------------------------
class TestMultiContractCost:
    """Risk manager must account for quantity in trade cost."""

    def _make_rm(
        self,
        settings: UserSettings,
        open_exposure: int = 0,
        daily_pnl: int = 0,
    ) -> RiskManager:
        """Build a RiskManager with mocked DB."""
        mock_db = AsyncMock()
        mock_result_exposure = MagicMock()
        mock_result_exposure.scalar.return_value = open_exposure
        mock_result_pnl = MagicMock()
        mock_result_pnl.scalar.return_value = daily_pnl
        mock_db.execute.side_effect = [mock_result_exposure, mock_result_pnl]
        return RiskManager(settings=settings, db=mock_db, user_id="test-user")

    @pytest.mark.asyncio
    @patch("backend.trading.cooldown.CooldownManager")
    async def test_single_contract_cost_yes(self, mock_cm_cls) -> None:
        """YES at 22c × 1 = 22c total cost."""
        mock_cm = AsyncMock()
        mock_cm.is_cooldown_active.return_value = (False, "")
        mock_cm_cls.return_value = mock_cm

        settings = UserSettings(max_trade_size_cents=100, max_daily_exposure_cents=5000)
        signal = TradeSignal(
            city="NYC",
            bracket="55-56F",
            side="yes",
            price_cents=22,
            quantity=1,
            model_probability=0.35,
            market_probability=0.22,
            ev=0.06,
            confidence="medium",
            market_ticker="KXHIGHNY-26FEB20-B3",
        )
        rm = self._make_rm(settings)
        allowed, reason = await rm.check_trade(signal)
        assert allowed is True

    @pytest.mark.asyncio
    @patch("backend.trading.cooldown.CooldownManager")
    async def test_multi_contract_blocks_when_exceeds_limit(self, mock_cm_cls) -> None:
        """YES at 22c × 5 = 110c exceeds max_trade_size=100c."""
        mock_cm = AsyncMock()
        mock_cm.is_cooldown_active.return_value = (False, "")
        mock_cm_cls.return_value = mock_cm

        settings = UserSettings(max_trade_size_cents=100, max_daily_exposure_cents=5000)
        signal = TradeSignal(
            city="NYC",
            bracket="55-56F",
            side="yes",
            price_cents=22,
            quantity=5,  # 22 × 5 = 110c > 100c
            model_probability=0.35,
            market_probability=0.22,
            ev=0.06,
            confidence="medium",
            market_ticker="KXHIGHNY-26FEB20-B3",
        )
        rm = self._make_rm(settings)
        allowed, reason = await rm.check_trade(signal)
        assert allowed is False
        assert "exceeds" in reason.lower() or "max" in reason.lower()

    @pytest.mark.asyncio
    @patch("backend.trading.cooldown.CooldownManager")
    async def test_multi_contract_passes_within_limit(self, mock_cm_cls) -> None:
        """YES at 22c × 4 = 88c within max_trade_size=100c."""
        mock_cm = AsyncMock()
        mock_cm.is_cooldown_active.return_value = (False, "")
        mock_cm_cls.return_value = mock_cm

        settings = UserSettings(max_trade_size_cents=100, max_daily_exposure_cents=5000)
        signal = TradeSignal(
            city="NYC",
            bracket="55-56F",
            side="yes",
            price_cents=22,
            quantity=4,  # 22 × 4 = 88c < 100c
            model_probability=0.35,
            market_probability=0.22,
            ev=0.06,
            confidence="medium",
            market_ticker="KXHIGHNY-26FEB20-B3",
        )
        rm = self._make_rm(settings)
        allowed, reason = await rm.check_trade(signal)
        assert allowed is True

    @pytest.mark.asyncio
    @patch("backend.trading.cooldown.CooldownManager")
    async def test_multi_contract_no_side_cost(self, mock_cm_cls) -> None:
        """NO at price=20c × 3: cost per contract = 80c, total = 240c."""
        mock_cm = AsyncMock()
        mock_cm.is_cooldown_active.return_value = (False, "")
        mock_cm_cls.return_value = mock_cm

        settings = UserSettings(max_trade_size_cents=200, max_daily_exposure_cents=5000)
        signal = TradeSignal(
            city="NYC",
            bracket="55-56F",
            side="no",
            price_cents=20,
            quantity=3,  # (100-20) × 3 = 240c > 200c
            model_probability=0.10,
            market_probability=0.20,
            ev=0.06,
            confidence="medium",
            market_ticker="KXHIGHNY-26FEB20-B3",
        )
        rm = self._make_rm(settings)
        allowed, reason = await rm.check_trade(signal)
        assert allowed is False

    @pytest.mark.asyncio
    @patch("backend.trading.cooldown.CooldownManager")
    async def test_multi_contract_exposure_check(self, mock_cm_cls) -> None:
        """Multi-contract total cost checked against exposure limit."""
        mock_cm = AsyncMock()
        mock_cm.is_cooldown_active.return_value = (False, "")
        mock_cm_cls.return_value = mock_cm

        settings = UserSettings(
            max_trade_size_cents=500,
            max_daily_exposure_cents=300,
        )
        signal = TradeSignal(
            city="NYC",
            bracket="55-56F",
            side="yes",
            price_cents=22,
            quantity=5,  # 22 × 5 = 110c
            model_probability=0.35,
            market_probability=0.22,
            ev=0.06,
            confidence="medium",
            market_ticker="KXHIGHNY-26FEB20-B3",
        )
        # 200c existing + 110c new = 310c > 300c limit
        rm = self._make_rm(settings, open_exposure=200)
        allowed, reason = await rm.check_trade(signal)
        assert allowed is False
        assert "exposure" in reason.lower()


# ---------------------------------------------------------------------------
# TestLazyLoading
# ---------------------------------------------------------------------------
class TestLazyLoading:
    """Verify User model relationships use 'select' not 'selectin'."""

    def test_trades_relationship_lazy_select(self) -> None:
        """User.trades uses lazy='select' (not 'selectin')."""
        rel = User.__mapper__.relationships["trades"]
        assert rel.lazy == "select"

    def test_forecasts_relationship_lazy_select(self) -> None:
        """User.forecasts uses lazy='select' (not 'selectin')."""
        rel = User.__mapper__.relationships["forecasts"]
        assert rel.lazy == "select"


# ---------------------------------------------------------------------------
# TestTradingCycleMetrics
# ---------------------------------------------------------------------------
class TestTradingCycleMetrics:
    """Verify new Prometheus metrics exist."""

    def test_step_duration_metric_exists(self) -> None:
        """TRADING_CYCLE_STEP_DURATION_SECONDS exists with step label."""
        from backend.common.metrics import TRADING_CYCLE_STEP_DURATION_SECONDS

        assert TRADING_CYCLE_STEP_DURATION_SECONDS is not None
        # Verify it has the expected label
        TRADING_CYCLE_STEP_DURATION_SECONDS.labels(step="test").observe(0.1)

    def test_total_duration_metric_exists(self) -> None:
        """TRADING_CYCLE_TOTAL_DURATION_SECONDS exists."""
        from backend.common.metrics import TRADING_CYCLE_TOTAL_DURATION_SECONDS

        assert TRADING_CYCLE_TOTAL_DURATION_SECONDS is not None
        TRADING_CYCLE_TOTAL_DURATION_SECONDS.observe(1.0)


# ---------------------------------------------------------------------------
# TestAlembicMigration
# ---------------------------------------------------------------------------
class TestAlembicMigration0003:
    """Verify migration 0003 structure."""

    def _load_migration(self):
        """Load migration module via importlib."""
        import importlib.util
        from pathlib import Path

        path = Path("alembic/versions/0003_add_performance_indexes.py")
        spec = importlib.util.spec_from_file_location("migration_0003", path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    def test_migration_revision(self) -> None:
        """Migration 0003 has correct revision chain."""
        m = self._load_migration()
        assert m.revision == "0003"
        assert m.down_revision == "0002"

    def test_upgrade_function_exists(self) -> None:
        """Migration has upgrade function."""
        m = self._load_migration()
        assert hasattr(m, "upgrade")
        assert callable(m.upgrade)

    def test_downgrade_function_exists(self) -> None:
        """Migration has downgrade function."""
        m = self._load_migration()
        assert hasattr(m, "downgrade")
        assert callable(m.downgrade)
