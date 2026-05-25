"""
backend/services/clients/dasha_client.py
==========================================
HTTP client for the dasha-engine microservice.

Design (SOLID)
--------------
- Single Responsibility : translates Python calls to HTTP; no dasha logic.
- Open / Closed         : new endpoints on the service → add a method here;
                          callers are unaffected.
- Dependency Inversion  : callers use this class through the factory
                          get_dasha_client() which returns either this HTTP
                          client or the local fallback — transparent swap.

Usage::

    from backend.services.clients.dasha_client import DashaServiceClient

    client = DashaServiceClient(base_url="http://localhost:8001", service_secret="...")
    result = client.calculate(birth_chart=chart, system="vimshottari", depth=2)
"""
from __future__ import annotations

from datetime import date
from typing import Any

from .base import BaseServiceClient


class DashaServiceClient(BaseServiceClient):
    """
    HTTP client wrapping the dasha-engine microservice REST API.

    All public methods mirror the service's endpoint contract so callers
    see a clean Python interface with no HTTP plumbing.
    """

    def list_systems(self) -> list[dict]:
        """
        Return metadata for all registered Dasha systems.

        Delegates to: GET /dasha/systems
        """
        resp = self._get("/dasha/systems")
        return resp.get("systems", [])

    def calculate(
        self,
        birth_chart: dict[str, Any],
        profile_id: str = "local",
        system: str = "vimshottari",
        from_date: str | None = None,
        to_date: str | None = None,
        depth: int = 2,
    ) -> dict:
        """
        Compute a full Dasha timeline.

        Parameters
        ----------
        birth_chart : Kundli JSON from the kundli-engine.
        profile_id  : User profile UUID (echoed in response).
        system      : Dasha system name (vimshottari, yogini, …).
        from_date   : Timeline start date (ISO 8601, default: today).
        to_date     : Timeline end date   (ISO 8601, default: today + 20 yr).
        depth       : Nesting depth 1–5 (default: 2 = Maha + Antardasha).

        Delegates to: POST /dasha/calculate
        """
        return self._post("/dasha/calculate", {
            "profile_id":  profile_id,
            "birth_chart": birth_chart,
            "system":      system,
            "from_date":   from_date or date.today().isoformat(),
            "to_date":     to_date   or f"{date.today().year + 20}-12-31",
            "depth":       depth,
        })

    def current(
        self,
        birth_chart: dict[str, Any],
        system: str = "vimshottari",
    ) -> dict:
        """
        Get the active Mahadasha + Antardasha for today.

        Delegates to: POST /dasha/current
        """
        return self._post("/dasha/current", {
            "birth_chart": birth_chart,
            "system":      system,
        })

    def health(self) -> dict:
        """Ping the service health endpoint."""
        return self._get("/health")
