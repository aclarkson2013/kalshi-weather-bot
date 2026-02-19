"""Structured logging setup for Boz Weather Trader.

Every log line includes: timestamp, level, module tag, message, and structured data.
Secrets are automatically redacted from log output.

Usage:
    from backend.common.logging import get_logger
    logger = get_logger("WEATHER")
    logger.info("Forecast fetched", extra={"data": {"city": "NYC", "temp_f": 56.3}})
"""

from __future__ import annotations

import json
import logging
import re
import sys
from datetime import UTC, datetime

# Module tags for structured logging
MODULE_TAGS = {
    "WEATHER",
    "MODEL",
    "MARKET",
    "TRADING",
    "ORDER",
    "RISK",
    "COOLDOWN",
    "AUTH",
    "SETTLE",
    "POSTMORTEM",
    "SYSTEM",
    "TEST",
}

# Regex to find secret-looking values in JSON strings
_SECRET_KEY_PATTERN = re.compile(
    r'"([^"]*(?:key|secret|password|token|private|pem|credential)[^"]*)":\s*"([^"]*)"',
    re.IGNORECASE,
)


def _redact_secrets(text: str) -> str:
    """Replace values of secret-looking keys with [REDACTED] in a string."""
    return _SECRET_KEY_PATTERN.sub(r'"\1": "[REDACTED]"', text)


class StructuredFormatter(logging.Formatter):
    """Formats log records as structured, human-readable lines.

    Output format:
        2025-02-15T10:30:00Z | INFO | WEATHER | Forecast fetched | {"city": "NYC"}
    """

    def format(self, record: logging.LogRecord) -> str:
        timestamp = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        level = record.levelname
        module_tag = getattr(record, "module_tag", "SYSTEM")

        # Include request ID when available (set by RequestIdMiddleware)
        try:
            from backend.common.middleware import request_id_var

            rid = request_id_var.get("")
        except ImportError:
            rid = ""

        # Extract structured data from extra
        data = getattr(record, "data", None)
        if data is not None:
            try:
                data_str = json.dumps(data, default=str)
                data_str = _redact_secrets(data_str)
            except (TypeError, ValueError):
                data_str = str(data)
        else:
            data_str = ""

        message = _redact_secrets(record.getMessage())

        parts = [timestamp, level]
        if rid:
            parts.append(f"rid={rid[:8]}")
        parts.extend([module_tag, message])
        if data_str:
            parts.append(data_str)

        return " | ".join(parts)


class ModuleTagLogger(logging.LoggerAdapter):
    """Logger adapter that injects module_tag and supports structured data.

    Usage:
        logger = get_logger("WEATHER")
        logger.info("Fetched forecast", extra={"data": {"city": "NYC"}})
    """

    def process(self, msg: str, kwargs: dict) -> tuple[str, dict]:
        # Inject module_tag into the record
        extra = kwargs.get("extra", {})
        extra["module_tag"] = self.extra.get("module_tag", "SYSTEM")
        kwargs["extra"] = extra
        return msg, kwargs


# Cache loggers to avoid duplicate handlers
_loggers: dict[str, ModuleTagLogger] = {}


def get_logger(module_tag: str) -> ModuleTagLogger:
    """Get a structured logger with the given module tag.

    Args:
        module_tag: One of the MODULE_TAGS (WEATHER, TRADING, ORDER, etc.)

    Returns:
        A logger adapter that injects the module tag into every log line.
    """
    if module_tag in _loggers:
        return _loggers[module_tag]

    logger = logging.getLogger(f"boz.{module_tag.lower()}")

    # Only add handler if this logger doesn't have one yet
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(StructuredFormatter())
        logger.addHandler(handler)
        logger.setLevel(logging.DEBUG)
        logger.propagate = False

    adapter = ModuleTagLogger(logger, {"module_tag": module_tag})
    _loggers[module_tag] = adapter
    return adapter
