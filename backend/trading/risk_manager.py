"""Risk management for the trading engine.

Enforces all trading risk limits: max trade size, daily exposure, daily loss,
EV threshold, and cooldown checks. All limits are user-configurable via
UserSettings with safe defaults.

CRITICAL: Uses database-level locking (SELECT FOR UPDATE) for concurrency
safety. Two concurrent Celery workers must not both approve trades that
together exceed the daily exposure limit.

All monetary values are in CENTS (integers) unless otherwise noted.

Risk check order (first failure short-circuits):
    1. Cooldown active?
    2. Trade size within max?
    3. Daily exposure limit?
    4. Daily loss limit?
    5. EV above threshold?

Usage:
    from backend.trading.risk_manager import RiskManager

    risk_mgr = RiskManager(settings=user_settings, db=session, user_id="u123")
    allowed, reason = await risk_mgr.check_trade(signal)
"""

from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.common.logging import get_logger
from backend.common.models import DailyRiskState, Trade, TradeStatus
from backend.common.schemas import TradeSignal, UserSettings

logger = get_logger("RISK")
ET = ZoneInfo("America/New_York")


def get_trading_day() -> date:
    """Get the current trading day in Eastern Time.

    The trading day runs from 00:00 ET to 23:59 ET. All daily risk
    limits reset at midnight ET.

    Returns:
        Today's date in the ET timezone.
    """
    return datetime.now(ET).date()


def is_new_trading_day(last_trading_day: date) -> bool:
    """Check if we've crossed into a new trading day.

    Args:
        last_trading_day: The last known trading day.

    Returns:
        True if today (ET) is a new day compared to last_trading_day.
    """
    return get_trading_day() > last_trading_day


class RiskManager:
    """Enforces all trading risk limits with database-level concurrency safety.

    All monetary comparisons use CENTS (integers) to match the database
    schema and avoid floating-point rounding issues.

    Args:
        settings: User-configurable risk parameters.
        db: Async SQLAlchemy session for database operations.
        user_id: The user ID for scoping risk checks.
    """

    def __init__(
        self,
        settings: UserSettings,
        db: AsyncSession,
        user_id: str,
    ) -> None:
        self.settings = settings
        self.db = db
        self.user_id = user_id

    async def check_trade(self, signal: TradeSignal) -> tuple[bool, str]:
        """Run ALL risk checks on a trade signal.

        Checks run IN ORDER -- first failure short-circuits:
        1. Cooldown active?
        2. Trade size within max?
        3. Daily exposure limit?
        4. Daily loss limit?
        5. EV above threshold?

        Args:
            signal: The trade signal to evaluate.

        Returns:
            Tuple of (allowed: bool, reason: str). If allowed is False,
            reason explains why the trade was blocked.
        """
        # 1. Cooldown check
        from backend.trading.cooldown import CooldownManager

        cm = CooldownManager(self.settings, self.db, self.user_id)
        cooldown_active, cooldown_reason = await cm.is_cooldown_active()
        if cooldown_active:
            logger.info(
                "Trade blocked: cooldown",
                extra={"data": {"reason": cooldown_reason}},
            )
            return False, f"Cooldown active: {cooldown_reason}"

        # 2. Trade size check (all in cents)
        trade_cost_cents = signal.price_cents if signal.side == "yes" else 100 - signal.price_cents

        if trade_cost_cents > self.settings.max_trade_size_cents:
            logger.info(
                "Trade blocked: exceeds max trade size",
                extra={
                    "data": {
                        "cost_cents": trade_cost_cents,
                        "max_cents": self.settings.max_trade_size_cents,
                    }
                },
            )
            return False, (
                f"Trade cost {trade_cost_cents}c exceeds max {self.settings.max_trade_size_cents}c"
            )

        # 3. Daily exposure check (cents)
        current_exposure_cents = await self.get_open_exposure_cents()
        total_exposure = current_exposure_cents + trade_cost_cents
        if total_exposure > self.settings.max_daily_exposure_cents:
            logger.info(
                "Trade blocked: daily exposure limit",
                extra={
                    "data": {
                        "current_exposure_cents": current_exposure_cents,
                        "trade_cost_cents": trade_cost_cents,
                        "limit_cents": self.settings.max_daily_exposure_cents,
                    }
                },
            )
            return False, (
                f"Would exceed daily exposure "
                f"({current_exposure_cents}c + {trade_cost_cents}c > "
                f"{self.settings.max_daily_exposure_cents}c)"
            )

        # 4. Daily loss check (cents)
        daily_loss_cents = await self.get_daily_pnl_cents()
        if daily_loss_cents <= -self.settings.daily_loss_limit_cents:
            logger.info(
                "Trade blocked: daily loss limit",
                extra={
                    "data": {
                        "daily_pnl_cents": daily_loss_cents,
                        "limit_cents": self.settings.daily_loss_limit_cents,
                    }
                },
            )
            return False, (
                f"Daily loss limit reached "
                f"(P&L: {daily_loss_cents}c, limit: "
                f"-{self.settings.daily_loss_limit_cents}c)"
            )

        # 5. EV threshold check (dollars)
        if signal.ev < self.settings.min_ev_threshold:
            return False, (
                f"EV ${signal.ev:.4f} below threshold ${self.settings.min_ev_threshold:.4f}"
            )

        logger.info(
            "Trade approved by risk manager",
            extra={
                "data": {
                    "city": signal.city,
                    "bracket": signal.bracket,
                    "side": signal.side,
                    "ev": signal.ev,
                    "cost_cents": trade_cost_cents,
                }
            },
        )
        return True, "All checks passed"

    async def get_daily_pnl_cents(self) -> int:
        """Sum today's realized P&L in cents from settled trades.

        Returns:
            Net P&L in cents for the current trading day. Negative = losses.
        """
        trading_day = get_trading_day()
        result = await self.db.execute(
            select(func.coalesce(func.sum(Trade.pnl_cents), 0)).where(
                Trade.user_id == self.user_id,
                Trade.settled_at.isnot(None),
                func.date(Trade.trade_date) == trading_day,
            )
        )
        return int(result.scalar())

    async def get_open_exposure_cents(self) -> int:
        """Sum cost in cents of all unsettled open positions.

        Calculates total capital at risk across all OPEN trades for
        the current user.

        Returns:
            Total exposure in cents.
        """
        result = await self.db.execute(
            select(func.coalesce(func.sum(Trade.price_cents * Trade.quantity), 0)).where(
                Trade.user_id == self.user_id,
                Trade.status == TradeStatus.OPEN,
            )
        )
        return int(result.scalar())

    async def check_and_reserve_exposure(self, amount_cents: int) -> bool:
        """Atomically check exposure limit and reserve if allowed.

        Uses SELECT FOR UPDATE to prevent race conditions when
        multiple trading cycles run concurrently.

        Args:
            amount_cents: The exposure amount to reserve, in cents.

        Returns:
            True if the reservation was successful, False if it
            would exceed the daily exposure limit.
        """
        trading_day = get_trading_day()
        trading_day_dt = datetime.combine(trading_day, datetime.min.time())

        result = await self.db.execute(
            select(DailyRiskState)
            .where(
                DailyRiskState.user_id == self.user_id,
                DailyRiskState.trading_day == trading_day_dt,
            )
            .with_for_update()
        )
        state = result.scalar_one_or_none()

        if state is None:
            state = DailyRiskState(
                user_id=self.user_id,
                trading_day=trading_day_dt,
                total_loss_cents=0,
                total_exposure_cents=0,
                consecutive_losses=0,
                trades_count=0,
            )
            self.db.add(state)

        if state.total_exposure_cents + amount_cents > self.settings.max_daily_exposure_cents:
            logger.info(
                "Exposure reservation denied",
                extra={
                    "data": {
                        "requested_cents": amount_cents,
                        "current_cents": state.total_exposure_cents,
                        "limit_cents": self.settings.max_daily_exposure_cents,
                    }
                },
            )
            return False

        state.total_exposure_cents += amount_cents
        state.trades_count += 1
        await self.db.flush()

        logger.info(
            "Exposure reserved",
            extra={
                "data": {
                    "amount_cents": amount_cents,
                    "new_total_cents": state.total_exposure_cents,
                }
            },
        )
        return True

    async def handle_daily_reset(self) -> None:
        """Reset daily risk counters when a new trading day starts.

        Checks if a DailyRiskState row exists for today. If not, the new
        day has begun and a fresh row is created. The absence of a row
        for today signals that the reset has already effectively occurred
        (defaults are zero).

        Call this at the start of every trading cycle.
        """
        trading_day = get_trading_day()
        trading_day_dt = datetime.combine(trading_day, datetime.min.time())
        state = await self._get_or_create_daily_state(trading_day_dt)

        # If the state was just created, log the reset
        if state.trades_count == 0 and state.total_loss_cents == 0:
            logger.info(
                "Daily limits reset",
                extra={"data": {"new_day": str(trading_day)}},
            )

    async def _get_or_create_daily_state(self, trading_day: datetime) -> DailyRiskState:
        """Get or create the DailyRiskState row for the given trading day.

        Args:
            trading_day: The trading day as a datetime.

        Returns:
            The DailyRiskState for the given day.
        """
        result = await self.db.execute(
            select(DailyRiskState).where(
                DailyRiskState.user_id == self.user_id,
                DailyRiskState.trading_day == trading_day,
            )
        )
        state = result.scalar_one_or_none()

        if state is None:
            state = DailyRiskState(
                user_id=self.user_id,
                trading_day=trading_day,
                total_loss_cents=0,
                total_exposure_cents=0,
                consecutive_losses=0,
                trades_count=0,
            )
            self.db.add(state)
            await self.db.flush()

        return state
