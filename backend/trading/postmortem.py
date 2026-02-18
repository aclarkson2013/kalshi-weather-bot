"""Post-settlement trade analysis and narrative generation.

After market settlement (NWS CLI report published), this module:
1. Determines if a trade won or lost based on actual temperature
2. Calculates final P&L in cents (including Kalshi fees)
3. Generates a human-readable narrative explaining the outcome
4. Updates the Trade record with settlement data

CRITICAL: All monetary calculations use CENTS (integers). The Trade ORM model
uses pnl_cents (int) and fees_cents (int).

Bracket label formats:
    "53-54F"   -> standard 2-degree bracket (lower <= temp <= upper)
    "<=52F"    -> bottom catch-all (temp <= bound)
    ">=57F"    -> top catch-all (temp >= bound)

Usage:
    from backend.trading.postmortem import settle_trade

    await settle_trade(trade, settlement, db)
"""

from __future__ import annotations

import re
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.common.logging import get_logger
from backend.common.models import (
    Settlement,
    Trade,
    TradeStatus,
    WeatherForecast,
)
from backend.trading.ev_calculator import estimate_fees

logger = get_logger("POSTMORTEM")


def generate_postmortem_narrative(
    trade: Trade,
    settlement: Settlement,
    forecasts: list[WeatherForecast],
) -> str:
    """Generate a human-readable post-mortem explanation for a trade.

    Compares the model prediction, market price, and actual outcome to
    explain why the trade won or lost.

    Args:
        trade: The Trade ORM model (must have status set to WON or LOST).
        settlement: The Settlement ORM with actual temperature data.
        forecasts: Weather forecasts that were active at trade time.

    Returns:
        A narrative string suitable for display in the PWA dashboard.

    Example output:
        "WIN (+78c): Bought YES on NYC 53-54F at 22c. Actual high was 53F.
        Our model predicted 28% probability. Forecast accuracy:
        NWS: 54F (+1F off); GFS: 53F (+0F off)."
    """
    actual_temp = settlement.actual_high_f
    bracket = trade.bracket_label
    side = trade.side.upper()
    price_cents = trade.price_cents
    status = trade.status

    # Determine outcome string
    pnl_cents = trade.pnl_cents or 0
    outcome_str = f"WIN (+{pnl_cents}c)" if status == TradeStatus.WON else f"LOSS ({pnl_cents}c)"

    # Build forecast comparison (sorted by accuracy)
    forecast_lines: list[str] = []
    for fc in sorted(forecasts, key=lambda f: abs(f.forecast_high_f - actual_temp)):
        diff = fc.forecast_high_f - actual_temp
        forecast_lines.append(
            f"{fc.source}: {fc.forecast_high_f:.0f}F ({'+' if diff >= 0 else ''}{diff:.0f}F off)"
        )

    forecast_summary = "; ".join(forecast_lines[:4])  # top 4 models

    narrative = (
        f"{outcome_str}: Bought {side} on {trade.city.value} {bracket} at "
        f"{price_cents}c. Actual high was {actual_temp:.0f}F. "
        f"Our model predicted {trade.model_probability:.0%} probability "
        f"for this bracket."
    )

    if forecast_summary:
        narrative += f" Forecast accuracy: {forecast_summary}."

    return narrative


async def settle_trade(
    trade: Trade,
    settlement: Settlement,
    db: AsyncSession,
) -> None:
    """Settle a trade after the actual temperature is known.

    Determines win/loss, calculates P&L (including fees in cents),
    generates a post-mortem narrative, and updates the trade record.

    Args:
        trade: The Trade ORM record to settle (must be OPEN status).
        settlement: The Settlement ORM with actual temperature data.
        db: Async database session.
    """
    actual_temp = settlement.actual_high_f

    # Determine if the bracket was hit
    won = _did_bracket_win(trade.bracket_label, actual_temp, trade.side)

    # Calculate P&L in cents
    cost_cents = trade.price_cents * trade.quantity
    if trade.side == "no":
        cost_cents = (100 - trade.price_cents) * trade.quantity

    if won:
        payout_cents = 100 * trade.quantity
        profit_cents = payout_cents - cost_cents
        fee_cents = estimate_fees(trade.price_cents, trade.side) * trade.quantity
        pnl_cents = profit_cents - fee_cents
        trade.status = TradeStatus.WON
        trade.fees_cents = fee_cents
    else:
        pnl_cents = -cost_cents
        trade.status = TradeStatus.LOST
        trade.fees_cents = 0

    trade.pnl_cents = pnl_cents
    trade.settlement_temp_f = actual_temp
    trade.settlement_source = settlement.source
    trade.settled_at = datetime.now(UTC)

    # Fetch forecasts for the post-mortem narrative
    forecasts_result = await db.execute(
        select(WeatherForecast).where(
            WeatherForecast.city == trade.city,
            WeatherForecast.forecast_date == trade.trade_date,
        )
    )
    forecasts = list(forecasts_result.scalars().all())

    # Generate and store the narrative
    trade.postmortem_narrative = generate_postmortem_narrative(trade, settlement, forecasts)

    await db.flush()

    logger.info(
        "Trade settled",
        extra={
            "data": {
                "trade_id": trade.id,
                "status": trade.status.value,
                "pnl_cents": trade.pnl_cents,
                "fees_cents": trade.fees_cents,
                "actual_temp_f": actual_temp,
                "bracket": trade.bracket_label,
            }
        },
    )


def _did_bracket_win(
    bracket_label: str,
    actual_temp: float,
    side: str,
) -> bool:
    """Determine if a bracket/side combination won given the actual temperature.

    Supported bracket label formats:
        "53-54F"   -> standard bracket: lower <= temp <= upper
        "<=52F"    -> bottom catch-all: temp <= bound
        ">=57F"    -> top catch-all: temp >= bound

    Also supports degree symbol variants: "53-54\u00b0F", "<=52\u00b0F"

    Args:
        bracket_label: The bracket label string.
        actual_temp: The actual high temperature in Fahrenheit.
        side: The trade side ("yes" or "no").

    Returns:
        True if the trade won, False if it lost.
    """
    # Normalize: strip degree symbols and whitespace
    label = bracket_label.replace("\u00b0", "").replace(" ", "").strip()
    bracket_hit = False

    if label.startswith("<=") or label.lower().startswith("below"):
        # Bottom catch-all bracket
        match = re.search(r"[\d.]+", label)
        if match:
            upper = float(match.group())
            bracket_hit = actual_temp <= upper
    elif label.startswith(">=") or label.lower().endswith("above"):
        # Top catch-all bracket
        match = re.search(r"[\d.]+", label)
        if match:
            lower = float(match.group())
            bracket_hit = actual_temp >= lower
    else:
        # Standard bracket: "53-54F" or "53-54"
        # Remove trailing F if present
        clean = label.rstrip("Ff")
        parts = clean.split("-")
        if len(parts) == 2:
            try:
                lower = float(parts[0])
                upper = float(parts[1])
                bracket_hit = lower <= actual_temp <= upper
            except ValueError:
                logger.error(
                    "Failed to parse bracket label",
                    extra={"data": {"bracket_label": bracket_label}},
                )
                return False

    if side == "yes":
        return bracket_hit
    else:  # "no"
        return not bracket_hit
