"""Celery application configuration for background task processing.

Run worker: celery -A backend.celery_app worker --loglevel=info
Run beat:   celery -A backend.celery_app beat --loglevel=info
"""

from __future__ import annotations

from celery import Celery
from celery.schedules import crontab

from backend.common.config import get_settings

settings = get_settings()

celery_app = Celery(
    "boz_weather_trader",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="America/New_York",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    # Global task timeouts — override per-task where needed
    task_soft_time_limit=300,  # 5 min: raises SoftTimeLimitExceeded
    task_time_limit=360,  # 6 min: hard kill (SIGKILL)
)

# ─── Beat Schedule ───
# Tasks are defined in their respective agent modules.
# They're registered here so Celery Beat knows when to run them.

celery_app.conf.beat_schedule = {
    # Agent 1: Weather — fetch forecasts every 30 minutes
    "fetch-forecasts-every-30-min": {
        "task": "backend.weather.scheduler.fetch_all_forecasts",
        "schedule": crontab(minute="*/30"),
    },
    # Agent 1: Weather — fetch NWS CLI reports at 8 AM ET daily
    "fetch-cli-report-morning": {
        "task": "backend.weather.scheduler.fetch_cli_reports",
        "schedule": crontab(hour=8, minute=0),
    },
    # Agent 4: Trading — main trading cycle every 15 minutes
    "trading-cycle": {
        "task": "backend.trading.scheduler.trading_cycle",
        "schedule": crontab(minute="*/15"),
    },
    # Agent 4: Trading — expire stale pending trades every 5 minutes
    "expire-pending-trades": {
        "task": "backend.trading.scheduler.check_pending_trades",
        "schedule": crontab(minute="*/5"),
    },
    # Agent 4: Trading — settle trades at 9 AM ET daily
    "settle-trades": {
        "task": "backend.trading.scheduler.settle_trades",
        "schedule": crontab(hour=9, minute=0),
    },
}
