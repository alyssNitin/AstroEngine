"""
test_safety_filter.py
=====================
Unit tests for SafetyFilter — no external dependencies required.
Covers TC-AI-002, TC-AI-008, and all safety-related conditions from the spec.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import unittest
from backend.ai_interpretation.safety_filter import SafetyFilter


class TestDeathQuestionBlocking(unittest.TestCase):
    """Future death questions must always be blocked."""

    def test_future_death_blocked_direct(self):
        result = SafetyFilter.check_message("When will I die?")
        self.assertTrue(result.blocked, "Direct death question should be blocked")
        self.assertIn("not", result.refusal_message.lower())

    def test_future_death_blocked_lifespan(self):
        result = SafetyFilter.check_message("What is my lifespan according to my chart?")
        self.assertTrue(result.blocked)

    def test_future_death_blocked_hindi_style(self):
        result = SafetyFilter.check_message("How long will I live?")
        self.assertTrue(result.blocked)

    def test_future_death_reason_code(self):
        result = SafetyFilter.check_message("When am I going to die?")
        self.assertEqual(result.reason, "future_death_blocked")

    def test_past_death_allowed(self):
        result = SafetyFilter.check_message("My late father passed away in 2010. What does his chart say?")
        self.assertFalse(result.blocked, "Past death question should be allowed")

    def test_past_death_deceased_parent(self):
        result = SafetyFilter.check_message("My deceased mother — what dasha was she running when she died?")
        self.assertFalse(result.blocked)

    def test_is_past_death_question(self):
        self.assertTrue(SafetyFilter.is_past_death_question("My late husband passed away"))
        self.assertFalse(SafetyFilter.is_past_death_question("When will I die?"))

    def test_is_future_death_question(self):
        self.assertTrue(SafetyFilter.is_future_death_question("When will I die?"))
        self.assertFalse(SafetyFilter.is_future_death_question("My father died last year"))

    def test_refusal_contains_alternative(self):
        result = SafetyFilter.check_message("Tell me my death date")
        self.assertIn("career", result.refusal_message.lower(),
                      "Refusal should redirect to valid topics")


class TestChildrenQuestionBlocking(unittest.TestCase):
    """Children under 5 years must never get predictive answers."""

    def test_child_age_3_blocked(self):
        result = SafetyFilter.check_message("What is the future of my 3 year old son?")
        self.assertTrue(result.blocked, "Question about 3-year-old should be blocked")

    def test_child_age_0_blocked(self):
        result = SafetyFilter.check_message("My baby is 8 months old. Will he be successful?")
        self.assertTrue(result.blocked, "Infant question should be blocked")

    def test_child_age_4_blocked(self):
        result = SafetyFilter.check_message("My 4 year old daughter — will she be a doctor?")
        self.assertTrue(result.blocked)

    def test_child_age_5_allowed(self):
        result = SafetyFilter.check_message("My 5 year old son — what does his chart say?")
        self.assertFalse(result.blocked, "5-year-old is at the threshold — should be allowed")

    def test_child_age_10_allowed(self):
        result = SafetyFilter.check_message("My 10 year old son — will he be good at sports?")
        self.assertFalse(result.blocked)

    def test_refusal_message_polite(self):
        result = SafetyFilter.check_message("My 2 year old baby's future?")
        self.assertTrue(result.blocked)
        self.assertIn("formative", result.refusal_message.lower(),
                      "Refusal should mention formative phase")

    def test_extract_age_years(self):
        age = SafetyFilter.extract_child_age_from_message("My 3 year old son")
        self.assertEqual(age, 3)

    def test_extract_age_months(self):
        age = SafetyFilter.extract_child_age_from_message("My 18 months old baby")
        self.assertEqual(age, 1, "18 months should convert to 1 year")

    def test_no_child_mention_not_blocked(self):
        result = SafetyFilter.check_message("Will I get a promotion this year?")
        self.assertFalse(result.blocked)


class TestConditionalChildrenPrompt(unittest.TestCase):
    """Children prompt should only be shown to married users."""

    def test_married_gets_children_prompt(self):
        self.assertTrue(SafetyFilter.should_include_children_prompt("married"))

    def test_single_skips_children_prompt(self):
        self.assertFalse(SafetyFilter.should_include_children_prompt("single"))

    def test_unmarried_skips_children_prompt(self):
        self.assertFalse(SafetyFilter.should_include_children_prompt("unmarried"))

    def test_in_relationship_skips_children_prompt(self):
        self.assertFalse(SafetyFilter.should_include_children_prompt("in a relationship"))

    def test_divorced_includes_children_prompt(self):
        self.assertTrue(SafetyFilter.should_include_children_prompt("divorced"))

    def test_widowed_includes_children_prompt(self):
        self.assertTrue(SafetyFilter.should_include_children_prompt("widowed"))

    def test_empty_defaults_to_include(self):
        self.assertTrue(SafetyFilter.should_include_children_prompt(""))

    def test_engaged_skips_children_prompt(self):
        self.assertFalse(SafetyFilter.should_include_children_prompt("engaged"))


class TestSafetyFilterCheckMessage(unittest.TestCase):
    """FilterResult object protocol."""

    def test_safe_message_returns_not_blocked(self):
        result = SafetyFilter.check_message("What career is good for me?")
        self.assertFalse(result.blocked)
        self.assertTrue(bool(result), "FilterResult bool should be True when not blocked")

    def test_blocked_message_bool_false(self):
        result = SafetyFilter.check_message("When will I die?")
        self.assertFalse(bool(result), "FilterResult bool should be False when blocked")

    def test_profile_child_ages_triggers_block(self):
        profile = {"children_info": {"ages": [2, 4]}}
        result = SafetyFilter.check_message(
            "What will happen to my child?", user_profile=profile
        )
        self.assertTrue(result.blocked)

    def test_profile_older_child_not_blocked(self):
        profile = {"children_info": {"ages": [8, 12]}}
        result = SafetyFilter.check_message(
            "What will happen to my child?", user_profile=profile
        )
        self.assertFalse(result.blocked)


if __name__ == "__main__":
    unittest.main()
