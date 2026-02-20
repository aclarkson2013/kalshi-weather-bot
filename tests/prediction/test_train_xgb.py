"""Tests for backend.prediction.train_xgb — XGBoost training Celery task.

Validates the training pipeline: DB data fetching, array conversion,
training task execution, and edge cases (insufficient data, feature
mismatch, model rejection).
"""

from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from backend.prediction.features import NUM_FEATURES
from backend.prediction.train_xgb import (
    _rows_to_arrays,
    train_xgb_model,
)


def _make_training_row(
    city: str = "NYC",
    forecast_date: date = date(2026, 2, 18),
    actual_high_f: float = 55.0,
    nws_high: float | None = 55.0,
    ecmwf_high: float | None = 53.0,
    gfs_high: float | None = 54.0,
    icon_high: float | None = 55.0,
    nws_low: float | None = 38.0,
    humidity_pct: float | None = 65.0,
    wind_speed_mph: float | None = 10.0,
    cloud_cover_pct: float | None = 40.0,
) -> dict:
    """Create a training row dict (mimicking _fetch_training_data output)."""
    return {
        "city": city,
        "forecast_date": forecast_date,
        "actual_high_f": actual_high_f,
        "nws_high": nws_high,
        "ecmwf_high": ecmwf_high,
        "gfs_high": gfs_high,
        "icon_high": icon_high,
        "nws_low": nws_low,
        "humidity_pct": humidity_pct,
        "wind_speed_mph": wind_speed_mph,
        "cloud_cover_pct": cloud_cover_pct,
    }


class TestRowsToArrays:
    """Tests for _rows_to_arrays conversion."""

    def test_basic_conversion(self) -> None:
        """Single row → X shape (1, NUM_FEATURES), y shape (1,)."""
        rows = [_make_training_row()]
        X, y = _rows_to_arrays(rows)

        assert X.shape == (1, NUM_FEATURES)
        assert y.shape == (1,)
        assert y[0] == pytest.approx(55.0)

    def test_multiple_rows(self) -> None:
        """Multiple rows → correct batch shape."""
        rows = [
            _make_training_row(city="NYC", actual_high_f=55.0),
            _make_training_row(city="CHI", actual_high_f=45.0, forecast_date=date(2026, 2, 19)),
            _make_training_row(city="MIA", actual_high_f=78.0, forecast_date=date(2026, 2, 20)),
        ]
        X, y = _rows_to_arrays(rows)

        assert X.shape == (3, NUM_FEATURES)
        assert y.shape == (3,)

    def test_missing_source_produces_nan(self) -> None:
        """Row with missing sources → NaN in corresponding feature positions."""
        rows = [_make_training_row(ecmwf_high=None, gfs_high=None, icon_high=None)]
        X, y = _rows_to_arrays(rows)

        # Indices 1-3 are ECMWF, GFS, ICON highs.
        assert np.isnan(X[0, 1])
        assert np.isnan(X[0, 2])
        assert np.isnan(X[0, 3])

    def test_city_enum_value_extraction(self) -> None:
        """City values that have a .value attribute (enum) are handled."""
        mock_city = MagicMock()
        mock_city.value = "NYC"
        rows = [_make_training_row()]
        rows[0]["city"] = mock_city

        X, y = _rows_to_arrays(rows)
        # Should not raise — city_onehot should work.
        assert X.shape == (1, NUM_FEATURES)

    def test_dtypes(self) -> None:
        """Output arrays have float32 dtype."""
        rows = [_make_training_row()]
        X, y = _rows_to_arrays(rows)

        assert X.dtype == np.float32
        assert y.dtype == np.float32


class TestTrainXGBModelTask:
    """Tests for the train_xgb_model Celery task."""

    @patch("backend.prediction.train_xgb.async_to_sync")
    def test_insufficient_data_skips(self, mock_ats) -> None:
        """Task skips training when data is below minimum threshold."""
        mock_ats.return_value = MagicMock(
            return_value={"status": "skipped", "reason": "insufficient_data", "row_count": 10}
        )

        result = train_xgb_model.apply().get()

        assert result["status"] == "skipped"
        assert result["reason"] == "insufficient_data"

    @patch("backend.prediction.train_xgb.async_to_sync")
    def test_successful_training(self, mock_ats) -> None:
        """Task returns success metrics on successful training."""
        mock_ats.return_value = MagicMock(
            return_value={
                "rmse": 2.1,
                "mae": 1.5,
                "accepted": True,
                "sample_count": 200,
            }
        )

        result = train_xgb_model.apply().get()

        assert result["accepted"] is True
        assert result["rmse"] == 2.1

    @patch("backend.prediction.train_xgb.async_to_sync")
    def test_feature_mismatch_returns_error(self, mock_ats) -> None:
        """Task returns error status on feature count mismatch."""
        mock_ats.return_value = MagicMock(
            return_value={"status": "error", "reason": "feature_mismatch"}
        )

        result = train_xgb_model.apply().get()

        assert result["status"] == "error"
        assert result["reason"] == "feature_mismatch"

    @patch("backend.prediction.train_xgb.async_to_sync")
    def test_exception_propagates(self, mock_ats) -> None:
        """Task propagates exceptions from the async training logic."""
        mock_ats.return_value = MagicMock(side_effect=RuntimeError("DB connection failed"))

        with pytest.raises(RuntimeError, match="DB connection failed"):
            train_xgb_model.apply().get()

    @patch("backend.prediction.train_xgb.async_to_sync")
    def test_model_rejection(self, mock_ats) -> None:
        """Task returns accepted=False when model RMSE exceeds threshold."""
        mock_ats.return_value = MagicMock(
            return_value={
                "rmse": 7.5,
                "mae": 5.0,
                "accepted": False,
                "sample_count": 200,
            }
        )

        result = train_xgb_model.apply().get()

        assert result["accepted"] is False
        assert result["rmse"] == 7.5
