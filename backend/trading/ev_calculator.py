"""Expected value calculation and bracket scanning for trade signal generation.

This is the mathematical core of the trading engine. For each bracket in each
city, it calculates expected value for both YES and NO sides, accounting for
Kalshi fees. Only trades with positive EV above the user's threshold are
generated as TradeSignal objects.

CRITICAL: All prices are in CENTS (integers). EV output is in DOLLARS (float).
Fee calculation returns CENTS (int).

Fee structure:
    - Kalshi charges 15% of profit on winning trades
    - Minimum fee = 1 cent per contract
    - For conservative EV, we subtract fees unconditionally (overestimates cost)

Usage:
    from backend.trading.ev_calculator import scan_all_brackets

    signals = scan_all_brackets(
        prediction=bracket_prediction,
        market_prices={"52-54F": 22, "54-56F": 35},
        market_tickers={"52-54F": "KXHIGHNY-26FEB18-T52", ...},
        min_ev_threshold=0.05,
    )
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from backend.common.logging import get_logger
from backend.common.schemas import BracketPrediction, TradeSignal

logger = get_logger("TRADING")
ET = ZoneInfo("America/New_York")


def estimate_fees(price_cents: int, side: str) -> int:
    """Estimate Kalshi fees for a trade in CENTS.

    Kalshi charges 15% of profit, with a minimum of 1 cent per contract.

    For YES side: profit_if_win = 100 - price_cents (payout minus cost)
    For NO side: profit_if_win = price_cents (the YES price is the NO profit)

    Args:
        price_cents: Market YES price in cents (1-99).
        side: "yes" or "no".

    Returns:
        Estimated fee in CENTS (int).

    Raises:
        ValueError: If price_cents is outside [1, 99] or side is invalid.
    """
    if not (1 <= price_cents <= 99):
        msg = f"price_cents must be 1-99, got {price_cents}"
        raise ValueError(msg)
    if side not in ("yes", "no"):
        msg = f"side must be 'yes' or 'no', got {side!r}"
        raise ValueError(msg)

    profit_if_win = 100 - price_cents if side == "yes" else price_cents

    fee_cents = max(1, int(profit_if_win * 0.15))
    return fee_cents


def calculate_ev(
    model_prob: float,
    market_price_cents: int,
    side: str,
) -> float:
    """Calculate expected value for a potential trade.

    Uses the conservative approach: fees are subtracted unconditionally
    (not only on wins). This slightly underestimates true EV, which is
    safer -- we'd rather miss a marginal trade than take a bad one.

    Args:
        model_prob: Our model's probability for the bracket (0.0 to 1.0).
        market_price_cents: Kalshi market YES price in CENTS (1-99).
        side: "yes" or "no".

    Returns:
        Expected value in DOLLARS (positive = profitable).

    Raises:
        ValueError: If model_prob is outside [0.0, 1.0] or inputs invalid.
    """
    if not (0.0 <= model_prob <= 1.0):
        msg = f"model_prob must be 0.0-1.0, got {model_prob}"
        raise ValueError(msg)

    if side == "yes":
        prob_win = model_prob
        cost_dollars = market_price_cents / 100
    elif side == "no":
        prob_win = 1.0 - model_prob
        cost_dollars = (100 - market_price_cents) / 100
    else:
        msg = f"side must be 'yes' or 'no', got {side!r}"
        raise ValueError(msg)

    fee_cents = estimate_fees(market_price_cents, side)
    fee_dollars = fee_cents / 100

    ev = (prob_win * 1.00) - cost_dollars - fee_dollars
    return round(ev, 4)


def scan_bracket(
    bracket_label: str,
    bracket_probability: float,
    market_price_cents: int,
    min_ev_threshold: float,
    city: str,
    prediction_date: str,
    confidence: str,
    market_ticker: str,
) -> TradeSignal | None:
    """Scan a single bracket for trading opportunities on both YES and NO sides.

    Calculates EV for both sides and returns a TradeSignal for the better
    side if it meets the minimum threshold.

    Args:
        bracket_label: Bracket label string (e.g., "53-54F").
        bracket_probability: Model probability for this bracket (0.0-1.0).
        market_price_cents: Current Kalshi YES price in cents.
        min_ev_threshold: Minimum EV in dollars to trigger a trade.
        city: City code (e.g., "NYC").
        prediction_date: Date string for the event.
        confidence: Model confidence level ("high", "medium", "low").
        market_ticker: Kalshi market ticker string.

    Returns:
        TradeSignal if a +EV opportunity exists, None otherwise.
    """
    # Calculate EV for both sides
    ev_yes = calculate_ev(bracket_probability, market_price_cents, "yes")
    ev_no = calculate_ev(bracket_probability, market_price_cents, "no")

    logger.debug(
        "Bracket scan",
        extra={
            "data": {
                "city": city,
                "bracket": bracket_label,
                "model_prob": round(bracket_probability, 4),
                "market_cents": market_price_cents,
                "ev_yes": ev_yes,
                "ev_no": ev_no,
            }
        },
    )

    # Pick the better side if it meets the threshold
    best_side: str | None = None
    best_ev = 0.0

    if ev_yes >= ev_no and ev_yes >= min_ev_threshold:
        best_side = "yes"
        best_ev = ev_yes
    elif ev_no > ev_yes and ev_no >= min_ev_threshold:
        best_side = "no"
        best_ev = ev_no

    if best_side is None:
        return None  # No trade opportunity

    # Calculate market probability from the perspective of the chosen side
    if best_side == "yes":
        market_prob = market_price_cents / 100
    else:
        market_prob = (100 - market_price_cents) / 100

    return TradeSignal(
        city=city,
        bracket=bracket_label,
        side=best_side,
        price_cents=market_price_cents,
        quantity=1,
        model_probability=bracket_probability,
        market_probability=round(market_prob, 4),
        ev=best_ev,
        confidence=confidence,
        market_ticker=market_ticker,
        reasoning=_generate_signal_reasoning(
            bracket_label, bracket_probability, market_price_cents, best_side, best_ev
        ),
    )


def scan_all_brackets(
    prediction: BracketPrediction,
    market_prices: dict[str, int],
    market_tickers: dict[str, str],
    min_ev_threshold: float,
) -> list[TradeSignal]:
    """Scan all brackets for a city and return all +EV trade signals.

    Args:
        prediction: Full bracket prediction for one city.
        market_prices: Mapping of bracket label to current YES price in cents.
        market_tickers: Mapping of bracket label to Kalshi market ticker string.
        min_ev_threshold: Minimum EV in dollars to trigger a trade.

    Returns:
        List of TradeSignal objects, sorted by EV descending (best first).
    """
    signals: list[TradeSignal] = []

    for bracket in prediction.brackets:
        price = market_prices.get(bracket.bracket_label)
        if price is None:
            logger.warning(
                "No market price for bracket",
                extra={
                    "data": {
                        "city": prediction.city,
                        "bracket": bracket.bracket_label,
                    }
                },
            )
            continue

        ticker = market_tickers.get(bracket.bracket_label)
        if ticker is None:
            logger.warning(
                "No market ticker for bracket",
                extra={
                    "data": {
                        "city": prediction.city,
                        "bracket": bracket.bracket_label,
                    }
                },
            )
            continue

        signal = scan_bracket(
            bracket_label=bracket.bracket_label,
            bracket_probability=bracket.probability,
            market_price_cents=price,
            min_ev_threshold=min_ev_threshold,
            city=prediction.city,
            prediction_date=str(prediction.date),
            confidence=prediction.confidence,
            market_ticker=ticker,
        )
        if signal is not None:
            signals.append(signal)

    # Sort by EV descending -- best opportunity first
    signals.sort(key=lambda s: s.ev, reverse=True)

    logger.info(
        "Bracket scan complete",
        extra={
            "data": {
                "city": prediction.city,
                "total_brackets": len(prediction.brackets),
                "signals_found": len(signals),
            }
        },
    )
    return signals


def validate_predictions(predictions: list[BracketPrediction]) -> bool:
    """Validate prediction data before trading on it.

    Returns True if ALL predictions are valid. Logs specific errors.
    If any prediction is invalid, returns False -- halt trading for this cycle.

    Checks:
        - Probabilities sum to ~1.0 (within 0.95-1.05 tolerance)
        - No NaN or negative probabilities
        - Exactly 6 brackets per prediction
        - Data freshness (predictions must be less than 2 hours old)

    Args:
        predictions: List of BracketPrediction objects to validate.

    Returns:
        True if all predictions pass validation, False otherwise.
    """
    for pred in predictions:
        # Probabilities must sum to ~1.0 (allow small floating point error)
        total = sum(b.probability for b in pred.brackets)
        if not (0.95 <= total <= 1.05):
            logger.error(
                "Bracket probabilities do not sum to 1.0",
                extra={"data": {"city": pred.city, "total": round(total, 4)}},
            )
            return False

        # No NaN or negative probabilities
        for b in pred.brackets:
            if math.isnan(b.probability) or b.probability < 0:
                logger.error(
                    "Invalid probability value",
                    extra={
                        "data": {
                            "city": pred.city,
                            "bracket": b.bracket_label,
                            "probability": b.probability,
                        }
                    },
                )
                return False

        # Must have exactly 6 brackets
        if len(pred.brackets) != 6:
            logger.error(
                "Expected 6 brackets",
                extra={"data": {"city": pred.city, "count": len(pred.brackets)}},
            )
            return False

        # Data freshness check -- predictions older than 2 hours are stale
        now = datetime.now(ET)
        generated = pred.generated_at
        # Handle timezone-naive datetimes by treating them as UTC
        if generated.tzinfo is None:
            from datetime import UTC

            generated = generated.replace(tzinfo=UTC)
        age = now - generated.astimezone(ET)
        if age > timedelta(hours=2):
            logger.warning(
                "Stale predictions detected",
                extra={
                    "data": {
                        "city": pred.city,
                        "age_hours": round(age.total_seconds() / 3600, 2),
                    }
                },
            )
            return False

    return True


def validate_market_prices(prices: dict[str, int]) -> bool:
    """Validate market prices from Kalshi before using them.

    Ensures all prices are integers in the valid range [1, 99].

    Args:
        prices: Mapping of bracket label to YES price in cents.

    Returns:
        True if all prices are valid, False otherwise.
    """
    for label, price in prices.items():
        if not isinstance(price, int):
            logger.error(
                "Market price is not an integer",
                extra={"data": {"bracket": label, "price": price}},
            )
            return False
        if not (1 <= price <= 99):
            logger.error(
                "Market price out of range",
                extra={"data": {"bracket": label, "price_cents": price}},
            )
            return False
    return True


def _generate_signal_reasoning(
    bracket_label: str,
    bracket_prob: float,
    market_price_cents: int,
    side: str,
    ev: float,
) -> str:
    """Generate human-readable reasoning for a trade signal.

    Args:
        bracket_label: The bracket label (e.g., "53-54F").
        bracket_prob: Model probability for the bracket.
        market_price_cents: Current YES price in cents.
        side: The trade side ("yes" or "no").
        ev: The calculated EV in dollars.

    Returns:
        A reasoning string suitable for display.
    """
    model_pct = bracket_prob * 100
    market_pct = market_price_cents if side == "yes" else 100 - market_price_cents
    edge = model_pct - market_pct

    return (
        f"Model: {model_pct:.1f}% vs Market: {market_pct}% "
        f"({'+' if edge > 0 else ''}{edge:.1f}% edge). "
        f"EV: ${ev:+.4f} per contract on {side.upper()} side."
    )
