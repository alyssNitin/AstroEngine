"""
dasha-engine/src/api/main.py
=============================
FastAPI application for the dasha-engine microservice.

Responsibilities (Single Responsibility Principle)
--------------------------------------------------
This module owns ONLY:
  - FastAPI app creation and middleware registration
  - HTTP request/response mapping
  - Input validation (via Pydantic schemas)
  - Error handling

Business logic lives in src/systems/*.py.
Configuration lives in src/config.py.
Logging setup lives in shared/logging.py.

Endpoints
---------
  GET  /health                  Liveness + readiness probe
  GET  /dasha/systems           List all registered Dasha systems
  POST /dasha/calculate         Full timeline for a birth chart
  POST /dasha/current           Active Maha+Antardasha as of today

Authentication
--------------
In production the API Gateway enforces auth before traffic reaches this
service. During development, set SERVICE_SECRET= (empty) to skip the
X-Service-Secret header check.

SOLID compliance
----------------
- S : routes only; no business logic
- O : adding a new dasha system requires zero changes here
- L : all dasha system classes are substitutable via DASHA_SYSTEMS registry
- I : narrow schemas — callers only provide what each endpoint needs
- D : config injected via src.config.settings (not imported from os.environ)
"""
from __future__ import annotations

import secrets
from contextlib import asynccontextmanager
from datetime import date
from typing import Any

from fastapi import FastAPI, HTTPException, Header, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

# ── Internal imports ──────────────────────────────────────────────────────────
from ..systems import DASHA_SYSTEMS
from ..config import settings
from shared.logging import get_logger, configure_logging
from shared.health import HealthResponse, DependencyStatus

log = get_logger(__name__)


# ── Lifespan ──────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan handler (replaces deprecated @app.on_event).

    Startup  : configure logging, log available dasha systems.
    Shutdown : flush any pending log buffers.
    """
    configure_logging(log_level=settings.log_level, json=settings.is_production)
    log.info(
        "dasha_engine_ready",
        systems=list(DASHA_SYSTEMS.keys()),
        port=settings.port,
        environment=settings.environment,
    )
    yield
    log.info("dasha_engine_shutdown")


# ── App factory ───────────────────────────────────────────────────────────────

app = FastAPI(
    title="Dasha Engine",
    description=(
        "Vedic Dasha calculation microservice.\n\n"
        "Supports: Vimshottari · Yogini · Chara · Kalachakra · Narayana · Moola\n\n"
        "All systems implement `AbstractDashaSystem` — see `src/systems/base.py`."
    ),
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# CORS — allow configured origins (wildcard in dev, explicit in prod)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "X-Service-Secret"],
)


# ── Security dependency ───────────────────────────────────────────────────────

def _verify_service_secret(x_service_secret: str | None = Header(default=None)) -> None:
    """
    Dependency: verify the inter-service shared secret.

    Skipped entirely when SERVICE_SECRET is empty (development mode).
    In production, every caller must supply the correct header.

    Raises
    ------
    HTTP 401 if secret is required but missing or wrong.
    """
    if not settings.service_secret:
        return   # dev mode — no auth required
    if not x_service_secret or not secrets.compare_digest(
        x_service_secret, settings.service_secret
    ):
        log.warning("service_secret_mismatch")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing X-Service-Secret header.",
        )


# ── Pydantic schemas ──────────────────────────────────────────────────────────

class DashaCalculateRequest(BaseModel):
    """
    Request body for POST /dasha/calculate.

    Interface Segregation: only the fields this endpoint actually needs.
    """

    profile_id: str = Field(
        ...,
        description="User's Kundli profile UUID — echoed back in the response.",
    )
    birth_chart: dict[str, Any] = Field(
        ...,
        description="Full kundli JSON from the kundli-engine service.",
    )
    system: str = Field(
        default="vimshottari",
        description="Dasha system key. Use GET /dasha/systems to list available options.",
    )
    from_date: str = Field(
        default_factory=lambda: date.today().isoformat(),
        description="Timeline start date (ISO 8601: YYYY-MM-DD).",
    )
    to_date: str = Field(
        default_factory=lambda: f"{date.today().year + 20}-12-31",
        description="Timeline end date (ISO 8601: YYYY-MM-DD).",
    )
    depth: int = Field(
        default=2,
        ge=1,
        le=settings.max_depth,
        description=(
            "Dasha nesting depth:\n"
            "  1 → Mahadasha only\n"
            "  2 → + Antardasha\n"
            "  3 → + Pratyantar\n"
            "  4 → + Sookshma\n"
            "  5 → + Prana (very large response)"
        ),
    )

    model_config = {"json_schema_extra": {
        "example": {
            "profile_id": "550e8400-e29b-41d4-a716-446655440000",
            "birth_chart": {"moon_nakshatra": "Ashwini", "moon_pada": 1},
            "system": "vimshottari",
            "from_date": "2024-01-01",
            "to_date":   "2044-12-31",
            "depth": 2,
        }
    }}


class CurrentDashaRequest(BaseModel):
    """Request body for POST /dasha/current."""

    birth_chart: dict[str, Any] = Field(
        ...,
        description="Full kundli JSON from the kundli-engine service.",
    )
    system: str = Field(
        default="vimshottari",
        description="Dasha system key.",
    )


# ── Exception handler ─────────────────────────────────────────────────────────

@app.exception_handler(Exception)
async def _unhandled_exception(request: Request, exc: Exception) -> JSONResponse:
    """Catch-all: log unhandled exceptions and return a safe 500 response."""
    log.error("unhandled_exception", path=request.url.path, error=str(exc), exc_info=exc)
    return JSONResponse(
        status_code=500,
        content={"detail": "An unexpected error occurred. Please try again."},
    )


# ── Routes ────────────────────────────────────────────────────────────────────

@app.get(
    "/health",
    response_model=HealthResponse,
    tags=["system"],
    summary="Liveness + readiness probe",
)
def health() -> HealthResponse:
    """
    Standard health check consumed by load balancers and Kubernetes probes.

    Returns the list of registered Dasha systems in `meta` so operators
    can verify the service started with the expected configuration.
    """
    return HealthResponse(
        service="dasha-engine",
        status="healthy",
        version=app.version,
        meta={"available_systems": list(DASHA_SYSTEMS.keys())},
    )


@app.get(
    "/dasha/systems",
    tags=["dasha"],
    summary="List all registered Dasha systems",
)
def list_systems() -> dict:
    """
    Return metadata for every registered Dasha system.

    Adding a new system (e.g. Ashtottari) only requires creating a new
    subclass in src/systems/ and registering it — this endpoint adapts
    automatically (Open/Closed Principle).
    """
    return {
        "systems": [
            {
                "name":         cls.name,
                "display_name": cls.display_name,
                "total_years":  cls.total_years,
                "description":  cls.description,
            }
            for cls in DASHA_SYSTEMS.values()
        ]
    }


@app.post(
    "/dasha/calculate",
    tags=["dasha"],
    summary="Calculate full Dasha timeline",
)
def calculate_dasha(req: DashaCalculateRequest) -> dict:
    """
    Compute a complete Dasha timeline for the supplied birth chart.

    The `birth_chart` must be the JSON returned by the kundli-engine's
    `/kundli/calculate` endpoint.  The `system` field selects the
    calculation algorithm.

    All Dasha system classes are interchangeable (Liskov Substitution)
    — switching from Vimshottari to Yogini requires only changing the
    `system` field; no code changes are needed here.
    """
    system_cls = DASHA_SYSTEMS.get(req.system.lower())
    if system_cls is None:
        raise HTTPException(
            status_code=400,
            detail={
                "error": f"Unknown dasha system: '{req.system}'",
                "available": list(DASHA_SYSTEMS.keys()),
            },
        )

    dasha = system_cls()
    try:
        result = dasha.calculate(
            birth_chart=req.birth_chart,
            from_date=req.from_date,
            to_date=req.to_date,
            depth=req.depth,
        )
    except Exception as exc:
        log.error("dasha_calculate_error", system=req.system, error=str(exc))
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    log.info("dasha_calculated", system=req.system, profile_id=req.profile_id)
    return {"profile_id": req.profile_id, **result}


@app.post(
    "/dasha/current",
    tags=["dasha"],
    summary="Get active Mahadasha + Antardasha for today",
)
def current_dasha(req: CurrentDashaRequest) -> dict:
    """
    Return only the active Dasha periods as of today's date.

    Lighter than `/dasha/calculate` — suitable for real-time widgets
    that just need "what dasha am I in right now?".
    """
    system_cls = DASHA_SYSTEMS.get(req.system.lower())
    if system_cls is None:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown dasha system: '{req.system}'",
        )

    dasha = system_cls()
    try:
        current = dasha.get_current(req.birth_chart)
    except Exception as exc:
        log.error("dasha_current_error", system=req.system, error=str(exc))
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return {
        "system":  req.system,
        "current": current,
        "as_of":   date.today().isoformat(),
    }
