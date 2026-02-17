# Product Requirements Document (PRD)
# Kalshi Weather Trading Bot

**Version:** 0.3
**Date:** February 17, 2026
**Status:** Draft - In Review

---

## 1. Overview

### 1.1 Problem Statement
Kalshi offers daily weather prediction markets (high temperature) for 4 major US cities. These markets are highly data-driven — settlement is based on the NWS Daily Climate Report, and weather forecasts from models like GFS, ECMWF, and HRRR are strong predictors of outcomes. Despite this, most retail traders on Kalshi trade manually, relying on gut feel or basic weather app checks. There is an opportunity to build an automated trading bot that leverages weather forecast data and ML models to identify mispriced contracts and execute trades programmatically.

### 1.2 Product Vision
A free, self-hostable weather trading bot delivered as a Progressive Web App (PWA). Users connect their Kalshi account via API keys, configure risk preferences and trading mode (manual approval or full auto), and let the bot analyze weather markets and execute trades on their behalf. The bot combines multiple weather data sources, uses statistical/ML models to generate probability distributions for temperature outcomes, compares those to market prices, and trades when it finds edge.

### 1.3 Target Users
- Retail Kalshi traders interested in weather markets who want automated execution
- Data-savvy traders who want to leverage weather models without building infrastructure
- Hobbyist traders looking for a hands-off approach to weather market trading
- Mobile-first users who want to monitor trades from their phone

### 1.4 Business Model
**Free and open-source.** No subscription, no revenue share. Users provide their own Kalshi API keys and are responsible for their own trading capital and outcomes.

### 1.5 Distribution Strategy
- **Primary**: Docker Compose — self-host on any machine (homelab, VPS, cloud)
- **Secondary**: One-click deploy templates for Railway / Fly.io / DigitalOcean ($5-10/mo)
- **Frontend**: Progressive Web App (PWA) — installable on iPhone/Android home screen, push notifications, works offline for cached data, no App Store approval needed
- **Future**: Native app wrapper (React Native) if demand warrants it

---

## 2. Market Context

### 2.1 Kalshi Weather Markets Structure

**Cities & Tickers:**
| City | Event Ticker | NWS Station | Resolution Location |
|------|-------------|-------------|-------------------|
| New York City | KXHIGHNY | KNYC | Central Park |
| Chicago | KXHIGHCHI | KMDW | Midway Airport |
| Miami | KXHIGHMIA | KMIA | Miami Intl Airport |
| Austin | KXHIGHAUS | KAUS | Bergstrom Intl Airport |

**Bracket Structure:**
- 6 brackets per event (per city per day)
- Middle 4 brackets: each spans 2 degrees Fahrenheit
- 2 edge brackets: catch-all for temps above/below the middle range
- Brackets are usually centered around the forecast high

**Market Timing:**
- Markets launch at **10:00 AM ET** the day before the event
- Markets close on the event day (exact time TBD per market)
- Settlement occurs the following morning based on the NWS Daily Climate Report

**Contract Mechanics:**
- Binary contracts: pays $1 if the official high falls in the stated range, $0 otherwise
- Contract prices range $0.01 - $0.99 (representing implied probability)
- Can buy YES (it happens) or NO (it doesn't)

**Settlement Source:**
- **Only** the NWS Daily Climate Report (CLI) is used
- Measurement period: 12:00 AM - 11:59 PM **Local Standard Time** (not daylight saving)
- Important: During DST, the high occurs between 1:00 AM and 12:59 AM local time the following day

### 2.2 Fee Structure
- Trading fee: ~1% per trade
- Settlement fee: ~10% of profit
- Withdrawal fee: ~2%

### 2.3 Available Market Types (Roadmap)

| Market Type | Status | MVP? | Notes |
|------------|--------|------|-------|
| **Daily High Temperature** | Active on Kalshi | **YES** | 4 cities, best liquidity, clearest data pipeline |
| Daily Low Temperature | TBD on Kalshi | No | Coming Soon — add when available |
| Daily Precipitation | TBD on Kalshi | No | Coming Soon — different data sources needed |
| Snowfall | Seasonal on Kalshi | No | Coming Soon — winter only |
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
        │   - Settings / risk config  │
        └──────────────┬──────────────┘
                       │ REST API
        ┌──────────────▼──────────────┐
        │    Python Backend (FastAPI) │
        │   - User session mgmt      │
        │   - Trading engine          │
        │   - EV calculator           │
        │   - Risk management         │
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

**Risk Management:**
- Maximum position size per market (user-configurable, default: $1 per trade for safety)
- Maximum daily loss limit (user-configurable)
- Maximum exposure across all markets
- Minimum EV threshold to trigger a trade
- Cooldown period after losses
- Conservative defaults for new users (small position sizes)

#### 3.2.4 Backend API Server
- RESTful API serving the frontend
- User session management (stores encrypted Kalshi API keys)
- Scheduling: Celery beat for data fetching, model runs, and trade execution
- Logging and audit trail for all trades
- Database for historical data, predictions, and trade records
- Web push notification service for trade alerts

#### 3.2.5 Web Frontend (PWA Dashboard)
- **Onboarding**: Step-by-step guided flow to connect Kalshi account (see Section 3.5)
- **Dashboard**: Overview of active positions, P&L, model predictions
- **Markets View**: Market type selector (high temp active, others "Coming Soon"), current markets with model probabilities vs. market prices
- **Trade Queue**: Pending trades awaiting approval (in Manual mode)
- **Settings**: Trading mode toggle (auto/manual), risk parameters, city selection, notification preferences
- **Trade History**: Full audit log of all executed trades with reasoning
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
git clone https://github.com/aclarkson2013/kalshi-weather-bot.git
cd kalshi-weather-bot
cp .env.example .env  # Configure your settings
docker-compose up -d
# Access at http://localhost:3000
```
- Perfect for homelabs, Raspberry Pi, VPS
- Full control over data
- Zero recurring cost (besides electricity)

#### Option B: One-Click Cloud Deploy
- **Railway**: One-click deploy button in README
- **Fly.io**: `fly launch` from repo
- **DigitalOcean App Platform**: App spec included
- Estimated cost: $5-15/month depending on provider

### 3.5 Authentication & Onboarding Flow

**Method: RSA API Key Pair only (no email/password)**

Our app never handles Kalshi passwords. Users generate API keys on Kalshi's website and paste them into our app. This is the most secure approach — our server only ever sees the API key, never the user's login credentials.

**Onboarding Steps (guided in-app):**

```
Step 1: Welcome Screen
  "Connect your Kalshi account to start trading weather markets."
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
  [Start Trading]
```

**Key Security Decisions:**
- RSA private keys are encrypted with AES-256 before storage
- Keys are only decrypted in-memory when making Kalshi API calls
- Private keys are never logged, never sent to our frontend, never exposed in API responses
- Users can revoke keys anytime on Kalshi's website (instant kill switch)
- Session tokens for our app are separate from Kalshi API keys

---

## 4. Feature Requirements

### 4.1 MVP (Phase 1)

#### P0 - Must Have
- [ ] **Guided onboarding flow** - Step-by-step walkthrough to generate RSA keys on Kalshi and connect account (see Section 3.5)
- [ ] **RSA API key validation & encrypted storage** - Validate key pair against Kalshi API, store private key AES-256 encrypted, never handle user passwords
- [ ] **Weather data pipeline** - Automated fetching from NWS API + Open-Meteo on a schedule
- [ ] **Basic prediction model** - Ensemble of NWS forecast + Open-Meteo models to generate bracket probabilities
- [ ] **EV calculation engine** - Compare model probabilities to market prices, identify +EV trades
- [ ] **Trading mode toggle** - User chooses Full Auto or Manual Approval mode
- [ ] **Automated trade execution** (Full Auto mode) - Place limit orders on Kalshi when EV threshold is met
- [ ] **Trade approval queue** (Manual mode) - Queue trades for user review with push notification
- [ ] **Basic PWA dashboard** - Show active markets, model predictions, current positions, P&L
- [ ] **Risk controls** - Max position size (default $1), daily loss limit, min EV threshold
- [ ] **Trade logging** - Full audit trail of every trade placed with reasoning
- [ ] **Docker Compose deployment** - One-command self-hosted setup
- [ ] **Market type selector UI** - High Temp active, others show "Coming Soon"

#### P1 - Should Have
- [ ] **Multi-city support** - Trade all 4 cities (NYC, Chicago, Miami, Austin) simultaneously
- [ ] **Real-time price updates** - WebSocket connection to Kalshi for live orderbook data
- [ ] **Push notifications** - Web push for trade executions, settlements, alerts
- [ ] **Performance analytics** - Cumulative P&L charts, win rate, ROI per city
- [ ] **PWA install prompt** - Encourage users to add to home screen
- [ ] **One-click cloud deploy** - Railway / Fly.io deploy buttons in README

### 4.2 Phase 2 (Post-MVP)

#### P1 - Should Have
- [ ] **XGBoost ML model** - Trained on historical data for improved predictions
- [ ] **Multiple model ensemble** - Combine statistical + ML models with weighted voting
- [ ] **Kelly Criterion position sizing** - Optimal bet sizing based on edge and bankroll
- [ ] **Backtesting module** - Test strategy against historical data
- [ ] **Historical forecast accuracy tracking** - Monitor model calibration over time

#### P2 - Nice to Have
- [ ] **Additional market plugins** - Precipitation, snowfall, low temperature
- [ ] **Market maker mode** - Two-sided quoting for advanced users
- [ ] **Webhook integrations** - Discord/Slack notifications
- [ ] **Social/leaderboard** - Compare performance with other users (opt-in)
- [ ] **Native mobile wrapper** - React Native shell if PWA demand warrants it

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
             → Push notification: "Yesterday's results: +$X.XX"
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

### 5.3 Data Storage

| Data Type | Storage | Retention |
|-----------|---------|-----------|
| Weather forecasts | PostgreSQL | 1 year |
| Model predictions | PostgreSQL | Indefinite |
| Trade history | PostgreSQL | Indefinite |
| Market prices (snapshots) | PostgreSQL | 6 months |
| Real-time orderbook | Redis (cache) | Current day |
| User API keys | PostgreSQL (encrypted AES-256) | While active |
| NWS CLI reports | PostgreSQL | Indefinite |
| Trade approval queue | Redis + PostgreSQL | 24 hours (Redis) / Indefinite (PG) |
| Push notification subscriptions | PostgreSQL | While active |

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

## 8. Success Metrics

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

## 9. Decisions Made

| Question | Decision | Rationale |
|----------|----------|-----------|
| Business model | Free, open-source | Lower barrier to entry, community-driven |
| Platform | PWA (not native iPhone app) | Cross-platform, no App Store hassle, one codebase |
| Demo mode | Skip | Owner will test with small trades ($1) on live markets |
| Hosting | Docker Compose (self-host) + cloud deploy options | Homelab-friendly + accessible to non-technical users |
| MVP market scope | High temperature only (4 cities) | Best liquidity, clearest pipeline; modular for future expansion |
| Trading mode | Toggle: Full Auto or Manual Approval | Each user picks their comfort level |
| Default trade size | $1 per trade | Conservative default for safety |
| Authentication | RSA API key pair only (no email/password) | Most secure — app never touches user's Kalshi password. Users generate keys on Kalshi's site and paste into our app. |

---

## 10. Remaining Open Questions

1. **Kalshi API tier**: Do users need Premier tier for full API access, or does basic work? Need to verify.
2. **Multi-user on single instance**: If self-hosting, should one Docker instance support multiple users, or is it one-instance-per-user?
3. **Liability**: Any legal considerations for distributing an open-source automated trading tool?
4. **Kalshi ToS**: Does Kalshi's ToS allow third-party bots? Need to confirm.

---

## 11. Risks & Mitigations

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| Model underperforms → user losses | High | Medium | Backtesting, conservative defaults ($1 trades), loss limits |
| Kalshi API changes or rate limits | Medium | Low | Abstract API layer, monitor changelog |
| NWS data delays or errors | High | Low | Fallback to Open-Meteo, alert user, pause trading |
| Weather model disagreement | Medium | Medium | Ensemble approach, flag low-confidence |
| Apple blocks PWA features | Low | Low | PWA push works on iOS 16.4+; fallback to email alerts |
| Regulatory changes | High | Low | Stay compliant with CFTC, monitor Kalshi ToS |
| Low liquidity in markets | Medium | Medium | Limit orders only, don't force fills |
| Self-hosted instance goes down | Medium | Medium | Health check alerts, Docker restart policies |

---

## 12. Milestones & Timeline (Estimated)

### Phase 1: MVP
- **Week 1-2**: Project setup, Docker Compose, Kalshi API integration, API key onboarding
- **Week 3-4**: Weather data pipeline (NWS + Open-Meteo), data storage
- **Week 5-6**: Prediction model (statistical ensemble), bracket probability engine
- **Week 7-8**: Trading engine, EV calculator, risk controls, auto/manual toggle
- **Week 9-10**: Next.js PWA frontend (dashboard, trade queue, settings, market selector)
- **Week 11-12**: Push notifications, testing, bug fixes, Docker deployment, README

### Phase 2: Enhanced
- **Week 13-16**: XGBoost ML model, performance analytics, backtesting module
- **Week 17-20**: Kelly sizing, additional market plugins (precipitation, snow), one-click cloud deploy

---

*This is a living document. It will be updated as the project evolves.*
