"""XGBoost model manager for temperature prediction.

Handles model lifecycle: loading from disk, making predictions, training
on historical data, and saving trained models.

Uses XGBoost JSON format for serialization (portable, human-readable,
not pickle — avoids security and compatibility issues).

Usage:
    from backend.prediction.xgb_model import XGBModelManager

    manager = XGBModelManager(model_dir="models")
    if manager.load():
        temp = manager.predict(features)
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import xgboost as xgb
from sklearn.metrics import mean_absolute_error, mean_squared_error

from backend.common.logging import get_logger
from backend.prediction.features import NUM_FEATURES

logger = get_logger("MODEL")

# Conservative hyperparameters — tuned for small datasets (<10K samples).
DEFAULT_PARAMS: dict = {
    "max_depth": 5,
    "learning_rate": 0.1,
    "n_estimators": 200,
    "subsample": 0.8,
    "colsample_bytree": 0.8,
    "objective": "reg:squarederror",
    "eval_metric": "rmse",
    "random_state": 42,
    "verbosity": 0,
}

# Model files.
MODEL_FILENAME = "xgb_temp.json"
METADATA_FILENAME = "xgb_temp_meta.json"

# Rejection threshold — don't deploy a model worse than this.
MAX_ACCEPTABLE_RMSE = 5.0  # degrees Fahrenheit


class XGBModelManager:
    """Manages XGBoost model lifecycle: load, predict, train, save."""

    def __init__(self, model_dir: str = "models") -> None:
        self._model: xgb.XGBRegressor | None = None
        self._model_dir = Path(model_dir)
        self._metadata: dict | None = None

    @property
    def model_path(self) -> Path:
        """Path to the serialized model file."""
        return self._model_dir / MODEL_FILENAME

    @property
    def metadata_path(self) -> Path:
        """Path to the model metadata file."""
        return self._model_dir / METADATA_FILENAME

    def is_available(self) -> bool:
        """Check if a trained model is loaded and ready for predictions."""
        return self._model is not None

    @property
    def metadata(self) -> dict | None:
        """Model training metadata (date, RMSE, MAE, sample count)."""
        return self._metadata

    def load(self) -> bool:
        """Load a trained model from disk.

        Returns:
            True if model was loaded successfully, False otherwise.
        """
        if not self.model_path.exists():
            logger.info(
                "No XGBoost model file found",
                extra={"data": {"path": str(self.model_path)}},
            )
            return False

        try:
            model = xgb.XGBRegressor()
            model.load_model(str(self.model_path))
            self._model = model

            # Load metadata if available.
            if self.metadata_path.exists():
                self._metadata = json.loads(self.metadata_path.read_text())

            logger.info(
                "XGBoost model loaded",
                extra={
                    "data": {
                        "path": str(self.model_path),
                        "metadata": self._metadata,
                    }
                },
            )
            return True

        except Exception as e:
            logger.warning(
                "Failed to load XGBoost model",
                extra={"data": {"error": str(e), "path": str(self.model_path)}},
            )
            self._model = None
            return False

    def predict(self, features: np.ndarray) -> float:
        """Predict high temperature from a feature vector.

        Args:
            features: 1-D array of shape (NUM_FEATURES,) from extract_features().

        Returns:
            Predicted high temperature in Fahrenheit.

        Raises:
            RuntimeError: If model is not loaded.
            ValueError: If feature vector has wrong shape.
        """
        if self._model is None:
            raise RuntimeError("XGBoost model not loaded — call load() first")

        if features.ndim == 1:
            features = features.reshape(1, -1)

        if features.shape[1] != NUM_FEATURES:
            raise ValueError(f"Expected {NUM_FEATURES} features, got {features.shape[1]}")

        prediction = self._model.predict(features)
        return float(prediction[0])

    def train(
        self,
        x_train: np.ndarray,
        y_train: np.ndarray,
        x_test: np.ndarray,
        y_test: np.ndarray,
    ) -> dict:
        """Train a new XGBoost model on historical data.

        Uses early stopping on the test set to prevent overfitting.

        Args:
            x_train: Training features, shape (n_train, NUM_FEATURES).
            y_train: Training targets (actual_high_f), shape (n_train,).
            x_test: Test features, shape (n_test, NUM_FEATURES).
            y_test: Test targets, shape (n_test,).

        Returns:
            Dict with training metrics: rmse, mae, train_rmse, sample_count,
            trained_at, accepted (bool).
        """
        model = xgb.XGBRegressor(
            **DEFAULT_PARAMS,
            early_stopping_rounds=20,
        )

        model.fit(
            x_train,
            y_train,
            eval_set=[(x_test, y_test)],
            verbose=False,
        )

        # Evaluate on test set.
        y_pred = model.predict(x_test)
        rmse = float(np.sqrt(mean_squared_error(y_test, y_pred)))
        mae = float(mean_absolute_error(y_test, y_pred))

        # Evaluate on training set (for comparison / overfitting check).
        y_train_pred = model.predict(x_train)
        train_rmse = float(np.sqrt(mean_squared_error(y_train, y_train_pred)))

        accepted = rmse <= MAX_ACCEPTABLE_RMSE

        metrics = {
            "rmse": round(rmse, 3),
            "mae": round(mae, 3),
            "train_rmse": round(train_rmse, 3),
            "sample_count": len(y_train) + len(y_test),
            "train_count": len(y_train),
            "test_count": len(y_test),
            "trained_at": datetime.now(UTC).isoformat(),
            "accepted": accepted,
            "best_iteration": model.best_iteration if hasattr(model, "best_iteration") else None,
        }

        if accepted:
            self._model = model
            self._metadata = metrics
            logger.info(
                "XGBoost model trained and accepted",
                extra={"data": metrics},
            )
        else:
            logger.warning(
                "XGBoost model rejected — RMSE too high",
                extra={"data": metrics},
            )

        return metrics

    def save(self) -> None:
        """Save the trained model and metadata to disk.

        Creates the model directory if it doesn't exist.

        Raises:
            RuntimeError: If no model is loaded/trained.
        """
        if self._model is None:
            raise RuntimeError("No model to save — train or load first")

        self._model_dir.mkdir(parents=True, exist_ok=True)
        self._model.save_model(str(self.model_path))

        if self._metadata:
            self.metadata_path.write_text(json.dumps(self._metadata, indent=2))

        logger.info(
            "XGBoost model saved",
            extra={"data": {"path": str(self.model_path)}},
        )

    def get_feature_importance(self) -> dict[str, float] | None:
        """Get feature importance scores from the trained model.

        Returns:
            Dict mapping feature names to importance scores, or None if
            no model is loaded.
        """
        if self._model is None:
            return None

        from backend.prediction.features import FEATURE_NAMES

        importances = self._model.feature_importances_
        return {
            name: round(float(score), 4)
            for name, score in zip(FEATURE_NAMES, importances, strict=True)
            if score > 0
        }
