"""
systems/chara.py
================
Chara Dasha (Jaimini) — Rashi (sign) based dasha system.

In Chara Dasha, each of the 12 Rashi (signs) gets a dasha period.
The duration of each sign's dasha equals:
  - Odd signs  → (Lagna sign to end of the sign sequence), reversed for 7th
  - Atmakaraka sign's dasha starts first

Simplified standard algorithm used here (Iranganti school):
  Duration of rasi dasha = (end_longitude_of_sign - AK_planet_longitude) → years
  Default: each sign gets (12 - its_index) years in a simple cycle.

For production, PyJHora/Jyotish library should be integrated for exact values.
"""
from __future__ import annotations
from datetime import date, timedelta
from .base import AbstractDashaSystem

_RASIS = [
    "Aries","Taurus","Gemini","Cancer","Leo","Virgo",
    "Libra","Scorpio","Sagittarius","Capricorn","Aquarius","Pisces",
]

# Jaimini karakas (highest degree = Atmakaraka)
_KARAKAS = ["Atmakaraka","Amatyakaraka","Bhratrukaraka","Matrukaraka",
             "Putrakaraka","Gnatikaraka","Darakaraka"]

_PLANETS = ["Sun","Moon","Mars","Mercury","Jupiter","Venus","Saturn","Rahu"]


def _add_years(d: date, years: float) -> date:
    return d + timedelta(days=int(years * 365.25))


def _get_lagna_rasi(birth_chart: dict) -> int:
    """Return 0-based lagna rasi index."""
    lagna_sign = (
        birth_chart.get("lagna", {}).get("sign")
        or birth_chart.get("birth_info", {}).get("lagna_sign")
        or "Aries"
    )
    try:
        return _RASIS.index(lagna_sign)
    except ValueError:
        return 0


def _rasi_duration(rasi_idx: int, lagna_idx: int) -> float:
    """
    Simplified Chara dasha duration for a sign.
    Standard rule: count from lagna to the sign in question.
    Odd lagna → forward count; Even lagna → backward count.
    Duration = count of signs (minimum 1, max 12).
    """
    if lagna_idx % 2 == 0:  # even lagna — backward count
        count = (lagna_idx - rasi_idx) % 12 or 12
    else:                   # odd lagna — forward count
        count = (rasi_idx - lagna_idx) % 12 or 12
    return float(count)


def _atmakaraka_sign(birth_chart: dict) -> int:
    """Return sign index of the Atmakaraka planet (highest degree)."""
    planets = (
        birth_chart.get("planets")
        or birth_chart.get("rasi_chart")
        or {}
    )
    best_deg  = -1
    best_sign = 0
    for pname in _PLANETS:
        pdata = planets.get(pname, {})
        if isinstance(pdata, dict):
            deg  = pdata.get("degree_in_sign", pdata.get("longitude", 0)) % 30
            sign = pdata.get("sign", "Aries")
            if deg > best_deg:
                best_deg  = deg
                try:
                    best_sign = _RASIS.index(sign)
                except ValueError:
                    best_sign = 0
    return best_sign


class CharaDasha(AbstractDashaSystem):
    name         = "chara"
    display_name = "Chara Dasha (Jaimini)"
    total_years  = 108   # Approximate — all 12 signs combined
    description  = (
        "Jaimini's sign-based dasha system. Duration of each sign's "
        "Mahadasha depends on the distance from the Lagna. Starts from "
        "the sign containing the Atmakaraka planet."
    )

    def calculate(self, birth_chart: dict, from_date: str,
                  to_date: str, depth: int = 2) -> dict:
        lagna_idx = _get_lagna_rasi(birth_chart)
        ak_sign   = _atmakaraka_sign(birth_chart)
        dob_str   = birth_chart.get("birth_info", {}).get("date", "1990-01-01")
        try:
            from datetime import datetime
            dob = datetime.strptime(dob_str, "%Y-%m-%d").date()
        except ValueError:
            dob = date(1990, 1, 1)

        timeline = []
        cursor   = dob
        # Start from AK sign, proceed through 12 signs
        for i in range(12):
            rasi_idx = (ak_sign + i) % 12
            years    = _rasi_duration(rasi_idx, lagna_idx)
            end      = _add_years(cursor, years)
            entry: dict = {
                "level":    1,
                "sign":     _RASIS[rasi_idx],
                "duration": f"{int(years)}yr",
                "start":    str(cursor),
                "end":      str(end),
            }
            if depth >= 2:
                entry["sub_periods"] = self._antardasha(
                    cursor, end, rasi_idx, lagna_idx)
            timeline.append(entry)
            cursor = end

        return {
            "system":       self.name,
            "display_name": self.display_name,
            "total_years":  self.total_years,
            "atmakaraka_sign": _RASIS[ak_sign],
            "timeline":     timeline,
            "current":      self._find_current(timeline),
        }

    def get_current(self, birth_chart: dict) -> dict:
        result = self.calculate(birth_chart, "", "", depth=1)
        return result.get("current", {"sign": "Unknown", "mahadasha": "Unknown", "antardasha": "Unknown"})

    def list_periods(self) -> list[str]:
        return _RASIS

    def _antardasha(self, start: date, end: date,
                    parent_rasi: int, lagna_idx: int) -> list[dict]:
        """12 sub-signs within a Mahadasha, proportional."""
        total_days = (end - start).days
        cursor     = start
        subs       = []
        total_sub  = sum(_rasi_duration((parent_rasi + i) % 12, lagna_idx)
                         for i in range(12))
        for i in range(12):
            ri       = (parent_rasi + i) % 12
            sub_yrs  = _rasi_duration(ri, lagna_idx)
            sub_days = int(total_days * sub_yrs / total_sub) if total_sub else 0
            sub_end  = cursor + timedelta(days=sub_days)
            subs.append({
                "level": 2,
                "sign":  _RASIS[ri],
                "start": str(cursor),
                "end":   str(sub_end),
            })
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
