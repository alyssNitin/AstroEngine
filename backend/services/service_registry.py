"""
backend/services/service_registry.py
======================================
Factory functions for obtaining service clients.

When USE_MICROSERVICES=true  → returns HTTP client that calls the microservice.
When USE_MICROSERVICES=false → returns a LocalFallback that calls the local module.

This is the Dependency Inversion / Strategy pattern in action:
callers in main.py do::

    from backend.services.service_registry import get_dasha_client
    client = get_dasha_client()
    result = client.calculate(birth_chart=chart)

...and they never need to know whether they're talking to a microservice
or a local function.

Environment variables
---------------------
USE_MICROSERVICES    'true' | 'false'  (default: false)
DASHA_ENGINE_URL     URL of dasha-engine   (default: http://localhost:8001)
NOTIFICATION_URL     URL of notification   (default: http://localhost:8002)
ANALYTICS_URL        URL of analytics      (default: http://localhost:8003)
SERVICE_SECRET       Shared inter-service auth secret
"""
from __future__ import annotations

import os
import logging

logger = logging.getLogger(__name__)

_USE_MICROSERVICES = os.environ.get("USE_MICROSERVICES", "false").lower() == "true"
_SERVICE_SECRET    = os.environ.get("SERVICE_SECRET", "")

_DASHA_URL        = os.environ.get("DASHA_ENGINE_URL",  "http://localhost:8001")
_NOTIFICATION_URL = os.environ.get("NOTIFICATION_URL",  "http://localhost:8002")
_ANALYTICS_URL    = os.environ.get("ANALYTICS_URL",     "http://localhost:8003")


# ── Dasha ─────────────────────────────────────────────────────────────────────

def get_dasha_client():
    """
    Return the appropriate Dasha client.

    Returns DashaServiceClient (HTTP) when USE_MICROSERVICES=true,
    otherwise DashaLocalFallback which wraps the local dasha engine.
    """
    if _USE_MICROSERVICES:
        from .clients.dasha_client import DashaServiceClient
        logger.info("Using dasha-engine microservice at %s", _DASHA_URL)
        return DashaServiceClient(base_url=_DASHA_URL, service_secret=_SERVICE_SECRET)
    from .local_fallbacks.dasha_fallback import DashaLocalFallback
    return DashaLocalFallback()


# ── Notification ──────────────────────────────────────────────────────────────

def get_notification_client():
    """
    Return the appropriate Notification client.

    Returns NotificationServiceClient (HTTP) when USE_MICROSERVICES=true,
    otherwise NotificationLocalFallback which wraps the local EmailService.
    """
    if _USE_MICROSERVICES:
        from .clients.notification_client import NotificationServiceClient
        logger.info("Using notification microservice at %s", _NOTIFICATION_URL)
        return NotificationServiceClient(
            base_url=_NOTIFICATION_URL, service_secret=_SERVICE_SECRET
        )
    from .local_fallbacks.notification_fallback import NotificationLocalFallback
    return NotificationLocalFallback()


# ── Analytics ─────────────────────────────────────────────────────────────────

def get_analytics_client():
    """
    Return the appropriate Analytics client.

    Returns AnalyticsServiceClient (HTTP) when USE_MICROSERVICES=true,
    otherwise AnalyticsLocalFallback which is a no-op stub.
    """
    if _USE_MICROSERVICES:
        from .clients.analytics_client import AnalyticsServiceClient
        logger.info("Using analytics microservice at %s", _ANALYTICS_URL)
        return AnalyticsServiceClient(
            base_url=_ANALYTICS_URL, service_secret=_SERVICE_SECRET
        )
    from .local_fallbacks.analytics_fallback import AnalyticsLocalFallback
    return AnalyticsLocalFallback()
