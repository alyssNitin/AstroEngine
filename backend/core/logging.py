"""
backend/core/logging.py
========================
Structured JSON logging for NarayanAstroReader.

Uses structlog for machine-readable, JSON-formatted log output in
production, and human-readable coloured output in development.

Usage
-----
    from backend.core.logging import get_logger

    log = get_logger(__name__)
    log.info("event", user_id="abc", report_type="personal")
    log.error("ai_error", exc_info=True, report_id="xyz")

Environment
-----------
  ENVIRONMENT=production  → JSON output (one line per event)
  ENVIRONMENT=development → coloured human-readable output (default)
  LOG_LEVEL               → DEBUG / INFO / WARNING / ERROR  (default INFO)
"""
from __future__ import annotations

import logging
import logging.config
import os
import sys

_ENVIRONMENT = os.environ.get("ENVIRONMENT", "development").lower()
_LOG_LEVEL   = os.environ.get("LOG_LEVEL", "INFO").upper()

# ── Try to import structlog; graceful fallback to stdlib ──────────────────────
try:
    import structlog
    _HAS_STRUCTLOG = True
except ImportError:
    _HAS_STRUCTLOG = False


def _configure_stdlib() -> None:
    """Configure stdlib logging as the underlying log sink."""
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=getattr(logging, _LOG_LEVEL, logging.INFO),
    )
    # Silence noisy third-party loggers
    for noisy in ("uvicorn.access", "httpx", "anthropic"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def configure_logging() -> None:
    """
    Call once at application startup (e.g. in FastAPI lifespan or __main__).
    Sets up structlog (or falls back to stdlib) according to ENVIRONMENT.
    """
    _configure_stdlib()

    if not _HAS_STRUCTLOG:
        logging.getLogger(__name__).warning(
            "structlog not installed — falling back to stdlib logging. "
            "Run: pip install structlog"
        )
        return

    shared_processors = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
    ]

    if _ENVIRONMENT == "production":
        # Machine-readable JSON — one line per event, easy to ship to ELK/Loki
        renderer = structlog.processors.JSONRenderer()
    else:
        # Human-readable coloured output for local development
        renderer = structlog.dev.ConsoleRenderer(colors=True)

    structlog.configure(
        processors=shared_processors + [
            structlog.processors.format_exc_info,
            renderer,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, _LOG_LEVEL, logging.INFO)
        ),
        context_class=dict,
        # stdlib.LoggerFactory() wraps stdlib logging.Logger objects which
        # have a .name attribute required by add_logger_name.
        # PrintLoggerFactory() creates PrintLogger objects that lack .name
        # → AttributeError at runtime on Python 3.13+.
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str):
    """
    Return a structlog logger bound with the given name.
    Falls back to stdlib logging.Logger when structlog is not installed.

    Args:
        name: Typically __name__ of the calling module.

    Returns:
        A structlog BoundLogger (or stdlib Logger as fallback).
    """
    if _HAS_STRUCTLOG:
        return structlog.get_logger(name)
    return logging.getLogger(name)


def bind_request_context(**kwargs) -> None:
    """
    Bind key-value pairs to the current async context so they appear in
    every subsequent log call within the same request.

    Example (FastAPI middleware)::

        bind_request_context(request_id=req_id, user_id=user.id)

    """
    try:
        import structlog  # noqa: PLC0415
        structlog.contextvars.bind_contextvars(**kwargs)
    except ImportError:
        pass  # no-op when structlog not installed


def clear_request_context() -> None:
    """Clear all bound context vars at the end of a request."""
    try:
        import structlog  # noqa: PLC0415
        structlog.contextvars.clear_contextvars()
    except ImportError:
        pass  # no-op when structlog not installed
