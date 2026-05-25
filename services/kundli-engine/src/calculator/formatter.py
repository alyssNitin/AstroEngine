"""
kundli_engine/formatter.py
==========================
Re-exports formatters from PyJHora's claude_formatter.py.
Falls back to built-in compact formatter if PyJHora is unavailable.
"""
from __future__ import annotations
import sys
from backend.config import PYJHORA_PATH

sys.path.insert(0, PYJHORA_PATH)

try:
    from claude_formatter import format_for_claude, format_for_claude_compact  # type: ignore
except ImportError:
    def format_for_claude(kundli: dict) -> str:  # type: ignore[misc]
        return format_for_claude_compact(kundli)

    def format_for_claude_compact(kundli: dict) -> str:  # type: ignore[misc]
        """Minimal fallback formatter -- mirrors PyJHora compact output structure."""
        bi    = kundli.get("birth_info", {})
        lagna = kundli.get("lagna", {})
        rasi  = kundli.get("rasi_chart", {})
        div   = kundli.get("divisional_charts", {})
        vim   = kundli.get("dashas", {}).get("vimshottari", {})

        lines = [
            "BIRTH DETAILS",
            f"  Name      : {bi.get('name','?')}",
            f"  Date      : {bi.get('date_of_birth','')}",
            f"  Time      : {bi.get('time_of_birth','')}",
            f"  Place     : {bi.get('place','')}",
            f"  Lat/Lon   : {bi.get('latitude','')} / {bi.get('longitude','')}",
            f"  Ayanamsa  : {bi.get('ayanamsa_mode','')} {bi.get('ayanamsa_value','')}",
            "",
            f"LAGNA (ASCENDANT): {lagna.get('rasi','')} {lagna.get('degree_str','')}  "
            f"Nakshatra: {lagna.get('nakshatra','')} Pada {lagna.get('nakshatra_pada','')}",
            "",
            "D1 RASI CHART",
        ]
        for planet, info in rasi.items():
            retro = " (R)" if info.get("retrograde") else ""
            lines.append(f"  {planet:<12} {info.get('rasi',''):<14} "
                         f"{info.get('degree_str',''):<10} "
                         f"{info.get('nakshatra','')}{retro}")

        # D9 Navamsa
        d9 = div.get("D9_Navamsa", {})
        if d9 and "error" not in d9:
            asc = d9.get("ascendant", {})
            lines.append("\nD9 NAVAMSA (Soul / Marriage / Dharma)")
            lines.append(f"  Lagna: {asc.get('rasi','')} {asc.get('degree','')} deg")
            for pn, pd in d9.get("planets", {}).items():
                lines.append(f"  {pn:<12} {pd.get('rasi',''):<14} {pd.get('degree','')} deg")

        # D10 Dasamsa
        d10 = div.get("D10_Dasamsa", {})
        if d10 and "error" not in d10:
            asc = d10.get("ascendant", {})
            lines.append("\nD10 DASAMSA (Career / Profession)")
            lines.append(f"  Lagna: {asc.get('rasi','')} {asc.get('degree','')} deg")
            for pn, pd in d10.get("planets", {}).items():
                lines.append(f"  {pn:<12} {pd.get('rasi',''):<14} {pd.get('degree','')} deg")

        # Vimshottari
        bal = vim.get("balance_at_birth", "N/A")
        lines.append(f"\nVIMSHOTTARI DASHA  (Balance at birth: {bal})")
        seen: set = set()
        for p in vim.get("periods", []):
            pair = (p.get("maha_lord",""), p.get("antara_lord",""))
            if pair in seen:
                continue
            seen.add(pair)
            lines.append(f"  {pair[0]:<14} {pair[1]:<14} {p.get('start_date','')}")

        return "\n".join(lines)

__all__ = ["format_for_claude", "format_for_claude_compact"]
