"""Multi-model ensemble for temperature prediction.

Orchestrates multiple ML models (XGBoost, Random Forest, Ridge) with
inverse-RMSE weighted voting. Models with lower test error get higher
weights in the final prediction.

Usage:
    from backend.prediction.model_ensemble import MultiModelEnsemble

    ensemble = MultiModelEnsemble(model_dir="models")
    ensemble.load_all()
    prediction, model_names = ensemble.predict(features)
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

from backend.common.logging import get_logger
from backend.common.metrics import ML_ENSEMBLE_AGREEMENT_F, ML_MODELS_AVAILABLE
from backend.prediction.ml_models import RFModelManager, RidgeModelManager
from backend.prediction.xgb_model import XGBModelManager

logger = get_logger("MODEL")

WEIGHTS_FILENAME = "ml_weights.json"

# Canonical model names used in weights, metrics, and model_sources.
MODEL_NAMES = {
    "XGBoost": "XGBoost",
    "RandomForest": "RandomForest",
    "Ridge": "Ridge",
}


class MultiModelEnsemble:
    """Manages multiple ML models with inverse-RMSE weighted voting."""

    def __init__(self, model_dir: str = "models") -> None:
        self._model_dir = Path(model_dir)
        self._xgb = XGBModelManager(model_dir=model_dir)
        self._rf = RFModelManager(model_dir=model_dir)
        self._ridge = RidgeModelManager(model_dir=model_dir)
        self._weights: dict[str, float] = {}

    @property
    def _managers(self) -> dict[str, XGBModelManager | RFModelManager | RidgeModelManager]:
        """Map of model name → manager instance."""
        return {
            MODEL_NAMES["XGBoost"]: self._xgb,
            MODEL_NAMES["RandomForest"]: self._rf,
            MODEL_NAMES["Ridge"]: self._ridge,
        }

    @property
    def weights(self) -> dict[str, float]:
        """Current model weights."""
        return dict(self._weights)

    def load_all(self) -> dict[str, bool]:
        """Load all models from disk, plus weights file if present.

        Returns:
            Dict mapping model name → whether it loaded successfully.
        """
        status = {}
        for name, manager in self._managers.items():
            status[name] = manager.load()

        # Load weights from file.
        weights_path = self._model_dir / WEIGHTS_FILENAME
        if weights_path.exists():
            try:
                data = json.loads(weights_path.read_text())
                self._weights = data.get("weights", {})
            except Exception:
                logger.warning("Failed to load ML weights file", exc_info=True)
                self._weights = {}

        # If no weights file but some models loaded, use equal weights.
        available = [n for n, ok in status.items() if ok]
        if not self._weights and available:
            self._weights = {n: 1.0 / len(available) for n in available}

        ML_MODELS_AVAILABLE.set(len(available))

        return status

    def is_any_available(self) -> bool:
        """True if at least one model is loaded."""
        return any(m.is_available() for m in self._managers.values())

    def predict(self, features: np.ndarray) -> tuple[float | None, list[str]]:
        """Weighted prediction across all available models.

        Returns:
            (weighted_prediction, list_of_contributing_model_names).
            Returns (None, []) if no models are available.
        """
        predictions: dict[str, float] = {}
        for name, manager in self._managers.items():
            if not manager.is_available():
                continue
            try:
                predictions[name] = manager.predict(features)
            except Exception:
                logger.warning(f"{name} prediction failed", exc_info=True)

        if not predictions:
            return None, []

        # Record model agreement (spread).
        values = list(predictions.values())
        if len(values) > 1:
            spread = max(values) - min(values)
            ML_ENSEMBLE_AGREEMENT_F.observe(spread)

        # Weighted average.
        weighted_sum = 0.0
        weight_total = 0.0
        contributing: list[str] = []

        for name, pred in predictions.items():
            w = self._weights.get(name, 0.0)
            if w <= 0:
                # Fallback: equal weight when no stored weight for this model.
                w = 1.0 / len(predictions)
            weighted_sum += pred * w
            weight_total += w
            contributing.append(name)

        if weight_total <= 0:
            return None, []

        return weighted_sum / weight_total, contributing

    def train_all(
        self,
        x_train: np.ndarray,
        y_train: np.ndarray,
        x_test: np.ndarray,
        y_test: np.ndarray,
    ) -> dict:
        """Train all three models and compute inverse-RMSE weights.

        Args:
            x_train: Training features.
            y_train: Training targets.
            x_test: Test features.
            y_test: Test targets.

        Returns:
            Dict with per-model metrics and computed weights.
        """
        all_metrics: dict[str, dict] = {}

        for name, manager in self._managers.items():
            try:
                metrics = manager.train(x_train, y_train, x_test, y_test)
                all_metrics[name] = metrics
                logger.info(
                    f"{name} training complete",
                    extra={"data": {"model": name, **metrics}},
                )
            except Exception:
                logger.error(f"{name} training failed", exc_info=True)
                all_metrics[name] = {"accepted": False, "error": "training_failed"}

        # Compute inverse-RMSE weights for accepted models.
        self._weights = self.compute_inverse_rmse_weights(all_metrics)

        return {
            "models": all_metrics,
            "weights": self._weights,
        }

    def save_all(self) -> None:
        """Save all accepted models and the weights file to disk."""
        self._model_dir.mkdir(parents=True, exist_ok=True)

        for name, manager in self._managers.items():
            if manager.is_available():
                try:
                    manager.save()
                except Exception:
                    logger.error(f"Failed to save {name} model", exc_info=True)

        # Save weights.
        weights_path = self._model_dir / WEIGHTS_FILENAME
        weights_data = {
            "weights": self._weights,
            "computed_at": datetime.now(UTC).isoformat(),
        }
        weights_path.write_text(json.dumps(weights_data, indent=2))

        logger.info(
            "Multi-model ensemble saved",
            extra={"data": {"weights": self._weights}},
        )

    @staticmethod
    def compute_inverse_rmse_weights(metrics: dict[str, dict]) -> dict[str, float]:
        """Compute normalized inverse-RMSE weights for accepted models.

        Models with lower RMSE get higher weight. Rejected models are excluded.

        Args:
            metrics: {model_name: {"rmse": float, "accepted": bool, ...}}

        Returns:
            {model_name: weight} where weights sum to 1.0.
            Empty dict if no models were accepted.
        """
        inverse_scores: dict[str, float] = {}

        for name, m in metrics.items():
            if not m.get("accepted"):
                continue
            rmse = m.get("rmse", 0.0)
            if rmse is None or rmse <= 0:
                # Perfect model or invalid — give a very high inverse score.
                inverse_scores[name] = 100.0
            else:
                inverse_scores[name] = 1.0 / rmse

        if not inverse_scores:
            return {}

        total = sum(inverse_scores.values())
        return {name: round(score / total, 4) for name, score in inverse_scores.items()}
