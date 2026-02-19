"""Prometheus metrics definitions for Boz Weather Trader.

All metric objects are centralized here as module-level singletons.
Import what you need from anywhere in the codebase:

    from backend.common.metrics import HTTP_REQUESTS_TOTAL, CELERY_TASK_TOTAL

The /metrics endpoint is mounted in backend/main.py via
prometheus_client.make_asgi_app().
"""

from __future__ import annotations

from prometheus_client import Counter, Gauge, Histogram, Info

# ─── App Info ───

APP_INFO = Info("app", "Application metadata")

# ─── HTTP Metrics ───

HTTP_REQUESTS_TOTAL = Counter(
    "http_requests_total",
    "Total HTTP requests",
    labelnames=["method", "path_template", "status_code"],
)

HTTP_REQUEST_DURATION_SECONDS = Histogram(
    "http_request_duration_seconds",
    "HTTP request duration in seconds",
    labelnames=["method", "path_template"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
)

HTTP_REQUESTS_IN_PROGRESS = Gauge(
    "http_requests_in_progress",
    "HTTP requests currently in progress",
    labelnames=["method"],
)

# ─── Celery Task Metrics ───

CELERY_TASK_TOTAL = Counter(
    "celery_task_total",
    "Total Celery task executions",
    labelnames=["task_name", "status"],
)

CELERY_TASK_DURATION_SECONDS = Histogram(
    "celery_task_duration_seconds",
    "Celery task duration in seconds",
    labelnames=["task_name"],
    buckets=(0.1, 0.5, 1.0, 5.0, 10.0, 30.0, 60.0, 120.0, 300.0),
)

# ─── Business Metrics: Trading ───

TRADING_CYCLES_TOTAL = Counter(
    "trading_cycles_total",
    "Total trading cycle outcomes",
    labelnames=["outcome"],
)

TRADES_EXECUTED_TOTAL = Counter(
    "trades_executed_total",
    "Total trades executed or queued",
    labelnames=["mode", "city"],
)

TRADES_RISK_BLOCKED_TOTAL = Counter(
    "trades_risk_blocked_total",
    "Trades blocked by risk manager",
    labelnames=["reason"],
)

# ─── Business Metrics: Weather ───

WEATHER_FETCHES_TOTAL = Counter(
    "weather_fetches_total",
    "Weather data fetch attempts",
    labelnames=["source", "city", "outcome"],
)


def set_app_info(version: str, environment: str) -> None:
    """Set the app_info metric values. Called once at startup."""
    APP_INFO.info({"version": version, "environment": environment})
