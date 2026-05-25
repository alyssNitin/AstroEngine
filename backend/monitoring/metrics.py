"""
backend/monitoring/metrics.py
==============================
Prometheus metrics for NarayanAstroReader.

Architecture §11.5: Each service must expose a /metrics endpoint compatible
with Prometheus scraping.  This module defines all application-level counters,
histograms and gauges, plus a FastAPI middleware that records request latency.

Usage
-----
In main.py (or any FastAPI app):

    from backend.monitoring.metrics import (
        setup_metrics_endpoint,
        MetricsMiddleware,
    )
    app.add_middleware(MetricsMiddleware)
    setup_metrics_endpoint(app)

Prometheus will then scrape GET /metrics in text exposition format.

Metrics exposed
---------------
  http_requests_total{method, endpoint, status_code}         Counter
  http_request_duration_seconds{method, endpoint}            Histogram
  wallet_operations_total{operation, status}                  Counter
  ai_report_generation_seconds{report_type}                  Histogram
  ai_report_requests_total{report_type, status}              Counter
  active_users_total                                          Gauge
  payment_webhooks_total{gateway, status}                     Counter
  kundli_chart_generation_seconds                            Histogram
  dasha_calculations_total{system, status}                    Counter
"""
from __future__ import annotations

import time
import os

# Graceful import — if prometheus_client is not installed, metrics are no-ops
try:
    from prometheus_client import (
        Counter,
        Gauge,
        Histogram,
        generate_latest,
        CONTENT_TYPE_LATEST,
        CollectorRegistry,
        REGISTRY,
    )
    _PROMETHEUS_AVAILABLE = True
except ImportError:
    _PROMETHEUS_AVAILABLE = False

# ── Metric definitions ────────────────────────────────────────────────────────

if _PROMETHEUS_AVAILABLE:

    HTTP_REQUESTS_TOTAL = Counter(
        "http_requests_total",
        "Total HTTP requests received",
        ["method", "endpoint", "status_code"],
    )

    HTTP_REQUEST_DURATION = Histogram(
        "http_request_duration_seconds",
        "HTTP request latency in seconds",
        ["method", "endpoint"],
        buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0],
    )

    WALLET_OPERATIONS_TOTAL = Counter(
        "wallet_operations_total",
        "Total wallet operations (debit/credit/balance)",
        ["operation", "status"],
    )

    AI_REPORT_DURATION = Histogram(
        "ai_report_generation_seconds",
        "AI report generation latency in seconds",
        ["report_type"],
        buckets=[1.0, 2.5, 5.0, 10.0, 15.0, 20.0, 30.0, 60.0],
    )

    AI_REPORT_REQUESTS_TOTAL = Counter(
        "ai_report_requests_total",
        "Total AI report generation requests",
        ["report_type", "status"],
    )

    ACTIVE_USERS = Gauge(
        "active_users_total",
        "Number of users with active sessions (approximation)",
    )

    PAYMENT_WEBHOOKS_TOTAL = Counter(
        "payment_webhooks_total",
        "Total payment webhook events received",
        ["gateway", "status"],
    )

    KUNDLI_CHART_DURATION = Histogram(
        "kundli_chart_generation_seconds",
        "Kundli chart generation latency in seconds",
        buckets=[0.1, 0.25, 0.5, 1.0, 2.0, 3.0, 5.0],
    )

    DASHA_CALCULATIONS_TOTAL = Counter(
        "dasha_calculations_total",
        "Total dasha calculation requests",
        ["system", "status"],
    )

else:
    # Stub objects that silently do nothing when prometheus_client is absent
    class _NoopMetric:
        def labels(self, **kw): return self
        def inc(self, *a, **kw): pass
        def dec(self, *a, **kw): pass
        def set(self, *a, **kw): pass
        def observe(self, *a, **kw): pass
        def time(self): return _NoopContextManager()

    class _NoopContextManager:
        def __enter__(self): return self
        def __exit__(self, *a): pass

    HTTP_REQUESTS_TOTAL      = _NoopMetric()
    HTTP_REQUEST_DURATION    = _NoopMetric()
    WALLET_OPERATIONS_TOTAL  = _NoopMetric()
    AI_REPORT_DURATION       = _NoopMetric()
    AI_REPORT_REQUESTS_TOTAL = _NoopMetric()
    ACTIVE_USERS             = _NoopMetric()
    PAYMENT_WEBHOOKS_TOTAL   = _NoopMetric()
    KUNDLI_CHART_DURATION    = _NoopMetric()
    DASHA_CALCULATIONS_TOTAL = _NoopMetric()


# ── Convenience recording helpers ─────────────────────────────────────────────

def record_wallet_op(operation: str, success: bool) -> None:
    """Record a wallet operation (debit/credit/balance/topup)."""
    WALLET_OPERATIONS_TOTAL.labels(
        operation=operation,
        status="success" if success else "failure",
    ).inc()


def record_ai_report(report_type: str, duration_seconds: float, success: bool) -> None:
    """Record an AI report generation event."""
    AI_REPORT_DURATION.labels(report_type=report_type).observe(duration_seconds)
    AI_REPORT_REQUESTS_TOTAL.labels(
        report_type=report_type,
        status="success" if success else "failure",
    ).inc()


def record_payment_webhook(gateway: str, success: bool) -> None:
    """Record a payment webhook event."""
    PAYMENT_WEBHOOKS_TOTAL.labels(
        gateway=gateway,
        status="success" if success else "failure",
    ).inc()


def record_kundli_chart(duration_seconds: float) -> None:
    """Record a kundli chart generation."""
    KUNDLI_CHART_DURATION.observe(duration_seconds)


def record_dasha_calc(system: str, success: bool) -> None:
    """Record a dasha calculation."""
    DASHA_CALCULATIONS_TOTAL.labels(
        system=system,
        status="success" if success else "failure",
    ).inc()


# ── FastAPI middleware ────────────────────────────────────────────────────────

class MetricsMiddleware:
    """
    ASGI middleware that records HTTP request count and latency for every
    request.  Normalises path parameters to avoid unbounded label cardinality
    (e.g. /kundli/abc123 becomes /kundli/{session_id}).
    """

    # Map path prefixes to normalised label names
    _PATH_NORMALISE = {
        "/kundli/":    "/kundli/{session_id}",
        "/dasha/":     "/dasha/{session_id}",
        "/profiles/":  "/profiles/{profile_id}",
        "/reports/":   "/reports/{report_id}",
        "/export/":    "/export/{session_id}",
        "/user/":      "/user/{id}",
        "/admin/":     "/admin/{action}",
    }

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        method   = scope.get("method", "UNKNOWN")
        raw_path = scope.get("path", "/")
        endpoint = self._normalise(raw_path)

        start = time.perf_counter()
        status_code = [500]

        async def send_wrapper(message):
            if message["type"] == "http.response.start":
                status_code[0] = message.get("status", 500)
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            duration = time.perf_counter() - start
            sc = str(status_code[0])

            HTTP_REQUESTS_TOTAL.labels(
                method=method, endpoint=endpoint, status_code=sc
            ).inc()
            HTTP_REQUEST_DURATION.labels(
                method=method, endpoint=endpoint
            ).observe(duration)

    def _normalise(self, path: str) -> str:
        for prefix, label in self._PATH_NORMALISE.items():
            if path.startswith(prefix) and path != prefix.rstrip("/"):
                return label
        return path


# ── /metrics endpoint factory ─────────────────────────────────────────────────

def setup_metrics_endpoint(app) -> None:
    """
    Register GET /metrics on the given FastAPI app.
    Only available when prometheus_client is installed.
    If not installed, the endpoint returns 501 Not Implemented.
    """
    from fastapi import Response

    @app.get(
        "/metrics",
        include_in_schema=False,  # Don't expose in public OpenAPI docs
        tags=["ops"],
        summary="Prometheus metrics scrape endpoint",
    )
    def metrics_endpoint() -> Response:
        if not _PROMETHEUS_AVAILABLE:
            return Response(
                content="# prometheus_client not installed\n",
                status_code=501,
                media_type="text/plain",
            )
        return Response(
            content=generate_latest(REGISTRY),
            media_type=CONTENT_TYPE_LATEST,
        )
