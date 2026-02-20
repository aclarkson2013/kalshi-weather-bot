"""Multi-model training pipeline (Celery task).

Queries historical forecast-vs-settlement data from the database, engineers
features, and trains all ML models (XGBoost, Random Forest, Ridge).
Computes inverse-RMSE weights and saves accepted models to disk.

Run manually:
    from backend.prediction.train_models import train_all_models
    train_all_models.apply()

Scheduled: Sunday 3 AM ET via Celery Beat (see celery_app.py).
"""

from __future__ import annotations

import time

from asgiref.sync import async_to_sync

from backend.celery_app import celery_app
from backend.common.config import get_settings
from backend.common.logging import get_logger
from backend.common.metrics import ML_TRAINING_DURATION_SECONDS
from backend.prediction.features import NUM_FEATURES
from backend.prediction.model_ensemble import MultiModelEnsemble
from backend.prediction.train_xgb import _fetch_training_data, _rows_to_arrays

logger = get_logger("MODEL")


async def _train_all_async() -> dict:
    """Async training logic — fetches data and trains all models.

    Returns:
        Training metrics dict, or dict with status="skipped" if insufficient data.
    """
    from backend.common.database import async_session

    settings = get_settings()

    async with async_session() as session:
        rows = await _fetch_training_data(session)

    if len(rows) < settings.xgb_min_training_samples:
        logger.info(
            "Insufficient training data for ML models",
            extra={
                "data": {
                    "row_count": len(rows),
                    "min_required": settings.xgb_min_training_samples,
                }
            },
        )
        return {"status": "skipped", "reason": "insufficient_data", "row_count": len(rows)}

    X, y = _rows_to_arrays(rows)  # noqa: N806

    if X.shape[1] != NUM_FEATURES:
        logger.error(
            "Feature count mismatch in training data",
            extra={"data": {"expected": NUM_FEATURES, "got": X.shape[1]}},
        )
        return {"status": "error", "reason": "feature_mismatch"}

    # Chronological split — respect time series ordering.
    split_idx = int(len(X) * 0.8)
    x_train, x_test = X[:split_idx], X[split_idx:]
    y_train, y_test = y[:split_idx], y[split_idx:]

    ensemble = MultiModelEnsemble(model_dir=settings.xgb_model_dir)
    result = ensemble.train_all(x_train, y_train, x_test, y_test)
    ensemble.save_all()

    result["status"] = "completed"
    result["row_count"] = len(rows)
    return result


@celery_app.task(
    bind=True,
    name="backend.prediction.train_models.train_all_models",
    soft_time_limit=600,
    time_limit=720,
)
def train_all_models(self) -> dict:  # noqa: ANN001
    """Celery task: Train all ML models on historical forecast vs. settlement data.

    Scheduled weekly via Celery Beat. Can also be run manually:
        train_all_models.apply()
    """
    start = time.monotonic()

    try:
        result = async_to_sync(_train_all_async)()

        duration = time.monotonic() - start
        ML_TRAINING_DURATION_SECONDS.observe(duration)

        logger.info(
            "Multi-model training task completed",
            extra={"data": {"duration_s": round(duration, 1), "result": result}},
        )

        return result

    except Exception as e:
        duration = time.monotonic() - start
        ML_TRAINING_DURATION_SECONDS.observe(duration)

        logger.error(
            "Multi-model training task failed",
            extra={"data": {"error": str(e), "duration_s": round(duration, 1)}},
        )
        raise
