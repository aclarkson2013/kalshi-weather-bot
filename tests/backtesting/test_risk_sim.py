"""Tests for BacktestRiskManager — bankroll tracking, limits, cooldowns."""

from __future__ import annotations

from backend.backtesting.risk_sim import BacktestRiskManager


class TestBacktestRiskManagerInit:
    """Tests for initialization and defaults."""

    def test_default_init(self):
        risk = BacktestRiskManager()
        assert risk.bankroll_cents == 100_000
        assert risk.max_daily_trades == 20
        assert risk.consecutive_loss_limit == 5
        assert risk.daily_trade_count == 0
        assert risk.consecutive_losses == 0
        assert risk.total_trades == 0
        assert risk.total_blocked == 0
        assert risk.peak_bankroll == 100_000

    def test_custom_init(self):
        risk = BacktestRiskManager(
            initial_bankroll_cents=50_000,
            max_daily_trades=10,
            consecutive_loss_limit=3,
        )
        assert risk.bankroll_cents == 50_000
        assert risk.max_daily_trades == 10
        assert risk.consecutive_loss_limit == 3


class TestCanTrade:
    """Tests for can_trade() risk checks."""

    def test_can_trade_when_limits_clear(self):
        risk = BacktestRiskManager()
        assert risk.can_trade() is True

    def test_blocked_when_bankroll_zero(self):
        risk = BacktestRiskManager(initial_bankroll_cents=0)
        assert risk.can_trade() is False
        assert risk.total_blocked == 1

    def test_blocked_when_bankroll_negative(self):
        risk = BacktestRiskManager(initial_bankroll_cents=100)
        risk.record_trade(pnl_cents=-200, won=False)
        assert risk.bankroll_cents == -100
        assert risk.can_trade() is False

    def test_blocked_at_daily_trade_limit(self):
        risk = BacktestRiskManager(max_daily_trades=3)
        for _ in range(3):
            risk.record_trade(pnl_cents=10, won=True)
        assert risk.can_trade() is False

    def test_blocked_at_consecutive_loss_limit(self):
        risk = BacktestRiskManager(consecutive_loss_limit=3)
        for _ in range(3):
            risk.record_trade(pnl_cents=-10, won=False)
        assert risk.consecutive_losses == 3
        assert risk.can_trade() is False

    def test_consecutive_losses_reset_on_win(self):
        risk = BacktestRiskManager(consecutive_loss_limit=3)
        risk.record_trade(pnl_cents=-10, won=False)
        risk.record_trade(pnl_cents=-10, won=False)
        assert risk.consecutive_losses == 2
        risk.record_trade(pnl_cents=50, won=True)
        assert risk.consecutive_losses == 0
        assert risk.can_trade() is True

    def test_blocked_increments_total_blocked(self):
        risk = BacktestRiskManager(max_daily_trades=1)
        risk.record_trade(pnl_cents=10, won=True)
        assert risk.can_trade() is False
        assert risk.can_trade() is False
        assert risk.total_blocked == 2


class TestRecordTrade:
    """Tests for record_trade() state updates."""

    def test_winning_trade_updates_bankroll(self):
        risk = BacktestRiskManager(initial_bankroll_cents=100_000)
        risk.record_trade(pnl_cents=68, won=True)
        assert risk.bankroll_cents == 100_068

    def test_losing_trade_updates_bankroll(self):
        risk = BacktestRiskManager(initial_bankroll_cents=100_000)
        risk.record_trade(pnl_cents=-20, won=False)
        assert risk.bankroll_cents == 99_980

    def test_daily_count_increments(self):
        risk = BacktestRiskManager()
        risk.record_trade(pnl_cents=10, won=True)
        risk.record_trade(pnl_cents=-5, won=False)
        assert risk.daily_trade_count == 2

    def test_total_trades_increments(self):
        risk = BacktestRiskManager()
        risk.record_trade(pnl_cents=10, won=True)
        risk.record_trade(pnl_cents=10, won=True)
        assert risk.total_trades == 2

    def test_peak_bankroll_tracks_highwater(self):
        risk = BacktestRiskManager(initial_bankroll_cents=100_000)
        risk.record_trade(pnl_cents=500, won=True)
        assert risk.peak_bankroll == 100_500
        risk.record_trade(pnl_cents=-200, won=False)
        assert risk.peak_bankroll == 100_500  # Doesn't decrease
        risk.record_trade(pnl_cents=800, won=True)
        assert risk.peak_bankroll == 101_100  # New peak


class TestAdvanceDay:
    """Tests for advance_day() daily reset."""

    def test_resets_daily_trade_count(self):
        risk = BacktestRiskManager()
        risk.record_trade(pnl_cents=10, won=True)
        risk.record_trade(pnl_cents=10, won=True)
        assert risk.daily_trade_count == 2
        risk.advance_day()
        assert risk.daily_trade_count == 0

    def test_preserves_consecutive_losses_across_days(self):
        risk = BacktestRiskManager()
        risk.record_trade(pnl_cents=-10, won=False)
        risk.record_trade(pnl_cents=-10, won=False)
        risk.advance_day()
        assert risk.consecutive_losses == 2

    def test_preserves_bankroll_across_days(self):
        risk = BacktestRiskManager(initial_bankroll_cents=100_000)
        risk.record_trade(pnl_cents=500, won=True)
        risk.advance_day()
        assert risk.bankroll_cents == 100_500

    def test_can_trade_after_daily_reset(self):
        risk = BacktestRiskManager(max_daily_trades=2)
        risk.record_trade(pnl_cents=10, won=True)
        risk.record_trade(pnl_cents=10, won=True)
        assert risk.can_trade() is False
        risk.advance_day()
        assert risk.can_trade() is True


class TestGetMaxTradeSize:
    """Tests for get_max_trade_size_cents()."""

    def test_ten_percent_of_bankroll(self):
        risk = BacktestRiskManager(initial_bankroll_cents=100_000)
        assert risk.get_max_trade_size_cents() == 10_000

    def test_minimum_floor(self):
        risk = BacktestRiskManager(initial_bankroll_cents=500)
        assert risk.get_max_trade_size_cents() == 100

    def test_updates_with_bankroll(self):
        risk = BacktestRiskManager(initial_bankroll_cents=100_000)
        risk.record_trade(pnl_cents=-50_000, won=False)
        assert risk.get_max_trade_size_cents() == 5_000
