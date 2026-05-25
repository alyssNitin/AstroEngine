"""
kundli_engine/engine.py
=======================
Thin adapter that delegates all chart computation to PyJHora's KundliEngine.
Adds path injection so PyJHora is importable from any working directory.
"""
from __future__ import annotations
import sys
import os

# ── Inject PyJHora path before importing anything from it ───────────────────
from backend.config import inject_pyjhora_path, PYJHORA_PATH
inject_pyjhora_path()
# ────────────────────────────────────────────────────────────────────────────

try:
    # Import the existing, battle-tested engine from PyJHora
    sys.path.insert(0, PYJHORA_PATH)
    from kundli_engine import KundliEngine as _BaseEngine          # type: ignore
    from kundli_engine import PLANET_NAMES, RASI_NAMES             # type: ignore
    _PYJHORA_AVAILABLE = True
except ImportError as _err:
    _PYJHORA_AVAILABLE = False
    _IMPORT_ERROR = str(_err)


class KundliEngine:
    """
    Facade over PyJHora KundliEngine.
    All public methods mirror the base engine; we add error wrapping,
    availability check, and a stub mode for unit testing.
    """

    def __init__(self) -> None:
        if _PYJHORA_AVAILABLE:
            self._engine = _BaseEngine()
        else:
            self._engine = None

    @property
    def available(self) -> bool:
        return _PYJHORA_AVAILABLE

    def generate(
        self,
        place_name: str,
        date_of_birth: str,
        time_of_birth: str,
        latitude: float | None = None,
        longitude: float | None = None,
        timezone_offset: float | None = None,
        name: str = "",
    ) -> dict:
        """
        Generate a complete kundli dict.
        Raises RuntimeError if PyJHora is not importable.
        Raises ValueError for bad birth data (propagated from PyJHora).
        """
        if not _PYJHORA_AVAILABLE:
            raise RuntimeError(
                f"PyJHora is not available: {_IMPORT_ERROR}.\n"
                f"Expected at: {PYJHORA_PATH}\n"
                "Install pyswisseph and ensure PyJHora is at the configured path."
            )
        return self._engine.generate(
            place_name=place_name,
            date_of_birth=date_of_birth,
            time_of_birth=time_of_birth,
            latitude=latitude,
            longitude=longitude,
            timezone_offset=timezone_offset,
            name=name,
        )

    def stub_kundli(self, name: str = "Test User") -> dict:
        """
        Return a minimal kundli dict for unit testing WITHOUT PyJHora.
        Mirrors the real output structure so tests can validate downstream logic.
        """
        return {
            "birth_info": {
                "name": name,
                "date_of_birth": "1990-06-15",
                "time_of_birth": "14:30:00",
                "place": "Chennai, India",
                "latitude": 13.0827,
                "longitude": 80.2707,
                "timezone_offset": 5.5,
                "ayanamsa_mode": "LAHIRI",
                "ayanamsa_value": 23.85,
            },
            "panchanga": {
                "weekday": "Friday",
                "tithi": "Panchami",
                "nakshatra": "Rohini",
                "yoga": "Siddha",
                "karana": "Bava",
            },
            "lagna": {
                "rasi": "Virgo",
                "rasi_short": "Vi",
                "degree": 14.5,
                "degree_str": "14°30'0\"",
                "full_longitude": 164.5,
                "nakshatra": "Hasta",
                "nakshatra_pada": 1,
            },
            "rasi_chart": {
                "Sun": {"rasi": "Gemini", "degree": 0.5, "degree_str": "0°30'0\"",
                        "nakshatra": "Mrigashira", "nakshatra_pada": 3, "retrograde": False,
                        "rasi_index": 2, "full_longitude": 60.5},
                "Moon": {"rasi": "Taurus", "degree": 22.3, "degree_str": "22°18'0\"",
                         "nakshatra": "Rohini", "nakshatra_pada": 4, "retrograde": False,
                         "rasi_index": 1, "full_longitude": 52.3},
                "Mars": {"rasi": "Capricorn", "degree": 8.0, "degree_str": "8°0'0\"",
                         "nakshatra": "Shravana", "nakshatra_pada": 1, "retrograde": False,
                         "rasi_index": 9, "full_longitude": 278.0},
                "Mercury": {"rasi": "Gemini", "degree": 18.2, "degree_str": "18°12'0\"",
                            "nakshatra": "Ardra", "nakshatra_pada": 2, "retrograde": False,
                            "rasi_index": 2, "full_longitude": 78.2},
                "Jupiter": {"rasi": "Cancer", "degree": 5.7, "degree_str": "5°42'0\"",
                            "nakshatra": "Pushya", "nakshatra_pada": 1, "retrograde": False,
                            "rasi_index": 3, "full_longitude": 95.7},
                "Venus": {"rasi": "Cancer", "degree": 25.1, "degree_str": "25°6'0\"",
                          "nakshatra": "Ashlesha", "nakshatra_pada": 2, "retrograde": False,
                          "rasi_index": 3, "full_longitude": 115.1},
                "Saturn": {"rasi": "Capricorn", "degree": 20.0, "degree_str": "20°0'0\"",
                           "nakshatra": "Shravana", "nakshatra_pada": 4, "retrograde": True,
                           "rasi_index": 9, "full_longitude": 290.0},
                "Rahu": {"rasi": "Capricorn", "degree": 15.5, "degree_str": "15°30'0\"",
                         "nakshatra": "Shravana", "nakshatra_pada": 2, "retrograde": True,
                         "rasi_index": 9, "full_longitude": 285.5},
                "Ketu": {"rasi": "Cancer", "degree": 15.5, "degree_str": "15°30'0\"",
                         "nakshatra": "Pushya", "nakshatra_pada": 4, "retrograde": True,
                         "rasi_index": 3, "full_longitude": 105.5},
            },
            "divisional_charts": {
                "D9_Navamsa": {
                    "ascendant": {"rasi": "Aries", "degree": 12.0},
                    "planets": {
                        "Sun": {"rasi": "Leo", "degree": 5.0},
                        "Moon": {"rasi": "Taurus", "degree": 20.0},
                    },
                },
                "D10_Dasamsa": {
                    "ascendant": {"rasi": "Taurus", "degree": 8.0},
                    "planets": {
                        "Sun": {"rasi": "Libra", "degree": 3.0},
                    },
                },
            },
            "bhava_chart": [{"house": i + 1} for i in range(12)],
            "special_planets": {},
            "dashas": {
                "vimshottari": {
                    "balance_at_birth": "9y 2m 5d",
                    "periods": [
                        {"maha_lord": "Moon", "antara_lord": "Moon", "pratyantara_lord": "Moon",
                         "start_date": "1990-06-15"},
                        {"maha_lord": "Moon", "antara_lord": "Mars", "pratyantara_lord": "Moon",
                         "start_date": "1990-11-18"},
                        {"maha_lord": "Mars", "antara_lord": "Mars", "pratyantara_lord": "Mars",
                         "start_date": "1999-08-20"},
                        {"maha_lord": "Rahu", "antara_lord": "Rahu", "pratyantara_lord": "Rahu",
                         "start_date": "2006-08-20"},
                        {"maha_lord": "Jupiter", "antara_lord": "Jupiter", "pratyantara_lord": "Jupiter",
                         "start_date": "2024-08-20"},
                    ],
                }
            },
        }
