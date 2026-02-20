"""Kalshi WebSocket market data feed consumer.

Maintains a persistent WebSocket connection to the Kalshi API, receives
real-time ticker updates for weather markets, and caches prices in Redis.
The trading cycle reads cached prices instead of making REST calls.

Architecture:
    Kalshi WS API → MarketFeedConsumer → Redis Cache → Trading Cycle
                                       → Redis pub/sub → Browser WS

Started as an asyncio background task during FastAPI lifespan, following
the same pattern as redis_subscriber() in backend/websocket/subscriber.py.

Usage:
    from backend.kalshi.market_feed import market_feed_consumer

    task = asyncio.create_task(market_feed_consumer())
"""

from __future__ import annotations

import asyncio
import contextlib
import json
from datetime import UTC, date, datetime, timedelta

import redis.asyncio as aioredis

from backend.common.config import get_settings
from backend.common.logging import get_logger
from backend.common.metrics import (
    KALSHI_WS_CONNECTED,
    KALSHI_WS_MESSAGES_TOTAL,
    KALSHI_WS_RECONNECTS_TOTAL,
)
from backend.kalshi.cache import (
    get_city_prices,
    set_city_prices,
    set_feed_status,
)
from backend.kalshi.markets import (
    WEATHER_SERIES_TICKERS,
    build_event_ticker,
    parse_bracket_from_market,
)
from backend.websocket.events import EVENTS_CHANNEL

logger = get_logger("MARKET")

MAX_BACKOFF_SECONDS = 60
NO_CREDENTIALS_WAIT = 60


class MarketFeedConsumer:
    """Consumes Kalshi WebSocket ticker updates and caches prices in Redis.

    Lifecycle:
        1. Load user credentials from DB
        2. Connect KalshiWebSocket with signed auth
        3. Subscribe to ticker channels for active weather markets
        4. Process messages: update Redis cache + publish events
        5. Periodically refresh subscriptions (new dates, expired markets)
        6. Handle disconnects with automatic reconnection

    Args:
        redis: Optional async Redis client (created if not provided).
    """

    def __init__(self, redis_client: aioredis.Redis | None = None) -> None:
        self._redis = redis_client
        self._running: bool = False
        self._ws = None
        self._subscribed_tickers: set[str] = set()
        self._ticker_to_bracket: dict[str, dict] = {}

    async def start(self) -> None:
        """Main loop: connect, subscribe, process messages, handle reconnects."""
        self._running = True

        while self._running:
            try:
                # Ensure Redis connection
                if self._redis is None:
                    settings = get_settings()
                    self._redis = aioredis.from_url(settings.redis_url, decode_responses=True)

                # Get auth credentials
                auth = await self._get_auth()
                if auth is None:
                    logger.info(
                        "No Kalshi credentials configured, retrying",
                        extra={"data": {"wait_seconds": NO_CREDENTIALS_WAIT}},
                    )
                    await asyncio.sleep(NO_CREDENTIALS_WAIT)
                    continue

                # Create and connect WebSocket
                from backend.kalshi.websocket import KalshiWebSocket

                demo = await self._is_demo_mode()
                url = KalshiWebSocket.DEMO_WS_URL if demo else None
                self._ws = KalshiWebSocket(auth, url=url)
                await self._ws.connect()

                # Update status
                KALSHI_WS_CONNECTED.set(1)
                await set_feed_status(self._redis, connected=True)

                # Subscribe to active tickers
                await self._subscribe_active_markets()

                # Process messages with periodic refresh
                await self._message_loop()

            except asyncio.CancelledError:
                break

            except Exception as exc:
                KALSHI_WS_RECONNECTS_TOTAL.inc()
                KALSHI_WS_CONNECTED.set(0)
                if self._redis is not None:
                    with contextlib.suppress(Exception):
                        await set_feed_status(self._redis, connected=False)

                wait = min(2 ** min(5, 5), MAX_BACKOFF_SECONDS)
                logger.warning(
                    "Market feed error, reconnecting",
                    extra={
                        "data": {
                            "error": str(exc),
                            "wait_seconds": wait,
                        }
                    },
                )
                await asyncio.sleep(wait)

        # Cleanup
        await self.stop()

    async def stop(self) -> None:
        """Gracefully stop the market feed consumer."""
        self._running = False

        if self._ws is not None:
            with contextlib.suppress(Exception):
                await self._ws.close()
            self._ws = None

        KALSHI_WS_CONNECTED.set(0)
        if self._redis is not None:
            with contextlib.suppress(Exception):
                await set_feed_status(self._redis, connected=False)
                await self._redis.aclose()
            self._redis = None

        self._subscribed_tickers.clear()
        logger.info("Market feed consumer stopped")

    # ─── Internal: Auth ───

    async def _get_auth(self):
        """Load Kalshi API credentials from the database.

        Returns:
            KalshiAuth instance, or None if no credentials are configured.
        """
        from sqlalchemy import select

        from backend.common.database import get_task_session
        from backend.common.encryption import decrypt_api_key
        from backend.common.models import User
        from backend.kalshi.auth import KalshiAuth

        try:
            session = await get_task_session()
            try:
                result = await session.execute(select(User).limit(1))
                user = result.scalar_one_or_none()
                if user is None or not user.kalshi_key_id:
                    return None

                private_key_pem = decrypt_api_key(user.encrypted_private_key)
                return KalshiAuth(
                    api_key_id=user.kalshi_key_id,
                    private_key_pem=private_key_pem,
                )
            finally:
                await session.close()
        except Exception as exc:
            logger.error(
                "Failed to load Kalshi credentials",
                extra={"data": {"error": str(exc)}},
            )
            return None

    async def _is_demo_mode(self) -> bool:
        """Check if the user has demo mode enabled.

        Returns:
            True if demo mode is enabled, True by default if not set.
        """
        from sqlalchemy import select

        from backend.common.database import get_task_session
        from backend.common.models import User

        try:
            session = await get_task_session()
            try:
                result = await session.execute(select(User).limit(1))
                user = result.scalar_one_or_none()
                if user is None:
                    return True
                return user.demo_mode if user.demo_mode is not None else True
            finally:
                await session.close()
        except Exception:
            return True

    # ─── Internal: Subscriptions ───

    async def _subscribe_active_markets(self) -> None:
        """Subscribe to ticker updates for today's and tomorrow's weather markets.

        Does a one-time REST bootstrap to discover individual market tickers
        for each event, then subscribes the WebSocket to each.
        """
        desired_tickers = await self._get_active_tickers()

        # Subscribe to new tickers
        new_tickers = desired_tickers - self._subscribed_tickers
        for ticker in sorted(new_tickers):
            if self._ws is not None:
                await self._ws.subscribe_ticker(ticker)
                self._subscribed_tickers.add(ticker)

        logger.info(
            "Subscribed to market tickers",
            extra={
                "data": {
                    "new": len(new_tickers),
                    "total": len(self._subscribed_tickers),
                }
            },
        )

    async def _get_active_tickers(self) -> set[str]:
        """Build the set of market tickers to subscribe to.

        Looks up today and tomorrow's events for all active cities,
        does a REST call to get individual market tickers per event.

        Returns:
            Set of individual market ticker strings.
        """
        from backend.kalshi.client import KalshiClient

        tickers: set[str] = set()
        today = date.today()
        dates = [today, today + timedelta(days=1)]

        # Get auth for REST bootstrap
        auth = await self._get_auth()
        if auth is None:
            return tickers

        demo = await self._is_demo_mode()
        client = KalshiClient(
            api_key_id=auth.api_key_id,
            private_key_pem="",  # Auth object already has the loaded key
            demo=demo,
        )

        for city in WEATHER_SERIES_TICKERS:
            for target_date in dates:
                try:
                    event_ticker = build_event_ticker(city, target_date)
                    markets = await client.get_event_markets(event_ticker)

                    date_str = target_date.strftime("%y%m%d")
                    for market in markets:
                        ticker = market.ticker
                        tickers.add(ticker)

                        # Build bracket info for mapping ticker → city+bracket
                        bracket = parse_bracket_from_market(
                            {
                                "floor_strike": market.floor_strike,
                                "cap_strike": market.cap_strike,
                                "ticker": ticker,
                            }
                        )
                        self._ticker_to_bracket[ticker] = {
                            "city": city,
                            "date_str": date_str,
                            "label": bracket["label"],
                        }
                except Exception as exc:
                    logger.warning(
                        "Failed to discover tickers for event",
                        extra={
                            "data": {
                                "city": city,
                                "date": str(target_date),
                                "error": str(exc),
                            }
                        },
                    )

        return tickers

    async def _refresh_subscriptions(self) -> None:
        """Refresh subscriptions — subscribe to new tickers, unsubscribe expired."""
        desired = await self._get_active_tickers()

        # Unsubscribe expired
        expired = self._subscribed_tickers - desired
        for ticker in expired:
            self._subscribed_tickers.discard(ticker)
            self._ticker_to_bracket.pop(ticker, None)

        if expired:
            logger.info(
                "Unsubscribed expired tickers",
                extra={"data": {"count": len(expired)}},
            )

        # Subscribe new
        new_tickers = desired - self._subscribed_tickers
        for ticker in sorted(new_tickers):
            if self._ws is not None:
                await self._ws.subscribe_ticker(ticker)
                self._subscribed_tickers.add(ticker)

        if new_tickers:
            logger.info(
                "Subscribed new tickers",
                extra={"data": {"count": len(new_tickers)}},
            )

    # ─── Internal: Message Processing ───

    async def _message_loop(self) -> None:
        """Process WebSocket messages with periodic subscription refresh."""
        settings = get_settings()
        refresh_interval = settings.kalshi_ws_refresh_minutes * 60
        last_refresh = asyncio.get_event_loop().time()

        if self._ws is None:
            return

        async for message in self._ws.listen():
            if not self._running:
                break

            await self._process_message(message)

            # Periodic subscription refresh
            now = asyncio.get_event_loop().time()
            if now - last_refresh >= refresh_interval:
                await self._refresh_subscriptions()
                last_refresh = now

    async def _process_message(self, message: dict) -> None:
        """Route a WebSocket message to the appropriate handler.

        Args:
            message: Parsed JSON dict from the Kalshi WebSocket.
        """
        msg_type = message.get("type", "")

        if msg_type == "ticker":
            KALSHI_WS_MESSAGES_TOTAL.labels(channel="ticker").inc()
            await self._handle_ticker_update(message)
        elif msg_type == "orderbook_delta":
            KALSHI_WS_MESSAGES_TOTAL.labels(channel="orderbook_delta").inc()
        elif msg_type == "error":
            logger.warning(
                "Kalshi WS error message",
                extra={"data": {"message": message}},
            )
        else:
            # Subscription confirmations, heartbeats, etc.
            KALSHI_WS_MESSAGES_TOTAL.labels(channel="other").inc()

    async def _handle_ticker_update(self, data: dict) -> None:
        """Handle a ticker update: cache the price and publish an event.

        Args:
            data: Ticker update message dict from Kalshi WS.
        """
        market_ticker = data.get("msg", {}).get("market_ticker", "")
        if not market_ticker:
            return

        bracket_info = self._ticker_to_bracket.get(market_ticker)
        if bracket_info is None:
            return

        city = bracket_info["city"]
        date_str = bracket_info["date_str"]
        label = bracket_info["label"]

        # Extract price (yes_price in cents)
        msg = data.get("msg", {})
        yes_price = msg.get("yes_price") or msg.get("last_price", 0)

        if self._redis is None:
            return

        # Read current cache, update the bracket, write back
        try:
            cached = await get_city_prices(self._redis, city, date_str)
            if cached is not None:
                prices, tickers = cached
            else:
                prices, tickers = {}, {}

            prices[label] = yes_price
            tickers[label] = market_ticker

            await set_city_prices(self._redis, city, date_str, prices, tickers)

            # Publish event for real-time frontend updates
            event = {
                "type": "market.price_update",
                "timestamp": datetime.now(UTC).isoformat(),
                "data": {
                    "city": city,
                    "bracket": label,
                    "ticker": market_ticker,
                    "yes_price": yes_price,
                },
            }
            await self._redis.publish(EVENTS_CHANNEL, json.dumps(event))

        except Exception as exc:
            logger.warning(
                "Failed to cache ticker update",
                extra={
                    "data": {
                        "ticker": market_ticker,
                        "error": str(exc),
                    }
                },
            )


async def market_feed_consumer() -> None:
    """Top-level entry point for the market feed background task.

    Wraps MarketFeedConsumer with retry logic. Called from FastAPI lifespan.
    Similar structure to redis_subscriber() in backend/websocket/subscriber.py.
    """
    consumer = MarketFeedConsumer()
    try:
        await consumer.start()
    except asyncio.CancelledError:
        logger.info("Market feed consumer shutting down")
    finally:
        await consumer.stop()
