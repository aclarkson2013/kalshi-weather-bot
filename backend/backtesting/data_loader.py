"""Data loader for backtesting — loads historical data or generates synthetic prices.

Provides functions to:
1. Generate synthetic market prices from model probabilities + noise
2. Generate synthetic market tickers
3. Group predictions by (city, date) for day-by-day simulation
4. Filter data to the requested date range

Usage:
    from backend.backtesting.data_loader import generate_synthetic_prices

    prices = generate_synthetic_prices(prediction, noise_cents=5, seed=42)
"""

from __future__ import annotations

import random
from datetime import date

from backend.common.logging import get_logger
from backend.common.schemas import BracketPrediction, CityCode

logger = get_logger("BACKTEST")

# Kalshi ticker prefix by city
TICKER_PREFIX: dict[str, str] = {
    "NYC": "KXHIGHNY",
    "CHI": "KXHIGHCH",
    "MIA": "KXHIGHMI",
    "AUS": "KXHIGHAU",
}


def generate_synthetic_prices(
    prediction: BracketPrediction,
    noise_cents: int = 5,
    rng: random.Random | None = None,
) -> dict[str, int]:
    """Generate synthetic market YES prices from model probabilities.

    Converts each bracket's probability to a price in cents (1-99),
    then adds random noise to simulate market mispricing.

    Args:
        prediction: A BracketPrediction with bracket probabilities.
        noise_cents: Max noise in either direction (default ±5 cents).
        rng: Random number generator for reproducibility.

    Returns:
        Dict mapping bracket_label → YES price in cents.
    """
    if rng is None:
        rng = random.Random()

    prices: dict[str, int] = {}
    for bracket in prediction.brackets:
        # Convert probability to implied price
        base_price = int(bracket.probability * 100)

        # Add noise
        if noise_cents > 0:
            noise = rng.randint(-noise_cents, noise_cents)
            price = base_price + noise
        else:
            price = base_price

        # Clamp to valid Kalshi range [1, 99]
        price = max(1, min(99, price))
        prices[bracket.bracket_label] = price

    return prices


def generate_synthetic_tickers(
    prediction: BracketPrediction,
) -> dict[str, str]:
    """Generate synthetic Kalshi market tickers for a prediction.

    Format: {PREFIX}-{YYMMMDD}-B{N} where N is the bracket index (1-6).

    Args:
        prediction: A BracketPrediction with city and date.

    Returns:
        Dict mapping bracket_label → ticker string.
    """
    prefix = TICKER_PREFIX.get(prediction.city, "KXHIGH")
    date_str = prediction.date.strftime("%y%b%d").upper()

    tickers: dict[str, str] = {}
    for i, bracket in enumerate(prediction.brackets, start=1):
        tickers[bracket.bracket_label] = f"{prefix}-{date_str}-B{i}"

    return tickers


def group_predictions_by_day(
    predictions: list[BracketPrediction],
) -> dict[date, dict[str, BracketPrediction]]:
    """Group predictions by (date, city) for day-by-day simulation.

    Args:
        predictions: List of BracketPrediction objects.

    Returns:
        Dict mapping date → {city → prediction}.
    """
    grouped: dict[date, dict[str, BracketPrediction]] = {}
    for pred in predictions:
        if pred.date not in grouped:
            grouped[pred.date] = {}
        grouped[pred.date][pred.city] = pred

    return grouped


def filter_predictions_by_config(
    predictions: list[BracketPrediction],
    cities: list[CityCode],
    start_date: date,
    end_date: date,
) -> list[BracketPrediction]:
    """Filter predictions to the backtest's city list and date range.

    Args:
        predictions: All available predictions.
        cities: Cities to include.
        start_date: Start of date range (inclusive).
        end_date: End of date range (inclusive).

    Returns:
        Filtered list of predictions.
    """
    return [p for p in predictions if p.city in cities and start_date <= p.date <= end_date]


def generate_settlement_temps(
    predictions: list[BracketPrediction],
    rng: random.Random | None = None,
) -> dict[tuple[str, date], float]:
    """Generate synthetic settlement temperatures from predictions.

    Uses the ensemble mean ± some random noise based on the std deviation.
    This gives realistic temperature outcomes for backtesting.

    Args:
        predictions: List of predictions to generate settlements for.
        rng: Random number generator for reproducibility.

    Returns:
        Dict mapping (city, date) → actual high temperature.
    """
    if rng is None:
        rng = random.Random()

    settlements: dict[tuple[str, date], float] = {}
    for pred in predictions:
        # Temperature from normal distribution centered on ensemble mean
        noise = rng.gauss(0, pred.ensemble_std_f)
        temp = round(pred.ensemble_mean_f + noise, 1)
        settlements[(pred.city, pred.date)] = temp

    return settlements
