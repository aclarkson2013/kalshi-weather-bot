"""Prediction engine — statistical probability distribution across Kalshi brackets.

Orchestrates: ensemble forecast → error distribution → bracket probabilities → confidence.
"""

from __future__ import annotations

from backend.prediction.pipeline import generate_prediction

__all__ = ["generate_prediction"]
