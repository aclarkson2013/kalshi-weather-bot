# Backend — Python Conventions

## Overview

The backend is a Python FastAPI application. All backend modules live under `backend/`. Shared code (schemas, config, database, logging) lives in `backend/common/`.

## Python Standards

- **Version:** Python 3.11+
- **Package Manager:** pip with `requirements.txt` (or Poetry if preferred)
- **Linter/Formatter:** ruff (replaces black, isort, flake8)
- **Type Checking:** All functions must have type hints. Use `from __future__ import annotations` at top of every file.
- **Docstrings:** Google style docstrings on all public functions and classes.

## Project Structure

```
backend/
├── main.py              → FastAPI app entry point, router registration
├── config.py            → Settings via pydantic-settings (reads .env)
├── common/
│   ├── schemas.py       → Pydantic models for ALL cross-module data
│   ├── database.py      → SQLAlchemy setup, session management
│   ├── models.py        → SQLAlchemy ORM models (database tables)
│   ├── logging.py       → Structured logging setup
│   └── exceptions.py    → Custom exception classes
├── weather/             → Agent 1: Weather data pipeline
├── kalshi/              → Agent 2: Kalshi API client
├── prediction/          → Agent 3: Prediction engine
└── trading/             → Agent 4: Trading engine
```

## Key Conventions

### Pydantic Schemas (backend/common/schemas.py)
- ALL data that crosses module boundaries must be a Pydantic model
- Agents should NOT import classes from other agent modules directly
- Use schema validation to catch data issues at module boundaries

### Database
- SQLAlchemy 2.0+ with async support
- Alembic for migrations
- All database models in `backend/common/models.py`
- Use async sessions for all database operations

### API Endpoints
- FastAPI routers, one per domain (weather, trading, settings, etc.)
- All endpoints return Pydantic models (auto-generates OpenAPI spec)
- Use dependency injection for database sessions, auth, etc.
- Meaningful HTTP status codes (don't just return 200 for everything)

### Async
- Use `async/await` for all I/O operations (HTTP calls, database, WebSocket)
- Use `httpx` for async HTTP client (not `requests`)
- Celery tasks for scheduled work (data fetching, model runs, trade execution)

### Error Handling
- Custom exceptions in `backend/common/exceptions.py`
- FastAPI exception handlers for consistent error responses
- All external API calls wrapped in try/except with retry logic
- Log errors with full context (but NEVER log secrets)

### Testing
- Framework: pytest + pytest-asyncio + pytest-httpx
- Fixtures in `conftest.py` at each test directory level
- Mock all external APIs using `pytest-httpx` or `unittest.mock`
- Database tests use a test database (separate from production)
- Every public function needs at least one test
- Test file naming: `test_{module_name}.py`

### Logging
- Import logger from `backend.common.logging`
- Every module gets its own logger with a module tag
- Example: `logger = get_logger("WEATHER")`
- Log structured data as a dict in the extra parameter
