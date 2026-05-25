"""
kundli_engine/shadbala.py
=========================
Shadbala — the six-fold planetary strength system from Parashari astrology.

The six sources of strength (balas):
  1. Sthana Bala   — positional strength (exaltation, own sign, etc.)
  2. Dig Bala      — directional strength (strongest house for each planet)
  3. Kala Bala     — temporal strength (day/night, hora, paksha, etc.)
  4. Chesta Bala   — motional strength (direct, slow, retrograde)
  5. Naisargika Bala — natural/permanent strength
  6. Drik Bala     — aspectual strength from other planets

All results are expressed in Shashtiamsas (1/60th of a sign = 1 unit).
Minimum required strengths (Ishta/Kashta thresholds) are also provided.

Input: kundli dict from KundliEngine.generate()
Output: dict with per-planet scores and totals.

Note: Full precision Shadbala requires exact house cusps, sunrise/sunset,
ayanamsa, and sub-division data. This module provides a well-structured
approximation from the data available in the standard kundli dict.
"""
from __future__ import annotations

import math
from typing import Any

# ── Constants ─────────────────────────────────────────────────────────────────

PLANETS = ["Sun", "Moon", "Mars", "Mercury", "Jupiter", "Venus", "Saturn"]

# Naisargika Bala (natural strength, fixed, in shashtiamsas)
_NAISARGIKA = {
    "Sun":     60.0,
    "Moon":    51.43,
    "Mars":    17.14,
    "Mercury": 25.70,
    "Jupiter": 34.28,
    "Venus":   42.86,
    "Saturn":   8.57,
}

# Dig Bala strongest house (1-based)
# Sun/Mars → 10th, Moon/Venus → 4th, Mercury/Jupiter → 1st, Saturn → 7th
_DIG_BALA_HOUSE = {
    "Sun": 10, "Moon": 4, "Mars": 10,
    "Mercury": 1, "Jupiter": 1,
    "Venus": 4, "Saturn": 7,
}

# Exaltation signs (0-indexed: 0=Aries, …, 11=Pisces)
_EXALT_SIGN = {
    "Sun": 0, "Moon": 1, "Mars": 9,
    "Mercury": 5, "Jupiter": 3,
    "Venus": 11, "Saturn": 6,
}
# Debilitation sign = exaltation + 6
_DEBIL_SIGN = {k: (v + 6) % 12 for k, v in _EXALT_SIGN.items()}

# Own signs (moolatrikona/swakshetra)
_OWN_SIGNS = {
    "Sun":     [4],       # Leo
    "Moon":    [3],       # Cancer
    "Mars":    [0, 7],    # Aries, Scorpio
    "Mercury": [2, 5],    # Gemini, Virgo
    "Jupiter": [8, 11],   # Sagittarius, Pisces
    "Venus":   [1, 6],    # Taurus, Libra
    "Saturn":  [9, 10],   # Capricorn, Aquarius
}

_RASIS = [
    "Aries","Taurus","Gemini","Cancer","Leo","Virgo",
    "Libra","Scorpio","Sagittarius","Capricorn","Aquarius","Pisces",
]

# ── Helpers ───────────────────────────────────────────────────────────────────

def _rasi_to_idx(rasi: str) -> int:
    try:
        return _RASIS.index(rasi)
    except ValueError:
        return 0


def _planet_sign(planet: str, rasi_chart: dict) -> int:
    return rasi_chart.get(planet, {}).get("rasi_index", 0)


def _planet_degree(planet: str, rasi_chart: dict) -> float:
    return float(rasi_chart.get(planet, {}).get("degree", 0.0))


def _planet_house(planet: str, rasi_chart: dict, lagna: dict) -> int:
    """Return 1-based house number for the planet."""
    lagna_idx = _rasi_to_idx(lagna.get("rasi", "Aries"))
    planet_idx = _planet_sign(planet, rasi_chart)
    return ((planet_idx - lagna_idx) % 12) + 1


def _is_retrograde(planet: str, rasi_chart: dict) -> bool:
    return bool(rasi_chart.get(planet, {}).get("retrograde", False))


# ── 1. Sthana Bala (Positional Strength) ────────────────────────────────────

def _sthana_bala(planet: str, rasi_chart: dict, lagna: dict) -> dict:
    """
    Sthana Bala = Uccha + Moolatrikona + Swakshetra + Drekkana + Saptamsa bala.
    Simplified to the three primary dignities + graded scale.
    """
    sign_idx = _planet_sign(planet, rasi_chart)
    degree   = _planet_degree(planet, rasi_chart)

    exalt_idx = _EXALT_SIGN.get(planet, 0)
    debil_idx = _DEBIL_SIGN.get(planet, 6)
    own_signs  = _OWN_SIGNS.get(planet, [])

    # Uccha (exaltation) bala: max 60 at exact exaltation degree, 0 at debilitation
    # Linear scale across the 180° from exalt to debil
    exalt_full_lon = exalt_idx * 30.0  + 10.0  # approximate exaltation degree
    planet_full_lon = sign_idx * 30.0 + degree

    angular_dist = abs(planet_full_lon - exalt_full_lon) % 360
    if angular_dist > 180:
        angular_dist = 360 - angular_dist
    uccha_bala = 60.0 * (1 - angular_dist / 180.0)

    # Saptavargaja bala (simplified: own sign / moolatrikona / exalt)
    if sign_idx == exalt_idx:
        saptha = 45.0
    elif sign_idx in own_signs:
        saptha = 30.0
    elif sign_idx == debil_idx:
        saptha = 0.0
    else:
        saptha = 7.5  # neutral placement

    total = uccha_bala + saptha
    return {
        "uccha_bala":       round(uccha_bala, 2),
        "saptavargaja_bala": round(saptha, 2),
        "total":            round(total, 2),
    }


# ── 2. Dig Bala (Directional Strength) ────────────────────────────────────────

def _dig_bala(planet: str, rasi_chart: dict, lagna: dict) -> dict:
    """
    Dig Bala: max 60 in strongest house, 0 in opposite house, linear between.
    """
    house = _planet_house(planet, rasi_chart, lagna)
    best  = _DIG_BALA_HOUSE.get(planet, 1)
    diff  = abs(house - best)
    if diff > 6:
        diff = 12 - diff
    score = 60.0 * (1 - diff / 6.0)
    return {"strongest_house": best, "actual_house": house, "total": round(score, 2)}


# ── 3. Kala Bala (Temporal Strength) ─────────────────────────────────────────

def _kala_bala(planet: str, birth_info: dict, rasi_chart: dict) -> dict:
    """
    Simplified Kala Bala:
      - Nathonnatha Bala: Sun/Moon/Venus strong by day; Moon/Mars/Saturn by night
      - Paksha Bala: malefics strong in Krishna, benefics in Shukla
      - Abda/Masa/Vara/Hora bala (fixed contribution approximation)
    """
    # Determine day/night from time of birth
    tob = birth_info.get("time_of_birth", "12:00")
    hour = 12.0
    try:
        parts = tob.replace(":", " ").split()
        hour = float(parts[0]) + float(parts[1]) / 60 if len(parts) >= 2 else float(parts[0])
    except Exception:
        pass
    is_day = 6.0 <= hour < 18.0

    # Nathonnatha bala
    _DAY_STRONG  = {"Sun", "Jupiter", "Venus"}
    _NIGHT_STRONG = {"Moon", "Mars", "Saturn"}
    if planet in _DAY_STRONG:
        nath = 60.0 if is_day else 0.0
    elif planet in _NIGHT_STRONG:
        nath = 60.0 if not is_day else 0.0
    else:
        nath = 30.0  # Mercury is always medium

    # Hora bala (very approximate — 60 if planet rules the birth hora)
    hora_lord_idx = int(hour) % 7
    _HORA_ORDER = ["Sun","Moon","Mars","Mercury","Jupiter","Venus","Saturn"]
    hora_lord = _HORA_ORDER[hora_lord_idx]
    hora_bala = 60.0 if hora_lord == planet else 0.0

    # Paksha (lunar phase) bala (approximate, 30 for all as we lack tithi)
    paksha_bala = 30.0

    total = nath + hora_bala + paksha_bala
    return {
        "nathonnatha_bala": round(nath, 2),
        "hora_bala":        round(hora_bala, 2),
        "paksha_bala":      round(paksha_bala, 2),
        "total":            round(total, 2),
    }


# ── 4. Chesta Bala (Motional Strength) ────────────────────────────────────────

def _chesta_bala(planet: str, rasi_chart: dict) -> dict:
    """
    Chesta Bala based on motion:
      Retrograde = 60, Direct fast = 15, Stationary ≈ 30.
    Sun and Moon don't retrograde; use latitude deviation instead (approx).
    """
    retro = _is_retrograde(planet, rasi_chart)
    if planet in ("Sun", "Moon"):
        # Use longitude speed proxy (not available directly — use medium value)
        score = 30.0
        motion = "mean"
    elif retro:
        score  = 60.0
        motion = "retrograde"
    else:
        score  = 15.0
        motion = "direct"
    return {"motion": motion, "total": round(score, 2)}


# ── 5. Naisargika Bala (Natural Strength) ────────────────────────────────────

def _naisargika_bala(planet: str) -> dict:
    score = _NAISARGIKA.get(planet, 0.0)
    return {"total": score}


# ── 6. Drik Bala (Aspectual Strength) ─────────────────────────────────────────

def _drik_bala(planet: str, rasi_chart: dict, lagna: dict) -> dict:
    """
    Simplified Drik Bala:
    Benefics (Jupiter, Venus, waxing Moon, unafflicted Mercury) aspecting
    the planet add strength; malefics reduce it.

    Full Drik Bala requires exact aspect degrees and aspect values.
    This gives a reasonable structural approximation.
    """
    _BENEFICS = {"Jupiter", "Venus", "Moon"}
    _MALEFICS = {"Sun", "Mars", "Saturn", "Rahu", "Ketu"}

    planet_house  = _planet_house(planet, rasi_chart, lagna)
    score = 0.0

    for other, data in rasi_chart.items():
        if other == planet:
            continue
        other_house = _planet_house(other, rasi_chart, lagna)
        # 7th house (opposition) aspect
        if abs(planet_house - other_house) == 6:
            if other in _BENEFICS:
                score += 15.0
            elif other in _MALEFICS:
                score -= 10.0
        # Jupiter also aspects 5th and 9th
        if other == "Jupiter":
            if abs(planet_house - other_house) in (4, 8):
                score += 10.0
        # Mars aspects 4th and 8th
        if other == "Mars":
            if abs(planet_house - other_house) in (3, 7):
                score -= 7.0
        # Saturn aspects 3rd and 10th
        if other == "Saturn":
            if abs(planet_house - other_house) in (2, 9):
                score -= 7.0

    score = max(-30.0, min(45.0, score))
    return {"total": round(score, 2)}


# ── Minimum required Shadbala strengths ──────────────────────────────────────

_MINIMUM_REQUIRED = {
    "Sun":     390.0,
    "Moon":    360.0,
    "Mars":    300.0,
    "Mercury": 420.0,
    "Jupiter": 390.0,
    "Venus":   330.0,
    "Saturn":  300.0,
}


# ── Main calculator ───────────────────────────────────────────────────────────

def calculate_shadbala(kundli: dict) -> dict:
    """
    Calculate Shadbala for all 7 classical planets.

    Parameters
    ----------
    kundli : dict returned by KundliEngine.generate()

    Returns
    -------
    {
      "planets": {
        "Sun": {
          "sthana_bala": {..., "total": float},
          "dig_bala":    {..., "total": float},
          "kala_bala":   {..., "total": float},
          "chesta_bala": {..., "total": float},
          "naisargika_bala": {"total": float},
          "drik_bala":   {..., "total": float},
          "shadbala_total":  float,   # sum of all 6
          "minimum_required": float,
          "is_strong": bool,
          "strength_ratio": float,    # shadbala / minimum
        },
        ...
      },
      "strongest_planet": str,
      "weakest_planet":   str,
    }
    """
    birth_info = kundli.get("birth_info", {})
    lagna      = kundli.get("lagna", {})
    rasi_chart = kundli.get("rasi_chart", {})

    results = {}

    for planet in PLANETS:
        if planet not in rasi_chart:
            continue

        sthana  = _sthana_bala(planet, rasi_chart, lagna)
        dig     = _dig_bala(planet, rasi_chart, lagna)
        kala    = _kala_bala(planet, birth_info, rasi_chart)
        chesta  = _chesta_bala(planet, rasi_chart)
        naisar  = _naisargika_bala(planet)
        drik    = _drik_bala(planet, rasi_chart, lagna)

        total = (
            sthana["total"] + dig["total"] + kala["total"]
            + chesta["total"] + naisar["total"] + drik["total"]
        )
        min_req = _MINIMUM_REQUIRED.get(planet, 300.0)

        results[planet] = {
            "sthana_bala":      sthana,
            "dig_bala":         dig,
            "kala_bala":        kala,
            "chesta_bala":      chesta,
            "naisargika_bala":  naisar,
            "drik_bala":        drik,
            "shadbala_total":   round(total, 2),
            "minimum_required": min_req,
            "is_strong":        total >= min_req,
            "strength_ratio":   round(total / min_req, 3) if min_req else 0.0,
        }

    # Rankings
    if results:
        strongest = max(results, key=lambda p: results[p]["shadbala_total"])
        weakest   = min(results, key=lambda p: results[p]["shadbala_total"])
    else:
        strongest = weakest = ""

    return {
        "planets":          results,
        "strongest_planet": strongest,
        "weakest_planet":   weakest,
    }


def validate_shadbala(result: dict) -> list[str]:
    """
    Validate Shadbala results against minimum required strengths.
    Returns a list of warning strings for weak planets (empty = all strong).

    Minimum required strengths (Rupas) per classical Parashari texts:
      Sun=390, Moon=360, Mars=300, Mercury=420, Jupiter=390,
      Venus=330, Saturn=300
    """
    warnings: list[str] = []
    planets = result.get("planets", {})

    for planet, data in planets.items():
        total    = data.get("shadbala_total", 0)
        min_req  = data.get("minimum_required", 0)
        ratio    = data.get("strength_ratio", 0)

        if not data.get("is_strong", True):
            warnings.append(
                f"{planet} is WEAK: Shadbala={total:.1f} Rupas, "
                f"required={min_req:.1f} Rupas, ratio={ratio:.2f}. "
                f"Malefic effects may be amplified in readings."
            )

        # Sanity check: no planet should have zero shadbala (indicates calc error)
        if total == 0:
            warnings.append(
                f"{planet}: shadbala_total is 0 — likely a calculation error. "
                f"Check that planet position is present in the kundli chart."
            )

    return warnings


def get_shadbala_summary(result: dict) -> dict:
    """
    Return a human-readable summary dict for API responses.
    Includes strong/weak classification and strength ratios for all planets.
    """
    planets = result.get("planets", {})
    summary = {}
    for planet, data in planets.items():
        summary[planet] = {
            "total_rupas":   round(data.get("shadbala_total", 0), 2),
            "minimum_rupas": data.get("minimum_required", 0),
            "is_strong":     data.get("is_strong", False),
            "strength_pct":  round(data.get("strength_ratio", 0) * 100, 1),
        }
    return {
        "planet_strengths": summary,
        "strongest": result.get("strongest_planet", ""),
        "weakest":   result.get("weakest_planet", ""),
        "weak_planets": [p for p, d in planets.items() if not d.get("is_strong", True)],
    }
