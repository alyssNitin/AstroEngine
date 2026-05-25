"""
ai_interpretation/safety_filter.py
====================================
Guards against questions the system must not answer:
  1. Questions about children under MIN_CHILD_AGE_FOR_QUESTIONS years old
  2. Questions about future death timing (always blocked)
  3. Questions about past death timing (allowed with context)

All public methods are pure functions -- no I/O, easy to unit test.
"""
from __future__ import annotations
import re
from datetime import date

# Keyword patterns
_DEATH_KEYWORDS = re.compile(
    r"\b(death|die|dying|deceased|pass\s*away|lifespan|longevity|"
    r"marana|mrityu|end\s*of\s*life|how\s*long\s*(will|shall)\s*[iI]\s+live|"
    r"when\s+will\s+[iI]\s+die|when\s+am\s+[iI]\s+going\s+to\s+die)\b",
    re.IGNORECASE,
)

_PAST_DEATH_PATTERNS = re.compile(
    r"\b(died|passed\s*away|already\s*dead|late\s+(father|mother|husband|wife|"
    r"son|daughter|brother|sister)|deceased\s+(father|mother))\b",
    re.IGNORECASE,
)

_CHILD_QUESTION_PATTERNS = re.compile(
    r"\b(my\s+(baby|infant|toddler|child|son|daughter|kid|boy|girl)|"
    r"(for|about)\s+my\s+(child|baby|son|daughter|kid|boy|girl)|"
    r"(baby|infant|toddler|child|son|daughter|kid)\s+(is|are|will|who|that)|"
    r"(future|life|career|health|destiny)\s+of\s+my\s+(child|son|daughter|kid|baby)|"
    r"my\s+\d+\s+year\s+old\s+(son|daughter|child|baby|boy|girl|kid))\b",
    re.IGNORECASE,
)

_CHILD_WORDS = re.compile(
    r"\b(baby|infant|toddler|son|daughter|child|kid|boy|girl)\b",
    re.IGNORECASE,
)

# Possessive-age pattern: "my 2 year old", "our 18-month-old", "their 3 yr old", etc.
_POSSESSIVE_AGE = re.compile(
    r"\b(my|our|his|her|their)\s+\d+[\s-]*(year|yr|month|mon)s?[\s-]*(old)?\b",
    re.IGNORECASE,
)

_AGE_PATTERNS = re.compile(
    r"(\d+)\s*(year|yr|month|mon)s?\s*(old)?\b",
    re.IGNORECASE,
)

# Polite refusal messages
_CHILD_REFUSAL = (
    "For children under 5 years of age, their chart is still in a very formative phase -- "
    "planets haven't had enough time to manifest their full karaka results. "
    "I lovingly suggest revisiting this question once your child is a little older. "
    "In the meantime, I can share what their birth chart suggests about their overall nature "
    "and future potential."
)

_FUTURE_DEATH_REFUSAL = (
    "Classical Vedic astrology -- in its highest form -- is a tool for understanding life's "
    "purpose, not for predicting the timing of its end. Even the greatest Jyotishis of tradition "
    "advise against using the chart for this purpose. "
    "I am here to help you make the most of the life ahead -- shall we explore career, "
    "relationships, health, or spiritual growth instead?"
)


class FilterResult:
    """Returned by check_message(); carries block decision and reason."""
    __slots__ = ("blocked", "refusal_message", "reason")

    def __init__(self, blocked: bool, refusal_message: str = "", reason: str = "") -> None:
        self.blocked = blocked
        self.refusal_message = refusal_message
        self.reason = reason

    def __bool__(self) -> bool:
        return not self.blocked   # True = safe to answer


class SafetyFilter:
    """
    Stateless safety guard.  All methods are classmethods for easy import.
    """

    @classmethod
    def check_message(
        cls,
        message: str,
        user_profile: dict | None = None,
    ) -> FilterResult:
        """
        Main entry point.  Returns FilterResult.
          .blocked         -- True if we should NOT answer
          .refusal_message -- polite response to send instead
          .reason          -- internal reason code (for logging/tests)
        """
        # 1. Death check
        death_result = cls._check_death(message)
        if death_result.blocked:
            return death_result

        # 2. Young children check
        child_result = cls._check_young_child(message, user_profile)
        if child_result.blocked:
            return child_result

        return FilterResult(blocked=False)

    @classmethod
    def should_include_children_prompt(cls, marital_status: str) -> bool:
        """
        Returns True only if user is married (or widowed/divorced with possible children).
        Unmarried / single / in-relationship -- False.
        Empty / unknown -- True (include by default; let the user decide).
        """
        status = (marital_status or "").lower()
        NOT_MARRIED = {"single", "unmarried", "not married", "no", "bachelor",
                       "in a relationship", "dating", "engaged"}
        MARRIED = {"married", "widowed", "divorced", "separated", "yes"}

        for kw in NOT_MARRIED:
            if kw in status:
                return False
        for kw in MARRIED:
            if kw in status:
                return True
        # Default: include (unknown status -- do not skip prediction)
        return True

    @classmethod
    def is_past_death_question(cls, message: str) -> bool:
        """Returns True if question is about someone who has ALREADY died."""
        return bool(_PAST_DEATH_PATTERNS.search(message))

    @classmethod
    def is_future_death_question(cls, message: str) -> bool:
        """Returns True if question is about future death prediction."""
        return (bool(_DEATH_KEYWORDS.search(message))
                and not cls.is_past_death_question(message))

    @classmethod
    def extract_child_age_from_message(cls, message: str) -> int | None:
        """
        Try to extract an age value from text like "3 year old", "18 months", etc.
        Returns age in years (rounded down), or None if not found.
        """
        match = _AGE_PATTERNS.search(message)
        if not match:
            return None
        num = int(match.group(1))
        unit = match.group(2).lower()
        if "month" in unit or "mon" in unit:
            return num // 12
        return num

    # ── Private helpers ──────────────────────────────────────────

    @classmethod
    def _check_death(cls, message: str) -> FilterResult:
        if not _DEATH_KEYWORDS.search(message):
            return FilterResult(blocked=False)

        if cls.is_past_death_question(message):
            # Past death -- allow but mark as sensitive
            return FilterResult(blocked=False, reason="past_death_allowed")

        # Future death -- always block
        return FilterResult(
            blocked=True,
            refusal_message=_FUTURE_DEATH_REFUSAL,
            reason="future_death_blocked",
        )

    @classmethod
    def _check_young_child(
        cls, message: str, user_profile: dict | None
    ) -> FilterResult:
        from backend.config import MIN_CHILD_AGE_FOR_QUESTIONS

        # Step 1: Extract age mentioned in message
        age = cls.extract_child_age_from_message(message)

        # Step 2: If age < threshold AND the message is clearly about a child, block
        if age is not None and age < MIN_CHILD_AGE_FOR_QUESTIONS:
            is_child_context = (
                _CHILD_WORDS.search(message)
                or _CHILD_QUESTION_PATTERNS.search(message)
                or _POSSESSIVE_AGE.search(message)
            )
            if is_child_context:
                return FilterResult(
                    blocked=True,
                    refusal_message=_CHILD_REFUSAL,
                    reason=f"child_age_{age}_too_young",
                )

        # Step 3: If no explicit child-question pattern, allow
        if not _CHILD_QUESTION_PATTERNS.search(message):
            return FilterResult(blocked=False)

        # Step 4: Pattern matched but age not extracted from message --
        #         fall back to user profile for stored child ages.
        if user_profile:
            # Support both profile structures:
            #   {"children_info": {"ages": [2, 5]}}  (legacy)
            #   {"children": [{"age": 2}, {"age": 5}]}  (new API shape)
            profile_ages: list[int] = []

            children_info = user_profile.get("children_info", {})
            if isinstance(children_info, dict):
                profile_ages.extend(children_info.get("ages", []))

            children_list = user_profile.get("children", [])
            if isinstance(children_list, list):
                profile_ages.extend(
                    c["age"] for c in children_list
                    if isinstance(c, dict) and c.get("age") is not None
                )

            if profile_ages and min(profile_ages) < MIN_CHILD_AGE_FOR_QUESTIONS:
                return FilterResult(
                    blocked=True,
                    refusal_message=_CHILD_REFUSAL,
                    reason="profile_child_age_too_young",
                )

        return FilterResult(blocked=False)
