"""Production middleware for Boz Weather Trader.

Provides request ID tracing, request logging, security headers,
and Prometheus HTTP metrics collection.
All four middleware classes are registered in backend/main.py.

Usage:
    from backend.common.middleware import request_id_var
    rid = request_id_var.get("")  # Access current request ID from anywhere
"""

from __future__ import annotations

import re
import time
import uuid
from contextvars import ContextVar

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from backend.common.logging import get_logger
from backend.common.metrics import (
    HTTP_REQUEST_DURATION_SECONDS,
    HTTP_REQUESTS_IN_PROGRESS,
    HTTP_REQUESTS_TOTAL,
)

# ContextVar — accessible from any async context during a request
request_id_var: ContextVar[str] = ContextVar("request_id", default="")

logger = get_logger("SYSTEM")

# Paths to skip in request logging and metrics (probes create noise)
_SKIP_LOG_PATHS = frozenset({"/health", "/ready", "/metrics"})

# Regex patterns for normalizing path templates (avoid high-cardinality labels)
_PATH_ID_PATTERNS = [
    (re.compile(r"/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"), "/{id}"),
    (re.compile(r"/[0-9a-f]{32}"), "/{id}"),
    (re.compile(r"/\d+"), "/{id}"),
]

# Paths to skip for metrics collection only
_SKIP_METRICS_PATHS = frozenset({"/health", "/ready", "/metrics"})


class RequestIdMiddleware(BaseHTTPMiddleware):
    """Inject a unique request ID into every request/response cycle.

    - Reads ``X-Request-ID`` from the incoming request (for cross-service
      tracing). If absent, generates a UUID4.
    - Stores the ID in a ``ContextVar`` so the structured logger can
      include it in every log line.
    - Returns the ID in the ``X-Request-ID`` response header.
    """

    async def dispatch(self, request: Request, call_next) -> Response:  # noqa: ANN001
        rid = request.headers.get("x-request-id") or uuid.uuid4().hex
        request_id_var.set(rid)

        response = await call_next(request)
        response.headers["X-Request-ID"] = rid
        return response


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Log every HTTP request with method, path, status, and duration.

    Skips ``/health`` and ``/ready`` to avoid polluting logs with
    probe traffic.
    """

    async def dispatch(self, request: Request, call_next) -> Response:  # noqa: ANN001
        if request.url.path in _SKIP_LOG_PATHS:
            return await call_next(request)

        start = time.perf_counter()
        response = await call_next(request)
        duration_ms = (time.perf_counter() - start) * 1000

        logger.info(
            f"{request.method} {request.url.path} {response.status_code}",
            extra={
                "data": {
                    "method": request.method,
                    "path": request.url.path,
                    "status": response.status_code,
                    "duration_ms": round(duration_ms, 1),
                    "request_id": request_id_var.get(""),
                }
            },
        )
        return response


def _normalize_path(path: str) -> str:
    """Normalize a URL path by replacing dynamic segments with {id}.

    Replaces UUIDs, 32-char hex strings, and numeric IDs to keep
    Prometheus label cardinality bounded.

    Examples:
        /api/trades/123         -> /api/trades/{id}
        /api/queue/550e8400-... -> /api/queue/{id}
    """
    for pattern, replacement in _PATH_ID_PATTERNS:
        path = pattern.sub(replacement, path)
    return path


class PrometheusMiddleware(BaseHTTPMiddleware):
    """Record Prometheus HTTP metrics for every request.

    Tracks request count, duration histogram, and in-progress gauge.
    Skips /health, /ready, and /metrics to avoid noise.
    """

    async def dispatch(self, request: Request, call_next) -> Response:  # noqa: ANN001
        path = request.url.path
        if path in _SKIP_METRICS_PATHS:
            return await call_next(request)

        method = request.method
        path_template = _normalize_path(path)

        HTTP_REQUESTS_IN_PROGRESS.labels(method=method).inc()
        start = time.perf_counter()

        try:
            response = await call_next(request)
        except Exception:
            HTTP_REQUESTS_TOTAL.labels(
                method=method,
                path_template=path_template,
                status_code="500",
            ).inc()
            HTTP_REQUEST_DURATION_SECONDS.labels(
                method=method,
                path_template=path_template,
            ).observe(time.perf_counter() - start)
            raise
        finally:
            HTTP_REQUESTS_IN_PROGRESS.labels(method=method).dec()

        duration = time.perf_counter() - start
        HTTP_REQUESTS_TOTAL.labels(
            method=method,
            path_template=path_template,
            status_code=str(response.status_code),
        ).inc()
        HTTP_REQUEST_DURATION_SECONDS.labels(
            method=method,
            path_template=path_template,
        ).observe(duration)

        return response


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Add security-related HTTP headers to every response.

    Headers follow OWASP recommendations for API servers.
    """

    HEADERS: dict[str, str] = {
        "X-Content-Type-Options": "nosniff",
        "X-Frame-Options": "DENY",
        "X-XSS-Protection": "1; mode=block",
        "Strict-Transport-Security": ("max-age=31536000; includeSubDomains"),
        "Referrer-Policy": "strict-origin-when-cross-origin",
        "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
        "Cache-Control": "no-store",
    }

    async def dispatch(self, request: Request, call_next) -> Response:  # noqa: ANN001
        response = await call_next(request)
        for header, value in self.HEADERS.items():
            response.headers[header] = value
        return response
