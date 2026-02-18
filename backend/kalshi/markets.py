"""Market discovery, ticker mapping, and bracket parsing for Kalshi weather markets.

Kalshi weather markets are organized as:
  Series (e.g., KXHIGHNY) -> Events (e.g., KXHIGHNY-26FEB18) -> Markets/Brackets

Each event has 6 bracket markets. The middle 4 are typically 2 degrees F wide,
and the top/bottom brackets are catch-all edge brackets.

Usage:
    from backend.kalshi.markets import (
        WEATHER_SERIES_TICKERS,
        build_event_ticker,
        parse_bracket_from_market,
        parse_event_markets,
    )

    ticker = build_event_ticker("NYC", date(2026, 2, 18))
    # -> "KXHIGHNY-26FEB18"
"""

from __future__ import annotations

from datetime import date

from backend.common.logging import get_logger
from backend.kalshi.models import KalshiMarket

logger = get_logger("MARKET")


# ─── Ticker Mappings ───

# City code -> Kalshi series ticker for daily high temperature markets
WEATHER_SERIES_TICKERS: dict[str, str] = {
    "NYC": "KXHIGHNY",
    "CHI": "KXHIGHCHI",
    "MIA": "KXHIGHMIA",
    "AUS": "KXHIGHAUS",
}

# Reverse lookup: series ticker -> city code
SERIES_TO_CITY: dict[str, str] = {v: k for k, v in WEATHER_SERIES_TICKERS.items()}


# ─── Ticker Construction ───


def build_event_ticker(city: str, target_date: date) -> str:
    """Build a Kalshi event ticker for a city and date.

    The event ticker format is: {series_ticker}-{YY}{MON}{DD}
    where MON is the uppercase 3-letter month abbreviation.

    Args:
        city: City code (NYC, CHI, MIA, AUS).
        target_date: The date of the weather event.

    Returns:
        Event ticker string, e.g., "KXHIGHNY-26FEB18".

    Raises:
        ValueError: If city code is not recognized.

    Examples:
        >>> build_event_ticker("NYC", date(2026, 2, 18))
        'KXHIGHNY-26FEB18'
        >>> build_event_ticker("CHI", date(2026, 3, 5))
        'KXHIGHCHI-26MAR05'
    """
    series = WEATHER_SERIES_TICKERS.get(city.upper())
    if not series:
        msg = f"Unknown city code: '{city}'. Valid codes: {list(WEATHER_SERIES_TICKERS.keys())}"
        raise ValueError(msg)

    # Format: YY + uppercase 3-letter month + DD
    date_str = target_date.strftime("%y%b%d").upper()
    return f"{series}-{date_str}"


# ─── Bracket Parsing ───


def parse_bracket_from_market(market: dict) -> dict:
    """Parse bracket range from a Kalshi market data dict.

    Uses floor_strike and cap_strike to determine the bracket type:
    - Bottom edge: floor_strike is None -> "Below XF"
    - Top edge: cap_strike is None -> "XF or above"
    - Middle: both present -> "X-YF"

    Args:
        market: Dict from Kalshi market API response. Must contain
                "floor_strike" and "cap_strike" keys (values may be None).

    Returns:
        Dict with bracket metadata:
            label: Human-readable label (e.g., "52-54F", "Below 48F")
            lower_bound_f: Floor temp in Fahrenheit, or None for bottom edge
            upper_bound_f: Cap temp in Fahrenheit, or None for top edge
            is_edge_lower: True if this is the bottom catch-all bracket
            is_edge_upper: True if this is the top catch-all bracket
            ticker: Market ticker (if present in input)
    """
    floor = market.get("floor_strike")
    cap = market.get("cap_strike")
    ticker = market.get("ticker", "")

    if floor is None and cap is not None:
        # Bottom edge bracket: "Below X F"
        label = f"Below {int(cap + 0.01)}F"
        return {
            "label": label,
            "lower_bound_f": None,
            "upper_bound_f": cap,
            "is_edge_lower": True,
            "is_edge_upper": False,
            "ticker": ticker,
        }

    if cap is None and floor is not None:
        # Top edge bracket: "X F or above"
        label = f"{int(floor)}F or above"
        return {
            "label": label,
            "lower_bound_f": floor,
            "upper_bound_f": None,
            "is_edge_lower": False,
            "is_edge_upper": True,
            "ticker": ticker,
        }

    if floor is not None and cap is not None:
        # Middle bracket: "X-Y F" (typically 2 degrees wide)
        label = f"{int(floor)}-{int(cap + 0.01)}F"
        return {
            "label": label,
            "lower_bound_f": floor,
            "upper_bound_f": cap,
            "is_edge_lower": False,
            "is_edge_upper": False,
            "ticker": ticker,
        }

    # Both None — unusual, log a warning
    logger.warning(
        "Market has both floor_strike and cap_strike as None",
        extra={"data": {"ticker": ticker}},
    )
    return {
        "label": "Unknown",
        "lower_bound_f": None,
        "upper_bound_f": None,
        "is_edge_lower": False,
        "is_edge_upper": False,
        "ticker": ticker,
    }


def parse_event_markets(markets: list[KalshiMarket]) -> list[dict]:
    """Parse all bracket markets for an event into structured bracket dicts.

    Converts a list of KalshiMarket models into a sorted list of bracket
    metadata dicts, ordered from lowest to highest temperature range.

    Args:
        markets: List of KalshiMarket models for a single event.

    Returns:
        List of bracket dicts (from parse_bracket_from_market), sorted by
        lower_bound_f (with bottom edge bracket first, top edge last).
    """
    brackets = []
    for market in markets:
        market_dict = {
            "floor_strike": market.floor_strike,
            "cap_strike": market.cap_strike,
            "ticker": market.ticker,
        }
        bracket = parse_bracket_from_market(market_dict)

        # Add pricing data from the market model
        bracket["yes_bid"] = market.yes_bid
        bracket["yes_ask"] = market.yes_ask
        bracket["no_bid"] = market.no_bid
        bracket["no_ask"] = market.no_ask
        bracket["last_price"] = market.last_price
        bracket["volume"] = market.volume
        bracket["status"] = market.status

        brackets.append(bracket)

    # Sort: bottom edge first, then by lower_bound_f, top edge last
    def sort_key(b: dict) -> float:
        if b["is_edge_lower"]:
            return float("-inf")
        if b["is_edge_upper"]:
            return float("inf")
        return b["lower_bound_f"] or 0.0

    brackets.sort(key=sort_key)

    logger.info(
        "Parsed event brackets",
        extra={
            "data": {
                "count": len(brackets),
                "labels": [b["label"] for b in brackets],
            }
        },
    )

    return brackets
