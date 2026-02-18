"""Order construction and validation for Kalshi weather markets.

Provides helper functions to build validated OrderRequest objects and
check them against market conditions before submission. All validation
happens locally to catch errors before hitting the Kalshi API.

CRITICAL: All prices are in CENTS (integers 1-99), NOT dollars.

Usage:
    from backend.kalshi.orders import build_order, validate_order_for_market

    order = build_order(
        ticker="KXHIGHNY-26FEB18-T52",
        side="yes",
        price_cents=22,
        count=1,
    )
    validate_order_for_market(order, market)  # raises if invalid
"""

from __future__ import annotations

from backend.common.logging import get_logger
from backend.kalshi.exceptions import KalshiOrderRejectedError
from backend.kalshi.models import KalshiMarket, OrderRequest

logger = get_logger("ORDER")


def build_order(
    ticker: str,
    side: str,
    price_cents: int,
    count: int = 1,
    action: str = "buy",
    order_type: str = "limit",
) -> OrderRequest:
    """Build a validated OrderRequest for the Kalshi API.

    Constructs an OrderRequest with all Pydantic validators applied
    at creation time. If any parameter is invalid, a ValueError is
    raised immediately.

    Args:
        ticker: Market ticker (e.g., "KXHIGHNY-26FEB18-T52").
        side: "yes" or "no".
        price_cents: Price in cents (1-99). NOT dollars.
        count: Number of contracts (>= 1).
        action: "buy" or "sell" (default: "buy").
        order_type: "limit" or "market" (default: "limit").

    Returns:
        A validated OrderRequest ready for submission.

    Raises:
        ValueError: If any parameter fails validation.
    """
    order = OrderRequest(
        ticker=ticker,
        action=action,
        side=side,
        type=order_type,
        count=count,
        yes_price=price_cents,
    )

    logger.info(
        "Order built",
        extra={
            "data": {
                "ticker": ticker,
                "action": action,
                "side": side,
                "price_cents": price_cents,
                "count": count,
                "type": order_type,
            }
        },
    )

    return order


def validate_order_for_market(
    order: OrderRequest,
    market: KalshiMarket,
) -> None:
    """Validate an order against current market conditions.

    Checks that the market is active and the order price is reasonable.
    Call this before submitting an order to catch issues that would be
    rejected by the API.

    Args:
        order: The OrderRequest to validate.
        market: The KalshiMarket the order is being placed on.

    Raises:
        KalshiOrderRejectedError: If the market is not active or the
            order price is out of valid range.
    """
    # Check market is active
    if market.status != "active":
        raise KalshiOrderRejectedError(
            f"Market {market.ticker} is not active (status: {market.status})",
            context={
                "ticker": market.ticker,
                "market_status": market.status,
                "order_action": order.action,
            },
        )

    # Check order ticker matches market ticker
    if order.ticker != market.ticker:
        raise KalshiOrderRejectedError(
            f"Order ticker '{order.ticker}' does not match market ticker '{market.ticker}'",
            context={
                "order_ticker": order.ticker,
                "market_ticker": market.ticker,
            },
        )

    # Check price is in valid cent range (already validated by Pydantic,
    # but belt-and-suspenders for the API boundary)
    if not (1 <= order.yes_price <= 99):
        raise KalshiOrderRejectedError(
            f"Price {order.yes_price} cents is outside valid range [1, 99]",
            context={
                "ticker": order.ticker,
                "yes_price": order.yes_price,
            },
        )

    logger.info(
        "Order validated against market",
        extra={
            "data": {
                "ticker": order.ticker,
                "side": order.side,
                "price_cents": order.yes_price,
                "market_status": market.status,
                "yes_bid": market.yes_bid,
                "yes_ask": market.yes_ask,
            }
        },
    )
