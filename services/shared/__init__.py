"""
services/shared
===============
Shared utilities imported by every NarayanAstroReader microservice.

Modules
-------
config   — BaseServiceConfig: env-driven settings (Dependency Inversion)
logging  — get_logger(): structured JSON logging via structlog
health   — HealthResponse: standard liveness/readiness Pydantic model
"""
