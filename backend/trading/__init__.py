"""Agent 4: Trading Engine — EV calculation, risk management, and trade execution.

This module is the decision-making core of Boz Weather Trader. It determines
which trades to place based on expected value calculations, enforces risk
limits, manages cooldowns, and orchestrates order execution on Kalshi.

Public API:
    - ev_calculator: EV math, bracket scanning, signal generation
    - risk_manager: Position limits, daily loss, exposure tracking
    - cooldown: Per-loss and consecutive-loss cooldown timers
    - trade_queue: Manual approval queue for trades
    - executor: Trade execution orchestrator
    - postmortem: Post-settlement trade analysis
    - scheduler: Celery tasks for the trading cycle
    - notifications: Web push notification service
"""

from __future__ import annotations

from backend.trading.cooldown import CooldownManager
from backend.trading.ev_calculator import (
    calculate_ev,
    estimate_fees,
    scan_all_brackets,
    scan_bracket,
    validate_market_prices,
    validate_predictions,
)
from backend.trading.exceptions import TradingError, TradingHaltedError
from backend.trading.executor import execute_trade
from backend.trading.notifications import NotificationService
from backend.trading.postmortem import generate_postmortem_narrative, settle_trade
from backend.trading.risk_manager import RiskManager, get_trading_day, is_new_trading_day
from backend.trading.trade_queue import approve_trade, queue_trade, reject_trade

__all__ = [
    "CooldownManager",
    "NotificationService",
    "RiskManager",
    "TradingError",
    "TradingHaltedError",
    "approve_trade",
    "calculate_ev",
    "estimate_fees",
    "execute_trade",
    "generate_postmortem_narrative",
    "get_trading_day",
    "is_new_trading_day",
    "queue_trade",
    "reject_trade",
    "scan_all_brackets",
    "scan_bracket",
    "settle_trade",
    "validate_market_prices",
    "validate_predictions",
]
