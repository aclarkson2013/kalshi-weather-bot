"""Tests for backend.prediction.ensemble — weighted ensemble and confidence.

Covers ``calculate_ensemble_forecast`` (10 tests) and
``assess_confidence`` (9 tests) plus additional edge-case tests.
"""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest

from backend.common.schemas import WeatherData, WeatherVariables
from backend.prediction.ensemble import (
    DEFAULT_MODEL_WEIGHTS,
    assess_confidence,
    calculate_ensemble_forecast,
)

# ─── Helpers ───


def _make_forecast(source: str, temp: float) -> WeatherData:
    """Create a WeatherData object with the given source and high temp."""
    now = datetime.now(UTC)
    return WeatherData(
        city="NYC",
        date=date(2026, 2, 18),
        forecast_high_f=temp,
        source=source,
        model_run_timestamp=now,
        variables=WeatherVariables(temp_high_f=temp),
        raw_data={"temp": temp},
        fetched_at=now,
    )


# ═══════════════════════════════════════════════════════════════
# calculate_ensemble_forecast
# ═══════════════════════════════════════════════════════════════


class TestCalculateEnsembleForecast:
    """Tests for the weighted-average ensemble calculation."""

    def test_basic_ensemble(self) -> None:
        """Three known sources produce a weighted average between min and max."""
        forecasts = [
            _make_forecast("NWS", 55.0),
            _make_forecast("Open-Meteo:ECMWF", 53.0),
            _make_forecast("Open-Meteo:GFS", 54.0),
        ]
        temp, spread, sources = calculate_ensemble_forecast(forecasts)

        # Weighted average: (55*0.35 + 53*0.30 + 54*0.20) / (0.35+0.30+0.20)
        expected = (55.0 * 0.35 + 53.0 * 0.30 + 54.0 * 0.20) / (0.35 + 0.30 + 0.20)
        assert abs(temp - expected) < 1e-9
        assert spread == pytest.approx(2.0)
        assert len(sources) == 3

    def test_single_source(self) -> None:
        """A single forecast yields its own temp and zero spread."""
        forecasts = [_make_forecast("NWS", 55.0)]
        temp, spread, sources = calculate_ensemble_forecast(forecasts)

        assert temp == pytest.approx(55.0)
        assert spread == pytest.approx(0.0)
        assert sources == ["NWS"]

    def test_empty_forecasts_raises(self) -> None:
        """An empty list must raise ValueError."""
        with pytest.raises(ValueError, match="No forecasts"):
            calculate_ensemble_forecast([])

    def test_all_weights_zero_raises(self) -> None:
        """Custom weights that are all zero must raise ValueError."""
        forecasts = [_make_forecast("NWS", 55.0)]
        with pytest.raises(ValueError, match="All weights are zero"):
            calculate_ensemble_forecast(forecasts, weights={"NWS": 0.0})

    def test_unknown_source_gets_default_weight(self) -> None:
        """An unrecognized source name receives the 0.05 default weight."""
        forecasts = [
            _make_forecast("NWS", 55.0),
            _make_forecast("SomeNewSource", 60.0),
        ]
        temp, spread, sources = calculate_ensemble_forecast(forecasts)

        # (55 * 0.35 + 60 * 0.05) / (0.35 + 0.05)
        expected = (55.0 * 0.35 + 60.0 * 0.05) / 0.40
        assert temp == pytest.approx(expected, abs=1e-9)
        assert "SomeNewSource" in sources

    def test_known_source_weights_applied(self) -> None:
        """NWS gets 0.35, ECMWF gets 0.30 from the default table."""
        assert DEFAULT_MODEL_WEIGHTS["NWS"] == pytest.approx(0.35)
        assert DEFAULT_MODEL_WEIGHTS["Open-Meteo:ECMWF"] == pytest.approx(0.30)

        forecasts = [
            _make_forecast("NWS", 60.0),
            _make_forecast("Open-Meteo:ECMWF", 50.0),
        ]
        temp, _spread, _sources = calculate_ensemble_forecast(forecasts)

        expected = (60.0 * 0.35 + 50.0 * 0.30) / (0.35 + 0.30)
        assert temp == pytest.approx(expected, abs=1e-9)

    def test_spread_calculation(self) -> None:
        """Spread equals max temp minus min temp across all sources."""
        forecasts = [
            _make_forecast("NWS", 50.0),
            _make_forecast("Open-Meteo:ECMWF", 56.0),
            _make_forecast("Open-Meteo:GFS", 53.0),
        ]
        _temp, spread, _sources = calculate_ensemble_forecast(forecasts)
        assert spread == pytest.approx(6.0)

    def test_sources_list_returned(self) -> None:
        """The returned source list matches the input forecast sources."""
        forecasts = [
            _make_forecast("NWS", 55.0),
            _make_forecast("Open-Meteo:ECMWF", 53.0),
        ]
        _temp, _spread, sources = calculate_ensemble_forecast(forecasts)
        assert sources == ["NWS", "Open-Meteo:ECMWF"]

    def test_custom_weights_override(self) -> None:
        """Custom weights completely override the defaults."""
        forecasts = [
            _make_forecast("NWS", 50.0),
            _make_forecast("Open-Meteo:ECMWF", 60.0),
        ]
        custom = {"NWS": 1.0, "Open-Meteo:ECMWF": 1.0}
        temp, _spread, _sources = calculate_ensemble_forecast(forecasts, weights=custom)

        # Equal weights → simple average
        assert temp == pytest.approx(55.0)

    def test_equal_temps_zero_spread(self) -> None:
        """When all sources agree on the same temp, spread is 0."""
        forecasts = [
            _make_forecast("NWS", 55.0),
            _make_forecast("Open-Meteo:ECMWF", 55.0),
            _make_forecast("Open-Meteo:GFS", 55.0),
        ]
        temp, spread, _sources = calculate_ensemble_forecast(forecasts)
        assert temp == pytest.approx(55.0)
        assert spread == pytest.approx(0.0)


# ═══════════════════════════════════════════════════════════════
# assess_confidence
# ═══════════════════════════════════════════════════════════════


class TestAssessConfidence:
    """Tests for confidence scoring logic."""

    def test_high_confidence(self) -> None:
        """Best-case inputs produce 'high' confidence (score >= 5)."""
        result = assess_confidence(
            forecast_spread_f=0.5,  # +3
            error_std_f=1.5,  # +2
            num_sources=5,  # +1
            data_age_minutes=30.0,  # +1  → total = 7
        )
        assert result == "high"

    def test_low_confidence(self) -> None:
        """Worst-case inputs produce 'low' confidence (score < 3)."""
        result = assess_confidence(
            forecast_spread_f=5.0,  # +0
            error_std_f=4.0,  # +0
            num_sources=2,  # +0
            data_age_minutes=180.0,  # -1  → total = -1
        )
        assert result == "low"

    def test_medium_confidence(self) -> None:
        """Moderate inputs produce 'medium' confidence (3 <= score < 5)."""
        result = assess_confidence(
            forecast_spread_f=2.0,  # +2
            error_std_f=2.5,  # +1
            num_sources=3,  # +0
            data_age_minutes=90.0,  # +0  → total = 3
        )
        assert result == "medium"

    def test_boundary_score_5_is_high(self) -> None:
        """A score of exactly 5 maps to 'high'."""
        # spread <= 1.0 → +3, error_std <= 2.0 → +2, sources < 4 → +0, age 60-120 → +0
        result = assess_confidence(
            forecast_spread_f=1.0,
            error_std_f=2.0,
            num_sources=3,
            data_age_minutes=90.0,
        )
        assert result == "high"

    def test_boundary_score_3_is_medium(self) -> None:
        """A score of exactly 3 maps to 'medium'."""
        # spread <= 1.0 → +3, error_std > 3.0 → +0, sources < 4 → +0, age 60-120 → +0
        result = assess_confidence(
            forecast_spread_f=1.0,
            error_std_f=3.5,
            num_sources=3,
            data_age_minutes=90.0,
        )
        assert result == "medium"

    def test_boundary_score_2_is_low(self) -> None:
        """A score of exactly 2 maps to 'low'."""
        # spread <= 2.0 → +2, error_std > 3.0 → +0, sources < 4 → +0, age 60-120 → +0
        result = assess_confidence(
            forecast_spread_f=2.0,
            error_std_f=3.5,
            num_sources=3,
            data_age_minutes=90.0,
        )
        assert result == "low"

    def test_stale_data_penalty(self) -> None:
        """Data age > 120 minutes incurs a -1 penalty."""
        # Start with a borderline-medium scenario (score = 3)
        # then add stale data to drop it to 2 → low
        result = assess_confidence(
            forecast_spread_f=1.0,  # +3
            error_std_f=3.5,  # +0
            num_sources=3,  # +0
            data_age_minutes=150.0,  # -1  → total = 2
        )
        assert result == "low"

    def test_fresh_data_bonus(self) -> None:
        """Data age <= 60 minutes gives a +1 freshness bonus."""
        # spread <= 2.0 → +2, error_std <= 3.0 → +1, sources < 4 → +0, age <= 60 → +1 = 4
        result = assess_confidence(
            forecast_spread_f=2.0,
            error_std_f=3.0,
            num_sources=3,
            data_age_minutes=30.0,
        )
        assert result == "medium"

    def test_lowercase_return_values(self) -> None:
        """Return value is always one of the three lowercase strings."""
        valid = {"high", "medium", "low"}
        test_cases = [
            (0.5, 1.5, 5, 30.0),
            (5.0, 4.0, 2, 180.0),
            (2.0, 2.5, 3, 90.0),
        ]
        for spread, std, sources, age in test_cases:
            result = assess_confidence(spread, std, sources, age)
            assert result in valid, f"Got unexpected value: {result!r}"
