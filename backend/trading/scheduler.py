"""Celery tasks for the trading engine scheduling.

These tasks are registered in the Celery beat schedule and orchestrate
the core trading cycle, pending trade expiration, and settlement.

Task schedule:
    - trading_cycle:        Every 15 minutes (scan + execute/queue trades)
    - check_pending_trades: Every 5 minutes (expire stale pending trades)
    - settle_trades:        9 AM ET daily (settle after NWS CLI published)

Uses asgiref.sync.async_to_sync for calling async functions from Celery
tasks, matching the pattern used in the weather scheduler.

Usage:
    These tasks are auto-discovered by Celery. Add the beat schedule to
    your Celery app configuration.
"""

from __future__ import annotations

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from asgiref.sync import async_to_sync
from celery import shared_task

from backend.common.database import get_task_session
from backend.common.logging import get_logger

logger = get_logger("TRADING")
ET = ZoneInfo("America/New_York")


# ─── Celery Tasks ───


@shared_task(bind=True, max_retries=2, default_retry_delay=30)
def trading_cycle(self) -> dict:
    """Main trading loop -- runs every 15 minutes via Celery Beat.

    This is the heartbeat of the trading engine. It scans for +EV
    opportunities and either executes (auto mode) or queues (manual mode)
    approved trades.

    Returns:
        Dict with task execution metadata.
    """
    start_time = datetime.now(UTC)

    logger.info(
        "Starting trading cycle",
        extra={"data": {}},
    )

    try:
        async_to_sync(_run_trading_cycle)()
    except Exception as exc:
        logger.error(
            "Trading cycle failed, retrying",
            extra={"data": {"error": str(exc)}},
        )
        raise self.retry(exc=exc) from exc

    elapsed = (datetime.now(UTC) - start_time).total_seconds()

    logger.info(
        "Trading cycle completed",
        extra={"data": {"elapsed_seconds": round(elapsed, 1)}},
    )

    return {
        "status": "completed",
        "elapsed_seconds": round(elapsed, 1),
    }


@shared_task
def check_pending_trades() -> dict:
    """Expire stale pending trades in manual mode.

    Runs every 5 minutes. Finds PendingTradeModel records past their
    TTL and marks them as EXPIRED.

    Returns:
        Dict with count of expired trades.
    """
    logger.info("Checking for stale pending trades", extra={"data": {}})

    try:
        count = async_to_sync(_expire_pending_trades)()
    except Exception as exc:
        logger.error(
            "Pending trade check failed",
            extra={"data": {"error": str(exc)}},
        )
        count = 0

    return {"status": "completed", "expired_count": count}


@shared_task(bind=True, max_retries=2, default_retry_delay=60)
def settle_trades(self) -> dict:
    """Check for settled markets and generate post-mortems.

    Runs at 9 AM ET daily (after NWS CLI reports publish ~7-8 AM).
    Finds open trades that have matching settlement data and resolves them.

    Returns:
        Dict with task execution metadata.
    """
    start_time = datetime.now(UTC)

    logger.info("Starting settlement cycle", extra={"data": {}})

    try:
        async_to_sync(_settle_and_postmortem)()
    except Exception as exc:
        logger.error(
            "Settlement cycle failed, retrying",
            extra={"data": {"error": str(exc)}},
        )
        raise self.retry(exc=exc) from exc

    elapsed = (datetime.now(UTC) - start_time).total_seconds()

    logger.info(
        "Settlement cycle completed",
        extra={"data": {"elapsed_seconds": round(elapsed, 1)}},
    )

    return {
        "status": "completed",
        "elapsed_seconds": round(elapsed, 1),
    }


# ─── Async Implementations ───


async def _run_trading_cycle() -> None:
    """Async implementation of the trading cycle.

    Steps (in order):
    1. Check if we've entered a new trading day -- reset daily limits if so
    2. Check if markets are open (6 AM - 11 PM ET)
    3. Load user settings for each active user
    4. Check cooldowns
    5. Fetch latest BracketPredictions from the database
    6. Validate predictions (sum to 1.0, no NaN, fresh enough)
    7. Fetch current market prices from Kalshi API
    8. Validate market prices (integers 1-99)
    9. Scan all brackets for +EV opportunities (both YES and NO sides)
    10. For each signal, run risk checks
    11. Execute (auto mode) or queue (manual mode) approved trades
    12. Log ALL decisions (including skipped trades and why)
    """
    from backend.trading.ev_calculator import (
        scan_all_brackets,
        validate_market_prices,
        validate_predictions,
    )
    from backend.trading.executor import execute_trade
    from backend.trading.risk_manager import RiskManager, get_trading_day
    from backend.trading.trade_queue import queue_trade

    # Step 2: Market hours check (before DB work)
    if not _are_markets_open():
        logger.debug(
            "Trading cycle skipped: markets closed",
            extra={"data": {}},
        )
        return

    session = await get_task_session()
    try:
        # Load user settings (placeholder -- single user for v1)
        user_settings = await _load_user_settings(session)
        if user_settings is None:
            logger.info(
                "Trading cycle skipped: no user configured",
                extra={"data": {}},
            )
            return

        user_id = await _get_user_id(session)
        if user_id is None:
            logger.info(
                "Trading cycle skipped: no user found",
                extra={"data": {}},
            )
            return

        risk_mgr = RiskManager(user_settings, session, user_id)

        # Step 1: Daily reset check
        await risk_mgr.handle_daily_reset()

        # Step 3-4: Cooldown check
        from backend.trading.cooldown import CooldownManager

        cm = CooldownManager(user_settings, session, user_id)
        cooldown_active, reason = await cm.is_cooldown_active()
        if cooldown_active:
            logger.info(
                "Trading cycle skipped: cooldown",
                extra={"data": {"reason": reason}},
            )
            return

        # Steps 5-11: Fetch predictions, scan, execute/queue
        # These are placeholders that need the prediction engine and
        # Kalshi client to be fully wired up.
        kalshi_client = await _get_kalshi_client(session, user_id)
        if kalshi_client is None:
            logger.info(
                "Trading cycle skipped: no Kalshi client available",
                extra={"data": {}},
            )
            return

        # Fetch predictions for active cities
        predictions = await _fetch_latest_predictions(session, user_settings.active_cities)
        if not predictions:
            logger.info(
                "Trading cycle skipped: no predictions available",
                extra={"data": {}},
            )
            return

        # Validate predictions
        if not validate_predictions(predictions):
            logger.error(
                "Trading cycle aborted: invalid predictions",
                extra={"data": {}},
            )
            return

        # Process each city's prediction
        for prediction in predictions:
            # Fetch market prices from Kalshi
            market_prices = await _fetch_market_prices(
                kalshi_client, prediction.city, prediction.date
            )
            if not market_prices:
                logger.info(
                    "Skipping city: no market prices",
                    extra={"data": {"city": prediction.city}},
                )
                continue

            if not validate_market_prices(market_prices):
                logger.error(
                    "Skipping city: invalid market prices",
                    extra={"data": {"city": prediction.city}},
                )
                continue

            # Fetch market tickers mapping
            market_tickers = await _fetch_market_tickers(
                kalshi_client, prediction.city, prediction.date
            )

            # Scan for opportunities
            signals = scan_all_brackets(
                prediction,
                market_prices,
                market_tickers,
                user_settings.min_ev_threshold,
            )
            if not signals:
                logger.debug(
                    "No +EV signals",
                    extra={"data": {"city": prediction.city}},
                )
                continue

            # Risk check and execute/queue each signal
            for signal in signals:
                allowed, risk_reason = await risk_mgr.check_trade(signal)
                if not allowed:
                    logger.info(
                        "Trade blocked by risk manager",
                        extra={
                            "data": {
                                "city": signal.city,
                                "bracket": signal.bracket,
                                "reason": risk_reason,
                            }
                        },
                    )
                    continue

                if user_settings.trading_mode == "auto":
                    await execute_trade(signal, kalshi_client, session, user_id)
                else:
                    notification_svc = await _get_notification_service(session, user_id)
                    await queue_trade(
                        signal,
                        session,
                        user_id,
                        signal.market_ticker,
                        notification_svc,
                    )

        await session.commit()

        logger.info(
            "Trading cycle complete",
            extra={"data": {"trading_day": str(get_trading_day())}},
        )

    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()


async def _expire_pending_trades() -> int:
    """Expire pending trades past their TTL.

    Returns:
        Number of trades expired.
    """
    from backend.trading.trade_queue import expire_stale_trades

    session = await get_task_session()
    try:
        count = await expire_stale_trades(session)
        await session.commit()
        return count
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()


async def _settle_and_postmortem() -> None:
    """Settle trades and generate post-mortem narratives.

    Finds all OPEN trades that have matching settlement data and
    settles them with P&L and narrative generation.
    """
    from sqlalchemy import select

    from backend.common.models import Settlement, Trade, TradeStatus
    from backend.trading.cooldown import CooldownManager
    from backend.trading.postmortem import settle_trade

    session = await get_task_session()
    try:
        # Find trades that need settlement
        open_trades_result = await session.execute(
            select(Trade).where(Trade.status == TradeStatus.OPEN)
        )

        settled_count = 0
        for trade in open_trades_result.scalars().all():
            # Look for matching settlement data
            settlement_result = await session.execute(
                select(Settlement).where(
                    Settlement.city == trade.city,
                    Settlement.settlement_date == trade.trade_date,
                )
            )
            settlement = settlement_result.scalar_one_or_none()
            if settlement is None:
                continue  # NWS CLI not published yet for this date

            await settle_trade(trade, settlement, session)
            settled_count += 1

            # Update cooldown based on win/loss
            user_settings = await _load_user_settings(session)
            if user_settings is not None:
                cm = CooldownManager(user_settings, session, trade.user_id)
                if trade.status == TradeStatus.WON:
                    await cm.on_trade_win()
                elif trade.status == TradeStatus.LOST:
                    await cm.on_trade_loss()

        await session.commit()

        logger.info(
            "Settlement cycle complete",
            extra={"data": {"settled_count": settled_count}},
        )

    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()


# ─── Helper Functions ───


def _are_markets_open() -> bool:
    """Check if Kalshi weather markets are currently tradeable.

    Markets open at 10:00 AM ET the day before the event and close
    around 11:59 PM ET on the event day. For simplicity, allow trading
    between 6:00 AM ET and 11:00 PM ET every day.

    Returns:
        True if markets are open, False otherwise.
    """
    now = datetime.now(ET)
    hour = now.hour
    return 6 <= hour <= 23


async def _load_user_settings(db) -> object | None:
    """Load user settings from the first user in the database.

    This is a v1 placeholder for single-user systems. In multi-user,
    this would iterate over all active users.

    Args:
        db: Async database session.

    Returns:
        UserSettings if a user exists, None otherwise.
    """
    from sqlalchemy import select

    from backend.common.models import User
    from backend.common.schemas import UserSettings

    result = await db.execute(select(User).limit(1))
    user = result.scalar_one_or_none()
    if user is None:
        return None

    # Parse active_cities from comma-separated string
    cities = [c.strip() for c in (user.active_cities or "").split(",") if c.strip()]

    return UserSettings(
        trading_mode=user.trading_mode or "manual",
        max_trade_size_cents=user.max_trade_size_cents or 100,
        daily_loss_limit_cents=user.daily_loss_limit_cents or 1000,
        max_daily_exposure_cents=user.max_daily_exposure_cents or 2500,
        min_ev_threshold=user.min_ev_threshold or 0.05,
        cooldown_per_loss_minutes=user.cooldown_per_loss_minutes or 60,
        consecutive_loss_limit=user.consecutive_loss_limit or 3,
        active_cities=cities or ["NYC", "CHI", "MIA", "AUS"],
        notifications_enabled=user.notifications_enabled
        if user.notifications_enabled is not None
        else True,
    )


async def _get_user_id(db) -> str | None:
    """Get the first user's ID from the database.

    Args:
        db: Async database session.

    Returns:
        User ID string, or None if no users exist.
    """
    from sqlalchemy import select

    from backend.common.models import User

    result = await db.execute(select(User.id).limit(1))
    row = result.scalar_one_or_none()
    return row


async def _get_kalshi_client(db, user_id: str) -> object | None:
    """Build an authenticated Kalshi client for the given user.

    Decrypts the user's stored API credentials and creates a KalshiClient.

    Args:
        db: Async database session.
        user_id: The user ID.

    Returns:
        KalshiClient instance, or None if credentials are unavailable.
    """
    from sqlalchemy import select

    from backend.common.encryption import decrypt_api_key
    from backend.common.models import User

    try:
        result = await db.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
        if user is None:
            return None

        from backend.kalshi.client import KalshiClient

        private_key_pem = decrypt_api_key(user.encrypted_private_key)
        return KalshiClient(
            api_key_id=user.kalshi_key_id,
            private_key_pem=private_key_pem,
            demo=True,  # Default to demo mode for safety
        )
    except Exception as exc:
        logger.error(
            "Failed to create Kalshi client",
            extra={"data": {"error": str(exc)}},
        )
        return None


async def _get_notification_service(db, user_id: str) -> object | None:
    """Build a notification service with the user's push subscription.

    Args:
        db: Async database session.
        user_id: The user ID.

    Returns:
        NotificationService instance, or None if push is not configured.
    """
    import json

    from sqlalchemy import select

    from backend.common.models import User
    from backend.trading.notifications import NotificationService

    try:
        result = await db.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
        if user is None or not user.push_subscription:
            return None

        subscription = json.loads(user.push_subscription)
        return NotificationService(subscription=subscription)
    except Exception as exc:
        logger.error(
            "Failed to create notification service",
            extra={"data": {"error": str(exc)}},
        )
        return None


async def _fetch_latest_predictions(db, cities: list[str]) -> list:
    """Fetch the latest BracketPredictions from the database.

    Args:
        db: Async database session.
        cities: List of city codes to fetch predictions for.

    Returns:
        List of BracketPrediction schema objects.
    """
    import json

    from sqlalchemy import select

    from backend.common.models import Prediction
    from backend.common.schemas import BracketPrediction, BracketProbability

    predictions = []
    for city in cities:
        result = await db.execute(
            select(Prediction)
            .where(Prediction.city == city)
            .order_by(Prediction.generated_at.desc())
            .limit(1)
        )
        pred = result.scalar_one_or_none()
        if pred is None:
            continue

        # Parse brackets from JSON
        brackets_data = pred.brackets_json
        if isinstance(brackets_data, str):
            brackets_data = json.loads(brackets_data)

        brackets = [BracketProbability(**b) for b in brackets_data]

        # Parse model_sources from comma-separated string
        model_sources = [s.strip() for s in (pred.model_sources or "").split(",") if s.strip()]

        predictions.append(
            BracketPrediction(
                city=city,
                date=pred.prediction_date.date()
                if hasattr(pred.prediction_date, "date")
                else pred.prediction_date,
                brackets=brackets,
                ensemble_mean_f=pred.ensemble_mean_f,
                ensemble_std_f=pred.ensemble_std_f,
                confidence=pred.confidence,
                model_sources=model_sources,
                generated_at=pred.generated_at,
            )
        )

    return predictions


async def _fetch_market_prices(kalshi_client, city: str, target_date) -> dict[str, int]:
    """Fetch current market prices from Kalshi for a city's brackets.

    Args:
        kalshi_client: Authenticated KalshiClient.
        city: City code (e.g., "NYC").
        target_date: The event date.

    Returns:
        Dict mapping bracket label to YES price in cents.
    """
    from backend.kalshi.markets import WEATHER_SERIES_TICKERS, parse_bracket_from_market

    try:
        series = WEATHER_SERIES_TICKERS.get(city)
        if series is None:
            return {}

        # Build event ticker
        if hasattr(target_date, "strftime"):
            date_str = target_date.strftime("%y%b%d").upper()
        else:
            date_str = str(target_date)
        event_ticker = f"{series}-{date_str}"

        markets = await kalshi_client.get_event_markets(event_ticker)

        prices: dict[str, int] = {}
        for market in markets:
            bracket_info = parse_bracket_from_market(
                {
                    "floor_strike": market.floor_strike,
                    "cap_strike": market.cap_strike,
                }
            )
            label = bracket_info["label"]
            # Use yes_ask as the market price (what you'd pay to buy YES)
            prices[label] = market.yes_ask if market.yes_ask > 0 else market.last_price

        return prices
    except Exception as exc:
        logger.error(
            "Failed to fetch market prices",
            extra={"data": {"city": city, "error": str(exc)}},
        )
        return {}


async def _fetch_market_tickers(kalshi_client, city: str, target_date) -> dict[str, str]:
    """Fetch market ticker mapping from Kalshi for a city's brackets.

    Args:
        kalshi_client: Authenticated KalshiClient.
        city: City code (e.g., "NYC").
        target_date: The event date.

    Returns:
        Dict mapping bracket label to market ticker string.
    """
    from backend.kalshi.markets import WEATHER_SERIES_TICKERS, parse_bracket_from_market

    try:
        series = WEATHER_SERIES_TICKERS.get(city)
        if series is None:
            return {}

        if hasattr(target_date, "strftime"):
            date_str = target_date.strftime("%y%b%d").upper()
        else:
            date_str = str(target_date)
        event_ticker = f"{series}-{date_str}"

        markets = await kalshi_client.get_event_markets(event_ticker)

        tickers: dict[str, str] = {}
        for market in markets:
            bracket_info = parse_bracket_from_market(
                {
                    "floor_strike": market.floor_strike,
                    "cap_strike": market.cap_strike,
                }
            )
            label = bracket_info["label"]
            tickers[label] = market.ticker

        return tickers
    except Exception as exc:
        logger.error(
            "Failed to fetch market tickers",
            extra={"data": {"city": city, "error": str(exc)}},
        )
        return {}


# ─── Celery Beat Schedule ───
# Add this to your Celery app configuration (e.g., backend/celery_app.py)

CELERY_BEAT_SCHEDULE = {
    "trading-cycle": {
        "task": "backend.trading.scheduler.trading_cycle",
        "schedule": 900.0,  # Every 15 minutes (crontab(minute="*/15"))
    },
    "expire-pending": {
        "task": "backend.trading.scheduler.check_pending_trades",
        "schedule": 300.0,  # Every 5 minutes (crontab(minute="*/5"))
    },
    "settle-trades": {
        "task": "backend.trading.scheduler.settle_trades",
        "schedule": 86400.0,  # Daily (crontab(hour=9, minute=0) for 9 AM ET)
    },
}
