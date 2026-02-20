"""Tests for backend.prediction.xgb_model — XGBoost model manager.

Validates model lifecycle: training, saving, loading, prediction, feature
importance extraction, and error handling.
"""

from __future__ import annotations

import json

import numpy as np
import pytest

from backend.prediction.features import FEATURE_NAMES, NUM_FEATURES
from backend.prediction.xgb_model import (
    MAX_ACCEPTABLE_RMSE,
    METADATA_FILENAME,
    MODEL_FILENAME,
    XGBModelManager,
)


def _make_synthetic_data(
    n: int = 200,
    noise_std: float = 1.0,
    seed: int = 42,
) -> tuple[np.ndarray, np.ndarray]:
    """Generate synthetic temperature data for testing.

    Creates a simple linear relationship: y ≈ x[0] + small_noise
    (feature 0 = NWS high, which is the strongest predictor).
    """
    rng = np.random.default_rng(seed)
    X = rng.standard_normal((n, NUM_FEATURES)).astype(np.float32)
    # Target = first feature + noise (simulates NWS high being dominant).
    X[:, 0] = rng.uniform(30.0, 90.0, n).astype(np.float32)
    y = X[:, 0] + rng.normal(0, noise_std, n).astype(np.float32)
    return X, y


class TestXGBModelManagerInit:
    """Tests for model manager initialization."""

    def test_not_available_on_init(self, tmp_path) -> None:
        """Model is not available immediately after construction."""
        manager = XGBModelManager(model_dir=str(tmp_path))
        assert not manager.is_available()

    def test_metadata_none_on_init(self, tmp_path) -> None:
        """Metadata is None before any training or loading."""
        manager = XGBModelManager(model_dir=str(tmp_path))
        assert manager.metadata is None

    def test_model_path_correct(self, tmp_path) -> None:
        """Model path is model_dir / xgb_temp.json."""
        manager = XGBModelManager(model_dir=str(tmp_path))
        assert manager.model_path == tmp_path / MODEL_FILENAME

    def test_metadata_path_correct(self, tmp_path) -> None:
        """Metadata path is model_dir / xgb_temp_meta.json."""
        manager = XGBModelManager(model_dir=str(tmp_path))
        assert manager.metadata_path == tmp_path / METADATA_FILENAME


class TestXGBModelManagerLoad:
    """Tests for model loading from disk."""

    def test_load_returns_false_when_no_file(self, tmp_path) -> None:
        """load() returns False when model file doesn't exist."""
        manager = XGBModelManager(model_dir=str(tmp_path))
        assert manager.load() is False
        assert not manager.is_available()

    def test_load_returns_false_for_corrupt_file(self, tmp_path) -> None:
        """load() returns False gracefully for a corrupt model file."""
        model_path = tmp_path / MODEL_FILENAME
        model_path.write_text("not a valid xgboost model")
        manager = XGBModelManager(model_dir=str(tmp_path))
        assert manager.load() is False
        assert not manager.is_available()


class TestXGBModelManagerTrain:
    """Tests for model training."""

    def test_train_returns_metrics(self, tmp_path) -> None:
        """train() returns a dict with expected metric keys."""
        manager = XGBModelManager(model_dir=str(tmp_path))
        X, y = _make_synthetic_data(n=200, noise_std=1.0)
        x_train, x_test = X[:160], X[160:]
        y_train, y_test = y[:160], y[160:]

        metrics = manager.train(x_train, y_train, x_test, y_test)

        assert "rmse" in metrics
        assert "mae" in metrics
        assert "train_rmse" in metrics
        assert "sample_count" in metrics
        assert "trained_at" in metrics
        assert "accepted" in metrics

    def test_good_data_accepted(self, tmp_path) -> None:
        """Model trained on clean data (low noise) is accepted."""
        manager = XGBModelManager(model_dir=str(tmp_path))
        X, y = _make_synthetic_data(n=200, noise_std=1.0)
        x_train, x_test = X[:160], X[160:]
        y_train, y_test = y[:160], y[160:]

        metrics = manager.train(x_train, y_train, x_test, y_test)

        assert metrics["accepted"] is True
        assert metrics["rmse"] <= MAX_ACCEPTABLE_RMSE
        assert manager.is_available()

    def test_bad_data_rejected(self, tmp_path) -> None:
        """Model trained on very noisy data (RMSE > 5.0) is rejected."""
        manager = XGBModelManager(model_dir=str(tmp_path))
        X, y = _make_synthetic_data(n=200, noise_std=50.0)
        x_train, x_test = X[:160], X[160:]
        y_train, y_test = y[:160], y[160:]

        metrics = manager.train(x_train, y_train, x_test, y_test)

        assert metrics["accepted"] is False
        assert metrics["rmse"] > MAX_ACCEPTABLE_RMSE
        # Model should NOT be loaded after rejection.
        assert not manager.is_available()

    def test_sample_counts_correct(self, tmp_path) -> None:
        """Metrics include correct train/test/total sample counts."""
        manager = XGBModelManager(model_dir=str(tmp_path))
        X, y = _make_synthetic_data(n=100)
        x_train, x_test = X[:80], X[80:]
        y_train, y_test = y[:80], y[80:]

        metrics = manager.train(x_train, y_train, x_test, y_test)

        assert metrics["train_count"] == 80
        assert metrics["test_count"] == 20
        assert metrics["sample_count"] == 100

    def test_metadata_stored_after_training(self, tmp_path) -> None:
        """After accepted training, metadata is stored on the manager."""
        manager = XGBModelManager(model_dir=str(tmp_path))
        X, y = _make_synthetic_data(n=200, noise_std=1.0)
        x_train, x_test = X[:160], X[160:]
        y_train, y_test = y[:160], y[160:]

        manager.train(x_train, y_train, x_test, y_test)

        assert manager.metadata is not None
        assert "rmse" in manager.metadata
        assert "trained_at" in manager.metadata


class TestXGBModelManagerPredict:
    """Tests for model prediction."""

    def test_predict_after_training(self, tmp_path) -> None:
        """Predictions work immediately after training."""
        manager = XGBModelManager(model_dir=str(tmp_path))
        X, y = _make_synthetic_data(n=200, noise_std=1.0)
        manager.train(X[:160], y[:160], X[160:], y[160:])

        # Predict for a sample with NWS high = 72.0.
        test_features = np.zeros(NUM_FEATURES, dtype=np.float32)
        test_features[0] = 72.0
        result = manager.predict(test_features)

        assert isinstance(result, float)
        # Should be roughly 72 (± training noise).
        assert 50.0 < result < 100.0

    def test_predict_raises_if_not_loaded(self, tmp_path) -> None:
        """predict() raises RuntimeError when no model is loaded."""
        manager = XGBModelManager(model_dir=str(tmp_path))
        features = np.zeros(NUM_FEATURES, dtype=np.float32)

        with pytest.raises(RuntimeError, match="not loaded"):
            manager.predict(features)

    def test_predict_wrong_feature_count(self, tmp_path) -> None:
        """predict() raises ValueError for wrong feature count."""
        manager = XGBModelManager(model_dir=str(tmp_path))
        X, y = _make_synthetic_data(n=200, noise_std=1.0)
        manager.train(X[:160], y[:160], X[160:], y[160:])

        bad_features = np.zeros(5, dtype=np.float32)
        with pytest.raises(ValueError, match="Expected"):
            manager.predict(bad_features)

    def test_predict_handles_2d_input(self, tmp_path) -> None:
        """predict() accepts 2-D input (1, NUM_FEATURES)."""
        manager = XGBModelManager(model_dir=str(tmp_path))
        X, y = _make_synthetic_data(n=200, noise_std=1.0)
        manager.train(X[:160], y[:160], X[160:], y[160:])

        features_2d = np.zeros((1, NUM_FEATURES), dtype=np.float32)
        features_2d[0, 0] = 65.0
        result = manager.predict(features_2d)
        assert isinstance(result, float)


class TestXGBModelManagerSaveLoad:
    """Tests for save/load round-trip."""

    def test_save_load_roundtrip(self, tmp_path) -> None:
        """Model saved to disk can be loaded and makes similar predictions."""
        manager = XGBModelManager(model_dir=str(tmp_path))
        X, y = _make_synthetic_data(n=200, noise_std=1.0)
        manager.train(X[:160], y[:160], X[160:], y[160:])

        test_features = np.zeros(NUM_FEATURES, dtype=np.float32)
        test_features[0] = 60.0
        pred_before_save = manager.predict(test_features)

        manager.save()

        # Load into a new manager.
        manager2 = XGBModelManager(model_dir=str(tmp_path))
        assert manager2.load() is True
        assert manager2.is_available()

        pred_after_load = manager2.predict(test_features)
        assert pred_before_save == pytest.approx(pred_after_load, abs=0.01)

    def test_save_creates_model_file(self, tmp_path) -> None:
        """save() creates the model JSON file on disk."""
        manager = XGBModelManager(model_dir=str(tmp_path))
        X, y = _make_synthetic_data(n=200, noise_std=1.0)
        manager.train(X[:160], y[:160], X[160:], y[160:])

        manager.save()

        assert (tmp_path / MODEL_FILENAME).exists()

    def test_save_creates_metadata_file(self, tmp_path) -> None:
        """save() creates the metadata JSON file alongside the model."""
        manager = XGBModelManager(model_dir=str(tmp_path))
        X, y = _make_synthetic_data(n=200, noise_std=1.0)
        manager.train(X[:160], y[:160], X[160:], y[160:])

        manager.save()

        meta_path = tmp_path / METADATA_FILENAME
        assert meta_path.exists()
        meta = json.loads(meta_path.read_text())
        assert "rmse" in meta
        assert "trained_at" in meta

    def test_save_raises_if_no_model(self, tmp_path) -> None:
        """save() raises RuntimeError when no model is loaded."""
        manager = XGBModelManager(model_dir=str(tmp_path))

        with pytest.raises(RuntimeError, match="No model"):
            manager.save()

    def test_save_creates_directory(self, tmp_path) -> None:
        """save() creates model_dir if it doesn't exist."""
        model_dir = tmp_path / "nested" / "models"
        manager = XGBModelManager(model_dir=str(model_dir))
        X, y = _make_synthetic_data(n=200, noise_std=1.0)
        manager.train(X[:160], y[:160], X[160:], y[160:])

        manager.save()

        assert model_dir.exists()
        assert (model_dir / MODEL_FILENAME).exists()

    def test_load_restores_metadata(self, tmp_path) -> None:
        """load() restores metadata from the saved JSON file."""
        manager = XGBModelManager(model_dir=str(tmp_path))
        X, y = _make_synthetic_data(n=200, noise_std=1.0)
        manager.train(X[:160], y[:160], X[160:], y[160:])
        manager.save()

        manager2 = XGBModelManager(model_dir=str(tmp_path))
        manager2.load()

        assert manager2.metadata is not None
        assert manager2.metadata["rmse"] == manager.metadata["rmse"]


class TestXGBModelManagerFeatureImportance:
    """Tests for feature importance extraction."""

    def test_feature_importance_after_training(self, tmp_path) -> None:
        """get_feature_importance() returns dict after training."""
        manager = XGBModelManager(model_dir=str(tmp_path))
        X, y = _make_synthetic_data(n=200, noise_std=1.0)
        manager.train(X[:160], y[:160], X[160:], y[160:])

        importance = manager.get_feature_importance()

        assert importance is not None
        assert isinstance(importance, dict)
        # All keys should be from FEATURE_NAMES.
        for key in importance:
            assert key in FEATURE_NAMES

    def test_feature_importance_none_when_no_model(self, tmp_path) -> None:
        """get_feature_importance() returns None when no model loaded."""
        manager = XGBModelManager(model_dir=str(tmp_path))
        assert manager.get_feature_importance() is None

    def test_nws_high_most_important(self, tmp_path) -> None:
        """NWS high should be the most important feature for synthetic data."""
        manager = XGBModelManager(model_dir=str(tmp_path))
        X, y = _make_synthetic_data(n=200, noise_std=1.0)
        manager.train(X[:160], y[:160], X[160:], y[160:])

        importance = manager.get_feature_importance()
        assert importance is not None
        # nws_high_f should have the highest importance.
        if "nws_high_f" in importance:
            max_feature = max(importance, key=importance.get)
            assert max_feature == "nws_high_f"
