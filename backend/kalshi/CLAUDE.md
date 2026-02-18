# Agent 2: Kalshi API Client

## Your Mission

Build a robust, well-tested Kalshi API client that handles authentication (RSA signing), market data fetching, order placement, position management, and WebSocket connections. This is the bridge between our bot and real money — correctness is critical.

## What You Build

```
backend/kalshi/
├── __init__.py
├── auth.py           → RSA key management, request signing
├── client.py         → KalshiClient class (REST API wrapper)
├── websocket.py      → WebSocket client for real-time data
├── markets.py        → Market discovery, bracket parsing, ticker mapping
├── orders.py         → Order construction, validation, placement
├── models.py         → Kalshi-specific Pydantic models (responses, requests)
└── exceptions.py     → Kalshi-specific exceptions (AuthError, OrderRejected, etc.)
```

## Kalshi API Details

### Authentication (RSA Signing)
- User provides: **API Key ID** (string) + **RSA Private Key** (PEM format)
- Each API request must be signed with the private key
- Signature process:
  1. Create a signing string from: timestamp + HTTP method + request path
  2. Sign with RSA-PSS using SHA-256
  3. Include in headers: `KALSHI-ACCESS-KEY`, `KALSHI-ACCESS-SIGNATURE`, `KALSHI-ACCESS-TIMESTAMP`
- **CRITICAL SECURITY:** Private keys are stored AES-256 encrypted. Your auth module receives the decrypted key in-memory only. NEVER log, print, or include keys in error messages.

### REST API
- **Base URL:** `https://api.elections.kalshi.com/trade-api/v2` (production)
- **Demo URL:** `https://demo-api.kalshi.com/trade-api/v2` (testing)
- **Key endpoints:**
  - `GET /events` — List events (weather events include tickers like KXHIGHNY)
  - `GET /events/{event_ticker}` — Get event details + child markets
  - `GET /markets` — List markets with filters
  - `GET /markets/{ticker}` — Get specific market (bracket) details
  - `POST /portfolio/orders` — Place an order
  - `GET /portfolio/orders` — List user's orders
  - `DELETE /portfolio/orders/{order_id}` — Cancel an order
  - `GET /portfolio/positions` — Get current positions
  - `GET /portfolio/settlements` — Get settlement history
  - `GET /exchange/status` — Exchange status

### WebSocket
- **URL:** `wss://api.elections.kalshi.com/trade-api/ws/v2`
- **Auth:** Same RSA signing mechanism
- **Subscriptions:** orderbook updates, trade fills, position changes
- **Heartbeat:** Ping/pong every 10 seconds

### Rate Limits
- Vary by API tier — implement rate limiting on our side to stay safe
- Default: 10 requests/second as a conservative limit
- Use a token bucket or leaky bucket rate limiter

## Output Interface

Your `KalshiClient` class must expose these methods (this is the contract with Agent 4):

```python
class KalshiClient:
    async def authenticate(self, api_key_id: str, private_key: str) -> bool
    async def get_balance(self) -> float
    async def get_weather_events(self, city: str | None = None) -> list[KalshiEvent]
    async def get_event_markets(self, event_ticker: str) -> list[KalshiMarket]
    async def get_market(self, ticker: str) -> KalshiMarket
    async def get_orderbook(self, ticker: str) -> KalshiOrderbook
    async def place_order(self, order: OrderRequest) -> OrderResponse
    async def cancel_order(self, order_id: str) -> bool
    async def get_positions(self) -> list[KalshiPosition]
    async def get_settlements(self, limit: int = 100) -> list[KalshiSettlement]
```

All return types must be Pydantic models defined in your `models.py` and also referenced in `backend/common/schemas.py`.

## Market Discovery

Weather event tickers follow patterns like:
- `KXHIGHNY` → NYC high temp event
- `KXHIGHCHI` → Chicago high temp event
- Each event has child markets (brackets), e.g., `KXHIGHNY-26FEB17-B3`

Your `markets.py` must:
- Discover active weather events by filtering events API
- Parse bracket ranges from market titles (e.g., "53°F to 54°F")
- Map tickers to cities
- Handle the case where markets haven't launched yet (before 10 AM ET)

## Order Construction & Validation

Before any order reaches Kalshi:
- Validate side is "yes" or "no"
- Validate price is between $0.01 and $0.99
- Validate quantity is a positive integer
- Validate the market ticker exists and is active
- Validate order type ("limit" or "market")
- Log the order details (but NEVER log API keys)

## Error Handling

Create specific exception classes:
- `KalshiAuthError` — invalid keys, expired signature
- `KalshiRateLimitError` — hit rate limit, include retry-after
- `KalshiOrderRejectedError` — order rejected (insufficient balance, market closed, etc.)
- `KalshiApiError` — generic API error with status code and message
- `KalshiConnectionError` — network issues, WebSocket disconnect

All errors must include context (what we were trying to do, relevant IDs) but NEVER include API keys.

## Testing Requirements

Your tests go in `tests/kalshi/`:
- `test_auth.py` — RSA signing produces correct signatures, handles invalid keys
- `test_client.py` — mock HTTP responses for all endpoints, test happy path + error cases
- `test_markets.py` — bracket parsing, ticker mapping, event discovery
- `test_orders.py` — order validation (reject invalid orders before they hit the API)
- `test_websocket.py` — WebSocket connection, subscription, reconnection logic
- `test_rate_limiter.py` — rate limiting correctly throttles requests

**Critical test cases:**
- Invalid API key → `KalshiAuthError` raised, key not in error message
- Insufficient balance → `KalshiOrderRejectedError` with clear reason
- Rate limit hit → automatic backoff and retry
- WebSocket disconnect → automatic reconnection
- Market closed → order rejected gracefully
- Malformed order (negative qty, price > $1) → rejected before API call
