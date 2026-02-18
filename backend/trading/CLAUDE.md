# Agent 4: Trading Engine

## Your Mission

Build the trading decision engine: EV calculation, risk management, cooldown logic, trade queue (for manual approval mode), and trade execution orchestration. You are the gatekeeper — you decide what trades happen and enforce all safety limits.

## What You Build

```
backend/trading/
├── __init__.py
├── ev_calculator.py   → Expected value calculation for each bracket
├── risk_manager.py    → Position limits, daily loss, exposure tracking
├── cooldown.py        → Cooldown timer logic (per-loss and consecutive)
├── trade_queue.py     → Trade approval queue for manual mode
├── executor.py        → Trade execution orchestrator (auto + manual modes)
├── postmortem.py      → Generate full trade post-mortem after settlement
├── scheduler.py       → Celery tasks for trading cycle
└── exceptions.py      → Trading-specific exceptions
```

## Dependencies

- **Input from Agent 3 (Prediction):** `BracketPrediction` objects (probability per bracket)
- **Input from Agent 2 (Kalshi):** `KalshiMarket` objects (current prices), `KalshiClient` (for placing orders)
- **User Settings:** Trading mode, max trade size, risk limits, cooldown config

## EV Calculation

For each bracket in each city:

```
EV = (model_probability * $1.00) - contract_price - estimated_fees

Example:
  Model says 28% chance for Bracket 3
  Market price: $0.22 (market thinks 22%)
  Fees: ~$0.01

  EV = (0.28 * 1.00) - 0.22 - 0.01 = +$0.05 per contract

  If EV > user's minimum threshold → signal a trade
```

**Also calculate EV for NO side:**
```
  NO price = 1.00 - YES price = $0.78
  Model prob of NOT bracket 3 = 1.0 - 0.28 = 0.72
  EV(NO) = (0.72 * 1.00) - 0.78 - 0.01 = -$0.07 → NOT a trade
```

Always check both YES and NO for every bracket — sometimes the NO side has better EV.

## Risk Management

All limits are user-configurable with safe defaults:

| Risk Control | Default | Range | Description |
|-------------|---------|-------|-------------|
| Max trade size | $1.00 | $0.01 - $100 | Maximum cost per individual trade |
| Daily loss limit | $10.00 | $1 - $1000 | Stop trading after this much loss in one day |
| Max daily exposure | $25.00 | $1 - $5000 | Total capital at risk across all open positions |
| Min EV threshold | 5% | 1% - 50% | Minimum expected value to trigger a trade |
| Cooldown per loss | 60 min | 0 (off) - 1440 min (24h) | Pause after each losing trade |
| Consecutive loss limit | 3 | 0 (off) - 10 | Pause for rest of day after N losses in a row |

**Risk checks happen BEFORE every trade, no exceptions:**
1. Is cooldown active? → BLOCK
2. Would this trade exceed max trade size? → BLOCK
3. Would this trade push daily exposure over limit? → BLOCK
4. Has daily loss limit been hit? → BLOCK
5. Is the EV above minimum threshold? → If no, SKIP
6. All checks pass → PROCEED

## Cooldown Logic

```python
# Per-loss cooldown
on_trade_loss(trade):
    if settings.cooldown_per_loss > 0:
        cooldown_until = now() + timedelta(minutes=settings.cooldown_per_loss)
        log(COOLDOWN, "Cooldown activated", {"until": cooldown_until})

# Consecutive loss cooldown
on_trade_loss(trade):
    consecutive_losses += 1
    if consecutive_losses >= settings.consecutive_loss_limit:
        cooldown_until = end_of_trading_day()
        log(COOLDOWN, "Consecutive loss limit hit", {"count": consecutive_losses})

# Reset
on_trade_win(trade):
    consecutive_losses = 0

# Check
is_cooldown_active() -> bool:
    return now() < cooldown_until
```

## Trade Queue (Manual Approval Mode)

When trading mode is "manual":
1. Bot identifies +EV trade
2. Create `PendingTrade` record in database (status: PENDING)
3. Send push notification to user with trade details
4. User sees trade in PWA dashboard trade queue
5. User taps Approve → bot executes via Kalshi client
6. User taps Reject → trade marked REJECTED, logged
7. Trade expires after configurable timeout (default: 30 min) → marked EXPIRED, logged

```python
class PendingTrade(BaseModel):
    id: str
    city: str
    bracket: str                    # e.g., "53-54°F"
    side: Literal["yes", "no"]
    price: float
    quantity: int
    model_probability: float
    market_probability: float
    ev: float
    confidence: str
    reasoning: str                  # Human-readable explanation
    status: Literal["PENDING", "APPROVED", "REJECTED", "EXPIRED", "EXECUTED"]
    created_at: datetime
    expires_at: datetime
    acted_at: datetime | None
```

## Trade Post-Mortem Generation

After settlement, generate a full post-mortem for each trade (see PRD Section 3.6):
- Pull the weather forecasts that were active at time of trade
- Pull the actual NWS CLI settlement data
- Compare model prediction vs. actual outcome
- Determine which weather models were most/least accurate
- Calculate final P&L after fees
- Generate human-readable narrative explaining why the trade won/lost
- Store in database, linked to the trade record

## Execution Orchestrator

The main trading loop (runs as Celery task):

```
every 15 minutes:
  1. Check if cooldown is active → if yes, skip
  2. Fetch latest BracketPredictions from prediction engine
  3. Fetch current market prices from Kalshi client
  4. For each bracket in each city:
     a. Calculate EV (YES and NO sides)
     b. Run risk checks
     c. If +EV and passes all risk checks:
        - AUTO mode: place order immediately
        - MANUAL mode: queue trade for approval
  5. Log all decisions (including skipped trades and why)
```

## Testing Requirements

Your tests go in `tests/trading/`:
- `test_ev_calculator.py` — EV math correctness, both YES and NO sides, fee inclusion
- `test_risk_manager.py` — all risk limits enforced correctly, edge cases at exact limits
- `test_cooldown.py` — cooldown activates/deactivates correctly, consecutive loss counting, reset on win
- `test_trade_queue.py` — state machine (PENDING→APPROVED→EXECUTED, PENDING→EXPIRED, etc.)
- `test_executor.py` — full execution flow, auto vs manual mode routing
- `test_postmortem.py` — post-mortem generation with correct data, narrative accuracy

**SAFETY TESTS (critical — in `tests/trading/test_safety.py`):**
- Max position size CANNOT be exceeded under any circumstances
- Daily loss limit STOPS all trading when hit
- Cooldown BLOCKS trades during active cooldown
- Invalid orders NEVER reach Kalshi API
- If prediction engine returns garbage (NaN, negative probabilities) → trading halts
- If Kalshi client is unreachable → trades queue, don't crash
- Concurrent trade signals don't create race conditions on risk limits
