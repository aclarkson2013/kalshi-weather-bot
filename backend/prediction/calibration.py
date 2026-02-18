"""Model calibration against historical actuals.

Checks how well-calibrated our probability predictions have been by
comparing predicted bracket probabilities to actual outcomes. Uses the
Brier score as the primary calibration metric.

This is a Phase 2 feature. The current implementation is a stub that
returns an "insufficient_data" status.

Usage:
    from backend.prediction.calibration import check_calibration

    report = await check_calibration("NYC", db_session=db)
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from backend.common.logging import get_logger

logger = get_logger("MODEL")


async def check_calibration(
    city: str,
    db_session: AsyncSession,
    lookback_days: int = 90,
) -> dict:
    """Check how well-calibrated our probability predictions have been.

    Compares predicted bracket probabilities to actual outcomes over the
    lookback period. For example, if we predicted 30% probability for a
    bracket across 100 days, the actual outcome should have landed in
    that bracket ~30 times.

    The Brier score is the standard metric for probability calibration:
        Brier = (1/N) * sum((predicted_prob - actual_outcome)^2)
        actual_outcome is 1 if temp landed in that bracket, 0 otherwise.
        Lower is better. 0.0 = perfect predictions.

    Args:
        city: City code ("NYC", "CHI", "MIA", "AUS").
        db_session: SQLAlchemy async session.
        lookback_days: Number of days to look back for calibration data.

    Returns:
        Dict with calibration metrics:
        {
            "city": str,
            "lookback_days": int,
            "sample_count": int,
            "brier_score": float | None,
            "calibration_buckets": list[dict],
            "status": str,
        }
    """
    # Phase 2: Implement actual calibration check.
    # For now, return a stub indicating no data.
    logger.info(
        "Calibration check requested (not yet implemented)",
        extra={
            "data": {
                "city": city,
                "lookback_days": lookback_days,
            }
        },
    )

    return {
        "city": city,
        "lookback_days": lookback_days,
        "sample_count": 0,
        "brier_score": None,
        "calibration_buckets": [],
        "status": "insufficient_data",
    }
