"""Weather-specific exceptions.

These are separate from backend.common.exceptions to keep the weather module
self-contained. The common module defines generic FetchError/ParseError for
cross-module use; these are weather-domain subclasses.
"""

from __future__ import annotations


class WeatherError(Exception):
    """Base exception for all weather module errors."""


class StaleDataError(WeatherError):
    """Raised when the newest forecast for a city is too old.

    Kalshi trading should pause when weather data exceeds the staleness
    threshold (120 minutes by default).
    """

    def __init__(self, city: str, age_minutes: float) -> None:
        self.city = city
        self.age_minutes = age_minutes
        super().__init__(
            f"Weather data for {city} is {age_minutes:.0f} minutes old (threshold: 120 minutes)"
        )


class FetchError(WeatherError):
    """Raised when an API fetch fails after all retries."""


class ParseError(WeatherError):
    """Raised when API response has unexpected structure."""
