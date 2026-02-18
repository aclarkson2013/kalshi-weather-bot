"""Tests for backend.trading.postmortem -- settlement, bracket matching, narratives.

After market settlement (NWS CLI report), this module determines win/loss,
calculates P&L in cents (including fees), and generates human-readable narratives.

Bracket label formats:
    "53-54F"   -> standard 2-degree bracket (lower <= temp <= upper)
    "<=52F"    -> bottom catch-all (temp <= bound)
    ">=57F"    -> top catch-all (temp >= bound)
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.common.models import Settlement, Trade, TradeStatus
from backend.trading.postmortem import (
    _did_bracket_win,
    generate_postmortem_narrative,
    settle_trade,
)


# ---------------------------------------------------------------------------
# TestDidBracketWin
# ---------------------------------------------------------------------------
class TestDidBracketWin:
    """Test _did_bracket_win -- bracket hit detection for all label formats."""

    def test_standard_bracket_hit_yes(self) -> None:
        """'53-54F', temp=53.5, side='yes' -> True (bracket hit, YES wins)."""
        assert _did_bracket_win("53-54F", 53.5, "yes") is True

    def test_standard_bracket_miss_yes(self) -> None:
        """'53-54F', temp=55, side='yes' -> False (bracket miss, YES loses)."""
        assert _did_bracket_win("53-54F", 55.0, "yes") is False

    def test_no_side_inverts(self) -> None:
        """'53-54F', temp=55, side='no' -> True (bracket miss, NO wins)."""
        assert _did_bracket_win("53-54F", 55.0, "no") is True

    def test_bottom_bracket(self) -> None:
        """'<=52F', temp=51 -> bracket hit (YES wins)."""
        assert _did_bracket_win("<=52F", 51.0, "yes") is True

    def test_bottom_bracket_miss(self) -> None:
        """'<=52F', temp=55 -> bracket miss (YES loses)."""
        assert _did_bracket_win("<=52F", 55.0, "yes") is False

    def test_top_bracket(self) -> None:
        """'>=57F', temp=58 -> bracket hit (YES wins)."""
        assert _did_bracket_win(">=57F", 58.0, "yes") is True

    def test_top_bracket_miss(self) -> None:
        """'>=57F', temp=55 -> bracket miss (YES loses)."""
        assert _did_bracket_win(">=57F", 55.0, "yes") is False

    def test_degree_symbol_handling(self) -> None:
        """'53-54\u00b0F' with degree symbol should parse correctly."""
        assert _did_bracket_win("53-54\u00b0F", 53.5, "yes") is True
        assert _did_bracket_win("53-54\u00b0F", 55.0, "yes") is False


# ---------------------------------------------------------------------------
# TestGeneratePostmortemNarrative
# ---------------------------------------------------------------------------
class TestGeneratePostmortemNarrative:
    """Test narrative generation for trade post-mortems."""

    def _make_trade(self, status: TradeStatus, pnl_cents: int = 67) -> MagicMock:
        """Create a mock Trade ORM object."""
        trade = MagicMock(spec=Trade)
        trade.bracket_label = "53-54F"
        trade.side = "yes"
        trade.price_cents = 22
        trade.quantity = 1
        trade.city = MagicMock()
        trade.city.value = "NYC"
        trade.trade_date = datetime(2026, 2, 18, tzinfo=UTC)
        trade.model_probability = 0.30
        trade.market_probability = 0.22
        trade.confidence = "medium"
        trade.status = status
        trade.pnl_cents = pnl_cents
        return trade

    def _make_settlement(self, temp: float = 53.5) -> MagicMock:
        """Create a mock Settlement ORM object."""
        settlement = MagicMock(spec=Settlement)
        settlement.actual_high_f = temp
        settlement.source = "NWS_CLI"
        return settlement

    def test_includes_outcome(self) -> None:
        """A winning trade narrative contains 'WIN'."""
        trade = self._make_trade(TradeStatus.WON, pnl_cents=67)
        settlement = self._make_settlement(53.5)
        narrative = generate_postmortem_narrative(trade, settlement, forecasts=[])
        assert "WIN" in narrative

    def test_includes_loss_outcome(self) -> None:
        """A losing trade narrative contains 'LOSS'."""
        trade = self._make_trade(TradeStatus.LOST, pnl_cents=-22)
        settlement = self._make_settlement(55.0)
        narrative = generate_postmortem_narrative(trade, settlement, forecasts=[])
        assert "LOSS" in narrative

    def test_includes_actual_temp(self) -> None:
        """The actual settlement temperature appears in the narrative."""
        trade = self._make_trade(TradeStatus.WON, pnl_cents=67)
        settlement = self._make_settlement(53.5)
        narrative = generate_postmortem_narrative(trade, settlement, forecasts=[])
        # Should contain "53F" or "54F" (rounded)
        assert "53" in narrative or "54" in narrative


# ---------------------------------------------------------------------------
# TestSettleTrade
# ---------------------------------------------------------------------------
class TestSettleTrade:
    """Test settle_trade -- async settlement of a trade."""

    def _make_trade(self) -> MagicMock:
        """Create a mock Trade ORM object for settlement."""
        trade = MagicMock(spec=Trade)
        trade.bracket_label = "53-54F"
        trade.side = "yes"
        trade.price_cents = 22
        trade.quantity = 1
        trade.city = MagicMock()
        trade.city.value = "NYC"
        trade.trade_date = datetime(2026, 2, 18, tzinfo=UTC)
        trade.model_probability = 0.30
        trade.market_probability = 0.22
        trade.confidence = "medium"
        trade.status = TradeStatus.OPEN
        trade.pnl_cents = None
        trade.fees_cents = None
        trade.settlement_temp_f = None
        trade.settlement_source = None
        trade.settled_at = None
        trade.postmortem_narrative = None
        return trade

    def _make_settlement(self, temp: float) -> MagicMock:
        """Create a mock Settlement ORM object."""
        settlement = MagicMock(spec=Settlement)
        settlement.actual_high_f = temp
        settlement.source = "NWS_CLI"
        return settlement

    def _make_mock_db(self) -> AsyncMock:
        """Create a mock DB that returns empty forecasts."""
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute.return_value = mock_result
        return mock_db

    @pytest.mark.asyncio
    async def test_winning_trade_pnl(self) -> None:
        """YES at 22c wins: pnl_cents = (100-22) - fee.
        fee = estimate_fees(22, 'yes') = max(1, int(78*0.15)) = 11c.
        pnl = 78 - 11 = 67c.
        """
        trade = self._make_trade()
        settlement = self._make_settlement(53.5)  # Within bracket 53-54F
        mock_db = self._make_mock_db()

        await settle_trade(trade, settlement, mock_db)

        assert trade.status == TradeStatus.WON
        assert trade.pnl_cents == 67
        assert trade.fees_cents == 11

    @pytest.mark.asyncio
    async def test_losing_trade_pnl(self) -> None:
        """YES at 22c loses: pnl_cents = -22 (lost the cost)."""
        trade = self._make_trade()
        settlement = self._make_settlement(55.0)  # Outside bracket 53-54F
        mock_db = self._make_mock_db()

        await settle_trade(trade, settlement, mock_db)

        assert trade.status == TradeStatus.LOST
        assert trade.pnl_cents == -22
        assert trade.fees_cents == 0
