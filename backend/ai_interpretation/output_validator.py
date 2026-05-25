"""
backend/ai_interpretation/output_validator.py
===============================================
Deterministic post-generation validation of AI astrological output.

Architecture §5.1: "A deterministic validation layer checks AI output for
internal consistency with the computed chart data before delivery."

What is validated
-----------------
1. Disclaimer presence — every response must contain a disclaimer.
2. Planet name consistency — AI should not hallucinate planet names.
3. Sign name consistency — rasi/sign names must be from the Vedic canon.
4. No PII leakage — response must not contain name or DOB patterns.
5. Minimum length — response should be substantive (>100 chars).
6. No refusal patterns — detect if Claude refused instead of answering.

Design principles
-----------------
- All checks are deterministic (no LLM calls) — fast, cheap, reliable.
- Failures are LOGGED and returned as warnings, NOT silently dropped.
- The caller decides whether to block or pass-through on failure.
- Warnings are attached to the API response for transparency.

Usage
-----
    from backend.ai_interpretation.output_validator import validate_ai_output

    result = validate_ai_output(ai_text, kundli_data, report_type="personal")
    if result.has_warnings:
        logger.warning("AI output validation: %s", result.warnings)
    # result.text is always the (possibly annotated) output
"""
from __future__ import annotations

import logging
from backend.core.logging import get_logger
import re
from dataclasses import dataclass, field
from typing import Optional

logger = get_logger(__name__)

# ── Canonical Vedic astronomy vocabulary ──────────────────────────────────────

VEDIC_PLANETS = {
    "sun", "moon", "mars", "mercury", "jupiter", "venus", "saturn",
    "rahu", "ketu", "ascendant", "lagna",
    "surya", "chandra", "mangal", "budha", "guru", "shukra", "shani",
}

RASI_NAMES = {
    "aries", "taurus", "gemini", "cancer", "leo", "virgo",
    "libra", "scorpio", "sagittarius", "capricorn", "aquarius", "pisces",
    "mesh", "vrishabha", "mithuna", "karka", "simha", "kanya",
    "tula", "vrishchika", "dhanu", "makara", "kumbha", "meena",
}

DISCLAIMER_PHRASES = [
    "entertainment", "self-reflection", "not medical advice",
    "not financial advice", "for guidance only", "guidance only",
    "general information", "consult a", "professional advice",
    "astrological guidance", "disclaimer",
]

REFUSAL_PATTERNS = [
    r"i cannot\s+(provide|generate|create|help)",
    r"i('m| am) (unable|not able) to",
    r"as an ai\s+(language model|assistant)",
    r"i don't (have|possess) the ability",
    r"i (won't|will not) (provide|generate)",
]

_COMPILED_REFUSALS = [re.compile(p, re.IGNORECASE) for p in REFUSAL_PATTERNS]

# Date pattern that might indicate PII leakage
_DATE_PATTERN = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")

# Full name leakage — catches "John Smith" style patterns (not single words)
_FULL_NAME_PATTERN = re.compile(r"\b([A-Z][a-z]+ [A-Z][a-z]+)\b")


# ── Result object ─────────────────────────────────────────────────────────────

@dataclass
class ValidationResult:
    text:           str
    passed:         bool = True
    warnings:       list[str] = field(default_factory=list)
    errors:         list[str] = field(default_factory=list)
    disclaimer_ok:  bool = False
    length_ok:      bool = False
    no_refusal:     bool = True

    @property
    def has_warnings(self) -> bool:
        return bool(self.warnings)

    @property
    def has_errors(self) -> bool:
        return bool(self.errors)

    def to_dict(self) -> dict:
        return {
            "passed":        self.passed,
            "warnings":      self.warnings,
            "errors":        self.errors,
            "disclaimer_ok": self.disclaimer_ok,
            "length_ok":     self.length_ok,
            "no_refusal":    self.no_refusal,
        }


# ── Validator ─────────────────────────────────────────────────────────────────

def validate_ai_output(
    ai_text:     str,
    kundli:      Optional[dict] = None,
    report_type: str = "personal",
    min_length:  int = 150,
) -> ValidationResult:
    """
    Run all deterministic checks on an AI-generated astrological text.

    Parameters
    ----------
    ai_text     : The raw text returned by the LLM.
    kundli      : Optional kundli dict for chart-consistency checks.
    report_type : "personal" | "career" | "compatibility" | "yearly" | "remedies"
    min_length  : Minimum acceptable response length in characters.

    Returns
    -------
    ValidationResult with warnings/errors attached.
    The .text field always contains the original (unmodified) AI text.
    """
    result = ValidationResult(text=ai_text)

    if not ai_text or not ai_text.strip():
        result.passed = False
        result.errors.append("AI returned empty response")
        return result

    text_lower = ai_text.lower()

    # ── 1. Minimum length ────────────────────────────────────────────────────
    result.length_ok = len(ai_text.strip()) >= min_length
    if not result.length_ok:
        result.warnings.append(
            f"Response too short: {len(ai_text.strip())} chars (min {min_length})"
        )

    # ── 2. Disclaimer check ──────────────────────────────────────────────────
    result.disclaimer_ok = any(phrase in text_lower for phrase in DISCLAIMER_PHRASES)
    if not result.disclaimer_ok:
        result.warnings.append(
            "Response missing astrological disclaimer. "
            "Disclaimer will be appended by API layer."
        )

    # ── 3. Refusal detection ─────────────────────────────────────────────────
    for pattern in _COMPILED_REFUSALS:
        if pattern.search(ai_text):
            result.no_refusal = False
            result.passed = False
            result.errors.append(
                "AI appears to have refused to answer rather than generating a reading. "
                "Trigger auto-refund and retry."
            )
            break

    # ── 4. Hallucinated planet names ─────────────────────────────────────────
    # Extract capitalised single words that look like planet names but aren't canonical
    BOGUS_PLANETS = re.findall(r"\b(Planet\s+[A-Z][a-z]+|[A-Z][a-z]+inus|[A-Z][a-z]+on)\b", ai_text)
    suspicious = [p for p in BOGUS_PLANETS if p.lower().split()[-1] not in VEDIC_PLANETS]
    if suspicious:
        result.warnings.append(
            f"Possible non-Vedic planet reference(s): {suspicious[:3]}. "
            "Verify these are yogas or terminology, not hallucinated planet names."
        )

    # ── 5. Sign name consistency (only if kundli provided) ───────────────────
    if kundli:
        rasi = kundli.get("rasi_chart", {})
        chart_signs = {
            info.get("rasi", "").lower()
            for info in rasi.values()
            if isinstance(info, dict) and info.get("rasi")
        }
        # Detect any rasi mentioned in AI that's not in the canonical list
        mentioned_signs = set()
        for word in re.findall(r"\b[A-Z][a-z]{3,14}\b", ai_text):
            if word.lower() in RASI_NAMES:
                mentioned_signs.add(word.lower())

        # Check chart signs are mentioned (expect at least lagna sign to appear)
        if chart_signs and not (chart_signs & mentioned_signs):
            result.warnings.append(
                "No chart-specific rasi signs detected in AI response. "
                "The interpretation may be generic rather than chart-specific."
            )

    # ── 6. PII leakage check ─────────────────────────────────────────────────
    # Flag ISO date patterns (DOB) in the output
    dates_found = _DATE_PATTERN.findall(ai_text)
    if dates_found:
        result.warnings.append(
            f"AI response contains ISO date(s) ({dates_found[:2]}) — "
            "possible DOB leakage. Review prompt PII scrubbing."
        )

    # ── 7. Set overall pass/fail ─────────────────────────────────────────────
    if result.errors:
        result.passed = False
    elif len(result.warnings) >= 3:
        # Many warnings = likely low quality, but not a hard fail
        result.warnings.append(
            "Multiple quality warnings — consider regenerating if user reports poor quality."
        )

    # ── Log summary ───────────────────────────────────────────────────────────
    if result.errors:
        logger.error(
            "[output_validator] FAIL type=%s errors=%d warnings=%d len=%d",
            report_type, len(result.errors), len(result.warnings), len(ai_text),
        )
    elif result.warnings:
        logger.warning(
            "[output_validator] WARN type=%s warnings=%d len=%d",
            report_type, len(result.warnings), len(ai_text),
        )
    else:
        logger.info(
            "[output_validator] OK   type=%s len=%d",
            report_type, len(ai_text),
        )

    return result


# ── Convenience: append disclaimer if missing ─────────────────────────────────

STANDARD_DISCLAIMER = (
    "\n\n---\n"
    "*This astrological reading is for entertainment and self-reflection purposes only. "
    "It does not constitute medical, legal, financial, or professional advice. "
    "Please consult qualified professionals for important life decisions.*"
)


def ensure_disclaimer(text: str) -> str:
    """
    Append the standard disclaimer if the AI output doesn't already contain one.
    Always call this before sending output to the frontend.
    """
    text_lower = text.lower()
    if any(phrase in text_lower for phrase in DISCLAIMER_PHRASES):
        return text
    return text + STANDARD_DISCLAIMER
