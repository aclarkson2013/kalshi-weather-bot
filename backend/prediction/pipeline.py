"""Prediction pipeline orchestrator.

Ties together the four prediction steps into a single entry point:
    1. Ensemble forecast (weighted average of multiple sources)
    2. Historical error distribution (per city/season)
    3. Bracket probability calculation (normal CDF)
    4. Confidence assessment (model agreement, accuracy, freshness)

Usage:
    from backend.prediction.pipeline import generate_prediction

    prediction = await generate_prediction(
        city="NYC",
        target_date=date(2026, 2, 18),
        forecasts=weather_data_list,
        kalshi_brackets=bracket_defs,
        db_session=db,
    )
"""

from __future__ import annotations

from datetime import UTC, date, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from backend.common.config import get_settings
from backend.common.logging import get_logger
from backend.common.metrics import ML_PREDICTIONS_TOTAL
from backend.common.schemas import BracketPrediction, WeatherData
from backend.prediction.brackets import calculate_bracket_probabilities
from backend.prediction.ensemble import assess_confidence, calculate_ensemble_forecast
from backend.prediction.error_dist import calculate_error_std
from backend.prediction.features import extract_features
from backend.prediction.model_ensemble import MultiModelEnsemble

logger = get_logger("MODEL")

# ─── Multi-model ensemble singleton (lazy-loaded on first use) ───
_ml_ensemble: MultiModelEnsemble | None = None


def _get_ml_ensemble() -> MultiModelEnsemble:
    """Get or initialize the multi-model ensemble singleton."""
    global _ml_ensemble  # noqa: PLW0603
    if _ml_ensemble is None:
        settings = get_settings()
        _ml_ensemble = MultiModelEnsemble(model_dir=settings.xgb_model_dir)
        status = _ml_ensemble.load_all()
        available = [k for k, v in status.items() if v]
        if available:
            logger.info(
                "ML models loaded",
                extra={"data": {"models": available, "weights": _ml_ensemble.weights}},
            )
        else:
            logger.info("No ML models available — ensemble-only mode")
    return _ml_ensemble


def _try_multi_model_prediction(
    forecasts: list[WeatherData],
    city: str,
    target_date: date,
) -> tuple[float | None, list[str]]:
    """Attempt a multi-model ML prediction, returning (None, []) on any failure.

    This function wraps all ML logic in try/except so the pipeline
    never crashes due to ML issues — it just falls back to ensemble-only.

    Returns:
        (predicted_temp, list_of_model_names) or (None, []) on failure.
    """
    settings = get_settings()
    if settings.ml_ensemble_weight <= 0.0:
        return None, []

    try:
        ensemble = _get_ml_ensemble()
        if not ensemble.is_any_available():
            return None, []

        features = extract_features(forecasts, city, target_date)
        prediction, model_names = ensemble.predict(features)

        if prediction is not None:
            for name in model_names:
                ML_PREDICTIONS_TOTAL.labels(city=city, model=name, status="success").inc()

        return prediction, model_names

    except Exception:
        ML_PREDICTIONS_TOTAL.labels(city=city, model="ensemble", status="error").inc()
        logger.warning(
            "Multi-model prediction failed — falling back to ensemble",
            extra={"data": {"city": city, "date": str(target_date)}},
            exc_info=True,
        )
        return None, []


async def generate_prediction(
    city: str,
    target_date: date,
    forecasts: list[WeatherData],
    kalshi_brackets: list[dict],
    db_session: AsyncSession,
    model_weights: dict[str, float] | None = None,
) -> BracketPrediction:
    """Run the full prediction pipeline for one city and date.

    This is the main entry point for the prediction engine. It orchestrates
    all four steps and returns a complete BracketPrediction ready for the
    trading engine.

    Args:
        city: City code ("NYC", "CHI", "MIA", "AUS").
        target_date: The date we are predicting the high temperature for.
        forecasts: List of WeatherData from multiple sources for this city/date.
        kalshi_brackets: Bracket definitions from Kalshi market data. Each dict
            must have keys: "lower_bound_f" (float|None), "upper_bound_f"
            (float|None), "label" (str).
        db_session: SQLAlchemy async session (for historical error lookup).
        model_weights: Optional override for ensemble weights.

    Returns:
        A complete BracketPrediction ready for the trading engine.
    """
    # Step 1: Ensemble forecast
    ensemble_temp, spread, sources = calculate_ensemble_forecast(
        forecasts,
        weights=model_weights,
    )

    # Step 1b: Multi-model ML prediction (blended with ensemble, graceful degradation)
    ml_temp, ml_models = _try_multi_model_prediction(forecasts, city, target_date)
    if ml_temp is not None:
        ml_weight = get_settings().ml_ensemble_weight
        final_temp = (1 - ml_weight) * ensemble_temp + ml_weight * ml_temp
        sources.extend(ml_models)
        logger.debug(
            "ML ensemble blended",
            extra={
                "data": {
                    "city": city,
                    "ensemble_temp": round(ensemble_temp, 2),
                    "ml_temp": round(ml_temp, 2),
                    "ml_weight": ml_weight,
                    "ml_models": ml_models,
                    "final_temp": round(final_temp, 2),
                }
            },
        )
        ensemble_temp = final_temp

    # Step 2: Historical error distribution
    error_std = await calculate_error_std(
        city=city,
        month=target_date.month,
        db_session=db_session,
    )

    # Step 3: Bracket probabilities
    bracket_probs = calculate_bracket_probabilities(
        ensemble_forecast_f=ensemble_temp,
        error_std_f=error_std,
        brackets=kalshi_brackets,
    )

    # Step 4: Confidence assessment
    # Calculate data age from the oldest forecast timestamp.
    now = datetime.now(UTC)
    oldest_forecast = min(fc.fetched_at for fc in forecasts)
    # Handle timezone-aware vs naive comparison safely.
    if oldest_forecast.tzinfo is None:
        data_age_minutes = (now.replace(tzinfo=None) - oldest_forecast).total_seconds() / 60.0
    else:
        data_age_minutes = (now - oldest_forecast).total_seconds() / 60.0

    confidence = assess_confidence(
        forecast_spread_f=spread,
        error_std_f=error_std,
        num_sources=len(sources),
        data_age_minutes=data_age_minutes,
    )

    # Build the BracketPrediction using the ACTUAL schema field names:
    # ensemble_mean_f (not ensemble_forecast_f), ensemble_std_f (not error_std_f).
    prediction = BracketPrediction(
        city=city,
        date=target_date,
        brackets=bracket_probs,
        ensemble_mean_f=round(ensemble_temp, 2),
        ensemble_std_f=round(error_std, 2),
        confidence=confidence,
        model_sources=sources,
        generated_at=now,
    )

    logger.info(
        "Prediction generated",
        extra={
            "data": {
                "city": city,
                "date": str(target_date),
                "ensemble_mean_f": prediction.ensemble_mean_f,
                "ensemble_std_f": prediction.ensemble_std_f,
                "confidence": confidence,
                "spread_f": round(spread, 2),
                "sources": sources,
                "bracket_count": len(bracket_probs),
            }
        },
    )

    return prediction
