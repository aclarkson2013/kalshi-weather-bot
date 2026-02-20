# Boz Weather Trader

Free, open-source automated trading bot for [Kalshi](https://kalshi.com) weather prediction markets. Analyzes weather forecasts from multiple sources, uses ML models to estimate bracket probabilities, and executes trades when it finds positive expected value.

## Features

- **Multi-source weather data** — NWS API + Open-Meteo ensemble forecasts
- **ML prediction engine** — XGBoost + Random Forest + Ridge regression with inverse-RMSE weighted voting
- **Automated +EV trading** — Compares model probabilities to market prices, trades when edge exceeds threshold
- **Kelly Criterion sizing** — Optimal position sizing based on edge and bankroll
- **Two trading modes** — Full Auto (hands-off) or Manual Approval (review each trade)
- **Risk controls** — Max position size, daily loss limit, cooldown periods, exposure limits
- **Real-time dashboard** — PWA installable on phone/desktop with live WebSocket updates
- **Trade post-mortems** — Auto-generated reports explaining why each trade won or lost
- **Backtesting** — Day-by-day historical simulation with Sharpe ratio, drawdown, ROI metrics
- **Forecast accuracy tracking** — Brier score calibration, per-source MAE/RMSE/bias
- **Demo mode** — Safe sandbox for new users (no real trades)
- **Monitoring** — Prometheus metrics, Grafana dashboards, Alertmanager (optional)
- **1,301 tests** — Comprehensive test suite across backend and frontend

## Quick Start (Docker Compose)

**Prerequisites:** [Docker](https://docs.docker.com/get-docker/) and [Docker Compose](https://docs.docker.com/compose/install/)

```bash
git clone https://github.com/aclarkson2013/boz-weather-trader.git
cd boz-weather-trader
bash scripts/generate-env.sh       # Creates .env with random encryption key
nano .env                           # Set NWS_USER_AGENT with your email
docker compose up -d                # Start all services
```

Open [http://localhost:3000](http://localhost:3000) to access the dashboard.

> **First time?** The app starts in demo mode. Follow the onboarding flow to connect your Kalshi API keys.

## Deploy to Cloud

| Platform | Cost | Setup Time | Guide |
|----------|------|------------|-------|
| **Oracle Cloud** | Free forever | ~30 min | [Deploy Guide](docs/deploy-oracle.md) |
| **Fly.io** | Free tier (3 VMs) | ~20 min | [Deploy Guide](docs/deploy-fly.md) |
| **Railway** | ~$5-15/month | ~15 min | [Deploy Guide](docs/deploy-railway.md) |

[![Deploy on Railway](https://railway.app/button.svg)](https://railway.app/template/new?repo=https://github.com/aclarkson2013/boz-weather-trader)

## Architecture

```
                    ┌──────────────┐
                    │   Browser    │  PWA (installable)
                    │  :3000       │
                    └──────┬───────┘
                           │
                    ┌──────▼───────┐
                    │   Frontend   │  Next.js 14
                    │   (PWA)      │
                    └──────┬───────┘
                           │ REST + WebSocket
                    ┌──────▼───────┐
                    │   Backend    │  FastAPI
                    │   :8000      │──── /health
                    └──┬───────┬───┘
                       │       │
            ┌──────────▼──┐ ┌──▼──────────┐
            │  PostgreSQL  │ │    Redis     │
            │  :5432       │ │    :6379     │
            └─────────────┘ └──────────────┘
                       │       │
            ┌──────────▼──┐ ┌──▼──────────┐
            │   Celery     │ │   Celery     │
            │   Worker     │ │   Beat       │
            └─────────────┘ └──────────────┘
```

**Backend** — FastAPI REST API + WebSocket server. Handles predictions, trading, and API endpoints.

**Frontend** — Next.js 14 PWA. Dashboard, market view, trade queue, performance charts, settings.

**Celery Worker** — Processes async tasks: weather fetching, prediction runs, trade execution, model retraining.

**Celery Beat** — Schedules recurring tasks: weather data every 30 min, trading cycles every 15 min, model retraining weekly.

**PostgreSQL** — Persistent storage: trades, weather forecasts, predictions, settlements, user settings.

**Redis** — Caching (weather data, market prices), Celery task broker, WebSocket pub/sub.

## Configuration

Copy `.env.example` to `.env` and customize. Key variables:

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `ENCRYPTION_KEY` | Yes | *(none)* | Fernet key for encrypting stored API keys |
| `DATABASE_URL` | No | `postgresql+asyncpg://boz:boz@localhost:5432/boz_weather_trader` | PostgreSQL connection |
| `REDIS_URL` | No | `redis://localhost:6379/0` | Redis connection |
| `NWS_USER_AGENT` | No | `BozWeatherTrader/1.0 (contact@example.com)` | NWS API requires contact email |
| `ENVIRONMENT` | No | `development` | Set to `production` for cloud deploys |
| `DEFAULT_MAX_TRADE_SIZE` | No | `1.00` | Max dollars per trade |
| `DEFAULT_DAILY_LOSS_LIMIT` | No | `10.00` | Stop trading after this daily loss |
| `DEFAULT_MIN_EV_THRESHOLD` | No | `0.05` | Minimum +EV (5%) to trigger trade |
| `ML_ENSEMBLE_WEIGHT` | No | `0.30` | ML model weight in final prediction blend |

See [`.env.example`](.env.example) for the complete list.

Generate an encryption key:
```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

## Monitoring (Optional)

The full Docker Compose includes Prometheus, Grafana, and Alertmanager:

```bash
# Full stack with monitoring
docker compose up -d

# Core services only (no monitoring) — saves ~1 GB RAM
docker compose -f docker-compose.yml -f docker-compose.cloud.yml up -d
```

When monitoring is enabled:
- **Grafana:** [http://localhost:3001](http://localhost:3001) (default: admin/admin)
- **Prometheus:** [http://localhost:9090](http://localhost:9090)
- 3 dashboards: API Overview, Trading & Weather, Kalshi WebSocket Feed
- 17 alert rules across 6 groups

## Development

```bash
# Backend tests (1,191 tests)
python -m pytest tests/ -x -q --tb=short

# Backend lint
ruff check backend/ tests/ && ruff format --check backend/ tests/

# Frontend tests (110 tests)
cd frontend && npm test

# Frontend lint
cd frontend && npm run lint
```

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | Python 3.11, FastAPI, SQLAlchemy 2, Alembic |
| Frontend | Next.js 14, React, Tailwind CSS, PWA |
| ML/Stats | XGBoost, scikit-learn (Random Forest, Ridge), NumPy |
| Data | PostgreSQL 16, Redis 7 |
| Tasks | Celery + Redis |
| Monitoring | Prometheus, Grafana, Alertmanager |
| CI/CD | GitHub Actions (4 jobs: lint, test, frontend, Docker build) |
| Deploy | Docker Compose |

## Supported Markets

| City | Ticker | NWS Station |
|------|--------|-------------|
| New York City | KXHIGHNY | KNYC (Central Park) |
| Chicago | KXHIGHCHI | KMDW (Midway Airport) |
| Miami | KXHIGHMIA | KMIA (Miami Intl) |
| Austin | KXHIGHAUS | KAUS (Bergstrom Intl) |

Currently supports daily high temperature markets. Architecture is modular for adding new market types.

## License

MIT License. See [pyproject.toml](pyproject.toml) for details.

## Disclaimer

This software is for educational and informational purposes. Trading involves risk of loss. Automated trading amplifies both gains and losses. Past performance does not guarantee future results. You are responsible for your own trading decisions and should only trade with money you can afford to lose. This is not financial advice.
