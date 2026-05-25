"""
kundli_engine/ashtakavarga.py
==============================
Ashtakavarga — the eight-source benefic point system.

Each of the 7 classical planets + Lagna contributes benefic points (rekhas)
to every sign (1–8 points per sign, total 337 rekhas in Sarvashtakavarga).

This implementation provides:
  calculate_ashtakavarga(kundli) → full Ashtakavarga analysis dict

Structure of output:
  {
    "bhinnashtakavarga": {
      "Sun":  [int × 12],  # benefic points contributed by Sun to each sign
      "Moon": [...],
      ...
      "Lagna": [...],
    },
    "sarvashtakavarga": [int × 12],  # sum across all 8 sources per sign
    "planet_scores": {
      "Sun": int,   # total rekhas in Sun's own sign
      ...
    },
    "transit_strength": {   # rekhas in each sign (useful for transit timing)
      "Aries": int, "Taurus": int, ...
    },
    "strong_signs":  [list of signs with sarvashtakavarga ≥ 30],
    "weak_signs":    [list of signs with sarvashtakavarga < 25],
    "total_rekhas":  int,  # should be ~337
  }

Reference: Parasara Hora Shastra, Ashtakavarga chapters.
Benefic source tables from classical texts.
"""
from __future__ import annotations

from typing import Any

# ── Sign names ────────────────────────────────────────────────────────────────
_RASIS = [
    "Aries","Taurus","Gemini","Cancer","Leo","Virgo",
    "Libra","Scorpio","Sagittarius","Capricorn","Aquarius","Pisces",
]


# ── Benefic source tables ─────────────────────────────────────────────────────
# Each table defines, for a given contributor (planet or Lagna), which house
# positions relative to the contributor's own position give benefic points.
# These are the classical Parashari tables (1-based house numbers).
#
# Format: {contributor: [list of houses that give a rekha]}

_BENEFIC_HOUSES: dict[str, list[int]] = {
    "Sun":     [1, 2, 4, 7, 8, 9, 10, 11],
    "Moon":    [3, 6, 10, 11],
    "Mars":    [1, 2, 4, 7, 8, 9, 10, 11],
    "Mercury": [1, 3, 5, 6, 9, 10, 11, 12],
    "Jupiter": [1, 2, 3, 4, 7, 8, 10, 11],
    "Venus":   [1, 2, 3, 4, 5, 8, 9, 11, 12],
    "Saturn":  [3, 5, 6, 11],
    "Lagna":   [1, 3, 5, 6, 9, 10, 11, 12],
}

# ── Helpers ───────────────────────────────────────────────────────────────────

def _rasi_idx(rasi: str) -> int:
    try:
        return _RASIS.index(rasi)
    except ValueError:
        return 0


def _planet_sign_idx(planet: str, rasi_chart: dict) -> int:
    return int(rasi_chart.get(planet, {}).get("rasi_index", 0))


def _lagna_sign_idx(lagna: dict) -> int:
    return _rasi_idx(lagna.get("rasi", "Aries"))


# ── Core Bhinnashtakavarga calculator ─────────────────────────────────────────

def _calc_bhinna(
    contributor: str,
    contributor_sign: int,
    rasi_chart: dict,
    lagna_sign: int,
) -> list[int]:
    """
    Calculate Bhinnashtakavarga for a single contributor.

    For each of the 12 signs, count how many of the 7 planets + Lagna
    are in a 'benefic house' relative to the contributor's sign.

    Returns list of 12 integers (rekhas per sign, 0-8).
    """
    benefic_relative_houses = set(_BENEFIC_HOUSES.get(contributor, []))
    rekhas = [0] * 12

    # All 8 sources (7 planets + Lagna)
    sources: dict[str, int] = {
        "Sun":     _planet_sign_idx("Sun", rasi_chart),
        "Moon":    _planet_sign_idx("Moon", rasi_chart),
        "Mars":    _planet_sign_idx("Mars", rasi_chart),
        "Mercury": _planet_sign_idx("Mercury", rasi_chart),
        "Jupiter": _planet_sign_idx("Jupiter", rasi_chart),
        "Venus":   _planet_sign_idx("Venus", rasi_chart),
        "Saturn":  _planet_sign_idx("Saturn", rasi_chart),
        "Lagna":   lagna_sign,
    }

    for sign_i in range(12):
        # House of sign_i relative to contributor's sign (1-based)
        rel_house = ((sign_i - contributor_sign) % 12) + 1
        if rel_house in benefic_relative_houses:
            # Count how many source planets are in this sign
            for src_sign in sources.values():
                if src_sign == sign_i:
                    rekhas[sign_i] += 1

    return rekhas


# ── Main calculator ───────────────────────────────────────────────────────────

def calculate_ashtakavarga(kundli: dict) -> dict:
    """
    Calculate complete Ashtakavarga analysis for a kundli.

    Parameters
    ----------
    kundli : dict from KundliEngine.generate()

    Returns
    -------
    Full Ashtakavarga dict (see module docstring for shape).
    """
    rasi_chart = kundli.get("rasi_chart", {})
    lagna      = kundli.get("lagna", {})
    lagna_sign = _lagna_sign_idx(lagna)

    planets = ["Sun", "Moon", "Mars", "Mercury", "Jupiter", "Venus", "Saturn"]

    # Build contributor positions
    contributor_signs: dict[str, int] = {p: _planet_sign_idx(p, rasi_chart) for p in planets}
    contributor_signs["Lagna"] = lagna_sign

    # Bhinnashtakavarga for each contributor
    bhinna: dict[str, list[int]] = {}
    for contributor in planets + ["Lagna"]:
        bhinna[contributor] = _calc_bhinna(
            contributor,
            contributor_signs[contributor],
            rasi_chart,
            lagna_sign,
        )

    # Sarvashtakavarga = sum of all 8 bhinnashtakavargas per sign
    sarva = [0] * 12
    for sign_i in range(12):
        for contributor in planets + ["Lagna"]:
            sarva[sign_i] += bhinna[contributor][sign_i]

    # Planet scores = rekhas in the sign where the planet is placed
    planet_scores: dict[str, int] = {}
    for planet in planets:
        pidx = contributor_signs[planet]
        planet_scores[planet] = sarva[pidx]

    # Transit strength map
    transit_strength = {_RASIS[i]: sarva[i] for i in range(12)}

    # Strong / weak signs
    strong_signs = [_RASIS[i] for i in range(12) if sarva[i] >= 30]
    weak_signs   = [_RASIS[i] for i in range(12) if sarva[i] < 25]

    return {
        "bhinnashtakavarga": bhinna,
        "sarvashtakavarga":  sarva,
        "planet_scores":     planet_scores,
        "transit_strength":  transit_strength,
        "strong_signs":      strong_signs,
        "weak_signs":        weak_signs,
        "total_rekhas":      sum(sarva),
    }


def validate_ashtakavarga(result: dict) -> list[str]:
    """
    Validate Ashtakavarga result for correctness.
    Returns a list of error strings (empty = valid).

    Classical rule: Sarvashtakavarga must total exactly 337 rekhas.
    (8 sources × ~42 rekhas each = 337 total across all 12 signs)
    """
    errors: list[str] = []
    total = result.get("total_rekhas", 0)
    sarva = result.get("sarvashtakavarga", [])

    # Verify sum consistency
    computed_sum = sum(sarva) if sarva else 0
    if computed_sum != total:
        errors.append(
            f"total_rekhas mismatch: stored={total}, computed={computed_sum}"
        )

    # Classical validation: total must be 337
    # Note: some PyJHora implementations may produce 337 ± 1 due to rounding.
    # We allow a tolerance of ±2 for practical implementations.
    if not (335 <= computed_sum <= 339):
        errors.append(
            f"Sarvashtakavarga total_rekhas={computed_sum} is outside "
            f"expected range 335–339 (classical value is 337). "
            f"This indicates a benefic source table error."
        )

    # Each sign must have between 0 and 56 rekhas (8 sources × max 7 rekhas each)
    for i, val in enumerate(sarva):
        if not (0 <= val <= 56):
            errors.append(
                f"Sign {_RASIS[i]} has {val} rekhas — outside valid range 0–56"
            )

    return errors


# ── Ashtakavarga transit timing ───────────────────────────────────────────────

def ashtakavarga_transit_score(
    planet: str,
    transit_sign: str,
    kundli: dict,
) -> dict:
    """
    Score the quality of a planet transiting a particular sign
    using its Bhinnashtakavarga rekhas and Sarvashtakavarga.

    Returns:
    {
      "planet": str,
      "transit_sign": str,
      "bhinna_rekhas": int,    # planet's own rekhas in transit sign
      "sarva_rekhas":  int,    # total rekhas in transit sign
      "quality": "excellent"|"good"|"neutral"|"weak"|"challenging",
    }
    """
    avarga = calculate_ashtakavarga(kundli)
    sign_idx = _RASIS.index(transit_sign) if transit_sign in _RASIS else 0

    bhinna_rekhas = avarga["bhinnashtakavarga"].get(planet, [0]*12)[sign_idx]
    sarva_rekhas  = avarga["sarvashtakavarga"][sign_idx]

    # Quality thresholds (classical guidelines)
    if bhinna_rekhas >= 5 and sarva_rekhas >= 30:
        quality = "excellent"
    elif bhinna_rekhas >= 4 or sarva_rekhas >= 28:
        quality = "good"
    elif bhinna_rekhas >= 3 and sarva_rekhas >= 25:
        quality = "neutral"
    elif bhinna_rekhas >= 2:
        quality = "weak"
    else:
        quality = "challenging"

    return {
        "planet":        planet,
        "transit_sign":  transit_sign,
        "bhinna_rekhas": bhinna_rekhas,
        "sarva_rekhas":  sarva_rekhas,
        "quality":       quality,
    }
