"""
test_ai_agent.py
================
Unit tests for AstroAgent — uses mocked Claude calls so no API key required.
Covers TC-AI-001 through TC-AI-008 from the spec.
"""
import sys, os, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import unittest
from unittest.mock import patch, MagicMock
from backend.ai_interpretation.agent import AstroAgent
from backend.ai_interpretation.safety_filter import SafetyFilter
from backend.ai_interpretation.planet_calibrator import PlanetKnowledge
from backend.kundli_engine.engine import KundliEngine

STUB_KUNDLI = KundliEngine().stub_kundli()

MOCK_PREDICTION_JSON = json.dumps({
    "overall_theme": "A life of intellectual exploration and service.",
    "predictions": [
        {"id": "education",     "category": "Education & Learning",   "emoji": "📚",
         "statement": "Mercury in Gemini indicates strong analytical mind — likely engineering or sciences.",
         "question": "Does this match your educational background?"},
        {"id": "career",        "category": "Career & Profession",    "emoji": "💼",
         "statement": "Saturn in 10th drives disciplined, structured career — IT or administration.",
         "question": "What is your current profession?"},
        {"id": "marriage",      "category": "Relationship & Marriage","emoji": "💑",
         "statement": "Venus in Cancer indicates emotional bond in marriage.",
         "question": "What is your current relationship status?"},
        {"id": "health",        "category": "Health & Vitality",       "emoji": "🏥",
         "statement": "6th house Virgo indicates digestive sensitivity.",
         "question": "Have you had digestive health issues?"},
        {"id": "current_phase", "category": "Current Life Phase",      "emoji": "⏳",
         "statement": "Jupiter mahadasha from 2024 brings expansion.",
         "question": "Does this describe your current life?"},
        {"id": "finances",      "category": "Wealth & Finances",       "emoji": "💰",
         "statement": "Jupiter in Cancer indicates steady wealth accumulation.",
         "question": "Does your financial situation match this?"},
        {"id": "spirituality",  "category": "Spiritual Path",          "emoji": "🪔",
         "statement": "Ketu in Cancer indicates past-life spiritual depth.",
         "question": "Do you have strong spiritual inclinations?"},
    ]
})

MOCK_REFINED = "Your chart reveals a deeply analytical mind guided by Mercury in Gemini...\n\nJupiter in Cancer brings natural wisdom..."

MOCK_CHAT   = "Based on your current Jupiter mahadasha, the next 3 years are excellent for career growth..."

MOCK_CAL    = json.dumps({
    "active_planets": [{"planet": "Jupiter", "domain": "education", "reason": "confirmed"}],
    "inactive_or_misread": [],
    "summary": "Jupiter is giving strong results"
})


def _make_agent() -> AstroAgent:
    """Create agent with dummy key — actual calls are mocked."""
    os.environ["ANTHROPIC_API_KEY"] = "sk-ant-test-key-000000000000000000000000"
    return AstroAgent()


class TestAgentPredictions(unittest.TestCase):

    @patch("backend.ai_interpretation.agent.AstroAgent._call_claude",
           return_value=MOCK_PREDICTION_JSON)
    def test_generate_predictions_returns_dict(self, _mock):
        agent = _make_agent()
        result = agent.generate_predictions("KUNDLI DATA HERE", marital_status="married")
        self.assertIsInstance(result, dict)

    @patch("backend.ai_interpretation.agent.AstroAgent._call_claude",
           return_value=MOCK_PREDICTION_JSON)
    def test_predictions_has_seven_domains_for_married(self, _mock):
        agent = _make_agent()
        result = agent.generate_predictions("KUNDLI", marital_status="married")
        ids = [p["id"] for p in result.get("predictions", [])]
        for expected in ["education", "career", "marriage", "health", "current_phase",
                         "finances", "spirituality"]:
            self.assertIn(expected, ids, f"Missing prediction id: {expected}")

    @patch("backend.ai_interpretation.agent.AstroAgent._call_claude",
           return_value=MOCK_PREDICTION_JSON)
    def test_overall_theme_present(self, _mock):
        agent = _make_agent()
        result = agent.generate_predictions("KUNDLI", marital_status="single")
        self.assertIn("overall_theme", result)
        self.assertGreater(len(result["overall_theme"]), 10)

    @patch("backend.ai_interpretation.agent.AstroAgent._call_claude",
           return_value=MOCK_PREDICTION_JSON)
    def test_each_prediction_has_required_fields(self, _mock):
        agent = _make_agent()
        result = agent.generate_predictions("KUNDLI", marital_status="married")
        for pred in result["predictions"]:
            with self.subTest(id=pred["id"]):
                self.assertIn("id",        pred)
                self.assertIn("category",  pred)
                self.assertIn("statement", pred)
                self.assertIn("question",  pred)
                self.assertIn("emoji",     pred)

    @patch("backend.ai_interpretation.agent.AstroAgent._call_claude",
           return_value="{invalid json}")
    def test_malformed_json_returns_fallback(self, _mock):
        agent = _make_agent()
        result = agent.generate_predictions("KUNDLI", marital_status="married")
        # Must not crash — returns graceful fallback
        self.assertIsInstance(result, dict)
        self.assertIn("overall_theme", result)


class TestConditionalChildrenPrediction(unittest.TestCase):
    """Children prediction must be absent when user is unmarried."""

    @patch("backend.ai_interpretation.agent.AstroAgent._call_claude",
           return_value=MOCK_PREDICTION_JSON)
    def test_children_absent_for_single(self, mock_call):
        agent = _make_agent()
        agent.generate_predictions("KUNDLI", marital_status="single")
        # Verify prompt contains instruction to omit children
        call_args = mock_call.call_args
        prompt_sent = str(call_args)
        self.assertIn("NOT married", prompt_sent,
                      "Prompt should instruct Claude to omit children for unmarried user")

    @patch("backend.ai_interpretation.agent.AstroAgent._call_claude",
           return_value=MOCK_PREDICTION_JSON)
    def test_children_prompt_included_for_married(self, mock_call):
        agent = _make_agent()
        agent.generate_predictions("KUNDLI", marital_status="married")
        call_args = mock_call.call_args
        prompt_sent = str(call_args)
        self.assertNotIn("NOT married", prompt_sent)


class TestAgentRefine(unittest.TestCase):

    @patch("backend.ai_interpretation.agent.AstroAgent._call_claude")
    def test_refine_returns_text_and_planet_knowledge(self, mock_call):
        mock_call.side_effect = [MOCK_CAL, MOCK_REFINED]
        agent = _make_agent()
        corrections = {
            "education": "Confirmed — I studied engineering",
            "career":    "Confirmed — IT sector",
        }
        refined_text, pk = agent.refine_with_feedback(
            kundli=STUB_KUNDLI,
            kundli_prompt="COMPACT KUNDLI",
            corrections=corrections,
            prior_messages=[
                {"role": "user", "content": "Analyse my chart"},
                {"role": "assistant", "content": MOCK_PREDICTION_JSON},
            ],
        )
        self.assertIsInstance(refined_text, str)
        self.assertGreater(len(refined_text), 10)
        self.assertIsInstance(pk, PlanetKnowledge)

    @patch("backend.ai_interpretation.agent.AstroAgent._call_claude")
    def test_refine_calibrates_active_planets(self, mock_call):
        mock_call.side_effect = [MOCK_CAL, MOCK_REFINED]
        agent = _make_agent()
        _, pk = agent.refine_with_feedback(
            kundli=STUB_KUNDLI,
            kundli_prompt="KUNDLI",
            corrections={"education": "Confirmed — engineering"},
            prior_messages=[],
        )
        self.assertGreater(len(pk.active), 0, "Should have at least one active planet signal")


class TestAgentChat(unittest.TestCase):

    @patch("backend.ai_interpretation.agent.AstroAgent._call_claude",
           return_value=MOCK_CHAT)
    def test_normal_chat_returns_response(self, _mock):
        agent = _make_agent()
        response, blocked = agent.chat(
            user_message="When will I get a promotion?",
            kundli_prompt="COMPACT KUNDLI",
            prior_messages=[],
            planet_knowledge=PlanetKnowledge(),
        )
        self.assertFalse(blocked)
        self.assertIsInstance(response, str)
        self.assertGreater(len(response), 10)

    def test_future_death_chat_blocked(self):
        agent = _make_agent()
        response, blocked = agent.chat(
            user_message="When will I die?",
            kundli_prompt="KUNDLI",
            prior_messages=[],
        )
        self.assertTrue(blocked, "Future death question must be blocked")
        self.assertGreater(len(response), 10, "Refusal message must not be empty")

    def test_young_child_chat_blocked(self):
        agent = _make_agent()
        response, blocked = agent.chat(
            user_message="What will happen to my 3 year old son?",
            kundli_prompt="KUNDLI",
            prior_messages=[],
        )
        self.assertTrue(blocked)
        self.assertIn("formative", response.lower())

    @patch("backend.ai_interpretation.agent.AstroAgent._call_claude",
           return_value="My late father passed away during Saturn dasha...")
    def test_past_death_chat_allowed(self, _mock):
        agent = _make_agent()
        response, blocked = agent.chat(
            user_message="My late father passed away — what dasha was it?",
            kundli_prompt="KUNDLI",
            prior_messages=[],
        )
        self.assertFalse(blocked, "Past death question must be allowed")

    @patch("backend.ai_interpretation.agent.AstroAgent._call_claude",
           return_value=MOCK_CHAT)
    def test_chat_caps_history(self, mock_call):
        agent = _make_agent()
        long_history = [
            {"role": "user", "content": f"msg {i}"}
            for i in range(20)
        ]
        agent.chat(
            user_message="New question",
            kundli_prompt="KUNDLI",
            prior_messages=long_history,
            max_history=10,
        )
        # The messages argument passed to _call_claude should be <= 11 (10 history + 1 new)
        call_messages = mock_call.call_args[1].get("messages") or mock_call.call_args[0][0]
        self.assertLessEqual(len(call_messages), 11)


class TestAgentParseJson(unittest.TestCase):

    def test_parse_clean_json(self):
        d = AstroAgent._parse_json('{"key": "value"}')
        self.assertEqual(d["key"], "value")

    def test_parse_json_with_markdown_fence(self):
        d = AstroAgent._parse_json('```json\n{"key": "value"}\n```')
        self.assertEqual(d["key"], "value")

    def test_parse_invalid_json_returns_empty(self):
        d = AstroAgent._parse_json("not json at all")
        self.assertEqual(d, {})

    def test_parse_json_embedded_in_text(self):
        d = AstroAgent._parse_json('Some text before {"key": "val"} some text after')
        self.assertEqual(d["key"], "val")


if __name__ == "__main__":
    unittest.main()
