"""
services/shared/config.py
==========================
Base configuration class for all NarayanAstroReader microservices.

Design (SOLID)
--------------
- Single Responsibility : reads env vars, exposes typed attributes; nothing else.
- Open / Closed         : subclass and add fields — never edit this file.
- Dependency Inversion  : services depend on this abstraction, not on os.environ
                          directly, so tests can inject config without monkeypatching.

Usage::

    from shared.config import BaseServiceConfig

    class DashaConfig(BaseServiceConfig):
        pyjhora_path: str = Field(default="", env="PYJHORA_PATH")

    cfg = DashaConfig()          # reads from env / .env file automatically
    print(cfg.host, cfg.port)
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


def _find_env_file() -> Optional[str]:
    """Walk up from CWD looking for a .env file (monorepo layout)."""
    here = Path.cwd()
    for candidate in [here, here.parent, here.parent.parent]:
        p = candidate / ".env"
        if p.exists():
            return str(p)
    return None


class BaseServiceConfig(BaseSettings):
    """
    Common configuration shared by every microservice.

    All settings are overridable via environment variables.
    The field name is the env-var name in UPPER_SNAKE_CASE by default
    (pydantic-settings convention).

    Attributes
    ----------
    host            : Bind address for uvicorn (default 0.0.0.0)
    port            : TCP port the service listens on (default 8000)
    environment     : 'development' | 'staging' | 'production'
    log_level       : Python logging level string
    service_secret  : Optional inter-service auth token (X-Service-Secret header)
    cors_origins    : Comma-separated allowed CORS origins ('*' in dev)
    """

    model_config = SettingsConfigDict(
        env_file=_find_env_file() or ".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",           # ignore unknown env vars — forward-compatible
    )

    # ── Server ────────────────────────────────────────────────────────────────
    host: str            = Field(default="0.0.0.0",     description="Bind address")
    port: int            = Field(default=8000,           description="TCP port")
    workers: int         = Field(default=1,              description="Uvicorn worker count")
    reload: bool         = Field(default=False,          description="Hot-reload (dev only)")

    # ── Environment ───────────────────────────────────────────────────────────
    environment: str     = Field(default="development",  description="Runtime environment")
    log_level: str       = Field(default="INFO",         description="Logging level")

    # ── Security ──────────────────────────────────────────────────────────────
    service_secret: str  = Field(
        default="",
        description=(
            "Shared secret for service-to-service calls (X-Service-Secret header). "
            "Leave empty in development; required in production."
        ),
    )
    cors_origins: str    = Field(
        default="*",
        description="Comma-separated CORS origins. Use '*' only in development.",
    )

    # ── Convenience properties ─────────────────────────────────────────────────
    @property
    def is_production(self) -> bool:
        return self.environment.lower() == "production"

    @property
    def allowed_origins(self) -> list[str]:
        """Parse cors_origins into a list suitable for CORSMiddleware."""
        if self.cors_origins.strip() == "*":
            return ["*"]
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]
