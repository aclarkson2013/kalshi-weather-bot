"""Model calibration against historical actuals.

Checks how well-calibrated our probability predictions have been by
comparing predicted bracket probabilities to actual outcomes. Uses the
Brier score as the primary calibration metric.

Usage:
    from backend.prediction.calibration import check_calibration

    report = await check_calibration("NYC", db_session=db)
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.response_schemas import CalibrationBucket, CalibrationReport
from backend.common.logging import get_logger
from backend.common.models import Prediction, Settlement

logger = get_logger("MODEL")

# Minimum sample count to consider calibration data meaningful
_MIN_SAMPLES = 10


def _temp_in_bracket(
    temp: float,
    lower: float | None,
    upper: float | None,
) -> bool:
    """Check whether a temperature falls within a bracket's bounds.

    Args:
        temp: Actual temperature in Fahrenheit.
        lower: Lower bound (inclusive), or None for bottom catch-all.
        upper: Upper bound (exclusive for middle brackets, inclusive for top catch-all),
               or None for top catch-all.

    Returns:
        True if temp lands in this bracket.
    """
    if lower is None and upper is None:
        return True
    if lower is None:
        # Bottom catch-all: temp <= upper
        return temp <= upper
    if upper is None:
        # Top catch-all: temp >= lower
        return temp >= lower
    # Middle bracket: lower <= temp < upper
    return lower <= temp < upper


async def check_calibration(
    city: str,
    db_session: AsyncSession,
    lookback_days: int = 90,
) -> CalibrationReport:
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
        CalibrationReport with Brier score and calibration buckets.
    """
    cutoff = datetime.utcnow() - timedelta(days=lookback_days)

    # Fetch predictions with matching settlements
    stmt = (
        select(Prediction.brackets_json, Settlement.actual_high_f)
        .join(
            Settlement,
            (Prediction.city == Settlement.city)
            & (Prediction.prediction_date == Settlement.settlement_date),
        )
        .where(
            Prediction.city == city,
            Settlement.actual_high_f.isnot(None),
            Prediction.prediction_date >= cutoff,
        )
        .order_by(Prediction.prediction_date.asc())
    )

    result = await db_session.execute(stmt)
    rows = result.all()

    if len(rows) < _MIN_SAMPLES:
        logger.info(
            "Insufficient calibration data",
            extra={
                "data": {
                    "city": city,
                    "lookback_days": lookback_days,
                    "sample_count": len(rows),
                    "min_required": _MIN_SAMPLES,
                }
            },
        )
        return CalibrationReport(
            city=city,
            lookback_days=lookback_days,
            sample_count=len(rows),
            brier_score=None,
            calibration_buckets=[],
            status="insufficient_data",
        )

    # Compute Brier score and collect data for calibration buckets
    brier_sum = 0.0
    total_bracket_predictions = 0
    # Calibration bins: 10 bins of width 0.1 (0-10%, 10-20%, ..., 90-100%)
    bin_predicted_sums: list[float] = [0.0] * 10
    bin_actual_sums: list[int] = [0] * 10
    bin_counts: list[int] = [0] * 10

    for brackets_json, actual_high in rows:
        # Parse brackets JSON
        brackets = brackets_json
        if isinstance(brackets, str):
            brackets = json.loads(brackets)

        for bracket in brackets:
            prob = bracket.get("probability", 0.0)
            lower = bracket.get("lower_bound_f")
            upper = bracket.get("upper_bound_f")

            outcome = 1 if _temp_in_bracket(actual_high, lower, upper) else 0

            # Brier score component
            brier_sum += (prob - outcome) ** 2
            total_bracket_predictions += 1

            # Calibration bin (0.0→bin0, 0.1→bin1, ..., 1.0→bin9)
            bin_idx = min(int(prob * 10), 9)
            bin_predicted_sums[bin_idx] += prob
            bin_actual_sums[bin_idx] += outcome
            bin_counts[bin_idx] += 1

    brier_score = brier_sum / total_bracket_predictions if total_bracket_predictions > 0 else None

    # Build calibration buckets (only include bins with data)
    calibration_buckets: list[CalibrationBucket] = []
    for i in range(10):
        if bin_counts[i] > 0:
            calibration_buckets.append(
                CalibrationBucket(
                    bin_start=round(i * 0.1, 1),
                    bin_end=round((i + 1) * 0.1, 1),
                    predicted_avg=round(bin_predicted_sums[i] / bin_counts[i], 4),
                    actual_rate=round(bin_actual_sums[i] / bin_counts[i], 4),
                    sample_count=bin_counts[i],
                )
            )

    logger.info(
        "Calibration check complete",
        extra={
            "data": {
                "city": city,
                "lookback_days": lookback_days,
                "sample_count": len(rows),
                "brier_score": round(brier_score, 4) if brier_score is not None else None,
                "buckets_count": len(calibration_buckets),
            }
        },
    )

    return CalibrationReport(
        city=city,
        lookback_days=lookback_days,
        sample_count=len(rows),
        brier_score=round(brier_score, 4) if brier_score is not None else None,
        calibration_buckets=calibration_buckets,
        status="ok",
    )
