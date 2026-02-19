"""Tests for Celery task timeout configuration.

Verifies that all scheduled tasks have soft_time_limit and time_limit set,
and that the soft limit is always less than the hard limit (giving tasks
a window for graceful cleanup before being killed).
"""

from __future__ import annotations

import pytest

from backend.trading.scheduler import (
    check_pending_trades,
    settle_trades,
    trading_cycle,
)
from backend.weather.scheduler import fetch_all_forecasts, fetch_cli_reports

# ─── Trading Tasks ───


class TestTradingTaskTimeouts:
    def test_trading_cycle_has_soft_time_limit(self):
        assert trading_cycle.soft_time_limit == 180

    def test_trading_cycle_has_time_limit(self):
        assert trading_cycle.time_limit == 240

    def test_check_pending_has_soft_time_limit(self):
        assert check_pending_trades.soft_time_limit == 120

    def test_check_pending_has_time_limit(self):
        assert check_pending_trades.time_limit == 180

    def test_settle_trades_has_soft_time_limit(self):
        assert settle_trades.soft_time_limit == 300

    def test_settle_trades_has_time_limit(self):
        assert settle_trades.time_limit == 360


# ─── Weather Tasks ───


class TestWeatherTaskTimeouts:
    def test_fetch_forecasts_has_soft_time_limit(self):
        assert fetch_all_forecasts.soft_time_limit == 240

    def test_fetch_forecasts_has_time_limit(self):
        assert fetch_all_forecasts.time_limit == 300

    def test_fetch_cli_has_soft_time_limit(self):
        assert fetch_cli_reports.soft_time_limit == 240

    def test_fetch_cli_has_time_limit(self):
        assert fetch_cli_reports.time_limit == 300


# ─── Invariants ───


class TestTimeoutInvariants:
    @pytest.mark.parametrize(
        "task",
        [
            trading_cycle,
            check_pending_trades,
            settle_trades,
            fetch_all_forecasts,
            fetch_cli_reports,
        ],
    )
    def test_soft_limit_less_than_hard_limit(self, task):
        assert task.soft_time_limit < task.time_limit, (
            f"{task.name}: soft_time_limit ({task.soft_time_limit}) "
            f"must be < time_limit ({task.time_limit})"
        )
