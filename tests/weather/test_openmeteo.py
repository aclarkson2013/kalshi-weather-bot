"""Tests for the Open-Meteo API client.

Tests module-level constants (OPENMETEO_MODELS, MODEL_SOURCE_LABELS,
DAILY_VARIABLES) and the _extract_model_daily helper that handles
different Open-Meteo response structures.
"""

from __future__ import annotations

from backend.weather.openmeteo import (
    DAILY_VARIABLES,
    MODEL_SOURCE_LABELS,
    OPENMETEO_MODELS,
    _extract_model_daily,
)

# ─── Module Constants Tests ───


class TestOpenMeteoConstants:
    """Verify module-level constants are correctly defined."""

    def test_openmeteo_models_has_three_models(self):
        """OPENMETEO_MODELS must contain exactly 3 models."""
        assert len(OPENMETEO_MODELS) == 3
        assert "gfs_seamless" in OPENMETEO_MODELS
        assert "ecmwf_ifs025" in OPENMETEO_MODELS
        assert "icon_seamless" in OPENMETEO_MODELS

    def test_model_source_labels_maps_correctly(self):
        """MODEL_SOURCE_LABELS must map each model to a readable label."""
        assert MODEL_SOURCE_LABELS["gfs_seamless"] == "Open-Meteo:GFS"
        assert MODEL_SOURCE_LABELS["ecmwf_ifs025"] == "Open-Meteo:ECMWF"
        assert MODEL_SOURCE_LABELS["icon_seamless"] == "Open-Meteo:ICON"

    def test_daily_variables_has_eight_variables(self):
        """DAILY_VARIABLES must contain exactly 8 variable names."""
        assert len(DAILY_VARIABLES) == 8
        assert "temperature_2m_max" in DAILY_VARIABLES
        assert "temperature_2m_min" in DAILY_VARIABLES
        assert "windspeed_10m_max" in DAILY_VARIABLES
        assert "windgusts_10m_max" in DAILY_VARIABLES
        assert "relative_humidity_2m_max" in DAILY_VARIABLES
        assert "cloudcover_mean" in DAILY_VARIABLES
        assert "dewpoint_2m_min" in DAILY_VARIABLES
        assert "surface_pressure_mean" in DAILY_VARIABLES


# ─── _extract_model_daily Tests ───


class TestExtractModelDaily:
    """Test extraction of per-model daily data from Open-Meteo response."""

    def test_handles_model_keyed_response(self):
        """Extracts daily data when model has its own top-level key.

        This is the format where each model's data is nested under
        response[model_name]["daily"].
        """
        raw = {
            "gfs_seamless": {
                "daily": {
                    "time": ["2026-02-17", "2026-02-18"],
                    "temperature_2m_max": [55.2, 52.1],
                    "temperature_2m_min": [38.5, 35.2],
                }
            }
        }
        result = _extract_model_daily(raw, "gfs_seamless")
        assert result is not None
        assert result["time"] == ["2026-02-17", "2026-02-18"]
        assert result["temperature_2m_max"] == [55.2, 52.1]

    def test_handles_suffix_keyed_response(self):
        """Extracts daily data when variables have model-suffix keys.

        This is the format where the shared "daily" block has keys like
        "temperature_2m_max_icon_seamless" that need remapping.
        """
        raw = {
            "daily": {
                "time": ["2026-02-17", "2026-02-18"],
                "temperature_2m_max_icon_seamless": [56.0, 53.2],
                "temperature_2m_min_icon_seamless": [39.0, 36.0],
            }
        }
        result = _extract_model_daily(raw, "icon_seamless")
        assert result is not None
        assert result["time"] == ["2026-02-17", "2026-02-18"]
        # Suffix should be stripped to get standard variable names
        assert result["temperature_2m_max"] == [56.0, 53.2]
        assert result["temperature_2m_min"] == [39.0, 36.0]

    def test_returns_none_for_missing_model(self):
        """Returns None when the requested model is not in the response."""
        raw = {
            "gfs_seamless": {
                "daily": {
                    "time": ["2026-02-17"],
                    "temperature_2m_max": [55.2],
                }
            }
        }
        result = _extract_model_daily(raw, "ecmwf_ifs025")
        assert result is None

    def test_returns_none_for_empty_response(self):
        """Returns None when the response has no daily data at all."""
        result = _extract_model_daily({}, "gfs_seamless")
        assert result is None

    def test_full_fixture_gfs(self, sample_openmeteo_response):
        """Extracts GFS data from the full fixture response."""
        result = _extract_model_daily(sample_openmeteo_response, "gfs_seamless")
        assert result is not None
        assert len(result["time"]) == 3
        assert result["temperature_2m_max"][0] == 55.2

    def test_full_fixture_icon_suffix(self, sample_openmeteo_response):
        """Extracts ICON data from the suffix-keyed 'daily' block."""
        result = _extract_model_daily(sample_openmeteo_response, "icon_seamless")
        assert result is not None
        assert len(result["time"]) == 3
        assert result["temperature_2m_max"][0] == 56.0
