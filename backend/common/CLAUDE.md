# Backend Common — Shared Foundation

## Overview

This module contains everything shared across all backend agents: Pydantic schemas (the interface contracts), database models, logging setup, configuration, and custom exceptions. This is built BEFORE the agents start, and agents import from here — never from each other.

## What Lives Here

```
backend/common/
├── __init__.py
├── schemas.py        → Pydantic models for ALL cross-module data (THE interface contracts)
├── database.py       → SQLAlchemy async engine, session factory, base model
├── models.py         → SQLAlchemy ORM models (all database tables)
├── logging.py        → Structured logging setup with module tags
├── config.py         → App settings via pydantic-settings (reads .env)
└── exceptions.py     → Base exception classes shared across modules
```

## schemas.py — Interface Contracts

This is the most important file in the project. It defines the data shapes that flow between modules. Agents must use these types — not ad-hoc dicts or custom classes.

### Key Schemas:

```python
# Weather Data (Agent 1 → Agent 3)
class WeatherData(BaseModel):
    city: Literal["NYC", "CHI", "MIA", "AUS"]
    date: date
    forecast_high_f: float
    source: str                    # "NWS", "Open-Meteo:GFS", "Open-Meteo:ECMWF", etc.
    model_run_timestamp: datetime
    variables: WeatherVariables    # temp, humidity, wind, cloud cover, etc.
    raw_data: dict                 # full raw API response
    fetched_at: datetime

class WeatherVariables(BaseModel):
    temp_high_f: float
    temp_low_f: float | None
    humidity_pct: float | None
    wind_speed_mph: float | None
    wind_gust_mph: float | None
    cloud_cover_pct: float | None
    dew_point_f: float | None
    pressure_mb: float | None

# Bracket Prediction (Agent 3 → Agent 4)
class BracketProbability(BaseModel):
    bracket_label: str             # e.g., "53-54°F"
    lower_bound_f: float | None    # None for bottom edge bracket
    upper_bound_f: float | None    # None for top edge bracket
    probability: float             # 0.0 to 1.0

class BracketPrediction(BaseModel):
    city: str
    date: date
    brackets: list[BracketProbability]  # 6 items, probabilities sum to 1.0
    ensemble_forecast_f: float
    confidence: Literal["HIGH", "MEDIUM", "LOW"]
    model_sources: list[str]
    forecast_spread_f: float
    error_std_f: float
    generated_at: datetime

# Trade Signal (Agent 4 internal + queue)
class TradeSignal(BaseModel):
    city: str
    bracket: BracketProbability
    side: Literal["yes", "no"]
    market_price: float
    model_probability: float
    ev: float
    confidence: str
    reasoning: str

# Trade Record (for post-mortem, Agent 4 → storage)
class TradeRecord(BaseModel):
    id: str
    city: str
    date: date
    bracket_label: str
    side: Literal["yes", "no"]
    entry_price: float
    quantity: int
    model_probability: float
    market_probability: float
    ev_at_entry: float
    confidence: str
    weather_forecasts: list[WeatherData]   # snapshots at time of trade
    prediction: BracketPrediction          # model output at time of trade
    status: Literal["OPEN", "WON", "LOST", "CANCELLED"]
    settlement_temp_f: float | None
    settlement_source: str | None
    pnl: float | None
    postmortem: str | None                 # generated narrative
    created_at: datetime
    settled_at: datetime | None

# User Settings
class UserSettings(BaseModel):
    trading_mode: Literal["auto", "manual"]
    max_trade_size: float          # dollars
    daily_loss_limit: float
    max_daily_exposure: float
    min_ev_threshold: float        # 0.0 to 1.0
    cooldown_per_loss_minutes: int
    consecutive_loss_limit: int
    cities: list[str]              # which cities to trade
```

## logging.py — Structured Logging

Provides a `get_logger(module_tag)` function that returns a logger configured for structured output:

```python
from backend.common.logging import get_logger

logger = get_logger("WEATHER")
logger.info("Fetched NWS forecast", extra={"city": "NYC", "high_f": 55})
```

Output format:
```
[2026-02-17 10:00:01] INFO  WEATHER  Fetched NWS forecast  {"city":"NYC","high_f":55}
```

## config.py — Application Settings

Uses pydantic-settings to read from environment variables / .env file:

```python
class Settings(BaseSettings):
    # Database
    database_url: str = "postgresql+asyncpg://user:pass@localhost:5432/boz"
    redis_url: str = "redis://localhost:6379/0"

    # Encryption
    encryption_key: str  # AES-256 key for API key storage

    # App
    environment: Literal["development", "production"] = "development"
    log_level: str = "INFO"

    # NWS
    nws_user_agent: str = "BozWeatherTrader/1.0"

    class Config:
        env_file = ".env"
```

## Rules for Agents

1. **Import from here, not from each other.** If Agent 4 needs weather data types, import from `backend.common.schemas`, not from `backend.weather`.
2. **Don't modify schemas without coordination.** Schema changes affect multiple agents. If you need a new field, add it to schemas.py and note it as optional with a default so existing code doesn't break.
3. **Use the logger.** Every module should use `get_logger("MODULE_TAG")`. Don't use `print()`.
4. **Never log secrets.** The logger should have a filter that catches and redacts anything that looks like an API key or private key.
