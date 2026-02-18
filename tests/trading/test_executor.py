"""Tests for backend.trading.executor -- execute_trade places orders and records them.

All prices are in CENTS (integers). Trade records are stored in the database.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.common.exceptions import InvalidOrderError
from backend.common.schemas import TradeRecord, TradeSignal
from backend.trading.executor import execute_trade


def _make_mock_response(
    order_id: str = "order-123",
    count: int = 1,
    status: str = "filled",
) -> MagicMock:
    """Create a mock order response from Kalshi."""
    mock = MagicMock()
    mock.order_id = order_id
    mock.count = count
    mock.status = status
    return mock


class TestExecuteTrade:
    """Tests for execute_trade -- the full order placement flow."""

    @pytest.mark.asyncio
    async def test_successful_execution(
        self, sample_signal: TradeSignal, mock_db: AsyncMock, mock_kalshi_client: AsyncMock
    ) -> None:
        """A successful execution returns a TradeRecord with correct fields."""
        result = await execute_trade(
            signal=sample_signal,
            kalshi_client=mock_kalshi_client,
            db=mock_db,
            user_id="test-user",
        )
        assert isinstance(result, TradeRecord)
        assert result.city == "NYC"
        assert result.side == "yes"
        assert result.status == "OPEN"

    @pytest.mark.asyncio
    async def test_records_trade_in_db(
        self, sample_signal: TradeSignal, mock_db: AsyncMock, mock_kalshi_client: AsyncMock
    ) -> None:
        """db.add is called with a Trade instance."""
        await execute_trade(
            signal=sample_signal,
            kalshi_client=mock_kalshi_client,
            db=mock_db,
            user_id="test-user",
        )
        mock_db.add.assert_called_once()
        mock_db.flush.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_returns_correct_price_cents(
        self, sample_signal: TradeSignal, mock_db: AsyncMock, mock_kalshi_client: AsyncMock
    ) -> None:
        """TradeRecord.price_cents matches the signal's price_cents."""
        result = await execute_trade(
            signal=sample_signal,
            kalshi_client=mock_kalshi_client,
            db=mock_db,
            user_id="test-user",
        )
        assert result.price_cents == sample_signal.price_cents

    @pytest.mark.asyncio
    async def test_api_failure_propagates(
        self, sample_signal: TradeSignal, mock_db: AsyncMock
    ) -> None:
        """When kalshi_client.place_order raises, the exception propagates."""
        mock_client = AsyncMock()
        mock_client.place_order.side_effect = ConnectionError("API unreachable")

        with pytest.raises(ConnectionError, match="API unreachable"):
            await execute_trade(
                signal=sample_signal,
                kalshi_client=mock_client,
                db=mock_db,
                user_id="test-user",
            )

    @pytest.mark.asyncio
    async def test_canceled_order_raises(
        self, sample_signal: TradeSignal, mock_db: AsyncMock
    ) -> None:
        """When response.status == 'canceled', InvalidOrderError is raised."""
        mock_client = AsyncMock()
        mock_client.place_order.return_value = _make_mock_response(status="canceled")

        with pytest.raises(InvalidOrderError):
            await execute_trade(
                signal=sample_signal,
                kalshi_client=mock_client,
                db=mock_db,
                user_id="test-user",
            )

    @pytest.mark.asyncio
    async def test_partial_fill_logged(
        self, sample_signal: TradeSignal, mock_db: AsyncMock
    ) -> None:
        """A response with 'resting' status (partial fill) still records the trade."""
        mock_client = AsyncMock()
        mock_client.place_order.return_value = _make_mock_response(status="resting", count=1)
        # resting is NOT canceled, so should proceed
        result = await execute_trade(
            signal=sample_signal,
            kalshi_client=mock_client,
            db=mock_db,
            user_id="test-user",
        )
        assert isinstance(result, TradeRecord)

    @pytest.mark.asyncio
    async def test_trade_id_is_uuid(
        self, sample_signal: TradeSignal, mock_db: AsyncMock, mock_kalshi_client: AsyncMock
    ) -> None:
        """The returned trade id is a valid UUID string."""
        result = await execute_trade(
            signal=sample_signal,
            kalshi_client=mock_kalshi_client,
            db=mock_db,
            user_id="test-user",
        )
        # Should not raise
        parsed = uuid.UUID(result.id)
        assert str(parsed) == result.id

    @pytest.mark.asyncio
    async def test_status_is_open(
        self, sample_signal: TradeSignal, mock_db: AsyncMock, mock_kalshi_client: AsyncMock
    ) -> None:
        """The returned status is 'OPEN'."""
        result = await execute_trade(
            signal=sample_signal,
            kalshi_client=mock_kalshi_client,
            db=mock_db,
            user_id="test-user",
        )
        assert result.status == "OPEN"
