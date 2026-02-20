"""Scikit-learn model managers for temperature prediction.

Provides Random Forest and Ridge Regression model managers that follow the
same interface as XGBModelManager: load, predict, train, save, is_available.

Key difference from XGBoost: sklearn models do NOT handle NaN natively.
NaN features are replaced with column-wise medians from training data.
These medians are stored in metadata and persist through save/load cycles.

Usage:
    from backend.prediction.ml_models import RFModelManager, RidgeModelManager

    rf = RFModelManager(model_dir="models")
    if rf.load():
        temp = rf.predict(features)
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import joblib
import numpy as np
from sklearn.ensemble import RandomForestRegressor
from sklearn.linear_model import Ridge
from sklearn.metrics import mean_absolute_error, mean_squared_error

from backend.common.logging import get_logger
from backend.prediction.features import NUM_FEATURES

logger = get_logger("MODEL")

# Rejection threshold — same as XGBoost.
MAX_ACCEPTABLE_RMSE = 5.0  # degrees Fahrenheit

# ─── Random Forest defaults ───
RF_MODEL_FILENAME = "rf_temp.joblib"
RF_METADATA_FILENAME = "rf_temp_meta.json"
DEFAULT_RF_PARAMS: dict = {
    "n_estimators": 200,
    "max_depth": 8,
    "min_samples_split": 5,
    "min_samples_leaf": 3,
    "random_state": 42,
    "n_jobs": 1,  # single-threaded for Celery safety
}

# ─── Ridge Regression defaults ───
RIDGE_MODEL_FILENAME = "ridge_temp.joblib"
RIDGE_METADATA_FILENAME = "ridge_temp_meta.json"
DEFAULT_RIDGE_PARAMS: dict = {
    "alpha": 1.0,
}


def _impute_nan(features: np.ndarray, fill_values: np.ndarray) -> np.ndarray:
    """Replace NaN values in features with stored fill values (medians)."""
    result = features.copy()
    nan_mask = np.isnan(result)
    if nan_mask.any():
        # For 1-D input, fill directly; for 2-D, broadcast by column.
        if result.ndim == 1:
            result[nan_mask] = fill_values[nan_mask]
        else:
            for col in range(result.shape[1]):
                col_mask = nan_mask[:, col]
                result[col_mask, col] = fill_values[col]
    return result


class RFModelManager:
    """Manages Random Forest model lifecycle: load, predict, train, save."""

    def __init__(self, model_dir: str = "models") -> None:
        self._model: RandomForestRegressor | None = None
        self._model_dir = Path(model_dir)
        self._metadata: dict | None = None
        self._nan_fill_values: np.ndarray | None = None

    @property
    def model_path(self) -> Path:
        """Path to the serialized model file."""
        return self._model_dir / RF_MODEL_FILENAME

    @property
    def metadata_path(self) -> Path:
        """Path to the model metadata file."""
        return self._model_dir / RF_METADATA_FILENAME

    def is_available(self) -> bool:
        """Check if a trained model is loaded and ready for predictions."""
        return self._model is not None

    @property
    def metadata(self) -> dict | None:
        """Model training metadata."""
        return self._metadata

    def load(self) -> bool:
        """Load a trained model from disk.

        Returns:
            True if model was loaded successfully, False otherwise.
        """
        if not self.model_path.exists():
            logger.info(
                "No Random Forest model file found",
                extra={"data": {"path": str(self.model_path)}},
            )
            return False

        try:
            self._model = joblib.load(self.model_path)

            if self.metadata_path.exists():
                self._metadata = json.loads(self.metadata_path.read_text())
                # Restore NaN fill values from metadata.
                fill_list = self._metadata.get("nan_fill_values")
                if fill_list is not None:
                    self._nan_fill_values = np.array(fill_list, dtype=np.float32)

            logger.info(
                "Random Forest model loaded",
                extra={"data": {"path": str(self.model_path)}},
            )
            return True

        except Exception as e:
            logger.warning(
                "Failed to load Random Forest model",
                extra={"data": {"error": str(e), "path": str(self.model_path)}},
            )
            self._model = None
            return False

    def predict(self, features: np.ndarray) -> float:
        """Predict high temperature from a feature vector.

        NaN values are replaced with column medians from training data.

        Args:
            features: 1-D array of shape (NUM_FEATURES,) from extract_features().

        Returns:
            Predicted high temperature in Fahrenheit.

        Raises:
            RuntimeError: If model is not loaded.
            ValueError: If feature vector has wrong shape.
        """
        if self._model is None:
            raise RuntimeError("Random Forest model not loaded — call load() first")

        if features.ndim == 1:
            features = features.reshape(1, -1)

        if features.shape[1] != NUM_FEATURES:
            raise ValueError(f"Expected {NUM_FEATURES} features, got {features.shape[1]}")

        # Impute NaN values before prediction.
        if self._nan_fill_values is not None:
            features = _impute_nan(features, self._nan_fill_values)

        prediction = self._model.predict(features)
        return float(prediction[0])

    def train(
        self,
        x_train: np.ndarray,
        y_train: np.ndarray,
        x_test: np.ndarray,
        y_test: np.ndarray,
    ) -> dict:
        """Train a new Random Forest model on historical data.

        Args:
            x_train: Training features, shape (n_train, NUM_FEATURES).
            y_train: Training targets, shape (n_train,).
            x_test: Test features, shape (n_test, NUM_FEATURES).
            y_test: Test targets, shape (n_test,).

        Returns:
            Dict with training metrics including rmse, mae, accepted.
        """
        # Compute NaN fill values from training data.
        self._nan_fill_values = np.nanmedian(x_train, axis=0).astype(np.float32)

        # Impute NaN in training and test data.
        x_train_clean = _impute_nan(x_train, self._nan_fill_values)
        x_test_clean = _impute_nan(x_test, self._nan_fill_values)

        model = RandomForestRegressor(**DEFAULT_RF_PARAMS)
        model.fit(x_train_clean, y_train)

        y_pred = model.predict(x_test_clean)
        rmse = float(np.sqrt(mean_squared_error(y_test, y_pred)))
        mae = float(mean_absolute_error(y_test, y_pred))

        y_train_pred = model.predict(x_train_clean)
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
            "nan_fill_values": self._nan_fill_values.tolist(),
        }

        if accepted:
            self._model = model
            self._metadata = metrics
            logger.info("Random Forest model trained and accepted", extra={"data": metrics})
        else:
            logger.warning("Random Forest model rejected — RMSE too high", extra={"data": metrics})

        return metrics

    def save(self) -> None:
        """Save the trained model and metadata to disk.

        Raises:
            RuntimeError: If no model is loaded/trained.
        """
        if self._model is None:
            raise RuntimeError("No model to save — train or load first")

        self._model_dir.mkdir(parents=True, exist_ok=True)
        joblib.dump(self._model, self.model_path)

        if self._metadata:
            self.metadata_path.write_text(json.dumps(self._metadata, indent=2))

        logger.info(
            "Random Forest model saved",
            extra={"data": {"path": str(self.model_path)}},
        )


class RidgeModelManager:
    """Manages Ridge Regression model lifecycle: load, predict, train, save."""

    def __init__(self, model_dir: str = "models") -> None:
        self._model: Ridge | None = None
        self._model_dir = Path(model_dir)
        self._metadata: dict | None = None
        self._nan_fill_values: np.ndarray | None = None

    @property
    def model_path(self) -> Path:
        """Path to the serialized model file."""
        return self._model_dir / RIDGE_MODEL_FILENAME

    @property
    def metadata_path(self) -> Path:
        """Path to the model metadata file."""
        return self._model_dir / RIDGE_METADATA_FILENAME

    def is_available(self) -> bool:
        """Check if a trained model is loaded and ready for predictions."""
        return self._model is not None

    @property
    def metadata(self) -> dict | None:
        """Model training metadata."""
        return self._metadata

    def load(self) -> bool:
        """Load a trained model from disk.

        Returns:
            True if model was loaded successfully, False otherwise.
        """
        if not self.model_path.exists():
            logger.info(
                "No Ridge model file found",
                extra={"data": {"path": str(self.model_path)}},
            )
            return False

        try:
            self._model = joblib.load(self.model_path)

            if self.metadata_path.exists():
                self._metadata = json.loads(self.metadata_path.read_text())
                fill_list = self._metadata.get("nan_fill_values")
                if fill_list is not None:
                    self._nan_fill_values = np.array(fill_list, dtype=np.float32)

            logger.info(
                "Ridge model loaded",
                extra={"data": {"path": str(self.model_path)}},
            )
            return True

        except Exception as e:
            logger.warning(
                "Failed to load Ridge model",
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
            raise RuntimeError("Ridge model not loaded — call load() first")

        if features.ndim == 1:
            features = features.reshape(1, -1)

        if features.shape[1] != NUM_FEATURES:
            raise ValueError(f"Expected {NUM_FEATURES} features, got {features.shape[1]}")

        if self._nan_fill_values is not None:
            features = _impute_nan(features, self._nan_fill_values)

        prediction = self._model.predict(features)
        return float(prediction[0])

    def train(
        self,
        x_train: np.ndarray,
        y_train: np.ndarray,
        x_test: np.ndarray,
        y_test: np.ndarray,
    ) -> dict:
        """Train a new Ridge Regression model on historical data.

        Args:
            x_train: Training features, shape (n_train, NUM_FEATURES).
            y_train: Training targets, shape (n_train,).
            x_test: Test features, shape (n_test, NUM_FEATURES).
            y_test: Test targets, shape (n_test,).

        Returns:
            Dict with training metrics including rmse, mae, accepted.
        """
        self._nan_fill_values = np.nanmedian(x_train, axis=0).astype(np.float32)

        x_train_clean = _impute_nan(x_train, self._nan_fill_values)
        x_test_clean = _impute_nan(x_test, self._nan_fill_values)

        model = Ridge(**DEFAULT_RIDGE_PARAMS)
        model.fit(x_train_clean, y_train)

        y_pred = model.predict(x_test_clean)
        rmse = float(np.sqrt(mean_squared_error(y_test, y_pred)))
        mae = float(mean_absolute_error(y_test, y_pred))

        y_train_pred = model.predict(x_train_clean)
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
            "nan_fill_values": self._nan_fill_values.tolist(),
        }

        if accepted:
            self._model = model
            self._metadata = metrics
            logger.info("Ridge model trained and accepted", extra={"data": metrics})
        else:
            logger.warning("Ridge model rejected — RMSE too high", extra={"data": metrics})

        return metrics

    def save(self) -> None:
        """Save the trained model and metadata to disk.

        Raises:
            RuntimeError: If no model is loaded/trained.
        """
        if self._model is None:
            raise RuntimeError("No model to save — train or load first")

        self._model_dir.mkdir(parents=True, exist_ok=True)
        joblib.dump(self._model, self.model_path)

        if self._metadata:
            self.metadata_path.write_text(json.dumps(self._metadata, indent=2))

        logger.info(
            "Ridge model saved",
            extra={"data": {"path": str(self.model_path)}},
        )
