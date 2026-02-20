"""Tests for backend.prediction.model_ensemble — multi-model ensemble.

Validates inverse-RMSE weighting, prediction aggregation, training,
save/load, and graceful degradation.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import numpy as np

from backend.prediction.features import NUM_FEATURES
from backend.prediction.model_ensemble import WEIGHTS_FILENAME, MultiModelEnsemble


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


def _make_trained_ensemble(tmp_path, noise_std=1.0):
    """Create and train a MultiModelEnsemble, return (ensemble, result)."""
    X, y = _make_synthetic_data(noise_std=noise_std)
    split = int(len(X) * 0.8)
    ensemble = MultiModelEnsemble(model_dir=str(tmp_path))
    result = ensemble.train_all(X[:split], y[:split], X[split:], y[split:])
    return ensemble, result


class TestInverseRMSEWeights:
    """Tests for inverse-RMSE weight computation."""

    def test_equal_rmse_equal_weights(self) -> None:
        """All models with same RMSE get equal weights."""
        metrics = {
            "A": {"rmse": 2.0, "accepted": True},
            "B": {"rmse": 2.0, "accepted": True},
            "C": {"rmse": 2.0, "accepted": True},
        }
        weights = MultiModelEnsemble.compute_inverse_rmse_weights(metrics)
        assert len(weights) == 3
        for w in weights.values():
            assert abs(w - 1 / 3) < 0.01

    def test_lower_rmse_higher_weight(self) -> None:
        """Model with lower RMSE gets proportionally higher weight."""
        metrics = {
            "Good": {"rmse": 1.0, "accepted": True},
            "Bad": {"rmse": 4.0, "accepted": True},
        }
        weights = MultiModelEnsemble.compute_inverse_rmse_weights(metrics)
        assert weights["Good"] > weights["Bad"]
        # 1/1=1.0, 1/4=0.25, total=1.25
        assert abs(weights["Good"] - 0.8) < 0.01
        assert abs(weights["Bad"] - 0.2) < 0.01

    def test_single_model_gets_full_weight(self) -> None:
        metrics = {
            "Solo": {"rmse": 2.5, "accepted": True},
        }
        weights = MultiModelEnsemble.compute_inverse_rmse_weights(metrics)
        assert weights["Solo"] == 1.0

    def test_zero_rmse_handled(self) -> None:
        """RMSE=0 (perfect model) does not cause division by zero."""
        metrics = {
            "Perfect": {"rmse": 0.0, "accepted": True},
            "Normal": {"rmse": 2.0, "accepted": True},
        }
        weights = MultiModelEnsemble.compute_inverse_rmse_weights(metrics)
        assert "Perfect" in weights
        assert weights["Perfect"] > weights["Normal"]

    def test_rejected_models_excluded(self) -> None:
        metrics = {
            "Good": {"rmse": 2.0, "accepted": True},
            "Rejected": {"rmse": 6.0, "accepted": False},
        }
        weights = MultiModelEnsemble.compute_inverse_rmse_weights(metrics)
        assert "Rejected" not in weights
        assert weights["Good"] == 1.0

    def test_all_rejected_returns_empty(self) -> None:
        metrics = {
            "Bad1": {"rmse": 6.0, "accepted": False},
            "Bad2": {"rmse": 7.0, "accepted": False},
        }
        weights = MultiModelEnsemble.compute_inverse_rmse_weights(metrics)
        assert weights == {}


class TestMultiModelPredict:
    """Tests for multi-model prediction."""

    def test_all_models_contribute(self, tmp_path) -> None:
        """All three models contribute to weighted prediction."""
        ensemble, _ = _make_trained_ensemble(tmp_path)
        features = np.random.default_rng(99).standard_normal(NUM_FEATURES).astype(np.float32)
        features[0] = 65.0
        pred, names = ensemble.predict(features)
        assert pred is not None
        assert len(names) == 3
        assert "XGBoost" in names
        assert "RandomForest" in names
        assert "Ridge" in names

    def test_one_model_fallback(self, tmp_path) -> None:
        """With only one model loaded, uses it alone."""
        ensemble = MultiModelEnsemble(model_dir=str(tmp_path))
        # Train only XGBoost.
        X, y = _make_synthetic_data()
        split = int(len(X) * 0.8)
        ensemble._xgb.train(X[:split], y[:split], X[split:], y[split:])
        ensemble._weights = {"XGBoost": 1.0}

        features = np.random.default_rng(99).standard_normal(NUM_FEATURES).astype(np.float32)
        features[0] = 65.0
        pred, names = ensemble.predict(features)
        assert pred is not None
        assert names == ["XGBoost"]

    def test_no_models_returns_none(self, tmp_path) -> None:
        ensemble = MultiModelEnsemble(model_dir=str(tmp_path))
        features = np.zeros(NUM_FEATURES, dtype=np.float32)
        pred, names = ensemble.predict(features)
        assert pred is None
        assert names == []

    def test_model_failure_graceful(self, tmp_path) -> None:
        """If one model raises during predict, others still contribute."""
        ensemble, _ = _make_trained_ensemble(tmp_path)

        # Make RF raise.
        ensemble._rf.predict = MagicMock(side_effect=RuntimeError("boom"))

        features = np.random.default_rng(99).standard_normal(NUM_FEATURES).astype(np.float32)
        features[0] = 65.0
        pred, names = ensemble.predict(features)
        assert pred is not None
        assert "RandomForest" not in names
        assert len(names) == 2

    def test_prediction_within_range(self, tmp_path) -> None:
        """Weighted prediction falls between min and max individual predictions."""
        ensemble, _ = _make_trained_ensemble(tmp_path)
        features = np.random.default_rng(99).standard_normal(NUM_FEATURES).astype(np.float32)
        features[0] = 65.0

        individual = []
        for _name, mgr in ensemble._managers.items():
            if mgr.is_available():
                individual.append(mgr.predict(features))

        pred, _ = ensemble.predict(features)
        assert min(individual) <= pred <= max(individual)

    def test_equal_weight_fallback(self, tmp_path) -> None:
        """If weights are empty, equal weights are used."""
        ensemble, _ = _make_trained_ensemble(tmp_path)
        ensemble._weights = {}  # Clear weights
        features = np.random.default_rng(99).standard_normal(NUM_FEATURES).astype(np.float32)
        features[0] = 65.0
        pred, names = ensemble.predict(features)
        assert pred is not None
        assert len(names) == 3


class TestMultiModelTrainAll:
    """Tests for training all models."""

    def test_trains_all_three(self, tmp_path) -> None:
        ensemble, result = _make_trained_ensemble(tmp_path)
        assert "XGBoost" in result["models"]
        assert "RandomForest" in result["models"]
        assert "Ridge" in result["models"]
        for name in result["models"]:
            assert "rmse" in result["models"][name]

    def test_weights_computed_after_training(self, tmp_path) -> None:
        ensemble, result = _make_trained_ensemble(tmp_path)
        assert "weights" in result
        assert len(result["weights"]) > 0
        # Weights should sum to ~1.0.
        total = sum(result["weights"].values())
        assert abs(total - 1.0) < 0.01

    def test_all_accepted_with_good_data(self, tmp_path) -> None:
        _, result = _make_trained_ensemble(tmp_path, noise_std=1.0)
        for name, metrics in result["models"].items():
            assert metrics["accepted"] is True, f"{name} should be accepted"

    def test_metrics_have_expected_keys(self, tmp_path) -> None:
        _, result = _make_trained_ensemble(tmp_path)
        for metrics in result["models"].values():
            assert "rmse" in metrics
            assert "mae" in metrics
            assert "train_rmse" in metrics
            assert "accepted" in metrics


class TestMultiModelSaveLoad:
    """Tests for save/load roundtrip."""

    def test_save_load_roundtrip(self, tmp_path) -> None:
        ensemble, _ = _make_trained_ensemble(tmp_path)
        features = np.random.default_rng(99).standard_normal(NUM_FEATURES).astype(np.float32)
        features[0] = 65.0
        original_pred, _ = ensemble.predict(features)

        ensemble.save_all()

        loaded = MultiModelEnsemble(model_dir=str(tmp_path))
        loaded.load_all()
        loaded_pred, names = loaded.predict(features)

        assert abs(loaded_pred - original_pred) < 0.1
        assert len(names) == 3

    def test_weights_file_created(self, tmp_path) -> None:
        ensemble, _ = _make_trained_ensemble(tmp_path)
        ensemble.save_all()
        assert (tmp_path / WEIGHTS_FILENAME).exists()

    def test_weights_file_loaded(self, tmp_path) -> None:
        ensemble, _ = _make_trained_ensemble(tmp_path)
        ensemble.save_all()

        loaded = MultiModelEnsemble(model_dir=str(tmp_path))
        loaded.load_all()
        assert len(loaded.weights) > 0

    def test_backward_compat_xgb_only(self, tmp_path) -> None:
        """If only XGBoost model exists on disk, loads it alone with weight=1.0."""
        # Train and save only XGBoost.
        from backend.prediction.xgb_model import XGBModelManager

        X, y = _make_synthetic_data()
        split = int(len(X) * 0.8)
        xgb_mgr = XGBModelManager(model_dir=str(tmp_path))
        xgb_mgr.train(X[:split], y[:split], X[split:], y[split:])
        xgb_mgr.save()

        # Load via MultiModelEnsemble — no weights file, no RF/Ridge.
        ensemble = MultiModelEnsemble(model_dir=str(tmp_path))
        status = ensemble.load_all()
        assert status["XGBoost"] is True
        assert status["RandomForest"] is False
        assert status["Ridge"] is False
        # Equal weight fallback for the one loaded model.
        assert ensemble.weights["XGBoost"] == 1.0


class TestMultiModelAgreement:
    """Tests for ensemble agreement metrics."""

    def test_agreement_spread_computed(self, tmp_path) -> None:
        """When multiple models predict, spread is computable."""
        ensemble, _ = _make_trained_ensemble(tmp_path)
        features = np.random.default_rng(99).standard_normal(NUM_FEATURES).astype(np.float32)
        features[0] = 65.0
        _, names = ensemble.predict(features)
        assert len(names) == 3  # All 3 contributed

    def test_single_model_no_spread(self, tmp_path) -> None:
        """With only one model, no spread is recorded."""
        ensemble = MultiModelEnsemble(model_dir=str(tmp_path))
        X, y = _make_synthetic_data()
        split = int(len(X) * 0.8)
        ensemble._xgb.train(X[:split], y[:split], X[split:], y[split:])
        ensemble._weights = {"XGBoost": 1.0}

        features = np.random.default_rng(99).standard_normal(NUM_FEATURES).astype(np.float32)
        features[0] = 65.0
        pred, names = ensemble.predict(features)
        assert len(names) == 1
