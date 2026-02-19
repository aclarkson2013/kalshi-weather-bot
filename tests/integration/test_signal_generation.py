"""Integration tests: Prediction → Trade Signals.

Tests validate_predictions() + validate_market_prices() + scan_all_brackets()
as a chain. Pure functions — no DB needed.
"""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest

from backend.common.schemas import BracketPrediction, BracketProbability
from backend.trading.ev_calculator import (
    scan_all_brackets,
    validate_market_prices,
    validate_predictions,
)


def _make_prediction(
    probs: list[float] | None = None,
    generated_at: datetime | None = None,
) -> BracketPrediction:
    """Helper to build a BracketPrediction with given probabilities."""
    probs = probs or [0.05, 0.10, 0.35, 0.25, 0.15, 0.10]
    return BracketPrediction(
        city="NYC",
        date=date(2026, 2, 20),
        brackets=[
            BracketProbability(
                bracket_label="<51",
                lower_bound_f=None,
                upper_bound_f=51.0,
                probability=probs[0],
            ),
            BracketProbability(
                bracket_label="51-53",
                lower_bound_f=51.0,
                upper_bound_f=53.0,
                probability=probs[1],
            ),
            BracketProbability(
                bracket_label="53-55",
                lower_bound_f=53.0,
                upper_bound_f=55.0,
                probability=probs[2],
            ),
            BracketProbability(
                bracket_label="55-57",
                lower_bound_f=55.0,
                upper_bound_f=57.0,
                probability=probs[3],
            ),
            BracketProbability(
                bracket_label="57-59",
                lower_bound_f=57.0,
                upper_bound_f=59.0,
                probability=probs[4],
            ),
            BracketProbability(
                bracket_label=">=59",
                lower_bound_f=59.0,
                upper_bound_f=None,
                probability=probs[5],
            ),
        ],
        ensemble_mean_f=54.2,
        ensemble_std_f=2.5,
        confidence="medium",
        model_sources=["NWS", "GFS", "ECMWF", "ICON"],
        generated_at=generated_at or datetime.now(UTC),
    )


@pytest.fixture
def prediction() -> BracketPrediction:
    """A fresh BracketPrediction for scanning."""
    return _make_prediction()


@pytest.fixture
def prices() -> dict[str, int]:
    """Market prices with 53-55 underpriced (model=35%, market=15c)."""
    return {
        "<51": 5,
        "51-53": 12,
        "53-55": 15,  # Underpriced vs 35% model → +EV YES
        "55-57": 50,  # Overpriced vs 25% model → possible +EV NO
        "57-59": 10,
        ">=59": 8,
    }


@pytest.fixture
def tickers() -> dict[str, str]:
    """Market ticker strings keyed by bracket label."""
    return {
        "<51": "KXHIGHNY-26FEB20-B1",
        "51-53": "KXHIGHNY-26FEB20-B2",
        "53-55": "KXHIGHNY-26FEB20-B3",
        "55-57": "KXHIGHNY-26FEB20-B4",
        "57-59": "KXHIGHNY-26FEB20-B5",
        ">=59": "KXHIGHNY-26FEB20-B6",
    }


def test_prediction_to_signals_happy_path(
    prediction: BracketPrediction,
    prices: dict[str, int],
    tickers: dict[str, str],
) -> None:
    """Divergent model vs market probs → at least 1 signal."""
    signals = scan_all_brackets(prediction, prices, tickers, min_ev_threshold=0.01)
    assert len(signals) >= 1
    for s in signals:
        assert s.ev >= 0.01


def test_signals_sorted_by_ev_descending(
    prediction: BracketPrediction,
    prices: dict[str, int],
    tickers: dict[str, str],
) -> None:
    """Signals should be sorted by EV descending (best first)."""
    signals = scan_all_brackets(prediction, prices, tickers, min_ev_threshold=0.01)
    if len(signals) > 1:
        for i in range(len(signals) - 1):
            assert signals[i].ev >= signals[i + 1].ev


def test_signal_fields_match_inputs(
    prediction: BracketPrediction,
    prices: dict[str, int],
    tickers: dict[str, str],
) -> None:
    """Signal city, bracket, and price should match inputs."""
    signals = scan_all_brackets(prediction, prices, tickers, min_ev_threshold=0.01)
    for s in signals:
        assert s.city == "NYC"
        assert s.bracket in prices
        assert s.price_cents == prices[s.bracket]
        assert s.market_ticker == tickers[s.bracket]


def test_no_signals_when_market_matches_model() -> None:
    """When market prices align with model probs, no +EV signals."""
    # Set market prices to match model probs closely (± fees)
    pred = _make_prediction(probs=[0.05, 0.10, 0.35, 0.25, 0.15, 0.10])
    aligned_prices = {
        "<51": 5,
        "51-53": 10,
        "53-55": 35,
        "55-57": 25,
        "57-59": 15,
        ">=59": 10,
    }
    tickers = {
        "<51": "B1",
        "51-53": "B2",
        "53-55": "B3",
        "55-57": "B4",
        "57-59": "B5",
        ">=59": "B6",
    }
    signals = scan_all_brackets(pred, aligned_prices, tickers, min_ev_threshold=0.05)
    # With conservative EV (fees subtracted unconditionally), aligned prices
    # should produce 0 or very few signals above the 5c threshold.
    # Each trade pays at least 1c fee, so most aligned brackets won't clear 5c EV.
    assert len(signals) == 0


def test_validate_then_scan_full_flow(
    prediction: BracketPrediction,
    prices: dict[str, int],
    tickers: dict[str, str],
) -> None:
    """Full defensive chain: validate predictions → validate prices → scan."""
    assert validate_predictions([prediction]) is True
    assert validate_market_prices(prices) is True

    signals = scan_all_brackets(prediction, prices, tickers, min_ev_threshold=0.01)
    assert isinstance(signals, list)
    for s in signals:
        assert s.ev >= 0.01


def test_signals_respect_ev_threshold(
    prediction: BracketPrediction,
    prices: dict[str, int],
    tickers: dict[str, str],
) -> None:
    """All returned signals must be >= the specified threshold."""
    threshold = 0.03
    signals = scan_all_brackets(prediction, prices, tickers, min_ev_threshold=threshold)
    for s in signals:
        assert s.ev >= threshold


def test_both_yes_and_no_sides_possible() -> None:
    """Crafted probs can produce signals on both YES and NO sides."""
    # 53-55: model=60%, market=15c → strong YES signal
    # 55-57: model=5%, market=50c → strong NO signal
    pred = _make_prediction(probs=[0.05, 0.05, 0.60, 0.05, 0.20, 0.05])
    prices = {
        "<51": 5,
        "51-53": 5,
        "53-55": 15,  # Way underpriced for 60% model → YES
        "55-57": 50,  # Way overpriced for 5% model → NO
        "57-59": 20,
        ">=59": 5,
    }
    tickers = {k: f"T-{k}" for k in prices}
    signals = scan_all_brackets(pred, prices, tickers, min_ev_threshold=0.01)

    sides = {s.side for s in signals}
    assert "yes" in sides
    assert "no" in sides


def test_missing_bracket_price_skipped(
    prediction: BracketPrediction,
    tickers: dict[str, str],
) -> None:
    """Missing price for a bracket → other brackets still scanned."""
    # Only provide 4 of 6 brackets
    partial_prices = {
        "<51": 5,
        "51-53": 12,
        "53-55": 15,
        "55-57": 50,
        # "57-59" and ">=59" missing
    }
    signals = scan_all_brackets(prediction, partial_prices, tickers, min_ev_threshold=0.01)
    # Should still return signals for the 4 brackets that have prices
    for s in signals:
        assert s.bracket in partial_prices
