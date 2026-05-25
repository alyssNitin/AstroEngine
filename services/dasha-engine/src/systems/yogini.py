"""
systems/yogini.py
=================
Yogini Dasha system — 36-year cycle governed by 8 Yogini lords.

The 8 Yoginis (manifestations of Shakti) each rule a period
proportional to their index (1–8 years), totalling 36 years.
The starting Yogini is determined by the Moon's nakshatra number
modulo 8.

Yogini lords & durations:
  Mangala(Moon)  1y  Pingala(Sun)   2y  Dhanya(Jupiter)  3y
  Bhramari(Mars) 4y  Bhadrika(Merc) 5y  Ulka(Saturn)     6y
  Siddha(Venus)  7y  Sankata(Rahu)  8y
"""
from __future__ import annotations
from datetime import date, timedelta
from .base import AbstractDashaSystem

_YOGINIS = [
    ("Mangala",  "Moon",    1),
    ("Pingala",  "Sun",     2),
    ("Dhanya",   "Jupiter", 3),
    ("Bhramari", "Mars",    4),
    ("Bhadrika", "Mercury", 5),
    ("Ulka",     "Saturn",  6),
    ("Siddha",   "Venus",   7),
    ("Sankata",  "Rahu",    8),
]
_TOTAL_YEARS = 36

_NAKSHATRAS = [
    "Ashwini","Bharani","Krittika","Rohini","Mrigashira","Ardra",
    "Punarvasu","Pushya","Ashlesha","Magha","Purva Phalguni",
    "Uttara Phalguni","Hasta","Chitra","Swati","Vishakha","Anuradha",
    "Jyeshtha","Mula","Purva Ashadha","Uttara Ashadha","Shravana",
    "Dhanishtha","Shatabhisha","Purva Bhadrapada","Uttara Bhadrapada",
    "Revati",
]


def _nakshatra_index(birth_chart: dict) -> int:
    """Return 0-based nakshatra index from Moon's position."""
    moon_lon = (
        birth_chart.get("planets", {}).get("Moon", {}).get("longitude", 0)
        or birth_chart.get("rasi_chart", {}).get("Moon", {}).get("longitude", 0)
    )
    return int(moon_lon / (360 / 27)) % 27


def _add_years(d: date, years: float) -> date:
    days = int(years * 365.25)
    return d + timedelta(days=days)


def _format_dur(years: float) -> str:
    total_days = int(years * 365.25)
    y, rem = divmod(total_days, 365)
    m, d   = divmod(rem, 30)
    return f"{y}yr {m}m {d}d"


class YoginiDasha(AbstractDashaSystem):
    name         = "yogini"
    display_name = "Yogini Dasha"
    total_years  = _TOTAL_YEARS
    description  = (
        "36-year cycle based on 8 Yogini lords. Starting point is the "
        "Moon's nakshatra at birth (nakshatra_number mod 8)."
    )

    def calculate(self, birth_chart: dict, from_date: str,
                  to_date: str, depth: int = 2) -> dict:
        nak_idx   = _nakshatra_index(birth_chart)
        start_idx = nak_idx % 8
        dob_str   = birth_chart.get("birth_info", {}).get("date", "1990-01-01")
        try:
            from datetime import datetime
            dob = datetime.strptime(dob_str, "%Y-%m-%d").date()
        except ValueError:
            dob = date(1990, 1, 1)

        # Balance remaining at birth (fractional completion of first period)
        moon_lon = (
            birth_chart.get("planets", {}).get("Moon", {}).get("longitude", 0)
            or birth_chart.get("rasi_chart", {}).get("Moon", {}).get("longitude", 0)
        )
        nak_fraction = (moon_lon % (360 / 27)) / (360 / 27)
        first_name, first_lord, first_years = _YOGINIS[start_idx]
        balance_years = first_years * (1 - nak_fraction)

        timeline = []
        cursor   = dob
        for i in range(8):
            idx = (start_idx + i) % 8
            name, lord, years = _YOGINIS[idx]
            period_years = balance_years if i == 0 else float(years)
            end = _add_years(cursor, period_years)

            entry: dict = {
                "level":    1,
                "yogini":   name,
                "lord":     lord,
                "start":    str(cursor),
                "end":      str(end),
                "duration": _format_dur(period_years),
            }
            if depth >= 2:
                entry["sub_periods"] = self._sub_periods(cursor, end, lord, depth)
            timeline.append(entry)
            cursor = end

        return {
            "system":       self.name,
            "display_name": self.display_name,
            "total_years":  self.total_years,
            "balance_at_birth": _format_dur(balance_years),
            "timeline":     timeline,
            "current":      self._find_current(timeline),
        }

    def get_current(self, birth_chart: dict) -> dict:
        result = self.calculate(birth_chart, "", "", depth=1)
        return result.get("current",
                          {"yogini": "Unknown", "lord": "Unknown",
                           "mahadasha": "Unknown", "antardasha": "Unknown"})

    def list_periods(self) -> list[str]:
        return [f"{n} ({l})" for n, l, _ in _YOGINIS]

    def _find_current(self, timeline: list) -> dict:
        today = str(date.today())
        for period in timeline:
            if period["start"] <= today <= period["end"]:
                return {
                    "yogini":    period["yogini"],
                    "lord":      period["lord"],
                    "started":   period["start"],
                    "ends":      period["end"],
                    "mahadasha": period["lord"],
                    "antardasha": period["lord"],
                }
        return {"yogini": "Unknown", "lord": "Unknown",
                "mahadasha": "Unknown", "antardasha": "Unknown"}


    def _sub_periods(self, start: date, end: date, parent_lord: str,
                     depth: int) -> list[dict]:
        """Antardasha: each of 8 Yoginis within the Mahadasha, proportional."""
        total_days = (end - start).days
        cursor     = start
        subs       = []
        for name, lord, years in _YOGINIS:
            frac     = years / _TOTAL_YEARS
            sub_days = int(total_days * frac)
            sub_end  = cursor + timedelta(days=sub_days)
            subs.append({
                "level":  2,
                "yogini": name,
                "lord":   lord,
                "start":  str(cursor),
                "end":    str(sub_end),
            })
            cursor = sub_end
        return subs
