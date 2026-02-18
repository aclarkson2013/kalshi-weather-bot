# Tests — Conventions & Guidelines

## Overview

This directory contains all tests for Boz Weather Trader. Tests are organized to mirror the source code structure. Every module ships with tests — no code is complete without them. External APIs (NWS, Open-Meteo, Kalshi) are ALWAYS mocked. Safety tests are the most critical tests in the entire project: they protect real money.

```
tests/
├── conftest.py          → Shared fixtures (database, mock clients, test data)
├── factories.py         → Test data factories for generating realistic test data
├── fixtures/            → Mock API response JSON files
│   ├── nws_points_nyc.json
│   ├── nws_forecast_nyc.json
│   ├── openmeteo_forecast_nyc.json
│   ├── kalshi_event_kxhighny.json
│   ├── kalshi_orderbook.json
│   ├── kalshi_order_response.json
│   └── nws_cli_nyc.json
├── weather/             → Unit tests for backend/weather/
│   ├── conftest.py      → Weather-specific fixtures (mock NWS/Open-Meteo responses)
│   ├── test_nws.py
│   ├── test_openmeteo.py
│   ├── test_normalizer.py
│   ├── test_stations.py
│   └── test_scheduler.py
├── kalshi/              → Unit tests for backend/kalshi/
│   ├── conftest.py      → Kalshi-specific fixtures (mock API responses, test keys)
│   ├── test_auth.py
│   ├── test_client.py
│   ├── test_markets.py
│   ├── test_orders.py
│   ├── test_websocket.py
│   └── test_rate_limiter.py
├── prediction/          → Unit tests for backend/prediction/
│   ├── conftest.py      → Prediction fixtures (sample weather data, bracket configs)
│   ├── test_ensemble.py
│   ├── test_brackets.py
│   ├── test_error_dist.py
│   ├── test_calibration.py
│   └── test_postmortem.py
├── trading/             → Unit tests + safety tests for backend/trading/
│   ├── conftest.py      → Trading fixtures (mock Kalshi client, sample predictions)
│   ├── test_ev_calculator.py
│   ├── test_risk_manager.py
│   ├── test_cooldown.py
│   ├── test_trade_queue.py
│   ├── test_executor.py
│   ├── test_postmortem.py
│   └── test_safety.py   → CRITICAL: safety tests (risk limits, key security, etc.)
└── integration/         → Cross-module integration tests
    ├── conftest.py      → Integration fixtures (Docker test DB, full pipeline setup)
    ├── test_weather_to_prediction.py
    ├── test_prediction_to_trading.py
    ├── test_trading_to_kalshi.py
    ├── test_risk_controls_e2e.py
    └── test_simulation.py  → Full pipeline replay with historical data
```

---

## Framework & Tools

- **pytest** — test runner
- **pytest-asyncio** — async test support (use `asyncio_mode = "auto"` in config)
- **pytest-httpx** — mock HTTP requests (for NWS, Open-Meteo, Kalshi API)
- **pytest-cov** — coverage reporting
- **pytest fixtures** + **test data factories** — test data generation
- **testcontainers** (optional) — spin up real PostgreSQL/Redis for integration tests

---

## Running Tests

```bash
# All tests
pytest

# Specific module
pytest tests/weather/
pytest tests/trading/

# Only safety tests (THE MOST IMPORTANT TESTS)
pytest tests/trading/test_safety.py -v

# With coverage
pytest --cov=backend --cov-report=html

# Only integration tests (requires Docker)
pytest tests/integration/ --integration

# Exclude integration tests (fast local run)
pytest -m "not integration"

# Run with verbose output and stop on first failure
pytest -vx
```

---

## Test Conventions

### Naming
- Test files: `test_{module}.py`
- Test functions: `test_{what_it_tests}` or `test_{scenario}_{expected_result}`
- Example: `test_ev_calculation_positive_edge()`, `test_risk_limit_blocks_trade_at_max()`

### Structure (Arrange-Act-Assert)
```python
def test_ev_calculation_positive_edge():
    # Arrange
    model_prob = 0.28
    market_price = 0.22
    fees = 0.01

    # Act
    ev = calculate_ev(model_prob, market_price, fees)

    # Assert
    assert ev == pytest.approx(0.05, abs=0.001)
```

### Fixtures
- Shared fixtures in `conftest.py` at each directory level
- Root `conftest.py` has database setup, common test data, and safe test settings
- Module `conftest.py` has module-specific mocks and fixtures
- Use `@pytest.fixture` decorators, not setup/teardown methods

### Mocking External APIs
- ALWAYS mock NWS, Open-Meteo, and Kalshi APIs — never hit real endpoints
- Use `pytest-httpx` for mocking HTTP calls (not `responses` or `aioresponses`)
- Store sample API responses in `tests/fixtures/` as JSON files
- See the "pytest-httpx Mocking Examples" section below for full patterns

### Database Tests
- All database tests use async SQLAlchemy 2.0
- Integration tests use a separate test database (not production)
- Use transaction rollback per test for clean state (see "Database Transaction Rollback Pattern" below)
- For unit tests, mock the database layer entirely

---

## pytest Configuration

Add this to your `pyproject.toml` so all test tooling is configured in one place:

```toml
# pyproject.toml (test section)
[tool.pytest.ini_options]
testpaths = ["tests"]
asyncio_mode = "auto"
markers = [
    "integration: marks tests requiring Docker services (deselect with '-m \"not integration\"')",
    "safety: marks critical safety tests that protect real money",
]
filterwarnings = [
    "ignore::DeprecationWarning",
]

[tool.coverage.run]
source = ["backend"]
omit = ["tests/*", "*/migrations/*"]

[tool.coverage.report]
show_missing = true
fail_under = 80
```

---

## Root conftest.py Implementation

This is the most important test infrastructure file. It provides the database engine, session fixtures, safe test settings, and sample data used by every test module.

```python
# tests/conftest.py
"""Root test configuration — shared fixtures for all test modules."""

import asyncio
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from backend.common.models import Base
from backend.common.config import Settings

# ─── Async Event Loop ───
@pytest.fixture(scope="session")
def event_loop():
    """Create a single event loop for the entire test session."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()

# ─── Test Database ───
TEST_DB_URL = "sqlite+aiosqlite:///test.db"  # In-memory alternative: "sqlite+aiosqlite://"

@pytest_asyncio.fixture(scope="session")
async def engine():
    """Create test database engine (session-scoped — created once)."""
    engine = create_async_engine(TEST_DB_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()

@pytest_asyncio.fixture
async def db(engine):
    """Create a fresh database session per test, with automatic rollback."""
    async with AsyncSession(engine, expire_on_commit=False) as session:
        async with session.begin():
            yield session
            await session.rollback()  # Clean state after each test

# ─── Test Settings ───
@pytest.fixture
def test_settings() -> Settings:
    """Create safe test settings (small limits, no real keys)."""
    return Settings(
        kalshi_key_id="test-key-id-not-real",
        kalshi_private_key_path="tests/fixtures/test_key.pem",
        database_url=TEST_DB_URL,
        redis_url="redis://localhost:6379/1",  # Use DB 1 for tests
        max_trade_size_cents=100,      # $1 max
        daily_loss_limit_cents=500,    # $5 max
        max_daily_exposure_cents=1000, # $10 max
        min_ev_threshold=0.05,         # 5%
        cooldown_per_loss_minutes=60,
        consecutive_loss_limit=3,
        trading_mode="manual",         # Never auto-trade in tests!
        active_cities=["NYC", "CHI"],
        encryption_key="dGVzdC1lbmNyeXB0aW9uLWtleS0zMi1ieXRlcw==",  # test key
    )

# ─── Sample Data Fixtures ───
@pytest.fixture
def sample_bracket_prediction():
    """A realistic BracketPrediction for NYC."""
    from backend.common.schemas import BracketPrediction, BracketProbability
    from datetime import date, datetime

    return BracketPrediction(
        city="NYC",
        date=date(2025, 2, 15),
        brackets=[
            BracketProbability(bracket_label="<=52F", lower_bound_f=float('-inf'), upper_bound_f=52, probability=0.08),
            BracketProbability(bracket_label="53-54F", lower_bound_f=53, upper_bound_f=54, probability=0.15),
            BracketProbability(bracket_label="55-56F", lower_bound_f=55, upper_bound_f=56, probability=0.30),
            BracketProbability(bracket_label="57-58F", lower_bound_f=57, upper_bound_f=58, probability=0.28),
            BracketProbability(bracket_label="59-60F", lower_bound_f=59, upper_bound_f=60, probability=0.12),
            BracketProbability(bracket_label=">=61F", lower_bound_f=61, upper_bound_f=float('inf'), probability=0.07),
        ],
        ensemble_mean_f=56.3,
        ensemble_std_f=2.1,
        confidence="medium",
        generated_at=datetime(2025, 2, 14, 15, 0, 0),
        model_sources=["NWS", "GFS", "ECMWF", "ICON"],
    )

@pytest.fixture
def sample_trade_signal():
    """A realistic TradeSignal for a +EV trade."""
    from backend.common.schemas import TradeSignal

    return TradeSignal(
        city="NYC",
        bracket="55-56F",
        side="yes",
        price_cents=22,
        quantity=1,
        model_probability=0.30,
        market_probability=0.22,
        ev=0.05,
        confidence="medium",
        market_ticker="KXHIGHNY-25FEB15-B3",
    )
```

### Key Design Decisions

- **`event_loop` is session-scoped** so all async fixtures share one loop. Without this, pytest-asyncio creates a new loop per test and session-scoped async fixtures break.
- **`engine` is session-scoped** so the test database is created once and shared. Table creation/destruction happens once per test run, not per test.
- **`db` is function-scoped** and rolls back after each test. Tests can insert, update, and delete freely without polluting other tests.
- **`test_settings` uses small dollar limits** so even if test code accidentally reaches a real API, the damage is capped at $1 per trade and $5 per day.
- **`trading_mode="manual"`** ensures no test can accidentally trigger automatic trading.

---

## Database Transaction Rollback Pattern

Every test gets a clean database via transaction rollback. This is the preferred pattern over truncating tables or recreating the schema per test — it is faster and guarantees isolation.

```python
# Advanced rollback pattern using nested transactions (savepoints).
# Use this if you need the session to support commits within the test
# (e.g., testing code that calls session.commit() internally).

@pytest_asyncio.fixture
async def db(engine):
    """Fresh DB session per test — auto-rolls back via savepoint."""
    connection = await engine.connect()
    transaction = await connection.begin()
    session = AsyncSession(bind=connection, expire_on_commit=False)

    yield session

    await session.close()
    await transaction.rollback()
    await connection.close()
```

This means tests can insert data freely — it is all cleaned up automatically. No manual teardown needed.

### When to Use Which Pattern

| Pattern | Use Case |
|---------|----------|
| Simple rollback (`session.begin()` + `session.rollback()`) | Tests that do NOT call `session.commit()` internally |
| Savepoint rollback (nested transaction via `connection.begin()`) | Tests where the code-under-test calls `session.commit()` |

---

## pytest-httpx Mocking Examples

All HTTP mocking uses `pytest-httpx`. This is the project standard — do NOT use `responses`, `aioresponses`, or `unittest.mock.patch` for HTTP calls.

### Weather-Specific Fixtures

```python
# tests/weather/conftest.py
"""Weather-specific fixtures with mock API responses."""

import json
import pytest
from pathlib import Path

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"

@pytest.fixture
def mock_nws_points(httpx_mock):
    """Mock NWS /points endpoint for NYC (Central Park)."""
    with open(FIXTURES_DIR / "nws_points_nyc.json") as f:
        response_data = json.load(f)

    httpx_mock.add_response(
        url="https://api.weather.gov/points/40.7831,-73.9712",
        json=response_data,
        headers={"Content-Type": "application/geo+json"},
    )
    return httpx_mock

@pytest.fixture
def mock_nws_forecast(httpx_mock):
    """Mock NWS forecast endpoint for NYC grid."""
    with open(FIXTURES_DIR / "nws_forecast_nyc.json") as f:
        response_data = json.load(f)

    httpx_mock.add_response(
        url="https://api.weather.gov/gridpoints/OKX/33,37/forecast",
        json=response_data,
    )
    return httpx_mock

@pytest.fixture
def mock_openmeteo(httpx_mock):
    """Mock Open-Meteo API response with multiple models."""
    with open(FIXTURES_DIR / "openmeteo_forecast_nyc.json") as f:
        response_data = json.load(f)

    httpx_mock.add_response(
        url__startswith="https://api.open-meteo.com/v1/forecast",
        json=response_data,
    )
    return httpx_mock
```

### Using Mocks in Tests

```python
# tests/weather/test_nws.py

import pytest

@pytest.mark.asyncio
async def test_fetch_nws_forecast(mock_nws_points, mock_nws_forecast):
    """Test that NWS forecast fetching works with mocked responses."""
    from backend.weather.nws import NWSClient

    client = NWSClient()
    forecast = await client.fetch_forecast("NYC")

    assert forecast.city == "NYC"
    assert forecast.forecast_high_f > 0
    assert forecast.source == "NWS"
```

### Mocking Error Responses

```python
# tests/weather/conftest.py (continued)

@pytest.fixture
def mock_nws_503(httpx_mock):
    """Simulate NWS API being down (503 Service Unavailable)."""
    httpx_mock.add_response(
        url__startswith="https://api.weather.gov/",
        status_code=503,
        json={"detail": "Service Unavailable"},
    )
    return httpx_mock

# tests/weather/test_nws.py (continued)

@pytest.mark.asyncio
async def test_nws_handles_503_gracefully(mock_nws_503):
    """Test that NWS client retries and raises appropriate error."""
    from backend.weather.nws import NWSClient
    from backend.common.exceptions import FetchError

    client = NWSClient()
    with pytest.raises(FetchError):
        await client.fetch_forecast("NYC")
```

### pytest-httpx Tips

| Feature | Syntax |
|---------|--------|
| Exact URL match | `url="https://..."` |
| URL prefix match | `url__startswith="https://api.weather.gov/"` |
| Set response status | `status_code=503` |
| Return JSON body | `json={"key": "value"}` |
| Set response headers | `headers={"Content-Type": "application/json"}` |
| Raise connection error | `httpx_mock.add_exception(httpx.ConnectError("Connection refused"))` |
| Multiple sequential responses | Call `add_response()` multiple times — they are returned in order |

---

## Async Testing Patterns

All async tests use `pytest-asyncio`. With `asyncio_mode = "auto"` in pyproject.toml, you do not need `@pytest.mark.asyncio` on every test — but including it is fine and makes intent explicit.

### Basic Async Test

```python
import pytest

@pytest.mark.asyncio
async def test_async_function():
    """Basic async test pattern."""
    result = await some_async_function()
    assert result is not None
```

### Testing with Time Mocking (Cooldowns, Staleness)

```python
@pytest.mark.asyncio
async def test_cooldown_expires():
    """Test that cooldown expires after the configured time."""
    from unittest.mock import patch
    from datetime import datetime, timedelta
    from backend.trading.cooldown import CooldownManager

    manager = CooldownManager(cooldown_minutes=60)

    # Activate cooldown
    manager.activate_per_loss()
    assert manager.is_active() is True

    # Fast-forward time by 61 minutes
    future_time = datetime.now() + timedelta(minutes=61)
    with patch('backend.trading.cooldown.datetime') as mock_dt:
        mock_dt.now.return_value = future_time
        mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
        assert manager.is_active() is False
```

### Testing with Mock Database Session

```python
@pytest.mark.asyncio
async def test_risk_manager_blocks_at_limit(db, test_settings):
    """Test that risk manager blocks trades at daily loss limit."""
    from backend.trading.risk_manager import RiskManager
    from backend.common.schemas import TradeSignal

    manager = RiskManager(settings=test_settings, db=db)

    # Simulate hitting the daily loss limit
    # ... add losing trades to DB totaling $5 (the test limit)

    signal = TradeSignal(...)  # A new trade
    allowed, reason = await manager.check_trade(signal)

    assert allowed is False
    assert "daily loss limit" in reason.lower()
```

### Testing Concurrent Operations

```python
@pytest.mark.asyncio
async def test_concurrent_operations_are_safe():
    """Test that concurrent calls don't cause race conditions."""
    import asyncio

    results = await asyncio.gather(
        operation_one(),
        operation_two(),
        operation_three(),
    )

    # Assert invariants that should hold regardless of execution order
    assert all(r.is_valid for r in results)
```

---

## Kalshi API Mocking

Kalshi API calls are mocked with `unittest.mock.AsyncMock` (for the client object) and `pytest-httpx` (for raw HTTP calls). Never hit the real Kalshi API in tests.

```python
# tests/kalshi/conftest.py
"""Kalshi-specific fixtures."""

import pytest
from unittest.mock import AsyncMock, MagicMock

@pytest.fixture
def mock_kalshi_client():
    """Create a fully mocked Kalshi client."""
    client = AsyncMock()

    # Mock get_event
    client.get_event.return_value = {
        "event": {
            "event_ticker": "KXHIGHNY-25FEB15",
            "title": "High Temperature in NYC on Feb 15",
            "status": "open",
            "markets": [
                {
                    "ticker": "KXHIGHNY-25FEB15-B1",
                    "floor_strike": None,
                    "cap_strike": 52,
                    "yes_ask": 8,
                    "no_ask": 94,
                },
                {
                    "ticker": "KXHIGHNY-25FEB15-B2",
                    "floor_strike": 53,
                    "cap_strike": 54,
                    "yes_ask": 15,
                    "no_ask": 87,
                },
                # ... more brackets
            ],
        }
    }

    # Mock create_order (successful)
    client.create_order.return_value = {
        "order": {
            "order_id": "ord-test-123",
            "ticker": "KXHIGHNY-25FEB15-B3",
            "action": "buy",
            "side": "yes",
            "type": "limit",
            "yes_price": 22,
            "count": 1,
            "status": "executed",
            "remaining_count": 0,
        }
    }

    # Mock create_order (rejected)
    client.create_order_rejected = AsyncMock(
        side_effect=Exception("Insufficient balance")
    )

    return client

@pytest.fixture
def test_rsa_private_key():
    """Generate a test RSA private key (NEVER use in production!)."""
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.hazmat.primitives import serialization

    private_key = rsa.generate_private_key(
        public_exponent=65537, key_size=2048
    )
    pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    return pem.decode()
```

### Usage in Tests

```python
# tests/kalshi/test_orders.py

@pytest.mark.asyncio
async def test_place_order_success(mock_kalshi_client):
    """Test that a valid order is placed successfully."""
    result = await mock_kalshi_client.create_order(
        ticker="KXHIGHNY-25FEB15-B3",
        action="buy",
        side="yes",
        type="limit",
        yes_price=22,
        count=1,
    )

    assert result["order"]["status"] == "executed"
    assert result["order"]["order_id"] == "ord-test-123"

@pytest.mark.asyncio
async def test_auth_header_uses_rsa_signature(test_rsa_private_key):
    """Test that auth creates a valid RSA-signed header."""
    from backend.kalshi.auth import create_auth_headers

    headers = create_auth_headers(
        key_id="test-key-id",
        private_key_pem=test_rsa_private_key,
        method="POST",
        path="/trade-api/v2/portfolio/orders",
    )

    assert "Authorization" in headers
    assert headers["Authorization"].startswith("Bearer ")
```

---

## Trading Safety Tests

These are the most critical tests in the entire project. They protect real money. Safety tests MUST pass before any code is merged. They test adversarial inputs, boundary conditions, and race conditions.

```python
# tests/trading/test_safety.py
"""
CRITICAL SAFETY TESTS — These protect real money.
These tests MUST pass before any code is merged.
Test adversarial inputs, boundary conditions, and race conditions.
"""

import pytest
import math
import asyncio
from unittest.mock import AsyncMock, patch
from backend.common.schemas import BracketPrediction, BracketProbability, TradeSignal


class TestRiskLimitsCannotBeBypassed:
    """Test that risk limits hold under all conditions."""

    @pytest.mark.asyncio
    async def test_max_trade_size_enforced(self, db, test_settings):
        """Trade larger than max_trade_size is ALWAYS blocked."""
        from backend.trading.risk_manager import RiskManager
        manager = RiskManager(test_settings, db)

        oversized_signal = TradeSignal(
            price_cents=200, quantity=1, ...  # $2 > $1 max
        )
        allowed, reason = await manager.check_trade(oversized_signal)
        assert allowed is False

    @pytest.mark.asyncio
    async def test_daily_loss_limit_stops_all_trading(self, db, test_settings):
        """Once daily loss is hit, ALL trades are blocked — even +EV ones."""
        ...

    @pytest.mark.asyncio
    async def test_exposure_limit_blocks_additional_trades(self, db, test_settings):
        """New trades are blocked when open exposure is at the limit."""
        ...

    @pytest.mark.asyncio
    async def test_risk_checks_atomic_no_race_condition(self, db, test_settings):
        """Concurrent trade signals cannot bypass exposure limit via race condition."""
        from backend.trading.risk_manager import RiskManager
        manager = RiskManager(test_settings, db)

        # Simulate two concurrent trades that together exceed the limit
        signal = TradeSignal(price_cents=60, quantity=1, ...)  # $0.60 each
        # Settings has max_daily_exposure_cents=1000 ($10)
        # Simulate existing exposure of $9.50
        # Both trades try to go through simultaneously

        results = await asyncio.gather(
            manager.check_trade(signal),
            manager.check_trade(signal),
        )

        # At most ONE should be allowed
        allowed_count = sum(1 for allowed, _ in results if allowed)
        assert allowed_count <= 1


class TestAPIKeySecurityInLogs:
    """Test that API keys NEVER leak into logs, errors, or responses."""

    def test_keys_redacted_in_log_output(self, caplog):
        """API key values must be replaced with [REDACTED] in all logs."""
        from backend.common.logging import get_logger
        logger = get_logger("TEST")

        test_key = "abc123-secret-key"
        logger.info("Auth attempt", extra={"data": {"key_id": test_key}})

        for record in caplog.records:
            assert test_key not in record.getMessage()

    def test_keys_not_in_exception_messages(self):
        """Exceptions must not contain key material."""
        ...


class TestGarbageInputHandling:
    """Test that upstream garbage data does not cause trades."""

    @pytest.mark.asyncio
    async def test_nan_probability_halts_trading(self):
        """NaN probabilities from prediction engine -> no trades."""
        from backend.trading.executor import validate_predictions

        bad_prediction = BracketPrediction(
            brackets=[
                BracketProbability(probability=float('nan'), ...)
            ],
            ...
        )
        assert validate_predictions([bad_prediction]) is False

    @pytest.mark.asyncio
    async def test_negative_probability_halts_trading(self):
        """Negative probabilities -> no trades."""
        ...

    @pytest.mark.asyncio
    async def test_probabilities_not_summing_to_one(self):
        """Bracket probabilities summing to 0.5 or 1.5 -> no trades."""
        ...

    @pytest.mark.asyncio
    async def test_stale_predictions_blocked(self):
        """Predictions older than 2 hours -> no trades."""
        ...


class TestNetworkFailureHandling:
    """Test graceful degradation when services are unreachable."""

    @pytest.mark.asyncio
    async def test_kalshi_unreachable_queues_trades(self):
        """If Kalshi API is down, trades queue for retry, do not crash."""
        ...

    @pytest.mark.asyncio
    async def test_database_unreachable_halts_trading(self):
        """If DB is down, trading halts completely (cannot check risk limits)."""
        ...
```

### Safety Test Checklist

Every safety test should be **paranoid**. When writing safety tests, cover:

1. **Boundary values** — test at exactly the limit, one cent below, one cent above
2. **Overflow/underflow** — what happens with `float('inf')`, `float('-inf')`, `float('nan')`
3. **Race conditions** — two signals arriving simultaneously
4. **Stale data** — predictions from 3 hours ago, market data from yesterday
5. **Garbage input** — negative prices, zero quantities, missing fields
6. **Key leakage** — grep all log output, error messages, and API responses for key material
7. **Mode enforcement** — `trading_mode="manual"` must block auto-execution

---

## Integration Test Patterns

Integration tests exercise the full pipeline from weather data to trade execution. They use mocked external APIs but real database sessions and real business logic.

```python
# tests/integration/conftest.py
"""Integration test fixtures — full pipeline with real-ish data."""

import pytest

# Mark all tests in this directory as integration tests
pytestmark = pytest.mark.integration

@pytest.fixture
def full_pipeline(db, mock_kalshi_client, test_settings):
    """Set up the complete pipeline for end-to-end tests."""
    return {
        "db": db,
        "kalshi": mock_kalshi_client,
        "settings": test_settings,
    }
```

### Integration Test Example

```python
# tests/integration/test_weather_to_prediction.py

import pytest

pytestmark = pytest.mark.integration

@pytest.mark.asyncio
async def test_weather_data_produces_valid_predictions(
    db, mock_nws_points, mock_nws_forecast, mock_openmeteo
):
    """End-to-end: fetch weather -> generate predictions -> validate output."""
    from backend.weather.nws import NWSClient
    from backend.prediction.ensemble import EnsemblePredictor

    # Fetch weather (mocked)
    nws = NWSClient()
    weather = await nws.fetch_forecast("NYC")

    # Generate predictions
    predictor = EnsemblePredictor()
    prediction = predictor.predict(weather_data=[weather])

    # Validate
    assert prediction.city == "NYC"
    assert len(prediction.brackets) == 6
    assert abs(sum(b.probability for b in prediction.brackets) - 1.0) < 0.01
    assert prediction.confidence in ("HIGH", "MEDIUM", "LOW")
```

### Running Integration Tests

```bash
# Integration tests are excluded by default (they are slower)
pytest -m "not integration"

# Run only integration tests
pytest tests/integration/ --integration

# Run everything including integration tests
pytest --integration
```

---

## Test Data Factories

Factories create realistic test data with sensible defaults. Use them when you need many variations of the same object or when fixtures are too rigid.

```python
# tests/factories.py
"""Test data factories for generating realistic test data."""

from backend.common.schemas import BracketProbability, BracketPrediction, TradeSignal
from datetime import date, datetime, timedelta
import random


def make_bracket_prediction(
    city: str = "NYC",
    target_date: date | None = None,
    mean_temp: float = 56.0,
    confidence: str = "medium",
    **overrides,
) -> BracketPrediction:
    """Create a realistic BracketPrediction with sensible defaults.

    Generates 6 brackets centered around mean_temp with a roughly
    Gaussian probability distribution.

    Args:
        city: City code (NYC, CHI, MIA, AUS).
        target_date: Date for the prediction. Defaults to tomorrow.
        mean_temp: Center of the temperature distribution in Fahrenheit.
        confidence: Prediction confidence level.
        **overrides: Override any field on the returned BracketPrediction.
    """
    if target_date is None:
        target_date = date.today() + timedelta(days=1)

    # Generate brackets centered on mean_temp
    base = int(mean_temp) - 3
    brackets = [
        BracketProbability(bracket_label=f"<={base}F", lower_bound_f=float('-inf'), upper_bound_f=base, probability=0.08),
        BracketProbability(bracket_label=f"{base+1}-{base+2}F", lower_bound_f=base+1, upper_bound_f=base+2, probability=0.15),
        BracketProbability(bracket_label=f"{base+3}-{base+4}F", lower_bound_f=base+3, upper_bound_f=base+4, probability=0.30),
        BracketProbability(bracket_label=f"{base+5}-{base+6}F", lower_bound_f=base+5, upper_bound_f=base+6, probability=0.28),
        BracketProbability(bracket_label=f"{base+7}-{base+8}F", lower_bound_f=base+7, upper_bound_f=base+8, probability=0.12),
        BracketProbability(bracket_label=f">={base+9}F", lower_bound_f=base+9, upper_bound_f=float('inf'), probability=0.07),
    ]

    data = dict(
        city=city,
        date=target_date,
        brackets=brackets,
        ensemble_mean_f=mean_temp,
        ensemble_std_f=2.1,
        confidence=confidence,
        generated_at=datetime.now(),
        model_sources=["NWS", "GFS", "ECMWF", "ICON"],
    )
    data.update(overrides)
    return BracketPrediction(**data)


def make_trade_signal(
    ev: float = 0.05,
    side: str = "yes",
    price_cents: int = 22,
    city: str = "NYC",
    **overrides,
) -> TradeSignal:
    """Create a TradeSignal with sensible defaults.

    Args:
        ev: Expected value (default 5%).
        side: "yes" or "no".
        price_cents: Market price in cents.
        city: City code.
        **overrides: Override any field on the returned TradeSignal.
    """
    data = dict(
        city=city,
        bracket="55-56F",
        side=side,
        price_cents=price_cents,
        quantity=1,
        model_probability=price_cents / 100.0 + ev,
        market_probability=price_cents / 100.0,
        ev=ev,
        confidence="medium",
        market_ticker=f"KXHIGH{city}-25FEB15-B3",
    )
    data.update(overrides)
    return TradeSignal(**data)
```

### Using Factories in Tests

```python
from tests.factories import make_bracket_prediction, make_trade_signal

def test_ev_calculator_with_various_spreads():
    """Test EV calculation across multiple probability spreads."""
    for ev in [0.01, 0.05, 0.10, 0.20]:
        signal = make_trade_signal(ev=ev, price_cents=30)
        assert signal.model_probability > signal.market_probability
        assert signal.ev == pytest.approx(ev)

def test_prediction_for_all_cities():
    """Test that predictions work for every supported city."""
    for city in ["NYC", "CHI", "MIA", "AUS"]:
        pred = make_bracket_prediction(city=city)
        assert pred.city == city
        assert len(pred.brackets) == 6
```

---

## Fixture File Format Reference

Store mock API responses as JSON in `tests/fixtures/`. These files represent realistic snapshots of external API responses and are loaded by module-specific conftest fixtures.

| File | Source API | Contents | Used By |
|------|-----------|----------|---------|
| `nws_points_nyc.json` | NWS `/points/{lat},{lon}` | Grid coordinates, forecast office, grid X/Y | `tests/weather/conftest.py` |
| `nws_forecast_nyc.json` | NWS `/gridpoints/{office}/{x},{y}/forecast` | Temperature periods (14 periods, day/night) | `tests/weather/conftest.py` |
| `openmeteo_forecast_nyc.json` | Open-Meteo `/v1/forecast` | Multi-model hourly temperatures (GFS, ECMWF, ICON) | `tests/weather/conftest.py` |
| `kalshi_event_kxhighny.json` | Kalshi `/trade-api/v2/events/{ticker}` | Event with 6 market brackets, prices, status | `tests/kalshi/conftest.py` |
| `kalshi_orderbook.json` | Kalshi `/trade-api/v2/orderbook/{ticker}` | Bid/ask arrays with price and quantity levels | `tests/kalshi/conftest.py` |
| `kalshi_order_response.json` | Kalshi `/trade-api/v2/portfolio/orders` | Order placement response (order_id, status, fill info) | `tests/kalshi/conftest.py` |
| `nws_cli_nyc.json` | NWS Daily Climate Report | Actual observed high temperature for settlement | `tests/trading/conftest.py` |

### Creating Fixture Files

1. Make a real API call (manually, via curl or httpx) and save the JSON response.
2. Scrub any sensitive data (API keys, user IDs) from the response.
3. Save with a descriptive filename in `tests/fixtures/`.
4. Add a corresponding `mock_*` fixture in the appropriate `conftest.py`.

Example:

```bash
# Fetch a real NWS response for NYC Central Park
curl -H "User-Agent: BozWeatherTrader/1.0" \
  "https://api.weather.gov/points/40.7831,-73.9712" \
  > tests/fixtures/nws_points_nyc.json
```

---

## CI/CD GitHub Actions Workflow

Tests run automatically via GitHub Actions on every push and PR. The workflow enforces linting, unit tests, integration tests, safety tests, and coverage thresholds.

```yaml
# .github/workflows/test.yml
name: Tests

on:
  push:
    branches: [main, develop]
  pull_request:
    branches: [main]

jobs:
  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      - run: pip install ruff
      - run: ruff check backend/ tests/
      - run: ruff format --check backend/ tests/

  backend-tests:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgres:16
        env:
          POSTGRES_USER: test
          POSTGRES_PASSWORD: test
          POSTGRES_DB: boz_test
        ports: ['5432:5432']
        options: >-
          --health-cmd pg_isready
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5
      redis:
        image: redis:7
        ports: ['6379:6379']

    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      - run: pip install -e ".[dev]"
      - name: Run unit tests
        run: pytest tests/ -m "not integration" --cov=backend --cov-report=xml
        env:
          DATABASE_URL: postgresql+asyncpg://test:test@localhost:5432/boz_test
          REDIS_URL: redis://localhost:6379/1
      - name: Run integration tests
        run: pytest tests/integration/ --integration
        env:
          DATABASE_URL: postgresql+asyncpg://test:test@localhost:5432/boz_test
          REDIS_URL: redis://localhost:6379/1
      - name: Run safety tests
        run: pytest tests/trading/test_safety.py -v
      - name: Check coverage thresholds
        run: |
          pytest --cov=backend/weather --cov-fail-under=80
          pytest --cov=backend/kalshi --cov-fail-under=80
          pytest --cov=backend/prediction --cov-fail-under=85
          pytest --cov=backend/trading --cov-fail-under=90

  frontend-tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: '20'
      - working-directory: frontend
        run: npm ci
      - working-directory: frontend
        run: npm run lint
      - working-directory: frontend
        run: npm test -- --coverage
```

### CI/CD Pipeline Summary

| Step | What It Does | Failure Blocks Merge? |
|------|--------------|-----------------------|
| Lint | `ruff check` + `ruff format --check` | Yes |
| Unit tests | All tests except `@pytest.mark.integration` | Yes |
| Integration tests | Full pipeline tests with Docker services | Yes |
| Safety tests | `tests/trading/test_safety.py` — risk limits, key security | Yes |
| Coverage check | Per-module thresholds (80-90%) | Yes |
| Frontend lint | ESLint | Yes |
| Frontend tests | Jest/Vitest with coverage | Yes |

On merge to main, an additional job runs:
- **Full simulation test** — 7 days of historical data replayed through the complete pipeline

---

## Coverage Requirements

| Module | Minimum Coverage | Rationale |
|--------|-----------------|-----------|
| `backend/weather/` | 80% | External API integration — mock-heavy |
| `backend/kalshi/` | 80% | External API integration — mock-heavy |
| `backend/prediction/` | 85% | This is the brain — higher standard |
| `backend/trading/` | 90% | This touches real money — highest standard |
| `frontend/` | 70% | UI code — visual testing supplements coverage |

---

## Build Checklist

Use this when setting up the test suite from scratch or verifying completeness:

1. Create `pyproject.toml` with pytest configuration (asyncio_mode, markers, coverage settings)
2. Create `tests/conftest.py` with database engine, session, settings, and sample data fixtures
3. Create `tests/factories.py` with test data factory functions
4. Create fixture JSON files in `tests/fixtures/` (mock API responses for NWS, Open-Meteo, Kalshi)
5. Create module-specific `conftest.py` files (`weather/`, `kalshi/`, `prediction/`, `trading/`)
6. Write unit tests for each module (following the naming and AAA pattern)
7. Write safety tests (`tests/trading/test_safety.py`) — THE MOST IMPORTANT TESTS
8. Write integration tests (`tests/integration/`)
9. Create `.github/workflows/test.yml` for CI/CD
10. Verify all coverage thresholds are met with `pytest --cov`

---

## Quick Reference: What to Mock and How

| External Dependency | Mock Tool | Example |
|-------------------|-----------|---------|
| NWS API (HTTP GET) | `pytest-httpx` | `httpx_mock.add_response(url="https://api.weather.gov/...", json={...})` |
| Open-Meteo API (HTTP GET) | `pytest-httpx` | `httpx_mock.add_response(url__startswith="https://api.open-meteo.com/", json={...})` |
| Kalshi REST API (HTTP POST) | `pytest-httpx` or `AsyncMock` | `mock_kalshi_client.create_order.return_value = {...}` |
| Kalshi WebSocket | `unittest.mock.AsyncMock` | Mock the WebSocket connection and message stream |
| PostgreSQL database | Transaction rollback fixture | `db` fixture auto-rolls back after each test |
| Redis cache | `fakeredis` or `unittest.mock` | Mock the Redis client or use fakeredis for integration |
| System clock | `unittest.mock.patch` | `patch('module.datetime')` to control time-dependent logic |
| File system (PEM keys) | `tmp_path` fixture + factory | Write test keys to `tmp_path` and point settings there |
