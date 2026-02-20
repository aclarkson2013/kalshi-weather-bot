"""Tests for backend.trading.ev_calculator -- EV math, bracket scanning, validation.

Fee calculation and EV math are the core of all trading decisions.
All prices are in CENTS (integers). EV output is in DOLLARS (float).
Fee calculation returns CENTS (int).
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from unittest.mock import patch
from zoneinfo import ZoneInfo

import pytest

from backend.common.schemas import BracketPrediction, BracketProbability, TradeSignal
from backend.trading.ev_calculator import (
    calculate_ev,
    estimate_fees,
    scan_all_brackets,
    scan_bracket,
    validate_market_prices,
    validate_predictions,
)
from backend.trading.kelly import KellySettings

ET = ZoneInfo("America/New_York")


# ---------------------------------------------------------------------------
# TestEstimateFees
# ---------------------------------------------------------------------------
class TestEstimateFees:
    """Fee calculation must be exact -- this is real money."""

    def test_yes_side_standard(self) -> None:
        """Buy YES at 22c: profit if win = 78c, fee = max(1, int(78*0.15)) = 11c."""
        assert estimate_fees(22, "yes") == 11

    def test_no_side_standard(self) -> None:
        """Buy NO where YES = 22c: profit if win = 22c, fee = max(1, int(22*0.15)) = 3c."""
        assert estimate_fees(22, "no") == 3

    def test_minimum_fee_applied(self) -> None:
        """Buy YES at 95c: profit = 5c, 15% = 0.75 -> fee = 1c (minimum)."""
        assert estimate_fees(95, "yes") == 1

    def test_high_price_yes(self) -> None:
        """Buy YES at 85c: profit = 15c, fee = max(1, int(15*0.15)) = 2c."""
        assert estimate_fees(85, "yes") == 2

    def test_high_price_no(self) -> None:
        """Buy NO where YES = 85c: profit if win = 85c, fee = max(1, int(85*0.15)) = 12c."""
        assert estimate_fees(85, "no") == 12

    def test_invalid_price_zero_raises(self) -> None:
        """Price of 0 is out of range [1, 99]."""
        with pytest.raises(ValueError, match="price_cents must be 1-99"):
            estimate_fees(0, "yes")

    def test_invalid_price_100_raises(self) -> None:
        """Price of 100 is out of range [1, 99]."""
        with pytest.raises(ValueError, match="price_cents must be 1-99"):
            estimate_fees(100, "yes")

    def test_invalid_side_raises(self) -> None:
        """Side must be 'yes' or 'no'."""
        with pytest.raises(ValueError, match="side must be"):
            estimate_fees(50, "maybe")

    def test_returns_int(self) -> None:
        """Fee must always be an integer (cents)."""
        result = estimate_fees(50, "yes")
        assert isinstance(result, int)


# ---------------------------------------------------------------------------
# TestCalculateEV
# ---------------------------------------------------------------------------
class TestCalculateEV:
    """EV calculation is the core of all trading decisions."""

    def test_positive_ev_yes(self) -> None:
        """Model 40%, market 22c YES: EV = (0.40 * 1.00) - 0.22 - 0.11 = +0.07."""
        ev = calculate_ev(0.40, 22, "yes")
        assert ev == 0.07

    def test_negative_ev_yes(self) -> None:
        """Model 20%, market 22c YES: EV = (0.20 * 1.00) - 0.22 - 0.11 = -0.13."""
        ev = calculate_ev(0.20, 22, "yes")
        assert ev == -0.13

    def test_no_side_ev(self) -> None:
        """Model 28% for bracket, market YES = 22c, NO side:
        prob_win = 0.72, cost = 0.78, fee = 0.03 -> EV = 0.72 - 0.78 - 0.03 = -0.09.
        """
        ev = calculate_ev(0.28, 22, "no")
        assert ev == -0.09

    def test_ev_symmetry_both_negative(self) -> None:
        """If model agrees with market (50/50), both sides negative due to fees."""
        ev_yes = calculate_ev(0.50, 50, "yes")
        ev_no = calculate_ev(0.50, 50, "no")
        assert ev_yes < 0, "YES side should be negative EV (fees eat the edge)"
        assert ev_no < 0, "NO side should be negative EV (fees eat the edge)"

    def test_invalid_prob_raises(self) -> None:
        """Probability > 1.0 must raise ValueError."""
        with pytest.raises(ValueError, match="model_prob must be"):
            calculate_ev(1.5, 50, "yes")

    def test_negative_prob_raises(self) -> None:
        """Probability < 0.0 must raise ValueError."""
        with pytest.raises(ValueError, match="model_prob must be"):
            calculate_ev(-0.1, 50, "yes")

    def test_returns_float(self) -> None:
        """EV must be a float."""
        result = calculate_ev(0.30, 30, "yes")
        assert isinstance(result, float)

    def test_ev_precision(self) -> None:
        """Result should be rounded to 4 decimal places."""
        ev = calculate_ev(0.333, 33, "yes")
        # Check that the number of decimal places is at most 4
        ev_str = f"{ev:.10f}"
        # After the 4th decimal, everything should be 0
        decimal_part = ev_str.split(".")[1]
        assert decimal_part[4:] == "000000", f"EV {ev} has more than 4 decimal places"


# ---------------------------------------------------------------------------
# TestScanBracket
# ---------------------------------------------------------------------------
class TestScanBracket:
    """Scanning a single bracket for +EV opportunities."""

    def test_positive_ev_returns_signal(self) -> None:
        """A bracket with +EV above threshold returns a TradeSignal."""
        signal = scan_bracket(
            bracket_label="55-56F",
            bracket_probability=0.45,
            market_price_cents=22,
            min_ev_threshold=0.05,
            city="NYC",
            prediction_date="2026-02-18",
            confidence="medium",
            market_ticker="KXHIGHNY-26FEB18-B3",
        )
        assert signal is not None
        assert isinstance(signal, TradeSignal)
        assert signal.ev >= 0.05

    def test_below_threshold_returns_none(self) -> None:
        """A bracket with +EV below threshold returns None."""
        signal = scan_bracket(
            bracket_label="55-56F",
            bracket_probability=0.30,
            market_price_cents=22,
            min_ev_threshold=0.10,  # high threshold
            city="NYC",
            prediction_date="2026-02-18",
            confidence="medium",
            market_ticker="KXHIGHNY-26FEB18-B3",
        )
        assert signal is None

    def test_picks_better_side(self) -> None:
        """When one side is +EV, returns that side."""
        # Model prob 45%, market 22c:
        # YES EV = 0.45 - 0.22 - 0.11 = +0.12 (good)
        # NO EV  = 0.55 - 0.78 - 0.03 = -0.26 (bad)
        signal = scan_bracket(
            bracket_label="55-56F",
            bracket_probability=0.45,
            market_price_cents=22,
            min_ev_threshold=0.05,
            city="NYC",
            prediction_date="2026-02-18",
            confidence="medium",
            market_ticker="KXHIGHNY-26FEB18-B3",
        )
        assert signal is not None
        assert signal.side == "yes"

    def test_no_opportunity_returns_none(self) -> None:
        """When both sides are negative EV, returns None."""
        signal = scan_bracket(
            bracket_label="55-56F",
            bracket_probability=0.50,
            market_price_cents=50,
            min_ev_threshold=0.01,
            city="NYC",
            prediction_date="2026-02-18",
            confidence="medium",
            market_ticker="KXHIGHNY-26FEB18-B3",
        )
        assert signal is None

    def test_signal_fields_populated(self) -> None:
        """Returned signal has correct city, bracket, and ticker."""
        signal = scan_bracket(
            bracket_label="55-56F",
            bracket_probability=0.50,
            market_price_cents=22,
            min_ev_threshold=0.01,
            city="NYC",
            prediction_date="2026-02-18",
            confidence="high",
            market_ticker="KXHIGHNY-26FEB18-B3",
        )
        assert signal is not None
        assert signal.city == "NYC"
        assert signal.bracket == "55-56F"
        assert signal.market_ticker == "KXHIGHNY-26FEB18-B3"
        assert signal.confidence == "high"


# ---------------------------------------------------------------------------
# TestScanAllBrackets
# ---------------------------------------------------------------------------
class TestScanAllBrackets:
    """Scanning all brackets for a city -- integration of scan_bracket."""

    def _make_prediction(self, brackets: list[BracketProbability]) -> BracketPrediction:
        """Helper to build a valid BracketPrediction."""
        return BracketPrediction(
            city="NYC",
            date=date(2026, 2, 18),
            brackets=brackets,
            ensemble_mean_f=55.0,
            ensemble_std_f=2.0,
            confidence="medium",
            model_sources=["NWS", "GFS"],
            generated_at=datetime.now(UTC),
        )

    def test_returns_sorted_by_ev(self) -> None:
        """Signals are returned sorted by EV descending."""
        brackets = [
            BracketProbability(bracket_label="53-54F", probability=0.10),
            BracketProbability(bracket_label="55-56F", probability=0.10),
            BracketProbability(bracket_label="57-58F", probability=0.50),
            BracketProbability(bracket_label="59-60F", probability=0.10),
            BracketProbability(bracket_label="<=52F", probability=0.10),
            BracketProbability(bracket_label=">=61F", probability=0.10),
        ]
        prediction = self._make_prediction(brackets)
        # Set prices so at least some brackets are +EV
        market_prices = {
            "53-54F": 5,
            "55-56F": 5,
            "57-58F": 22,
            "59-60F": 5,
            "<=52F": 5,
            ">=61F": 5,
        }
        market_tickers = {
            "53-54F": "T1",
            "55-56F": "T2",
            "57-58F": "T3",
            "59-60F": "T4",
            "<=52F": "T5",
            ">=61F": "T6",
        }
        signals = scan_all_brackets(prediction, market_prices, market_tickers, 0.01)
        if len(signals) > 1:
            for i in range(len(signals) - 1):
                assert signals[i].ev >= signals[i + 1].ev

    def test_missing_price_skipped(self) -> None:
        """Brackets without a market price are skipped."""
        brackets = [
            BracketProbability(bracket_label="53-54F", probability=0.10),
            BracketProbability(bracket_label="55-56F", probability=0.50),
            BracketProbability(bracket_label="57-58F", probability=0.10),
            BracketProbability(bracket_label="59-60F", probability=0.10),
            BracketProbability(bracket_label="<=52F", probability=0.10),
            BracketProbability(bracket_label=">=61F", probability=0.10),
        ]
        prediction = self._make_prediction(brackets)
        # Only provide price for one bracket
        market_prices = {"55-56F": 22}
        market_tickers = {"55-56F": "T2"}
        signals = scan_all_brackets(prediction, market_prices, market_tickers, 0.01)
        # Only one bracket had a price, so at most one signal
        for s in signals:
            assert s.bracket == "55-56F"

    def test_missing_ticker_skipped(self) -> None:
        """Brackets without a market ticker are skipped even if price exists."""
        brackets = [
            BracketProbability(bracket_label="53-54F", probability=0.50),
            BracketProbability(bracket_label="55-56F", probability=0.10),
            BracketProbability(bracket_label="57-58F", probability=0.10),
            BracketProbability(bracket_label="59-60F", probability=0.10),
            BracketProbability(bracket_label="<=52F", probability=0.10),
            BracketProbability(bracket_label=">=61F", probability=0.10),
        ]
        prediction = self._make_prediction(brackets)
        # Price exists but no ticker
        market_prices = {"53-54F": 22}
        market_tickers = {}  # empty -- no tickers
        signals = scan_all_brackets(prediction, market_prices, market_tickers, 0.01)
        assert len(signals) == 0

    def test_empty_when_no_opportunities(self) -> None:
        """Returns empty list when no brackets have +EV."""
        brackets = [
            BracketProbability(bracket_label="53-54F", probability=0.17),
            BracketProbability(bracket_label="55-56F", probability=0.17),
            BracketProbability(bracket_label="57-58F", probability=0.16),
            BracketProbability(bracket_label="59-60F", probability=0.17),
            BracketProbability(bracket_label="<=52F", probability=0.17),
            BracketProbability(bracket_label=">=61F", probability=0.16),
        ]
        prediction = self._make_prediction(brackets)
        # Prices roughly match model probs -- fees eat any edge
        market_prices = {
            "53-54F": 17,
            "55-56F": 17,
            "57-58F": 16,
            "59-60F": 17,
            "<=52F": 17,
            ">=61F": 16,
        }
        market_tickers = {
            "53-54F": "T1",
            "55-56F": "T2",
            "57-58F": "T3",
            "59-60F": "T4",
            "<=52F": "T5",
            ">=61F": "T6",
        }
        signals = scan_all_brackets(prediction, market_prices, market_tickers, 0.05)
        assert len(signals) == 0


# ---------------------------------------------------------------------------
# TestValidatePredictions
# ---------------------------------------------------------------------------
class TestValidatePredictions:
    """Validate prediction data before trading on it."""

    def _make_valid_prediction(self) -> BracketPrediction:
        """Create a valid prediction for testing."""
        return BracketPrediction(
            city="NYC",
            date=date(2026, 2, 18),
            brackets=[
                BracketProbability(bracket_label="<=52F", probability=0.08),
                BracketProbability(bracket_label="53-54F", probability=0.15),
                BracketProbability(bracket_label="55-56F", probability=0.30),
                BracketProbability(bracket_label="57-58F", probability=0.28),
                BracketProbability(bracket_label="59-60F", probability=0.12),
                BracketProbability(bracket_label=">=61F", probability=0.07),
            ],
            ensemble_mean_f=56.0,
            ensemble_std_f=2.0,
            confidence="medium",
            model_sources=["NWS", "GFS"],
            generated_at=datetime.now(UTC),
        )

    def test_valid_predictions_pass(self) -> None:
        """Standard valid predictions pass validation."""
        pred = self._make_valid_prediction()
        assert validate_predictions([pred]) is True

    def test_probabilities_not_summing_fails(self) -> None:
        """Probabilities summing to 0.5 should fail validation."""
        # BracketPrediction's validator rejects probs that don't sum to ~1.0,
        # so we create a valid one and then mutate bracket probs directly.
        pred = self._make_valid_prediction()
        # Halve all probabilities so they sum to ~0.5
        for b in pred.brackets:
            b.probability = b.probability / 2.0
        assert validate_predictions([pred]) is False

    def test_nan_probability_fails(self) -> None:
        """NaN probability must cause validation failure."""
        # We need to bypass Pydantic validation, so construct and patch
        pred = self._make_valid_prediction()
        # Directly mutate the bracket probability to NaN
        pred.brackets[0].probability = float("nan")
        assert validate_predictions([pred]) is False

    def test_wrong_bracket_count_fails(self) -> None:
        """Predictions with 5 brackets (instead of 6) should fail."""
        # Build a prediction with 5 brackets that sum to ~1.0
        pred = BracketPrediction(
            city="NYC",
            date=date(2026, 2, 18),
            brackets=[
                BracketProbability(bracket_label="<=52F", probability=0.10),
                BracketProbability(bracket_label="53-54F", probability=0.20),
                BracketProbability(bracket_label="55-56F", probability=0.30),
                BracketProbability(bracket_label="57-58F", probability=0.25),
                BracketProbability(bracket_label=">=61F", probability=0.15),
            ],
            ensemble_mean_f=56.0,
            ensemble_std_f=2.0,
            confidence="medium",
            model_sources=["NWS"],
            generated_at=datetime.now(UTC),
        )
        assert validate_predictions([pred]) is False


# ---------------------------------------------------------------------------
# TestValidateMarketPrices
# ---------------------------------------------------------------------------
class TestValidateMarketPrices:
    """Validate market prices from Kalshi before using them."""

    def test_valid_prices_pass(self) -> None:
        """All valid integer prices [1, 99] pass."""
        prices = {"53-54F": 22, "55-56F": 35, "57-58F": 50}
        assert validate_market_prices(prices) is True

    def test_zero_price_fails(self) -> None:
        """Price of 0 is invalid."""
        prices = {"53-54F": 0}
        assert validate_market_prices(prices) is False

    def test_hundred_price_fails(self) -> None:
        """Price of 100 is invalid."""
        prices = {"53-54F": 100}
        assert validate_market_prices(prices) is False

    def test_non_int_fails(self) -> None:
        """Float price is invalid."""
        prices = {"53-54F": 22.5}
        assert validate_market_prices(prices) is False


# ---------------------------------------------------------------------------
# TestScanBracketKellyIntegration
# ---------------------------------------------------------------------------
class TestScanBracketKellyIntegration:
    """Test Kelly Criterion integration with scan_bracket and scan_all_brackets."""

    def _scan_with_kelly(
        self,
        kelly_enabled: bool = True,
        kelly_fraction: float = 0.25,
        max_contracts: int = 10,
        max_bankroll_pct: float = 0.05,
        bankroll_cents: int = 50_000,
        max_trade_size_cents: int = 5000,
        bracket_probability: float = 0.45,
        market_price_cents: int = 22,
    ) -> TradeSignal | None:
        """Helper to call scan_bracket with Kelly params."""
        settings = KellySettings(
            use_kelly_sizing=kelly_enabled,
            kelly_fraction=kelly_fraction,
            max_contracts_per_trade=max_contracts,
            max_bankroll_pct_per_trade=max_bankroll_pct,
        )
        return scan_bracket(
            bracket_label="55-56F",
            bracket_probability=bracket_probability,
            market_price_cents=market_price_cents,
            min_ev_threshold=0.01,
            city="NYC",
            prediction_date="2026-02-18",
            confidence="medium",
            market_ticker="KXHIGHNY-26FEB18-B3",
            kelly_settings=settings,
            bankroll_cents=bankroll_cents,
            max_trade_size_cents=max_trade_size_cents,
        )

    def test_kelly_disabled_returns_quantity_one(self) -> None:
        """When kelly_settings.use_kelly_sizing=False, quantity=1."""
        signal = self._scan_with_kelly(kelly_enabled=False)
        assert signal is not None
        assert signal.quantity == 1

    def test_kelly_none_returns_quantity_one(self) -> None:
        """When kelly_settings is None, quantity=1 (backward compatible)."""
        signal = scan_bracket(
            bracket_label="55-56F",
            bracket_probability=0.45,
            market_price_cents=22,
            min_ev_threshold=0.01,
            city="NYC",
            prediction_date="2026-02-18",
            confidence="medium",
            market_ticker="KXHIGHNY-26FEB18-B3",
        )
        assert signal is not None
        assert signal.quantity == 1

    def test_kelly_enabled_increases_quantity(self) -> None:
        """With Kelly enabled and large bankroll, quantity should be > 1."""
        signal = self._scan_with_kelly(
            bankroll_cents=100_000,
            max_contracts=100,
            max_bankroll_pct=0.50,
            max_trade_size_cents=100_000,
            kelly_fraction=0.50,
        )
        assert signal is not None
        assert signal.quantity > 1

    def test_kelly_no_edge_returns_none(self) -> None:
        """When Kelly finds no edge after fees, the trade is skipped."""
        # Model prob = 50%, market = 50c → no edge after fees
        signal = self._scan_with_kelly(
            bracket_probability=0.50,
            market_price_cents=50,
        )
        # EV threshold may catch this too, but with min_ev=0.01 it might pass EV
        # but fail Kelly (which is stricter about fees)
        # Either way, the trade should be None or have quantity
        # Actually the EV calc itself will return None since both sides are -EV with fees
        assert signal is None

    def test_max_contracts_cap_respected(self) -> None:
        """Kelly output is capped at max_contracts_per_trade."""
        signal = self._scan_with_kelly(
            bankroll_cents=1_000_000,
            max_contracts=3,
            max_bankroll_pct=1.0,
            max_trade_size_cents=1_000_000,
            kelly_fraction=1.0,
        )
        assert signal is not None
        assert signal.quantity <= 3

    def test_max_bankroll_pct_cap(self) -> None:
        """Quantity limited by bankroll percentage cap."""
        # Bankroll = 10000c, 2% = 200c. YES at 50c → max 4 contracts
        signal = self._scan_with_kelly(
            bankroll_cents=10_000,
            max_contracts=100,
            max_bankroll_pct=0.02,
            max_trade_size_cents=100_000,
            kelly_fraction=1.0,
            bracket_probability=0.80,
            market_price_cents=50,
        )
        assert signal is not None
        assert signal.quantity <= 4

    def test_max_trade_size_cap(self) -> None:
        """Quantity limited by max_trade_size_cents."""
        # max_trade_size = 50c, YES at 22c → max 2 contracts
        signal = self._scan_with_kelly(
            bankroll_cents=1_000_000,
            max_contracts=100,
            max_bankroll_pct=1.0,
            max_trade_size_cents=50,
            kelly_fraction=1.0,
        )
        assert signal is not None
        assert signal.quantity <= 2

    def test_small_bankroll_floors_to_one(self) -> None:
        """With tiny bankroll and positive edge, floors to 1 contract."""
        signal = self._scan_with_kelly(
            bankroll_cents=100,
            kelly_fraction=0.10,
        )
        assert signal is not None
        assert signal.quantity == 1

    def test_kelly_failure_falls_back_to_one(self) -> None:
        """If Kelly raises, graceful degradation to quantity=1."""
        settings = KellySettings(use_kelly_sizing=True, kelly_fraction=0.25)
        with patch(
            "backend.trading.kelly.calculate_kelly_size",
            side_effect=RuntimeError("model crashed"),
        ):
            signal = scan_bracket(
                bracket_label="55-56F",
                bracket_probability=0.45,
                market_price_cents=22,
                min_ev_threshold=0.01,
                city="NYC",
                prediction_date="2026-02-18",
                confidence="medium",
                market_ticker="KXHIGHNY-26FEB18-B3",
                kelly_settings=settings,
                bankroll_cents=50_000,
                max_trade_size_cents=5000,
            )
        assert signal is not None
        assert signal.quantity == 1

    def test_scan_all_brackets_passes_kelly_params(self) -> None:
        """scan_all_brackets passes Kelly settings through to scan_bracket."""
        brackets = [
            BracketProbability(bracket_label="53-54F", probability=0.05),
            BracketProbability(bracket_label="55-56F", probability=0.45),
            BracketProbability(bracket_label="57-58F", probability=0.25),
            BracketProbability(bracket_label="59-60F", probability=0.10),
            BracketProbability(bracket_label="<=52F", probability=0.05),
            BracketProbability(bracket_label=">=61F", probability=0.10),
        ]
        prediction = BracketPrediction(
            city="NYC",
            date=date(2026, 2, 18),
            brackets=brackets,
            ensemble_mean_f=55.0,
            ensemble_std_f=2.0,
            confidence="medium",
            model_sources=["NWS", "GFS"],
            generated_at=datetime.now(UTC),
        )
        market_prices = {
            "53-54F": 5,
            "55-56F": 22,
            "57-58F": 20,
            "59-60F": 5,
            "<=52F": 5,
            ">=61F": 5,
        }
        market_tickers = {
            "53-54F": "T1",
            "55-56F": "T2",
            "57-58F": "T3",
            "59-60F": "T4",
            "<=52F": "T5",
            ">=61F": "T6",
        }
        settings = KellySettings(
            use_kelly_sizing=True,
            kelly_fraction=0.25,
            max_contracts_per_trade=100,
            max_bankroll_pct_per_trade=0.50,
        )
        signals = scan_all_brackets(
            prediction,
            market_prices,
            market_tickers,
            0.01,
            kelly_settings=settings,
            bankroll_cents=100_000,
            max_trade_size_cents=100_000,
        )
        # All signals should have Kelly-calculated quantities
        for s in signals:
            assert s.quantity >= 1

    def test_sort_order_preserved_with_kelly(self) -> None:
        """Signals are still sorted by EV descending after Kelly sizing."""
        brackets = [
            BracketProbability(bracket_label="53-54F", probability=0.10),
            BracketProbability(bracket_label="55-56F", probability=0.10),
            BracketProbability(bracket_label="57-58F", probability=0.50),
            BracketProbability(bracket_label="59-60F", probability=0.10),
            BracketProbability(bracket_label="<=52F", probability=0.10),
            BracketProbability(bracket_label=">=61F", probability=0.10),
        ]
        prediction = BracketPrediction(
            city="NYC",
            date=date(2026, 2, 18),
            brackets=brackets,
            ensemble_mean_f=55.0,
            ensemble_std_f=2.0,
            confidence="medium",
            model_sources=["NWS"],
            generated_at=datetime.now(UTC),
        )
        market_prices = {
            "53-54F": 5,
            "55-56F": 5,
            "57-58F": 22,
            "59-60F": 5,
            "<=52F": 5,
            ">=61F": 5,
        }
        market_tickers = {
            "53-54F": "T1",
            "55-56F": "T2",
            "57-58F": "T3",
            "59-60F": "T4",
            "<=52F": "T5",
            ">=61F": "T6",
        }
        settings = KellySettings(use_kelly_sizing=True, kelly_fraction=0.25)
        signals = scan_all_brackets(
            prediction,
            market_prices,
            market_tickers,
            0.01,
            kelly_settings=settings,
            bankroll_cents=50_000,
            max_trade_size_cents=5000,
        )
        if len(signals) > 1:
            for i in range(len(signals) - 1):
                assert signals[i].ev >= signals[i + 1].ev
