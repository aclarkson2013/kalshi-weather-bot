"""Integration tests — end-to-end backtest with realistic multi-city data."""

from __future__ import annotations

from datetime import UTC, date, datetime

from backend.backtesting.engine import run_backtest
from backend.backtesting.metrics import compute_metrics
from backend.backtesting.schemas import BacktestConfig
from backend.common.schemas import BracketPrediction, BracketProbability


def _nyc_prediction(pred_date: date) -> BracketPrediction:
    return BracketPrediction(
        city="NYC",
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
        ensemble_mean_f=56.5,
        ensemble_std_f=2.0,
        confidence="medium",
        model_sources=["NWS", "GFS", "ECMWF"],
        generated_at=datetime(pred_date.year, pred_date.month, pred_date.day - 1, 15, 0, tzinfo=UTC)
        if pred_date.day > 1
        else datetime(pred_date.year, pred_date.month, 1, 15, 0, tzinfo=UTC),
    )


def _chi_prediction(pred_date: date) -> BracketPrediction:
    return BracketPrediction(
        city="CHI",
        date=pred_date,
        brackets=[
            BracketProbability(
                bracket_label="<=30F", lower_bound_f=None, upper_bound_f=30, probability=0.08
            ),
            BracketProbability(
                bracket_label="31-32F", lower_bound_f=31, upper_bound_f=32, probability=0.18
            ),
            BracketProbability(
                bracket_label="33-34F", lower_bound_f=33, upper_bound_f=34, probability=0.32
            ),
            BracketProbability(
                bracket_label="35-36F", lower_bound_f=35, upper_bound_f=36, probability=0.24
            ),
            BracketProbability(
                bracket_label="37-38F", lower_bound_f=37, upper_bound_f=38, probability=0.12
            ),
            BracketProbability(
                bracket_label=">=39F", lower_bound_f=39, upper_bound_f=None, probability=0.06
            ),
        ],
        ensemble_mean_f=33.8,
        ensemble_std_f=2.5,
        confidence="medium",
        model_sources=["NWS", "GFS"],
        generated_at=datetime(pred_date.year, pred_date.month, pred_date.day - 1, 15, 0, tzinfo=UTC)
        if pred_date.day > 1
        else datetime(pred_date.year, pred_date.month, 1, 15, 0, tzinfo=UTC),
    )


class TestEndToEndBacktest:
    """Full pipeline integration tests."""

    def test_7_day_multi_city_backtest(self):
        """Run a full 7-day, 2-city backtest with synthetic data."""
        config = BacktestConfig(
            cities=["NYC", "CHI"],
            start_date=date(2025, 3, 1),
            end_date=date(2025, 3, 7),
            initial_bankroll_cents=100_000,
            min_ev_threshold=0.02,
            use_kelly=False,
            price_noise_cents=10,
        )

        predictions = []
        settlements = {}
        for day_offset in range(7):
            d = date(2025, 3, 1 + day_offset)
            predictions.append(_nyc_prediction(d))
            predictions.append(_chi_prediction(d))
            settlements[("NYC", d)] = 56.0 + (day_offset % 3 - 1)  # 55, 56, 57 cycle
            settlements[("CHI", d)] = 33.5 + (day_offset % 4 - 1)  # Cycles around

        result = run_backtest(config, predictions, settlements, seed=42)
        result = compute_metrics(result)

        # Structural assertions
        assert result.total_days_simulated == 7
        assert result.config == config
        assert result.total_trades == result.wins + result.losses
        if result.total_trades > 0:
            assert 0.0 <= result.win_rate <= 1.0
        assert isinstance(result.roi_pct, float)
        assert isinstance(result.sharpe_ratio, float)
        assert result.max_drawdown_pct >= 0.0
        assert result.duration_seconds >= 0

    def test_kelly_vs_flat_comparison(self):
        """Run same data with and without Kelly to compare."""
        predictions = [_nyc_prediction(date(2025, 3, d)) for d in range(1, 6)]
        settlements = {("NYC", date(2025, 3, d)): 55.5 + (d % 2) for d in range(1, 6)}

        flat_config = BacktestConfig(
            cities=["NYC"],
            start_date=date(2025, 3, 1),
            end_date=date(2025, 3, 5),
            initial_bankroll_cents=100_000,
            use_kelly=False,
            price_noise_cents=10,
            min_ev_threshold=0.01,
        )
        kelly_config = BacktestConfig(
            cities=["NYC"],
            start_date=date(2025, 3, 1),
            end_date=date(2025, 3, 5),
            initial_bankroll_cents=100_000,
            use_kelly=True,
            kelly_fraction=0.25,
            price_noise_cents=10,
            min_ev_threshold=0.01,
        )

        flat_result = compute_metrics(run_backtest(flat_config, predictions, settlements, seed=42))
        kelly_result = compute_metrics(
            run_backtest(kelly_config, predictions, settlements, seed=42)
        )

        # Both should run without errors
        assert flat_result.total_days_simulated == 5
        assert kelly_result.total_days_simulated == 5

        # Kelly result should have kelly_stats
        assert flat_result.kelly_stats is None
        assert kelly_result.kelly_stats is not None

    def test_consecutive_loss_cooldown_integration(self):
        """Verify consecutive loss cooldown blocks trades."""
        config = BacktestConfig(
            cities=["NYC"],
            start_date=date(2025, 3, 1),
            end_date=date(2025, 3, 1),
            initial_bankroll_cents=100_000,
            consecutive_loss_limit=2,  # Very tight limit
            use_kelly=False,
            price_noise_cents=10,
            min_ev_threshold=0.01,
        )
        # Settlement way outside any bracket means many losses
        predictions = [_nyc_prediction(date(2025, 3, 1))]
        settlements = {("NYC", date(2025, 3, 1)): 80.0}  # Way above all brackets
        result = run_backtest(config, predictions, settlements, seed=42)
        day = result.days[0]
        # With tight loss limit, some trades should be blocked
        total_activity = len(day.trades) + day.trades_blocked_by_risk
        if total_activity > 2:
            assert day.trades_blocked_by_risk > 0

    def test_bankroll_depleted_stops_trading(self):
        """When bankroll goes to zero, trading stops."""
        config = BacktestConfig(
            cities=["NYC"],
            start_date=date(2025, 3, 1),
            end_date=date(2025, 3, 5),
            initial_bankroll_cents=1_000,  # Very small bankroll ($10)
            use_kelly=False,
            price_noise_cents=10,
            min_ev_threshold=0.01,
        )
        predictions = [_nyc_prediction(date(2025, 3, d)) for d in range(1, 6)]
        settlements = {
            ("NYC", date(2025, 3, d)): 80.0  # Always wrong → losses
            for d in range(1, 6)
        }
        result = run_backtest(config, predictions, settlements, seed=42)
        result = compute_metrics(result)

        # Bankroll should be heavily depleted
        final_day = result.days[-1]
        assert final_day.bankroll_end_cents < config.initial_bankroll_cents

    def test_result_serializable(self):
        """BacktestResult should be JSON-serializable via Pydantic."""
        config = BacktestConfig(
            cities=["NYC"],
            start_date=date(2025, 3, 1),
            end_date=date(2025, 3, 3),
            use_kelly=True,
            price_noise_cents=10,
        )
        predictions = [_nyc_prediction(date(2025, 3, d)) for d in range(1, 4)]
        settlements = {("NYC", date(2025, 3, d)): 55.5 for d in range(1, 4)}
        result = run_backtest(config, predictions, settlements, seed=42)
        result = compute_metrics(result)

        # Should serialize without error
        json_str = result.model_dump_json()
        assert isinstance(json_str, str)
        assert "total_trades" in json_str
