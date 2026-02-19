"""FastAPI application factory for Boz Weather Trader.

Run with: uvicorn backend.main:app --reload
"""

from __future__ import annotations

import traceback

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from backend.api.auth import router as auth_router
from backend.api.dashboard import router as dashboard_router
from backend.api.logs import router as logs_router
from backend.api.markets import router as markets_router
from backend.api.notifications import router as notifications_router
from backend.api.performance import router as performance_router
from backend.api.queue import router as queue_router
from backend.api.settings import router as settings_router
from backend.api.trades import router as trades_router
from backend.common.config import get_settings
from backend.common.exceptions import BozBaseException
from backend.common.logging import get_logger
from backend.common.middleware import (
    RequestIdMiddleware,
    RequestLoggingMiddleware,
    SecurityHeadersMiddleware,
    request_id_var,
)
from backend.kalshi.exceptions import (
    KalshiAuthError,
    KalshiError,
    KalshiRateLimitError,
)

logger = get_logger("SYSTEM")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="Boz Weather Trader",
        version="0.1.0",
        description="Automated weather prediction market trading bot for Kalshi",
    )

    # CORS — allow frontend origins (dev + Docker)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:3000",  # Next.js dev server
            "http://127.0.0.1:3000",
            "http://frontend:3000",  # Docker Compose networking
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Production middleware (last added = outermost = runs first on request)
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(RequestLoggingMiddleware)
    app.add_middleware(RequestIdMiddleware)

    # ─── Exception Handlers ───

    @app.exception_handler(BozBaseException)
    async def boz_exception_handler(request: Request, exc: BozBaseException) -> JSONResponse:
        """Handle all Boz-specific exceptions with structured JSON responses."""
        logger.error(
            f"{type(exc).__name__}: {exc}",
            extra={"data": {"path": str(request.url), "context": exc.context}},
        )
        return JSONResponse(
            status_code=400,
            content={
                "error": type(exc).__name__,
                "message": str(exc),
            },
        )

    @app.exception_handler(KalshiAuthError)
    async def kalshi_auth_error_handler(request: Request, exc: KalshiAuthError) -> JSONResponse:
        """Handle Kalshi authentication failures as 401."""
        logger.error(
            f"KalshiAuthError: {exc}",
            extra={"data": {"path": str(request.url)}},
        )
        return JSONResponse(
            status_code=401,
            content={
                "error": "KalshiAuthError",
                "message": str(exc),
            },
        )

    @app.exception_handler(KalshiRateLimitError)
    async def kalshi_rate_limit_handler(
        request: Request, exc: KalshiRateLimitError
    ) -> JSONResponse:
        """Handle Kalshi rate limit errors as 429."""
        logger.warning(
            f"KalshiRateLimitError: {exc}",
            extra={"data": {"path": str(request.url)}},
        )
        return JSONResponse(
            status_code=429,
            content={
                "error": "KalshiRateLimitError",
                "message": str(exc),
            },
        )

    @app.exception_handler(KalshiError)
    async def kalshi_error_handler(request: Request, exc: KalshiError) -> JSONResponse:
        """Handle general Kalshi API errors as 502 (bad gateway)."""
        logger.error(
            f"KalshiError: {exc}",
            extra={"data": {"path": str(request.url)}},
        )
        return JSONResponse(
            status_code=502,
            content={
                "error": "KalshiError",
                "message": str(exc),
            },
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        """Catch-all for unhandled exceptions — log traceback, return 500."""
        rid = request_id_var.get("")
        logger.error(
            f"Unhandled {type(exc).__name__}: {exc}",
            extra={
                "data": {
                    "path": str(request.url),
                    "request_id": rid,
                    "traceback": traceback.format_exc(),
                }
            },
        )
        body: dict = {
            "error": "InternalServerError",
            "message": "An unexpected error occurred",
        }
        if rid:
            body["request_id"] = rid
        return JSONResponse(status_code=500, content=body)

    # ─── Health / Readiness ───

    @app.get("/health")
    async def health_check() -> dict:
        """Liveness probe — confirms the process is running."""
        return {"status": "ok", "version": "0.1.0"}

    @app.get("/ready")
    async def readiness_check() -> JSONResponse:
        """Readiness probe — checks DB and Redis connectivity."""
        checks: dict[str, str] = {}
        all_ok = True

        # Database check
        try:
            from backend.common.database import _get_engine

            engine = _get_engine()
            async with engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
            checks["database"] = "ok"
        except Exception as exc:
            checks["database"] = f"error: {type(exc).__name__}"
            all_ok = False

        # Redis check
        try:
            import redis.asyncio as aioredis

            settings = get_settings()
            r = aioredis.from_url(settings.redis_url)
            await r.ping()
            await r.aclose()
            checks["redis"] = "ok"
        except Exception as exc:
            checks["redis"] = f"error: {type(exc).__name__}"
            all_ok = False

        return JSONResponse(
            status_code=200 if all_ok else 503,
            content={
                "status": "ok" if all_ok else "degraded",
                "version": "0.1.0",
                "checks": checks,
            },
        )

    # ─── Router Mounting ───

    app.include_router(auth_router, prefix="/api/auth", tags=["auth"])
    app.include_router(dashboard_router, prefix="/api/dashboard", tags=["dashboard"])
    app.include_router(markets_router, prefix="/api/markets", tags=["markets"])
    app.include_router(trades_router, prefix="/api/trades", tags=["trades"])
    app.include_router(queue_router, prefix="/api/queue", tags=["queue"])
    app.include_router(settings_router, prefix="/api/settings", tags=["settings"])
    app.include_router(logs_router, prefix="/api/logs", tags=["logs"])
    app.include_router(performance_router, prefix="/api/performance", tags=["performance"])
    app.include_router(notifications_router, prefix="/api/notifications", tags=["notifications"])

    logger.info("App started", extra={"data": {"version": "0.1.0"}})

    return app


app = create_app()
