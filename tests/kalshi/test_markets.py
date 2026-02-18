"""Tests for Kalshi market discovery, ticker mapping, and bracket parsing.

Verifies ticker constants, event ticker construction, bracket parsing
for edge and middle brackets, and the parse_event_markets aggregation.
"""

from __future__ import annotations

from datetime import date

import pytest

from backend.kalshi.markets import (
    SERIES_TO_CITY,
    WEATHER_SERIES_TICKERS,
    build_event_ticker,
    parse_bracket_from_market,
    parse_event_markets,
)
from backend.kalshi.models import KalshiMarket

# ─── Ticker Mapping Constants ───


class TestWeatherSeriesTickers:
    """Tests for WEATHER_SERIES_TICKERS and SERIES_TO_CITY mappings."""

    def test_has_4_entries(self) -> None:
        """WEATHER_SERIES_TICKERS has exactly 4 city entries."""
        assert len(WEATHER_SERIES_TICKERS) == 4

    def test_nyc_maps_to_kxhighny(self) -> None:
        """NYC maps to KXHIGHNY."""
        assert WEATHER_SERIES_TICKERS["NYC"] == "KXHIGHNY"

    def test_chi_maps_to_kxhighchi(self) -> None:
        """CHI maps to KXHIGHCHI."""
        assert WEATHER_SERIES_TICKERS["CHI"] == "KXHIGHCHI"

    def test_mia_maps_to_kxhighmia(self) -> None:
        """MIA maps to KXHIGHMIA."""
        assert WEATHER_SERIES_TICKERS["MIA"] == "KXHIGHMIA"

    def test_aus_maps_to_kxhighaus(self) -> None:
        """AUS maps to KXHIGHAUS."""
        assert WEATHER_SERIES_TICKERS["AUS"] == "KXHIGHAUS"

    def test_series_to_city_is_inverse_mapping(self) -> None:
        """SERIES_TO_CITY is the exact inverse of WEATHER_SERIES_TICKERS."""
        assert len(SERIES_TO_CITY) == len(WEATHER_SERIES_TICKERS)
        for city, series in WEATHER_SERIES_TICKERS.items():
            assert SERIES_TO_CITY[series] == city


# ─── Event Ticker Construction ───


class TestBuildEventTicker:
    """Tests for build_event_ticker function."""

    def test_nyc_feb_18_2026(self) -> None:
        """NYC + date(2026,2,18) produces 'KXHIGHNY-26FEB18'."""
        result = build_event_ticker("NYC", date(2026, 2, 18))
        assert result == "KXHIGHNY-26FEB18"

    def test_chi_mar_05_2026(self) -> None:
        """CHI + date(2026,3,5) produces 'KXHIGHCHI-26MAR05'."""
        result = build_event_ticker("CHI", date(2026, 3, 5))
        assert result == "KXHIGHCHI-26MAR05"

    def test_raises_for_unknown_city(self) -> None:
        """ValueError is raised for an unrecognized city code."""
        with pytest.raises(ValueError, match="Unknown city code"):
            build_event_ticker("LON", date(2026, 2, 18))


# ─── Bracket Parsing ───


class TestParseBracketFromMarket:
    """Tests for parse_bracket_from_market function."""

    def test_bottom_edge_bracket(self) -> None:
        """Bottom edge: floor=None, cap=47.99 produces 'Below 48F'."""
        market = {"floor_strike": None, "cap_strike": 47.99, "ticker": "T48"}
        result = parse_bracket_from_market(market)

        assert result["label"] == "Below 48F"
        assert result["lower_bound_f"] is None
        assert result["upper_bound_f"] == 47.99
        assert result["is_edge_lower"] is True
        assert result["is_edge_upper"] is False

    def test_top_edge_bracket(self) -> None:
        """Top edge: floor=58.0, cap=None produces '58F or above'."""
        market = {"floor_strike": 58.0, "cap_strike": None, "ticker": "T58"}
        result = parse_bracket_from_market(market)

        assert result["label"] == "58F or above"
        assert result["lower_bound_f"] == 58.0
        assert result["upper_bound_f"] is None
        assert result["is_edge_lower"] is False
        assert result["is_edge_upper"] is True

    def test_middle_bracket(self) -> None:
        """Middle: floor=52.0, cap=53.99 produces '52-54F'."""
        market = {"floor_strike": 52.0, "cap_strike": 53.99, "ticker": "T52"}
        result = parse_bracket_from_market(market)

        assert result["label"] == "52-54F"
        assert result["lower_bound_f"] == 52.0
        assert result["upper_bound_f"] == 53.99
        assert result["is_edge_lower"] is False
        assert result["is_edge_upper"] is False

    def test_both_none_produces_unknown(self) -> None:
        """Both floor and cap as None produces 'Unknown' label."""
        market = {"floor_strike": None, "cap_strike": None, "ticker": "TXXX"}
        result = parse_bracket_from_market(market)

        assert result["label"] == "Unknown"
        assert result["lower_bound_f"] is None
        assert result["upper_bound_f"] is None
        assert result["is_edge_lower"] is False
        assert result["is_edge_upper"] is False


# ─── Event Markets Parsing ───


class TestParseEventMarkets:
    """Tests for parse_event_markets function."""

    def _make_markets(self) -> list[KalshiMarket]:
        """Create a list of 4 KalshiMarket models for testing sort order."""
        return [
            # Middle bracket (out of order on purpose)
            KalshiMarket(
                ticker="KXHIGHNY-26FEB18-T54",
                event_ticker="KXHIGHNY-26FEB18",
                title="54-56F",
                status="active",
                floor_strike=54.0,
                cap_strike=55.99,
                yes_bid=15,
                yes_ask=18,
                volume=200,
            ),
            # Top edge
            KalshiMarket(
                ticker="KXHIGHNY-26FEB18-T58",
                event_ticker="KXHIGHNY-26FEB18",
                title="58F or above",
                status="active",
                floor_strike=58.0,
                cap_strike=None,
                yes_bid=10,
                yes_ask=14,
                volume=100,
            ),
            # Bottom edge
            KalshiMarket(
                ticker="KXHIGHNY-26FEB18-T48",
                event_ticker="KXHIGHNY-26FEB18",
                title="Below 48F",
                status="active",
                floor_strike=None,
                cap_strike=47.99,
                yes_bid=5,
                yes_ask=8,
                volume=50,
            ),
            # Middle bracket
            KalshiMarket(
                ticker="KXHIGHNY-26FEB18-T52",
                event_ticker="KXHIGHNY-26FEB18",
                title="52-54F",
                status="active",
                floor_strike=52.0,
                cap_strike=53.99,
                yes_bid=22,
                yes_ask=25,
                volume=1542,
            ),
        ]

    def test_sorts_brackets_correctly(self) -> None:
        """parse_event_markets sorts bottom edge first, top edge last."""
        markets = self._make_markets()
        brackets = parse_event_markets(markets)

        assert len(brackets) == 4
        # First bracket should be bottom edge
        assert brackets[0]["is_edge_lower"] is True
        assert brackets[0]["label"] == "Below 48F"
        # Last bracket should be top edge
        assert brackets[-1]["is_edge_upper"] is True
        assert brackets[-1]["label"] == "58F or above"
        # Middle brackets sorted by lower_bound_f
        assert brackets[1]["lower_bound_f"] == 52.0
        assert brackets[2]["lower_bound_f"] == 54.0

    def test_adds_pricing_data_from_market(self) -> None:
        """parse_event_markets includes pricing data (yes_bid, yes_ask, etc.)."""
        markets = self._make_markets()
        brackets = parse_event_markets(markets)

        # Check the bottom edge bracket
        bottom = brackets[0]
        assert bottom["yes_bid"] == 5
        assert bottom["yes_ask"] == 8
        assert bottom["volume"] == 50
        assert bottom["status"] == "active"

        # Check a middle bracket (52-54F)
        mid = brackets[1]
        assert mid["yes_bid"] == 22
        assert mid["yes_ask"] == 25
        assert mid["volume"] == 1542
        assert mid["last_price"] == 0  # default
