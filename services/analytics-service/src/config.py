"""
analytics-service/src/config.py
=================================
Runtime configuration for the analytics microservice.

Environment variables
---------------------
PORT            TCP port              (default: 8003)
DATABASE_URL    PostgreSQL DSN        (default: in-memory sample data)
ADMIN_SECRET    Admin panel secret    (gates all analytics endpoints)
"""
from __future__ import annotations

from pydantic import Field
from shared.config import BaseServiceConfig


class AnalyticsConfig(BaseServiceConfig):
    """Analytics-service settings."""

    port: int = Field(default=8003, description="Analytics service listen port")

    database_url: str = Field(
        default="",
        description=(
            "PostgreSQL DSN. When empty the service returns realistic sample data "
            "so the dashboard works without a live database (useful in CI/CD)."
        ),
    )

    admin_secret: str = Field(
        default="",
        description=(
            "Secret required in X-Admin-Secret header. "
            "When empty in development, auth is skipped."
        ),
    )

    @property
    def db_available(self) -> bool:
        return bool(self.database_url)


settings = AnalyticsConfig()
