"""
systems/moola.py
================
Moola Dasha — Nakshatra-based system with 9 planets, 100-year cycle.

Nakshatra group → starting planet:
  Nakshatras 1-9  (Ashwini–Ashlesha): Sun group
  Nakshatras 10-18(Magha–Jyeshtha)  : Moon group
  Nakshatras 19-27(Mula–Revati)     : Mars group

Planet sequence & years:
  Sun(7) Moon(6) Mars(10) Rahu(18) Jup(16) Sat(19) Merc(17) Ketu(3) Ven(4)
  Total = 100 years
"""
from __future__ import annotations
from datetime import date, timedelta
from .base import AbstractDashaSystem

_MOOLA_ORDER = [
    ("Sun",     7),
    ("Moon",    6),
    ("Mars",   10),
    ("Rahu",   18),
    ("Jupiter",16),
    ("Saturn", 19),
    ("Mercury",17),
    ("Ketu",    3),
    ("Venus",   4),
]
_TOTAL_YEARS = 100

_ALL_NAKS = [
    "Ashwini","Bharani","Krittika","Rohini","Mrigashira","Ardra",
    "Punarvasu","Pushya","Ashlesha","Magha","Purva Phalguni","Uttara Phalguni",
    "Hasta","Chitra","Swati","Vishakha","Anuradha","Jyeshtha",
    "Mula","Purva Ashadha","Uttara Ashadha","Shravana","Dhanishtha",
    "Shatabhisha","Purva Bhadrapada","Uttara Bhadrapada","Revati",
]

# Nakshatra → starting planet index (0-based into _MOOLA_ORDER)
def _starting_planet(nak_idx: int) -> int:
    group = nak_idx // 9          # 0=Sun, 1=Moon, 2=Mars
    within = nak_idx % 9         # position in group
    # Each group of 9 nakshatras maps to 9 planets in order
    return (group * 1 + within) % 9  # simplified — rotate by group offset


def _add_years(d: date, years: float) -> date:
    return d + timedelta(days=int(years * 365.25))


def _format_dur(years: float) -> str:
    total_days = int(years * 365.25)
    y, rem     = divmod(total_days, 365)
    m, d       = divmod(rem, 30)
    return f"{y}yr {m}m {d}d"


class MoolaDasha(AbstractDashaSystem):
    name         = "moola"
    display_name = "Moola Dasha"
    total_years  = _TOTAL_YEARS
    description  = (
        "Nakshatra-based 100-year dasha system. Nine planets rule in "
        "sequence: Sun(7), Moon(6), Mars(10), Rahu(18), Jupiter(16), "
        "Saturn(19), Mercury(17), Ketu(3), Venus(4). Starting planet "
        "is determined by the Moon's nakshatra group."
    )

    def calculate(self, birth_chart: dict, from_date: str,
                  to_date: str, depth: int = 2) -> dict:
        moon_lon = (
            birth_chart.get("planets", {}).get("Moon", {}).get("longitude", 0)
            or birth_chart.get("rasi_chart", {}).get("Moon", {}).get("longitude", 0)
        )
        nak_idx     = int(moon_lon / (360 / 27)) % 27
        start_idx   = _starting_planet(nak_idx)
        nak_frac    = (moon_lon % (360 / 27)) / (360 / 27)
        first_years = _MOOLA_ORDER[start_idx][1]
        balance     = first_years * (1 - nak_frac)

        dob_str = birth_chart.get("birth_info", {}).get("date", "1990-01-01")
        try:
            from datetime import datetime
            dob = datetime.strptime(dob_str, "%Y-%m-%d").date()
        except ValueError:
            dob = date(1990, 1, 1)

        timeline = []
        cursor   = dob
        for i in range(9):
            idx    = (start_idx + i) % 9
            planet, years = _MOOLA_ORDER[idx]
            period_years  = balance if i == 0 else float(years)
            end = _add_years(cursor, period_years)
            entry: dict = {
                "level":    1,
                "planet":   planet,
                "duration": _format_dur(period_years),
                "start":    str(cursor),
                "end":      str(end),
            }
            if depth >= 2:
                entry["sub_periods"] = self._antardasha(cursor, end, start_idx)
            timeline.append(entry)
            cursor = end

        return {
            "system":           self.name,
            "display_name":     self.display_name,
            "total_years":      self.total_years,
            "nakshatra":        _ALL_NAKS[nak_idx],
            "balance_at_birth": _format_dur(balance),
            "timeline":         timeline,
            "current":          self._find_current(timeline),
        }

    def get_current(self, birth_chart: dict) -> dict:
        result = self.calculate(birth_chart, "", "", depth=1)
        return result.get("current", {"planet": "Unknown", "mahadasha": "Unknown", "antardasha": "Unknown"})

    def list_periods(self) -> list[str]:
        return [p for p, _ in _MOOLA_ORDER]

    def _antardasha(self, start: date, end: date, parent_idx: int) -> list[dict]:
        total_days = (end - start).days
        cursor     = start
        subs       = []
        for i in range(9):
            idx     = (parent_idx + i) % 9
            planet, years = _MOOLA_ORDER[idx]
            sub_days = int(total_days * years / _TOTAL_YEARS)
            sub_end  = cursor + timedelta(days=sub_days)
            subs.append({"level": 2, "planet": planet,
                          "start": str(cursor), "end": str(sub_end)})
            cursor = sub_end
        return subs

    def _find_current(self, timeline: list) -> dict:
        today = str(date.today())
        for p in timeline:
            if p["start"] <= today <= p["end"]:
                return {
                    "planet":    p["planet"],
                    "mahadasha": p["planet"],
                    "antardasha": p["planet"],
                    "started":   p["start"],
                    "ends":      p["end"],
                }
        return {"planet": "Unknown", "mahadasha": "Unknown", "antardasha": "Unknown"}
