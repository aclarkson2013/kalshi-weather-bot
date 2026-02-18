"""Pydantic models for Kalshi API requests and responses.

All prices are in CENTS (integers 1-99), NOT dollars. This matches the
Kalshi API convention and prevents float rounding errors in trading.

Usage:
    from backend.kalshi.models import (
        KalshiMarket, OrderRequest, dollars_to_cents, cents_to_dollars,
    )

    order = OrderRequest(
        ticker="KXHIGHNY-26FEB18-T52",
        action="buy",
        side="yes",
        type="limit",
        count=1,
        yes_price=22,  # $0.22 in cents
    )
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, field_validator

# ─── Helper Functions ───


def dollars_to_cents(price: float) -> int:
    """Convert a dollar price to Kalshi API cents.

    Rounds to the nearest cent to handle floating point imprecision.

    Args:
        price: Price in dollars (e.g., 0.22).

    Returns:
        Price in cents as an integer (e.g., 22).
    """
    return int(round(price * 100))


def cents_to_dollars(cents: int) -> float:
    """Convert Kalshi API cents to a dollar price.

    Args:
        cents: Price in cents (e.g., 22).

    Returns:
        Price in dollars as a float (e.g., 0.22).
    """
    return cents / 100.0


# ─── Event & Market Models ───


class KalshiEvent(BaseModel):
    """A Kalshi event containing multiple bracket markets.

    Example: "Highest temperature in NYC on Feb 18?" with 6 bracket markets.
    """

    event_ticker: str
    series_ticker: str
    title: str
    category: str
    status: str
    markets: list[str] = Field(default_factory=list)


class KalshiMarket(BaseModel):
    """A single Kalshi market (bracket) with current pricing.

    Prices are in cents (integers). Edge brackets have one null strike:
    - Bottom edge: floor_strike=None, cap_strike=47.99
    - Top edge: floor_strike=58.0, cap_strike=None
    - Middle: floor_strike=52.0, cap_strike=53.99
    """

    ticker: str
    event_ticker: str
    title: str
    subtitle: str | None = None
    status: str
    yes_bid: int = 0
    yes_ask: int = 0
    no_bid: int = 0
    no_ask: int = 0
    last_price: int = 0
    volume: int = 0
    open_interest: int = 0
    floor_strike: float | None = None
    cap_strike: float | None = None
    result: str | None = None
    close_time: datetime | None = None
    expiration_time: datetime | None = None


class KalshiOrderbook(BaseModel):
    """Current orderbook for a Kalshi market.

    Each entry in yes/no lists is [price_cents, quantity].

    Example:
        yes: [[22, 10], [21, 5]]  # 10 contracts at 22c, 5 at 21c
        no: [[78, 8], [79, 3]]
    """

    yes: list[list[int]] = Field(default_factory=list)
    no: list[list[int]] = Field(default_factory=list)


# ─── Order Models ───


class OrderRequest(BaseModel):
    """A validated order request ready to send to the Kalshi API.

    All validation happens at construction time via field_validators.
    Call validate_for_submission() as an explicit pre-flight check
    before sending to the API.

    Attributes:
        ticker: Market ticker (e.g., "KXHIGHNY-26FEB18-T52").
        action: "buy" or "sell".
        side: "yes" or "no".
        type: "limit" or "market".
        count: Number of contracts (>= 1).
        yes_price: Price in cents (1-99).
    """

    ticker: str
    action: str
    side: str
    type: str
    count: int = Field(ge=1)
    yes_price: int = Field(ge=1, le=99)

    @field_validator("action")
    @classmethod
    def validate_action(cls, v: str) -> str:
        """Ensure action is 'buy' or 'sell'."""
        if v not in ("buy", "sell"):
            msg = f"action must be 'buy' or 'sell', got '{v}'"
            raise ValueError(msg)
        return v

    @field_validator("side")
    @classmethod
    def validate_side(cls, v: str) -> str:
        """Ensure side is 'yes' or 'no'."""
        if v not in ("yes", "no"):
            msg = f"side must be 'yes' or 'no', got '{v}'"
            raise ValueError(msg)
        return v

    @field_validator("type")
    @classmethod
    def validate_type(cls, v: str) -> str:
        """Ensure order type is 'limit' or 'market'."""
        if v not in ("limit", "market"):
            msg = f"type must be 'limit' or 'market', got '{v}'"
            raise ValueError(msg)
        return v

    @field_validator("count")
    @classmethod
    def validate_count(cls, v: int) -> int:
        """Ensure count is at least 1."""
        if v < 1:
            msg = f"count must be >= 1, got {v}"
            raise ValueError(msg)
        return v

    @field_validator("yes_price")
    @classmethod
    def validate_price(cls, v: int) -> int:
        """Ensure yes_price is in valid cent range [1, 99]."""
        if not (1 <= v <= 99):
            msg = f"yes_price must be 1-99 cents, got {v}"
            raise ValueError(msg)
        return v

    def validate_for_submission(self) -> None:
        """Run all validators as an explicit pre-flight check.

        Pydantic validators already ran at construction time, but this
        provides a clear call site for the client to use before sending
        the order to the API. Also checks that the ticker is non-empty.

        Raises:
            ValueError: If the ticker is empty.
        """
        if not self.ticker or not self.ticker.strip():
            msg = "ticker must be a non-empty string"
            raise ValueError(msg)

    def to_api_dict(self) -> dict:
        """Convert to the dict format expected by the Kalshi POST /portfolio/orders API.

        Returns:
            Dict with keys: ticker, action, side, type, count, yes_price.
        """
        return {
            "ticker": self.ticker,
            "action": self.action,
            "side": self.side,
            "type": self.type,
            "count": self.count,
            "yes_price": self.yes_price,
        }


class OrderResponse(BaseModel):
    """Response from a successful order placement on Kalshi.

    Attributes:
        order_id: Unique identifier assigned by Kalshi.
        ticker: Market ticker the order was placed on.
        action: "buy" or "sell".
        side: "yes" or "no".
        type: "limit" or "market".
        count: Number of contracts.
        yes_price: Price in cents.
        status: Order status (e.g., "resting", "executed", "canceled").
        created_time: When the order was created.
    """

    order_id: str
    ticker: str
    action: str
    side: str
    type: str
    count: int
    yes_price: int
    status: str
    created_time: datetime


# ─── Position & Settlement Models ───


class KalshiPosition(BaseModel):
    """A current open position on Kalshi.

    All monetary values are in cents.

    Attributes:
        ticker: Market ticker.
        market_exposure: Current exposure in cents.
        resting_orders_count: Number of unfilled resting orders.
        total_traded: Total number of contracts traded.
        realized_pnl: Realized profit/loss in cents.
    """

    ticker: str
    market_exposure: int = 0
    resting_orders_count: int = 0
    total_traded: int = 0
    realized_pnl: int = 0


class KalshiSettlement(BaseModel):
    """A settled market position with outcome.

    Attributes:
        ticker: Market ticker.
        market_result: Settlement result (e.g., "yes", "no").
        revenue: Revenue in cents.
        settled_time: When the market was settled.
    """

    ticker: str
    market_result: str
    revenue: int
    settled_time: datetime
