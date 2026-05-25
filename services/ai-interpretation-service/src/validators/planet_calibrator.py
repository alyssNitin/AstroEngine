"""
ai_interpretation/planet_calibrator.py
=======================================
Builds a knowledge map of which planets are ACTIVELY giving results
for a specific native, based on their confirmations and corrections
of the initial predictions.
"""
from __future__ import annotations
import re
from dataclasses import dataclass, field, asdict


# House -> karaka (natural significator) mapping
HOUSE_KARAKAS: dict[int, list[str]] = {
    1: ["Sun", "Lagna lord"],
    2: ["Jupiter", "Venus"],
    3: ["Mars", "Mercury"],
    4: ["Moon", "Venus", "Mercury"],
    5: ["Jupiter"],
    6: ["Mars", "Saturn"],
    7: ["Venus", "Jupiter"],
    8: ["Saturn"],
    9: ["Jupiter", "Sun"],
    10: ["Saturn", "Sun", "Mercury", "Jupiter"],
    11: ["Jupiter", "Saturn"],
    12: ["Saturn", "Ketu"],
}

# Domain -> primary astrological indicators
DOMAIN_INDICATORS: dict[str, dict] = {
    "education": {
        "planets": ["Jupiter", "Mercury"],
        "houses":  [4, 5, 9],
        "charts":  ["D24_Siddhamsa"],
    },
    "career": {
        "planets": ["Saturn", "Sun", "Mercury"],
        "houses":  [10, 6, 11],
        "charts":  ["D10_Dasamsa"],
    },
    "marriage": {
        "planets": ["Venus", "Jupiter"],
        "houses":  [7, 2, 11],
        "charts":  ["D9_Navamsa"],
    },
    "children": {
        "planets": ["Jupiter"],
        "houses":  [5, 9],
        "charts":  ["D7_Saptamsa"],
    },
    "health": {
        "planets": ["Sun", "Moon", "Mars"],
        "houses":  [1, 6, 8, 12],
        "charts":  [],
    },
    "current_phase": {
        "planets": ["Moon"],
        "houses":  [],
        "charts":  [],
    },
    "finances": {
        "planets": ["Jupiter", "Venus", "Mercury"],
        "houses":  [2, 11, 5],
        "charts":  ["D2_Hora"],
    },
    "spirituality": {
        "planets": ["Jupiter", "Ketu", "Saturn"],
        "houses":  [9, 12, 8],
        "charts":  [],
    },
}


@dataclass
class PlanetSignal:
    planet: str
    domain: str
    confirmed: bool    # True = prediction was confirmed; False = corrected/wrong
    reason: str
    strength: float = 1.0   # 0.0-1.0 confidence weight


@dataclass
class PlanetKnowledge:
    active:    list[PlanetSignal] = field(default_factory=list)
    inactive:  list[PlanetSignal] = field(default_factory=list)
    summary:   str = ""

    def to_dict(self) -> dict:
        return {
            "active":   [asdict(s) for s in self.active],
            "inactive": [asdict(s) for s in self.inactive],
            "summary":  self.summary,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "PlanetKnowledge":
        obj = cls()
        obj.active   = [PlanetSignal(**s) for s in d.get("active", [])]
        obj.inactive = [PlanetSignal(**s) for s in d.get("inactive", [])]
        obj.summary  = d.get("summary", "")
        return obj

    def active_planet_names(self) -> list[str]:
        return list({s.planet for s in self.active})

    def for_prompt(self) -> str:
        if not self.active and not self.inactive:
            return "No calibration data yet -- treat all planets as equally weighted."
        lines = []
        if self.active:
            lines.append("CONFIRMED ACTIVE planets (rely on these for insights):")
            for s in self.active:
                lines.append(f"  [OK] {s.planet} ({s.domain}): {s.reason}")
        if self.inactive:
            lines.append("INACTIVE/MISREAD planets (use with caution):")
            for s in self.inactive:
                lines.append(f"  [X] {s.planet} ({s.domain}): {s.reason}")
        if self.summary:
            lines.append(f"\nSummary: {self.summary}")
        return "\n".join(lines)


class PlanetCalibrator:
    """
    Analyses user feedback and maps confirmations/corrections
    to astrological planets, building a PlanetKnowledge object.
    """

    @classmethod
    def calibrate_from_feedback(
        cls,
        corrections: dict,
        kundli: dict,
        llm_calibration: dict | None = None,
    ) -> PlanetKnowledge:
        """
        Build PlanetKnowledge from:
          1. Rule-based mapping (domain -> planet, confirmed or not)
          2. Optional LLM-generated calibration enrichment
        """
        pk = PlanetKnowledge()

        for domain, feedback_text in corrections.items():
            confirmed = cls._is_confirmed(feedback_text)
            indicators = DOMAIN_INDICATORS.get(domain, {})
            planets = indicators.get("planets", [])

            reason = cls._build_reason(domain, feedback_text, kundli, confirmed)

            for planet in planets:
                signal = PlanetSignal(
                    planet=planet,
                    domain=domain,
                    confirmed=confirmed,
                    reason=reason,
                    strength=1.0 if confirmed else 0.5,
                )
                if confirmed:
                    pk.active.append(signal)
                else:
                    pk.inactive.append(signal)

        # Enrich with LLM calibration if provided
        if llm_calibration:
            cls._merge_llm_calibration(pk, llm_calibration)

        pk.summary = cls._build_summary(pk)
        return pk

    @classmethod
    def merge_new_feedback(
        cls,
        existing_knowledge: PlanetKnowledge,
        new_corrections: dict,
        kundli: dict,
    ) -> PlanetKnowledge:
        """Add new chat feedback into existing planet knowledge."""
        new_pk = cls.calibrate_from_feedback(new_corrections, kundli)
        # Merge signals -- new always overwrites existing for same planet+domain
        existing_keys = {(s.planet, s.domain) for s in existing_knowledge.active + existing_knowledge.inactive}
        for s in new_pk.active:
            if (s.planet, s.domain) not in existing_keys:
                existing_knowledge.active.append(s)
        for s in new_pk.inactive:
            if (s.planet, s.domain) not in existing_keys:
                existing_knowledge.inactive.append(s)
        existing_knowledge.summary = cls._build_summary(existing_knowledge)
        return existing_knowledge

    @staticmethod
    def _is_confirmed(text: str) -> bool:
        """Heuristic: does this feedback text indicate confirmation?"""
        text_lower = text.lower()

        # Explicit negation prefixes override positive keywords
        NEGATION_PREFIXES = [
            "not quite", "not correct", "not right", "not accurate",
            "not true", "not matching", "no,", "nope", "wrong",
            "actually", "incorrect", "inaccurate", "doesn't match",
            "does not match", "that's not", "that is not",
        ]
        for neg in NEGATION_PREFIXES:
            if neg in text_lower:
                return False

        CONFIRM_MARKERS = [
            "confirmed", "yes,", "yes ", "yes!", "correct", "that's right",
            "that is right", "accurate", "true", "matches", "absolutely", "exactly",
            "right!", "right,", "confirmed --", "confirmed-",
        ]
        for m in CONFIRM_MARKERS:
            if m in text_lower:
                return True
        # Standalone "right" at end of sentence is positive
        if re.search(r"\bright[.!]?\s*$", text_lower):
            return True
        return False

    @staticmethod
    def _build_reason(
        domain: str,
        feedback: str,
        kundli: dict,
        confirmed: bool,
    ) -> str:
        rasi = kundli.get("rasi_chart", {})
        indicators = DOMAIN_INDICATORS.get(domain, {})
        primary_planets = indicators.get("planets", [])

        planet_positions = []
        for p in primary_planets:
            if p in rasi:
                info = rasi[p]
                planet_positions.append(
                    f"{p} in {info.get('rasi', '?')} ({info.get('degree_str', '?')})"
                )

        pos_str = "; ".join(planet_positions) if planet_positions else "chart position unknown"
        action  = "Confirmed" if confirmed else "Corrected"
        short_feedback = feedback[:80] + ("..." if len(feedback) > 80 else "")

        return f"{action} for {domain} | {pos_str} | User: '{short_feedback}'"

    @staticmethod
    def _merge_llm_calibration(pk: PlanetKnowledge, llm: dict) -> None:
        """Incorporate Claude's richer calibration signals."""
        for item in llm.get("active_planets", []):
            planet = item.get("planet", "")
            domain = item.get("domain", "")
            reason = item.get("reason", "")
            # Only add if not already present from rule-based
            exists = any(s.planet == planet and s.domain == domain for s in pk.active)
            if not exists and planet:
                pk.active.append(PlanetSignal(
                    planet=planet, domain=domain, confirmed=True,
                    reason=f"[LLM] {reason}", strength=0.8,
                ))
        pk.summary = llm.get("summary", pk.summary) or pk.summary

    @staticmethod
    def _build_summary(pk: PlanetKnowledge) -> str:
        active_names  = list({s.planet for s in pk.active})
        inactive_names = list({s.planet for s in pk.inactive})
        parts = []
        if active_names:
            parts.append(f"Active planets: {', '.join(active_names)}")
        if inactive_names:
            parts.append(f"Needs review: {', '.join(inactive_names)}")
        return " | ".join(parts) if parts else "Calibration pending."
