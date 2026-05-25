"""
services/shared/health.py
==========================
Standard health-check models used by every microservice.

Every service exposes GET /health returning a HealthResponse.
Load balancers, Kubernetes probes, and docker-compose health checks
all depend on this contract.

Design (SOLID)
--------------
- Single Responsibility : health response schema only.
- Interface Segregation : minimal contract — name + status + optional extras.
- Open / Closed         : subclass HealthResponse to add service-specific
                          fields without changing the base shape.

Usage::

    from shared.health import HealthResponse, DependencyStatus

    @app.get("/health", response_model=HealthResponse)
    def health() -> HealthResponse:
        db_ok = ping_database()
        return HealthResponse(
            service="dasha-engine",
            status="healthy" if db_ok else "degraded",
            dependencies={"postgres": DependencyStatus(ok=db_ok)},
        )
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from pydantic import BaseModel, Field


class DependencyStatus(BaseModel):
    """Status of a single downstream dependency."""

    ok: bool = Field(..., description="True if the dependency is reachable and healthy")
    latency_ms: Optional[float] = Field(
        default=None, description="Round-trip latency in milliseconds (if measured)"
    )
    detail: Optional[str] = Field(
        default=None, description="Human-readable detail or error message"
    )


class HealthResponse(BaseModel):
    """
    Standard health-check response.

    HTTP status codes:
      200 — status is 'healthy'
      207 — status is 'degraded' (some dependencies unavailable but service running)
      503 — status is 'unhealthy' (service cannot serve requests)
    """

    service: str = Field(..., description="Service name (e.g. 'dasha-engine')")
    status: str = Field(
        ...,
        description="'healthy' | 'degraded' | 'unhealthy'",
        pattern="^(healthy|degraded|unhealthy)$",
    )
    version: str = Field(default="1.0.0", description="Service version")
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(tz=timezone.utc),
        description="UTC timestamp of the health check",
    )
    dependencies: dict[str, DependencyStatus] = Field(
        default_factory=dict,
        description="Status of downstream dependencies (DB, Redis, other services)",
    )
    meta: dict[str, Any] = Field(
        default_factory=dict,
        description="Service-specific metadata (e.g. available dasha systems)",
    )

    @property
    def http_status_code(self) -> int:
        """Map health status to HTTP status code."""
        return {"healthy": 200, "degraded": 207, "unhealthy": 503}.get(
            self.status, 200
        )
