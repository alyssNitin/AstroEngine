"""
backend/services/clients/analytics_client.py
=============================================
HTTP client for the analytics microservice.

Usage::

    from backend.services.clients.analytics_client import AnalyticsServiceClient

    client = AnalyticsServiceClient(base_url="http://localhost:8003")
    client.track("reading_started", user_id="uuid-123")
"""
from __future__ import annotations

from .base import BaseServiceClient


class AnalyticsServiceClient(BaseServiceClient):
    """HTTP client wrapping the analytics microservice REST API."""

    def track(
        self,
        event_type: str,
        user_id: str | None = None,
        meta: dict | None = None,
    ) -> bool:
        """
        Fire-and-forget event tracking.

        Never raises — analytics should never break the main request flow.
        """
        try:
            resp = self._post("/events/track", {
                "event_type": event_type,
                "user_id":    user_id,
                "meta":       meta or {},
            })
            return bool(resp.get("tracked", False))
        except Exception:
            return False   # silent degradation

    def get_traffic(self, from_date: str, to_date: str) -> dict:
        return self._get("/admin/analytics/traffic",
                         params={"from_date": from_date, "to_date": to_date})

    def get_revenue(self, from_date: str, to_date: str) -> dict:
        return self._get("/admin/analytics/revenue",
                         params={"from_date": from_date, "to_date": to_date})

    def get_llm_costs(self, from_date: str, to_date: str) -> dict:
        return self._get("/admin/analytics/llm-costs",
                         params={"from_date": from_date, "to_date": to_date})

    def health(self) -> dict:
        return self._get("/health")
