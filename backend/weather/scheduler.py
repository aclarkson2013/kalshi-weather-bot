"""Celery tasks for scheduled weather data fetching and storage.

These tasks are registered in the Celery beat schedule defined in
backend/celery_app.py. They run periodically to keep weather forecasts
up-to-date for the prediction engine and trading logic.

Task schedule:
  - fetch_all_forecasts: Every 30 minutes (NWS + Open-Meteo for all cities)
  - fetch_cli_reports:   8:00 AM ET daily (NWS CLI settlement data)
"""

from __future__ import annotations

from datetime import UTC, datetime

from asgiref.sync import async_to_sync
from celery import shared_task
from sqlalchemy import select

from backend.common.database import get_task_session
from backend.common.logging import get_logger
from backend.common.metrics import WEATHER_FETCHES_TOTAL
from backend.common.models import CityEnum, Settlement, WeatherForecast
from backend.common.schemas import WeatherData
from backend.weather.cli_parser import parse_cli_text
from backend.weather.nws import fetch_nws_cli, fetch_nws_forecast, fetch_nws_gridpoint
from backend.weather.openmeteo import fetch_openmeteo_forecast
from backend.weather.stations import VALID_CITIES

logger = get_logger("WEATHER")


# ─── Database Storage ───


async def _store_weather_data(forecasts: list[WeatherData]) -> int:
    """Store a batch of WeatherData objects into the database.

    Each WeatherData is converted to a WeatherForecast ORM model
    and inserted. Duplicate detection is left to the caller or
    handled by the unique index on (city, forecast_date, source).

    Args:
        forecasts: List of WeatherData objects to store.

    Returns:
        Number of forecasts successfully stored.
    """
    if not forecasts:
        return 0

    stored = 0
    session = await get_task_session()

    try:
        for forecast in forecasts:
            orm_obj = WeatherForecast(
                city=forecast.city,
                forecast_date=datetime.combine(forecast.date, datetime.min.time()),
                source=forecast.source,
                forecast_high_f=forecast.forecast_high_f,
                forecast_low_f=(
                    forecast.variables.temp_low_f
                    if forecast.variables.temp_low_f is not None
                    else None
                ),
                humidity_pct=forecast.variables.humidity_pct,
                wind_speed_mph=forecast.variables.wind_speed_mph,
                cloud_cover_pct=forecast.variables.cloud_cover_pct,
                raw_data=forecast.raw_data,
                fetched_at=forecast.fetched_at,
            )
            session.add(orm_obj)
            stored += 1

        await session.commit()

        logger.info(
            "Stored weather forecasts in database",
            extra={"data": {"count": stored}},
        )

    except Exception as exc:
        await session.rollback()
        logger.error(
            "Failed to store weather forecasts",
            extra={"data": {"error": str(exc), "count": len(forecasts)}},
        )
        raise
    finally:
        await session.close()

    return stored


# ─── Async Fetch Orchestration ───


async def _fetch_all_forecasts_async() -> None:
    """Fetch NWS + Open-Meteo forecasts for all cities and store results.

    Errors for individual city/source combinations are logged but do
    not fail the entire operation. This ensures partial data is still
    available even if one source is down.
    """
    all_forecasts: list[WeatherData] = []

    for city in VALID_CITIES:
        # Fetch NWS period forecast
        try:
            nws_period = await fetch_nws_forecast(city)
            all_forecasts.extend(nws_period)
            WEATHER_FETCHES_TOTAL.labels(source="NWS", city=city, outcome="success").inc()
            logger.info(
                "Fetched NWS period forecast",
                extra={
                    "data": {
                        "city": city,
                        "count": len(nws_period),
                        "high_f": (nws_period[0].forecast_high_f if nws_period else None),
                    }
                },
            )
        except Exception as exc:
            WEATHER_FETCHES_TOTAL.labels(source="NWS", city=city, outcome="error").inc()
            logger.error(
                "NWS period forecast fetch failed",
                extra={"data": {"city": city, "error": str(exc)}},
            )

        # Fetch NWS gridpoint data
        try:
            nws_grid = await fetch_nws_gridpoint(city)
            all_forecasts.extend(nws_grid)
            WEATHER_FETCHES_TOTAL.labels(source="NWS_gridpoint", city=city, outcome="success").inc()
            logger.info(
                "Fetched NWS gridpoint data",
                extra={
                    "data": {
                        "city": city,
                        "count": len(nws_grid),
                    }
                },
            )
        except Exception as exc:
            WEATHER_FETCHES_TOTAL.labels(source="NWS_gridpoint", city=city, outcome="error").inc()
            logger.error(
                "NWS gridpoint fetch failed",
                extra={"data": {"city": city, "error": str(exc)}},
            )

        # Fetch Open-Meteo multi-model forecasts
        try:
            om_data = await fetch_openmeteo_forecast(city)
            all_forecasts.extend(om_data)
            WEATHER_FETCHES_TOTAL.labels(source="Open-Meteo", city=city, outcome="success").inc()
            logger.info(
                "Fetched Open-Meteo forecasts",
                extra={
                    "data": {
                        "city": city,
                        "count": len(om_data),
                        "models": list({r.source for r in om_data}),
                    }
                },
            )
        except Exception as exc:
            WEATHER_FETCHES_TOTAL.labels(source="Open-Meteo", city=city, outcome="error").inc()
            logger.error(
                "Open-Meteo fetch failed",
                extra={"data": {"city": city, "error": str(exc)}},
            )

    # Store all collected forecasts
    if all_forecasts:
        try:
            stored = await _store_weather_data(all_forecasts)
            logger.info(
                "Completed forecast fetch cycle",
                extra={
                    "data": {
                        "total_fetched": len(all_forecasts),
                        "total_stored": stored,
                        "cities": VALID_CITIES,
                    }
                },
            )
        except Exception as exc:
            logger.error(
                "Failed to store fetched forecasts",
                extra={"data": {"error": str(exc)}},
            )
    else:
        logger.warning(
            "No forecasts fetched in this cycle",
            extra={"data": {"cities": VALID_CITIES}},
        )


async def _fetch_cli_reports_async() -> None:
    """Fetch NWS CLI (Daily Climate Reports) and create Settlement records.

    For each city, fetches the CLI text product from NWS, parses the
    official observed high temperature, and creates a Settlement record
    in the database. The downstream `_settle_and_postmortem()` task
    (trading scheduler) uses these Settlement records to resolve trades.

    The CLI report is published ~7-8 AM local time the morning after
    the settlement day. Duplicate settlements (same city + date) are
    detected and skipped.

    Errors for individual cities are logged but do not fail the entire
    operation, ensuring partial data is still captured.
    """
    for city in VALID_CITIES:
        try:
            # 1. Fetch raw CLI text from NWS
            cli_text = await fetch_nws_cli(city)

            # 2. Parse text to extract temps and metadata
            report = parse_cli_text(cli_text)

            # 3. Create Settlement record in DB (with duplicate check)
            session = await get_task_session()
            try:
                existing = await session.execute(
                    select(Settlement).where(
                        Settlement.city == CityEnum(city),
                        Settlement.settlement_date == report.report_date,
                    )
                )
                if existing.scalar_one_or_none() is not None:
                    logger.info(
                        "Settlement already exists, skipping",
                        extra={
                            "data": {
                                "city": city,
                                "date": str(report.report_date),
                            }
                        },
                    )
                    continue

                settlement = Settlement(
                    city=CityEnum(city),
                    settlement_date=report.report_date,
                    actual_high_f=report.high_f,
                    actual_low_f=report.low_f,
                    source="NWS_CLI",
                    raw_data={
                        "station": report.station,
                        "raw_text": report.raw_text[:2000],
                    },
                )
                session.add(settlement)
                await session.commit()

                WEATHER_FETCHES_TOTAL.labels(source="NWS_CLI", city=city, outcome="success").inc()
                logger.info(
                    "Created settlement record from CLI report",
                    extra={
                        "data": {
                            "city": city,
                            "date": str(report.report_date),
                            "high_f": report.high_f,
                            "low_f": report.low_f,
                            "station": report.station,
                        }
                    },
                )
            except Exception:
                await session.rollback()
                raise
            finally:
                await session.close()

        except Exception as exc:
            WEATHER_FETCHES_TOTAL.labels(source="NWS_CLI", city=city, outcome="error").inc()
            logger.error(
                "CLI report fetch/parse failed",
                extra={"data": {"city": city, "error": str(exc)}},
            )


# ─── Celery Tasks ───


@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    soft_time_limit=240,
    time_limit=300,
)
def fetch_all_forecasts(self) -> dict:
    """Fetch forecasts from all sources for all cities.

    Runs every 30 minutes via Celery beat. Errors for individual
    city/source combinations are logged but do not fail the entire task.
    The task retries up to 3 times on unhandled exceptions.

    Returns:
        Dict with task execution metadata.
    """
    start_time = datetime.now(UTC)

    logger.info(
        "Starting forecast fetch cycle",
        extra={"data": {"cities": VALID_CITIES}},
    )

    try:
        async_to_sync(_fetch_all_forecasts_async)()
    except Exception as exc:
        logger.error(
            "Forecast fetch cycle failed, retrying",
            extra={"data": {"error": str(exc)}},
        )
        raise self.retry(exc=exc) from exc

    elapsed = (datetime.now(UTC) - start_time).total_seconds()

    logger.info(
        "Forecast fetch cycle completed",
        extra={"data": {"elapsed_seconds": round(elapsed, 1)}},
    )

    return {
        "status": "completed",
        "elapsed_seconds": round(elapsed, 1),
        "cities": VALID_CITIES,
    }


@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=120,
    soft_time_limit=240,
    time_limit=300,
)
def fetch_cli_reports(self) -> dict:
    """Fetch NWS Daily Climate Reports for settlement verification.

    Runs at 8 AM ET daily (D+1). The CLI report contains the official
    high temperature used by Kalshi for settlement.

    Returns:
        Dict with task execution metadata.
    """
    start_time = datetime.now(UTC)

    logger.info(
        "Starting CLI report fetch",
        extra={"data": {"cities": VALID_CITIES}},
    )

    try:
        async_to_sync(_fetch_cli_reports_async)()
    except Exception as exc:
        logger.error(
            "CLI report fetch failed, retrying",
            extra={"data": {"error": str(exc)}},
        )
        raise self.retry(exc=exc) from exc

    elapsed = (datetime.now(UTC) - start_time).total_seconds()

    logger.info(
        "CLI report fetch completed",
        extra={"data": {"elapsed_seconds": round(elapsed, 1)}},
    )

    return {
        "status": "completed",
        "elapsed_seconds": round(elapsed, 1),
        "cities": VALID_CITIES,
    }
