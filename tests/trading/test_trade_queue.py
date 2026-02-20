"""Tests for backend.trading.trade_queue -- manual trade approval queue.

State machine: PENDING -> APPROVED | REJECTED | EXPIRED.
Default TTL is 30 minutes.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.common.models import PendingTradeModel, PendingTradeStatus
from backend.common.schemas import TradeSignal
from backend.trading.trade_queue import (
    PENDING_TRADE_TTL_MINUTES,
    approve_trade,
    expire_stale_trades,
    queue_trade,
    reject_trade,
)


class TestQueueTrade:
    """Tests for queue_trade -- creating pending trades."""

    @pytest.mark.asyncio
    async def test_queue_creates_pending_trade(
        self, sample_signal: TradeSignal, mock_db: AsyncMock
    ) -> None:
        """queue_trade returns a PendingTrade with status PENDING."""
        result = await queue_trade(
            signal=sample_signal,
            db=mock_db,
            user_id="test-user",
            market_ticker="KXHIGHNY-26FEB18-B3",
        )
        assert result.status == "PENDING"
        assert result.city == "NYC"
        assert result.side == "yes"
        assert result.price_cents == 22

    @pytest.mark.asyncio
    async def test_queue_sets_expiration(
        self, sample_signal: TradeSignal, mock_db: AsyncMock
    ) -> None:
        """expires_at is approximately 30 minutes after created_at."""
        result = await queue_trade(
            signal=sample_signal,
            db=mock_db,
            user_id="test-user",
            market_ticker="KXHIGHNY-26FEB18-B3",
        )
        delta = result.expires_at - result.created_at
        # Should be approximately 30 minutes
        assert abs(delta.total_seconds() - PENDING_TRADE_TTL_MINUTES * 60) < 5

    @pytest.mark.asyncio
    async def test_queue_sends_notification(
        self, sample_signal: TradeSignal, mock_db: AsyncMock
    ) -> None:
        """When notification_service is provided, send is called."""
        mock_notif = AsyncMock()
        await queue_trade(
            signal=sample_signal,
            db=mock_db,
            user_id="test-user",
            market_ticker="KXHIGHNY-26FEB18-B3",
            notification_service=mock_notif,
        )
        mock_notif.send.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_queue_handles_notification_failure(
        self, sample_signal: TradeSignal, mock_db: AsyncMock
    ) -> None:
        """If notification service raises, queue_trade does not crash."""
        mock_notif = AsyncMock()
        mock_notif.send.side_effect = RuntimeError("push failed")
        # Should not raise
        result = await queue_trade(
            signal=sample_signal,
            db=mock_db,
            user_id="test-user",
            market_ticker="KXHIGHNY-26FEB18-B3",
            notification_service=mock_notif,
        )
        assert result.status == "PENDING"


class TestApproveTrade:
    """Tests for approve_trade -- approving pending trades."""

    def _mock_db_with_trade(
        self, status: PendingTradeStatus = PendingTradeStatus.PENDING, expired: bool = False
    ) -> AsyncMock:
        """Create a mock DB that returns a PendingTradeModel with the given status."""
        mock_trade = MagicMock(spec=PendingTradeModel)
        mock_trade.status = status
        if expired:
            mock_trade.expires_at = datetime.now(UTC).replace(tzinfo=None) - timedelta(minutes=5)
        else:
            mock_trade.expires_at = datetime.now(UTC).replace(tzinfo=None) + timedelta(minutes=30)
        mock_trade.acted_at = None

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_trade
        mock_db.execute.return_value = mock_result
        return mock_db

    @pytest.mark.asyncio
    async def test_approve_changes_status(self) -> None:
        """Approving a PENDING trade changes status to APPROVED."""
        mock_db = self._mock_db_with_trade(PendingTradeStatus.PENDING)
        result = await approve_trade("trade-123", mock_db)
        assert result.status == PendingTradeStatus.APPROVED

    @pytest.mark.asyncio
    async def test_approve_nonexistent_raises(self) -> None:
        """Approving a nonexistent trade raises ValueError."""
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        with pytest.raises(ValueError, match="not found"):
            await approve_trade("bad-id", mock_db)

    @pytest.mark.asyncio
    async def test_approve_non_pending_raises(self) -> None:
        """Approving an already-APPROVED trade raises ValueError."""
        mock_db = self._mock_db_with_trade(PendingTradeStatus.APPROVED)
        with pytest.raises(ValueError, match="not PENDING"):
            await approve_trade("trade-123", mock_db)


class TestRejectTrade:
    """Tests for reject_trade -- rejecting pending trades."""

    def _mock_db_with_trade(
        self, status: PendingTradeStatus = PendingTradeStatus.PENDING
    ) -> AsyncMock:
        """Create a mock DB that returns a PendingTradeModel."""
        mock_trade = MagicMock(spec=PendingTradeModel)
        mock_trade.status = status
        mock_trade.acted_at = None

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_trade
        mock_db.execute.return_value = mock_result
        return mock_db

    @pytest.mark.asyncio
    async def test_reject_changes_status(self) -> None:
        """Rejecting a PENDING trade changes status to REJECTED."""
        mock_db = self._mock_db_with_trade(PendingTradeStatus.PENDING)
        result = await reject_trade("trade-123", mock_db)
        assert result.status == PendingTradeStatus.REJECTED

    @pytest.mark.asyncio
    async def test_reject_nonexistent_raises(self) -> None:
        """Rejecting a nonexistent trade raises ValueError."""
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        with pytest.raises(ValueError, match="not found"):
            await reject_trade("bad-id", mock_db)


class TestExpireStaleTrades:
    """Tests for expire_stale_trades -- expiring old pending trades."""

    @pytest.mark.asyncio
    async def test_expire_stale_trades(self) -> None:
        """Trades past TTL get their status set to EXPIRED and count is returned."""
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.rowcount = 3
        mock_db.execute.return_value = mock_result

        count = await expire_stale_trades(mock_db)
        assert count == 3
        mock_db.execute.assert_awaited_once()
        mock_db.flush.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_expire_returns_zero_when_none_expired(self) -> None:
        """When no trades are stale, returns 0."""
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.rowcount = 0
        mock_db.execute.return_value = mock_result

        count = await expire_stale_trades(mock_db)
        assert count == 0
