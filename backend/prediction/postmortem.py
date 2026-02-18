"""Generate trade post-mortem narratives after settlement.

After the NWS CLI report comes in with the actual high temperature, this
module generates a human-readable narrative explaining why a trade won or
lost. The narrative is stored on the Trade record and displayed in the
frontend dashboard.

Usage:
    from backend.prediction.postmortem import generate_postmortem_narrative

    narrative = generate_postmortem_narrative(trade, settlement_temp_f=56.0)
"""

from __future__ import annotations

from backend.common.logging import get_logger
from backend.common.models import Trade, TradeStatus

logger = get_logger("POSTMORTEM")


def generate_postmortem_narrative(
    trade: Trade,
    settlement_temp_f: float,
) -> str:
    """Generate human-readable post-mortem narrative for a settled trade.

    This narrative is stored alongside the trade record and displayed in the
    dashboard for the user to understand why a trade won or lost. Works
    directly with the Trade ORM model fields.

    Args:
        trade: The Trade ORM model with all trade details.
            Uses: price_cents, pnl_cents, status, model_probability,
            market_probability, bracket_label, city, side, confidence.
        settlement_temp_f: Actual temperature from NWS CLI report (Fahrenheit).

    Returns:
        Multi-line narrative string explaining why the trade won/lost.
    """
    won = trade.status == TradeStatus.WON

    # Determine outcome string with P&L.
    if won and trade.pnl_cents is not None:
        pnl_dollars = trade.pnl_cents / 100
        outcome_str = f"WIN (+${pnl_dollars:.2f})"
    elif trade.pnl_cents is not None:
        pnl_dollars = abs(trade.pnl_cents) / 100
        outcome_str = f"LOSS (-${pnl_dollars:.2f})"
    else:
        outcome_str = "WIN" if won else "LOSS"

    # Build the narrative.
    lines: list[str] = []

    lines.append("WHAT WE TRADED")
    lines.append(
        f"  Bought {trade.side.upper()} on {trade.bracket_label} bracket "
        f"@ {trade.price_cents}c (1 contract)"
    )
    lines.append("")

    lines.append("WHAT HAPPENED")
    lines.append(f"  Actual high: {settlement_temp_f:.0f}F (NWS CLI Report)")
    lines.append(f"  Result: {outcome_str}")
    lines.append("")

    lines.append("WHY WE TOOK THIS TRADE")
    lines.append(f"  - Our model predicted {trade.model_probability:.0%} chance for this bracket")
    lines.append(
        f"  - Market was pricing it at {trade.market_probability:.0%} ({trade.price_cents}c)"
    )

    edge = trade.model_probability - trade.market_probability
    edge_sign = "+" if edge > 0 else ""
    lines.append(f"  - Edge: {edge_sign}{edge:.1%}")
    lines.append(f"  - Confidence: {trade.confidence}")
    lines.append("")

    lines.append("OUTCOME ANALYSIS")
    lines.append(f"  - Settlement temperature: {settlement_temp_f:.0f}F")
    lines.append(f"  - Target bracket: {trade.bracket_label}")
    if won:
        lines.append("  - The actual temperature landed in our target bracket.")
    else:
        lines.append("  - The actual temperature fell outside our target bracket.")

    narrative = "\n".join(lines)

    logger.info(
        "Post-mortem generated",
        extra={
            "data": {
                "trade_id": trade.id,
                "city": str(trade.city),
                "result": "WIN" if won else "LOSS",
                "settlement_temp_f": settlement_temp_f,
                "bracket": trade.bracket_label,
            }
        },
    )

    return narrative
