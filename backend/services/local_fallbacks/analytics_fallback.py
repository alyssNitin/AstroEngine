"""
Local fallback for the analytics service — no-op stub.
Analytics never break the main request flow (fire-and-forget).
"""
from __future__ import annotations
import logging

logger = logging.getLogger(__name__)


class AnalyticsLocalFallback:
    """Silent no-op — analytics are optional in local/monolith mode."""

    def track(self, event_type: str, user_id=None, meta=None) -> bool:
        logger.debug("[analytics-local] event=%s user=%s", event_type, user_id)
        return True

    def get_traffic(self, from_date: str, to_date: str) -> dict:
        return {"note": "analytics microservice not running"}

    def get_revenue(self, from_date: str, to_date: str) -> dict:
        return {"note": "analytics microservice not running"}

    def get_llm_costs(self, from_date: str, to_date: str) -> dict:
        return {"note": "analytics microservice not running"}

    def health(self) -> dict:
        return {"service": "analytics-service", "status": "local-fallback"}
