"""Metrics calculator for backtest results.

Computes aggregate statistics from raw backtest day/trade data:
- Win rate, total P&L, ROI
- Sharpe ratio (daily returns)
- Maximum drawdown
- Per-city breakdown
- Kelly effectiveness metrics

Usage:
    from backend.backtesting.metrics import compute_metrics

    result = compute_metrics(result)  # Mutates result in-place and returns it
"""

from __future__ import annotations

import math

from backend.backtesting.schemas import (
    BacktestResult,
    CityStats,
    KellyStats,
)
from backend.common.logging import get_logger

logger = get_logger("BACKTEST")


def compute_metrics(result: BacktestResult) -> BacktestResult:
    """Compute all aggregate metrics on a BacktestResult.

    Populates: total_trades, wins, losses, win_rate, total_pnl_cents,
    roi_pct, sharpe_ratio, max_drawdown_pct, per_city_stats, kelly_stats,
    total_days_simulated, days_with_trades.

    Args:
        result: BacktestResult with days and trades populated.

    Returns:
        The same BacktestResult with metrics filled in.
    """
    all_trades = []
    for day in result.days:
        all_trades.extend(day.trades)

    result.total_days_simulated = len(result.days)
    result.days_with_trades = sum(1 for d in result.days if d.trades)
    result.total_trades = len(all_trades)
    result.wins = sum(1 for t in all_trades if t.won)
    result.losses = result.total_trades - result.wins
    result.win_rate = result.wins / result.total_trades if result.total_trades > 0 else 0.0
    result.total_pnl_cents = sum(t.pnl_cents for t in all_trades)
    result.roi_pct = _compute_roi(result.total_pnl_cents, result.config.initial_bankroll_cents)
    result.sharpe_ratio = _compute_sharpe(result)
    result.max_drawdown_pct = _compute_max_drawdown(result)
    result.per_city_stats = _compute_per_city_stats(all_trades)

    if result.config.use_kelly:
        result.kelly_stats = _compute_kelly_stats(all_trades)

    return result


def _compute_roi(total_pnl_cents: int, initial_bankroll_cents: int) -> float:
    """Compute return on investment as a percentage.

    Args:
        total_pnl_cents: Total P&L in cents.
        initial_bankroll_cents: Starting bankroll in cents.

    Returns:
        ROI as a percentage (e.g., 8.5 for 8.5%).
    """
    if initial_bankroll_cents <= 0:
        return 0.0
    return round((total_pnl_cents / initial_bankroll_cents) * 100, 2)


def _compute_sharpe(result: BacktestResult) -> float:
    """Compute annualized Sharpe ratio from daily returns.

    Uses daily P&L divided by starting bankroll as daily return.
    Annualizes with sqrt(252) (trading days per year).

    Args:
        result: BacktestResult with days populated.

    Returns:
        Annualized Sharpe ratio (0.0 if insufficient data).
    """
    if len(result.days) < 2:
        return 0.0

    daily_returns = [d.daily_pnl_cents / result.config.initial_bankroll_cents for d in result.days]

    mean_return = sum(daily_returns) / len(daily_returns)
    variance = sum((r - mean_return) ** 2 for r in daily_returns) / len(daily_returns)
    std_return = math.sqrt(variance)

    if std_return < 1e-12:
        return 0.0

    # Annualize: Sharpe = (mean_daily / std_daily) * sqrt(252)
    sharpe = (mean_return / std_return) * math.sqrt(252)
    return round(sharpe, 4)


def _compute_max_drawdown(result: BacktestResult) -> float:
    """Compute maximum drawdown as a percentage of peak bankroll.

    Tracks the peak bankroll across all days and finds the largest
    decline from peak to trough.

    Args:
        result: BacktestResult with days populated.

    Returns:
        Maximum drawdown as a percentage (e.g., 5.2 for 5.2%).
    """
    if not result.days:
        return 0.0

    peak = result.config.initial_bankroll_cents
    max_dd = 0.0

    for day in result.days:
        if day.bankroll_end_cents > peak:
            peak = day.bankroll_end_cents
        if peak > 0:
            dd = (peak - day.bankroll_end_cents) / peak * 100
            max_dd = max(max_dd, dd)

    return round(max_dd, 2)


def _compute_per_city_stats(trades: list) -> dict[str, CityStats]:
    """Compute per-city aggregate statistics.

    Args:
        trades: All simulated trades across all days.

    Returns:
        Dict mapping city code → CityStats.
    """
    city_trades: dict[str, list] = {}
    for trade in trades:
        if trade.city not in city_trades:
            city_trades[trade.city] = []
        city_trades[trade.city].append(trade)

    stats: dict[str, CityStats] = {}
    for city, city_trade_list in city_trades.items():
        wins = sum(1 for t in city_trade_list if t.won)
        total = len(city_trade_list)
        pnl = sum(t.pnl_cents for t in city_trade_list)
        avg_ev = sum(t.ev for t in city_trade_list) / total if total > 0 else 0.0
        stats[city] = CityStats(
            city=city,
            total_trades=total,
            wins=wins,
            losses=total - wins,
            win_rate=round(wins / total, 4) if total > 0 else 0.0,
            total_pnl_cents=pnl,
            avg_ev=round(avg_ev, 4),
        )

    return stats


def _compute_kelly_stats(trades: list) -> KellyStats:
    """Compute Kelly sizing effectiveness metrics.

    Args:
        trades: All simulated trades.

    Returns:
        KellyStats with sizing analysis.
    """
    if not trades:
        return KellyStats()

    quantities = [t.quantity for t in trades]
    avg_qty = sum(quantities) / len(quantities)
    max_qty = max(quantities)

    # Compute what PnL would have been with flat 1-contract sizing
    from backend.trading.ev_calculator import estimate_fees

    flat_pnl = 0
    for trade in trades:
        if trade.won:
            cost_1 = trade.price_cents if trade.side == "yes" else 100 - trade.price_cents
            payout_1 = 100
            profit_1 = payout_1 - cost_1
            fee_1 = estimate_fees(trade.price_cents, trade.side)
            flat_pnl += profit_1 - fee_1
        else:
            flat_pnl -= trade.price_cents if trade.side == "yes" else 100 - trade.price_cents

    actual_pnl = sum(t.pnl_cents for t in trades)
    pnl_vs_flat = actual_pnl - flat_pnl

    return KellyStats(
        avg_quantity=round(avg_qty, 2),
        max_quantity=max_qty,
        pnl_vs_flat=pnl_vs_flat,
    )
