#!/usr/bin/env python3
"""
analytics-service/start.py
===========================
Standalone entry point for the analytics microservice.

Usage
-----
  python start.py
  python start.py --port 8003
  docker run -p 8003:8003 --env-file ../../.env analytics-service
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

_SERVICE_ROOT  = Path(__file__).parent
_SERVICES_ROOT = _SERVICE_ROOT.parent

sys.path.insert(0, str(_SERVICE_ROOT))
sys.path.insert(0, str(_SERVICES_ROOT))


def _bootstrap() -> None:
    from src.config import settings
    from shared.logging import configure_logging, get_logger

    configure_logging(log_level=settings.log_level, json=settings.is_production)
    log = get_logger("analytics-service.start")

    if not settings.db_available:
        log.warning(
            "database_not_configured",
            hint="DATABASE_URL not set — returning sample data for all metrics.",
        )
    if not settings.admin_secret:
        log.warning(
            "admin_secret_not_set",
            hint="Set ADMIN_SECRET to protect analytics endpoints in production.",
        )

    log.info(
        "analytics_service_starting",
        port=settings.port,
        db_available=settings.db_available,
        environment=settings.environment,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Analytics microservice")
    parser.add_argument("--host",   default=None)
    parser.add_argument("--port",   type=int, default=None)
    parser.add_argument("--reload", action="store_true")
    args = parser.parse_args()

    _bootstrap()

    from src.config import settings
    import uvicorn

    uvicorn.run(
        "src.api.main:app",
        host=args.host or settings.host,
        port=args.port or settings.port,
        reload=args.reload or settings.reload,
        app_dir=str(_SERVICE_ROOT),
        log_level=settings.log_level.lower(),
    )


if __name__ == "__main__":
    main()
