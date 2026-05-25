"""
systems/narayana.py
===================
Narayana Dasha (Jaimini) — Rashi-based dasha (variant of Chara).

Narayana Dasha is a sign-based system where each Rashi gets a fixed
duration based on its position from the Lagna. The key difference from
Chara Dasha is that Narayana Dasha always starts from the Lagna sign
(not the Atmakaraka sign) and uses a fixed-forward sequence.

Duration rule (simplified):
  - Count from the sign to its dispositor's sign
  - Odd rasis: count forward; Even rasis: count backward
"""
from __future__ import annotations
from datetime import date, timedelta
from .base import AbstractDashaSystem

_RASIS = [
    "Aries","Taurus","Gemini","Cancer","Leo","Virgo",
    "Libra","Scorpio","Sagittarius","Capricorn","Aquarius","Pisces",
]
_RASI_LORDS = {
    "Aries":"Mars","Taurus":"Venus","Gemini":"Mercury","Cancer":"Moon",
    "Leo":"Sun","Virgo":"Mercury","Libra":"Venus","Scorpio":"Mars",
    "Sagittarius":"Jupiter","Capricorn":"Saturn","Aquarius":"Saturn",
    "Pisces":"Jupiter",
}
_ODD_RASIS  = {"Aries","Gemini","Leo","Libra","Sagittarius","Aquarius"}
_EVEN_RASIS = {"Taurus","Cancer","Virgo","Scorpio","Capricorn","Pisces"}


def _add_years(d: date, years: float) -> date:
    return d + timedelta(days=int(years * 365.25))


def _get_lagna_rasi(birth_chart: dict) -> int:
    lagna_sign = (
        birth_chart.get("lagna", {}).get("sign")
        or birth_chart.get("birth_info", {}).get("lagna_sign")
        or "Aries"
    )
    try:
        return _RASIS.index(lagna_sign)
    except ValueError:
        return 0


def _narayana_duration(rasi_idx: int) -> float:
    """
    Duration = count of signs from rasi to its dispositor's rasi.
    Odd signs count forward; even signs count backward.
    """
    sign = _RASIS[rasi_idx]
    lord = _RASI_LORDS.get(sign, "Mars")
    # Find the sign lord's exaltation/own sign (simplified: use own sign)
    lord_sign_map = {
        "Sun":"Leo","Moon":"Cancer","Mars":"Aries","Mercury":"Virgo",
        "Jupiter":"Sagittarius","Venus":"Taurus","Saturn":"Capricorn",
        "Rahu":"Aquarius","Ketu":"Scorpio",
    }
    lord_rasi = _RASIS.index(lord_sign_map.get(lord, "Aries"))
    if sign in _ODD_RASIS:
        count = (lord_rasi - rasi_idx) % 12 or 12
    else:
        count = (rasi_idx - lord_rasi) % 12 or 12
    return float(max(1, count))


class NarayanaDasha(AbstractDashaSystem):
    name         = "narayana"
    display_name = "Narayana Dasha (Jaimini)"
    total_years  = 108
    description  = (
        "Jaimini's Rashi-based dasha starting from the Lagna. Duration "
        "of each sign depends on the distance to its dispositor's sign. "
        "Odd signs count forward; even signs count backward."
    )

    def calculate(self, birth_chart: dict, from_date: str,
                  to_date: str, depth: int = 2) -> dict:
        lagna_idx = _get_lagna_rasi(birth_chart)
        dob_str   = birth_chart.get("birth_info", {}).get("date", "1990-01-01")
        try:
            from datetime import datetime
            dob = datetime.strptime(dob_str, "%Y-%m-%d").date()
        except ValueError:
            dob = date(1990, 1, 1)

        timeline = []
        cursor   = dob
        for i in range(12):
            rasi_idx = (lagna_idx + i) % 12
            years    = _narayana_duration(rasi_idx)
            end      = _add_years(cursor, years)
            entry: dict = {
                "level":    1,
                "sign":     _RASIS[rasi_idx],
                "lord":     _RASI_LORDS.get(_RASIS[rasi_idx], ""),
                "duration": f"{int(years)}yr",
                "start":    str(cursor),
                "end":      str(end),
            }
            if depth >= 2:
                entry["sub_periods"] = self._antardasha(
                    cursor, end, rasi_idx)
            timeline.append(entry)
            cursor = end

        return {
            "system":       self.name,
            "display_name": self.display_name,
            "total_years":  self.total_years,
            "lagna_sign":   _RASIS[lagna_idx],
            "timeline":     timeline,
            "current":      self._find_current(timeline),
        }

    def get_current(self, birth_chart: dict) -> dict:
        result = self.calculate(birth_chart, "", "", depth=1)
        return result.get("current", {"sign": "Unknown", "mahadasha": "Unknown", "antardasha": "Unknown"})

    def list_periods(self) -> list[str]:
        return _RASIS

    def _antardasha(self, start: date, end: date, parent_rasi: int) -> list[dict]:
        total_days = (end - start).days
        total_yrs  = sum(_narayana_duration((parent_rasi + i) % 12)
                         for i in range(12)) or 1
        cursor = start
        subs   = []
        for i in range(12):
            ri       = (parent_rasi + i) % 12
            sub_yrs  = _narayana_duration(ri)
            sub_days = int(total_days * sub_yrs / total_yrs)
            sub_end  = cursor + timedelta(days=sub_days)
            subs.append({"level": 2, "sign": _RASIS[ri],
                          "lord": _RASI_LORDS.get(_RASIS[ri], ""),
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
