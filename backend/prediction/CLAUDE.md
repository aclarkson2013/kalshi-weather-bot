# Agent 3: Prediction Engine

## Your Mission

Build the statistical prediction engine that takes weather forecast data and produces probability distributions across Kalshi brackets. You are the brain of the bot — your probabilities directly determine which trades get placed.

## What You Build

```
backend/prediction/
├── __init__.py
├── ensemble.py       → Weighted ensemble of multiple forecast sources
├── brackets.py       → Bracket probability calculator
├── error_dist.py     → Historical forecast error distribution analysis
├── calibration.py    → Model calibration against historical actuals
├── postmortem.py     → Generate trade post-mortem data after settlement
└── exceptions.py     → Prediction-specific exceptions
```

## Dependencies

- **Input from Agent 1 (Weather):** `WeatherData` objects from `backend/common/schemas.py`
- **Input from Agent 2 (Kalshi):** Bracket definitions from `KalshiMarket` objects (bracket ranges)
- **Output to Agent 4 (Trading):** `BracketPrediction` objects — probability for each bracket

## How Prediction Works

### Step 1: Ensemble Forecast
Combine multiple weather sources into a single best-estimate forecast:

```
NWS point forecast:        55°F  (weight: 0.35)
Open-Meteo GFS:            54°F  (weight: 0.20)
Open-Meteo ECMWF:          53°F  (weight: 0.30)
Open-Meteo ICON:           55°F  (weight: 0.10)
Open-Meteo GEM:            54°F  (weight: 0.05)
────────────────────────────────────────────────
Weighted ensemble:         54.05°F
```

Weights should be:
- Configurable (stored in config)
- Ideally learned from historical accuracy per city (Phase 2)
- ECMWF generally gets higher weight — it's the most accurate model globally

### Step 2: Forecast Error Distribution
The ensemble gives us a point estimate (54.05°F), but we need a probability distribution. The key question: **how often is the forecast wrong, and by how much?**

Use historical data to build an error distribution:
1. For each city, collect past forecasts and compare to actual NWS CLI high temps
2. Calculate forecast errors (actual - predicted) for each day
3. Fit a probability distribution (normal or t-distribution) to the errors
4. The standard deviation varies by city and season:
   - NYC in summer: ±1.5°F std dev (forecasts are accurate)
   - Chicago in winter: ±3.5°F std dev (forecasts are volatile)

### Step 3: Bracket Probability Calculation
Given the ensemble forecast and error distribution, calculate P(temp in bracket) for each bracket:

```
Ensemble forecast: 54.05°F
Error distribution: Normal(mean=0, std=2.1)

Bracket 1: P(temp < 51) = P(error < -3.05) = 7.3%
Bracket 2: P(51 ≤ temp < 53) = P(-3.05 ≤ error < -1.05) = 15.2%
Bracket 3: P(53 ≤ temp < 55) = P(-1.05 ≤ error < 0.95) = 31.8%  ← most likely
Bracket 4: P(55 ≤ temp < 57) = P(0.95 ≤ error < 2.95) = 28.1%
Bracket 5: P(57 ≤ temp < 59) = P(2.95 ≤ error < 4.95) = 12.4%
Bracket 6: P(temp ≥ 59) = P(error ≥ 4.95) = 5.2%
                                              ─────────
                                              100.0%  ← MUST sum to 100%
```

### Step 4: Confidence Assessment
Rate confidence based on:
- **Model agreement:** If all sources are within 1°F → HIGH confidence
- **Model agreement:** If spread > 3°F → LOW confidence
- **Historical accuracy:** If this city/season has high forecast error → lower confidence
- **Data freshness:** If forecasts are > 6 hours old → lower confidence

## Output Schema

Your output MUST conform to `BracketPrediction` in `backend/common/schemas.py`:

```python
class BracketPrediction(BaseModel):
    city: str
    date: date
    brackets: list[BracketProbability]  # 6 items, probabilities sum to 1.0
    ensemble_forecast_f: float          # weighted ensemble temp
    confidence: Literal["HIGH", "MEDIUM", "LOW"]
    model_sources: list[str]            # which models contributed
    forecast_spread_f: float            # max - min across models
    error_std_f: float                  # historical error std dev used
    generated_at: datetime
```

## Post-Mortem Data

After settlement (NWS CLI report comes in), generate post-mortem data:
- What we predicted vs. what happened
- Which model(s) were most accurate
- Was our probability distribution well-calibrated?
- Feed this back into calibration for future improvement

## Testing Requirements

Your tests go in `tests/prediction/`:
- `test_ensemble.py` — weighted average calculation, handle missing sources, weight normalization
- `test_brackets.py` — probability distribution sums to 100%, edge cases (forecast at bracket boundary), all bracket types (wide edge brackets vs narrow center)
- `test_error_dist.py` — error distribution fitting, per-city/season variation
- `test_calibration.py` — calibration against known historical data
- `test_postmortem.py` — post-mortem generation with correct data

**Critical test cases:**
- Bracket probabilities MUST sum to 1.0 (within floating point tolerance)
- All probabilities must be ≥ 0 and ≤ 1
- If only 1 weather source available → still produces valid output (100% weight)
- If 0 weather sources → raises error, does NOT produce garbage probabilities
- Extreme temperatures (below 0°F, above 110°F) handled correctly
- Bracket boundaries match exactly what Kalshi provides (don't drift by 1°F)
