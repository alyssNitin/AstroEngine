"""
kundli_engine/dasha_systems.py
==============================
Additional Dasha system calculators beyond Vimshottari.

Implements:
  - Yogini Dasha   (8-lord cycle, 36-year total)
  - Chara Dasha    (sign-based, Jaimini)
  - Kalachakra Dasha (nakshatra-based, 4 cycles)
  - Narayana Dasha (sign-based, rasi-level; Jaimini variant)
  - Moola Dasha    (nakshatra-based, 9 planets)

All calculators accept:
    birth_info (dict)  — from engine.generate()["birth_info"]
    lagna      (dict)  — from engine.generate()["lagna"]
    rasi_chart (dict)  — from engine.generate()["rasi_chart"]

and return a dasha dict shaped like:
    {
        "name": "<system name>",
        "total_years": <int>,
        "balance_at_birth": "<Xyr Ym Zd>",
        "periods": [
            {"lord": "...", "start_date": "...", "duration_years": ..., "sub_periods": [...]},
            ...
        ]
    }

Calculations are approximate/indicative when PyJHora does not expose the
given system directly; exact results require the full library integration.
"""
from __future__ import annotations

import math
from datetime import date, timedelta
from typing import Any

# ── Constants ─────────────────────────────────────────────────────────────────

_NAKSHATRAS = [
    "Ashwini", "Bharani", "Krittika", "Rohini", "Mrigashira", "Ardra",
    "Punarvasu", "Pushya", "Ashlesha", "Magha", "Purva Phalguni", "Uttara Phalguni",
    "Hasta", "Chitra", "Swati", "Vishakha", "Anuradha", "Jyeshtha",
    "Mula", "Purva Ashadha", "Uttara Ashadha", "Shravana", "Dhanishtha",
    "Shatabhisha", "Purva Bhadrapada", "Uttara Bhadrapada", "Revati",
]

_RASIS = [
    "Aries", "Taurus", "Gemini", "Cancer", "Leo", "Virgo",
    "Libra", "Scorpio", "Sagittarius", "Capricorn", "Aquarius", "Pisces",
]

# Yogini lords in order (8-fold cycle, 36 total years)
_YOGINI_ORDER = ["Moon", "Sun", "Jupiter", "Mars", "Mercury", "Saturn", "Venus", "Rahu"]
_YOGINI_YEARS = [1,       2,     3,         4,      5,          6,        7,        8]

# Moon nakshatra → Yogini start index  (nakshatra_number mod 8, 0-indexed)
# Yogini cycle starts from Mangala (Moon) at Ashwini
_YOGINI_NAMES = ["Mangala", "Pingala", "Dhanya", "Bhramari", "Bhadrika", "Ulka", "Siddha", "Sankata"]

# Moola dasha: 9 planets, years [7,6,10,18,16,19,17,3,4] total 100
_MOOLA_ORDER = ["Sun", "Moon", "Mars", "Rahu", "Jupiter", "Saturn", "Mercury", "Ketu", "Venus"]
_MOOLA_YEARS = [7,      6,      10,    18,      16,         19,        17,        3,      4]

# ── Helpers ───────────────────────────────────────────────────────────────────

def _parse_date(dob: str) -> date:
    """Parse DD/MM/YYYY or YYYY-MM-DD."""
    dob = dob.strip()
    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y"):
        try:
            from datetime import datetime
            return datetime.strptime(dob, fmt).date()
        except ValueError:
            pass
    raise ValueError(f"Cannot parse date: {dob!r}")


def _add_years(d: date, years: float) -> date:
    """Add fractional years to a date (approximate)."""
    days = int(years * 365.25)
    return d + timedelta(days=days)


def _format_duration(years: float) -> str:
    total_days = int(years * 365.25)
    y = total_days // 365
    rem = total_days % 365
    m = rem // 30
    d = rem % 30
    return f"{y}yr {m}m {d}d"


def _moon_nakshatra_index(rasi_chart: dict) -> int:
    """Return 0-based nakshatra index (0=Ashwini) from Moon's nakshatra."""
    moon = rasi_chart.get("Moon", {})
    nak = moon.get("nakshatra", "Ashwini")
    try:
        return _NAKSHATRAS.index(nak)
    except ValueError:
        return 0


def _moon_longitude(rasi_chart: dict) -> float:
    moon = rasi_chart.get("Moon", {})
    return float(moon.get("full_longitude", 0.0))


def _lagna_rasi_index(lagna: dict) -> int:
    rasi = lagna.get("rasi", "Aries")
    try:
        return _RASIS.index(rasi)
    except ValueError:
        return 0


# ── Yogini Dasha ──────────────────────────────────────────────────────────────

def yogini_dasha(birth_info: dict, lagna: dict, rasi_chart: dict) -> dict:
    """
    Calculate Yogini Dasha sequence from birth date.

    The Yogini cycle is 36 years total (1+2+3+4+5+6+7+8).
    Moon's nakshatra at birth determines the starting Yogini and balance.
    """
    dob = _parse_date(birth_info.get("date_of_birth", "01/01/1990"))

    # Moon nakshatra index → Yogini index (0-based)
    nak_idx = _moon_nakshatra_index(rasi_chart)
    yogini_idx = nak_idx % 8  # 0-7

    # Balance at birth: how far through the current Yogini period
    # Each nakshatra occupies 13°20'. Moon position within nakshatra gives balance.
    moon_lon = _moon_longitude(rasi_chart)
    nak_lon   = (nak_idx * (360 / 27))          # start longitude of nakshatra
    nak_span  = 360 / 27                         # 13.333°
    elapsed_fraction = (moon_lon - nak_lon) / nak_span
    elapsed_fraction = max(0.0, min(1.0, elapsed_fraction))

    current_period_years = _YOGINI_YEARS[yogini_idx]
    balance_years = current_period_years * (1.0 - elapsed_fraction)

    periods = []
    cursor = dob
    # First period (partial balance)
    end = _add_years(cursor, balance_years)
    periods.append({
        "lord":           _YOGINI_ORDER[yogini_idx],
        "yogini_name":    _YOGINI_NAMES[yogini_idx],
        "duration_years": round(balance_years, 2),
        "start_date":     cursor.isoformat(),
        "end_date":       end.isoformat(),
        "sub_periods":    [],
    })
    cursor = end

    # Subsequent full periods
    for i in range(1, 20):   # cover ~36 years × a few cycles
        idx = (yogini_idx + i) % 8
        dur = _YOGINI_YEARS[idx]
        end = _add_years(cursor, dur)
        periods.append({
            "lord":           _YOGINI_ORDER[idx],
            "yogini_name":    _YOGINI_NAMES[idx],
            "duration_years": dur,
            "start_date":     cursor.isoformat(),
            "end_date":       end.isoformat(),
            "sub_periods":    [],
        })
        cursor = end

    return {
        "name":             "Yogini",
        "total_years":      36,
        "balance_at_birth": _format_duration(balance_years),
        "periods":          periods,
    }


# ── Chara Dasha (Jaimini sign-based) ─────────────────────────────────────────

def chara_dasha(birth_info: dict, lagna: dict, rasi_chart: dict) -> dict:
    """
    Calculate Chara Dasha (Jaimini) — sign-based, starts from Lagna rasi.

    Each rasi gets a period of 1–12 years determined by the count of planets
    in the rasi and special rules. This is a simplified version.
    """
    dob = _parse_date(birth_info.get("date_of_birth", "01/01/1990"))
    lagna_idx = _lagna_rasi_index(lagna)

    # Build planet-in-rasi count
    rasi_planet_count = [0] * 12
    for planet_data in rasi_chart.values():
        ridx = planet_data.get("rasi_index", 0)
        if 0 <= ridx < 12:
            rasi_planet_count[ridx] += 1

    # Chara dasha year for each rasi: planets in rasi + 1, max 12
    def _chara_years(rasi_idx: int) -> int:
        planets = rasi_planet_count[rasi_idx]
        # Odd rasi (Aries=0,Gemini=2,...): count from beginning of sign
        # Even rasi: count from end — simplified here as (12 - planets) or (planets+1)
        if rasi_idx % 2 == 0:   # Odd rasi (0-indexed even)
            return max(1, min(12, planets + 1))
        else:                    # Even rasi
            return max(1, min(12, 12 - planets))

    periods = []
    cursor  = dob
    # Start from lagna rasi, go through all 12 rasis
    for i in range(12):
        ridx = (lagna_idx + i) % 12
        dur  = _chara_years(ridx)
        end  = _add_years(cursor, dur)
        periods.append({
            "lord":           _RASIS[ridx],
            "duration_years": dur,
            "start_date":     cursor.isoformat(),
            "end_date":       end.isoformat(),
            "sub_periods":    [],
        })
        cursor = end

    return {
        "name":             "Chara (Jaimini)",
        "total_years":      sum(_chara_years(i) for i in range(12)),
        "balance_at_birth": _format_duration(_chara_years(lagna_idx)),
        "periods":          periods,
    }


# ── Kalachakra Dasha ──────────────────────────────────────────────────────────

# 4 groups of nakshatras (savya / apasavya), 9 nakshatras each
# Each group cycles through rasis in a specific order.
# Simplified: year durations by group
_KC_GROUPS = [
    # Group 1: nakshatras 1-9 (Ashwini to Ashlesha) — savya
    {"rasi_order": [0,1,2,3,4,5,6,7,8,9,10,11], "years": [7,16,9,10,19,17,3,4,18]},
    # Group 2: nakshatras 10-18 (Magha to Jyeshtha) — apasavya
    {"rasi_order": [11,10,9,8,7,6,5,4,3,2,1,0], "years": [7,16,9,10,19,17,3,4,18]},
    # Group 3: nakshatras 19-27 (Mula to Revati) — savya
    {"rasi_order": [0,1,2,3,4,5,6,7,8,9,10,11], "years": [7,16,9,10,19,17,3,4,18]},
    # Group 4 doesn't exist but cycle repeats
]
_KC_LORDS = ["Aries","Taurus","Gemini","Cancer","Leo","Virgo","Libra","Scorpio","Sagittarius"]

def kalachakra_dasha(birth_info: dict, lagna: dict, rasi_chart: dict) -> dict:
    """
    Calculate Kalachakra Dasha — nakshatra-pada based, 4 cycles.

    Simplified calculation; full precision requires the complete Kalachakra tables.
    """
    dob = _parse_date(birth_info.get("date_of_birth", "01/01/1990"))
    nak_idx = _moon_nakshatra_index(rasi_chart)

    # Determine group (0-2) and position within group
    group_idx = (nak_idx // 9) % 3
    pos_in_group = nak_idx % 9

    # Period durations from the KC table
    durations = [7, 16, 9, 10, 19, 17, 3, 4, 18]  # 100-year cycle

    # Balance in first period
    moon_lon = _moon_longitude(rasi_chart)
    nak_lon  = nak_idx * (360 / 27)
    elapsed  = max(0, min(1, (moon_lon - nak_lon) / (360 / 27)))
    first_dur = durations[pos_in_group]
    balance   = first_dur * (1.0 - elapsed)

    periods = []
    cursor  = dob

    # First period (balance)
    end = _add_years(cursor, balance)
    periods.append({
        "lord":           _RASIS[(group_idx * 4 + pos_in_group) % 12],
        "duration_years": round(balance, 2),
        "start_date":     cursor.isoformat(),
        "end_date":       end.isoformat(),
        "sub_periods":    [],
    })
    cursor = end

    for i in range(1, 15):
        pos = (pos_in_group + i) % 9
        grp = ((group_idx * 9 + pos_in_group + i) // 9) % 3
        dur = durations[pos]
        end = _add_years(cursor, dur)
        periods.append({
            "lord":           _RASIS[(grp * 4 + pos) % 12],
            "duration_years": dur,
            "start_date":     cursor.isoformat(),
            "end_date":       end.isoformat(),
            "sub_periods":    [],
        })
        cursor = end

    return {
        "name":             "Kalachakra",
        "total_years":      100,
        "balance_at_birth": _format_duration(balance),
        "periods":          periods,
    }


# ── Narayana Dasha ────────────────────────────────────────────────────────────

def narayana_dasha(birth_info: dict, lagna: dict, rasi_chart: dict) -> dict:
    """
    Calculate Narayana Dasha (Jaimini rasi-based).

    Starts from the stronger of lagna/7th house rasi.
    Each rasi gets 1–12 years (count of house lord from lagna).
    """
    dob = _parse_date(birth_info.get("date_of_birth", "01/01/1990"))
    lagna_idx = _lagna_rasi_index(lagna)

    # Narayana dasha duration = count of rasi from lagna (1-indexed)
    def _narayana_years(rasi_idx: int) -> int:
        diff = (rasi_idx - lagna_idx) % 12
        return max(1, diff if diff != 0 else 12)

    periods = []
    cursor  = dob
    for i in range(12):
        ridx = (lagna_idx + i) % 12
        dur  = _narayana_years(ridx)
        end  = _add_years(cursor, dur)
        periods.append({
            "lord":           _RASIS[ridx],
            "duration_years": dur,
            "start_date":     cursor.isoformat(),
            "end_date":       end.isoformat(),
            "sub_periods":    [],
        })
        cursor = end

    return {
        "name":             "Narayana (Jaimini)",
        "total_years":      sum(_narayana_years(i) for i in range(12)),
        "balance_at_birth": _format_duration(_narayana_years(lagna_idx)),
        "periods":          periods,
    }


# ── Moola Dasha ───────────────────────────────────────────────────────────────

def moola_dasha(birth_info: dict, lagna: dict, rasi_chart: dict) -> dict:
    """
    Calculate Moola Dasha — nakshatra-based, 9 planets, 100-year cycle.

    Starts from the planet that owns the Moon's nakshatra.
    """
    dob = _parse_date(birth_info.get("date_of_birth", "01/01/1990"))

    # Nakshatra → ruling planet (same as Vimshottari but used differently)
    _NAK_LORDS = [
        "Ketu","Venus","Sun","Moon","Mars","Rahu","Jupiter","Saturn","Mercury",  # 1-9
        "Ketu","Venus","Sun","Moon","Mars","Rahu","Jupiter","Saturn","Mercury",  # 10-18
        "Ketu","Venus","Sun","Moon","Mars","Rahu","Jupiter","Saturn","Mercury",  # 19-27
    ]

    nak_idx = _moon_nakshatra_index(rasi_chart)
    nak_lord = _NAK_LORDS[nak_idx]

    # Start position in Moola order
    try:
        start_pos = _MOOLA_ORDER.index(nak_lord)
    except ValueError:
        start_pos = 0

    # Balance
    moon_lon = _moon_longitude(rasi_chart)
    nak_lon  = nak_idx * (360 / 27)
    elapsed  = max(0, min(1, (moon_lon - nak_lon) / (360 / 27)))
    first_dur = _MOOLA_YEARS[start_pos]
    balance   = first_dur * (1.0 - elapsed)

    periods = []
    cursor  = dob

    # First (balance)
    end = _add_years(cursor, balance)
    periods.append({
        "lord":           _MOOLA_ORDER[start_pos],
        "duration_years": round(balance, 2),
        "start_date":     cursor.isoformat(),
        "end_date":       end.isoformat(),
        "sub_periods":    [],
    })
    cursor = end

    for i in range(1, 12):
        pos = (start_pos + i) % 9
        dur = _MOOLA_YEARS[pos]
        end = _add_years(cursor, dur)
        periods.append({
            "lord":           _MOOLA_ORDER[pos],
            "duration_years": dur,
            "start_date":     cursor.isoformat(),
            "end_date":       end.isoformat(),
            "sub_periods":    [],
        })
        cursor = end

    return {
        "name":             "Moola",
        "total_years":      100,
        "balance_at_birth": _format_duration(balance),
        "periods":          periods,
    }


# ── Public dispatcher ─────────────────────────────────────────────────────────

_DASHA_CALCULATORS = {
    "yogini":      yogini_dasha,
    "chara":       chara_dasha,
    "kalachakra":  kalachakra_dasha,
    "narayana":    narayana_dasha,
    "moola":       moola_dasha,
}


def calculate_dasha(
    system: str,
    birth_info: dict,
    lagna: dict,
    rasi_chart: dict,
) -> dict:
    """
    Calculate a named dasha system.

    Parameters
    ----------
    system : one of yogini | chara | kalachakra | narayana | moola
    birth_info, lagna, rasi_chart : sections from KundliEngine.generate()

    Returns a dict with keys: name, total_years, balance_at_birth, periods
    """
    system = system.lower().strip()
    calc = _DASHA_CALCULATORS.get(system)
    if calc is None:
        available = ", ".join(sorted(_DASHA_CALCULATORS))
        raise ValueError(f"Unknown dasha system '{system}'. Available: {available}")
    return calc(birth_info, lagna, rasi_chart)


def available_systems() -> list[str]:
    """Return list of available additional dasha systems."""
    return sorted(_DASHA_CALCULATORS.keys())
