# Product Requirements Document (PRD)
# Boz Weather Trader

**Version:** 1.2
**Date:** February 19, 2026
**Status:** All P0+P1 complete (28 phases, 1301 tests)

---

## 1. Overview

### 1.1 Problem Statement
Kalshi offers daily weather prediction markets (high temperature) for US cities. These markets are highly data-driven — settlement is based on the NWS Daily Climate Report, and weather forecasts from models like GFS, ECMWF, and HRRR are strong predictors of outcomes. Despite this, most retail traders on Kalshi trade manually, relying on gut feel or basic weather app checks. There is an opportunity to build an automated trading bot that leverages weather forecast data and ML models to identify mispriced contracts and execute trades programmatically.

### 1.2 Product Vision
**Boz Weather Trader** is a free, self-hostable weather trading bot delivered as a Progressive Web App (PWA). Users connect their Kalshi account via API keys, configure risk preferences and trading mode (manual approval or full auto), and let the bot analyze weather markets and execute trades on their behalf. The bot combines multiple weather data sources, uses statistical/ML models to generate probability distributions for temperature outcomes, compares those to market prices, and trades when it finds edge.

### 1.3 Target Users
- Retail Kalshi traders interested in weather markets who want automated execution
- Data-savvy traders who want to leverage weather models without building infrastructure
- Hobbyist traders looking for a hands-off approach to weather market trading
- Mobile-first users who want to monitor trades from their phone

### 1.4 Business Model
**Free and open-source.** No subscription, no revenue share. Users provide their own Kalshi API keys and are responsible for their own trading capital and outcomes.

### 1.5 Distribution Strategy
- **Primary**: Docker Compose — self-host on any machine (homelab, VPS, cloud)
- **Secondary**: One-click deploy templates for cloud platforms (see Section 3.4 for free and paid options)
- **Frontend**: Progressive Web App (PWA) — installable on iPhone/Android home screen, push notifications, works offline for cached data, no App Store approval needed
- **Future**: Native app wrapper (React Native) if demand warrants it

---

## 2. Market Context

### 2.1 Kalshi Weather Markets Structure

**Cities & Tickers (currently available on Kalshi):**
| City | Event Ticker | NWS Station | Resolution Location |
|------|-------------|-------------|-------------------|
| New York City | KXHIGHNY | KNYC | Central Park |
| Chicago | KXHIGHCHI | KMDW | Midway Airport |
| Miami | KXHIGHMIA | KMIA | Miami Intl Airport |
| Austin | KXHIGHAUS | KAUS | Bergstrom Intl Airport |

> **Note:** These 4 cities are the only daily high temperature markets that Kalshi currently offers. This is a Kalshi platform limitation, not our design choice. If Kalshi adds more cities in the future (e.g., LA, Dallas, Seattle), Boz Weather Trader will automatically support them — our architecture dynamically discovers available markets via the Kalshi API.

### 2.2 Bracket Structure

Each daily high temperature event is divided into **6 brackets** (contracts). Exactly one bracket wins each day — the one where the actual NWS-reported high temperature lands.

**Example: NYC forecast high of 55°F**
```
Bracket 1:  Below 51°F         → pays $1 if actual high < 51°F
Bracket 2:  51°F to 52°F       → pays $1 if actual high is 51-52°F
Bracket 3:  53°F to 54°F       → pays $1 if actual high is 53-54°F
Bracket 4:  55°F to 56°F       → pays $1 if actual high is 55-56°F  ← forecast center
Bracket 5:  57°F to 58°F       → pays $1 if actual high is 57-58°F
Bracket 6:  59°F or above      → pays $1 if actual high ≥ 59°F
```

**How it works:**
- The **middle 4 brackets** each span exactly 2 degrees Fahrenheit
- The **2 edge brackets** (top and bottom) are catch-alls for everything above or below
- Brackets are usually centered around the NWS forecast high, so the predicted temp sits in one of the middle brackets
- Contract prices reflect what the market thinks the probability is (e.g., $0.35 = the market believes there's a 35% chance the temp lands in that bracket)
- You can buy **YES** (betting the temp WILL land in that bracket) or **NO** (betting it WON'T)
- Exactly ONE bracket wins each day — the losing 5 pay $0

**Where Boz Weather Trader finds edge:** If our model calculates a 30% chance for Bracket 3 but the market is pricing it at $0.18 (18%), that's a +EV trade — we buy YES on Bracket 3 because we believe the market is underpricing it.

### 2.3 Market Timing — The Daily Lifecycle

```
TUESDAY 10:00 AM ET — Kalshi launches WEDNESDAY's weather markets
  ├── 6 brackets appear for each city (24 total contracts across 4 cities)
  ├── Prices start forming as traders buy/sell
  └── Boz Weather Trader fetches brackets, compares to model, starts trading

TUESDAY afternoon/evening — Prices move as forecasts update
  ├── New weather model runs (GFS, ECMWF) come in every 6-12 hours
  ├── Boz re-checks weather data every 30 min, re-calculates probabilities
  └── If model shift creates new +EV opportunities, bot trades/queues them

WEDNESDAY (the actual day) — The weather happens
  ├── Markets may still be open for some morning trading
  ├── By afternoon, the daily high has likely been reached
  └── Markets close (no more trading possible)

THURSDAY morning ~8:00 AM ET — Settlement
  ├── NWS publishes the Daily Climate Report (CLI)
  │   e.g., "NYC high: 54°F" measured at Central Park
  ├── Kalshi settles: Bracket 3 (53-54°F) pays $1, all others pay $0
  └── Boz records settlement, updates P&L, logs model accuracy

KEY INSIGHT: Markets launch ~24 hours before the event. The further out
the forecast, the more uncertain it is — and more uncertainty means more
potential for mispricing that our model can exploit.
```

### 2.4 Fee Structure
- Trading fee: ~1% per trade
- Settlement fee: ~10% of profit
- Withdrawal fee: ~2%

### 2.5 Available Market Types (Roadmap)

| Market Type | Status on Kalshi | In Boz MVP? | Notes |
|------------|-----------------|-------------|-------|
| **Daily High Temperature** | Active (4 cities) | **YES** | Best liquidity, clearest data pipeline |
| Daily Low Temperature | TBD | No | Coming Soon — add when Kalshi offers it |
| Daily Precipitation | TBD | No | Coming Soon — different data sources needed |
| Snowfall | Seasonal | No | Coming Soon — winter only |
| Weekly/Monthly Climate | TBD | No | Coming Soon — longer-term markets |

**MVP focuses on Daily High Temperature only.** The architecture is modular — each market type is a plugin with its own data source, model, and bracket logic. The UI will show a market selector from day one with "Coming Soon" badges on unavailable types. This lets us ship a polished, well-tested product for the most liquid market first, then add markets incrementally once each model is proven profitable.

---

## 3. Technical Architecture

### 3.1 High-Level System Design

```
┌─────────────────────────────────────────────────────────────────┐
│                     USER DEVICES                                 │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐                      │
│  │ iPhone   │  │ Android  │  │ Desktop  │   (PWA - installable) │
│  │ (PWA)    │  │ (PWA)    │  │ Browser  │                       │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘                      │
└───────┼──────────────┼─────────────┼────────────────────────────┘
        │              │             │
        └──────────────┼─────────────┘
                       │ HTTPS
        ┌──────────────▼──────────────┐
        │      Next.js Frontend       │
        │   (PWA + Service Worker)    │
        │   - Dashboard               │
        │   - Market selector         │
        │   - Trade approval queue    │
        │   - Trade post-mortems      │
        │   - Settings / risk config  │
        └──────────────┬──────────────┘
                       │ REST API
        ┌──────────────▼──────────────┐
        │    Python Backend (FastAPI) │
        │   - User session mgmt      │
        │   - Trading engine          │
        │   - EV calculator           │
        │   - Risk management         │
        │   - Trade post-mortem gen   │
        └──────┬──────────┬───────────┘
               │          │
    ┌──────────▼──┐  ┌────▼──────────┐
    │  Scheduler  │  │  PostgreSQL   │
    │  (Celery +  │  │  + Redis      │
    │   Redis)    │  │               │
    └──────┬──────┘  └───────────────┘
           │
    ┌──────▼──────────────────────────┐
    │        DATA & TRADING LAYER     │
    │                                 │
    │  ┌───────────┐  ┌────────────┐  │
    │  │ Weather   │  │  Kalshi    │  │
    │  │ Data      │  │  API       │  │
    │  │ Pipeline  │  │  Client    │  │
    │  └─────┬─────┘  └─────┬──────┘  │
    └────────┼──────────────┼─────────┘
             │              │
    ┌────────▼────┐  ┌──────▼──────┐
    │ NWS API     │  │ Kalshi      │
    │ Open-Meteo  │  │ REST + WS   │
    │ Visual Cross│  │             │
    └─────────────┘  └─────────────┘
```

### 3.2 Core Components

#### 3.2.1 Weather Data Layer
**Primary Data Sources:**
1. **NWS API** (api.weather.gov) - Free, no API key required
   - Gridpoint forecasts (hourly, 7-day)
   - Daily Climate Reports (CLI) - the actual settlement source
   - Station observations (METAR data)

2. **Open-Meteo API** - Free for non-commercial use, no API key
   - Historical weather data (80+ years via ERA5 reanalysis)
   - Historical forecast data (backtesting model accuracy)
   - Multiple model outputs (GFS, ECMWF, ICON, etc.)
   - Hourly resolution, up to 16-day forecasts

3. **Visual Crossing** (or similar) - For enriched historical data
   - 3+ years of historical data for model training
   - Features: tmin, tmax, cloud cover, wind gust, humidity (~28 features)

**Key Weather Variables to Collect:**
- Temperature (current, forecast high/low, hourly)
- Cloud cover, humidity, dew point
- Wind speed and gusts
- Precipitation probability
- Pressure systems
- Model run timestamps (for freshness)

#### 3.2.2 ML/Statistical Prediction Engine
**Approach: Ensemble of models for temperature prediction**

1. **Baseline Model**: Weighted average of NWS point forecast + Open-Meteo multi-model ensemble
2. **XGBoost Model** (Phase 2): Trained on historical weather data to predict next-day tmax
   - Features: historical temps, cloud cover, wind, humidity, season, etc.
   - Hyperparameter tuning via grid search / Bayesian optimization
3. **Probability Distribution Generator**: Convert point forecast into probability distribution across Kalshi brackets
   - Use historical forecast error distribution (how often is NWS off by X degrees?)
   - Generate P(temp in bracket) for each of the 6 brackets
4. **Model Calibration**: Backtest against historical NWS CLI reports to calibrate confidence

**Market Type Plugin Architecture:**
Each market type (high temp, low temp, precipitation, etc.) implements a standard interface:
```
MarketPlugin:
  - get_data_sources() → list of API endpoints to fetch
  - fetch_data() → raw weather data
  - predict() → probability distribution across brackets
  - get_settlement_source() → how this market resolves
```
This makes adding new market types straightforward without touching the core trading engine.

**Key Outputs:**
- Probability estimate for each bracket (must sum to ~100%)
- Confidence interval / uncertainty measure
- Comparison to market-implied probabilities (contract prices)
- Expected value calculation per contract

#### 3.2.3 Trading Engine
**Trading Mode Toggle (User-Configurable):**
- **Full Auto**: Bot executes trades immediately when EV threshold is met. No user intervention.
- **Manual Approval**: Bot identifies trades and queues them for user approval. User gets a push notification, reviews the trade (with model reasoning), and taps approve/reject. Trade expires if not acted on within a configurable window.

**Strategy Logic:**
1. Fetch current market prices for all brackets in selected cities
2. Compare model probabilities to market-implied probabilities
3. Calculate expected value (EV) for each potential trade:
   - `EV = (model_prob * payout) - (contract_price) - fees`
4. If Full Auto: execute trades where EV exceeds threshold
5. If Manual: queue trades for user approval with push notification
6. Position sizing based on user-defined limits (Kelly Criterion in Phase 2)

**Order Execution:**
- Use Kalshi REST API for order placement
- Support limit orders (preferred) and market orders
- WebSocket connection for real-time price updates
- Batch order support (up to 20 per request)

**Risk Management (all user-configurable):**
- Maximum position size per market (default: $1 per trade)
- Maximum daily loss limit (default: $10)
- Maximum exposure across all markets (default: $25)
- Minimum EV threshold to trigger a trade (default: 5%)
- Cooldown after loss: pause trading after a loss (default: 60 minutes, adjustable from 0/off to 24 hours)
- Cooldown after consecutive losses: pause for rest of day after N losses in a row (default: 3, adjustable from 0/off to 10)
- Conservative defaults for new users (small position sizes)

#### 3.2.4 Backend API Server
- RESTful API serving the frontend
- User session management (stores encrypted Kalshi API keys)
- Scheduling: Celery beat for data fetching, model runs, and trade execution
- Logging and audit trail for all trades
- Database for historical data, predictions, and trade records
- Web push notification service for trade alerts
- Trade post-mortem generator (runs after settlement)

#### 3.2.5 Web Frontend (PWA Dashboard)
- **Onboarding**: Step-by-step guided flow to connect Kalshi account (see Section 3.5)
- **Dashboard**: Overview of active positions, P&L, model predictions
- **Markets View**: Market type selector (high temp active, others "Coming Soon"), current markets with model probabilities vs. market prices
- **Trade Queue**: Pending trades awaiting approval (in Manual mode)
- **Trade History & Post-Mortems**: Full audit log of all trades, each with an executive summary explaining why the trade was taken and why it won or lost (see Section 3.6)
- **Settings**: Trading mode toggle (auto/manual), risk parameters (including cooldown controls), city selection, notification preferences
- **Performance**: Charts showing cumulative P&L, accuracy metrics, ROI per city
- **PWA Features**: Installable to home screen, push notifications, offline-capable for cached data

### 3.3 Tech Stack

| Layer | Technology | Rationale |
|-------|-----------|-----------|
| Frontend | Next.js + React + Tailwind CSS | PWA support, SSR, great mobile experience |
| PWA | next-pwa / Workbox | Service worker, offline caching, push notifications |
| Backend | Python (FastAPI) | Best ML/data science ecosystem, async support |
| Database | PostgreSQL + Redis | Relational data + caching/task queue |
| ML | XGBoost, scikit-learn, pandas, numpy | Proven for tabular data / time-series |
| Task Queue | Celery + Redis | Scheduled jobs (data fetch, model runs, trade execution) |
| Notifications | Web Push API (via pywebpush) | Push notifications to PWA on all devices |
| Containerization | Docker + Docker Compose | Self-hostable on homelab, VPS, or cloud |
| Auth | Kalshi API keys (user-provided, encrypted at rest) | No password storage needed |

### 3.4 Deployment Options

#### Option A: Self-Hosted (Docker Compose)
```bash
git clone https://github.com/aclarkson2013/boz-weather-trader.git
cd boz-weather-trader
cp .env.example .env  # Configure your settings
docker-compose up -d
# Access at http://localhost:3000
```
- Perfect for homelabs, Raspberry Pi, VPS
- Full control over data
- Zero recurring cost (besides electricity)

#### Option B: Cloud Deploy (Free Tiers Available)

**Free options:**
- **Oracle Cloud Free Tier**: Free forever ARM VM (4 OCPU, 24GB RAM — more than enough)
- **Google Cloud Free Tier**: f1-micro instance, free forever
- **Fly.io Free Tier**: Up to 3 shared VMs free

**Paid options ($5-15/month):**
- **Railway**: One-click deploy button in README
- **Fly.io** (beyond free tier): `fly launch` from repo
- **DigitalOcean App Platform**: App spec included

> **Note:** The $5-15/month cost is what the cloud platform charges for hosting — Boz Weather Trader itself is free. Think of it like paying for electricity at someone else's house.

### 3.5 Authentication & Onboarding Flow

**Method: RSA API Key Pair only (no email/password)**

Boz Weather Trader never handles Kalshi passwords. Users generate API keys on Kalshi's website and paste them into our app. This is the most secure approach — our server only ever sees the API key, never the user's login credentials.

**Onboarding Steps (guided in-app):**

```
Step 1: Welcome Screen
  "Welcome to Boz Weather Trader.
   Connect your Kalshi account to start trading weather markets."
  [Get Started] button

Step 2: Generate API Keys (with screenshots/instructions)
  "To connect, you'll need to create API keys on Kalshi's website."
  1. Log into kalshi.com
  2. Go to Account Settings → API Keys
  3. Click "Generate New Key"
  4. Kalshi will create an RSA key pair and let you download the private key
  5. Copy your Key ID and the private key file contents
  [I have my keys →]

Step 3: Enter API Keys
  - Field 1: "API Key ID" (text input)
  - Field 2: "Private Key" (textarea — paste PEM-formatted RSA private key)
  [Connect Account]

Step 4: Validation
  - App calls Kalshi API to verify the key pair works
  - On success: "Connected! Your account balance is $X.XX"
  - On failure: "Invalid keys. Please double-check and try again." + troubleshooting tips

Step 5: Risk Disclaimer
  - User must acknowledge trading risks before proceeding
  - Checkbox: "I understand that trading involves risk of loss..."
  [I Understand, Continue]

Step 6: Initial Settings
  - Trading mode: Full Auto / Manual Approval (default: Manual)
  - Max trade size: (default: $1.00)
  - Cities to trade: checkboxes (default: all 4)
  - Cooldown after loss: slider (default: 60 minutes)
  [Start Trading]
```

**Key Security Decisions:**
- RSA private keys are encrypted with AES-256 before storage
- Keys are only decrypted in-memory when making Kalshi API calls
- Private keys are never logged, never sent to our frontend, never exposed in API responses
- Users can revoke keys anytime on Kalshi's website (instant kill switch)
- Session tokens for our app are separate from Kalshi API keys

### 3.6 Trade Post-Mortem (Executive Summary)

After each market settles, Boz Weather Trader automatically generates a structured post-mortem for every trade. This explains **why** the trade was taken and **why** it won or lost — like a mini executive brief for each trade.

**Post-Mortem Template:**
```
TRADE #247 — NYC High Temp | Feb 16, 2026
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Result: WIN ✅  |  P&L: +$0.62

WHAT WE TRADED
  Bought YES on 53-54°F bracket @ $0.38 (1 contract)

WHAT HAPPENED
  Actual high: 54°F (NWS CLI Report, Central Park)
  Winning bracket: 53-54°F ✅

WHY WE TOOK THIS TRADE
  • Our model predicted 34% chance for this bracket
  • Market was pricing it at 22% ($0.22) — 12 percentage point edge
  • NWS point forecast said 56°F, but our model weighted the
    ECMWF run more heavily due to its recent accuracy in NYC
  • Open-Meteo ensemble average: 54.2°F (closer to our prediction)
  • Historical forecast error for NYC in February: ±2.1°F std dev

WHY IT WORKED (or DIDN'T WORK)
  • A cold front moved through faster than the GFS model predicted,
    keeping temps lower than the NWS consensus
  • ECMWF's 54°F forecast was spot-on
  • Market was over-weighting the NWS point forecast and ignoring
    the European model divergence

MODEL CONFIDENCE AT TIME OF TRADE
  Confidence: HIGH (model agreement: 3 of 4 sources within 1°F)
  EV at entry: +$0.12 per contract
```

**Data captured for each post-mortem:**
- All weather model forecasts at time of trade (NWS, GFS, ECMWF, etc.)
- Market price at time of trade vs. model probability
- Actual settlement temperature and source
- Which models were most/least accurate
- Confidence level and EV at entry
- Position size and P&L

These post-mortems are stored indefinitely and browsable in the Trade History view. Users can filter by city, result (win/loss), confidence level, and date range.

### 3.7 Data Storage Architecture

All data lives inside the Docker setup, on whatever machine hosts the bot.

```
Your Machine (homelab / cloud VPS)
  └── Docker
       ├── Container: backend     (FastAPI — Python app)
       ├── Container: frontend    (Next.js — PWA dashboard)
       ├── Container: postgres    (PostgreSQL — all persistent data)
       ├── Container: redis       (Redis — cache + task queue)
       └── Container: celery      (Celery worker — scheduled jobs)

       └── Volume: /data/postgres   ← your actual data lives here on disk
       └── Volume: /data/redis      ← cache data
```

**Where each type of data is stored:**

| Data Type | Where | Why |
|-----------|-------|-----|
| Weather forecasts (historical) | PostgreSQL | Queryable, joinable with trade data |
| Model predictions | PostgreSQL | Need to compare predictions vs. actuals |
| Trade history + post-mortems | PostgreSQL | Permanent record, full audit trail |
| Market price snapshots | PostgreSQL | Historical analysis |
| NWS CLI settlement reports | PostgreSQL | Ground truth for model accuracy |
| User API keys (encrypted) | PostgreSQL | AES-256 encrypted at rest |
| Push notification subscriptions | PostgreSQL | Persistent across restarts |
| Real-time orderbook data | Redis (cache) | Fast, ephemeral — only need current day |
| Trade approval queue | Redis + PostgreSQL | Redis for speed, PG for persistence |
| Celery task state | Redis | Task queue, expires naturally |

**Backup:** The Docker volume (`/data/postgres`) can be backed up by copying it, or by running `pg_dump` on a schedule. We'll include a backup script in the repo.

---

## 4. Feature Requirements

### 4.1 MVP (Phase 1)

#### P0 - Must Have
- [x] **Guided onboarding flow** - Step-by-step walkthrough to generate RSA keys on Kalshi and connect account (Phase 17)
- [x] **RSA API key validation & encrypted storage** - Validate key pair against Kalshi API, store private key AES-256 encrypted (Phase 2, 15)
- [x] **Weather data pipeline** - Automated fetching from NWS API + Open-Meteo on a schedule (Phase 2)
- [x] **Basic prediction model** - Ensemble of NWS forecast + Open-Meteo models to generate bracket probabilities (Phase 3)
- [x] **EV calculation engine** - Compare model probabilities to market prices, identify +EV trades (Phase 3)
- [x] **Trading mode toggle** - User chooses Full Auto or Manual Approval mode (Phase 4)
- [x] **Automated trade execution** (Full Auto mode) - Place limit orders on Kalshi when EV threshold is met (Phase 3)
- [x] **Trade approval queue** (Manual mode) - Queue trades for user review with push notification (Phase 3, 5)
- [x] **Basic PWA dashboard** - Show active markets, model predictions, current positions, P&L (Phase 5)
- [x] **Risk controls** - Max position size, daily loss limit, min EV threshold, adjustable cooldown periods (Phase 3)
- [x] **Trade logging** - Full audit trail of every trade placed with reasoning (Phase 4)
- [x] **Trade post-mortems** - Auto-generated executive summary for each trade after settlement (Phase 3, 14)
- [x] **Structured logging** - Module-tagged, leveled logs to stdout + database (Phase 1)
- [x] **Unit + safety tests** - Every module ships with tests; 834 backend + 110 frontend = 944 tests (All phases)
- [x] **CI/CD pipeline** - GitHub Actions: 3 parallel jobs (lint, test, frontend) (Phase 8)
- [x] **Docker Compose deployment** - 9-service Docker Compose (backend, frontend, postgres, redis, celery worker/beat, prometheus, grafana, alertmanager) (Phase 6, 16, 19)
- [x] **Market type selector UI** - High Temp active, others show "Coming Soon" (Phase 5)
- [x] **Demo mode** - Safe demo/production toggle, new users start in demo mode (Phase 15, 17)

#### P1 - Should Have
- [x] **Multi-city support** - Trade all 4 cities (NYC, Chicago, Miami, Austin) simultaneously (Phase 2 — active_cities in user settings)
- [x] **Real-time price updates** - WebSocket connection to Kalshi for live orderbook data + Redis cache (Phase 18, 20)
- [x] **Push notifications** - Web push for trade executions, settlements, alerts (Phase 3 — NotificationService)
- [x] **Performance analytics** - Cumulative P&L charts, win rate, ROI per city (Phase 5 — performance page + charts)
- [x] **PWA install prompt** - Installable via manifest.json + next-pwa service worker (Phase 5)
- [x] **Log viewer in dashboard** - Filterable log viewer with module/level/time filters (Phase 5)
- [x] **One-click cloud deploy** - Railway / Fly.io / Oracle Cloud deploy guides in README (Phase 28)

### 4.2 Phase 2 (Post-MVP) — Not Yet Started

#### P1 - Should Have
- [x] **XGBoost ML model** - Trained on historical data for improved predictions (Phase 23)
- [x] **Multiple model ensemble** - Combine statistical + ML models with weighted voting (Phase 27)
- [x] **Kelly Criterion position sizing** - Optimal bet sizing based on edge and bankroll (Phase 24)
- [x] **Backtesting module** - Test strategy against historical data (Phase 25)
- [x] **Historical forecast accuracy tracking** - Monitor model calibration over time (Phase 26)

#### P2 - Nice to Have
- [ ] **Additional market plugins** - Precipitation, snowfall, low temperature
- [ ] **Market maker mode** - Two-sided quoting for advanced users
- [ ] **Webhook integrations** - Discord/Slack notifications
- [ ] **Social/leaderboard** - Compare performance with other users (opt-in)
- [ ] **Native mobile wrapper** - React Native shell if PWA demand warrants it

### 4.3 Implementation Phases (Complete Log)

| Phase | What | Key Deliverables | Tests Added |
|-------|------|-----------------|-------------|
| 1 | Scaffolding + Common | Project structure, schemas, config, DB, logging, encryption | — |
| 2 | Weather + Kalshi clients | NWS, Open-Meteo, Kalshi REST/WS, auth, markets, rate limiters | — |
| 3 | Prediction + Trading engines | Ensemble, brackets, EV calc, risk manager, cooldowns, trade queue, executor | — |
| 4 | REST API (FastAPI) | 10 API routers, dependency injection, response schemas | — |
| 5 | Frontend PWA (Next.js 14) | Dashboard, onboarding, markets, queue, trades, logs, performance, settings | 110 |
| 6 | Docker Compose | 6 services (backend, frontend, postgres, redis, celery worker/beat) | — |
| 7 | Celery scheduler tests | Trading cycle, settlement, trade expiry task tests | 51 |
| 8 | GitHub Actions CI/CD | 3 parallel jobs: backend-lint, backend-test, frontend | — |
| 9 | Integration tests | Cross-module tests: signal gen, error prop, prediction, risk, settlement, trading cycle | 47 |
| 10 | Alembic migrations | Initial schema (8 tables) + demo_mode migration | — |
| 11 | Production hardening | Middleware (request ID, logging, Prometheus, security headers), health checks, task timeouts | — |
| 12 | Monitoring & Observability | Prometheus metrics (13 metric objects), /metrics endpoint | — |
| 13 | E2E smoke tests | Real auth path, full middleware stack, 11 test classes | 35 |
| 14 | NWS CLI Settlement | CLI parser, fetch pipeline, Settlement record creation | — |
| 15 | Kalshi auth integration | Demo mode toggle, /status endpoint, E2E wiring, migration 0002 | — |
| 16 | Grafana dashboards | 2 dashboards (18 panels), Prometheus/Grafana/Alertmanager Docker stack | 22 |
| 17 | Frontend onboarding UI | Demo mode toggle, auth status, connection status components | — |
| 18 | WebSocket streaming | Redis pub/sub → FastAPI WS → browser, SWR revalidation, 3 WS metrics | 35 |
| 19 | Prometheus alerting | 14 alert rules, 5 groups, Alertmanager webhook routing, inhibit rules | 56 |
| 20 | Kalshi WS market feed | Persistent WS feed, Redis price cache, cache-first trading, 3 alert rules | 42 |
| 21 | Grafana WS dashboard | Kalshi WS Feed dashboard (6 panels), timezone test fixes | +9 |
| 22 | Performance + prod deploy | N+1 fix, SQL aggregation, GZip, smart Cache-Control, multi-stage Docker, prod compose, CI coverage | — |
| 23 | XGBoost ML model | 21-feature regression, ensemble blend, training pipeline, Celery task, graceful fallback | 62 |
| 24 | Kelly Criterion sizing | Fractional Kelly (0.25×), fee-adjusted, wired into ev_calculator + scheduler, Prometheus metrics | 18 |
| 25 | Backtesting module | Day-by-day simulation engine, synthetic prices, in-memory risk sim, metrics (Sharpe/drawdown/ROI), Kelly comparison, API endpoint | 95 |
| 26 | Forecast accuracy tracking | Brier score calibration, per-source MAE/RMSE/bias, error trends, 3 API endpoints | 54 |
| 27 | Multi-model ML ensemble | XGBoost + Random Forest + Ridge with inverse-RMSE weighting, training pipeline, graceful degradation | 57 |
| 28 | One-click cloud deploy | README, Railway/Fly.io/Oracle guides, fly.toml, railway.json, docker-compose.cloud.yml, generate-env.sh | — |
| **Total** | | **1191 backend + 110 frontend = 1301 tests** | |

---

## 5. Data Flow

### 5.1 Daily Trading Cycle

```
Timeline (Eastern Time):
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Day Before (D-1):
  06:00 AM  - Fetch latest NWS + Open-Meteo forecasts for D-day
  08:00 AM  - Run prediction model, generate bracket probabilities
  09:00 AM  - Pre-compute EV for expected bracket structures
  10:00 AM  - Markets launch on Kalshi → Fetch actual brackets + prices
  10:01 AM  - Compare model probabilities to market prices
  10:05 AM  - Execute initial trades (auto) or queue for approval (manual)
             → Push notification sent to user if in manual mode

Ongoing (D-1 afternoon → D-day):
  Every 30m - Re-fetch weather data (model updates, new observations)
  Every 30m - Re-run predictions if data materially changed
  Every 15m - Check market prices, execute/queue if new +EV opportunities

Day Of (D-day):
  Morning   - Monitor any final trading opportunities
  Market Close - No more trades possible

Day After (D+1):
  ~08:00 AM - NWS publishes Daily Climate Report (CLI)
  ~09:00 AM - Kalshi settles markets based on CLI
  ~09:30 AM - Record settlement, update P&L, log model accuracy
  ~09:35 AM - Generate trade post-mortems for all settled trades
             → Push notification: "Yesterday's results: +$X.XX — 2 wins, 1 loss"
```

### 5.2 Manual Approval Flow

```
Bot identifies +EV trade
       │
       ▼
Queue trade in database (status: PENDING)
       │
       ▼
Send push notification to user's device
"NYC High Temp 52-53°F: Model says 34%, market says 22%. Buy YES @ $0.22?"
       │
       ▼
User opens PWA → sees trade queue
       │
       ├── Approve → Bot places order on Kalshi
       │
       ├── Reject → Trade discarded, logged
       │
       └── Expires (configurable, default 30 min) → Trade discarded, logged
```

---

## 6. API Integrations

### 6.1 Kalshi API
- **Auth**: RSA key-pair based authentication (user-generated on Kalshi's site)
  - User provides: API Key ID + RSA Private Key (PEM format)
  - Each API request is signed with the private key using RSA cryptographic signing
  - No email/password authentication — API keys only
- **REST API**: Market data, order placement, portfolio management
- **WebSocket**: Real-time orderbook, fills, positions (authenticated via same RSA keys)
- **Rate limits**: Tier-dependent (to be documented per tier)
- **Key endpoints**:
  - GET /markets - Fetch market data
  - POST /orders - Place orders
  - GET /portfolio/positions - Check positions
  - WebSocket subscriptions for real-time data

### 6.2 NWS API (api.weather.gov)
- **Auth**: None (just User-Agent header)
- **Endpoints**:
  - `/points/{lat},{lon}` - Location metadata
  - `/gridpoints/{office}/{x},{y}/forecast` - 12h period forecasts
  - `/gridpoints/{office}/{x},{y}` - Raw numerical forecast data
  - Station observations for real-time conditions
- **Rate limits**: Reasonable (not strictly documented, be respectful)
- **Data format**: JSON (GeoJSON)

### 6.3 Open-Meteo API
- **Auth**: None required (free tier)
- **Endpoints**:
  - Forecast API - Up to 16-day hourly forecasts
  - Historical Weather API - ERA5 reanalysis back to 1940
  - Historical Forecast API - Past model runs for backtesting
  - ECMWF API - European model data
- **Rate limits**: Generous free tier
- **Data format**: JSON

---

## 7. Security & Compliance

### 7.1 Security Requirements
- Kalshi API keys stored encrypted at rest (AES-256)
- API keys never logged or exposed in frontend
- HTTPS everywhere (required for PWA + push notifications)
- Keys transmitted only to Kalshi API, never to third parties
- Session management with secure tokens (httpOnly cookies)
- Rate limiting on our API to prevent abuse
- Docker secrets support for sensitive configuration

### 7.2 Compliance Considerations
- Kalshi is CFTC-regulated — the bot must comply with Kalshi's Terms of Service
- Users must accept Kalshi's Developer Agreement to use API
- Bot should include disclaimers: not financial advice, past performance doesn't guarantee future results
- Users are responsible for their own trading activity and tax obligations
- Must respect Kalshi's API rate limits and usage policies

### 7.3 Risk Disclaimers (Required — shown during onboarding)
- Trading involves risk of loss
- Automated trading amplifies both gains and losses
- Weather prediction is inherently uncertain
- Past model performance is not indicative of future results
- Users should only trade with money they can afford to lose
- This tool is not financial advice

---

## 8. Testing & Logging Strategy

### 8.1 Testing Philosophy

**Every module ships with tests. No exceptions.** Each sub-agent writes tests alongside its code — testing is not a separate phase, it's part of building each feature. Code is not considered complete until its tests pass.

**Test framework:** pytest (Python backend) + Jest/Vitest (Next.js frontend)

### 8.2 Test Layers

#### Layer 1: Unit Tests (written by each agent alongside code)

Every function, class, and module gets unit tests. External APIs are mocked — tests never hit real NWS, Open-Meteo, or Kalshi during testing.

| Module | Example Unit Tests |
|--------|--------------------|
| **Weather Pipeline** | NWS response parsing, Open-Meteo data normalization, missing data handling, timezone conversion, stale data detection |
| **Kalshi Client** | RSA signature generation, order payload construction, market data parsing, error handling for rate limits / auth failures |
| **Prediction Engine** | Bracket probability distribution sums to 100%, forecast error distribution calculation, ensemble weighting, edge case temps (0°F, 100°F+) |
| **Trading Engine** | EV calculation accuracy, risk limit enforcement (max position, daily loss), cooldown trigger/reset logic, trade queue state machine (PENDING→APPROVED→EXECUTED) |
| **Frontend** | Component rendering, onboarding flow step transitions, settings form validation, trade approval UI states |

**Coverage target:** > 80% line coverage for backend, > 70% for frontend

#### Layer 2: Integration Tests (written during module integration)

Tests that verify modules work correctly together. These use real database containers (via Docker) but mock external APIs.

| Integration Test | What It Verifies |
|-----------------|-----------------|
| Weather → Prediction | Weather pipeline output correctly feeds into prediction engine; schema matches |
| Prediction → Trading | Probability distribution correctly compared to market prices; EV calculation uses correct inputs |
| Trading → Kalshi Client | Trading engine correctly calls Kalshi client methods; order payloads are valid |
| Trading → Risk Controls | Risk limits actually stop trades (daily loss hit → no more trades; cooldown active → trades queued not executed) |
| Backend → Database | Data persists correctly; encrypted keys can be stored and retrieved; trade history is queryable |
| Frontend → Backend API | API responses render correctly in dashboard; onboarding flow works end-to-end |

#### Layer 3: Simulation / End-to-End Tests (pre-launch validation)

Replay historical data through the entire system to verify the full pipeline works correctly.

```
Historical Simulation Test:
  1. Load 30 days of historical NWS + Open-Meteo forecast data
  2. Load corresponding Kalshi market prices (snapshots)
  3. Run prediction engine → verify probabilities are reasonable
  4. Run trading engine → verify it identifies correct +EV trades
  5. Simulate order execution → verify orders would have been valid
  6. Load actual NWS CLI settlements → verify P&L calculation is correct
  7. Generate post-mortems → verify they contain accurate data

  PASS CRITERIA: Full pipeline runs without errors, P&L matches
  manual calculation, no trades violate risk limits
```

This simulation doubles as the **backtesting module** in Phase 2.

#### Layer 4: Safety Tests (critical for a trading bot)

Specific tests to ensure the bot can't do anything dangerous:

| Safety Test | What It Prevents |
|-------------|-----------------|
| Max position size enforced | Bot can't accidentally buy 1000 contracts instead of 1 |
| Daily loss limit enforced | Bot stops trading after hitting the loss limit, even if +EV trades exist |
| Cooldown actually pauses trading | After N consecutive losses, bot pauses — doesn't keep trading |
| Invalid orders rejected | Malformed orders never reach Kalshi API |
| Encrypted keys never leaked | API keys don't appear in logs, error messages, API responses, or frontend |
| Stale data stops trading | If weather data is > 2 hours old, bot pauses and alerts user |
| Network failure handling | If Kalshi API is unreachable, bot queues orders and retries — doesn't crash |

### 8.3 Structured Logging

Every step of the system produces structured logs for debugging and audit trails. Logs are written to both stdout (Docker logs) and PostgreSQL (queryable history).

**Log Format:**
```
[TIMESTAMP]  [LEVEL]  [MODULE]  [MESSAGE]  {structured_data}

Examples:
[2026-02-17 10:00:01] INFO   WEATHER   Fetched NWS forecast for NYC         {"city":"NYC","high_f":55,"source":"NWS","model_run":"2026-02-17T06:00Z"}
[2026-02-17 10:00:02] INFO   WEATHER   Fetched Open-Meteo ensemble for NYC  {"city":"NYC","high_f":53.8,"models":["GFS","ECMWF","ICON"],"source":"Open-Meteo"}
[2026-02-17 10:00:03] INFO   MODEL     Generated bracket probabilities      {"city":"NYC","brackets":[8,15,28,31,12,6],"confidence":"HIGH"}
[2026-02-17 10:00:04] INFO   MARKET    Fetched Kalshi market prices          {"city":"NYC","prices":[0.05,0.12,0.22,0.35,0.18,0.08],"event":"KXHIGHNY-26FEB17"}
[2026-02-17 10:00:04] INFO   TRADING   EV calculation complete               {"city":"NYC","bracket":3,"model_prob":0.28,"market_price":0.22,"ev":0.06,"action":"BUY_YES"}
[2026-02-17 10:00:05] INFO   ORDER     Placed limit order on Kalshi          {"city":"NYC","side":"YES","bracket":"53-54°F","price":0.22,"qty":1,"order_id":"abc123"}
[2026-02-17 10:00:05] INFO   RISK      Position update                       {"daily_exposure":0.22,"max_daily":25.00,"pct_used":"0.9%"}
[2026-02-17 10:00:05] WARN   RISK      Approaching daily limit               {"daily_exposure":22.50,"max_daily":25.00,"pct_used":"90%"}
[2026-02-17 10:00:06] ERROR  KALSHI    Order rejected by Kalshi              {"order_id":"abc123","reason":"insufficient_balance","kalshi_error_code":"ERR_402"}
[2026-02-17 10:00:06] INFO   COOLDOWN  Cooldown activated                    {"trigger":"consecutive_losses","count":3,"pause_until":"2026-02-18T00:00:00"}
```

**Log Levels:**
| Level | When Used |
|-------|-----------|
| DEBUG | Detailed internal state (only in development) |
| INFO | Normal operations: data fetched, predictions made, trades placed |
| WARN | Approaching limits, stale data, degraded performance |
| ERROR | Failed operations: API errors, order rejections, data fetch failures |
| CRITICAL | System-breaking issues: database down, all APIs unreachable, risk limit breach |

**Log Modules:**
| Module Tag | What It Covers |
|------------|---------------|
| WEATHER | NWS/Open-Meteo data fetching, parsing, storage |
| MODEL | Prediction engine, probability calculations, ensemble weighting |
| MARKET | Kalshi market data fetching, bracket discovery, price snapshots |
| TRADING | EV calculations, trade decisions, queue management |
| ORDER | Order placement, fills, cancellations on Kalshi |
| RISK | Position limits, daily loss tracking, cooldown activation/reset |
| COOLDOWN | Cooldown timer start/stop/reset events |
| AUTH | API key validation, session management (never logs key values) |
| SETTLE | NWS CLI report fetching, settlement processing, P&L calculation |
| POSTMORTEM | Trade post-mortem generation |
| SYSTEM | Docker health, scheduler status, database connectivity |

### 8.4 Log Viewer in Dashboard

The PWA dashboard includes a **Log Viewer** page where users can:
- View real-time logs as they stream in
- Filter by module (WEATHER, TRADING, ORDER, etc.)
- Filter by level (show only WARN + ERROR)
- Filter by time range
- Search log messages
- Export logs as CSV/JSON for debugging

### 8.5 CI/CD Pipeline

Tests run automatically on every commit via GitHub Actions:

```
On every push / PR:
  1. Lint: ruff (Python) + ESLint (TypeScript)
  2. Unit tests: pytest (backend) + Jest (frontend)
  3. Integration tests: docker-compose up test containers
  4. Safety tests: run full safety test suite
  5. Coverage report: fail if below thresholds (80% backend, 70% frontend)

On merge to main:
  6. Build Docker images
  7. Run simulation test against 7 days of historical data
  8. Tag release if all pass
```

### 8.6 Testing Requirements Per Agent

Each sub-agent must deliver code WITH passing tests. This is the definition of "done":

| Agent | Code Deliverable | Test Deliverable |
|-------|-----------------|-----------------|
| **Agent 1** (Weather) | `backend/weather/` | `tests/weather/` — unit tests for all fetchers, parsers, normalizers |
| **Agent 2** (Kalshi) | `backend/kalshi/` | `tests/kalshi/` — unit tests for auth, client methods, error handling |
| **Agent 3** (Prediction) | `backend/prediction/` | `tests/prediction/` — unit tests for models, bracket calculator, ensemble |
| **Agent 4** (Trading) | `backend/trading/` | `tests/trading/` — unit tests for EV calc, risk controls, cooldown, trade queue + safety tests |
| **Agent 5** (Frontend) | `frontend/` | `frontend/__tests__/` — component tests, flow tests, API mocking |
| **Integration** (me) | Wiring + Docker | `tests/integration/` — cross-module tests, simulation test |

---

## 9. Success Metrics

| Metric | Target | Measurement |
|--------|--------|-------------|
| Model accuracy (bracket hit rate) | > 40% (vs ~16.7% random) | % of times the correct bracket was predicted as most likely |
| Positive EV trades | > 60% of trades should be +EV in retrospect | Backtest + live tracking |
| User P&L | Positive over 30-day rolling window | Aggregate across users (anonymized) |
| System uptime | > 99.5% | Monitoring |
| Trade execution latency | < 2 seconds from signal to order placed | Logging |
| Data freshness | Weather data < 30 min old at time of trade | Timestamp tracking |
| PWA install rate | > 30% of active users | Analytics |
| Manual mode response time | < 15 min avg approval time | Trade queue metrics |

---

## 10. Decisions Made

| Question | Decision | Rationale |
|----------|----------|-----------|
| Product name | **Boz Weather Trader** | — |
| Business model | Free, open-source | Lower barrier to entry, community-driven |
| Platform | PWA (not native iPhone app) | Cross-platform, no App Store hassle, one codebase |
| Demo mode | **Implemented** (Phase 15) | New users start in demo mode by default; togglable in settings |
| Hosting | Docker Compose (self-host) + cloud deploy options (free & paid) | Homelab-friendly + accessible to non-technical users |
| MVP market scope | High temperature only (4 cities — all Kalshi currently offers) | Best liquidity, clearest pipeline; modular for future expansion |
| Trading mode | Toggle: Full Auto or Manual Approval | Each user picks their comfort level |
| Default trade size | $1 per trade | Conservative default for safety |
| Authentication | RSA API key pair only (no email/password) | Most secure — app never touches user's Kalshi password |
| Cooldown periods | User-adjustable (0/off to 24 hours per loss, consecutive loss threshold adjustable) | Flexibility for different risk tolerances |
| Trade post-mortems | Auto-generated after every settlement | Transparency — users understand why trades won or lost |
| Testing strategy | Tests required with every module; 4 test layers; CI/CD pipeline | Trading bot — bugs cost real money. No code ships without tests. |
| Logging | Structured, module-tagged logs to stdout + DB; log viewer in dashboard | Full auditability and debugging for every trade decision |

---

## 11. Resolved Questions

1. **Kalshi API tier**: Basic tier is sufficient — no Premier tier needed.
2. **Multi-user on single instance**: One instance per user. Each user provides their own Kalshi API key. No centralized user data storage.
3. **Liability**: Not a concern — each user sets up the bot on their own infrastructure. The project does not store user data centrally.
4. **Kalshi ToS**: Kalshi allows third-party bots/automated trading.

---

## 12. Risks & Mitigations

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| Model underperforms → user losses | High | Medium | Backtesting, conservative defaults ($1 trades), loss limits, adjustable cooldowns |
| Kalshi API changes or rate limits | Medium | Low | Abstract API layer, monitor changelog |
| NWS data delays or errors | High | Low | Fallback to Open-Meteo, alert user, pause trading |
| Weather model disagreement | Medium | Medium | Ensemble approach, flag low-confidence in post-mortem |
| Apple blocks PWA features | Low | Low | PWA push works on iOS 16.4+; fallback to email alerts |
| Regulatory changes | High | Low | Stay compliant with CFTC, monitor Kalshi ToS |
| Low liquidity in markets | Medium | Medium | Limit orders only, don't force fills |
| Self-hosted instance goes down | Medium | Medium | Health check alerts, Docker restart policies |

---

## 13. Development Strategy

### 13.1 Sub-Agent Architecture (Claude Code)

This project is well-suited for **parallel development using Claude Code sub-agents**. The codebase has clearly separable, independent modules with clean interfaces between them.

**Recommended Agent Breakdown:**

| Agent | Module | What It Builds | Dependencies |
|-------|--------|---------------|-------------|
| **Agent 1** | Weather Data Pipeline | NWS + Open-Meteo fetchers, data normalization, storage | None — can start immediately |
| **Agent 2** | Kalshi API Client | Auth (RSA signing), market data, order placement, WebSocket | None — can start immediately |
| **Agent 3** | Prediction Engine | Statistical ensemble, bracket probability calculator, post-mortem data | Needs Agent 1's data format (interface contract) |
| **Agent 4** | Trading Engine | EV calculator, risk controls, cooldowns, order logic, trade queue | Needs Agent 2's API client (interface contract) |
| **Agent 5** | Frontend (PWA) | Dashboard, onboarding, trade queue, post-mortems, settings | Needs backend API contracts (can start with mocks) |

**Parallelization Strategy:**
```
Week 1-2:  Agent 1 (Weather) + Agent 2 (Kalshi) → run in parallel
Week 3-4:  Agent 3 (Prediction) + Agent 4 (Trading) → run in parallel
           (consume outputs from Agents 1 & 2)
Week 5-6:  Agent 5 (Frontend) → builds against backend APIs
Week 7+:   Integration, testing, Docker setup
```

**Why this works:** Each module communicates through well-defined interfaces (function signatures, data schemas, API contracts). We define those contracts upfront, then each agent builds its module independently. Integration happens when the pieces snap together.

**Interface Contracts (defined before coding begins):**
- Weather Data → Prediction Engine: `WeatherData` schema (temps, humidity, wind, model source, timestamp)
- Kalshi Client → Trading Engine: `KalshiClient` class interface (get_markets, place_order, get_positions)
- Backend → Frontend: REST API spec (OpenAPI/Swagger, auto-generated from FastAPI)
- Trading Engine → Trade Post-Mortem: `TradeRecord` schema (all data needed to generate the summary)

### 13.2 Milestones & Timeline (Estimated)

#### Phase 1: MVP
- **Week 1-2**: Project setup, Docker Compose, interface contracts, Agents 1+2 (Weather + Kalshi)
- **Week 3-4**: Agents 3+4 (Prediction + Trading), data storage
- **Week 5-6**: Agent 5 (Frontend PWA — dashboard, onboarding, trade queue, post-mortems)
- **Week 7-8**: Integration, risk controls, cooldown logic
- **Week 9-10**: Push notifications, testing, bug fixes, Docker deployment, README

#### Phase 2: Enhanced
- **Week 11-14**: XGBoost ML model, performance analytics, backtesting module
- **Week 15-18**: Kelly sizing, additional market plugins (precipitation, snow), one-click cloud deploy

---

*This is a living document. It will be updated as the project evolves.*
