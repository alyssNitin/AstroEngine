"""
backend/monitoring/alerting.py
================================
PagerDuty Events API v2 integration for NarayanAstroReader.

Architecture §11.5: PagerDuty alerting on SLA breach and elevated error rates.

Environment variables
---------------------
  PAGERDUTY_INTEGRATION_KEY   : PagerDuty service integration key (Events API v2)
  PAGERDUTY_ENABLED           : "true" to send real alerts (default: "false" in dev)
  ALERT_ERROR_RATE_THRESHOLD  : float, error rate % to trigger P1 alert (default: 1.0)
  ALERT_LATENCY_P99_MS        : int, p99 latency ms to trigger alert (default: 5000)

Usage
-----
    from backend.monitoring.alerting import alert_manager
    alert_manager.trigger_critical("JWT_SECRET missing", "Production startup")
    alert_manager.resolve("JWT_SECRET missing")
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import threading
import time
import urllib.request
import urllib.error
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)

_PAGERDUTY_EVENTS_URL = "https://events.pagerduty.com/v2/enqueue"

_INTEGRATION_KEY: str = os.environ.get("PAGERDUTY_INTEGRATION_KEY", "")
_ENABLED: bool = os.environ.get("PAGERDUTY_ENABLED", "false").lower() == "true"

# SLA thresholds
_ERROR_RATE_THRESHOLD: float = float(os.environ.get("ALERT_ERROR_RATE_THRESHOLD", "1.0"))
_LATENCY_P99_MS: int = int(os.environ.get("ALERT_LATENCY_P99_MS", "5000"))


@dataclass
class Alert:
    dedup_key: str
    summary: str
    severity: str          # critical | error | warning | info
    source: str
    component: str
    triggered_at: float = field(default_factory=time.time)
    resolved: bool = False


class AlertManager:
    """
    Manages sending and resolving PagerDuty incidents via Events API v2.

    Thread-safe.  Deduplicates by dedup_key so repeated triggers don't
    spam PagerDuty with duplicate incidents.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._active: dict[str, Alert] = {}   # dedup_key → Alert

    # ── Public API ────────────────────────────────────────────────────────────

    def trigger_critical(self, summary: str, component: str = "api") -> str:
        """Trigger a P0 critical alert."""
        return self._trigger(summary, "critical", component)

    def trigger_error(self, summary: str, component: str = "api") -> str:
        """Trigger a P1 high-severity alert."""
        return self._trigger(summary, "error", component)

    def trigger_warning(self, summary: str, component: str = "api") -> str:
        """Trigger a P2 warning alert."""
        return self._trigger(summary, "warning", component)

    def resolve(self, dedup_key: str) -> None:
        """Resolve a previously triggered alert by dedup_key."""
        with self._lock:
            if dedup_key not in self._active:
                return
            self._active[dedup_key].resolved = True

        self._send_event("resolve", dedup_key, "", "info", "api")
        with self._lock:
            self._active.pop(dedup_key, None)

    def check_error_rate(self, error_count: int, total_count: int) -> None:
        """
        Auto-trigger/resolve error-rate alert based on current counts.
        Call periodically (e.g. every 60s) from a monitoring loop.
        """
        if total_count == 0:
            return
        rate = (error_count / total_count) * 100
        key = "error_rate_breach"

        if rate > _ERROR_RATE_THRESHOLD:
            self.trigger_error(
                f"Error rate {rate:.1f}% exceeds threshold {_ERROR_RATE_THRESHOLD}%",
                component="api",
            )
        else:
            self.resolve(key)

    def check_latency(self, p99_ms: float) -> None:
        """Auto-trigger/resolve latency breach alert."""
        key = "latency_p99_breach"
        if p99_ms > _LATENCY_P99_MS:
            self.trigger_error(
                f"p99 latency {p99_ms:.0f}ms exceeds SLA {_LATENCY_P99_MS}ms",
                component="api",
            )
        else:
            self.resolve(key)

    def alert_payment_failure(self, gateway: str, error: str) -> None:
        """Trigger a payment webhook failure alert."""
        self.trigger_error(
            f"Payment webhook failure [{gateway}]: {error}",
            component="payment",
        )

    def alert_db_connection_loss(self, error: str) -> None:
        """Trigger a critical DB connection lost alert."""
        self.trigger_critical(
            f"Database connection lost: {error}",
            component="database",
        )

    # ── Internal ──────────────────────────────────────────────────────────────

    def _trigger(self, summary: str, severity: str, component: str) -> str:
        dedup_key = self._make_dedup_key(summary, component)
        with self._lock:
            if dedup_key in self._active and not self._active[dedup_key].resolved:
                return dedup_key   # Already active — no duplicate
            self._active[dedup_key] = Alert(
                dedup_key=dedup_key,
                summary=summary,
                severity=severity,
                source="NarayanAstroReader",
                component=component,
            )

        self._send_event("trigger", dedup_key, summary, severity, component)
        return dedup_key

    def _send_event(
        self,
        action: str,        # "trigger" | "resolve"
        dedup_key: str,
        summary: str,
        severity: str,
        component: str,
    ) -> None:
        if not _ENABLED:
            logger.info(
                "PagerDuty [DISABLED] action=%s key=%s summary=%s",
                action, dedup_key, summary,
            )
            return

        if not _INTEGRATION_KEY:
            logger.warning(
                "PAGERDUTY_INTEGRATION_KEY not set — cannot send alert: %s", summary
            )
            return

        payload = {
            "routing_key": _INTEGRATION_KEY,
            "dedup_key":   dedup_key,
            "event_action": action,
        }

        if action == "trigger":
            payload["payload"] = {
                "summary":   summary,
                "severity":  severity,
                "source":    "NarayanAstroReader API",
                "component": component,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "custom_details": {
                    "environment": os.environ.get("ENVIRONMENT", "development"),
                    "service":     "narayan-astro-reader",
                },
            }

        body = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            _PAGERDUTY_EVENTS_URL,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=5) as resp:
                logger.info(
                    "PagerDuty %s sent: key=%s status=%d",
                    action, dedup_key, resp.status,
                )
        except urllib.error.HTTPError as e:
            logger.error(
                "PagerDuty HTTP error %d for key=%s: %s", e.code, dedup_key, e.read()
            )
        except Exception as e:
            logger.error("PagerDuty send failed for key=%s: %s", dedup_key, e)

    @staticmethod
    def _make_dedup_key(summary: str, component: str) -> str:
        raw = f"{component}:{summary}"
        return hashlib.sha256(raw.encode()).hexdigest()[:32]


# ── Singleton ─────────────────────────────────────────────────────────────────
alert_manager = AlertManager()


# ── FastAPI integration helper ─────────────────────────────────────────────────

def wire_alerting_to_app(app) -> None:
    """
    Register a startup/shutdown handler and an exception handler on the
    FastAPI app so critical unhandled exceptions trigger PagerDuty alerts.
    """
    from fastapi import Request
    from fastapi.responses import JSONResponse

    @app.exception_handler(Exception)
    async def _unhandled_exception_handler(request: Request, exc: Exception):
        alert_manager.trigger_error(
            f"Unhandled exception on {request.method} {request.url.path}: "
            f"{type(exc).__name__}: {exc}",
            component="api",
        )
        return JSONResponse(
            status_code=500,
            content={"detail": "An internal server error occurred."},
        )
