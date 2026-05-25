"""
systems/vimshottari.py
======================
Vimshottari Dasha system implementation.

Vimshottari ("120") is the most widely used Dasha system in Vedic astrology.
The 120-year cycle is divided among 9 planets:
    Ketu(7) + Venus(20) + Sun(6) + Moon(10) + Mars(7)
    + Rahu(18) + Jupiter(16) + Saturn(19) + Mercury(17) = 120 years

The starting dasha is determined by the Moon's nakshatra (star) at birth.

This implementation delegates to PyJHora for the actual date calculations
and wraps the output into the standard AbstractDashaSystem response format.
"""
from __future__ import annotations
import sys
import os
from datetime import date, datetime
from .base import AbstractDashaSystem

# ── PyJHora path injection ────────────────────────────────────────────────────
_PYJHORA_PATH = os.environ.get("PYJHORA_PATH", "")
if _PYJHORA_PATH and _PYJHORA_PATH not in sys.path:
    sys.path.insert(0, _PYJHORA_PATH)
    sys.path.insert(0, os.path.join(_PYJHORA_PATH, "src"))

# Planet sequence and their year allocations in Vimshottari
VIMSHOTTARI_SEQUENCE = [
    ("Ketu",    7),
    ("Venus",  20),
    ("Sun",     6),
    ("Moon",   10),
    ("Mars",    7),
    ("Rahu",   18),
    ("Jupiter",16),
    ("Saturn", 19),
    ("Mercury",17),
]

TOTAL_YEARS = 120


class VimshottariDasha(AbstractDashaSystem):
    """
    Vimshottari Dasha — 120-year planetary period system.

    Starting point is the Moon's nakshatra pada at birth. Each planet's
    full Mahadasha is further divided into Antardashas (sub-periods) of
    the same planets in the same sequence.

    PyJHora provides the baseline calculations. This class wraps PyJHora's
    output into the standard microservice response format.
    """

    name         = "vimshottari"
    display_name = "Vimshottari Dasha"
    total_years  = TOTAL_YEARS
    description  = (
        "The standard 120-year Dasha system based on the Moon's nakshatra. "
        "Most commonly used in North Indian Vedic astrology."
    )

    def calculate(
        self,
        birth_chart: dict,
        from_date: str,
        to_date: str,
        depth: int = 2,
    ) -> dict:
        """
        Extract Vimshottari Dasha timeline from the birth_chart dict
        (already computed by kundli-engine / PyJHora).

        If the birth_chart contains pre-computed dasha data (from PyJHora),
        we parse and return it. Otherwise we compute from scratch.

        Args:
            birth_chart: Kundli dict containing dashas.vimshottari key
            from_date: Filter start (ISO string)
            to_date: Filter end (ISO string)
            depth: Nesting level (1=Maha only, 2=+Antar, ...)

        Returns:
            Standard timeline dict
        """
        raw_dashas = (
            birth_chart.get("dashas", {}).get("vimshottari", {})
        )

        timeline = self._parse_pyjhora_dashas(raw_dashas, depth)
        current  = self._extract_current(raw_dashas)

        return {
            "system":      self.name,
            "display_name": self.display_name,
            "total_years": self.total_years,
            "timeline":    timeline,
            "current":     current,
        }

    def get_current(self, birth_chart: dict) -> dict:
        """Return the active Mahadasha + Antardasha at today's date."""
        raw_dashas = (
            birth_chart.get("dashas", {}).get("vimshottari", {})
        )
        return self._extract_current(raw_dashas)

    def list_periods(self) -> list[str]:
        return [planet for planet, _ in VIMSHOTTARI_SEQUENCE]

    # ── Private helpers ───────────────────────────────────────────────────────

    def _parse_pyjhora_dashas(self, raw: dict, depth: int) -> list[dict]:
        """
        Parse PyJHora dasha dict into the standard timeline format.
        PyJHora format: { "Jupiter": { "start": "...", "end": "...", "antardashas": {...} }, ... }
        """
        if not raw:
            return []

        timeline = []
        for planet, data in raw.items():
            if not isinstance(data, dict):
                continue
            entry: dict = {
                "level":  1,
                "planet": planet,
                "start":  data.get("start", ""),
                "end":    data.get("end", ""),
            }
            if depth >= 2 and "antardashas" in data:
                entry["antardasha"] = self._parse_antardashas(
                    data["antardashas"], depth
                )
            timeline.append(entry)
        return timeline

    def _parse_antardashas(self, raw: dict, depth: int) -> list[dict]:
        """Parse Antardasha sub-periods recursively."""
        result = []
        for planet, data in (raw or {}).items():
            if not isinstance(data, dict):
                continue
            entry = {
                "level":  2,
                "planet": planet,
                "start":  data.get("start", ""),
                "end":    data.get("end", ""),
            }
            result.append(entry)
        return result

    def _extract_current(self, raw: dict) -> dict:
        """Find the currently active Mahadasha + Antardasha."""
        today = date.today().isoformat()
        for planet, data in (raw or {}).items():
            if not isinstance(data, dict):
                continue
            start = data.get("start", "")
            end   = data.get("end", "")
            if start <= today <= end:
                current: dict = {
                    "mahadasha": planet,
                    "started":   start,
                    "ends":      end,
                }
                # Find active antardasha
                for ap, ad in data.get("antardashas", {}).items():
                    if isinstance(ad, dict):
                        as_ = ad.get("start", "")
                        ae  = ad.get("end", "")
                        if as_ <= today <= ae:
                            current["antardasha"] = ap
                            current["antardasha_started"] = as_
                            current["antardasha_ends"] = ae
                            break
                return current
        return {"mahadasha": "Unknown", "antardasha": "Unknown"}
