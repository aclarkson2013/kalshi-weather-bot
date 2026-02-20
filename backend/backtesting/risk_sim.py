"""In-memory risk manager for backtesting.

Mirrors the behavior of the real RiskManager (daily trade limits,
consecutive loss cooldown, bankroll tracking) but operates entirely
in memory with no database or async calls.

Usage:
    risk = BacktestRiskManager(
        initial_bankroll_cents=100_000,
        max_daily_trades=20,
        consecutive_loss_limit=5,
    )
    if risk.can_trade():
        risk.record_trade(pnl_cents=68, won=True)
    risk.advance_day()
"""

from __future__ import annotations

from backend.common.logging import get_logger

logger = get_logger("BACKTEST")


class BacktestRiskManager:
    """Lightweight in-memory risk manager for backtest simulation.

    Tracks bankroll, daily trade count, and consecutive losses.
    Resets daily counters on advance_day().

    Attributes:
        bankroll_cents: Current bankroll in cents.
        max_daily_trades: Maximum trades allowed per day.
        consecutive_loss_limit: Max consecutive losses before blocking.
    """

    def __init__(
        self,
        initial_bankroll_cents: int = 100_000,
        max_daily_trades: int = 20,
        consecutive_loss_limit: int = 5,
    ) -> None:
        self.bankroll_cents = initial_bankroll_cents
        self.max_daily_trades = max_daily_trades
        self.consecutive_loss_limit = consecutive_loss_limit

        self._daily_trade_count = 0
        self._consecutive_losses = 0
        self._total_trades = 0
        self._total_blocked = 0
        self._peak_bankroll = initial_bankroll_cents

    @property
    def daily_trade_count(self) -> int:
        """Number of trades executed today."""
        return self._daily_trade_count

    @property
    def consecutive_losses(self) -> int:
        """Current consecutive loss streak."""
        return self._consecutive_losses

    @property
    def total_trades(self) -> int:
        """Total trades across all days."""
        return self._total_trades

    @property
    def total_blocked(self) -> int:
        """Total trades blocked by risk controls."""
        return self._total_blocked

    @property
    def peak_bankroll(self) -> int:
        """Highest bankroll seen (for drawdown calculation)."""
        return self._peak_bankroll

    def can_trade(self) -> bool:
        """Check if a trade is allowed under current risk limits.

        Returns:
            True if trading is allowed, False if blocked.
        """
        if self.bankroll_cents <= 0:
            self._total_blocked += 1
            return False

        if self._daily_trade_count >= self.max_daily_trades:
            self._total_blocked += 1
            return False

        if self._consecutive_losses >= self.consecutive_loss_limit:
            self._total_blocked += 1
            return False

        return True

    def record_trade(self, pnl_cents: int, won: bool) -> None:
        """Record the outcome of a simulated trade.

        Args:
            pnl_cents: P&L in cents (positive for wins, negative for losses).
            won: Whether the trade was a winner.
        """
        self.bankroll_cents += pnl_cents
        self._daily_trade_count += 1
        self._total_trades += 1

        if won:
            self._consecutive_losses = 0
        else:
            self._consecutive_losses += 1

        # Track peak for drawdown
        if self.bankroll_cents > self._peak_bankroll:
            self._peak_bankroll = self.bankroll_cents

    def advance_day(self) -> None:
        """Reset daily counters. Called between simulation days."""
        self._daily_trade_count = 0
        # NOTE: consecutive losses persist across days (intentional)

    def get_max_trade_size_cents(self) -> int:
        """Get maximum trade cost in cents based on current bankroll.

        Returns a fraction of the bankroll to prevent any single trade
        from wiping out the account. Uses 10% of bankroll as the cap.

        Returns:
            Maximum trade cost in cents.
        """
        return max(100, self.bankroll_cents // 10)
