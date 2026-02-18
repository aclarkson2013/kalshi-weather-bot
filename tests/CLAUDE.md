# Tests — Conventions & Guidelines

## Overview

This directory contains all tests for Boz Weather Trader. Tests are organized to mirror the source code structure.

```
tests/
├── conftest.py          → Shared fixtures (database, mock clients, test data)
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

## Framework & Tools

- **pytest** — test runner
- **pytest-asyncio** — async test support
- **pytest-httpx** — mock HTTP requests (for NWS, Open-Meteo, Kalshi API)
- **pytest-cov** — coverage reporting
- **factory-boy** or **pytest fixtures** — test data generation
- **testcontainers** (optional) — spin up real PostgreSQL/Redis for integration tests

## Running Tests

```bash
# All tests
pytest

# Specific module
pytest tests/weather/
pytest tests/trading/

# Only safety tests
pytest tests/trading/test_safety.py

# With coverage
pytest --cov=backend --cov-report=html

# Only integration tests (requires Docker)
pytest tests/integration/ --integration
```

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
- Root `conftest.py` has database setup, common test data
- Module `conftest.py` has module-specific mocks and fixtures
- Use `@pytest.fixture` decorators, not setup/teardown methods

### Mocking External APIs
- ALWAYS mock NWS, Open-Meteo, and Kalshi APIs — never hit real endpoints
- Use `pytest-httpx` for mocking HTTP calls
- Store sample API responses in `tests/fixtures/` as JSON files
- Example fixture files:
  - `tests/fixtures/nws_forecast_nyc.json`
  - `tests/fixtures/openmeteo_forecast_nyc.json`
  - `tests/fixtures/kalshi_event_kxhighny.json`
  - `tests/fixtures/kalshi_orderbook.json`

### Database Tests
- Integration tests use a separate test database (not production)
- Use transactions that roll back after each test (clean state)
- For unit tests, mock the database layer entirely

### Safety Tests (tests/trading/test_safety.py)
These are the most critical tests in the entire project. They verify:
1. Risk limits cannot be bypassed under any circumstances
2. API keys never appear in logs, errors, or responses
3. Stale data triggers a trading pause
4. Network failures are handled gracefully
5. Concurrent operations don't create race conditions
6. Invalid/garbage input from upstream modules is caught

Safety tests should be paranoid — test weird edge cases, boundary conditions, and adversarial inputs.

## Coverage Requirements

| Module | Minimum Coverage |
|--------|-----------------|
| backend/weather/ | 80% |
| backend/kalshi/ | 80% |
| backend/prediction/ | 85% (this is the brain — higher standard) |
| backend/trading/ | 90% (this touches real money — highest standard) |
| frontend/ | 70% |

## CI/CD Integration

Tests run automatically via GitHub Actions on every push/PR:
1. Lint check (ruff + ESLint)
2. Unit tests (all modules)
3. Integration tests (with Docker)
4. Safety tests
5. Coverage check (fail if below thresholds)

On merge to main:
6. Full simulation test (7 days of historical data replayed)
