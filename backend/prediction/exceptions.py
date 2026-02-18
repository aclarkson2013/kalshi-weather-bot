"""Prediction-specific exceptions.

These are separate from backend.common.exceptions to keep the prediction module
self-contained. The trading engine can catch PredictionError to handle any
prediction failure gracefully.
"""

from __future__ import annotations


class PredictionError(Exception):
    """Base exception for prediction module errors."""


class InsufficientDataError(PredictionError):
    """Raised when there is not enough data to generate a prediction."""


class EnsembleError(PredictionError):
    """Raised when ensemble calculation fails (no sources, all weights zero)."""


class BracketError(PredictionError):
    """Raised when bracket probability calculation fails."""


class CalibrationError(PredictionError):
    """Raised when calibration process encounters an error."""
