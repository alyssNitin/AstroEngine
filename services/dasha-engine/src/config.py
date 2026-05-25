"""
dasha-engine/src/config.py
===========================
All runtime configuration for the dasha-engine microservice.

Every setting is read from the environment (or a .env file in the project
root). No magic defaults are buried in business logic — configuration lives
here exclusively (Single Responsibility + Dependency Inversion).

Environment variables
---------------------
HOST            Bind address          (default: 0.0.0.0)
PORT            TCP port              (default: 8001)
WORKERS         Uvicorn workers       (default: 2)
ENVIRONMENT     development | production
LOG_LEVEL       DEBUG | INFO | WARNING | ERROR
SERVICE_SECRET  Shared secret for X-Service-Secret auth header
CORS_ORIGINS    Comma-separated allowed origins
PYJHORA_PATH    Path to PyJHora library (needed for Swiss Ephemeris)
"""
from __future__ import annotations

from pydantic import Field

# shared is on sys.path when the service starts via start.py
from shared.config import BaseServiceConfig


class DashaEngineConfig(BaseServiceConfig):
    """
    Dasha-engine–specific settings extending the common base.

    Inherits: host, port, workers, reload, environment, log_level,
              service_secret, cors_origins
    """

    # Override default port so each service has a unique default
    port: int = Field(default=8001, description="Dasha-engine listen port")

    # PyJHora is needed for Swiss Ephemeris calculations
    pyjhora_path: str = Field(
        default="",
        description=(
            "Absolute path to PyJHora checkout. Added to sys.path at startup. "
            "Set via PYJHORA_PATH env var."
        ),
    )

    # Maximum nesting depth allowed in a single request (guards against
    # combinatorial explosion on very deep recursion)
    max_depth: int = Field(
        default=5,
        description="Maximum dasha nesting depth accepted by POST /dasha/calculate",
    )


# Module-level singleton — import this in routes instead of creating
# a new instance per request (respects Dependency Inversion via DI if needed)
settings = DashaEngineConfig()
