# Boz Weather Trader — Project Guide

## What This Project Is

Boz Weather Trader is a free, open-source automated trading bot for Kalshi weather prediction markets. It fetches weather forecast data from NWS and Open-Meteo, generates probability distributions for temperature outcomes, compares them to Kalshi market prices, and executes trades when it finds positive expected value (+EV).

**PRD:** See `PRD.md` for the full product requirements document (v0.5+).

## Architecture Overview

```
frontend/          → Next.js PWA (dashboard, onboarding, trade queue)
backend/
  ├── main.py      → FastAPI app entry point, /metrics endpoint, middleware stack
  ├── celery_app.py → Celery config, beat schedule, task signal instrumentation
  ├── weather/     → Agent 1: NWS + Open-Meteo data pipeline
  ├── kalshi/      → Agent 2: Kalshi API client (auth, orders, markets)
  ├── prediction/  → Agent 3: Statistical ensemble + bracket probabilities
  ├── trading/     → Agent 4: EV calculator, risk controls, trade queue
  └── common/      → Shared schemas, config, database, logging, middleware, metrics
tests/
  ├── common/      → Unit tests for shared modules (metrics, middleware)
  ├── weather/     → Unit tests for weather pipeline (incl. CLI parser + fetch)
  ├── kalshi/      → Unit tests for Kalshi client
  ├── prediction/  → Unit tests for prediction engine
  ├── trading/     → Unit tests for trading engine + safety tests
  ├── e2e/         → End-to-end smoke tests (real auth path, real middleware)
  └── integration/ → Cross-module integration tests
```

## Tech Stack

- **Backend:** Python 3.11+, FastAPI, Celery + Redis, PostgreSQL
- **Frontend:** Next.js 14+, React, Tailwind CSS, PWA (Workbox)
- **ML/Stats:** scipy, numpy (Gaussian CDF for bracket probabilities)
- **Monitoring:** prometheus-client (Prometheus metrics via `/metrics` endpoint)
- **Containerization:** Docker + Docker Compose
- **Testing:** pytest (backend), Jest/Vitest (frontend)
- **CI/CD:** GitHub Actions
- **Linting:** ruff (Python), ESLint + Prettier (TypeScript)

## Critical Rules (All Agents Must Follow)

### Security — Non-Negotiable
- **NEVER** log API keys, private keys, or any secret values
- **NEVER** expose API keys in frontend code, API responses, or error messages
- RSA private keys must be AES-256 encrypted at rest
- Keys are only decrypted in-memory when making Kalshi API calls
- All secrets come from environment variables or Docker secrets, never hardcoded

### Testing — Mandatory
- Every module ships with tests. No code is complete without tests.
- External APIs (NWS, Open-Meteo, Kalshi) are ALWAYS mocked in tests — never hit real APIs
- Coverage targets: >80% backend, >70% frontend
- Safety tests are required for any code touching: order placement, risk limits, API keys, position sizing
- Run `pytest` before considering any backend work "done"
- Run `npm test` before considering any frontend work "done"

### Code Style
- Python: Follow ruff defaults. Type hints on all function signatures. Docstrings on all public functions.
- TypeScript: Follow ESLint + Prettier config. Strict TypeScript mode.
- Commits: Conventional commit style preferred. Always include `Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>`

### Logging
- Use structured logging everywhere (see `backend/common/logging.py`)
- Every log line must include: timestamp, level, module tag, message, and structured data dict
- Module tags: WEATHER, MODEL, MARKET, TRADING, ORDER, RISK, COOLDOWN, AUTH, SETTLE, POSTMORTEM, SYSTEM
- NEVER log sensitive data (API keys, private keys, passwords)
- Log at appropriate levels: DEBUG (dev only), INFO (normal ops), WARN (approaching limits), ERROR (failures), CRITICAL (system down)

### Monitoring (Prometheus Metrics)
- All Prometheus metric objects are centralized in `backend/common/metrics.py` — import from there
- HTTP metrics are collected automatically by `PrometheusMiddleware` in `backend/common/middleware.py`
- Celery task metrics are collected automatically via signals in `backend/celery_app.py`
- Business counters (trading cycles, trades executed, risk blocks, weather fetches) are incremented inline
- The `/metrics` endpoint exposes all metrics for Prometheus scraping
- Keep label cardinality bounded — normalize dynamic values (IDs, timestamps) before using as labels

### Interface Contracts
- All cross-module communication uses Pydantic models defined in `backend/common/schemas.py`
- Do NOT import directly from another agent's module — use the shared schemas
- If you need a new shared type, add it to `backend/common/schemas.py`

### Error Handling
- Never let exceptions crash the bot silently
- All API calls must have retry logic with exponential backoff
- Network failures should trigger WARN logs and graceful degradation, not crashes
- Trading-related errors must trigger alerts to the user (push notification or log)

## Key Domain Knowledge

### Kalshi Weather Markets
- 4 cities: NYC (Central Park), Chicago (Midway), Miami (MIA), Austin (AUS)
- 6 brackets per city per day (middle 4 are 2°F wide, top/bottom are catch-alls)
- Markets launch 10:00 AM ET the day before the event
- Settlement: NWS Daily Climate Report (CLI), published the morning after
- Measurement period: 12:00 AM - 11:59 PM LOCAL STANDARD TIME (not DST)
- Contract pays $1 if temp lands in bracket, $0 otherwise

### NWS API
- Base URL: https://api.weather.gov
- No auth needed, just set User-Agent header
- Be respectful of rate limits — no more than 1 request/second

### Open-Meteo API
- Base URL: https://api.open-meteo.com/v1/
- No auth needed
- Free for non-commercial use

### Kalshi API
- Docs: https://docs.kalshi.com
- Auth: RSA key pair (API Key ID + PEM private key)
- REST + WebSocket + FIX 4.4
- Rate limits vary by tier

## File Naming Conventions
- Python: snake_case for files and functions, PascalCase for classes
- TypeScript: camelCase for files, PascalCase for components
- Tests mirror source structure: `backend/weather/nws.py` → `tests/weather/test_nws.py`
- All test files prefixed with `test_`

## Environment Variables
- All config via `.env` file (see `.env.example`)
- Never commit `.env` — it's in `.gitignore`
- Required vars documented in `.env.example` with comments
