"""WebSocket client for real-time Kalshi market data.

Provides streaming orderbook deltas and ticker updates with automatic
reconnection and heartbeat management. Uses the same RSA signing
mechanism as the REST API for authentication.

Features:
- Authenticated WebSocket connection with RSA signing
- Orderbook delta and ticker subscriptions
- Automatic ping/pong heartbeat (every 10 seconds)
- Exponential backoff reconnection (2^attempt seconds, max 5 retries)
- Automatic re-subscription on reconnect

Usage:
    from backend.kalshi.auth import KalshiAuth
    from backend.kalshi.websocket import KalshiWebSocket

    auth = KalshiAuth(api_key_id, private_key_pem)
    ws = KalshiWebSocket(auth)  # production URL
    ws = KalshiWebSocket(auth, url=KalshiWebSocket.DEMO_WS_URL)  # demo mode
    await ws.connect()
    await ws.subscribe_orderbook("KXHIGHNY-26FEB18-T52")

    async for message in ws.listen():
        print(message)

    await ws.close()
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator

import websockets

from backend.common.logging import get_logger
from backend.kalshi.auth import KalshiAuth
from backend.kalshi.exceptions import KalshiConnectionError

logger = get_logger("MARKET")


class KalshiWebSocket:
    """WebSocket client for real-time Kalshi market data.

    Handles connection, authentication, subscriptions, heartbeat,
    and automatic reconnection with exponential backoff.

    Args:
        auth: KalshiAuth instance for signing the WebSocket connection.
        url: Optional WebSocket URL override (e.g., DEMO_WS_URL for demo mode).
             Defaults to WS_URL (production) if not provided.
    """

    WS_URL = "wss://api.elections.kalshi.com/trade-api/ws/v2"
    DEMO_WS_URL = "wss://demo-api.kalshi.com/trade-api/ws/v2"
    WS_AUTH_PATH = "/trade-api/ws/v2"
    HEARTBEAT_INTERVAL = 10  # seconds
    MAX_RECONNECT_RETRIES = 5

    def __init__(self, auth: KalshiAuth, url: str | None = None) -> None:
        self.auth = auth
        self._url = url or self.WS_URL
        self.ws: websockets.WebSocketClientProtocol | None = None
        self._running: bool = False
        self._subscriptions: list[dict] = []
        self._msg_id: int = 0
        self._heartbeat_task: asyncio.Task | None = None

    async def connect(self) -> None:
        """Establish WebSocket connection with signed auth headers.

        Signs a GET request to /trade-api/ws/v2 and includes the
        authentication headers in the WebSocket handshake.

        Raises:
            KalshiConnectionError: If the connection cannot be established.
        """
        headers = self.auth.sign_request("GET", self.WS_AUTH_PATH)

        try:
            self.ws = await websockets.connect(
                self._url,
                extra_headers=headers,
            )
        except Exception as exc:
            raise KalshiConnectionError(
                f"WebSocket connection failed: {exc}",
                context={"url": self._url},
            ) from exc

        self._running = True

        # Start heartbeat task
        if self._heartbeat_task is not None:
            self._heartbeat_task.cancel()
        self._heartbeat_task = asyncio.create_task(self._heartbeat())

        logger.info("WebSocket connected", extra={"data": {"url": self._url}})

    async def subscribe_orderbook(self, ticker: str) -> None:
        """Subscribe to orderbook delta updates for a market ticker.

        Receives real-time changes to the orderbook (new orders,
        cancellations, fills) rather than full snapshots.

        Args:
            ticker: Market ticker to subscribe to (e.g., "KXHIGHNY-26FEB18-T52").
        """
        self._msg_id += 1
        msg = {
            "id": self._msg_id,
            "cmd": "subscribe",
            "params": {
                "channels": ["orderbook_delta"],
                "market_ticker": ticker,
            },
        }
        await self._send(msg)
        self._subscriptions.append(msg)

        logger.info(
            "Subscribed to orderbook",
            extra={"data": {"ticker": ticker}},
        )

    async def subscribe_ticker(self, ticker: str) -> None:
        """Subscribe to ticker-level updates (price, volume changes).

        Receives notifications when the market's last price, volume,
        or other aggregate fields change.

        Args:
            ticker: Market ticker to subscribe to (e.g., "KXHIGHNY-26FEB18-T52").
        """
        self._msg_id += 1
        msg = {
            "id": self._msg_id,
            "cmd": "subscribe",
            "params": {
                "channels": ["ticker"],
                "market_ticker": ticker,
            },
        }
        await self._send(msg)
        self._subscriptions.append(msg)

        logger.info(
            "Subscribed to ticker",
            extra={"data": {"ticker": ticker}},
        )

    async def listen(self) -> AsyncIterator[dict]:
        """Yield parsed messages from the WebSocket.

        Automatically handles reconnection on disconnect. Each yielded
        value is a parsed JSON dict from the Kalshi WebSocket feed.

        Yields:
            Parsed JSON messages as dicts.

        Raises:
            KalshiConnectionError: If reconnection fails after max retries.
        """
        while self._running:
            try:
                if self.ws is None:
                    await self._reconnect()
                    continue

                raw = await asyncio.wait_for(
                    self.ws.recv(),
                    timeout=30,
                )
                data = json.loads(raw)
                yield data

            except TimeoutError:
                # No message received within timeout — heartbeat handles keepalive
                continue

            except websockets.ConnectionClosed:
                logger.warning("WebSocket disconnected, attempting reconnect")
                await self._reconnect()

            except asyncio.CancelledError:
                break

    async def close(self) -> None:
        """Gracefully close the WebSocket connection.

        Stops the heartbeat task and closes the underlying WebSocket.
        """
        self._running = False

        if self._heartbeat_task is not None:
            self._heartbeat_task.cancel()
            self._heartbeat_task = None

        if self.ws is not None:
            await self.ws.close()
            self.ws = None

        logger.info("WebSocket closed")

    # ─── Internal Methods ───

    async def _send(self, msg: dict) -> None:
        """Send a JSON message to the WebSocket.

        Args:
            msg: Dict to serialize and send.

        Raises:
            KalshiConnectionError: If the WebSocket is not connected.
        """
        if self.ws is None:
            raise KalshiConnectionError(
                "Cannot send message: WebSocket is not connected",
            )
        await self.ws.send(json.dumps(msg))

    async def _heartbeat(self) -> None:
        """Send periodic pings to keep the connection alive.

        Runs as a background task while the WebSocket is connected.
        Sends a ping every HEARTBEAT_INTERVAL seconds.
        """
        while self._running:
            try:
                if self.ws is not None:
                    await self.ws.ping()
                await asyncio.sleep(self.HEARTBEAT_INTERVAL)
            except (asyncio.CancelledError, Exception):
                break

    async def _reconnect(self) -> None:
        """Reconnect with exponential backoff, re-subscribe to previous channels.

        Attempts to reconnect up to MAX_RECONNECT_RETRIES times with
        exponentially increasing delays (2^attempt seconds).

        Raises:
            KalshiConnectionError: If all reconnection attempts fail.
        """
        for attempt in range(self.MAX_RECONNECT_RETRIES):
            try:
                wait = 2**attempt
                logger.info(
                    "Reconnect attempt",
                    extra={
                        "data": {
                            "attempt": attempt + 1,
                            "max_retries": self.MAX_RECONNECT_RETRIES,
                            "wait_seconds": wait,
                        }
                    },
                )
                await asyncio.sleep(wait)
                await self.connect()

                # Re-subscribe to all previous subscriptions
                for sub in self._subscriptions:
                    await self._send(sub)

                logger.info(
                    "Reconnected and re-subscribed",
                    extra={
                        "data": {
                            "subscription_count": len(self._subscriptions),
                        }
                    },
                )
                return

            except Exception:
                logger.error(
                    "Reconnect attempt failed",
                    extra={"data": {"attempt": attempt + 1}},
                )

        raise KalshiConnectionError(
            f"WebSocket reconnection failed after {self.MAX_RECONNECT_RETRIES} attempts",
            context={"url": self._url},
        )
