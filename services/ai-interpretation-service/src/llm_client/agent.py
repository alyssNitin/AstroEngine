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
import os
import re
import time
from typing import Any

from backend.config import ANTHROPIC_MODEL, AI_MAX_TOKENS

logger = logging.getLogger(__name__)

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
)
from backend.ai_interpretation.safety_filter import SafetyFilter
from backend.ai_interpretation.planet_calibrator import PlanetCalibrator, PlanetKnowledge

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

        prompt = PREDICTIONS_PROMPT.format(
            kundli_prompt=kundli_prompt,
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

        system = REFINE_SYSTEM.format(
            planet_knowledge=planet_knowledge.for_prompt(),
            language_instruction=lang_instr,
        ) + f"\n\nKundli data:\n{kundli_prompt}"

        messages = prior_messages + [{"role": "user", "content": refine_msg}]

        refined_text = self._call_claude(
            messages=messages,
            system=system,
            max_tokens=AI_MAX_TOKENS,
            caller="refine_with_feedback",
        )
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
        system = REFINE_SYSTEM.format(
            planet_knowledge=planet_knowledge.for_prompt(),
            language_instruction=lang_instr,
        ) + f"\n\nKundli data:\n{kundli_prompt}"
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

        yield {"type": "done", "full_text": full_text, "planet_knowledge": planet_knowledge}

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
        ) + f"\n\nKundli data:\n{kundli_prompt}"

        recent   = prior_messages[-max_history:]
        messages = recent + [{"role": "user", "content": user_message}]

        response = self._call_claude(
            messages=messages,
            system=system,
            max_tokens=8192,
            caller="chat",
        )
        return response, False

    # ── Private helpers ──────────────────────────────────────────────────────

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
            raise RuntimeError(
                "anthropic SDK not installed. Run: pip install anthropic"
            )
        client = anthropic.Anthropic(api_key=self._api_key)
        kwargs: dict[str, Any] = dict(
            model=ANTHROPIC_MODEL,
            max_tokens=max_tokens,
            messages=messages,
        )
        if system:
            kwargs["system"] = system

        t0 = time.perf_counter()
        resp = client.messages.create(**kwargs)
        elapsed = time.perf_counter() - t0

        # ── Token accounting & cost calculation ───────────────────────────────
        usage     = getattr(resp, "usage", None)
        in_tok    = getattr(usage, "input_tokens",  0) if usage else 0
        out_tok   = getattr(usage, "output_tokens", 0) if usage else 0
        call_cost = in_tok * _COST_PER_INPUT_TOKEN + out_tok * _COST_PER_OUTPUT_TOKEN

        # Accumulate into caller-tagged running total
        _session_costs[caller] = _session_costs.get(caller, 0.0) + call_cost
        total_so_far = sum(_session_costs.values())

        log_line = (
            f"[CLAUDE] fn={caller:<22} model={ANTHROPIC_MODEL} "
            f"in={in_tok:>5} out={out_tok:>5} tok  "
            f"cost=${call_cost:.5f}  total=${total_so_far:.5f}  "
            f"time={elapsed:.2f}s"
        )
        logger.info(log_line)
        print(log_line)          # also echo to terminal for dev visibility

        return resp.content[0].text

    @staticmethod
    def _parse_json(text: str) -> dict:
        """Robust JSON extractor: handles markdown fences, preamble text, trailing commas."""
        if not text:
            return {}
        # 1. Strip all markdown code fences (```json, ```, ~~~)
        cleaned = re.sub(r"```(?:json|JSON)?|~~~", "", text).strip()
        # 2. Try direct parse first (ideal case)
        try:
            _result = json.loads(cleaned)
            return _result if isinstance(_result, dict) else {}
        except json.JSONDecodeError:
            pass
        # 3. Find first '{' and last '}' to extract the JSON object
        start = cleaned.find('{')
        end   = cleaned.rfind('}')
        if start != -1 and end != -1 and end > start:
            candidate = cleaned[start:end + 1]
            try:
                return json.loads(candidate)
            except json.JSONDecodeError:
                # 4. Fix trailing commas before ] or } (common Claude quirk)
                fixed = re.sub(r',\s*([\]}])', r'\1', candidate)
                try:
                    return json.loads(fixed)
                except json.JSONDecodeError:
                    pass
        return {}

    def _parse_predictions(self, raw: str) -> dict:
        data = self._parse_json(raw)
        if not data or "predictions" not in data:
            return {
                "overall_theme": raw[:400] if raw else "Unable to generate predictions.",
                "predictions": [],
                "_raw": raw,
                "_parse_error": True,
            }
        return data
