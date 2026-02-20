"""Tests for backtesting schemas — config validation, defaults, edge cases."""

from __future__ import annotations

from datetime import date

import pytest

from backend.backtesting.schemas import (
    BacktestConfig,
    BacktestDay,
    BacktestResult,
    CityStats,
    KellyStats,
    SimulatedTrade,
)

# ─── BacktestConfig Tests ───


class TestBacktestConfig:
    """Tests for BacktestConfig validation."""

    def test_default_config_creates_with_required_fields(self):
        config = BacktestConfig(
            start_date=date(2025, 3, 1),
            end_date=date(2025, 3, 7),
        )
        assert config.cities == ["NYC", "CHI", "MIA", "AUS"]
        assert config.initial_bankroll_cents == 100_000
        assert config.min_ev_threshold == 0.02
        assert config.use_kelly is True
        assert config.kelly_fraction == 0.25
        assert config.max_daily_trades == 20
        assert config.consecutive_loss_limit == 5
        assert config.price_noise_cents == 5

    def test_custom_config(self):
        config = BacktestConfig(
            cities=["NYC"],
            start_date=date(2025, 1, 1),
            end_date=date(2025, 1, 31),
            initial_bankroll_cents=200_000,
            min_ev_threshold=0.05,
            use_kelly=False,
        )
        assert config.cities == ["NYC"]
        assert config.initial_bankroll_cents == 200_000
        assert config.use_kelly is False

    def test_end_date_before_start_date_raises(self):
        with pytest.raises(ValueError, match="end_date.*must be >= start_date"):
            BacktestConfig(
                start_date=date(2025, 3, 7),
                end_date=date(2025, 3, 1),
            )

    def test_same_start_and_end_date_allowed(self):
        config = BacktestConfig(
            start_date=date(2025, 3, 1),
            end_date=date(2025, 3, 1),
        )
        assert config.start_date == config.end_date

    def test_empty_cities_raises(self):
        with pytest.raises(ValueError, match="At least one city"):
            BacktestConfig(
                cities=[],
                start_date=date(2025, 3, 1),
                end_date=date(2025, 3, 7),
            )

    def test_bankroll_below_minimum_raises(self):
        with pytest.raises(ValueError):
            BacktestConfig(
                start_date=date(2025, 3, 1),
                end_date=date(2025, 3, 7),
                initial_bankroll_cents=500,  # Below 1000 min
            )

    def test_ev_threshold_out_of_range_raises(self):
        with pytest.raises(ValueError):
            BacktestConfig(
                start_date=date(2025, 3, 1),
                end_date=date(2025, 3, 7),
                min_ev_threshold=1.5,
            )

    def test_kelly_fraction_bounds(self):
        # Too low
        with pytest.raises(ValueError):
            BacktestConfig(
                start_date=date(2025, 3, 1),
                end_date=date(2025, 3, 7),
                kelly_fraction=0.005,
            )
        # Too high
        with pytest.raises(ValueError):
            BacktestConfig(
                start_date=date(2025, 3, 1),
                end_date=date(2025, 3, 7),
                kelly_fraction=1.5,
            )


# ─── SimulatedTrade Tests ───


class TestSimulatedTrade:
    """Tests for SimulatedTrade model."""

    def test_winning_trade(self):
        trade = SimulatedTrade(
            day=date(2025, 3, 1),
            city="NYC",
            bracket_label="55-56F",
            side="yes",
            price_cents=20,
            quantity=2,
            model_probability=0.35,
            market_probability=0.20,
            ev=0.05,
            confidence="medium",
            actual_temp_f=55.5,
            won=True,
            pnl_cents=140,
            fees_cents=24,
            bankroll_after_cents=100_140,
        )
        assert trade.won is True
        assert trade.pnl_cents == 140

    def test_losing_trade(self):
        trade = SimulatedTrade(
            day=date(2025, 3, 1),
            city="CHI",
            bracket_label="33-34F",
            side="yes",
            price_cents=18,
            quantity=1,
            model_probability=0.30,
            market_probability=0.18,
            ev=0.03,
            confidence="medium",
            actual_temp_f=36.0,
            won=False,
            pnl_cents=-18,
            fees_cents=0,
            bankroll_after_cents=99_982,
        )
        assert trade.won is False
        assert trade.pnl_cents == -18

    def test_price_cents_validation(self):
        with pytest.raises(ValueError):
            SimulatedTrade(
                day=date(2025, 3, 1),
                city="NYC",
                bracket_label="55-56F",
                side="yes",
                price_cents=0,  # Below 1
                quantity=1,
                model_probability=0.35,
                market_probability=0.20,
                ev=0.05,
                confidence="medium",
                actual_temp_f=55.5,
                won=True,
                pnl_cents=68,
                fees_cents=12,
                bankroll_after_cents=100_068,
            )


# ─── BacktestDay Tests ───


class TestBacktestDay:
    """Tests for BacktestDay model."""

    def test_empty_day(self):
        day = BacktestDay(
            day=date(2025, 3, 1),
            bankroll_start_cents=100_000,
            bankroll_end_cents=100_000,
        )
        assert day.trades == []
        assert day.daily_pnl_cents == 0

    def test_day_with_trades(self):
        day = BacktestDay(
            day=date(2025, 3, 1),
            trades=[],
            daily_pnl_cents=150,
            bankroll_start_cents=100_000,
            bankroll_end_cents=100_150,
            trades_blocked_by_risk=2,
        )
        assert day.trades_blocked_by_risk == 2


# ─── CityStats Tests ───


class TestCityStats:
    """Tests for CityStats model."""

    def test_defaults(self):
        stats = CityStats(city="NYC")
        assert stats.total_trades == 0
        assert stats.wins == 0
        assert stats.win_rate == 0.0

    def test_populated(self):
        stats = CityStats(
            city="CHI",
            total_trades=50,
            wins=28,
            losses=22,
            win_rate=0.56,
            total_pnl_cents=1500,
            avg_ev=0.04,
        )
        assert stats.win_rate == 0.56


# ─── KellyStats Tests ───


class TestKellyStats:
    """Tests for KellyStats model."""

    def test_defaults(self):
        stats = KellyStats()
        assert stats.avg_quantity == 0.0
        assert stats.pnl_vs_flat == 0

    def test_populated(self):
        stats = KellyStats(
            avg_quantity=3.2,
            max_quantity=8,
            pnl_vs_flat=2500,
            avg_edge_cents=4.5,
        )
        assert stats.max_quantity == 8


# ─── BacktestResult Tests ───


class TestBacktestResult:
    """Tests for BacktestResult model."""

    def test_minimal_result(self, default_config):
        result = BacktestResult(config=default_config)
        assert result.total_trades == 0
        assert result.win_rate == 0.0
        assert result.days == []

    def test_full_result(self, default_config):
        result = BacktestResult(
            config=default_config,
            total_trades=100,
            wins=55,
            losses=45,
            win_rate=0.55,
            total_pnl_cents=8500,
            roi_pct=8.5,
            sharpe_ratio=1.2,
            max_drawdown_pct=3.5,
            total_days_simulated=7,
            days_with_trades=6,
            duration_seconds=0.45,
        )
        assert result.roi_pct == 8.5
        assert result.sharpe_ratio == 1.2
