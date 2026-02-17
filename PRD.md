# Product Requirements Document (PRD)
# Kalshi Weather Trading Bot

**Version:** 0.1 (Draft)
**Date:** February 17, 2026
**Status:** Draft - Pending Review

---

## 1. Overview

### 1.1 Problem Statement
Kalshi offers daily weather prediction markets (high temperature) for 4 major US cities. These markets are highly data-driven — settlement is based on the NWS Daily Climate Report, and weather forecasts from models like GFS, ECMWF, and HRRR are strong predictors of outcomes. Despite this, most retail traders on Kalshi trade manually, relying on gut feel or basic weather app checks. There is an opportunity to build an automated trading bot that leverages weather forecast data and ML models to identify mispriced contracts and execute trades programmatically.

### 1.2 Product Vision
A web-based weather trading bot that any user can log into with their Kalshi account credentials (API keys), configure their risk preferences, and let it automatically analyze weather markets and execute trades on their behalf. The bot will combine multiple weather data sources, use statistical/ML models to generate probability distributions for temperature outcomes, compare those to market prices, and trade when it finds edge.

### 1.3 Target Users
- Retail Kalshi traders interested in weather markets who want automated execution
- Data-savvy traders who want to leverage weather models without building infrastructure
- Hobbyist traders looking for a hands-off approach to weather market trading

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

---

## 3. Technical Architecture

### 3.1 High-Level System Design

```
+-------------------+     +------------------+     +------------------+
|   Web Frontend    |<--->|   Backend API    |<--->|   Kalshi API     |
|   (Dashboard)     |     |   (Core Logic)   |     |   (Trading)      |
+-------------------+     +------------------+     +------------------+
                                  |
                          +-------+--------+
                          |                |
                   +------+------+  +------+------+
                   | Weather     |  | ML/Stats    |
                   | Data Layer  |  | Engine      |
                   +-------------+  +-------------+
                          |
              +-----------+-----------+
              |           |           |
        +-----+---+ +----+----+ +----+----+
        |  NWS    | | Open-   | | ECMWF/  |
        |  API    | | Meteo   | | GFS     |
        +---------+ +---------+ +---------+
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
2. **XGBoost Model**: Trained on historical weather data to predict next-day tmax
   - Features: historical temps, cloud cover, wind, humidity, season, etc.
   - Hyperparameter tuning via grid search / Bayesian optimization
3. **Probability Distribution Generator**: Convert point forecast into probability distribution across Kalshi brackets
   - Use historical forecast error distribution (how often is NWS off by X degrees?)
   - Generate P(temp in bracket) for each of the 6 brackets
4. **Model Calibration**: Backtest against historical NWS CLI reports to calibrate confidence

**Key Outputs:**
- Probability estimate for each bracket (must sum to ~100%)
- Confidence interval / uncertainty measure
- Comparison to market-implied probabilities (contract prices)
- Expected value calculation per contract

#### 3.2.3 Trading Engine
**Strategy Logic:**
1. Fetch current market prices for all brackets in all 4 cities
2. Compare model probabilities to market-implied probabilities
3. Calculate expected value (EV) for each potential trade:
   - `EV = (model_prob * payout) - (contract_price) - fees`
4. Execute trades where EV exceeds user-defined threshold
5. Position sizing based on Kelly Criterion or user-defined limits

**Order Execution:**
- Use Kalshi REST API for order placement
- Support limit orders (preferred) and market orders
- WebSocket connection for real-time price updates
- Batch order support (up to 20 per request)

**Risk Management:**
- Maximum position size per market (user-configurable)
- Maximum daily loss limit
- Maximum exposure across all markets
- Minimum EV threshold to trigger a trade
- Cooldown period after losses

#### 3.2.4 Backend API Server
- RESTful API serving the frontend
- User session management (stores encrypted Kalshi API keys)
- Scheduling: cron jobs for data fetching, model runs, and trade execution
- Logging and audit trail for all trades
- Database for historical data, predictions, and trade records

#### 3.2.5 Web Frontend (Dashboard)
- **Login**: User provides their Kalshi API key pair (public + private RSA key)
- **Dashboard**: Overview of active positions, P&L, model predictions
- **Markets View**: Current weather markets with model probabilities vs. market prices
- **Settings**: Risk parameters, trading preferences, city selection
- **Trade History**: Full audit log of all executed trades with reasoning
- **Performance**: Charts showing cumulative P&L, accuracy metrics, ROI

### 3.3 Tech Stack (Proposed)

| Layer | Technology | Rationale |
|-------|-----------|-----------|
| Frontend | Next.js + React + Tailwind CSS | Modern, fast, great DX |
| Backend | Python (FastAPI) | Best ML/data science ecosystem, async support |
| Database | PostgreSQL + Redis | Relational data + caching/queues |
| ML | XGBoost, scikit-learn, pandas | Proven for tabular data / time-series |
| Task Queue | Celery + Redis | Scheduled jobs, async model runs |
| Deployment | Docker + cloud hosting (TBD) | Portable, scalable |
| Auth | Kalshi API keys (user-provided) | No password storage needed |

---

## 4. Feature Requirements

### 4.1 MVP (Phase 1)

#### P0 - Must Have
- [ ] **User authentication via Kalshi API keys** - User pastes their API key pair, we validate against Kalshi API, store encrypted
- [ ] **Weather data pipeline** - Automated fetching from NWS API + Open-Meteo on a schedule
- [ ] **Basic prediction model** - Ensemble of NWS forecast + Open-Meteo models to generate bracket probabilities
- [ ] **EV calculation engine** - Compare model probabilities to market prices, identify +EV trades
- [ ] **Automated trade execution** - Place limit orders on Kalshi when EV threshold is met
- [ ] **Basic dashboard** - Show active markets, model predictions, current positions, P&L
- [ ] **Risk controls** - Max position size, daily loss limit, min EV threshold
- [ ] **Trade logging** - Full audit trail of every trade placed with reasoning

#### P1 - Should Have
- [ ] **Multi-city support** - Trade all 4 cities (NYC, Chicago, Miami, Austin) simultaneously
- [ ] **Real-time price updates** - WebSocket connection to Kalshi for live orderbook data
- [ ] **Backtesting module** - Test strategy against historical data before going live
- [ ] **Performance analytics** - Cumulative P&L charts, win rate, ROI per city
- [ ] **Manual override** - User can approve/reject trades before execution

### 4.2 Phase 2 (Post-MVP)

#### P1 - Should Have
- [ ] **XGBoost ML model** - Trained on historical data for improved predictions
- [ ] **Multiple model ensemble** - Combine statistical + ML models with weighted voting
- [ ] **Kelly Criterion position sizing** - Optimal bet sizing based on edge and bankroll
- [ ] **Alerting system** - Email/push notifications for trades placed, large market moves, settlement results
- [ ] **Historical forecast accuracy tracking** - Monitor model calibration over time

#### P2 - Nice to Have
- [ ] **Additional weather markets** - Precipitation, snowfall, low temperature (if Kalshi adds them)
- [ ] **Market maker mode** - Two-sided quoting for advanced users
- [ ] **Social/leaderboard** - Compare performance with other users (opt-in)
- [ ] **Mobile-responsive dashboard** - Full functionality on mobile devices
- [ ] **Webhook integrations** - Discord/Slack notifications

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
  10:05 AM  - Execute initial trades where EV > threshold

Ongoing (D-1 afternoon → D-day):
  Every 30m - Re-fetch weather data (model updates, new observations)
  Every 30m - Re-run predictions if data materially changed
  Every 15m - Check market prices, execute if new +EV opportunities

Day Of (D-day):
  Morning   - Monitor any final trading opportunities
  Market Close - No more trades possible

Day After (D+1):
  ~08:00 AM - NWS publishes Daily Climate Report (CLI)
  ~09:00 AM - Kalshi settles markets based on CLI
  ~09:30 AM - Record settlement, update P&L, log model accuracy
```

### 5.2 Data Storage

| Data Type | Storage | Retention |
|-----------|---------|-----------|
| Weather forecasts | PostgreSQL | 1 year |
| Model predictions | PostgreSQL | Indefinite |
| Trade history | PostgreSQL | Indefinite |
| Market prices (snapshots) | PostgreSQL | 6 months |
| Real-time orderbook | Redis (cache) | Current day |
| User API keys | PostgreSQL (encrypted) | While active |
| NWS CLI reports | PostgreSQL | Indefinite |

---

## 6. API Integrations

### 6.1 Kalshi API
- **Auth**: RSA key-pair based authentication
- **REST API**: Market data, order placement, portfolio management
- **WebSocket**: Real-time orderbook, fills, positions
- **Rate limits**: Tier-dependent (to be documented per tier)
- **Demo environment**: Available for testing before live trading
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
- HTTPS everywhere
- Keys transmitted only to Kalshi API, never to third parties
- Session management with secure tokens
- Rate limiting on our API to prevent abuse

### 7.2 Compliance Considerations
- Kalshi is CFTC-regulated — the bot must comply with Kalshi's Terms of Service
- Users must accept Kalshi's Developer Agreement to use API
- Bot should include disclaimers: not financial advice, past performance doesn't guarantee future results
- Users are responsible for their own trading activity and tax obligations
- Must respect Kalshi's API rate limits and usage policies

### 7.3 Risk Disclaimers (Required)
- Trading involves risk of loss
- Automated trading amplifies both gains and losses
- Weather prediction is inherently uncertain
- Past model performance is not indicative of future results
- Users should only trade with money they can afford to lose

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

---

## 9. Open Questions

1. **Pricing model**: Free? Subscription? Revenue share on profits?
2. **Hosting**: Who pays for infrastructure? Self-hosted option?
3. **Kalshi API tier**: Do users need Premier tier for full API access, or does basic work?
4. **Multi-user architecture**: Shared model predictions, individual trading? Or fully isolated per user?
5. **Liability**: Legal structure around providing automated trading tools?
6. **Additional markets**: Should we support non-temperature weather markets (rain, snow) from day 1?
7. **Mobile**: Is a mobile app needed, or is responsive web sufficient?
8. **Demo mode**: Should we offer paper trading using Kalshi's demo API before users go live?

---

## 10. Risks & Mitigations

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| Model underperforms → user losses | High | Medium | Backtesting, conservative defaults, loss limits |
| Kalshi API changes or rate limits | Medium | Low | Abstract API layer, monitor changelog |
| NWS data delays or errors | High | Low | Fallback to Open-Meteo, alert user |
| Weather model disagreement | Medium | Medium | Ensemble approach, flag low-confidence |
| User stores weak API keys | Medium | Medium | Validation on key entry, security best practices |
| Regulatory changes | High | Low | Stay compliant with CFTC, monitor Kalshi ToS |
| Low liquidity in markets | Medium | Medium | Limit order only, don't force fills |

---

## 11. Milestones & Timeline (Estimated)

### Phase 1: MVP
- **Week 1-2**: Project setup, Kalshi API integration, basic authentication
- **Week 3-4**: Weather data pipeline (NWS + Open-Meteo)
- **Week 5-6**: Prediction model (statistical ensemble)
- **Week 7-8**: Trading engine + risk controls
- **Week 9-10**: Frontend dashboard (basic)
- **Week 11-12**: Testing, backtesting, bug fixes, deployment

### Phase 2: Enhanced
- **Week 13-16**: XGBoost ML model, performance analytics, alerting
- **Week 17-20**: Kelly sizing, market maker mode, mobile responsive

---

*This is a living document. It will be updated as decisions are made on open questions and as the project evolves.*
