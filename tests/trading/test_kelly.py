"""Tests for backend.trading.kelly — Kelly Criterion position sizing.

Tests cover:
- Raw Kelly fraction math (YES and NO sides, with fees)
- Fractional Kelly sizing with safety caps
- Edge cases (negative edge, zero bankroll, extreme probabilities)
- Fee-adjusted calculations matching Kalshi's 15% profit fee
- All 5 safety caps
"""

from __future__ import annotations

import pytest

from backend.trading.kelly import (
    KellyResult,
    KellySettings,
    calculate_kelly_fraction,
    calculate_kelly_size,
)


# ---------------------------------------------------------------------------
# TestCalculateKellyFraction
# ---------------------------------------------------------------------------
class TestCalculateKellyFraction:
    """Test the raw Kelly fraction math."""

    def test_positive_edge_yes(self) -> None:
        """Model 35% vs market 22c YES → positive Kelly fraction."""
        f = calculate_kelly_fraction(0.35, 22, "yes")
        assert f > 0

    def test_positive_edge_no(self) -> None:
        """Model 10% for bracket vs market 80c YES → NO side has positive edge."""
        # Market says 80% chance, model says 10% → NO side prob = 90%
        # NO cost = 20c, NO profit = 80c, fee = max(1, int(80*0.15)) = 12c
        # net = 68c. Kelly = (0.90 * 68 - 0.10 * 20) / 68
        f = calculate_kelly_fraction(0.10, 80, "no")
        assert f > 0

    def test_negative_edge_yes(self) -> None:
        """Model 10% vs market 50c YES → negative edge, no bet."""
        f = calculate_kelly_fraction(0.10, 50, "yes")
        assert f < 0

    def test_negative_edge_no(self) -> None:
        """Model 90% for bracket vs market 80c YES → NO side negative edge."""
        # NO side prob = 1 - 0.90 = 10%, cost = 20c
        f = calculate_kelly_fraction(0.90, 80, "no")
        assert f < 0

    def test_zero_edge(self) -> None:
        """When model prob equals market price, Kelly ≈ 0 or slightly negative (fees)."""
        # YES at 50c, model 50%: without fees Kelly = 0, with fees < 0
        f = calculate_kelly_fraction(0.50, 50, "yes")
        assert f <= 0  # Fees push it negative

    def test_high_edge_yes(self) -> None:
        """Model 80% vs market 20c → large Kelly fraction."""
        f = calculate_kelly_fraction(0.80, 20, "yes")
        assert f > 0.5

    def test_extreme_prob_1(self) -> None:
        """Model prob = 1.0 → Kelly = 1.0 (max bet, adjusted for fees)."""
        f = calculate_kelly_fraction(1.0, 50, "yes")
        assert f > 0.9  # Close to 1 after fees

    def test_extreme_prob_0(self) -> None:
        """Model prob = 0.0 on YES side → Kelly deeply negative."""
        f = calculate_kelly_fraction(0.0, 50, "yes")
        assert f < 0

    def test_cheap_contract_yes(self) -> None:
        """YES at 5c with model 15% → positive edge."""
        f = calculate_kelly_fraction(0.15, 5, "yes")
        assert f > 0

    def test_expensive_contract_yes(self) -> None:
        """YES at 95c with model 97% → small positive edge after fees."""
        f = calculate_kelly_fraction(0.97, 95, "yes")
        # Profit if win = 5c, fee = 1c (min), net = 4c
        # Kelly = (0.97 * 4 - 0.03 * 95) / 4
        assert f > 0  # Edge exists but small

    def test_fee_impact(self) -> None:
        """Kelly with fees < Kelly without fees (fees reduce edge)."""
        with_fees = calculate_kelly_fraction(0.35, 22, "yes", fee_rate=0.15)
        without_fees = calculate_kelly_fraction(0.35, 22, "yes", fee_rate=0.0)
        assert with_fees < without_fees

    def test_invalid_model_prob_low(self) -> None:
        """model_prob < 0 raises ValueError."""
        with pytest.raises(ValueError, match="model_prob"):
            calculate_kelly_fraction(-0.1, 50, "yes")

    def test_invalid_model_prob_high(self) -> None:
        """model_prob > 1 raises ValueError."""
        with pytest.raises(ValueError, match="model_prob"):
            calculate_kelly_fraction(1.1, 50, "yes")

    def test_invalid_price_low(self) -> None:
        """price_cents < 1 raises ValueError."""
        with pytest.raises(ValueError, match="price_cents"):
            calculate_kelly_fraction(0.5, 0, "yes")

    def test_invalid_price_high(self) -> None:
        """price_cents > 99 raises ValueError."""
        with pytest.raises(ValueError, match="price_cents"):
            calculate_kelly_fraction(0.5, 100, "yes")

    def test_invalid_side(self) -> None:
        """Invalid side raises ValueError."""
        with pytest.raises(ValueError, match="side"):
            calculate_kelly_fraction(0.5, 50, "both")

    def test_symmetry(self) -> None:
        """YES at 50c with p=0.7 should equal NO at 50c with p=0.3."""
        yes_f = calculate_kelly_fraction(0.70, 50, "yes")
        no_f = calculate_kelly_fraction(0.30, 50, "no")
        # Both should have similar edges (same net exposure)
        assert abs(yes_f - no_f) < 0.01


# ---------------------------------------------------------------------------
# TestCalculateKellySize
# ---------------------------------------------------------------------------
class TestCalculateKellySize:
    """Test the full Kelly sizing with safety caps."""

    def test_disabled_returns_one(self) -> None:
        """When use_kelly_sizing is False, always returns 1 contract."""
        settings = KellySettings(use_kelly_sizing=False)
        result = calculate_kelly_size(0.35, 22, "yes", 50000, settings)
        assert result.optimal_quantity == 1
        assert result.cost_cents == 22
        assert "disabled" in result.reasons[0].lower()

    def test_negative_edge_returns_zero(self) -> None:
        """Negative edge → 0 contracts."""
        settings = KellySettings(use_kelly_sizing=True)
        result = calculate_kelly_size(0.10, 50, "yes", 50000, settings)
        assert result.optimal_quantity == 0
        assert result.cost_cents == 0
        assert "negative" in result.reasons[0].lower()

    def test_positive_edge_returns_positive(self) -> None:
        """Positive edge with a decent bankroll → at least 1 contract."""
        settings = KellySettings(
            use_kelly_sizing=True,
            kelly_fraction=0.25,
            max_contracts_per_trade=100,
            max_bankroll_pct_per_trade=0.10,
        )
        result = calculate_kelly_size(0.40, 22, "yes", 100_00, settings, max_trade_size_cents=5000)
        assert result.optimal_quantity >= 1
        assert result.cost_cents > 0

    def test_raw_kelly_populated(self) -> None:
        """KellyResult includes raw and adjusted fractions."""
        settings = KellySettings(use_kelly_sizing=True, kelly_fraction=0.25)
        result = calculate_kelly_size(0.35, 22, "yes", 50000, settings)
        assert result.raw_kelly_fraction > 0
        assert result.adjusted_kelly_fraction > 0
        assert result.adjusted_kelly_fraction < result.raw_kelly_fraction

    def test_max_contracts_cap(self) -> None:
        """Quantity capped by max_contracts_per_trade."""
        settings = KellySettings(
            use_kelly_sizing=True,
            kelly_fraction=1.0,  # Full Kelly = aggressive
            max_contracts_per_trade=3,
            max_bankroll_pct_per_trade=1.0,
        )
        result = calculate_kelly_size(
            0.80, 10, "yes", 1_000_00, settings, max_trade_size_cents=100_00
        )
        assert result.optimal_quantity <= 3

    def test_bankroll_pct_cap(self) -> None:
        """Quantity capped by max_bankroll_pct_per_trade."""
        settings = KellySettings(
            use_kelly_sizing=True,
            kelly_fraction=1.0,
            max_contracts_per_trade=1000,
            max_bankroll_pct_per_trade=0.02,  # 2% of bankroll
        )
        # Bankroll = 10000c, 2% = 200c. YES at 50c → max 4 contracts
        result = calculate_kelly_size(0.80, 50, "yes", 10000, settings, max_trade_size_cents=100_00)
        assert result.optimal_quantity <= 4

    def test_max_trade_size_cap(self) -> None:
        """Quantity capped by max_trade_size_cents from risk manager."""
        settings = KellySettings(
            use_kelly_sizing=True,
            kelly_fraction=1.0,
            max_contracts_per_trade=1000,
            max_bankroll_pct_per_trade=1.0,
        )
        # max_trade_size = 100c, YES at 25c → max 4 contracts
        result = calculate_kelly_size(0.80, 25, "yes", 1_000_00, settings, max_trade_size_cents=100)
        assert result.optimal_quantity <= 4

    def test_floor_at_one_contract(self) -> None:
        """Small bankroll with positive edge → floor at 1 contract."""
        settings = KellySettings(
            use_kelly_sizing=True,
            kelly_fraction=0.1,  # Very conservative
            max_contracts_per_trade=10,
            max_bankroll_pct_per_trade=0.05,
        )
        # Small bankroll (100c), fraction of fraction → less than 1 contract
        result = calculate_kelly_size(0.35, 22, "yes", 100, settings, max_trade_size_cents=5000)
        assert result.optimal_quantity == 1  # Floored to 1

    def test_no_side_cost_calculation(self) -> None:
        """NO side cost = 100 - price_cents."""
        settings = KellySettings(use_kelly_sizing=False)
        result = calculate_kelly_size(0.10, 80, "no", 50000, settings)
        assert result.cost_cents == 20  # 100 - 80

    def test_edge_cents_positive(self) -> None:
        """Positive edge trade shows positive edge_cents."""
        settings = KellySettings(use_kelly_sizing=True, kelly_fraction=0.25)
        result = calculate_kelly_size(0.40, 22, "yes", 50000, settings)
        assert result.edge_cents > 0

    def test_default_settings(self) -> None:
        """None settings → KellySettings with defaults (disabled)."""
        result = calculate_kelly_size(0.35, 22, "yes", 50000, None)
        assert result.optimal_quantity == 1
        assert "disabled" in result.reasons[0].lower()

    def test_result_type(self) -> None:
        """Returns a KellyResult dataclass."""
        result = calculate_kelly_size(0.35, 22, "yes", 50000)
        assert isinstance(result, KellyResult)

    def test_multiple_caps_applied(self) -> None:
        """When multiple caps apply, the tightest one wins."""
        settings = KellySettings(
            use_kelly_sizing=True,
            kelly_fraction=1.0,
            max_contracts_per_trade=2,  # This is the tightest cap
            max_bankroll_pct_per_trade=1.0,
        )
        result = calculate_kelly_size(
            0.80, 10, "yes", 1_000_00, settings, max_trade_size_cents=100_00
        )
        assert result.optimal_quantity <= 2

    def test_quarter_kelly_reduces_variance(self) -> None:
        """Quarter Kelly produces fewer contracts than half Kelly."""
        quarter = KellySettings(
            use_kelly_sizing=True,
            kelly_fraction=0.25,
            max_contracts_per_trade=100,
            max_bankroll_pct_per_trade=1.0,
        )
        half = KellySettings(
            use_kelly_sizing=True,
            kelly_fraction=0.50,
            max_contracts_per_trade=100,
            max_bankroll_pct_per_trade=1.0,
        )
        r_quarter = calculate_kelly_size(
            0.50, 22, "yes", 100_000, quarter, max_trade_size_cents=100_000
        )
        r_half = calculate_kelly_size(0.50, 22, "yes", 100_000, half, max_trade_size_cents=100_000)
        assert r_quarter.optimal_quantity <= r_half.optimal_quantity


# ---------------------------------------------------------------------------
# TestKellySettings
# ---------------------------------------------------------------------------
class TestKellySettings:
    """Test KellySettings defaults and edge cases."""

    def test_defaults(self) -> None:
        """Default settings: disabled, quarter Kelly, 5% bankroll, 10 contracts."""
        s = KellySettings()
        assert s.use_kelly_sizing is False
        assert s.kelly_fraction == 0.25
        assert s.max_bankroll_pct_per_trade == 0.05
        assert s.max_contracts_per_trade == 10

    def test_custom_settings(self) -> None:
        """Custom settings are accepted."""
        s = KellySettings(
            use_kelly_sizing=True,
            kelly_fraction=0.5,
            max_bankroll_pct_per_trade=0.10,
            max_contracts_per_trade=20,
        )
        assert s.use_kelly_sizing is True
        assert s.kelly_fraction == 0.5
        assert s.max_bankroll_pct_per_trade == 0.10
        assert s.max_contracts_per_trade == 20


# ---------------------------------------------------------------------------
# TestKellyResult
# ---------------------------------------------------------------------------
class TestKellyResult:
    """Test KellyResult dataclass."""

    def test_default_values(self) -> None:
        """Default KellyResult has sensible defaults."""
        r = KellyResult()
        assert r.raw_kelly_fraction == 0.0
        assert r.adjusted_kelly_fraction == 0.0
        assert r.optimal_quantity == 1
        assert r.cost_cents == 0
        assert r.edge_cents == 0.0
        assert r.reasons == []

    def test_reasons_mutable(self) -> None:
        """Each KellyResult has its own reasons list (no shared mutable default)."""
        r1 = KellyResult()
        r2 = KellyResult()
        r1.reasons.append("test")
        assert r2.reasons == []
