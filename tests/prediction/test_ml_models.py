"""Tests for backend.prediction.ml_models — RF and Ridge model managers.

Validates model lifecycle: training, saving, loading, prediction, NaN handling,
and error handling. Follows the same pattern as test_xgb_model.py.
"""

from __future__ import annotations

import numpy as np
import pytest

from backend.prediction.features import NUM_FEATURES
from backend.prediction.ml_models import (
    MAX_ACCEPTABLE_RMSE,
    RF_METADATA_FILENAME,
    RF_MODEL_FILENAME,
    RIDGE_METADATA_FILENAME,
    RIDGE_MODEL_FILENAME,
    RFModelManager,
    RidgeModelManager,
)


def _make_synthetic_data(
    n: int = 200,
    noise_std: float = 1.0,
    seed: int = 42,
) -> tuple[np.ndarray, np.ndarray]:
    """Generate synthetic temperature data for testing."""
    rng = np.random.default_rng(seed)
    X = rng.standard_normal((n, NUM_FEATURES)).astype(np.float32)
    X[:, 0] = rng.uniform(30.0, 90.0, n).astype(np.float32)
    y = X[:, 0] + rng.normal(0, noise_std, n).astype(np.float32)
    return X, y


def _train_manager(manager, tmp_path, noise_std=1.0):
    """Helper: train a manager on synthetic data and return metrics."""
    X, y = _make_synthetic_data(noise_std=noise_std)
    split = int(len(X) * 0.8)
    return manager.train(X[:split], y[:split], X[split:], y[split:])


# ─── Random Forest Tests ───


class TestRFModelManagerInit:
    """Tests for RF model manager initialization."""

    def test_not_available_on_init(self, tmp_path) -> None:
        manager = RFModelManager(model_dir=str(tmp_path))
        assert not manager.is_available()

    def test_metadata_none_on_init(self, tmp_path) -> None:
        manager = RFModelManager(model_dir=str(tmp_path))
        assert manager.metadata is None

    def test_model_path_correct(self, tmp_path) -> None:
        manager = RFModelManager(model_dir=str(tmp_path))
        assert manager.model_path == tmp_path / RF_MODEL_FILENAME


class TestRFModelManagerTrain:
    """Tests for RF model training."""

    def test_train_returns_metrics(self, tmp_path) -> None:
        manager = RFModelManager(model_dir=str(tmp_path))
        metrics = _train_manager(manager, tmp_path)
        assert "rmse" in metrics
        assert "mae" in metrics
        assert "accepted" in metrics
        assert "nan_fill_values" in metrics

    def test_good_data_accepted(self, tmp_path) -> None:
        manager = RFModelManager(model_dir=str(tmp_path))
        metrics = _train_manager(manager, tmp_path, noise_std=1.0)
        assert metrics["accepted"] is True
        assert metrics["rmse"] <= MAX_ACCEPTABLE_RMSE
        assert manager.is_available()

    def test_bad_data_rejected(self, tmp_path) -> None:
        manager = RFModelManager(model_dir=str(tmp_path))
        metrics = _train_manager(manager, tmp_path, noise_std=50.0)
        assert metrics["accepted"] is False

    def test_sample_counts_correct(self, tmp_path) -> None:
        manager = RFModelManager(model_dir=str(tmp_path))
        metrics = _train_manager(manager, tmp_path)
        assert metrics["train_count"] == 160
        assert metrics["test_count"] == 40
        assert metrics["sample_count"] == 200


class TestRFModelManagerPredict:
    """Tests for RF model prediction."""

    def test_predict_after_training(self, tmp_path) -> None:
        manager = RFModelManager(model_dir=str(tmp_path))
        _train_manager(manager, tmp_path)
        features = np.random.default_rng(99).standard_normal(NUM_FEATURES).astype(np.float32)
        features[0] = 65.0
        result = manager.predict(features)
        assert isinstance(result, float)
        assert 30.0 <= result <= 100.0

    def test_predict_raises_if_not_loaded(self, tmp_path) -> None:
        manager = RFModelManager(model_dir=str(tmp_path))
        features = np.zeros(NUM_FEATURES, dtype=np.float32)
        with pytest.raises(RuntimeError, match="not loaded"):
            manager.predict(features)

    def test_predict_wrong_feature_count(self, tmp_path) -> None:
        manager = RFModelManager(model_dir=str(tmp_path))
        _train_manager(manager, tmp_path)
        features = np.zeros(5, dtype=np.float32)
        with pytest.raises(ValueError, match="Expected"):
            manager.predict(features)

    def test_predict_handles_nan_features(self, tmp_path) -> None:
        """NaN features are replaced with training medians."""
        manager = RFModelManager(model_dir=str(tmp_path))
        _train_manager(manager, tmp_path)
        features = np.full(NUM_FEATURES, np.nan, dtype=np.float32)
        result = manager.predict(features)
        assert isinstance(result, float)
        assert not np.isnan(result)


class TestRFModelManagerSaveLoad:
    """Tests for RF model persistence."""

    def test_save_load_roundtrip(self, tmp_path) -> None:
        manager = RFModelManager(model_dir=str(tmp_path))
        _train_manager(manager, tmp_path)
        features = np.random.default_rng(99).standard_normal(NUM_FEATURES).astype(np.float32)
        features[0] = 65.0
        original = manager.predict(features)
        manager.save()

        loaded = RFModelManager(model_dir=str(tmp_path))
        assert loaded.load() is True
        assert abs(loaded.predict(features) - original) < 0.01

    def test_save_creates_model_file(self, tmp_path) -> None:
        manager = RFModelManager(model_dir=str(tmp_path))
        _train_manager(manager, tmp_path)
        manager.save()
        assert (tmp_path / RF_MODEL_FILENAME).exists()
        assert (tmp_path / RF_METADATA_FILENAME).exists()

    def test_nan_fill_values_persist(self, tmp_path) -> None:
        """NaN fill values survive save/load cycle."""
        manager = RFModelManager(model_dir=str(tmp_path))
        _train_manager(manager, tmp_path)
        manager.save()

        loaded = RFModelManager(model_dir=str(tmp_path))
        loaded.load()
        assert loaded._nan_fill_values is not None
        assert len(loaded._nan_fill_values) == NUM_FEATURES


# ─── Ridge Regression Tests ───


class TestRidgeModelManagerInit:
    """Tests for Ridge model manager initialization."""

    def test_not_available_on_init(self, tmp_path) -> None:
        manager = RidgeModelManager(model_dir=str(tmp_path))
        assert not manager.is_available()

    def test_model_path_correct(self, tmp_path) -> None:
        manager = RidgeModelManager(model_dir=str(tmp_path))
        assert manager.model_path == tmp_path / RIDGE_MODEL_FILENAME


class TestRidgeModelManagerTrain:
    """Tests for Ridge model training."""

    def test_train_returns_metrics(self, tmp_path) -> None:
        manager = RidgeModelManager(model_dir=str(tmp_path))
        metrics = _train_manager(manager, tmp_path)
        assert "rmse" in metrics
        assert "mae" in metrics
        assert "accepted" in metrics

    def test_good_data_accepted(self, tmp_path) -> None:
        manager = RidgeModelManager(model_dir=str(tmp_path))
        metrics = _train_manager(manager, tmp_path, noise_std=1.0)
        assert metrics["accepted"] is True
        assert manager.is_available()

    def test_bad_data_rejected(self, tmp_path) -> None:
        manager = RidgeModelManager(model_dir=str(tmp_path))
        metrics = _train_manager(manager, tmp_path, noise_std=50.0)
        assert metrics["accepted"] is False


class TestRidgeModelManagerPredict:
    """Tests for Ridge model prediction."""

    def test_predict_after_training(self, tmp_path) -> None:
        manager = RidgeModelManager(model_dir=str(tmp_path))
        _train_manager(manager, tmp_path)
        features = np.random.default_rng(99).standard_normal(NUM_FEATURES).astype(np.float32)
        features[0] = 65.0
        result = manager.predict(features)
        assert isinstance(result, float)

    def test_predict_handles_nan_features(self, tmp_path) -> None:
        manager = RidgeModelManager(model_dir=str(tmp_path))
        _train_manager(manager, tmp_path)
        features = np.full(NUM_FEATURES, np.nan, dtype=np.float32)
        result = manager.predict(features)
        assert isinstance(result, float)
        assert not np.isnan(result)

    def test_predict_wrong_feature_count(self, tmp_path) -> None:
        manager = RidgeModelManager(model_dir=str(tmp_path))
        _train_manager(manager, tmp_path)
        features = np.zeros(5, dtype=np.float32)
        with pytest.raises(ValueError, match="Expected"):
            manager.predict(features)


class TestRidgeModelManagerSaveLoad:
    """Tests for Ridge model persistence."""

    def test_save_load_roundtrip(self, tmp_path) -> None:
        manager = RidgeModelManager(model_dir=str(tmp_path))
        _train_manager(manager, tmp_path)
        features = np.random.default_rng(99).standard_normal(NUM_FEATURES).astype(np.float32)
        features[0] = 65.0
        original = manager.predict(features)
        manager.save()

        loaded = RidgeModelManager(model_dir=str(tmp_path))
        assert loaded.load() is True
        assert abs(loaded.predict(features) - original) < 0.01

    def test_save_creates_model_file(self, tmp_path) -> None:
        manager = RidgeModelManager(model_dir=str(tmp_path))
        _train_manager(manager, tmp_path)
        manager.save()
        assert (tmp_path / RIDGE_MODEL_FILENAME).exists()
        assert (tmp_path / RIDGE_METADATA_FILENAME).exists()
