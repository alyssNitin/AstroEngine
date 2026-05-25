#!/usr/bin/env python3
"""
notification-service/start.py
==============================
Standalone entry point for the notification microservice.

Usage
-----
  python start.py
  python start.py --port 8002 --reload
  docker run -p 8002:8002 --env-file ../../.env notification-service
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
    log = get_logger("notification-service.start")

    if not settings.smtp_configured:
        log.warning(
            "smtp_not_configured",
            hint="Emails will be printed to console. Set EMAIL_HOST/EMAIL_USER/EMAIL_PASSWORD.",
        )

    log.info(
        "notification_service_starting",
        port=settings.port,
        email_provider=settings.email_provider,
        smtp_configured=settings.smtp_configured,
        environment=settings.environment,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Notification microservice")
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
