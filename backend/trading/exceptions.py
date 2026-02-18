"""Trading-specific exception classes.

These extend the common BozBaseException hierarchy. Use them for errors
that originate within the trading engine (EV calculation, risk checks,
execution failures, etc.).

For risk limit violations, cooldown blocks, and invalid orders, prefer
the exceptions in backend.common.exceptions which are shared across modules.
"""

from __future__ import annotations

from backend.common.exceptions import BozBaseException


class TradingError(BozBaseException):
    """General trading engine error.

    Raised when the trading cycle encounters a non-specific failure
    (e.g., unexpected data format, missing dependencies).
    """


class TradingHaltedError(BozBaseException):
    """Trading has been halted due to a safety condition.

    Raised when the engine detects invalid data, system issues,
    or other conditions that make it unsafe to continue trading.
    This is more severe than a cooldown — it indicates a systemic problem.
    """
