"""
systems/kalachakra.py
=====================
Kalachakra Dasha — Nakshatra-pada based wheel dasha.

The 27 nakshatras × 4 padas = 108 padas. Each pada belongs to one of
12 signs that cycle in a specific pattern. Two groups:
  Savya  (forward) : Aries→Scorpio
  Apasavya (backward): Sagittarius→Taurus

Each Rashi dasha duration in Kalachakra:
  Aries 7, Taurus 16, Gemini 9, Cancer 21, Leo 5, Virgo 9,
  Libra 16, Scorpio 21 — then repeats in reverse for Apasavya

This implementation uses the standard Kalachakra durations.
"""
from __future__ import annotations
from datetime import date, timedelta
from .base import AbstractDashaSystem

_RASIS = [
    "Aries","Taurus","Gemini","Cancer","Leo","Virgo",
    "Libra","Scorpio","Sagittarius","Capricorn","Aquarius","Pisces",
]

# Standard Kalachakra dasha years per sign (Savya group)
_SAVYA_DURATIONS = {
    "Aries":7,"Taurus":16,"Gemini":9,"Cancer":21,"Leo":5,"Virgo":9,
    "Libra":16,"Scorpio":21,
}
# Apasavya (reverse) group
_APASAVYA_DURATIONS = {
    "Sagittarius":7,"Capricorn":16,"Aquarius":9,"Pisces":21,
    "Aries":5,"Taurus":9,"Gemini":16,"Cancer":21,
}

# Nakshatra → group & starting Rashi
# Each nakshatra covers 3 padas of 2 groups, alternating Savya/Apasavya
_NAK_GROUPS = {}  # built below
_SAVYA_NAKS = [
    "Ashwini","Bharani","Krittika","Rohini","Mrigashira","Ardra",
    "Punarvasu","Pushya","Ashlesha",
]
_APASAVYA_NAKS = [
    "Magha","Purva Phalguni","Uttara Phalguni","Hasta","Chitra","Swati",
    "Vishakha","Anuradha","Jyeshtha",
]
_SAVYA_NAK2 = [
    "Mula","Purva Ashadha","Uttara Ashadha","Shravana","Dhanishtha","Shatabhisha",
    "Purva Bhadrapada","Uttara Bhadrapada","Revati",
]
_ALL_NAKS = [
    "Ashwini","Bharani","Krittika","Rohini","Mrigashira","Ardra",
    "Punarvasu","Pushya","Ashlesha","Magha","Purva Phalguni","Uttara Phalguni",
    "Hasta","Chitra","Swati","Vishakha","Anuradha","Jyeshtha",
    "Mula","Purva Ashadha","Uttara Ashadha","Shravana","Dhanishtha",
    "Shatabhisha","Purva Bhadrapada","Uttara Bhadrapada","Revati",
]


def _add_years(d: date, years: float) -> date:
    return d + timedelta(days=int(years * 365.25))


def _moon_nakshatra_pada(birth_chart: dict) -> tuple[int, int]:
    """Return (nakshatra_index 0-26, pada 1-4) from Moon's longitude."""
    moon_lon = (
        birth_chart.get("planets", {}).get("Moon", {}).get("longitude", 0)
        or birth_chart.get("rasi_chart", {}).get("Moon", {}).get("longitude", 0)
    )
    nak_idx = int(moon_lon / (360 / 27)) % 27
    pada    = int((moon_lon % (360 / 27)) / (360 / 27 / 4)) + 1
    return nak_idx, min(pada, 4)


def _is_savya(nak_idx: int) -> bool:
    """Savya nakshatras: 0-8, 18-26; Apasavya: 9-17."""
    return nak_idx < 9 or nak_idx >= 18


def _starting_sign(nak_idx: int, pada: int) -> int:
    """Map nakshatra+pada to the starting Kalachakra Rashi index."""
    if nak_idx < 9:       # first Savya group
        return (nak_idx * 4 + (pada - 1)) % 8
    elif nak_idx < 18:    # Apasavya group (starts Sagittarius = index 8)
        return 8 + (((nak_idx - 9) * 4 + (pada - 1)) % 8)
    else:                 # second Savya group (wraps back)
        return (nak_idx - 18) * 4 % 12


def _kalachakra_signs(start_sign: int, savya: bool) -> list[tuple[str, float]]:
    """Return ordered (sign, years) list for one Kalachakra cycle."""
    if savya:
        order = list(_SAVYA_DURATIONS.items())   # 8 signs
    else:
        order = list(_APASAVYA_DURATIONS.items())
    # Rotate to start_sign
    n = start_sign % len(order)
    return order[n:] + order[:n]


class KalachakraDasha(AbstractDashaSystem):
    name         = "kalachakra"
    display_name = "Kalachakra Dasha"
    total_years  = 100
    description  = (
        "Nakshatra-pada based wheel dasha. Each of the 108 padas maps to "
        "a starting Rashi. Two groups: Savya (forward) and Apasavya "
        "(backward), each with 8 signs and fixed year allocations."
    )

    def calculate(self, birth_chart: dict, from_date: str,
                  to_date: str, depth: int = 2) -> dict:
        nak_idx, pada = _moon_nakshatra_pada(birth_chart)
        savya         = _is_savya(nak_idx)
        start_sign    = _starting_sign(nak_idx, pada)
        signs_years   = _kalachakra_signs(start_sign, savya)
        dob_str       = birth_chart.get("birth_info", {}).get("date", "1990-01-01")
        try:
            from datetime import datetime
            dob = datetime.strptime(dob_str, "%Y-%m-%d").date()
        except ValueError:
            dob = date(1990, 1, 1)

        # Balance in first sign
        moon_lon   = (
            birth_chart.get("planets", {}).get("Moon", {}).get("longitude", 0)
            or birth_chart.get("rasi_chart", {}).get("Moon", {}).get("longitude", 0)
        )
        pada_frac    = ((moon_lon % (360 / 27)) % (360 / 27 / 4)) / (360 / 27 / 4)
        first_years  = signs_years[0][1] if signs_years else 7
        balance      = first_years * (1 - pada_frac)

        timeline = []
        cursor   = dob
        for i, (sign, years) in enumerate(signs_years):
            period_years = balance if i == 0 else years
            end = _add_years(cursor, period_years)
            entry: dict = {
                "level":    1,
                "sign":     sign,
                "group":    "savya" if savya else "apasavya",
                "duration": f"{int(period_years)}yr",
                "start":    str(cursor),
                "end":      str(end),
            }
            if depth >= 2:
                entry["sub_periods"] = self._antardasha(cursor, end, signs_years)
            timeline.append(entry)
            cursor = end

        return {
            "system":           self.name,
            "display_name":     self.display_name,
            "total_years":      self.total_years,
            "group":            "savya" if savya else "apasavya",
            "nakshatra":        _ALL_NAKS[nak_idx] if nak_idx < 27 else "Unknown",
            "pada":             pada,
            "balance_at_birth": f"{balance:.1f}yr",
            "timeline":         timeline,
            "current":          self._find_current(timeline),
        }

    def get_current(self, birth_chart: dict) -> dict:
        result = self.calculate(birth_chart, "", "", depth=1)
        return result.get("current", {"sign": "Unknown", "mahadasha": "Unknown", "antardasha": "Unknown"})

    def list_periods(self) -> list[str]:
        return list(_SAVYA_DURATIONS.keys()) + list(_APASAVYA_DURATIONS.keys())

    def _antardasha(self, start: date, end: date,
                    parent_cycle: list) -> list[dict]:
        total_days = (end - start).days
        total_yrs  = sum(y for _, y in parent_cycle) or 1
        cursor     = start
        subs       = []
        for sign, years in parent_cycle:
            sub_days = int(total_days * years / total_yrs)
            sub_end  = cursor + timedelta(days=sub_days)
            subs.append({"level": 2, "sign": sign,
                          "start": str(cursor), "end": str(sub_end)})
            cursor = sub_end
        return subs

    def _find_current(self, timeline: list) -> dict:
        today = str(date.today())
        for p in timeline:
            if p["start"] <= today <= p["end"]:
                return {
                    "sign":      p["sign"],
                    "mahadasha": p["sign"],
                    "antardasha": p["sign"],
                    "started":   p["start"],
                    "ends":      p["end"],
                }
        return {"sign": "Unknown", "mahadasha": "Unknown", "antardasha": "Unknown"}
