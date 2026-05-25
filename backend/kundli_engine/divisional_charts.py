"""
backend/kundli_engine/divisional_charts.py
===========================================
B19: Classical Parashari divisional chart (Varga) calculations.

Implements D1–D16 (excluding D11 which has no classical definition) using the
standard formulas from Brihat Parasara Hora Sastra (BPHS) and Phaladeepika.

Divisional charts supported
----------------------------
  D1  Rasi          — birth chart (identity, all-round)
  D2  Hora          — wealth, finances
  D3  Drekkana      — siblings, courage
  D4  Chaturthamsa  — property, fixed assets
  D5  Panchamsa     — good / bad deeds, authority (rare)
  D6  Shashthamsa   — health, enemies, maternal  (rare)
  D7  Saptamsha     — children, grandchildren
  D8  Ashtamsha     — sudden events, obstacles  (rare)
  D9  Navamsa       — spouse, dharma, marriage (MOST IMPORTANT)
  D10 Dasamsa       — career, profession, livelihood
  D12 Dwadasamsa    — parents, ancestors
  D16 Shodasamsa    — vehicles, comforts, pleasures

Formula (general)
------------------
  For a planet at full longitude L (0–360):
    rasi_index  = floor(L / 30)          # 0 = Aries … 11 = Pisces
    deg_in_sign = L % 30                 # 0.0 – 29.99°
    part        = floor(deg_in_sign * N / 30)  # 0 – N-1
  Then map (rasi_index, part) → result_sign using the BPHS table for that Varga.

Public API
----------
  calculate_divisional_chart(kundli, division)  → dict
    division: int in {1,2,3,4,5,6,7,8,9,10,12,16}

  calculate_all_divisional_charts(kundli)       → dict
    Returns a dict keyed by "D{N}_<Name>".

  get_varga_strength(planet_name, kundli)       → dict
    Returns how many Vargas a planet occupies in its own or exalted sign
    (Vaiseshikamsa scheme: Parijata at 2, Uttama at 3, …, Vargottama etc.)
"""
from __future__ import annotations

import math
from typing import Dict, List, Optional

# ── Constants ─────────────────────────────────────────────────────────────────

RASI_NAMES: List[str] = [
    "Aries", "Taurus", "Gemini", "Cancer",
    "Leo", "Virgo", "Libra", "Scorpio",
    "Sagittarius", "Capricorn", "Aquarius", "Pisces",
]
RASI_SHORT: List[str] = [
    "Ar", "Ta", "Ge", "Ca", "Le", "Vi",
    "Li", "Sc", "Sg", "Cp", "Aq", "Pi",
]

# Classical planet sign ownerships (for Vargottama / Vaiseshikamsa)
_OWN_SIGNS: Dict[str, List[int]] = {
    "Sun":     [4],          # Leo
    "Moon":    [3],          # Cancer
    "Mars":    [0, 7],       # Aries, Scorpio
    "Mercury": [2, 5],       # Gemini, Virgo
    "Jupiter": [8, 11],      # Sagittarius, Pisces
    "Venus":   [1, 6],       # Taurus, Libra
    "Saturn":  [9, 10],      # Capricorn, Aquarius
    "Rahu":    [10],         # Aquarius (Parashari)
    "Ketu":    [7],          # Scorpio
}

_EXALTATION_SIGNS: Dict[str, int] = {
    "Sun":     0,   # Aries
    "Moon":    1,   # Taurus
    "Mars":    9,   # Capricorn
    "Mercury": 5,   # Virgo
    "Jupiter": 3,   # Cancer
    "Venus":   11,  # Pisces
    "Saturn":  6,   # Libra
    "Rahu":    2,   # Gemini
    "Ketu":    8,   # Sagittarius
}

# Sign modalities: 0=movable/cardinal, 1=fixed, 2=dual/mutable
_MODALITY: List[int] = [0, 1, 2, 0, 1, 2, 0, 1, 2, 0, 1, 2]

# Sign elements: 0=Fire, 1=Earth, 2=Air, 3=Water
_ELEMENT: List[int] = [0, 1, 2, 3, 0, 1, 2, 3, 0, 1, 2, 3]


# ── Internal helpers ──────────────────────────────────────────────────────────

def _longitude(full_long: float) -> tuple[int, float]:
    """Return (rasi_index 0-11, degrees_in_sign 0-30)."""
    full_long = full_long % 360
    return int(full_long / 30), full_long % 30


def _sign_info(rasi_idx: int) -> dict:
    idx = rasi_idx % 12
    return {
        "rasi":      RASI_NAMES[idx],
        "rasi_short": RASI_SHORT[idx],
        "rasi_index": idx,
    }


def _extract_planets(kundli: dict) -> dict:
    """Return planet → full_longitude mapping from a kundli dict."""
    chart = kundli.get("rasi_chart") or {}
    result = {}
    for planet, data in chart.items():
        if isinstance(data, dict) and "full_longitude" in data:
            result[planet] = float(data["full_longitude"])
    return result


def _extract_lagna_longitude(kundli: dict) -> Optional[float]:
    lagna = kundli.get("lagna") or {}
    return lagna.get("full_longitude")


# ── Divisional chart formulas (BPHS) ─────────────────────────────────────────

def _d1(rasi_idx: int, _deg: float) -> int:
    """D1 — Rasi (identity): same as natal sign."""
    return rasi_idx


def _d2(rasi_idx: int, deg: float) -> int:
    """
    D2 — Hora (wealth).
    Odd signs (0-indexed even = Aries, Gemini…): first half → Leo, second → Cancer.
    Even signs (0-indexed odd = Taurus, Cancer…): first half → Cancer, second → Leo.
    """
    # "odd" per BPHS = Aries, Gemini, Leo, Libra, Sag, Aquarius = even indices 0,2,4,6,8,10
    if rasi_idx % 2 == 0:   # odd sign by BPHS convention
        return 4 if deg < 15 else 3   # Leo (4) or Cancer (3)
    else:                              # even sign
        return 3 if deg < 15 else 4   # Cancer (3) or Leo (4)


def _d3(rasi_idx: int, deg: float) -> int:
    """
    D3 — Drekkana (siblings, courage).
    3 parts of 10° each. Each part maps to a trine.
    Part 0 → same sign, Part 1 → 5th sign, Part 2 → 9th sign.
    """
    part = int(deg / 10)
    return (rasi_idx + part * 4) % 12


def _d4(rasi_idx: int, deg: float) -> int:
    """
    D4 — Chaturthamsa (property).
    4 parts of 7.5° each: +0, +3, +6, +9 signs from natal sign.
    """
    part = int(deg / 7.5)
    return (rasi_idx + part * 3) % 12


def _d5(rasi_idx: int, deg: float) -> int:
    """
    D5 — Panchamsa (past deeds / authority).
    5 parts of 6° each.
    Odd signs (BPHS): counted from Aries.
    Even signs: counted from Sagittarius.
    """
    part = int(deg / 6)
    if rasi_idx % 2 == 0:
        return part % 12                    # from Aries
    else:
        return (8 + part) % 12             # from Sagittarius


def _d6(rasi_idx: int, deg: float) -> int:
    """
    D6 — Shashthamsa (health, enemies).
    6 parts of 5° each, counted from same sign.
    """
    part = int(deg / 5)
    return (rasi_idx + part) % 12


def _d7(rasi_idx: int, deg: float) -> int:
    """
    D7 — Saptamsha (children).
    7 parts of 4°17'8.57"
    Odd signs: from same sign. Even signs: from 7th sign.
    """
    part = int(deg * 7 / 30)
    if rasi_idx % 2 == 0:
        return (rasi_idx + part) % 12
    else:
        return (rasi_idx + 6 + part) % 12


def _d8(rasi_idx: int, deg: float) -> int:
    """
    D8 — Ashtamsha (obstacles, sudden events).
    8 parts of 3.75° each.
    Counted from same sign (Aries for all per some texts; BPHS: from sign itself).
    """
    part = int(deg * 8 / 30)
    return (rasi_idx + part) % 12


def _d9(rasi_idx: int, deg: float) -> int:
    """
    D9 — Navamsa (spouse, dharma). Most important Varga.
    9 parts of 3°20' each.
    Starting signs by element:
      Fire  (0,4,8):  start from Aries  (0)
      Earth (1,5,9):  start from Capricorn (9)
      Air   (2,6,10): start from Libra  (6)
      Water (3,7,11): start from Cancer (3)
    """
    _starts = [0, 9, 6, 3]   # indexed by element (Fire, Earth, Air, Water)
    start = _starts[_ELEMENT[rasi_idx]]
    part  = int(deg * 9 / 30)
    return (start + part) % 12


def _d10(rasi_idx: int, deg: float) -> int:
    """
    D10 — Dasamsa (career, profession).
    10 parts of 3° each.
    Odd signs: counted from same sign. Even signs: counted from 9th sign (add 8).
    """
    part = int(deg * 10 / 30)
    if rasi_idx % 2 == 0:
        return (rasi_idx + part) % 12
    else:
        return (rasi_idx + 8 + part) % 12


def _d12(rasi_idx: int, deg: float) -> int:
    """
    D12 — Dwadasamsa (parents, ancestors).
    12 parts of 2.5° each, counted from same sign.
    """
    part = int(deg * 12 / 30)
    return (rasi_idx + part) % 12


def _d16(rasi_idx: int, deg: float) -> int:
    """
    D16 — Shodasamsa (vehicles, comforts).
    16 parts of 1.875° each.
    Movable signs: from Aries (0). Fixed: from Leo (4). Dual: from Sagittarius (8).
    """
    _starts = [0, 4, 8]   # by modality: movable, fixed, dual
    start = _starts[_MODALITY[rasi_idx]]
    part  = int(deg * 16 / 30)
    return (start + part) % 12


_DIVISIONAL_FN = {
    1:  _d1,
    2:  _d2,
    3:  _d3,
    4:  _d4,
    5:  _d5,
    6:  _d6,
    7:  _d7,
    8:  _d8,
    9:  _d9,
    10: _d10,
    12: _d12,
    16: _d16,
}

_VARGA_NAMES = {
    1:  "Rasi",
    2:  "Hora",
    3:  "Drekkana",
    4:  "Chaturthamsa",
    5:  "Panchamsa",
    6:  "Shashthamsa",
    7:  "Saptamsha",
    8:  "Ashtamsha",
    9:  "Navamsa",
    10: "Dasamsa",
    12: "Dwadasamsa",
    16: "Shodasamsa",
}

_VARGA_SIGNIFICANCE = {
    1:  "Physique, appearance, general well-being",
    2:  "Wealth, finances, property",
    3:  "Siblings, courage, short journeys",
    4:  "Fixed assets, property, happiness, mother",
    5:  "Past-life meritorious deeds, authority",
    6:  "Health, diseases, enemies, obstacles",
    7:  "Children, procreation",
    8:  "Longevity, sudden events, obstacles",
    9:  "Spouse, dharma, marriage, spiritual inclination",
    10: "Profession, career, livelihood, social status",
    12: "Parents, ancestors, father",
    16: "Vehicles, comforts, pleasures",
}


# ── Public API ────────────────────────────────────────────────────────────────

def calculate_divisional_chart(kundli: dict, division: int) -> dict:
    """
    Calculate a single divisional chart (Varga).

    Parameters
    ----------
    kundli   : dict — full kundli output from KundliEngine.generate()
    division : int  — divisional number (1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 12, 16)

    Returns
    -------
    dict with:
      name       : str — e.g. "Navamsa"
      division   : int — e.g. 9
      significance: str — classical domain
      ascendant  : dict — rasi/degree for the ascendant (if available)
      planets    : dict[str, dict] — one entry per planet
    """
    if division not in _DIVISIONAL_FN:
        raise ValueError(
            f"Unsupported division D{division}. "
            f"Supported: {sorted(_DIVISIONAL_FN.keys())}"
        )

    fn = _DIVISIONAL_FN[division]
    planets_out: dict = {}

    # Process each planet
    for planet, full_long in _extract_planets(kundli).items():
        rasi_idx, deg = _longitude(full_long)
        result_sign   = fn(rasi_idx, deg)
        info          = _sign_info(result_sign)
        # Vargottama: same sign in D1 and D9 (or same sign in this Varga as D1)
        is_vargottama = (result_sign == rasi_idx) if division != 1 else False
        planets_out[planet] = {
            **info,
            "vargottama": is_vargottama,
        }

    # Process lagna (ascendant)
    ascendant_out: dict = {}
    lagna_long = _extract_lagna_longitude(kundli)
    if lagna_long is not None:
        rasi_idx, deg = _longitude(lagna_long)
        result_sign   = fn(rasi_idx, deg)
        ascendant_out = _sign_info(result_sign)

    return {
        "name":         _VARGA_NAMES.get(division, f"D{division}"),
        "division":     division,
        "significance": _VARGA_SIGNIFICANCE.get(division, ""),
        "ascendant":    ascendant_out,
        "planets":      planets_out,
    }


def calculate_all_divisional_charts(kundli: dict) -> dict:
    """
    Calculate all supported divisional charts (D1–D16).

    Returns
    -------
    dict keyed by "D{N}_{Name}" e.g. "D9_Navamsa", "D10_Dasamsa", etc.
    """
    result = {}
    for division, name in _VARGA_NAMES.items():
        key = f"D{division}_{name}"
        try:
            result[key] = calculate_divisional_chart(kundli, division)
        except Exception as exc:
            result[key] = {"error": str(exc), "division": division, "name": name}
    return result


def get_varga_strength(planet_name: str, kundli: dict) -> dict:
    """
    Compute the Vaiseshikamsa (Varga strength) of a planet.

    Counts how many Vargas the planet occupies in its own or exaltation sign.

    Classical thresholds (Phaladeepika):
      2  vargas → Parijata
      3  vargas → Uttama
      4  vargas → Gopura
      5  vargas → Simhasana
      6  vargas → Paravata
      7  vargas → Devaloka
      8  vargas → Brahmaloka
      10 vargas → Sridhama (Saptavargaja Bala)

    Returns
    -------
    dict with:
      planet           : str
      own_sign_count   : int — how many Vargas planet is in own sign
      exalted_count    : int — how many Vargas planet is in exaltation sign
      total_strong     : int — own + exalted
      vaiseshikamsa    : str — classical strength category
      vargottama       : bool — same sign in D1 and D9
      detail           : dict[str, str] — per-Varga sign placement
    """
    own_signs  = set(_OWN_SIGNS.get(planet_name, []))
    exalt_sign = _EXALTATION_SIGNS.get(planet_name)

    own_count   = 0
    exalt_count = 0
    vargottama  = False
    detail: dict = {}

    # D1 sign for vargottama check
    d1_sign: Optional[int] = None
    planets_map = _extract_planets(kundli)
    if planet_name in planets_map:
        d1_sign, _ = _longitude(planets_map[planet_name])

    for division in sorted(_DIVISIONAL_FN.keys()):
        try:
            varga = calculate_divisional_chart(kundli, division)
        except Exception:
            continue
        planet_data = varga.get("planets", {}).get(planet_name)
        if planet_data is None:
            continue
        sign_idx = planet_data.get("rasi_index")
        if sign_idx is None:
            continue
        detail[f"D{division}"] = planet_data.get("rasi", "?")
        if sign_idx in own_signs:
            own_count += 1
        if exalt_sign is not None and sign_idx == exalt_sign:
            exalt_count += 1
        # Vargottama: D1 == D9
        if division == 9 and d1_sign is not None and sign_idx == d1_sign:
            vargottama = True

    total = own_count + exalt_count

    # Vaiseshikamsa category
    if total >= 10:
        category = "Sridhama"
    elif total >= 8:
        category = "Brahmaloka"
    elif total >= 7:
        category = "Devaloka"
    elif total >= 6:
        category = "Paravata"
    elif total >= 5:
        category = "Simhasana"
    elif total >= 4:
        category = "Gopura"
    elif total >= 3:
        category = "Uttama"
    elif total >= 2:
        category = "Parijata"
    elif vargottama:
        category = "Vargottama"
    else:
        category = "Ordinary"

    return {
        "planet":         planet_name,
        "own_sign_count": own_count,
        "exalted_count":  exalt_count,
        "total_strong":   total,
        "vaiseshikamsa":  category,
        "vargottama":     vargottama,
        "detail":         detail,
    }
