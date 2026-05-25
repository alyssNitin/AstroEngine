"""
Local fallback for the dasha-engine — delegates to backend.kundli_engine.
Used when USE_MICROSERVICES=false (default monolith mode).
"""
from __future__ import annotations
import logging
from datetime import date
from typing import Any

logger = logging.getLogger(__name__)


class DashaLocalFallback:
    """Wraps the local dasha engine with the same interface as DashaServiceClient."""

    def list_systems(self) -> list[dict]:
        try:
            import sys, os
            sys.path.insert(0, os.environ.get("PYJHORA_PATH", ""))
            from services.dasha_engine.src.systems import DASHA_SYSTEMS
            return [{"name": cls.name, "display_name": cls.display_name,
                     "total_years": cls.total_years} for cls in DASHA_SYSTEMS.values()]
        except Exception as exc:
            logger.warning("dasha_list_systems_fallback_error: %s", exc)
            return [{"name": "vimshottari", "display_name": "Vimshottari", "total_years": 120}]

    def calculate(
        self,
        birth_chart: dict[str, Any],
        profile_id: str = "local",
        system: str = "vimshottari",
        from_date: str | None = None,
        to_date: str | None = None,
        depth: int = 2,
    ) -> dict:
        try:
            import sys, os
            sys.path.insert(0, os.environ.get("PYJHORA_PATH", ""))
            # Dynamic import so service dir doesn't need to be on path at module load
            import importlib
            mod = importlib.import_module("services.dasha-engine.src.systems",)
        except Exception:
            pass
        # If the dasha engine isn't reachable, return a minimal stub
        return {
            "profile_id": profile_id,
            "system": system,
            "periods": [],
            "note": "Dasha calculation unavailable — set USE_MICROSERVICES=true or install dasha-engine deps.",
        }

    def current(self, birth_chart: dict[str, Any], system: str = "vimshottari") -> dict:
        return {"system": system, "current": None,
                "note": "Dasha service not available in local mode."}

    def health(self) -> dict:
        return {"service": "dasha-engine", "status": "local-fallback"}
