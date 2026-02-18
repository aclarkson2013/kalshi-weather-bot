"""Tests for order construction and validation for Kalshi weather markets.

Verifies build_order creates valid OrderRequest objects with correct
defaults, and validate_order_for_market catches invalid orders before
they hit the Kalshi API.
"""

from __future__ import annotations

import pytest

from backend.kalshi.exceptions import KalshiOrderRejectedError
from backend.kalshi.models import KalshiMarket, OrderRequest
from backend.kalshi.orders import build_order, validate_order_for_market


class TestBuildOrder:
    """Tests for the build_order helper function."""

    def test_creates_valid_order_request(self) -> None:
        """build_order creates a valid OrderRequest with given parameters."""
        order = build_order(
            ticker="KXHIGHNY-26FEB18-T52",
            side="yes",
            price_cents=22,
            count=3,
        )
        assert isinstance(order, OrderRequest)
        assert order.ticker == "KXHIGHNY-26FEB18-T52"
        assert order.side == "yes"
        assert order.yes_price == 22
        assert order.count == 3

    def test_default_action_is_buy(self) -> None:
        """build_order defaults action to 'buy'."""
        order = build_order(
            ticker="KXHIGHNY-26FEB18-T52",
            side="yes",
            price_cents=22,
        )
        assert order.action == "buy"

    def test_default_type_is_limit(self) -> None:
        """build_order defaults order_type to 'limit'."""
        order = build_order(
            ticker="KXHIGHNY-26FEB18-T52",
            side="yes",
            price_cents=22,
        )
        assert order.type == "limit"

    def test_raises_value_error_for_invalid_price(self) -> None:
        """build_order raises ValueError for price outside 1-99 range."""
        with pytest.raises(Exception):
            build_order(
                ticker="KXHIGHNY-26FEB18-T52",
                side="yes",
                price_cents=0,
            )
        with pytest.raises(Exception):
            build_order(
                ticker="KXHIGHNY-26FEB18-T52",
                side="yes",
                price_cents=100,
            )


class TestValidateOrderForMarket:
    """Tests for validate_order_for_market function."""

    def _make_market(
        self,
        status: str = "active",
        ticker: str = "KXHIGHNY-26FEB18-T52",
    ) -> KalshiMarket:
        """Helper to create a KalshiMarket for validation tests."""
        return KalshiMarket(
            ticker=ticker,
            event_ticker="KXHIGHNY-26FEB18",
            title="NYC high temp: 52F to 53F?",
            status=status,
            yes_bid=22,
            yes_ask=25,
        )

    def _make_order(
        self,
        ticker: str = "KXHIGHNY-26FEB18-T52",
        yes_price: int = 22,
    ) -> OrderRequest:
        """Helper to create an OrderRequest for validation tests."""
        return OrderRequest(
            ticker=ticker,
            action="buy",
            side="yes",
            type="limit",
            count=1,
            yes_price=yes_price,
        )

    def test_passes_for_active_market_with_matching_ticker(self) -> None:
        """Validation passes for an active market with matching ticker."""
        market = self._make_market(status="active")
        order = self._make_order(ticker="KXHIGHNY-26FEB18-T52")

        # Should not raise
        validate_order_for_market(order, market)

    def test_raises_for_inactive_market(self) -> None:
        """Validation raises KalshiOrderRejectedError for inactive market."""
        market = self._make_market(status="closed")
        order = self._make_order()

        with pytest.raises(KalshiOrderRejectedError, match="not active"):
            validate_order_for_market(order, market)

    def test_raises_for_ticker_mismatch(self) -> None:
        """Validation raises KalshiOrderRejectedError for mismatched tickers."""
        market = self._make_market(ticker="KXHIGHNY-26FEB18-T52")
        order = self._make_order(ticker="KXHIGHNY-26FEB18-T54")

        with pytest.raises(KalshiOrderRejectedError, match="does not match"):
            validate_order_for_market(order, market)

    def test_raises_for_invalid_price_range(self) -> None:
        """Validation raises KalshiOrderRejectedError for price outside [1, 99].

        Note: Pydantic validators already enforce this at construction time,
        so this test verifies the belt-and-suspenders check in validate_order_for_market.
        We construct a valid order and then manually override the price to bypass
        Pydantic's validator.
        """
        market = self._make_market()
        order = self._make_order(yes_price=50)

        # Manually override yes_price to bypass Pydantic validator
        # This simulates a corrupted order object reaching the validation
        object.__setattr__(order, "yes_price", 0)

        with pytest.raises(KalshiOrderRejectedError, match="outside valid range"):
            validate_order_for_market(order, market)
