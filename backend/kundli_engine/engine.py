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

    @staticmethod
    def _sanitize_place(place_name: str) -> str:
        """
        Normalize place_name so PyJHora's utils.get_location() never crashes
        from a tuple-unpack error.

        PyJHora's Google-scrape fallback does:
            _city, _country = place_name.split(',')
        which raises ValueError when place_name has >1 comma
        (e.g. "Mumbai, Maharashtra, India" → 3 parts).

        We collapse such names to "City, Country" (first + last segment).
        Single-part or already-clean "City, Country" names pass through unchanged.
        """
        parts = [p.strip() for p in place_name.split(",") if p.strip()]
        if len(parts) <= 2:
            return place_name  # already safe
        # Keep first segment (city) + last segment (country)
        return f"{parts[0]}, {parts[-1]}"

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
        # Sanitize place name before passing to PyJHora to prevent
        # "too many values to unpack" when the name has >1 comma.
        safe_place = self._sanitize_place(place_name)
        return self._engine.generate(
            place_name=safe_place,
            date_of_birth=date_of_birth,
            time_of_birth=time_of_birth,
            latitude=latitude,
            longitude=longitude,
            timezone_offset=timezone_offset,
            name=name,
        )


    def calculate(self, **kwargs) -> dict:
        """Alias for generate() — accepts the same keyword arguments."""
        return self.generate(**kwargs)

    def get_dasha(self, system: str, kundli: dict) -> dict:
        """
        Calculate an additional dasha system for an already-computed kundli.

        Parameters
        ----------
        system : yogini | chara | kalachakra | narayana | moola
        kundli : the dict returned by generate() / calculate()

        Returns a dasha dict: {name, total_years, balance_at_birth, periods}.
        """
        from backend.kundli_engine.dasha_systems import calculate_dasha
        return calculate_dasha(
            system     = system,
            birth_info = kundli.get("birth_info", {}),
            lagna      = kundli.get("lagna", {}),
            rasi_chart = kundli.get("rasi_chart", {}),
        )

    @staticmethod
    def available_dasha_systems() -> list:
        """Return list of additional dasha systems (beyond Vimshottari)."""
        from backend.kundli_engine.dasha_systems import available_systems
        return available_systems()


    def get_shadbala(self, kundli: dict) -> dict:
        """
        Calculate Shadbala (six-fold planetary strength) for a kundli.

        Parameters
        ----------
        kundli : dict returned by generate() / calculate()

        Returns a dict with per-planet strength scores and rankings.
        See backend/kundli_engine/shadbala.py for full structure.
        """
        from backend.kundli_engine.shadbala import calculate_shadbala
        return calculate_shadbala(kundli)

    def get_ashtakavarga(self, kundli: dict) -> dict:
        """
        Calculate Ashtakavarga (eight-source benefic points) for a kundli.

        Parameters
        ----------
        kundli : dict returned by generate() / calculate()

        Returns Bhinnashtakavarga per planet, Sarvashtakavarga,
        transit strength, strong/weak signs.
        See backend/kundli_engine/ashtakavarga.py for full structure.
        """
        from backend.kundli_engine.ashtakavarga import calculate_ashtakavarga
        return calculate_ashtakavarga(kundli)

    def get_ashtakavarga_transit(self, planet: str, transit_sign: str, kundli: dict) -> dict:
        """
        Score a planet's transit through a specific sign using Ashtakavarga.

        Returns: {planet, transit_sign, bhinna_rekhas, sarva_rekhas, quality}
        """
        from backend.kundli_engine.ashtakavarga import ashtakavarga_transit_score
        return ashtakavarga_transit_score(planet, transit_sign, kundli)

    # ── B19: Divisional charts D1-D16 ─────────────────────────────────────────

    def get_divisional_chart(self, kundli: dict, division: int) -> dict:
        """
        B19 -- Calculate a single divisional chart (Varga).

        Parameters
        ----------
        kundli   : dict returned by generate() / calculate()
        division : int -- e.g. 9 for Navamsa, 10 for Dasamsa

        Supported divisions: 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 12, 16

        Returns dict with keys:
          name, division, significance, ascendant, planets
        """
        from backend.kundli_engine.divisional_charts import calculate_divisional_chart
        return calculate_divisional_chart(kundli, division)

    def get_all_divisional_charts(self, kundli: dict) -> dict:
        """
        B19 -- Calculate all supported divisional charts (D1-D16).

        Returns a dict keyed by "D{N}_{Name}" e.g. "D9_Navamsa".
        """
        from backend.kundli_engine.divisional_charts import calculate_all_divisional_charts
        return calculate_all_divisional_charts(kundli)

    def get_varga_strength(self, planet: str, kundli: dict) -> dict:
        """
        B19 -- Compute Vaiseshikamsa (Varga strength) of a planet across all Vargas.

        Returns: {planet, own_sign_count, exalted_count, total_strong,
                  vaiseshikamsa, vargottama, detail}
        """
        from backend.kundli_engine.divisional_charts import get_varga_strength
        return get_varga_strength(planet, kundli)

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
                "degree_str": "14d30m0s",
                "full_longitude": 164.5,
                "nakshatra": "Hasta",
                "nakshatra_pada": 1,
            },
            "rasi_chart": {
                "Sun": {"rasi": "Gemini", "degree": 0.5, "degree_str": "0d30m0s",
                        "nakshatra": "Mrigashira", "nakshatra_pada": 3, "retrograde": False,
                        "rasi_index": 2, "full_longitude": 60.5},
                "Moon": {"rasi": "Taurus", "degree": 22.3, "degree_str": "22d18m0s",
                         "nakshatra": "Rohini", "nakshatra_pada": 4, "retrograde": False,
                         "rasi_index": 1, "full_longitude": 52.3},
                "Mars": {"rasi": "Capricorn", "degree": 8.0, "degree_str": "8d0m0s",
                         "nakshatra": "Shravana", "nakshatra_pada": 1, "retrograde": False,
                         "rasi_index": 9, "full_longitude": 278.0},
                "Mercury": {"rasi": "Gemini", "degree": 18.2, "degree_str": "18d12m0s",
                            "nakshatra": "Ardra", "nakshatra_pada": 2, "retrograde": False,
                            "rasi_index": 2, "full_longitude": 78.2},
                "Jupiter": {"rasi": "Cancer", "degree": 5.7, "degree_str": "5d42m0s",
                            "nakshatra": "Pushya", "nakshatra_pada": 1, "retrograde": False,
                            "rasi_index": 3, "full_longitude": 95.7},
                "Venus": {"rasi": "Cancer", "degree": 25.1, "degree_str": "25d6m0s",
                          "nakshatra": "Ashlesha", "nakshatra_pada": 2, "retrograde": False,
                          "rasi_index": 3, "full_longitude": 115.1},
                "Saturn": {"rasi": "Capricorn", "degree": 20.0, "degree_str": "20d0m0s",
                           "nakshatra": "Shravana", "nakshatra_pada": 4, "retrograde": True,
                           "rasi_index": 9, "full_longitude": 290.0},
                "Rahu": {"rasi": "Capricorn", "degree": 15.5, "degree_str": "15d30m0s",
                         "nakshatra": "Shravana", "nakshatra_pada": 2, "retrograde": True,
                         "rasi_index": 9, "full_longitude": 285.5},
                "Ketu": {"rasi": "Cancer", "degree": 15.5, "degree_str": "15d30m0s",
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
