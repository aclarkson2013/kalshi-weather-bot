# Agent 1: Weather Data Pipeline

## Your Mission

Build the weather data fetching, parsing, normalization, and storage layer. You are the foundation — every other module depends on your data being correct, timely, and consistently formatted.

## What You Build

```
backend/weather/
├── __init__.py
├── nws.py            → NWS API client (forecasts, CLI reports, observations)
├── openmeteo.py      → Open-Meteo API client (forecasts, historical, multi-model)
├── normalizer.py     → Normalize data from all sources into WeatherData schema
├── scheduler.py      → Celery tasks for scheduled data fetching
├── stations.py       → NWS station configs for each Kalshi city
└── exceptions.py     → Weather-specific exceptions (StaleDataError, etc.)
```

## Data Sources

### NWS API (api.weather.gov)
- **No auth needed** — just set a descriptive User-Agent header: `"BozWeatherTrader/1.0 (contact@email.com)"`
- **Key endpoints:**
  - `/points/{lat},{lon}` → returns grid coordinates + forecast office
  - `/gridpoints/{office}/{x},{y}/forecast` → 12-hour period forecasts
  - `/gridpoints/{office}/{x},{y}` → raw numerical forecast data (hourly)
  - `/stations/{stationId}/observations/latest` → current conditions
- **Rate limit:** Be respectful — no more than 1 request per second
- **Gotcha:** NWS API occasionally returns 500 errors. Implement retry with backoff.
- **Gotcha:** Forecast grid coordinates need to be looked up once per station, then cached.

### NWS Station Mapping (Critical for Settlement)
These are the EXACT stations Kalshi uses for settlement:
| City | Station ID | Lat/Lon | NWS Office |
|------|-----------|---------|------------|
| NYC | KNYC (Central Park) | 40.7828, -73.9653 | OKX |
| Chicago | KMDW (Midway) | 41.7868, -87.7522 | LOT |
| Miami | KMIA (Miami Intl) | 25.7959, -80.2870 | MFL |
| Austin | KAUS (Bergstrom Intl) | 30.1945, -97.6699 | EWX |

### Open-Meteo API (api.open-meteo.com)
- **No auth needed**
- **Key endpoints:**
  - `/v1/forecast` → up to 16-day hourly forecasts, multiple models
  - `/v1/archive` → historical weather data (ERA5 reanalysis, back to 1940)
  - `/v1/ecmwf` → ECMWF model specifically
- **Models to fetch:** GFS, ECMWF (IFS), ICON, GEM, JMA — use `&models=` parameter
- **Key variables:** `temperature_2m_max`, `temperature_2m_min`, `cloudcover`, `windspeed_10m`, `relative_humidity_2m`, `dewpoint_2m`

## Output Schema

All weather data you produce MUST conform to the `WeatherData` schema defined in `backend/common/schemas.py`. This is the contract between you and Agent 3 (Prediction Engine).

Key fields:
- `city`: str (one of: "NYC", "CHI", "MIA", "AUS")
- `date`: date (the day being forecast)
- `forecast_high_f`: float (predicted high in Fahrenheit)
- `source`: str (e.g., "NWS", "Open-Meteo:GFS", "Open-Meteo:ECMWF")
- `model_run_timestamp`: datetime (when this forecast was generated)
- `raw_data`: dict (full raw response for audit trail)
- `fetched_at`: datetime (when we fetched it)

## Scheduling

Use Celery tasks for:
- **Every 30 minutes:** Fetch latest NWS + Open-Meteo forecasts for all 4 cities
- **06:00 AM ET daily:** Full data refresh for the day's markets
- **08:00 AM ET daily (D+1):** Fetch NWS CLI report (settlement data)

## Staleness Detection

- Track `fetched_at` timestamp for all data
- If the newest forecast for a city is > 2 hours old, raise `StaleDataError`
- The trading engine will pause trading if data is stale

## Testing Requirements

Your tests go in `tests/weather/`:
- `test_nws.py` — mock NWS API responses, test parsing, error handling, retries
- `test_openmeteo.py` — mock Open-Meteo responses, test multi-model parsing
- `test_normalizer.py` — test that raw data correctly maps to WeatherData schema
- `test_stations.py` — test station config correctness
- `test_scheduler.py` — test Celery task scheduling logic

**Critical test cases:**
- NWS returns 500 → retry logic kicks in
- NWS returns unexpected JSON structure → graceful error, not crash
- Open-Meteo model missing from response → handle gracefully
- Temperature in Celsius → correctly converted to Fahrenheit
- Timezone handling for each city (especially LST vs DST)
