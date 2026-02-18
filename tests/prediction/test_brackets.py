"""Tests for backend.prediction.brackets — bracket probability calculation.

Validates that ``calculate_bracket_probabilities`` produces a correct
normal-CDF-based probability distribution across Kalshi brackets.
"""

from __future__ import annotations

import pytest

from backend.prediction.brackets import calculate_bracket_probabilities

# ─── Local bracket fixture (also available via conftest) ───

SAMPLE_BRACKETS: list[dict] = [
    {"lower_bound_f": None, "upper_bound_f": 51.0, "label": "<51"},
    {"lower_bound_f": 51.0, "upper_bound_f": 53.0, "label": "51-53"},
    {"lower_bound_f": 53.0, "upper_bound_f": 55.0, "label": "53-55"},
    {"lower_bound_f": 55.0, "upper_bound_f": 57.0, "label": "55-57"},
    {"lower_bound_f": 57.0, "upper_bound_f": 59.0, "label": "57-59"},
    {"lower_bound_f": 59.0, "upper_bound_f": None, "label": ">=59"},
]


# ═══════════════════════════════════════════════════════════════
# Probability invariants
# ═══════════════════════════════════════════════════════════════


def test_probabilities_sum_to_one() -> None:
    """All bracket probabilities must sum to 1.0 within 1e-9 tolerance."""
    results = calculate_bracket_probabilities(
        ensemble_forecast_f=54.0,
        error_std_f=2.0,
        brackets=SAMPLE_BRACKETS,
    )
    total = sum(r.probability for r in results)
    assert abs(total - 1.0) < 1e-9


def test_six_brackets_returned() -> None:
    """Output list length matches the input bracket count (6)."""
    results = calculate_bracket_probabilities(
        ensemble_forecast_f=54.0,
        error_std_f=2.0,
        brackets=SAMPLE_BRACKETS,
    )
    assert len(results) == 6


def test_all_probabilities_non_negative() -> None:
    """Every probability must be in [0, 1]."""
    results = calculate_bracket_probabilities(
        ensemble_forecast_f=54.0,
        error_std_f=2.0,
        brackets=SAMPLE_BRACKETS,
    )
    for r in results:
        assert 0.0 <= r.probability <= 1.0


# ═══════════════════════════════════════════════════════════════
# Distribution shape
# ═══════════════════════════════════════════════════════════════


def test_most_likely_bracket_contains_forecast() -> None:
    """The bracket containing 54F (53-55) should have the highest probability."""
    results = calculate_bracket_probabilities(
        ensemble_forecast_f=54.0,
        error_std_f=2.0,
        brackets=SAMPLE_BRACKETS,
    )
    probs = [r.probability for r in results]
    max_idx = probs.index(max(probs))
    assert results[max_idx].bracket_label == "53-55"


def test_extreme_low_temperature() -> None:
    """Forecast far below brackets concentrates > 99 % in the bottom bracket."""
    results = calculate_bracket_probabilities(
        ensemble_forecast_f=30.0,
        error_std_f=2.0,
        brackets=SAMPLE_BRACKETS,
    )
    assert results[0].probability > 0.99


def test_extreme_high_temperature() -> None:
    """Forecast far above brackets concentrates > 99 % in the top bracket."""
    results = calculate_bracket_probabilities(
        ensemble_forecast_f=80.0,
        error_std_f=2.0,
        brackets=SAMPLE_BRACKETS,
    )
    assert results[-1].probability > 0.99


def test_very_small_std_concentrates() -> None:
    """A tiny std concentrates nearly all probability in the containing bracket."""
    results = calculate_bracket_probabilities(
        ensemble_forecast_f=54.0,
        error_std_f=0.1,
        brackets=SAMPLE_BRACKETS,
    )
    # 54F falls in 53-55 bracket
    assert results[2].probability > 0.99


def test_large_std_spreads_evenly() -> None:
    """A very large std means no single bracket dominates (all < 0.5)."""
    results = calculate_bracket_probabilities(
        ensemble_forecast_f=54.0,
        error_std_f=20.0,
        brackets=SAMPLE_BRACKETS,
    )
    for r in results:
        assert r.probability < 0.5


# ═══════════════════════════════════════════════════════════════
# Error handling
# ═══════════════════════════════════════════════════════════════


def test_error_std_zero_raises() -> None:
    """Zero std dev is invalid and must raise ValueError."""
    with pytest.raises(ValueError, match="positive"):
        calculate_bracket_probabilities(
            ensemble_forecast_f=54.0,
            error_std_f=0.0,
            brackets=SAMPLE_BRACKETS,
        )


def test_negative_std_raises() -> None:
    """Negative std dev is invalid and must raise ValueError."""
    with pytest.raises(ValueError, match="positive"):
        calculate_bracket_probabilities(
            ensemble_forecast_f=54.0,
            error_std_f=-1.0,
            brackets=SAMPLE_BRACKETS,
        )


def test_empty_brackets_raises() -> None:
    """An empty brackets list must raise ValueError."""
    with pytest.raises(ValueError, match="empty"):
        calculate_bracket_probabilities(
            ensemble_forecast_f=54.0,
            error_std_f=2.0,
            brackets=[],
        )


# ═══════════════════════════════════════════════════════════════
# Boundary and structural checks
# ═══════════════════════════════════════════════════════════════


def test_boundary_temperature() -> None:
    """Forecast exactly on a bracket boundary (53.0) still produces valid output."""
    results = calculate_bracket_probabilities(
        ensemble_forecast_f=53.0,
        error_std_f=2.0,
        brackets=SAMPLE_BRACKETS,
    )
    total = sum(r.probability for r in results)
    assert abs(total - 1.0) < 1e-9
    for r in results:
        assert 0.0 <= r.probability <= 1.0


def test_bracket_labels_preserved() -> None:
    """Output bracket labels must match the input labels in order."""
    results = calculate_bracket_probabilities(
        ensemble_forecast_f=54.0,
        error_std_f=2.0,
        brackets=SAMPLE_BRACKETS,
    )
    expected_labels = [b["label"] for b in SAMPLE_BRACKETS]
    actual_labels = [r.bracket_label for r in results]
    assert actual_labels == expected_labels


def test_normalization_handles_float_drift() -> None:
    """After normalization, probabilities sum to exactly 1.0."""
    results = calculate_bracket_probabilities(
        ensemble_forecast_f=55.0,
        error_std_f=2.5,
        brackets=SAMPLE_BRACKETS,
    )
    total = sum(r.probability for r in results)
    assert total == pytest.approx(1.0, abs=1e-12)
