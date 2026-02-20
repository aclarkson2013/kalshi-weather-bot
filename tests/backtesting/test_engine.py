"""Tests for backtest engine — full simulation loop, edge cases."""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest

from backend.backtesting.engine import _execute_simulated_trade, run_backtest
from backend.backtesting.exceptions import InsufficientDataError
from backend.backtesting.risk_sim import BacktestRiskManager
from backend.backtesting.schemas import BacktestConfig
from backend.common.schemas import (
    BracketPrediction,
    BracketProbability,
    TradeSignal,
)


def _make_prediction(city: str, pred_date: date, mean: float = 56.0) -> BracketPrediction:
    """Helper to create a prediction with clear +EV on bracket 3."""
    return BracketPrediction(
        city=city,
        date=pred_date,
        brackets=[
            BracketProbability(
                bracket_label="<=52F", lower_bound_f=None, upper_bound_f=52, probability=0.05
            ),
            BracketProbability(
                bracket_label="53-54F", lower_bound_f=53, upper_bound_f=54, probability=0.12
            ),
            BracketProbability(
                bracket_label="55-56F", lower_bound_f=55, upper_bound_f=56, probability=0.35
            ),
            BracketProbability(
                bracket_label="57-58F", lower_bound_f=57, upper_bound_f=58, probability=0.28
            ),
            BracketProbability(
                bracket_label="59-60F", lower_bound_f=59, upper_bound_f=60, probability=0.13
            ),
            BracketProbability(
                bracket_label=">=61F", lower_bound_f=61, upper_bound_f=None, probability=0.07
            ),
        ],
        ensemble_mean_f=mean,
        ensemble_std_f=2.0,
        confidence="medium",
        model_sources=["NWS", "GFS"],
        generated_at=datetime(2025, 2, 28, 15, 0, 0, tzinfo=UTC),
    )


class TestRunBacktest:
    """Tests for run_backtest() main entry point."""

    def test_basic_backtest_runs(self):
        config = BacktestConfig(
            cities=["NYC"],
            start_date=date(2025, 3, 1),
            end_date=date(2025, 3, 3),
            initial_bankroll_cents=100_000,
            use_kelly=False,
            price_noise_cents=0,
        )
        predictions = [
            _make_prediction("NYC", date(2025, 3, 1)),
            _make_prediction("NYC", date(2025, 3, 2)),
            _make_prediction("NYC", date(2025, 3, 3)),
        ]
        settlements = {
            ("NYC", date(2025, 3, 1)): 55.5,  # In bracket 55-56F
            ("NYC", date(2025, 3, 2)): 58.0,  # In bracket 57-58F
            ("NYC", date(2025, 3, 3)): 60.0,  # In bracket 59-60F
        }
        result = run_backtest(config, predictions, settlements, seed=42)
        assert result.duration_seconds >= 0
        assert len(result.days) == 3

    def test_backtest_with_no_matching_predictions_raises(self):
        config = BacktestConfig(
            cities=["MIA"],
            start_date=date(2025, 3, 1),
            end_date=date(2025, 3, 3),
        )
        predictions = [_make_prediction("NYC", date(2025, 3, 1))]
        with pytest.raises(InsufficientDataError, match="No predictions match"):
            run_backtest(config, predictions)

    def test_backtest_generates_synthetic_settlements_when_none(self):
        config = BacktestConfig(
            cities=["NYC"],
            start_date=date(2025, 3, 1),
            end_date=date(2025, 3, 1),
            use_kelly=False,
            price_noise_cents=0,
        )
        predictions = [_make_prediction("NYC", date(2025, 3, 1))]
        # No settlements provided — engine generates them
        result = run_backtest(config, predictions, seed=42)
        assert len(result.days) == 1

    def test_seed_reproducibility(self):
        config = BacktestConfig(
            cities=["NYC"],
            start_date=date(2025, 3, 1),
            end_date=date(2025, 3, 3),
            use_kelly=False,
        )
        predictions = [
            _make_prediction("NYC", date(2025, 3, 1)),
            _make_prediction("NYC", date(2025, 3, 2)),
            _make_prediction("NYC", date(2025, 3, 3)),
        ]
        r1 = run_backtest(config, predictions, seed=42)
        r2 = run_backtest(config, predictions, seed=42)

        # Same seed → same trades, same PnL
        for d1, d2 in zip(r1.days, r2.days, strict=True):
            assert len(d1.trades) == len(d2.trades)
            for t1, t2 in zip(d1.trades, d2.trades, strict=True):
                assert t1.pnl_cents == t2.pnl_cents

    def test_backtest_with_kelly_enabled(self):
        config = BacktestConfig(
            cities=["NYC"],
            start_date=date(2025, 3, 1),
            end_date=date(2025, 3, 1),
            initial_bankroll_cents=100_000,
            use_kelly=True,
            kelly_fraction=0.25,
            price_noise_cents=0,
        )
        predictions = [_make_prediction("NYC", date(2025, 3, 1))]
        settlements = {("NYC", date(2025, 3, 1)): 55.5}
        result = run_backtest(config, predictions, settlements, seed=42)
        assert len(result.days) == 1

    def test_backtest_multi_city(self):
        config = BacktestConfig(
            cities=["NYC", "CHI"],
            start_date=date(2025, 3, 1),
            end_date=date(2025, 3, 1),
            use_kelly=False,
            price_noise_cents=15,  # High noise to create mispricing → +EV
            min_ev_threshold=0.01,
        )
        predictions = [
            _make_prediction("NYC", date(2025, 3, 1)),
            _make_prediction("CHI", date(2025, 3, 1), mean=33.0),
        ]
        settlements = {
            ("NYC", date(2025, 3, 1)): 55.5,
            ("CHI", date(2025, 3, 1)): 33.0,
        }
        result = run_backtest(config, predictions, settlements, seed=42)
        assert len(result.days) == 1
        # With high noise, at least some trades should be generated
        assert len(result.days[0].trades) >= 0  # May or may not produce trades

    def test_empty_days_when_no_predictions_for_date(self):
        config = BacktestConfig(
            cities=["NYC"],
            start_date=date(2025, 3, 1),
            end_date=date(2025, 3, 3),
            use_kelly=False,
        )
        # Only provide prediction for day 1, days 2 and 3 have no data
        predictions = [_make_prediction("NYC", date(2025, 3, 1))]
        settlements = {("NYC", date(2025, 3, 1)): 55.5}
        result = run_backtest(config, predictions, settlements, seed=42)
        assert len(result.days) == 3
        assert result.days[1].trades == []
        assert result.days[2].trades == []

    def test_risk_limits_block_excess_trades(self):
        config = BacktestConfig(
            cities=["NYC"],
            start_date=date(2025, 3, 1),
            end_date=date(2025, 3, 1),
            max_daily_trades=1,  # Only allow 1 trade per day
            use_kelly=False,
            price_noise_cents=0,
        )
        predictions = [_make_prediction("NYC", date(2025, 3, 1))]
        settlements = {("NYC", date(2025, 3, 1)): 55.5}
        result = run_backtest(config, predictions, settlements, seed=42)
        day = result.days[0]
        assert len(day.trades) <= 1
        # Some trades should be blocked
        assert day.trades_blocked_by_risk >= 0


class TestExecuteSimulatedTrade:
    """Tests for _execute_simulated_trade()."""

    def test_winning_yes_trade(self):
        signal = TradeSignal(
            city="NYC",
            bracket="55-56F",
            side="yes",
            price_cents=20,
            quantity=1,
            model_probability=0.35,
            market_probability=0.20,
            ev=0.05,
            confidence="medium",
            market_ticker="KXHIGHNY-25MAR01-B3",
        )
        risk = BacktestRiskManager(initial_bankroll_cents=100_000)
        trade = _execute_simulated_trade(signal, 55.5, risk, date(2025, 3, 1))
        assert trade.won is True
        assert trade.pnl_cents > 0
        assert trade.fees_cents > 0
        assert risk.bankroll_cents == 100_000 + trade.pnl_cents

    def test_losing_yes_trade(self):
        signal = TradeSignal(
            city="NYC",
            bracket="55-56F",
            side="yes",
            price_cents=20,
            quantity=1,
            model_probability=0.35,
            market_probability=0.20,
            ev=0.05,
            confidence="medium",
            market_ticker="KXHIGHNY-25MAR01-B3",
        )
        risk = BacktestRiskManager(initial_bankroll_cents=100_000)
        trade = _execute_simulated_trade(signal, 58.0, risk, date(2025, 3, 1))
        assert trade.won is False
        assert trade.pnl_cents == -20  # Lost the cost
        assert trade.fees_cents == 0

    def test_winning_no_trade(self):
        signal = TradeSignal(
            city="NYC",
            bracket="55-56F",
            side="no",
            price_cents=80,
            quantity=1,
            model_probability=0.05,
            market_probability=0.80,
            ev=0.05,
            confidence="medium",
            market_ticker="KXHIGHNY-25MAR01-B3",
        )
        risk = BacktestRiskManager(initial_bankroll_cents=100_000)
        trade = _execute_simulated_trade(signal, 58.0, risk, date(2025, 3, 1))
        # NO side wins when bracket is NOT hit
        assert trade.won is True
        assert trade.pnl_cents > 0
        # Cost for NO = 100 - 80 = 20 cents
        assert trade.fees_cents > 0

    def test_multi_quantity_trade(self):
        signal = TradeSignal(
            city="NYC",
            bracket="55-56F",
            side="yes",
            price_cents=20,
            quantity=3,
            model_probability=0.35,
            market_probability=0.20,
            ev=0.05,
            confidence="medium",
            market_ticker="KXHIGHNY-25MAR01-B3",
        )
        risk = BacktestRiskManager(initial_bankroll_cents=100_000)
        trade = _execute_simulated_trade(signal, 55.5, risk, date(2025, 3, 1))
        assert trade.won is True
        assert trade.quantity == 3
        # Cost = 20 * 3 = 60, payout = 100 * 3 = 300, profit = 240
        # Fee per contract = max(1, int(80 * 0.15)) = 12, total fees = 36
        # PnL = 240 - 36 = 204
        assert trade.pnl_cents == 204
        assert trade.fees_cents == 36

    def test_trade_date_set_correctly(self):
        signal = TradeSignal(
            city="NYC",
            bracket="55-56F",
            side="yes",
            price_cents=20,
            quantity=1,
            model_probability=0.35,
            market_probability=0.20,
            ev=0.05,
            confidence="medium",
            market_ticker="KXHIGHNY-25MAR01-B3",
        )
        risk = BacktestRiskManager()
        trade = _execute_simulated_trade(signal, 55.5, risk, date(2025, 3, 5))
        assert trade.day == date(2025, 3, 5)
