"""Tests for data_loader — synthetic prices, tickers, grouping, filtering."""

from __future__ import annotations

import random
from datetime import UTC, date, datetime

from backend.backtesting.data_loader import (
    filter_predictions_by_config,
    generate_settlement_temps,
    generate_synthetic_prices,
    generate_synthetic_tickers,
    group_predictions_by_day,
)
from backend.common.schemas import BracketPrediction, BracketProbability


class TestGenerateSyntheticPrices:
    """Tests for generate_synthetic_prices()."""

    def test_generates_price_for_each_bracket(self, sample_prediction_nyc):
        prices = generate_synthetic_prices(sample_prediction_nyc)
        assert len(prices) == 6
        for bracket in sample_prediction_nyc.brackets:
            assert bracket.bracket_label in prices

    def test_prices_in_valid_range(self, sample_prediction_nyc):
        rng = random.Random(42)
        prices = generate_synthetic_prices(sample_prediction_nyc, noise_cents=20, rng=rng)
        for price in prices.values():
            assert 1 <= price <= 99

    def test_zero_noise_gives_deterministic_prices(self, sample_prediction_nyc):
        prices = generate_synthetic_prices(sample_prediction_nyc, noise_cents=0)
        # 35% probability → 35 cents (truncated)
        assert prices["55-56F"] == 35

    def test_seed_reproducibility(self, sample_prediction_nyc):
        prices1 = generate_synthetic_prices(
            sample_prediction_nyc, noise_cents=5, rng=random.Random(42)
        )
        prices2 = generate_synthetic_prices(
            sample_prediction_nyc, noise_cents=5, rng=random.Random(42)
        )
        assert prices1 == prices2

    def test_different_seeds_give_different_prices(self, sample_prediction_nyc):
        prices1 = generate_synthetic_prices(
            sample_prediction_nyc, noise_cents=10, rng=random.Random(1)
        )
        prices2 = generate_synthetic_prices(
            sample_prediction_nyc, noise_cents=10, rng=random.Random(99)
        )
        # At least some prices should differ
        assert prices1 != prices2

    def test_low_probability_clamps_to_minimum(self):
        """A bracket with very low probability should still have price >= 1."""
        pred = BracketPrediction(
            city="NYC",
            date=date(2025, 3, 1),
            brackets=[
                BracketProbability(
                    bracket_label=f"B{i}",
                    probability=prob,
                )
                for i, prob in enumerate([0.01, 0.01, 0.01, 0.01, 0.01, 0.95], start=1)
            ],
            ensemble_mean_f=56.0,
            ensemble_std_f=2.0,
            confidence="medium",
            model_sources=["NWS"],
            generated_at=datetime(2025, 2, 28, 15, 0, 0, tzinfo=UTC),
        )
        # With large negative noise, should clamp to 1
        rng = random.Random(42)
        prices = generate_synthetic_prices(pred, noise_cents=5, rng=rng)
        for price in prices.values():
            assert price >= 1


class TestGenerateSyntheticTickers:
    """Tests for generate_synthetic_tickers()."""

    def test_generates_ticker_for_each_bracket(self, sample_prediction_nyc):
        tickers = generate_synthetic_tickers(sample_prediction_nyc)
        assert len(tickers) == 6

    def test_ticker_format(self, sample_prediction_nyc):
        tickers = generate_synthetic_tickers(sample_prediction_nyc)
        # NYC, date 2025-03-01 → KXHIGHNY-25MAR01-B1 through B6
        assert tickers["<=52F"] == "KXHIGHNY-25MAR01-B1"
        assert tickers[">=61F"] == "KXHIGHNY-25MAR01-B6"

    def test_chi_prefix(self, sample_prediction_chi):
        tickers = generate_synthetic_tickers(sample_prediction_chi)
        first = list(tickers.values())[0]
        assert first.startswith("KXHIGHCH-")


class TestGroupPredictionsByDay:
    """Tests for group_predictions_by_day()."""

    def test_groups_by_date_and_city(self, sample_prediction_nyc, sample_prediction_chi):
        grouped = group_predictions_by_day([sample_prediction_nyc, sample_prediction_chi])
        assert date(2025, 3, 1) in grouped
        assert "NYC" in grouped[date(2025, 3, 1)]
        assert "CHI" in grouped[date(2025, 3, 1)]

    def test_multiple_dates(self, sample_prediction_nyc):
        # Create a second prediction for a different date
        pred2 = sample_prediction_nyc.model_copy(update={"date": date(2025, 3, 2)})
        grouped = group_predictions_by_day([sample_prediction_nyc, pred2])
        assert len(grouped) == 2
        assert date(2025, 3, 1) in grouped
        assert date(2025, 3, 2) in grouped

    def test_empty_list(self):
        grouped = group_predictions_by_day([])
        assert grouped == {}


class TestFilterPredictionsByConfig:
    """Tests for filter_predictions_by_config()."""

    def test_filters_by_city(self, sample_prediction_nyc, sample_prediction_chi):
        filtered = filter_predictions_by_config(
            [sample_prediction_nyc, sample_prediction_chi],
            cities=["NYC"],
            start_date=date(2025, 3, 1),
            end_date=date(2025, 3, 7),
        )
        assert len(filtered) == 1
        assert filtered[0].city == "NYC"

    def test_filters_by_date_range(self, sample_prediction_nyc):
        pred_before = sample_prediction_nyc.model_copy(update={"date": date(2025, 2, 28)})
        pred_after = sample_prediction_nyc.model_copy(update={"date": date(2025, 3, 8)})
        filtered = filter_predictions_by_config(
            [pred_before, sample_prediction_nyc, pred_after],
            cities=["NYC"],
            start_date=date(2025, 3, 1),
            end_date=date(2025, 3, 7),
        )
        assert len(filtered) == 1
        assert filtered[0].date == date(2025, 3, 1)

    def test_inclusive_boundaries(self, sample_prediction_nyc):
        filtered = filter_predictions_by_config(
            [sample_prediction_nyc],
            cities=["NYC"],
            start_date=date(2025, 3, 1),
            end_date=date(2025, 3, 1),
        )
        assert len(filtered) == 1

    def test_empty_when_no_match(self, sample_prediction_nyc):
        filtered = filter_predictions_by_config(
            [sample_prediction_nyc],
            cities=["MIA"],
            start_date=date(2025, 3, 1),
            end_date=date(2025, 3, 7),
        )
        assert len(filtered) == 0


class TestGenerateSettlementTemps:
    """Tests for generate_settlement_temps()."""

    def test_generates_temp_for_each_prediction(self, sample_prediction_nyc, sample_prediction_chi):
        temps = generate_settlement_temps([sample_prediction_nyc, sample_prediction_chi])
        assert ("NYC", date(2025, 3, 1)) in temps
        assert ("CHI", date(2025, 3, 1)) in temps

    def test_seed_reproducibility(self, sample_prediction_nyc):
        temps1 = generate_settlement_temps([sample_prediction_nyc], rng=random.Random(42))
        temps2 = generate_settlement_temps([sample_prediction_nyc], rng=random.Random(42))
        assert temps1 == temps2

    def test_temps_near_ensemble_mean(self, sample_prediction_nyc):
        """With many samples, average should be close to ensemble mean."""
        rng = random.Random(42)
        temps_list = []
        for _ in range(1000):
            temps = generate_settlement_temps([sample_prediction_nyc], rng=rng)
            temps_list.append(temps[("NYC", date(2025, 3, 1))])
        avg = sum(temps_list) / len(temps_list)
        assert abs(avg - sample_prediction_nyc.ensemble_mean_f) < 0.5
