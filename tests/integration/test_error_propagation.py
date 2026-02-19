"""Integration tests: Bad data detection and propagation.

Tests that invalid predictions and market prices are caught by the
validation functions before they can reach the trading engine.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from backend.common.schemas import BracketPrediction, BracketProbability
from backend.prediction.ensemble import calculate_ensemble_forecast
from backend.trading.ev_calculator import validate_market_prices, validate_predictions


def _make_prediction(
    probs: list[float] | None = None,
    bracket_count: int = 6,
    generated_at: datetime | None = None,
) -> BracketPrediction:
    """Helper to build a BracketPrediction for validation tests."""
    default_probs = [0.05, 0.10, 0.35, 0.25, 0.15, 0.10]
    probs = probs or default_probs[:bracket_count]

    brackets = []
    labels = ["<51", "51-53", "53-55", "55-57", "57-59", ">=59"]
    for i in range(bracket_count):
        brackets.append(
            BracketProbability(
                bracket_label=labels[i] if i < len(labels) else f"extra-{i}",
                lower_bound_f=float(51 + i * 2) if i > 0 else None,
                upper_bound_f=float(51 + (i + 1) * 2) if i < bracket_count - 1 else None,
                probability=probs[i],
            )
        )

    return BracketPrediction(
        city="NYC",
        date=datetime.now(UTC).date(),
        brackets=brackets,
        ensemble_mean_f=54.2,
        ensemble_std_f=2.5,
        confidence="medium",
        model_sources=["NWS", "GFS", "ECMWF", "ICON"],
        generated_at=generated_at or datetime.now(UTC),
    )


def test_stale_prediction_blocked() -> None:
    """Prediction older than 2 hours → validate_predictions returns False."""
    stale_time = datetime.now(UTC) - timedelta(hours=3)
    pred = _make_prediction(generated_at=stale_time)
    assert validate_predictions([pred]) is False


def test_nan_probability_blocked() -> None:
    """NaN probability → validate_predictions returns False."""
    pred = _make_prediction()
    # Manually inject NaN (bypassing Pydantic validator)
    pred.brackets[2].probability = float("nan")
    assert validate_predictions([pred]) is False


def test_wrong_bracket_count() -> None:
    """5 brackets instead of 6 → validate_predictions returns False."""
    # Build a 5-bracket prediction by adjusting probs to sum to ~1.0
    five_probs = [0.10, 0.20, 0.35, 0.25, 0.10]
    pred = _make_prediction(probs=five_probs, bracket_count=5)
    assert validate_predictions([pred]) is False


def test_probabilities_dont_sum() -> None:
    """Probabilities summing to 0.5 → validate_predictions returns False.

    Note: BracketPrediction's Pydantic validator rejects sum outside 0.95-1.05,
    so we must set probabilities after construction.
    """
    pred = _make_prediction()
    # Halve all probabilities → sum ≈ 0.5
    for b in pred.brackets:
        b.probability = b.probability / 2.0
    assert validate_predictions([pred]) is False


def test_invalid_market_price_zero() -> None:
    """Price of 0 → validate_market_prices returns False."""
    prices = {"53-55": 0, "55-57": 25}
    assert validate_market_prices(prices) is False


def test_invalid_market_price_hundred() -> None:
    """Price of 100 → validate_market_prices returns False."""
    prices = {"53-55": 100, "55-57": 25}
    assert validate_market_prices(prices) is False


def test_float_market_price() -> None:
    """Float price (22.5) → validate_market_prices returns False."""
    prices = {"53-55": 22.5, "55-57": 25}
    assert validate_market_prices(prices) is False


def test_empty_forecasts_raises() -> None:
    """Empty forecast list → ValueError from ensemble calculation."""
    with pytest.raises(ValueError, match="No forecasts provided"):
        calculate_ensemble_forecast([])
