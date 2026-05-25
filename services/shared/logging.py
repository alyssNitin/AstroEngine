"""
services/shared/logging.py
===========================
Structured logging for all NarayanAstroReader microservices.

Uses structlog when available; falls back to a stdlib wrapper that accepts
the same structlog-style keyword-argument calls so callers never crash
regardless of which backend is active.

Design (SOLID)
--------------
- SRP : logging setup only — no business logic.
- LSP : _StdlibAdapter and structlog BoundLogger honour the same call
        signature — callers cannot tell the difference.
- DIP : callers depend on get_logger() abstraction, not on structlog directly.

Usage::

    from shared.logging import get_logger, configure_logging
    configure_logging(log_level="INFO", json=False)
    log = get_logger(__name__)
    log.info("service_started", port=8000)
    log.warning("config_missing", key="X", hint="Set in .env")
"""
from __future__ import annotations

import logging
import sys
from typing import Any


# ---------------------------------------------------------------------------
# Stdlib adapter — makes stdlib loggers accept structlog-style **kwargs
# ---------------------------------------------------------------------------

class _StdlibAdapter:
    """Thin wrapper so callers can always write log.info("event", key=val).

    Stdlib Logger._log() rejects unknown keyword arguments, so this adapter
    converts extra kwargs into readable key=value pairs appended to the
    event string before passing it to the underlying logger.

    Example output::

        2024-01-15T10:23:45Z WARNING  dasha-engine.start  pyjhora_path_unset  hint=Set PYJHORA_PATH in .env
    """

    def __init__(self, logger: logging.Logger) -> None:
        self._log = logger

    @staticmethod
    def _fmt(event: str, kwargs: dict) -> str:
        if not kwargs:
            return event
        pairs = "  ".join(f"{k}={v}" for k, v in kwargs.items())
        return f"{event}  {pairs}"

    def debug(self, event: str, *args: Any, **kwargs: Any) -> None:
        self._log.debug(self._fmt(event, kwargs))

    def info(self, event: str, *args: Any, **kwargs: Any) -> None:
        self._log.info(self._fmt(event, kwargs))

    def warning(self, event: str, *args: Any, **kwargs: Any) -> None:
        self._log.warning(self._fmt(event, kwargs))

    warn = warning  # structlog alias

    def error(self, event: str, *args: Any, **kwargs: Any) -> None:
        self._log.error(self._fmt(event, kwargs))

    def critical(self, event: str, *args: Any, **kwargs: Any) -> None:
        self._log.critical(self._fmt(event, kwargs))

    def exception(self, event: str, *args: Any, **kwargs: Any) -> None:
        self._log.exception(self._fmt(event, kwargs))

    def bind(self, **new_values: Any) -> "_StdlibAdapter":
        """structlog compat — returns self (stdlib has no bound context)."""
        return self

    def unbind(self, *keys: str) -> "_StdlibAdapter":
        """structlog compat — no-op."""
        return self


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def configure_logging(log_level: str = "INFO", json: bool = False) -> None:
    """Configure the root logger and structlog (if installed).

    Parameters
    ----------
    log_level : Python logging level string ('DEBUG', 'INFO', 'WARNING' ...)
    json      : Emit JSON log lines (True in production, False in dev)
    """
    level = getattr(logging, log_level.upper(), logging.INFO)

    try:
        import structlog  # noqa: PLC0415

        # stdlib.LoggerFactory() wraps stdlib logging.Logger objects, which
        # have a .name attribute — required by add_logger_name.
        # PrintLoggerFactory() produces PrintLogger objects that lack .name,
        # causing AttributeError: 'PrintLogger' object has no attribute 'name'.
        logging.basicConfig(
            format="%(message)s",
            stream=sys.stdout,
            level=level,
            force=True,
        )

        shared_processors: list[Any] = [
            structlog.contextvars.merge_contextvars,
            structlog.stdlib.add_log_level,
            structlog.stdlib.add_logger_name,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
        ]
        if json:
            shared_processors.append(structlog.processors.JSONRenderer())
        else:
            shared_processors.append(
                structlog.dev.ConsoleRenderer(colors=sys.stderr.isatty())
            )

        structlog.configure(
            processors=shared_processors,
            wrapper_class=structlog.make_filtering_bound_logger(level),
            context_class=dict,
            logger_factory=structlog.stdlib.LoggerFactory(),   # ← has .name
            cache_logger_on_first_use=True,
        )

    except ImportError:
        # structlog not installed — stdlib fallback
        logging.basicConfig(
            format="%(asctime)s %(levelname)-8s %(name)s  %(message)s",
            datefmt="%Y-%m-%dT%H:%M:%SZ",
            stream=sys.stdout,
            level=level,
            force=True,
        )


def get_logger(name: str) -> Any:
    """Return a logger for the given module name.

    Returns a structlog BoundLogger if structlog is installed, otherwise a
    :class:`_StdlibAdapter` that accepts identical keyword-argument calls.

    Both support::

        log.info("event_name", key="value", other=123)
        log.warning("something_wrong", hint="check config")

    Parameters
    ----------
    name : Module or component name, e.g. ``__name__`` or ``"dasha-engine"``
    """
    try:
        import structlog  # noqa: PLC0415
        return structlog.get_logger(name)
    except ImportError:
        return _StdlibAdapter(logging.getLogger(name))
