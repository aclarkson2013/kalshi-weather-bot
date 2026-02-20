"""Backtesting-specific exceptions."""

from __future__ import annotations

from backend.common.exceptions import BozBaseException


class BacktestError(BozBaseException):
    """General backtesting error (bad config, engine failure, etc.)."""


class InsufficientDataError(BozBaseException):
    """Not enough historical data to run the requested backtest."""
