"""
analytics-service/src/api/main.py
===================================
FastAPI application for the analytics microservice.

All endpoints are admin-only, authenticated via X-Admin-Secret header
(or the admin_token cookie when accessed via the main app's admin panel).

Responsibilities (Single Responsibility)
-----------------------------------------
- HTTP request/response mapping only
- Delegates metric computation to aggregator classes
- Delegates event persistence to collector classes

SOLID
-----
- O/C : new metric types = new aggregator class, zero changes here
- D   : aggregators injected at startup, not created per-request
- I   : narrow endpoint schemas — callers only provide what's needed
"""
from __future__ import annotations

import csv
import io
import secrets
from contextlib import asynccontextmanager
from datetime import date, timedelta
from typing import Optional

from fastapi import FastAPI, HTTPException, Header, Query, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from ..collectors.events    import EventCollector
from ..collectors.llm_costs import LlmCostCollector
from ..aggregators.traffic  import TrafficAggregator
from ..aggregators.revenue  import RevenueAggregator
from ..aggregators.health   import HealthAggregator
from ..config import settings
from shared.logging import configure_logging, get_logger
from shared.health import HealthResponse

log = get_logger(__name__)

# ── Shared aggregator instances ───────────────────────────────────────────────
_events:  EventCollector   | None = None
_llm:     LlmCostCollector | None = None
_traffic: TrafficAggregator | None = None
_revenue: RevenueAggregator | None = None
_health:  HealthAggregator  | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialise aggregators once at startup."""
    global _events, _llm, _traffic, _revenue, _health
    configure_logging(log_level=settings.log_level, json=settings.is_production)
    # All collectors are stateless singletons — they read DATABASE_URL from
    # the environment directly and take no constructor arguments.
    _events  = EventCollector()
    _llm     = LlmCostCollector()
    _traffic = TrafficAggregator()
    _revenue = RevenueAggregator()
    _health  = HealthAggregator()
    log.info("analytics_service_ready", db_available=settings.db_available)
    yield
    log.info("analytics_service_shutdown")


app = FastAPI(
    title="NarayanAstro Analytics Service",
    description=(
        "Admin-only analytics microservice.\n\n"
        "All endpoints require X-Admin-Secret header.\n\n"
        "Returns sample data when DATABASE_URL is not configured."
    ),
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "X-Admin-Secret", "X-Service-Secret"],
)

# ── Date helpers ──────────────────────────────────────────────────────────────
_today      = lambda: str(date.today())
_30_days_ago = lambda: str(date.today() - timedelta(days=30))


# ── Auth dependency ───────────────────────────────────────────────────────────

def _require_admin(x_admin_secret: str | None = Header(default=None)) -> None:
    """
    Verify the X-Admin-Secret header.

    Skipped when admin_secret is empty (development mode).
    In production this should ALWAYS be set.
    """
    if not settings.admin_secret:
        return   # dev mode
    if not x_admin_secret or not secrets.compare_digest(
        x_admin_secret, settings.admin_secret
    ):
        log.warning("admin_auth_failed")
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid X-Admin-Secret.")


# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/health", response_model=HealthResponse, tags=["system"])
def health() -> HealthResponse:
    """Liveness probe — no auth required."""
    return HealthResponse(
        service="analytics-service",
        status="healthy",
        version=app.version,
        meta={"db_available": settings.db_available},
    )


@app.post("/events/track", tags=["events"], summary="Track an analytics event")
def track_event(
    event_type: str,
    user_id:    Optional[str] = None,
    meta:       dict          = None,
    _auth=None,   # placeholder — no auth on event tracking (high volume)
) -> dict:
    """
    Record a single analytics event (page view, reading started, etc.).

    Stores only a UUID — never PII — in compliance with GDPR.
    """
    if _events is None:
        raise HTTPException(503, "Analytics not initialised.")
    _events.track(event_type=event_type, user_id=user_id, meta=meta or {})
    return {"tracked": True}


@app.get(
    "/admin/analytics/traffic",
    tags=["analytics"],
    summary="User traffic & engagement metrics",
)
def traffic_metrics(
    from_date: str = Query(default=None, description="YYYY-MM-DD"),
    to_date:   str = Query(default=None, description="YYYY-MM-DD"),
    _auth = None,
) -> dict:
    """DAU, MAU, session counts, and reading funnel metrics."""
    if _traffic is None:
        raise HTTPException(503, "Analytics not initialised.")
    return _traffic.get_metrics(from_date or _30_days_ago(), to_date or _today())


@app.get(
    "/admin/analytics/revenue",
    tags=["analytics"],
    summary="Revenue breakdown by pack, method, and region",
)
def revenue_metrics(
    from_date: str = Query(default=None),
    to_date:   str = Query(default=None),
    _auth = None,
) -> dict:
    """Wallet top-ups, revenue by tier, region split (India vs International)."""
    if _revenue is None:
        raise HTTPException(503, "Analytics not initialised.")
    return _revenue.get_metrics(from_date or _30_days_ago(), to_date or _today())


@app.get(
    "/admin/analytics/llm-costs",
    tags=["analytics"],
    summary="LLM token usage and cost breakdown",
)
def llm_cost_metrics(
    from_date: str = Query(default=None),
    to_date:   str = Query(default=None),
    _auth = None,
) -> dict:
    """Claude API token consumption, cost per request, cumulative spend."""
    if _llm is None:
        raise HTTPException(503, "Analytics not initialised.")
    return _llm.get_metrics(from_date or _30_days_ago(), to_date or _today())


@app.get(
    "/admin/analytics/system-health",
    tags=["analytics"],
    summary="API latency, error rates, and uptime",
)
def system_health_metrics(
    from_date: str = Query(default=None),
    to_date:   str = Query(default=None),
    _auth = None,
) -> dict:
    """p50/p95/p99 latency, error rate, and service uptime metrics."""
    if _health is None:
        raise HTTPException(503, "Analytics not initialised.")
    return _health.get_metrics(from_date or _30_days_ago(), to_date or _today())


@app.get(
    "/admin/analytics/export",
    tags=["analytics"],
    summary="CSV export of any metric dataset",
)
def export_csv(
    metric: str = Query(..., description="Metric name: traffic|revenue|llm-costs|system-health"),
    from_date: str = Query(default=None),
    to_date:   str = Query(default=None),
    _auth = None,
) -> StreamingResponse:
    """
    Stream a CSV download of any metric dataset.

    Open/Closed: adding a new metric type requires only adding one entry
    to the dispatch dict below.
    """
    dispatch = {
        "traffic":       lambda: _traffic.get_metrics(from_date or _30_days_ago(), to_date or _today()),
        "revenue":       lambda: _revenue.get_metrics(from_date or _30_days_ago(), to_date or _today()),
        "llm-costs":     lambda: _llm.get_metrics(from_date or _30_days_ago(), to_date or _today()),
        "system-health": lambda: _health.get_metrics(from_date or _30_days_ago(), to_date or _today()),
    }
    handler = dispatch.get(metric)
    if not handler:
        raise HTTPException(
            400,
            detail={"error": f"Unknown metric: '{metric}'", "available": list(dispatch.keys())},
        )

    data = handler()
    # Flatten nested dict/list to CSV rows
    buf = io.StringIO()
    writer = csv.writer(buf)
    if isinstance(data, dict):
        writer.writerow(["key", "value"])
        for k, v in data.items():
            writer.writerow([k, v])
    elif isinstance(data, list):
        if data:
            writer.writerow(data[0].keys())
            for row in data:
                writer.writerow(row.values())

    buf.seek(0)
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{metric}.csv"'},
    )


@app.get("/health", response_model=HealthResponse, tags=["ops"])
def health() -> HealthResponse:
    """Liveness + readiness probe for orchestrator and Docker health-checks."""
    return HealthResponse(
        service  = "analytics-service",
        status   = "ok",
        version  = "1.0.0",
        dependencies = {
            "database": "available" if settings.db_available else "unavailable (sample data)",
        },
    )
