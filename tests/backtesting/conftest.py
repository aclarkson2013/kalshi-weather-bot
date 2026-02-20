"""Shared fixtures for backtesting tests."""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest

from backend.backtesting.schemas import BacktestConfig, SimulatedTrade
from backend.common.schemas import (
    BracketPrediction,
    BracketProbability,
)


@pytest.fixture
def default_config() -> BacktestConfig:
    """A default backtest config for a 7-day window."""
    return BacktestConfig(
        cities=["NYC", "CHI"],
        start_date=date(2025, 3, 1),
        end_date=date(2025, 3, 7),
        initial_bankroll_cents=100_000,
        min_ev_threshold=0.02,
        use_kelly=True,
        kelly_fraction=0.25,
        max_daily_trades=20,
        consecutive_loss_limit=5,
    )


@pytest.fixture
def single_city_config() -> BacktestConfig:
    """Config targeting only NYC for 3 days."""
    return BacktestConfig(
        cities=["NYC"],
        start_date=date(2025, 3, 1),
        end_date=date(2025, 3, 3),
        initial_bankroll_cents=50_000,
        min_ev_threshold=0.03,
        use_kelly=False,
    )


@pytest.fixture
def sample_prediction_nyc() -> BracketPrediction:
    """A realistic NYC prediction with clear edge on bracket 3."""
    return BracketPrediction(
        city="NYC",
        date=date(2025, 3, 1),
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
        generated_at=datetime(2025, 2, 28, 15, 0, 0, tzinfo=UTC),
    )


@pytest.fixture
def sample_prediction_chi() -> BracketPrediction:
    """A realistic Chicago prediction."""
    return BracketPrediction(
        city="CHI",
        date=date(2025, 3, 1),
        brackets=[
            BracketProbability(
                bracket_label="<=30F", lower_bound_f=None, upper_bound_f=30, probability=0.10
            ),
            BracketProbability(
                bracket_label="31-32F", lower_bound_f=31, upper_bound_f=32, probability=0.20
            ),
            BracketProbability(
                bracket_label="33-34F", lower_bound_f=33, upper_bound_f=34, probability=0.30
            ),
            BracketProbability(
                bracket_label="35-36F", lower_bound_f=35, upper_bound_f=36, probability=0.22
            ),
            BracketProbability(
                bracket_label="37-38F", lower_bound_f=37, upper_bound_f=38, probability=0.11
            ),
            BracketProbability(
                bracket_label=">=39F", lower_bound_f=39, upper_bound_f=None, probability=0.07
            ),
        ],
        ensemble_mean_f=33.5,
        ensemble_std_f=2.5,
        confidence="medium",
        model_sources=["NWS", "GFS"],
        generated_at=datetime(2025, 2, 28, 15, 0, 0, tzinfo=UTC),
    )


@pytest.fixture
def sample_market_prices_nyc() -> dict[str, int]:
    """Market YES prices for NYC brackets (model has edge on 55-56F)."""
    return {
        "<=52F": 5,
        "53-54F": 12,
        "55-56F": 20,  # Model says 35% but market is 20% → +EV on YES
        "57-58F": 30,
        "59-60F": 18,
        ">=61F": 8,
    }


@pytest.fixture
def sample_market_tickers_nyc() -> dict[str, str]:
    """Market tickers for NYC brackets."""
    return {
        "<=52F": "KXHIGHNY-25MAR01-B1",
        "53-54F": "KXHIGHNY-25MAR01-B2",
        "55-56F": "KXHIGHNY-25MAR01-B3",
        "57-58F": "KXHIGHNY-25MAR01-B4",
        "59-60F": "KXHIGHNY-25MAR01-B5",
        ">=61F": "KXHIGHNY-25MAR01-B6",
    }


@pytest.fixture
def sample_market_prices_chi() -> dict[str, int]:
    """Market YES prices for Chicago brackets."""
    return {
        "<=30F": 8,
        "31-32F": 15,
        "33-34F": 18,  # Model says 30% but market is 18% → +EV on YES
        "35-36F": 25,
        "37-38F": 15,
        ">=39F": 7,
    }


@pytest.fixture
def sample_market_tickers_chi() -> dict[str, str]:
    """Market tickers for Chicago brackets."""
    return {
        "<=30F": "KXHIGHCH-25MAR01-B1",
        "31-32F": "KXHIGHCH-25MAR01-B2",
        "33-34F": "KXHIGHCH-25MAR01-B3",
        "35-36F": "KXHIGHCH-25MAR01-B4",
        "37-38F": "KXHIGHCH-25MAR01-B5",
        ">=39F": "KXHIGHCH-25MAR01-B6",
    }


def make_winning_trade(
    day: date = date(2025, 3, 1),
    city: str = "NYC",
    price_cents: int = 20,
    quantity: int = 1,
) -> SimulatedTrade:
    """Helper to create a winning SimulatedTrade."""
    # YES side win: pnl = (100 - price) * qty - fees * qty - 0 (no loss cost)
    # Simplified: pnl = (100 * qty) - (price * qty) - fees
    cost = price_cents * quantity
    payout = 100 * quantity
    fee_per = max(1, int((100 - price_cents) * 0.15))
    fees = fee_per * quantity
    pnl = payout - cost - fees
    return SimulatedTrade(
        day=day,
        city=city,
        bracket_label="55-56F",
        side="yes",
        price_cents=price_cents,
        quantity=quantity,
        model_probability=0.35,
        market_probability=0.20,
        ev=0.05,
        confidence="medium",
        actual_temp_f=55.5,
        won=True,
        pnl_cents=pnl,
        fees_cents=fees,
        bankroll_after_cents=100_000 + pnl,
    )


def make_losing_trade(
    day: date = date(2025, 3, 1),
    city: str = "NYC",
    price_cents: int = 20,
    quantity: int = 1,
) -> SimulatedTrade:
    """Helper to create a losing SimulatedTrade."""
    cost = price_cents * quantity
    return SimulatedTrade(
        day=day,
        city=city,
        bracket_label="55-56F",
        side="yes",
        price_cents=price_cents,
        quantity=quantity,
        model_probability=0.35,
        market_probability=0.20,
        ev=0.05,
        confidence="medium",
        actual_temp_f=58.0,
        won=False,
        pnl_cents=-cost,
        fees_cents=0,
        bankroll_after_cents=100_000 - cost,
    )
