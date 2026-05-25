#!/usr/bin/env python3
"""
dasha-engine/start.py
======================
Standalone entry point for the dasha-engine microservice.

Usage
-----
  python start.py                  # default host/port from config
  python start.py --port 8001      # override port
  python start.py --reload         # hot-reload for development

The script:
  1. Resolves the PyJHora path and adds it to sys.path
  2. Configures structured logging
  3. Validates critical settings
  4. Launches uvicorn

Running with Docker
-------------------
  docker build -t dasha-engine .
  docker run -p 8001:8001 --env-file ../../.env dasha-engine
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

# ── Path setup ────────────────────────────────────────────────────────────────
# Make 'src' and 'shared' importable without installing the package
_SERVICE_ROOT = Path(__file__).parent
_SERVICES_ROOT = _SERVICE_ROOT.parent

sys.path.insert(0, str(_SERVICE_ROOT))          # exposes 'src.*'
sys.path.insert(0, str(_SERVICES_ROOT))         # exposes 'shared.*'


def _bootstrap() -> None:
    """Validate environment and wire up PyJHora before uvicorn starts."""
    from src.config import settings
    from shared.logging import configure_logging

    configure_logging(
        log_level=settings.log_level,
        json=settings.is_production,
    )

    from shared.logging import get_logger
    log = get_logger("dasha-engine.start")

    # Add PyJHora to sys.path so Swiss Ephemeris functions are importable
    if settings.pyjhora_path:
        pyjhora = Path(settings.pyjhora_path)
        if pyjhora.exists():
            sys.path.insert(0, str(pyjhora))
            log.info("pyjhora_loaded", path=str(pyjhora))
        else:
            log.warning(
                "pyjhora_not_found",
                path=str(pyjhora),
                hint="Dasha calculations will use fallback stub data.",
            )
    else:
        log.warning(
            "pyjhora_path_unset",
            hint="Set PYJHORA_PATH in .env for real ephemeris calculations.",
        )

    if settings.is_production and not settings.service_secret:
        log.warning(
            "service_secret_unset",
            hint="Set SERVICE_SECRET in production to authenticate inter-service calls.",
        )

    log.info(
        "dasha_engine_starting",
        host=settings.host,
        port=settings.port,
        environment=settings.environment,
        workers=settings.workers,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Dasha-engine microservice")
    parser.add_argument("--host",    default=None, help="Override HOST env var")
    parser.add_argument("--port",    type=int, default=None, help="Override PORT env var")
    parser.add_argument("--workers", type=int, default=None, help="Override WORKERS env var")
    parser.add_argument("--reload",  action="store_true", help="Enable hot-reload (dev only)")
    args = parser.parse_args()

    _bootstrap()

    from src.config import settings
    import uvicorn

    uvicorn.run(
        "src.api.main:app",
        host=args.host    or settings.host,
        port=args.port    or settings.port,
        workers=args.workers or settings.workers,
        reload=args.reload or settings.reload,
        app_dir=str(_SERVICE_ROOT),
        log_level=settings.log_level.lower(),
    )


if __name__ == "__main__":
    main()
