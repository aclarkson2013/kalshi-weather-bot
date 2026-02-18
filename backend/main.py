"""FastAPI application factory for Boz Weather Trader.

Run with: uvicorn backend.main:app --reload
"""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from backend.common.exceptions import BozBaseException
from backend.common.logging import get_logger

logger = get_logger("SYSTEM")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="Boz Weather Trader",
        version="0.1.0",
        description="Automated weather prediction market trading bot for Kalshi",
    )

    # CORS — allow frontend dev server
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:3000",  # Next.js dev server
            "http://127.0.0.1:3000",
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

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

    # ─── Health Check ───

    @app.get("/health")
    async def health_check() -> dict:
        """Health check endpoint for Docker/load balancer."""
        return {"status": "ok", "version": "0.1.0"}

    # ─── Router Mounting ───
    # Routers will be added as agent modules are built:
    # app.include_router(auth_router, prefix="/api/auth", tags=["auth"])
    # app.include_router(weather_router, prefix="/api/weather", tags=["weather"])
    # app.include_router(markets_router, prefix="/api/markets", tags=["markets"])
    # app.include_router(trading_router, prefix="/api/trading", tags=["trading"])
    # app.include_router(settings_router, prefix="/api/settings", tags=["settings"])
    # app.include_router(dashboard_router, prefix="/api/dashboard", tags=["dashboard"])

    logger.info("App started", extra={"data": {"version": "0.1.0"}})

    return app


app = create_app()
