"""Tests for backend.prediction.postmortem — trade narrative generation.

Validates that ``generate_postmortem_narrative`` produces correct
human-readable narratives for both winning and losing trades.
Uses MagicMock to build Trade ORM objects without a real database.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from backend.common.models import TradeStatus
from backend.prediction.postmortem import generate_postmortem_narrative

# ─── Helpers ───


def _make_trade(
    *,
    status: TradeStatus = TradeStatus.WON,
    price_cents: int = 25,
    pnl_cents: int = 75,
    side: str = "yes",
    bracket_label: str = "53-55",
    city: str = "NYC",
    model_probability: float = 0.35,
    market_probability: float = 0.25,
    confidence: str = "medium",
) -> MagicMock:
    """Create a mock Trade ORM object with sensible defaults."""
    trade = MagicMock()
    trade.id = "trade-test-001"
    trade.status = status
    trade.price_cents = price_cents
    trade.pnl_cents = pnl_cents
    trade.side = side
    trade.bracket_label = bracket_label
    trade.city = city
    trade.model_probability = model_probability
    trade.market_probability = market_probability
    trade.confidence = confidence
    return trade


# ═══════════════════════════════════════════════════════════════
# Tests
# ═══════════════════════════════════════════════════════════════


class TestGeneratePostmortemNarrative:
    """Tests for the postmortem narrative generator."""

    def test_winning_trade_narrative(self) -> None:
        """A WON trade narrative must contain 'WIN'."""
        trade = _make_trade(status=TradeStatus.WON, pnl_cents=75)
        narrative = generate_postmortem_narrative(trade, settlement_temp_f=54.0)
        assert "WIN" in narrative

    def test_losing_trade_narrative(self) -> None:
        """A LOST trade narrative must contain 'LOSS'."""
        trade = _make_trade(status=TradeStatus.LOST, pnl_cents=-25)
        narrative = generate_postmortem_narrative(trade, settlement_temp_f=60.0)
        assert "LOSS" in narrative

    def test_includes_price_cents(self) -> None:
        """The narrative includes the entry price in cents."""
        trade = _make_trade(price_cents=42)
        narrative = generate_postmortem_narrative(trade, settlement_temp_f=54.0)
        assert "42" in narrative

    def test_includes_model_probability(self) -> None:
        """The narrative includes the model probability as a percentage."""
        trade = _make_trade(model_probability=0.35)
        narrative = generate_postmortem_narrative(trade, settlement_temp_f=54.0)
        # 0.35 formatted as "35%" via f"{0.35:.0%}"
        assert "35%" in narrative

    def test_includes_city_and_bracket(self) -> None:
        """The narrative references the city (via bracket_label) and bracket."""
        trade = _make_trade(city="NYC", bracket_label="53-55")
        narrative = generate_postmortem_narrative(trade, settlement_temp_f=54.0)
        assert "53-55" in narrative

    def test_includes_settlement_temp(self) -> None:
        """The narrative includes the actual settlement temperature."""
        trade = _make_trade()
        narrative = generate_postmortem_narrative(trade, settlement_temp_f=56.0)
        assert "56" in narrative

    def test_returns_string(self) -> None:
        """The function always returns a string."""
        trade = _make_trade()
        narrative = generate_postmortem_narrative(trade, settlement_temp_f=54.0)
        assert isinstance(narrative, str)

    def test_pnl_cents_displayed(self) -> None:
        """P&L value appears in the narrative (converted to dollars)."""
        trade = _make_trade(status=TradeStatus.WON, pnl_cents=75)
        narrative = generate_postmortem_narrative(trade, settlement_temp_f=54.0)
        # pnl_cents=75 → $0.75
        assert "0.75" in narrative
