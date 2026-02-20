"""Tests for metrics calculator — win rate, ROI, Sharpe, drawdown."""

from __future__ import annotations

from datetime import date

from backend.backtesting.metrics import (
    _compute_max_drawdown,
    _compute_per_city_stats,
    _compute_roi,
    _compute_sharpe,
    compute_metrics,
)
from backend.backtesting.schemas import (
    BacktestConfig,
    BacktestDay,
    BacktestResult,
)

from .conftest import make_losing_trade, make_winning_trade


def _make_config(**kwargs) -> BacktestConfig:
    defaults = {
        "start_date": date(2025, 3, 1),
        "end_date": date(2025, 3, 3),
        "initial_bankroll_cents": 100_000,
    }
    defaults.update(kwargs)
    return BacktestConfig(**defaults)


def _make_result(days: list[BacktestDay], **config_kwargs) -> BacktestResult:
    config = _make_config(**config_kwargs)
    return BacktestResult(config=config, days=days)


class TestComputeROI:
    """Tests for _compute_roi()."""

    def test_positive_roi(self):
        assert _compute_roi(8500, 100_000) == 8.5

    def test_negative_roi(self):
        assert _compute_roi(-5000, 100_000) == -5.0

    def test_zero_bankroll(self):
        assert _compute_roi(100, 0) == 0.0

    def test_zero_pnl(self):
        assert _compute_roi(0, 100_000) == 0.0


class TestComputeSharpe:
    """Tests for _compute_sharpe()."""

    def test_positive_sharpe(self):
        days = [
            BacktestDay(
                day=date(2025, 3, d),
                daily_pnl_cents=100,
                bankroll_start_cents=100_000 + (d - 1) * 100,
                bankroll_end_cents=100_000 + d * 100,
            )
            for d in range(1, 11)
        ]
        result = _make_result(days)
        sharpe = _compute_sharpe(result)
        # Constant positive daily return → infinite Sharpe (std=0 → returns 0)
        # Actually, when all returns are the same, std=0 → sharpe=0
        assert sharpe == 0.0  # Zero variance means undefined

    def test_mixed_returns_sharpe(self):
        days = [
            BacktestDay(
                day=date(2025, 3, 1),
                daily_pnl_cents=200,
                bankroll_start_cents=100_000,
                bankroll_end_cents=100_200,
            ),
            BacktestDay(
                day=date(2025, 3, 2),
                daily_pnl_cents=-50,
                bankroll_start_cents=100_200,
                bankroll_end_cents=100_150,
            ),
            BacktestDay(
                day=date(2025, 3, 3),
                daily_pnl_cents=150,
                bankroll_start_cents=100_150,
                bankroll_end_cents=100_300,
            ),
        ]
        result = _make_result(days)
        sharpe = _compute_sharpe(result)
        assert sharpe > 0  # Net positive with some variance

    def test_single_day_returns_zero(self):
        days = [
            BacktestDay(
                day=date(2025, 3, 1),
                daily_pnl_cents=100,
                bankroll_start_cents=100_000,
                bankroll_end_cents=100_100,
            ),
        ]
        result = _make_result(days)
        assert _compute_sharpe(result) == 0.0

    def test_empty_days(self):
        result = _make_result([])
        assert _compute_sharpe(result) == 0.0


class TestComputeMaxDrawdown:
    """Tests for _compute_max_drawdown()."""

    def test_no_drawdown(self):
        days = [
            BacktestDay(
                day=date(2025, 3, d),
                bankroll_start_cents=100_000 + (d - 1) * 100,
                bankroll_end_cents=100_000 + d * 100,
            )
            for d in range(1, 4)
        ]
        result = _make_result(days)
        assert _compute_max_drawdown(result) == 0.0

    def test_simple_drawdown(self):
        days = [
            BacktestDay(
                day=date(2025, 3, 1),
                bankroll_start_cents=100_000,
                bankroll_end_cents=110_000,  # Peak
            ),
            BacktestDay(
                day=date(2025, 3, 2),
                bankroll_start_cents=110_000,
                bankroll_end_cents=100_000,  # 9.09% drawdown from 110K peak
            ),
        ]
        result = _make_result(days)
        dd = _compute_max_drawdown(result)
        assert abs(dd - 9.09) < 0.1

    def test_recovery_after_drawdown(self):
        days = [
            BacktestDay(
                day=date(2025, 3, 1),
                bankroll_start_cents=100_000,
                bankroll_end_cents=110_000,
            ),
            BacktestDay(
                day=date(2025, 3, 2),
                bankroll_start_cents=110_000,
                bankroll_end_cents=100_000,
            ),
            BacktestDay(
                day=date(2025, 3, 3),
                bankroll_start_cents=100_000,
                bankroll_end_cents=115_000,  # Recovery to new peak
            ),
        ]
        result = _make_result(days)
        dd = _compute_max_drawdown(result)
        # Max DD was ~9.09% from 110K to 100K
        assert abs(dd - 9.09) < 0.1

    def test_empty_days(self):
        result = _make_result([])
        assert _compute_max_drawdown(result) == 0.0


class TestComputePerCityStats:
    """Tests for _compute_per_city_stats()."""

    def test_single_city(self):
        trades = [
            make_winning_trade(city="NYC"),
            make_losing_trade(city="NYC"),
            make_winning_trade(city="NYC"),
        ]
        stats = _compute_per_city_stats(trades)
        assert "NYC" in stats
        assert stats["NYC"].total_trades == 3
        assert stats["NYC"].wins == 2
        assert stats["NYC"].losses == 1

    def test_multi_city(self):
        trades = [
            make_winning_trade(city="NYC"),
            make_losing_trade(city="CHI"),
        ]
        stats = _compute_per_city_stats(trades)
        assert len(stats) == 2
        assert stats["NYC"].wins == 1
        assert stats["CHI"].losses == 1

    def test_empty_trades(self):
        stats = _compute_per_city_stats([])
        assert stats == {}


class TestComputeMetrics:
    """Tests for compute_metrics() — full integration."""

    def test_full_metrics_computation(self):
        w = make_winning_trade(day=date(2025, 3, 1))
        loss = make_losing_trade(day=date(2025, 3, 2))
        days = [
            BacktestDay(
                day=date(2025, 3, 1),
                trades=[w],
                daily_pnl_cents=w.pnl_cents,
                bankroll_start_cents=100_000,
                bankroll_end_cents=100_000 + w.pnl_cents,
            ),
            BacktestDay(
                day=date(2025, 3, 2),
                trades=[loss],
                daily_pnl_cents=loss.pnl_cents,
                bankroll_start_cents=100_000 + w.pnl_cents,
                bankroll_end_cents=100_000 + w.pnl_cents + loss.pnl_cents,
            ),
        ]
        result = _make_result(days, use_kelly=False)
        result = compute_metrics(result)

        assert result.total_trades == 2
        assert result.wins == 1
        assert result.losses == 1
        assert result.win_rate == 0.5
        assert result.total_pnl_cents == w.pnl_cents + loss.pnl_cents
        assert result.total_days_simulated == 2
        assert result.days_with_trades == 2
        assert isinstance(result.roi_pct, float)
        assert isinstance(result.sharpe_ratio, float)
        assert isinstance(result.max_drawdown_pct, float)
        assert "NYC" in result.per_city_stats
        assert result.kelly_stats is None  # Kelly disabled

    def test_metrics_with_kelly(self):
        w = make_winning_trade(day=date(2025, 3, 1), quantity=3)
        days = [
            BacktestDay(
                day=date(2025, 3, 1),
                trades=[w],
                daily_pnl_cents=w.pnl_cents,
                bankroll_start_cents=100_000,
                bankroll_end_cents=100_000 + w.pnl_cents,
            ),
        ]
        result = _make_result(days, use_kelly=True)
        result = compute_metrics(result)
        assert result.kelly_stats is not None
        assert result.kelly_stats.avg_quantity == 3.0
        assert result.kelly_stats.max_quantity == 3

    def test_empty_result(self):
        result = _make_result([])
        result = compute_metrics(result)
        assert result.total_trades == 0
        assert result.win_rate == 0.0
        assert result.roi_pct == 0.0
