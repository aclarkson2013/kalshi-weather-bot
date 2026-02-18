"""Kalshi-specific test fixtures — RSA keys, auth instances, sample API data.

Provides reusable fixtures for all tests in the tests/kalshi/ directory.
Generates a fresh RSA key pair for authentication tests and provides
sample market/event data matching the Kalshi API response format.
"""

from __future__ import annotations

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from backend.kalshi.auth import KalshiAuth


@pytest.fixture
def rsa_key_pair():
    """Generate a 2048-bit RSA key pair for testing.

    Returns a dict with:
        api_key_id: A test API key ID string.
        private_key_pem: The RSA private key in PEM format (str).
    """
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
    )
    pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    )
    return {
        "api_key_id": "test-key-12345678",
        "private_key_pem": pem.decode(),
    }


@pytest.fixture
def kalshi_auth(rsa_key_pair):
    """Create a KalshiAuth instance using the test RSA key pair."""
    return KalshiAuth(
        api_key_id=rsa_key_pair["api_key_id"],
        private_key_pem=rsa_key_pair["private_key_pem"],
    )


@pytest.fixture
def sample_market_data():
    """A dict representing a Kalshi market API response (middle bracket).

    Matches the shape returned by GET /trade-api/v2/markets/{ticker}.
    """
    return {
        "market": {
            "ticker": "KXHIGHNY-26FEB18-T52",
            "event_ticker": "KXHIGHNY-26FEB18",
            "title": "NYC high temp: 52F to 53F?",
            "subtitle": "Will the highest temperature be between 52F and 53F?",
            "status": "active",
            "yes_bid": 22,
            "yes_ask": 25,
            "no_bid": 74,
            "no_ask": 78,
            "last_price": 23,
            "volume": 1542,
            "open_interest": 823,
            "floor_strike": 52.0,
            "cap_strike": 53.99,
            "result": None,
            "close_time": "2026-02-18T23:00:00Z",
            "expiration_time": "2026-02-19T14:00:00Z",
        }
    }


@pytest.fixture
def sample_event_data():
    """A dict representing a Kalshi event API response.

    Matches the shape returned by GET /trade-api/v2/events/{event_ticker}.
    """
    return {
        "event": {
            "event_ticker": "KXHIGHNY-26FEB18",
            "series_ticker": "KXHIGHNY",
            "title": "Highest temperature in NYC on Feb 18?",
            "category": "Climate",
            "status": "active",
            "markets": [
                "KXHIGHNY-26FEB18-T48",
                "KXHIGHNY-26FEB18-T50",
                "KXHIGHNY-26FEB18-T52",
                "KXHIGHNY-26FEB18-T54",
                "KXHIGHNY-26FEB18-T56",
                "KXHIGHNY-26FEB18-T58",
            ],
        }
    }
