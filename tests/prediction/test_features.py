"""Tests for backend.prediction.features — XGBoost feature engineering.

Validates feature extraction for both live prediction (from WeatherData objects)
and training (from DB query dicts). Tests cover feature count, NaN handling,
cyclical encoding, city one-hot, and edge cases.
"""

from __future__ import annotations

import math
from datetime import UTC, date, datetime

import numpy as np
import pytest

from backend.common.schemas import WeatherData, WeatherVariables
from backend.prediction.features import (
    CITY_CODES,
    FEATURE_NAMES,
    KNOWN_SOURCES,
    NUM_FEATURES,
    extract_features,
    extract_training_row,
)


class TestFeatureConstants:
    """Validate feature constants and their relationships."""

    def test_num_features_matches_feature_names(self) -> None:
        """NUM_FEATURES must equal len(FEATURE_NAMES)."""
        assert NUM_FEATURES == len(FEATURE_NAMES)

    def test_num_features_is_21(self) -> None:
        """Feature count is 4+4+3+2+4+4 = 21."""
        assert NUM_FEATURES == 21

    def test_known_sources_order(self) -> None:
        """Known sources are in the expected fixed order."""
        assert KNOWN_SOURCES == ["NWS", "Open-Meteo:ECMWF", "Open-Meteo:GFS", "Open-Meteo:ICON"]

    def test_city_codes_order(self) -> None:
        """City codes are in the expected fixed order."""
        assert CITY_CODES == ["NYC", "CHI", "MIA", "AUS"]


class TestExtractTrainingRow:
    """Tests for extract_training_row (pure dict-based extraction)."""

    def test_all_sources_present(self) -> None:
        """All 4 sources → correct feature count, no NaN in highs."""
        source_highs = {
            "NWS": 55.0,
            "Open-Meteo:ECMWF": 53.0,
            "Open-Meteo:GFS": 54.0,
            "Open-Meteo:ICON": 55.0,
        }
        source_lows = {"NWS": 38.0}
        nws_vars = {"humidity_pct": 65.0, "wind_speed_mph": 10.0, "cloud_cover_pct": 40.0}

        features = extract_training_row(
            source_highs=source_highs,
            source_lows=source_lows,
            nws_vars=nws_vars,
            city="NYC",
            month=2,
            day_of_year=50,
        )

        assert features.shape == (NUM_FEATURES,)
        assert features.dtype == np.float32
        # First 4 are highs — all present.
        assert features[0] == pytest.approx(55.0)  # NWS high
        assert features[1] == pytest.approx(53.0)  # ECMWF high
        assert features[2] == pytest.approx(54.0)  # GFS high
        assert features[3] == pytest.approx(55.0)  # ICON high

    def test_missing_sources_produce_nan(self) -> None:
        """Missing sources → NaN in the corresponding feature positions."""
        source_highs = {"NWS": 55.0}  # Only NWS available.
        features = extract_training_row(
            source_highs=source_highs,
            source_lows={},
            nws_vars={},
            city="NYC",
            month=1,
            day_of_year=1,
        )

        assert features[0] == pytest.approx(55.0)  # NWS high present.
        assert np.isnan(features[1])  # ECMWF missing.
        assert np.isnan(features[2])  # GFS missing.
        assert np.isnan(features[3])  # ICON missing.

    def test_missing_lows_produce_nan(self) -> None:
        """Missing low temps → NaN in low feature positions (indices 4-7)."""
        features = extract_training_row(
            source_highs={"NWS": 55.0},
            source_lows={},
            nws_vars={},
            city="NYC",
            month=6,
            day_of_year=180,
        )

        # Lows are indices 4-7 — all should be NaN.
        for i in range(4, 8):
            assert np.isnan(features[i])

    def test_nws_weather_vars(self) -> None:
        """NWS weather variables appear at correct positions (indices 8-10)."""
        nws_vars = {"humidity_pct": 72.0, "wind_speed_mph": 15.5, "cloud_cover_pct": 80.0}
        features = extract_training_row(
            source_highs={"NWS": 55.0},
            source_lows={},
            nws_vars=nws_vars,
            city="NYC",
            month=1,
            day_of_year=1,
        )

        assert features[8] == pytest.approx(72.0)  # humidity
        assert features[9] == pytest.approx(15.5)  # wind
        assert features[10] == pytest.approx(80.0)  # cloud cover

    def test_missing_nws_vars_produce_nan(self) -> None:
        """Missing NWS weather variables → NaN at positions 8-10."""
        features = extract_training_row(
            source_highs={"NWS": 55.0},
            source_lows={},
            nws_vars={},
            city="NYC",
            month=1,
            day_of_year=1,
        )

        for i in range(8, 11):
            assert np.isnan(features[i])

    def test_spread_with_multiple_sources(self) -> None:
        """Spread = max - min of available highs (index 11)."""
        source_highs = {"NWS": 55.0, "Open-Meteo:ECMWF": 50.0, "Open-Meteo:GFS": 52.0}
        features = extract_training_row(
            source_highs=source_highs,
            source_lows={},
            nws_vars={},
            city="NYC",
            month=1,
            day_of_year=1,
        )

        assert features[11] == pytest.approx(5.0)  # 55 - 50

    def test_spread_with_single_source(self) -> None:
        """Single source → spread = 0.0."""
        features = extract_training_row(
            source_highs={"NWS": 55.0},
            source_lows={},
            nws_vars={},
            city="NYC",
            month=1,
            day_of_year=1,
        )

        assert features[11] == pytest.approx(0.0)

    def test_spread_with_no_sources(self) -> None:
        """No sources → spread = NaN."""
        features = extract_training_row(
            source_highs={},
            source_lows={},
            nws_vars={},
            city="NYC",
            month=1,
            day_of_year=1,
        )

        assert np.isnan(features[11])

    def test_source_count(self) -> None:
        """Source count (index 12) equals number of available highs."""
        features_3 = extract_training_row(
            source_highs={"NWS": 55.0, "Open-Meteo:ECMWF": 53.0, "Open-Meteo:GFS": 54.0},
            source_lows={},
            nws_vars={},
            city="NYC",
            month=1,
            day_of_year=1,
        )
        assert features_3[12] == pytest.approx(3.0)

    def test_cyclical_month_encoding_january(self) -> None:
        """January (month=1) → sin(2π/12) ≈ 0.5, cos(2π/12) ≈ 0.866."""
        features = extract_training_row(
            source_highs={"NWS": 55.0},
            source_lows={},
            nws_vars={},
            city="NYC",
            month=1,
            day_of_year=1,
        )

        expected_sin = math.sin(2 * math.pi * 1 / 12)
        expected_cos = math.cos(2 * math.pi * 1 / 12)
        assert features[15] == pytest.approx(expected_sin, abs=1e-5)  # sin_month
        assert features[16] == pytest.approx(expected_cos, abs=1e-5)  # cos_month

    def test_cyclical_month_encoding_july(self) -> None:
        """July (month=7) → sin(7π/6) ≈ -0.5, cos(7π/6) ≈ -0.866."""
        features = extract_training_row(
            source_highs={"NWS": 55.0},
            source_lows={},
            nws_vars={},
            city="NYC",
            month=7,
            day_of_year=182,
        )

        expected_sin = math.sin(2 * math.pi * 7 / 12)
        expected_cos = math.cos(2 * math.pi * 7 / 12)
        assert features[15] == pytest.approx(expected_sin, abs=1e-5)
        assert features[16] == pytest.approx(expected_cos, abs=1e-5)

    def test_city_onehot_nyc(self) -> None:
        """NYC → [1, 0, 0, 0] at positions 17-20."""
        features = extract_training_row(
            source_highs={"NWS": 55.0},
            source_lows={},
            nws_vars={},
            city="NYC",
            month=1,
            day_of_year=1,
        )

        assert features[17] == pytest.approx(1.0)  # NYC
        assert features[18] == pytest.approx(0.0)  # CHI
        assert features[19] == pytest.approx(0.0)  # MIA
        assert features[20] == pytest.approx(0.0)  # AUS

    def test_city_onehot_mia(self) -> None:
        """MIA → [0, 0, 1, 0] at positions 17-20."""
        features = extract_training_row(
            source_highs={"NWS": 55.0},
            source_lows={},
            nws_vars={},
            city="MIA",
            month=1,
            day_of_year=1,
        )

        assert features[17] == pytest.approx(0.0)
        assert features[18] == pytest.approx(0.0)
        assert features[19] == pytest.approx(1.0)  # MIA
        assert features[20] == pytest.approx(0.0)

    def test_unknown_city_all_zeros(self) -> None:
        """Unknown city code → all zeros in one-hot positions."""
        features = extract_training_row(
            source_highs={"NWS": 55.0},
            source_lows={},
            nws_vars={},
            city="DEN",
            month=1,
            day_of_year=1,
        )

        for i in range(17, 21):
            assert features[i] == pytest.approx(0.0)


class TestExtractFeatures:
    """Tests for extract_features (WeatherData-based extraction for live prediction)."""

    def test_returns_correct_shape(self, sample_forecasts) -> None:
        """Feature vector from WeatherData list has shape (NUM_FEATURES,)."""
        features = extract_features(sample_forecasts, city="NYC", target_date=date(2026, 2, 18))
        assert features.shape == (NUM_FEATURES,)

    def test_extracts_high_temps(self, sample_forecasts) -> None:
        """Per-source highs extracted from WeatherData objects."""
        features = extract_features(sample_forecasts, city="NYC", target_date=date(2026, 2, 18))

        # NWS=55, ECMWF=53, GFS=54, ICON=55 from conftest fixtures.
        assert features[0] == pytest.approx(55.0)  # NWS
        assert features[1] == pytest.approx(53.0)  # ECMWF
        assert features[2] == pytest.approx(54.0)  # GFS
        assert features[3] == pytest.approx(55.0)  # ICON

    def test_extracts_low_temps(self, sample_forecasts) -> None:
        """Low temps from NWS extracted via WeatherVariables.temp_low_f."""
        features = extract_features(sample_forecasts, city="NYC", target_date=date(2026, 2, 18))

        # NWS low is 38.0 from conftest.
        assert features[4] == pytest.approx(38.0)

    def test_single_source_forecast(self) -> None:
        """Single-source input → only that source's feature is non-NaN."""
        now = datetime.now(UTC)
        forecasts = [
            WeatherData(
                city="CHI",
                date=date(2026, 3, 1),
                forecast_high_f=45.0,
                source="NWS",
                model_run_timestamp=now,
                variables=WeatherVariables(temp_high_f=45.0),
                raw_data={},
                fetched_at=now,
            ),
        ]

        features = extract_features(forecasts, city="CHI", target_date=date(2026, 3, 1))
        assert features[0] == pytest.approx(45.0)  # NWS present.
        assert np.isnan(features[1])  # ECMWF missing.
        assert features[12] == pytest.approx(1.0)  # source_count = 1
        assert features[18] == pytest.approx(1.0)  # city_chi = 1

    def test_temporal_features_from_date(self) -> None:
        """Temporal features derived from target_date correctly."""
        now = datetime.now(UTC)
        forecasts = [
            WeatherData(
                city="NYC",
                date=date(2026, 7, 4),
                forecast_high_f=85.0,
                source="NWS",
                model_run_timestamp=now,
                variables=WeatherVariables(temp_high_f=85.0),
                raw_data={},
                fetched_at=now,
            ),
        ]

        features = extract_features(forecasts, city="NYC", target_date=date(2026, 7, 4))

        # month=7, day_of_year=185 (July 4 in non-leap year 2026)
        assert features[13] == pytest.approx(7.0)  # month
        assert features[14] == pytest.approx(185.0)  # day_of_year
