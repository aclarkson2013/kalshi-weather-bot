"""Test data factories for generating realistic test data.

Usage:
    from tests.factories import make_bracket_prediction, make_trade_signal

    prediction = make_bracket_prediction(city="CHI", mean_temp=45.0)
    signal = make_trade_signal(ev=0.08, price_cents=30)
"""

from __future__ import annotations

from datetime import UTC, date, datetime

from backend.common.schemas import (
    BracketPrediction,
    BracketProbability,
    TradeSignal,
)


def make_bracket_prediction(
    city: str = "NYC",
    target_date: date | None = None,
    mean_temp: float = 56.0,
    std_temp: float = 2.0,
    confidence: str = "medium",
    **overrides,
) -> BracketPrediction:
    """Create a realistic BracketPrediction with sensible defaults.

    Generates 6 brackets centered around mean_temp. Override any field
    by passing it as a keyword argument.
    """
    if target_date is None:
        target_date = date(2025, 2, 15)

    # Generate realistic brackets around the mean
    center = int(mean_temp)
    brackets = [
        BracketProbability(
            bracket_label=f"≤{center - 4}°F",
            lower_bound_f=None,
            upper_bound_f=center - 4,
            probability=0.08,
        ),
        BracketProbability(
            bracket_label=f"{center - 3}-{center - 2}°F",
            lower_bound_f=center - 3,
            upper_bound_f=center - 2,
            probability=0.15,
        ),
        BracketProbability(
            bracket_label=f"{center - 1}-{center}°F",
            lower_bound_f=center - 1,
            upper_bound_f=center,
            probability=0.30,
        ),
        BracketProbability(
            bracket_label=f"{center + 1}-{center + 2}°F",
            lower_bound_f=center + 1,
            upper_bound_f=center + 2,
            probability=0.28,
        ),
        BracketProbability(
            bracket_label=f"{center + 3}-{center + 4}°F",
            lower_bound_f=center + 3,
            upper_bound_f=center + 4,
            probability=0.12,
        ),
        BracketProbability(
            bracket_label=f"≥{center + 5}°F",
            lower_bound_f=center + 5,
            upper_bound_f=None,
            probability=0.07,
        ),
    ]

    defaults = {
        "city": city,
        "date": target_date,
        "brackets": brackets,
        "ensemble_mean_f": mean_temp,
        "ensemble_std_f": std_temp,
        "confidence": confidence,
        "model_sources": ["NWS", "GFS", "ECMWF", "ICON"],
        "generated_at": datetime(2025, 2, 14, 15, 0, 0, tzinfo=UTC),
    }
    defaults.update(overrides)
    return BracketPrediction(**defaults)


def make_trade_signal(
    city: str = "NYC",
    bracket: str = "55-56°F",
    side: str = "yes",
    price_cents: int = 22,
    ev: float = 0.05,
    confidence: str = "medium",
    **overrides,
) -> TradeSignal:
    """Create a TradeSignal with sensible defaults.

    Override any field by passing it as a keyword argument.
    """
    defaults = {
        "city": city,
        "bracket": bracket,
        "side": side,
        "price_cents": price_cents,
        "quantity": 1,
        "model_probability": 0.30,
        "market_probability": price_cents / 100,
        "ev": ev,
        "confidence": confidence,
        "market_ticker": f"KXHIGH{city[:2]}-25FEB15-B3",
        "reasoning": f"Model edge: EV=${ev:.2f}",
    }
    defaults.update(overrides)
    return TradeSignal(**defaults)
