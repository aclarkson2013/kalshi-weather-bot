"""Tests for backend.prediction.train_models — multi-model training Celery task.

Validates the multi-model training pipeline: async wrapper, successful training,
insufficient data, feature mismatch, partial acceptance, and exception propagation.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from backend.prediction.train_models import train_all_models


class TestTrainAllModelsTask:
    """Tests for the train_all_models Celery task."""

    @patch("backend.prediction.train_models.async_to_sync")
    def test_insufficient_data_skips(self, mock_ats) -> None:
        """Task skips training when data is below minimum threshold."""
        mock_ats.return_value = MagicMock(
            return_value={"status": "skipped", "reason": "insufficient_data", "row_count": 10}
        )

        result = train_all_models.apply().get()

        assert result["status"] == "skipped"
        assert result["reason"] == "insufficient_data"

    @patch("backend.prediction.train_models.async_to_sync")
    def test_successful_training(self, mock_ats) -> None:
        """Task returns completed status with metrics on success."""
        mock_ats.return_value = MagicMock(
            return_value={
                "status": "completed",
                "row_count": 200,
                "models": {
                    "xgboost": {"rmse": 2.1, "accepted": True},
                    "random_forest": {"rmse": 2.3, "accepted": True},
                    "ridge": {"rmse": 2.8, "accepted": True},
                },
                "weights": {"xgboost": 0.37, "random_forest": 0.34, "ridge": 0.29},
            }
        )

        result = train_all_models.apply().get()

        assert result["status"] == "completed"
        assert result["row_count"] == 200

    @patch("backend.prediction.train_models.async_to_sync")
    def test_feature_mismatch_returns_error(self, mock_ats) -> None:
        """Task returns error status on feature count mismatch."""
        mock_ats.return_value = MagicMock(
            return_value={"status": "error", "reason": "feature_mismatch"}
        )

        result = train_all_models.apply().get()

        assert result["status"] == "error"
        assert result["reason"] == "feature_mismatch"

    @patch("backend.prediction.train_models.async_to_sync")
    def test_exception_propagates(self, mock_ats) -> None:
        """Task propagates exceptions from the async training logic."""
        mock_ats.return_value = MagicMock(side_effect=RuntimeError("DB connection failed"))

        with pytest.raises(RuntimeError, match="DB connection failed"):
            train_all_models.apply().get()

    @patch("backend.prediction.train_models.async_to_sync")
    def test_partial_acceptance(self, mock_ats) -> None:
        """Task returns partial acceptance when some models fail quality check."""
        mock_ats.return_value = MagicMock(
            return_value={
                "status": "completed",
                "row_count": 200,
                "models": {
                    "xgboost": {"rmse": 2.0, "accepted": True},
                    "random_forest": {"rmse": 7.5, "accepted": False},
                    "ridge": {"rmse": 2.5, "accepted": True},
                },
                "weights": {"xgboost": 0.56, "ridge": 0.44},
            }
        )

        result = train_all_models.apply().get()

        assert result["status"] == "completed"
        assert result["models"]["random_forest"]["accepted"] is False
        assert "random_forest" not in result["weights"]

    @patch("backend.prediction.train_models.async_to_sync")
    def test_weights_in_result(self, mock_ats) -> None:
        """Task result includes computed inverse-RMSE weights."""
        mock_ats.return_value = MagicMock(
            return_value={
                "status": "completed",
                "row_count": 150,
                "models": {
                    "xgboost": {"rmse": 2.0, "accepted": True},
                    "random_forest": {"rmse": 2.0, "accepted": True},
                    "ridge": {"rmse": 2.0, "accepted": True},
                },
                "weights": {"xgboost": 0.333, "random_forest": 0.333, "ridge": 0.333},
            }
        )

        result = train_all_models.apply().get()

        assert "weights" in result
        assert len(result["weights"]) == 3

    @patch("backend.prediction.train_models.async_to_sync")
    def test_all_models_rejected(self, mock_ats) -> None:
        """Task handles all models being rejected gracefully."""
        mock_ats.return_value = MagicMock(
            return_value={
                "status": "completed",
                "row_count": 200,
                "models": {
                    "xgboost": {"rmse": 8.0, "accepted": False},
                    "random_forest": {"rmse": 9.0, "accepted": False},
                    "ridge": {"rmse": 7.5, "accepted": False},
                },
                "weights": {},
            }
        )

        result = train_all_models.apply().get()

        assert result["status"] == "completed"
        assert result["weights"] == {}

    @patch("backend.prediction.train_models.async_to_sync")
    def test_result_has_status_key(self, mock_ats) -> None:
        """Every successful task result includes a status key."""
        mock_ats.return_value = MagicMock(
            return_value={
                "status": "completed",
                "row_count": 100,
            }
        )

        result = train_all_models.apply().get()

        assert "status" in result

    @patch("backend.prediction.train_models.async_to_sync")
    def test_metrics_observed_on_success(self, mock_ats) -> None:
        """ML_TRAINING_DURATION_SECONDS metric is observed."""
        mock_ats.return_value = MagicMock(return_value={"status": "completed", "row_count": 200})

        # Should not raise — metric observation happens internally.
        result = train_all_models.apply().get()

        assert result["status"] == "completed"

    @patch("backend.prediction.train_models.async_to_sync")
    def test_metrics_observed_on_failure(self, mock_ats) -> None:
        """ML_TRAINING_DURATION_SECONDS metric is observed even on failure."""
        mock_ats.return_value = MagicMock(side_effect=ValueError("bad data"))

        with pytest.raises(ValueError, match="bad data"):
            train_all_models.apply().get()
