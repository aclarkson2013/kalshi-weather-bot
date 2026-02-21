"""Tests for backend.trading.sync -- Kalshi portfolio sync service.

Verifies the reconciliation algorithm: fetching filled orders from Kalshi,
checking for existing Trade records, and creating new ones for orphaned orders.
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.kalshi.models import OrderResponse
from backend.trading.sync import (
    _parse_city_from_ticker,
    sync_portfolio,
)


def _make_order(
    order_id: str = "order-001",
    ticker: str = "KXHIGHNY-26FEB21-B47.5",
    side: str = "yes",
    yes_price: int = 22,
    fill_count: int = 1,
    status: str = "executed",
) -> OrderResponse:
    """Create a mock OrderResponse."""
    return OrderResponse(
        order_id=order_id,
        ticker=ticker,
        action="buy",
        side=side,
        type="limit",
        fill_count=fill_count,
        initial_count=fill_count,
        yes_price=yes_price,
        status=status,
        created_time=datetime(2026, 2, 21, 15, 0, 0, tzinfo=UTC),
        taker_fees=0,
        taker_fill_cost=0,
    )


def _make_mock_market(
    ticker: str = "KXHIGHNY-26FEB21-B47.5",
    floor_strike: float | None = 47.0,
    cap_strike: float | None = 49.99,
) -> MagicMock:
    """Create a mock KalshiMarket."""
    market = MagicMock()
    market.ticker = ticker
    market.floor_strike = floor_strike
    market.cap_strike = cap_strike
    return market


class TestParseCityFromTicker:
    """Tests for _parse_city_from_ticker."""

    def test_nyc(self) -> None:
        assert _parse_city_from_ticker("KXHIGHNY-26FEB22-T38") == "NYC"

    def test_chicago(self) -> None:
        assert _parse_city_from_ticker("KXHIGHCHI-26FEB21-T35") == "CHI"

    def test_miami(self) -> None:
        assert _parse_city_from_ticker("KXHIGHMIA-26FEB21-B81.5") == "MIA"

    def test_austin(self) -> None:
        assert _parse_city_from_ticker("KXHIGHAUS-26FEB22-T62") == "AUS"

    def test_unknown_ticker(self) -> None:
        assert _parse_city_from_ticker("KXELECTION-26FEB22-P50") is None

    def test_empty_ticker(self) -> None:
        assert _parse_city_from_ticker("") is None

    def test_no_dashes(self) -> None:
        assert _parse_city_from_ticker("KXHIGHNY") is None


class TestSyncPortfolio:
    """Tests for sync_portfolio."""

    @pytest.mark.asyncio
    async def test_happy_path_syncs_new_orders(self) -> None:
        """Orders not in DB get synced as new Trade records."""
        order1 = _make_order(order_id="ord-001", ticker="KXHIGHNY-26FEB21-B47.5")
        order2 = _make_order(order_id="ord-002", ticker="KXHIGHMIA-26FEB21-B81.5")

        client = AsyncMock()
        client.get_orders.return_value = [order1, order2]
        client.get_market.return_value = _make_mock_market()

        db = AsyncMock()
        # No existing trades found (scalar_one_or_none returns None)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        db.execute.return_value = mock_result

        result = await sync_portfolio(client, db, "user-1")

        assert result.synced_count == 2
        assert result.skipped_count == 0
        assert result.failed_count == 0
        assert db.add.call_count == 2
        assert db.commit.called

    @pytest.mark.asyncio
    async def test_skips_already_tracked_orders(self) -> None:
        """Orders already in DB by kalshi_order_id are skipped."""
        order = _make_order(order_id="ord-existing")

        client = AsyncMock()
        client.get_orders.return_value = [order]

        db = AsyncMock()
        # Order already exists in DB
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = "existing-trade-id"
        db.execute.return_value = mock_result

        result = await sync_portfolio(client, db, "user-1")

        assert result.synced_count == 0
        assert result.skipped_count == 1
        assert db.add.call_count == 0

    @pytest.mark.asyncio
    async def test_empty_order_list(self) -> None:
        """No orders from Kalshi returns empty result."""
        client = AsyncMock()
        client.get_orders.return_value = []

        db = AsyncMock()

        result = await sync_portfolio(client, db, "user-1")

        assert result.synced_count == 0
        assert result.skipped_count == 0
        assert result.failed_count == 0

    @pytest.mark.asyncio
    async def test_skips_non_weather_tickers(self) -> None:
        """Non-weather market tickers are skipped."""
        order = _make_order(
            order_id="ord-election",
            ticker="KXELECTION-26FEB21-P50",
        )

        client = AsyncMock()
        client.get_orders.return_value = [order]

        db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        db.execute.return_value = mock_result

        result = await sync_portfolio(client, db, "user-1")

        assert result.synced_count == 0
        assert result.skipped_count == 1

    @pytest.mark.asyncio
    async def test_skips_zero_fill_count(self) -> None:
        """Orders with fill_count=0 are skipped."""
        order = _make_order(order_id="ord-nofill", fill_count=0)

        client = AsyncMock()
        client.get_orders.return_value = [order]

        db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        db.execute.return_value = mock_result

        result = await sync_portfolio(client, db, "user-1")

        assert result.synced_count == 0
        assert result.skipped_count == 1

    @pytest.mark.asyncio
    async def test_auth_failure_returns_error_result(self) -> None:
        """Kalshi auth failure returns SyncResult with error."""
        client = AsyncMock()
        client.get_orders.side_effect = Exception("Auth failed: invalid key")

        db = AsyncMock()

        result = await sync_portfolio(client, db, "user-1")

        assert result.synced_count == 0
        assert result.failed_count == 1
        assert len(result.errors) == 1
        assert "Auth failed" in result.errors[0]

    @pytest.mark.asyncio
    async def test_market_fetch_failure_uses_fallback_label(self) -> None:
        """When market details fetch fails, uses ticker suffix as label."""
        order = _make_order(order_id="ord-new", ticker="KXHIGHNY-26FEB21-B47.5")

        client = AsyncMock()
        client.get_orders.return_value = [order]
        client.get_market.side_effect = Exception("Rate limited")

        db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        db.execute.return_value = mock_result

        result = await sync_portfolio(client, db, "user-1")

        assert result.synced_count == 1
        # Trade was created with fallback label
        trade_arg = db.add.call_args[0][0]
        assert trade_arg.bracket_label == "B47.5"

    @pytest.mark.asyncio
    async def test_synced_trade_sentinel_values(self) -> None:
        """Synced trades have model_probability=0.0, ev=0.0, confidence=low."""
        order = _make_order(order_id="ord-sync", yes_price=35, fill_count=2)

        client = AsyncMock()
        client.get_orders.return_value = [order]
        client.get_market.return_value = _make_mock_market()

        db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        db.execute.return_value = mock_result

        result = await sync_portfolio(client, db, "user-1")

        assert result.synced_count == 1
        trade = db.add.call_args[0][0]
        assert trade.model_probability == 0.0
        assert trade.ev_at_entry == 0.0
        assert trade.confidence == "low"
        assert trade.market_probability == 0.35
        assert trade.quantity == 2
        assert trade.price_cents == 35

    @pytest.mark.asyncio
    async def test_mixed_orders_counted_correctly(self) -> None:
        """Mix of new, existing, and non-weather orders counted correctly."""
        order_new = _make_order(order_id="ord-new", ticker="KXHIGHNY-26FEB21-B47.5")
        order_existing = _make_order(order_id="ord-existing", ticker="KXHIGHMIA-26FEB21-B81.5")
        order_non_weather = _make_order(order_id="ord-election", ticker="KXELECTION-26FEB21-P50")

        client = AsyncMock()
        client.get_orders.return_value = [order_new, order_existing, order_non_weather]
        client.get_market.return_value = _make_mock_market()

        db = AsyncMock()

        # First call: order_new not tracked (returns None)
        # Second call: order_existing already tracked (returns "id")
        mock_result_none = MagicMock()
        mock_result_none.scalar_one_or_none.return_value = None
        mock_result_existing = MagicMock()
        mock_result_existing.scalar_one_or_none.return_value = "existing-id"
        db.execute.side_effect = [mock_result_none, mock_result_existing]

        result = await sync_portfolio(client, db, "user-1")

        assert result.synced_count == 1
        assert result.skipped_count == 2  # existing + non-weather

    @pytest.mark.asyncio
    async def test_market_details_cached_per_ticker(self) -> None:
        """Market details are fetched once per unique ticker, not per order."""
        order1 = _make_order(order_id="ord-1", ticker="KXHIGHNY-26FEB21-B47.5")
        order2 = _make_order(order_id="ord-2", ticker="KXHIGHNY-26FEB21-B47.5")

        client = AsyncMock()
        client.get_orders.return_value = [order1, order2]
        client.get_market.return_value = _make_mock_market()

        db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        db.execute.return_value = mock_result

        await sync_portfolio(client, db, "user-1")

        # get_market should only be called once for the shared ticker
        assert client.get_market.call_count == 1

    @pytest.mark.asyncio
    async def test_synced_trade_has_correct_order_id(self) -> None:
        """Synced trade records store the Kalshi order ID."""
        order = _make_order(order_id="kalshi-order-xyz")

        client = AsyncMock()
        client.get_orders.return_value = [order]
        client.get_market.return_value = _make_mock_market()

        db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        db.execute.return_value = mock_result

        await sync_portfolio(client, db, "user-1")

        trade = db.add.call_args[0][0]
        assert trade.kalshi_order_id == "kalshi-order-xyz"

    @pytest.mark.asyncio
    async def test_synced_trade_has_correct_city(self) -> None:
        """Synced trade has the correct city parsed from ticker."""
        order = _make_order(order_id="ord-aus", ticker="KXHIGHAUS-26FEB21-T73")

        client = AsyncMock()
        client.get_orders.return_value = [order]
        client.get_market.return_value = _make_mock_market(
            ticker="KXHIGHAUS-26FEB21-T73",
            floor_strike=None,
            cap_strike=72.99,
        )

        db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        db.execute.return_value = mock_result

        await sync_portfolio(client, db, "user-1")

        trade = db.add.call_args[0][0]
        assert trade.city == "AUS"

    @pytest.mark.asyncio
    async def test_per_order_failure_continues_processing(self) -> None:
        """An error on one order doesn't stop processing other orders."""
        order_good = _make_order(order_id="ord-good", ticker="KXHIGHNY-26FEB21-B47.5")
        order_bad = _make_order(order_id="ord-bad", ticker="KXHIGHMIA-26FEB21-B81.5")

        client = AsyncMock()
        client.get_orders.return_value = [order_bad, order_good]
        client.get_market.return_value = _make_mock_market()

        db = AsyncMock()
        # First order: DB check raises error
        # Second order: not tracked
        mock_result_error = MagicMock()
        mock_result_error.scalar_one_or_none.side_effect = Exception("DB error")
        mock_result_ok = MagicMock()
        mock_result_ok.scalar_one_or_none.return_value = None
        db.execute.side_effect = [mock_result_error, mock_result_ok]

        result = await sync_portfolio(client, db, "user-1")

        assert result.synced_count == 1
        assert result.failed_count == 1
        assert len(result.errors) == 1
