"""
ai_interpretation/agent.py
===========================
Orchestrates the full AI interpretation flow:
  Step 1: generate_predictions() -- 7-8 life-domain predictions, conditional on profile
  Step 2: refine_with_feedback() -- deep analysis after user confirms/corrects
  Step 3: chat()                 -- ongoing Q&A with safety filter + planet calibration
"""
from __future__ import annotations
import json
import logging
from backend.core.logging import get_logger
import os
import re
import time
from typing import Any

from backend.config import ANTHROPIC_MODEL, AI_MAX_TOKENS

logger = get_logger(__name__)

# ── Cost constants for claude-sonnet-4-6 ─────────────────────────────────────
# Pricing: https://www.anthropic.com/pricing
_COST_PER_INPUT_TOKEN  = 3.00 / 1_000_000   # $3.00 per million input tokens
_COST_PER_OUTPUT_TOKEN = 15.00 / 1_000_000  # $15.00 per million output tokens

# ── Session-level cost accumulator (module-level, reset on server restart) ───
_session_costs: dict[str, float] = {}  # {session_tag: cumulative_usd}
from backend.ai_interpretation.prompts import (
    SYSTEM_ASTROLOGER, PREDICTIONS_PROMPT, CHILDREN_BLOCK_INCLUDE,
    CHILDREN_BLOCK_EXCLUDE, REFINE_SYSTEM, CHAT_SYSTEM,
    SAFETY_REMINDER_DEFAULT, PLANET_CALIBRATION_PROMPT, LANGUAGE_INSTRUCTION,
    CAREER_SYSTEM, CAREER_REPORT_PROMPT,
    COMPATIBILITY_SYSTEM, COMPATIBILITY_REPORT_PROMPT,
    DASHA_NARRATIVE_PROMPT,
)
from backend.ai_interpretation.safety_filter import SafetyFilter
from backend.ai_interpretation.planet_calibrator import PlanetCalibrator, PlanetKnowledge
from backend.ai_interpretation.pii_scrubber import scrub_prompt
from backend.ai_interpretation.output_validator import validate_ai_output, ensure_disclaimer

DEFAULT_LANGUAGE = "English"


class AstroAgent:
    """Stateless AI agent -- sessions are managed by the API layer."""

    def __init__(self, api_key: str | None = None) -> None:
        # Read lazily so tests can set os.environ before instantiation
        self._api_key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
        if not self._api_key:
            raise ValueError(
                "Anthropic API key not found. "
                "Set ANTHROPIC_API_KEY in your .env file."
            )

    # Step 1 -- Initial predictions

    def generate_predictions(
        self,
        kundli_prompt: str,
        marital_status: str = "",
        language: str = DEFAULT_LANGUAGE,
    ) -> dict:
        """
        Call Claude to produce structured life predictions.
        Conditionally includes or excludes the children prompt based on marital status.
        Responds in the requested language.
        """
        include_children = SafetyFilter.should_include_children_prompt(marital_status)
        children_block   = CHILDREN_BLOCK_INCLUDE if include_children else CHILDREN_BLOCK_EXCLUDE

        conditional_instructions = ""
        if not include_children:
            conditional_instructions = (
                "NOTE: The user has indicated they are NOT married. "
                "Do NOT include a children prediction. "
                "Omit the children block entirely from the predictions array."
            )

        lang_instr = LANGUAGE_INSTRUCTION.format(language=language) if language != DEFAULT_LANGUAGE else ""

        # Scrub PII before sending to LLM
        safe_kundli_prompt = scrub_prompt(kundli_prompt)

        prompt = PREDICTIONS_PROMPT.format(
            kundli_prompt=safe_kundli_prompt,
            children_block=children_block,
            conditional_instructions=conditional_instructions,
            language_instruction=lang_instr,
        )

        raw = self._call_claude(
            messages=[{"role": "user", "content": prompt}],
            system=SYSTEM_ASTROLOGER,
            max_tokens=8192,
            caller="generate_predictions",
        )
        result = self._parse_predictions(raw)

        # Auto-retry once if JSON parsing failed
        if result.get("_parse_error"):
            retry_prompt = (
                "Your previous response could not be parsed as JSON. "
                "Reply with ONLY the raw JSON object — no explanation, no markdown fences, "
                "no text before or after. Start your response with { and end with }."
            )
            raw2 = self._call_claude(
                messages=[
                    {"role": "user", "content": prompt},
                    {"role": "assistant", "content": raw},
                    {"role": "user", "content": retry_prompt},
                ],
                system=SYSTEM_ASTROLOGER,
                max_tokens=8192,
                caller="generate_predictions_retry",
            )
            result = self._parse_predictions(raw2)

        return result

    # Step 2 -- Refine with user feedback + planet calibration

    def refine_with_feedback(
        self,
        kundli: dict,
        kundli_prompt: str,
        corrections: dict,
        prior_messages: list[dict],
        language: str = DEFAULT_LANGUAGE,
    ) -> tuple[str, PlanetKnowledge]:
        """
        Accepts user confirmations/corrections.
        Returns (refined_analysis_text, planet_knowledge).
        """
        # 1. Build planet calibration (rule-based, fast)
        planet_knowledge = PlanetCalibrator.calibrate_from_feedback(corrections, kundli)

        # 2. Optionally enrich calibration via Claude
        try:
            cal_prompt = PLANET_CALIBRATION_PROMPT.format(
                kundli_prompt=kundli_prompt,
                feedback=json.dumps(corrections, indent=2),
            )
            cal_raw = self._call_claude(
                messages=[{"role": "user", "content": cal_prompt}],
                max_tokens=800,
                caller="planet_calibration",
            )
            llm_cal = self._parse_json(cal_raw)
            planet_knowledge = PlanetCalibrator.calibrate_from_feedback(
                corrections, kundli, llm_calibration=llm_cal
            )
        except Exception:
            pass   # Fallback to rule-based calibration

        # 3. Build correction summary for Claude
        correction_lines = [f"  * {k.upper()}: {v}" for k, v in corrections.items()]
        refine_msg = (
            "Here is the user's feedback on your initial predictions:\n\n"
            + "\n".join(correction_lines)
            + "\n\nNow provide the deep personalised analysis as described in your instructions."
        )

        lang_instr = LANGUAGE_INSTRUCTION.format(language=language) if language != DEFAULT_LANGUAGE else ""

        # Scrub PII before including kundli data in system prompt
        safe_kundli_prompt = scrub_prompt(kundli_prompt)

        system = REFINE_SYSTEM.format(
            planet_knowledge=planet_knowledge.for_prompt(),
            language_instruction=lang_instr,
        ) + f"\n\nKundli data:\n{safe_kundli_prompt}"

        messages = prior_messages + [{"role": "user", "content": refine_msg}]

        refined_text = self._call_claude(
            messages=messages,
            system=system,
            max_tokens=AI_MAX_TOKENS,
            caller="refine_with_feedback",
        )

        # Deterministic output validation
        val = validate_ai_output(refined_text, kundli, report_type="personal")
        refined_text = ensure_disclaimer(refined_text)
        if val.has_errors:
            logger.error("[refine_with_feedback] validation errors: %s", val.errors)

        return refined_text, planet_knowledge

    # Step 2b -- Streaming refine (solves browser timeout for long Claude calls)

    def stream_refine(
        self,
        kundli: dict,
        kundli_prompt: str,
        corrections: dict,
        prior_messages: list[dict],
        language: str = DEFAULT_LANGUAGE,
    ):
        """
        Generator version of refine_with_feedback.
        Yields dicts:
          {"type": "chunk",   "text": "<partial text>"}
          {"type": "done",    "full_text": "...", "planet_knowledge": PlanetKnowledge}
          {"type": "error",   "message": "..."}
        """
        # 1. Planet calibration (fast, non-streaming)
        planet_knowledge = PlanetCalibrator.calibrate_from_feedback(corrections, kundli)
        try:
            cal_prompt = PLANET_CALIBRATION_PROMPT.format(
                kundli_prompt=kundli_prompt,
                feedback=json.dumps(corrections, indent=2),
            )
            cal_raw = self._call_claude(
                messages=[{"role": "user", "content": cal_prompt}],
                max_tokens=800,
                caller="planet_calibration",
            )
            llm_cal = self._parse_json(cal_raw)
            planet_knowledge = PlanetCalibrator.calibrate_from_feedback(
                corrections, kundli, llm_calibration=llm_cal
            )
        except Exception:
            pass  # Fallback to rule-based calibration

        # 2. Build messages for refine
        correction_lines = [f"  * {k.upper()}: {v}" for k, v in corrections.items()]
        refine_msg = (
            "Here is the user's feedback on your initial predictions:\n\n"
            + "\n".join(correction_lines)
            + "\n\nNow provide the deep personalised analysis as described in your instructions."
        )
        lang_instr = LANGUAGE_INSTRUCTION.format(language=language) if language != DEFAULT_LANGUAGE else ""
        # Scrub PII before including kundli data in system prompt
        safe_kundli_prompt = scrub_prompt(kundli_prompt)
        system = REFINE_SYSTEM.format(
            planet_knowledge=planet_knowledge.for_prompt(),
            language_instruction=lang_instr,
        ) + f"\n\nKundli data:\n{safe_kundli_prompt}"
        messages = prior_messages + [{"role": "user", "content": refine_msg}]

        # 3. Stream Claude's response
        try:
            import anthropic
        except ImportError:
            yield {"type": "error", "message": "anthropic SDK not installed"}
            return

        client = anthropic.Anthropic(api_key=self._api_key)
        full_text = ""
        t0 = time.perf_counter()
        in_tok = out_tok = 0

        try:
            with client.messages.stream(
                model=ANTHROPIC_MODEL,
                max_tokens=AI_MAX_TOKENS,
                system=system,
                messages=messages,
            ) as stream:
                for text_chunk in stream.text_stream:
                    full_text += text_chunk
                    yield {"type": "chunk", "text": text_chunk}

                # Capture final usage after stream completes
                final_msg = stream.get_final_message()
                usage  = getattr(final_msg, "usage", None)
                in_tok  = getattr(usage, "input_tokens",  0) if usage else 0
                out_tok = getattr(usage, "output_tokens", 0) if usage else 0

        except Exception as exc:
            yield {"type": "error", "message": str(exc)}
            return

        elapsed   = time.perf_counter() - t0
        call_cost = in_tok * _COST_PER_INPUT_TOKEN + out_tok * _COST_PER_OUTPUT_TOKEN
        _session_costs["stream_refine"] = _session_costs.get("stream_refine", 0.0) + call_cost
        total_so_far = sum(_session_costs.values())
        log_line = (
            f"[CLAUDE] fn=stream_refine          model={ANTHROPIC_MODEL} "
            f"in={in_tok:>5} out={out_tok:>5} tok  "
            f"cost=${call_cost:.5f}  total=${total_so_far:.5f}  "
            f"time={elapsed:.2f}s"
        )
        logger.info(log_line)
        print(log_line)

        # Deterministic output validation + ensure disclaimer
        val = validate_ai_output(full_text, kundli, report_type="personal")
        full_text = ensure_disclaimer(full_text)
        if val.has_errors:
            logger.error("[stream_refine] validation errors: %s", val.errors)

        yield {
            "type": "done",
            "full_text": full_text,
            "planet_knowledge": planet_knowledge,
            "validation": val.to_dict(),
        }

    # Step 3 -- Ongoing chat

    def chat(
        self,
        user_message: str,
        kundli_prompt: str,
        prior_messages: list[dict],
        planet_knowledge: PlanetKnowledge | None = None,
        user_profile: dict | None = None,
        max_history: int = 10,
        language: str = DEFAULT_LANGUAGE,
    ) -> tuple[str, bool]:
        """
        Answer a free-form user question.
        Returns (response_text, was_blocked_by_safety).
        Applies safety filter before calling Claude.
        """
        result = SafetyFilter.check_message(user_message, user_profile)
        if result.blocked:
            return result.refusal_message, True

        pk_str = planet_knowledge.for_prompt() if planet_knowledge else "No calibration yet."
        lang_instr = LANGUAGE_INSTRUCTION.format(language=language) if language != DEFAULT_LANGUAGE else ""

        system = CHAT_SYSTEM.format(
            planet_knowledge=pk_str,
            safety_reminder=SAFETY_REMINDER_DEFAULT,
            language_instruction=lang_instr,
        ) + f"\n\nKundli data:\n{scrub_prompt(kundli_prompt)}"

        recent   = prior_messages[-max_history:]
        messages = recent + [{"role": "user", "content": user_message}]

        response = self._call_claude(
            messages=messages,
            system=system,
            max_tokens=8192,
            caller="chat",
        )
        return response, False

    # ── Career Report ────────────────────────────────────────────────────────

    def generate_career_report(
        self,
        kundli_prompt: str,
        refined_analysis: str = "",
        language: str = DEFAULT_LANGUAGE,
    ) -> str:
        """
        Generate a deep career guidance report using D10 and 10th house analysis.

        Returns the full report as a plain-text string (Markdown-safe).
        """
        lang_instr = LANGUAGE_INSTRUCTION.format(language=language) if language != DEFAULT_LANGUAGE else ""
        system  = CAREER_SYSTEM.format(language_instruction=lang_instr)
        prompt  = CAREER_REPORT_PROMPT.format(
            kundli_prompt=kundli_prompt,
            refined_analysis=refined_analysis or "(Deep reading not yet available)",
            language_instruction=lang_instr,
        )
        return self._call_claude(
            messages=[{"role": "user", "content": prompt}],
            system=system,
            max_tokens=AI_MAX_TOKENS,
            caller="career_report",
        )

    def stream_career_report(
        self,
        kundli_prompt: str,
        refined_analysis: str = "",
        language: str = DEFAULT_LANGUAGE,
    ):
        """Streaming version of the career report (SSE-compatible generator)."""
        lang_instr = LANGUAGE_INSTRUCTION.format(language=language) if language != DEFAULT_LANGUAGE else ""
        system  = CAREER_SYSTEM.format(language_instruction=lang_instr)
        prompt  = CAREER_REPORT_PROMPT.format(
            kundli_prompt=kundli_prompt,
            refined_analysis=refined_analysis or "(Deep reading not yet available)",
            language_instruction=lang_instr,
        )
        yield from self._stream_claude(
            messages=[{"role": "user", "content": prompt}],
            system=system,
            max_tokens=AI_MAX_TOKENS,
            caller="career_report_stream",
        )

    # ── Compatibility Report ─────────────────────────────────────────────────

    def generate_compatibility_report(
        self,
        person1_kundli: str,
        person2_kundli: str,
        language: str = DEFAULT_LANGUAGE,
    ) -> str:
        """
        Generate a Vedic compatibility (Kundli Milan) report for two birth charts.

        Returns the full report as a plain-text string.
        """
        lang_instr = LANGUAGE_INSTRUCTION.format(language=language) if language != DEFAULT_LANGUAGE else ""
        system  = COMPATIBILITY_SYSTEM.format(language_instruction=lang_instr)
        prompt  = COMPATIBILITY_REPORT_PROMPT.format(
            person1_kundli=person1_kundli,
            person2_kundli=person2_kundli,
            language_instruction=lang_instr,
        )
        return self._call_claude(
            messages=[{"role": "user", "content": prompt}],
            system=system,
            max_tokens=AI_MAX_TOKENS,
            caller="compatibility_report",
        )

    def stream_compatibility_report(
        self,
        person1_kundli: str,
        person2_kundli: str,
        language: str = DEFAULT_LANGUAGE,
    ):
        """Streaming version of compatibility report."""
        lang_instr = LANGUAGE_INSTRUCTION.format(language=language) if language != DEFAULT_LANGUAGE else ""
        system  = COMPATIBILITY_SYSTEM.format(language_instruction=lang_instr)
        prompt  = COMPATIBILITY_REPORT_PROMPT.format(
            person1_kundli=person1_kundli,
            person2_kundli=person2_kundli,
            language_instruction=lang_instr,
        )
        yield from self._stream_claude(
            messages=[{"role": "user", "content": prompt}],
            system=system,
            max_tokens=AI_MAX_TOKENS,
            caller="compatibility_report_stream",
        )

    # ── Dasha Narrative ──────────────────────────────────────────────────────

    def generate_dasha_narrative(
        self,
        kundli_prompt: str,
        dasha_data: str,
        language: str = DEFAULT_LANGUAGE,
    ) -> str:
        """Convert raw dasha timeline data into a personalised narrative."""
        lang_instr = LANGUAGE_INSTRUCTION.format(language=language) if language != DEFAULT_LANGUAGE else ""
        prompt = DASHA_NARRATIVE_PROMPT.format(
            dasha_data=dasha_data,
            kundli_prompt=kundli_prompt,
            language_instruction=lang_instr,
        )
        return self._call_claude(
            messages=[{"role": "user", "content": prompt}],
            system=SYSTEM_ASTROLOGER,
            max_tokens=AI_MAX_TOKENS,
            caller="dasha_narrative",
        )

    # ── Private helpers ──────────────────────────────────────────────────────

    def _stream_claude(
        self,
        messages: list[dict],
        system: str = "",
        max_tokens: int = 8192,
        caller: str = "unknown",
    ):
        """
        Generic streaming Claude generator.
        Yields dicts:
          {"type": "chunk", "text": "<partial text>"}
          {"type": "done",  "full_text": "..."}
          {"type": "error", "message": "..."}
        """
        try:
            import anthropic
        except ImportError:
            yield {"type": "error", "message": "anthropic SDK not installed"}
            return

        client    = anthropic.Anthropic(api_key=self._api_key)
        full_text = ""
        t0        = time.perf_counter()
        in_tok = out_tok = 0

        try:
            kwargs = dict(model=ANTHROPIC_MODEL, max_tokens=max_tokens, messages=messages)
            if system:
                kwargs["system"] = system

            with client.messages.stream(**kwargs) as stream:
                for text_chunk in stream.text_stream:
                    full_text += text_chunk
                    yield {"type": "chunk", "text": text_chunk}

                final_msg = stream.get_final_message()
                usage   = getattr(final_msg, "usage", None)
                in_tok  = getattr(usage, "input_tokens",  0) if usage else 0
                out_tok = getattr(usage, "output_tokens", 0) if usage else 0

        except Exception as exc:
            yield {"type": "error", "message": str(exc)}
            return

        elapsed   = time.perf_counter() - t0
        call_cost = in_tok * _COST_PER_INPUT_TOKEN + out_tok * _COST_PER_OUTPUT_TOKEN
        _session_costs[caller] = _session_costs.get(caller, 0.0) + call_cost
        log_line  = (
            f"[CLAUDE] fn={caller:<25} model={ANTHROPIC_MODEL} "
            f"in={in_tok:>5} out={out_tok:>5} tok  "
            f"cost=${call_cost:.5f}  time={elapsed:.2f}s"
        )
        logger.info(log_line)
        print(log_line)
        yield {"type": "done", "full_text": full_text}

    def _call_claude(
        self,
        messages: list[dict],
        system: str = "",
        max_tokens: int = 8192,
        caller: str = "unknown",
    ) -> str:
        try:
            import anthropic
        except ImportError:
            raise RuntimeError("anthropic SDK not installed. Run: pip install anthropic")
        client = anthropic.Anthropic(api_key=self._api_key)
        kwargs: dict[str, Any] = dict(
            model=ANTHROPIC_MODEL,
            max_tokens=max_tokens,
            messages=messages,
        )
        if system:
            kwargs["system"] = system

        # B6: AI response caching — check cache before calling LLM
        # Cache key uses the full messages payload + system prompt
        _cache_key_data = {"messages": messages, "system": system or "", "model": ANTHROPIC_MODEL}
        _report_type    = caller
        _language       = "English"  # extracted from messages if present
        try:
            from backend.cache.redis_cache import get_ai_response_cached, set_ai_response_cache
            _cached = get_ai_response_cached(_cache_key_data, _report_type, _language)
            if _cached:
                logger.info("[CLAUDE] Cache HIT for fn=%s — skipping LLM call", caller)
                return _cached
        except Exception:
            pass   # Cache unavailable — proceed to LLM

        t0   = time.perf_counter()
        resp = client.messages.create(**kwargs)
        elapsed = time.perf_counter() - t0

        usage     = getattr(resp, "usage", None)
        in_tok    = getattr(usage, "input_tokens",  0) if usage else 0
        out_tok   = getattr(usage, "output_tokens", 0) if usage else 0
        call_cost = in_tok * _COST_PER_INPUT_TOKEN + out_tok * _COST_PER_OUTPUT_TOKEN
        _session_costs[caller] = _session_costs.get(caller, 0.0) + call_cost
        total_so_far = sum(_session_costs.values())
        log_line = (
            f"[CLAUDE] fn={caller:<25} model={ANTHROPIC_MODEL} "
            f"in={in_tok:>5} out={out_tok:>5} tok  "
            f"cost=${call_cost:.5f}  total=${total_so_far:.5f}  "
            f"time={elapsed:.2f}s"
        )
        logger.info(log_line)
        print(log_line)

        content = resp.content
        result_text = content[0].text if content and hasattr(content[0], "text") else ""

        # B6: Store result in cache for future identical requests
        if result_text:
            try:
                from backend.cache.redis_cache import set_ai_response_cache
                set_ai_response_cache(_cache_key_data, _report_type, _language, result_text)
            except Exception:
                pass

        return result_text

    def _parse_predictions(self, raw: str) -> dict:
        """
        Safely parse a Claude predictions response.

        On success: returns the parsed dict (must contain 'predictions' list).
        On failure: returns {"_parse_error": True, "_raw": raw} so the caller
        can auto-retry or refund the user — never raises.

        This wraps _parse_json which raises ValueError on bad JSON.
        """
        try:
            result = self._parse_json(raw)
            # Ensure the mandatory 'predictions' key exists
            if not isinstance(result, dict):
                return {"_parse_error": True, "_raw": raw}
            if "predictions" not in result:
                # Claude sometimes returns a top-level list instead of a dict
                if isinstance(result, list):
                    return {"predictions": result, "overall_theme": ""}
                return {"_parse_error": True, "_raw": raw}
            return result
        except Exception as exc:  # noqa: BLE001
            import logging as _log
            _log.getLogger(__name__).warning(
                "AstroAgent._parse_predictions: JSON parse failed — %s | raw[:200]=%s",
                exc, raw[:200],
            )
            return {"_parse_error": True, "_raw": raw}

    def _parse_json(self, raw: str) -> dict:
        """Extract and parse the first JSON object from a Claude response."""
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            pass
        # Strip markdown code fences
        cleaned = re.sub(r"```(?:json)?", "", raw).strip()
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            pass
        # Find first { ... } block
        m = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if m:
            try:
                return json.loads(m.group())
            except json.JSONDecodeError:
                pass
        raise ValueError(f"Could not parse JSON from Claude response: {raw[:200]}")

    # ── Yearly Forecast ──────────────────────────────────────────────────────

    def stream_yearly_forecast(self, profile: dict, year: int | None = None, language: str = "English"):
        """
        Generate a 12-month Vedic yearly forecast using Dasha/Antardasha and
        transits. Returns an SSE-compatible streaming generator.
        """
        import datetime as _dt
        yr = year or _dt.datetime.now().year
        name = profile.get("name", "the native")
        dob  = profile.get("date_of_birth", "")
        kundli = profile.get("kundli_json", {})
        dasha  = profile.get("predictions_json", {}).get("dasha", {})

        system = (
            "You are a highly experienced Vedic astrologer. "
            "Provide a comprehensive, month-by-month yearly forecast based on "
            "Dasha/Antardasha periods, planetary transits, and the natal chart. "
            "Be specific, practical, and encouraging. "
            "AI-generated astrological guidance is for entertainment and self-reflection only."
        )
        prompt = (
            f"Generate a detailed Vedic astrology yearly forecast for {name} for the year {yr}.\n"
            f"Date of birth: {dob}\n"
            f"Current Dasha/Antardasha: {json.dumps(dasha, ensure_ascii=False)[:800]}\n"
            f"Key chart data: {json.dumps(kundli, ensure_ascii=False)[:1200]}\n\n"
            f"Please provide:\n"
            f"1. Overall theme for {yr}\n"
            f"2. Month-by-month forecast (January to December)\n"
            f"3. Key dates/periods to watch\n"
            f"4. Focus areas: Career, Finance, Relationships, Health, Spiritual\n"
            f"Respond in {language}."
        )
        return self._stream_claude(
            messages=[{"role": "user", "content": prompt}],
            system=system,
            max_tokens=8192,
            caller="yearly_forecast",
        )

    # ── Vedic Remedies ───────────────────────────────────────────────────────

    def stream_remedies_report(self, profile: dict, area: str = "general", language: str = "English"):
        """
        Generate Vedic remedies tailored to the user's chart and requested area.
        area: "general" | "career" | "health" | "relationships" | "finance"
        Returns an SSE-compatible streaming generator.
        """
        name    = profile.get("name", "the native")
        dob     = profile.get("date_of_birth", "")
        kundli  = profile.get("kundli_json", {})
        planets = kundli.get("planets", [])
        weak    = [p["name"] for p in planets if p.get("strength") == "weak"] if planets else []

        system = (
            "You are an expert Vedic astrologer specialising in practical remedies "
            "(Upayas). Provide actionable, traditional, and modern Vedic remedies. "
            "Include mantras, gemstones, colours, days, charity, and lifestyle changes. "
            "Always note these are traditional suggestions, not medical/financial advice."
        )
        weak_str = ", ".join(weak) or "none identified"
        prompt = (
            f"Generate detailed Vedic astrological remedies for {name}.\n"
            f"Date of birth: {dob}\n"
            f"Area of focus: {area}\n"
            f"Weak planets (if any): {weak_str}.\n"
            f"Chart summary: {json.dumps(kundli, ensure_ascii=False)[:1000]}\n\n"
            f"Please provide remedies organised as:\n"
            f"1. Primary remedies for the focus area\n"
            f"2. Mantras and their recitation schedule\n"
            f"3. Gemstone / crystal recommendations\n"
            f"4. Colour therapy and auspicious days\n"
            f"5. Charity and service suggestions\n"
            f"6. Lifestyle and dietary guidance\n"
            f"7. Yantra or puja recommendations\n"
            f"Respond in {language}. Mark as guidance only, not medical advice."
        )
        return self._stream_claude(
            messages=[{"role": "user", "content": prompt}],
            system=system,
            max_tokens=6144,
            caller="remedies_report",
        )
