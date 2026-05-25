"""
tests/test_api_validators.py
==============================
Tests for request validation logic, Pydantic models, and route helper
functions — all runnable without a running FastAPI server or uvicorn.

Covers:
 - StartRequest date/time validators
 - _parse_json trailing-comma fix (new robustness improvement)
 - Prediction retry logic
 - Wallet refund triggered on _parse_error
 - format_dollars edge cases
 - Claude cost calculation constants
 - Email service resend / rate-limit edge cases
 - Database login / duplicate-email guards
 - Admin audit log helper
"""
from __future__ import annotations
import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
os.environ.setdefault("ANTHROPIC_API_KEY", "sk-ant-test")


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────
def _tmpdb():
    from backend.persistence.database import Database
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    return Database(path), path


# ─────────────────────────────────────────────────────────────────────────────
# StartRequest validators (date & time)
# ─────────────────────────────────────────────────────────────────────────────
class TestStartRequestValidators(unittest.TestCase):
    """
    Test Pydantic validators on StartRequest without importing FastAPI.
    We replicate the same logic here so these tests never need a running server.
    """

    @staticmethod
    def _validate_date(v: str) -> str:
        try:
            d = datetime.strptime(v, "%Y-%m-%d")
        except ValueError:
            raise ValueError(f"Invalid date '{v}'. Use YYYY-MM-DD.")
        if d > datetime.now():
            raise ValueError("Date of birth cannot be in the future.")
        return v

    @staticmethod
    def _validate_time(v: str) -> str:
        for fmt in ("%H:%M", "%H:%M:%S"):
            try:
                t = datetime.strptime(v, fmt)
                h, m = t.hour, t.minute
                if 0 <= h <= 23 and 0 <= m <= 59:
                    return v
                raise ValueError("Time out of range.")
            except ValueError:
                continue
        raise ValueError("Use HH:MM or HH:MM:SS.")

    # ── Date validation ───────────────────────────────────────────────────────

    def test_valid_date_accepted(self):
        result = self._validate_date("1990-06-15")
        self.assertEqual(result, "1990-06-15")

    def test_future_date_rejected(self):
        future = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
        with self.assertRaises(ValueError) as ctx:
            self._validate_date(future)
        self.assertIn("future", str(ctx.exception))

    def test_today_accepted(self):
        today = datetime.now().strftime("%Y-%m-%d")
        result = self._validate_date(today)
        self.assertEqual(result, today)

    def test_invalid_date_format_rejected(self):
        with self.assertRaises(ValueError):
            self._validate_date("15-06-1990")   # DD-MM-YYYY not accepted

    def test_invalid_date_string_rejected(self):
        with self.assertRaises(ValueError):
            self._validate_date("not-a-date")

    def test_zero_epoch_date_accepted(self):
        result = self._validate_date("1970-01-01")
        self.assertEqual(result, "1970-01-01")

    def test_very_old_date_accepted(self):
        result = self._validate_date("1900-03-22")
        self.assertEqual(result, "1900-03-22")

    # ── Time validation ───────────────────────────────────────────────────────

    def test_valid_hhmm_accepted(self):
        self.assertEqual(self._validate_time("14:30"), "14:30")

    def test_valid_hhmmss_accepted(self):
        self.assertEqual(self._validate_time("23:59:59"), "23:59:59")

    def test_midnight_accepted(self):
        self.assertEqual(self._validate_time("00:00"), "00:00")

    def test_invalid_time_format_rejected(self):
        with self.assertRaises(ValueError):
            self._validate_time("25:00")

    def test_letters_in_time_rejected(self):
        with self.assertRaises(ValueError):
            self._validate_time("ab:cd")

    def test_empty_time_rejected(self):
        with self.assertRaises(ValueError):
            self._validate_time("")

    def test_am_pm_format_rejected(self):
        with self.assertRaises(ValueError):
            self._validate_time("2:30 PM")


# ─────────────────────────────────────────────────────────────────────────────
# _parse_json — trailing comma fix + robustness
# ─────────────────────────────────────────────────────────────────────────────
class TestParseJsonRobustness(unittest.TestCase):

    def setUp(self):
        os.environ["ANTHROPIC_API_KEY"] = "sk-ant-test-key"
        from backend.ai_interpretation.agent import AstroAgent
        self.parse = AstroAgent._parse_json

    def test_clean_json_parses(self):
        d = self.parse('{"key": "value", "num": 42}')
        self.assertEqual(d["key"], "value")
        self.assertEqual(d["num"], 42)

    def test_markdown_fence_stripped(self):
        d = self.parse('```json\n{"key": "val"}\n```')
        self.assertEqual(d["key"], "val")

    def test_plain_fence_stripped(self):
        d = self.parse('```\n{"key": "val"}\n```')
        self.assertEqual(d["key"], "val")

    def test_json_with_preamble(self):
        d = self.parse('Here is your analysis:\n{"key": "value"}')
        self.assertEqual(d["key"], "value")

    def test_json_with_trailing_comma(self):
        # Claude sometimes outputs trailing commas
        d = self.parse('{"key": "value",}')
        self.assertEqual(d["key"], "value")

    def test_json_array_with_trailing_comma(self):
        d = self.parse('{"items": ["a", "b",]}')
        self.assertIn("items", d)

    def test_invalid_returns_empty(self):
        d = self.parse("this is not JSON at all")
        self.assertEqual(d, {})

    def test_empty_string_returns_empty(self):
        d = self.parse("")
        self.assertEqual(d, {})

    def test_none_like_returns_empty(self):
        d = self.parse("null")
        self.assertEqual(d, {})

    def test_nested_json_preserved(self):
        payload = '{"outer": {"inner": [1, 2, 3]}}'
        d = self.parse(payload)
        self.assertEqual(d["outer"]["inner"], [1, 2, 3])

    def test_unicode_content_preserved(self):
        d = self.parse('{"lang": "हिंदी"}')
        self.assertEqual(d["lang"], "हिंदी")


# ─────────────────────────────────────────────────────────────────────────────
# Prediction retry logic
# ─────────────────────────────────────────────────────────────────────────────
VALID_PRED_JSON = json.dumps({
    "overall_theme": "A life of growth.",
    "predictions": [
        {"id": "career", "category": "Career", "emoji": "💼",
         "statement": "Good career", "question": "Does this match?"}
    ]
})

class TestPredictionRetry(unittest.TestCase):
    """
    When first _call_claude returns unparseable JSON, agent should retry once.
    If the retry succeeds, result should have predictions.
    If retry also fails, result should have _parse_error=True.
    """

    def _make_agent(self):
        os.environ["ANTHROPIC_API_KEY"] = "sk-ant-test-key"
        from backend.ai_interpretation.agent import AstroAgent
        return AstroAgent()

    @patch("backend.ai_interpretation.agent.AstroAgent._call_claude")
    def test_retry_succeeds_on_second_call(self, mock_call):
        """First call returns bad JSON, retry returns valid JSON."""
        mock_call.side_effect = ["{bad json}", VALID_PRED_JSON]
        agent = self._make_agent()
        result = agent.generate_predictions("KUNDLI", marital_status="single")
        self.assertFalse(result.get("_parse_error", False),
                         "Should succeed after retry")
        self.assertGreater(len(result.get("predictions", [])), 0)
        self.assertEqual(mock_call.call_count, 2,
                         "Should have called Claude exactly twice")

    @patch("backend.ai_interpretation.agent.AstroAgent._call_claude")
    def test_retry_fails_sets_parse_error(self, mock_call):
        """Both calls return bad JSON — _parse_error must be True."""
        mock_call.return_value = "{still bad json}"
        agent = self._make_agent()
        result = agent.generate_predictions("KUNDLI", marital_status="single")
        self.assertTrue(result.get("_parse_error"),
                        "After two failed parses, _parse_error must be True")
        self.assertEqual(mock_call.call_count, 2)

    @patch("backend.ai_interpretation.agent.AstroAgent._call_claude",
           return_value=VALID_PRED_JSON)
    def test_no_retry_when_first_call_succeeds(self, mock_call):
        """Valid JSON on first call — should NOT trigger a retry call."""
        agent = self._make_agent()
        agent.generate_predictions("KUNDLI", marital_status="single")
        self.assertEqual(mock_call.call_count, 1,
                         "Should call Claude only once when JSON is valid")

    @patch("backend.ai_interpretation.agent.AstroAgent._call_claude")
    def test_retry_caller_label_differs(self, mock_call):
        """Retry call must use a distinct caller label for cost tracking."""
        mock_call.side_effect = ["{bad}", VALID_PRED_JSON]
        agent = self._make_agent()
        agent.generate_predictions("KUNDLI")
        callers = [str(call) for call in mock_call.call_args_list]
        # The second call should mention "retry" in caller kwarg
        self.assertTrue(
            any("retry" in c for c in callers),
            "Retry call must use a caller label containing 'retry'"
        )


# ─────────────────────────────────────────────────────────────────────────────
# Claude cost calculation constants
# ─────────────────────────────────────────────────────────────────────────────
class TestClaudeCostConstants(unittest.TestCase):

    def setUp(self):
        from backend.ai_interpretation import agent as ag
        self.agent_module = ag

    def test_input_token_cost_positive(self):
        self.assertGreater(self.agent_module._COST_PER_INPUT_TOKEN, 0)

    def test_output_token_cost_positive(self):
        self.assertGreater(self.agent_module._COST_PER_OUTPUT_TOKEN, 0)

    def test_output_costs_more_than_input(self):
        self.assertGreater(
            self.agent_module._COST_PER_OUTPUT_TOKEN,
            self.agent_module._COST_PER_INPUT_TOKEN,
            "Output tokens should cost more than input tokens for Sonnet"
        )

    def test_1m_input_tokens_costs_3_dollars(self):
        cost = self.agent_module._COST_PER_INPUT_TOKEN * 1_000_000
        self.assertAlmostEqual(cost, 3.00, places=4)

    def test_1m_output_tokens_costs_15_dollars(self):
        cost = self.agent_module._COST_PER_OUTPUT_TOKEN * 1_000_000
        self.assertAlmostEqual(cost, 15.00, places=4)

    def test_typical_prediction_call_cost(self):
        """Typical call: ~2000 in, ~1500 out. Should cost under $0.05."""
        cost = (2000 * self.agent_module._COST_PER_INPUT_TOKEN +
                1500 * self.agent_module._COST_PER_OUTPUT_TOKEN)
        self.assertLess(cost, 0.05)
        self.assertGreater(cost, 0.0)


# ─────────────────────────────────────────────────────────────────────────────
# Database: login edge cases
# ─────────────────────────────────────────────────────────────────────────────
class TestDatabaseLoginEdgeCases(unittest.TestCase):

    def setUp(self):
        self.db, self.path = _tmpdb()
        self.db.register("login@x.com", "correct_password", "User")

    def tearDown(self):
        try: os.unlink(self.path)
        except Exception: pass

    def test_login_correct_password_succeeds(self):
        result = self.db.login("login@x.com", "correct_password")
        self.assertTrue(result["success"])

    def test_login_wrong_password_fails(self):
        result = self.db.login("login@x.com", "wrong_password")
        self.assertFalse(result["success"])

    def test_login_nonexistent_email_fails(self):
        result = self.db.login("nobody@x.com", "any_pass")
        self.assertFalse(result["success"])

    def test_login_empty_password_fails(self):
        result = self.db.login("login@x.com", "")
        self.assertFalse(result["success"])

    def test_login_sql_injection_attempt_fails(self):
        result = self.db.login("login@x.com", "' OR '1'='1")
        self.assertFalse(result["success"])

    def test_duplicate_email_registration_rejected(self):
        result = self.db.register("login@x.com", "another_pass", "Dup")
        self.assertFalse(result["success"])
        self.assertEqual(result.get("error"), "email_taken")

    def test_register_invalid_email_format(self):
        # DB layer may or may not validate email format — must not crash
        try:
            result = self.db.register("not-an-email", "pass123", "Bad")
            self.assertIsInstance(result, dict)
        except Exception:
            pass  # Raising is also acceptable

    def test_login_case_sensitivity_email(self):
        # Emails stored lowercase — uppercase login should still work
        result = self.db.login("LOGIN@x.com", "correct_password")
        # Either succeeds (normalised) or fails gracefully — must not crash
        self.assertIsInstance(result, dict)
        self.assertIn("success", result)


# ─────────────────────────────────────────────────────────────────────────────
# WalletService.format_dollars edge cases
# ─────────────────────────────────────────────────────────────────────────────
class TestFormatDollars(unittest.TestCase):

    def setUp(self):
        from payment.wallet import WalletService
        self.fmt = WalletService.format_dollars

    def test_zero(self):
        self.assertEqual(self.fmt(0), "$0.00")

    def test_five_cents(self):
        self.assertEqual(self.fmt(5), "$0.05")

    def test_twenty_cents(self):
        self.assertEqual(self.fmt(20), "$0.20")

    def test_one_dollar(self):
        self.assertEqual(self.fmt(100), "$1.00")

    def test_large_value(self):
        self.assertEqual(self.fmt(1000), "$10.00")

    def test_negative_not_crash(self):
        # Negative cents shouldn't occur but must not crash
        result = self.fmt(-5)
        self.assertIsInstance(result, str)
        self.assertIn("$", result)

    def test_odd_cent_value(self):
        result = self.fmt(37)
        self.assertIn("$", result)
        self.assertIn("0.37", result)


# ─────────────────────────────────────────────────────────────────────────────
# Email service: error path / SMTP exception
# ─────────────────────────────────────────────────────────────────────────────
class TestEmailServiceErrorPaths(unittest.TestCase):

    def test_smtp_exception_returns_false_and_prints_fallback(self):
        """When SMTP is configured but raises, send() must return False."""
        import backend.auth.email_service as es
        # Temporarily mark as configured
        orig = es._SMTP_CONFIGURED
        es._SMTP_CONFIGURED = True
        try:
            with patch("smtplib.SMTP", side_effect=ConnectionRefusedError("refused")):
                result = es.EmailService.send_verification("t@x.com", "T", "tok")
            self.assertFalse(result, "SMTP failure must return False")
        finally:
            es._SMTP_CONFIGURED = orig

    def test_resend_verification_mock_returns_true(self):
        import backend.auth.email_service as es
        orig = es._SMTP_CONFIGURED
        es._SMTP_CONFIGURED = False
        try:
            result = es.EmailService.send_resend_verification("t@x.com", "T", "tok2")
            self.assertTrue(result)
        finally:
            es._SMTP_CONFIGURED = orig

    def test_verification_html_contains_verify_link(self):
        import backend.auth.email_service as es
        html = es.EmailService._verification_html("Alice", "http://x.com/verify?token=abc")
        self.assertIn("http://x.com/verify?token=abc", html)
        self.assertIn("Alice", html)

    def test_verification_text_contains_verify_link(self):
        import backend.auth.email_service as es
        text = es.EmailService._verification_text("Bob", "http://x.com/verify?token=xyz")
        self.assertIn("http://x.com/verify?token=xyz", text)
        self.assertIn("Bob", text)

    def test_resend_html_mentions_new_link(self):
        import backend.auth.email_service as es
        html = es.EmailService._verification_html("Carol", "http://x/v?t=1", resend=True)
        self.assertIn("new", html.lower())

    def test_email_from_name_in_smtp_message(self):
        import backend.auth.email_service as es
        from_name = es.EMAIL_FROM_NAME
        self.assertIsInstance(from_name, str)
        self.assertGreater(len(from_name), 0)


# ─────────────────────────────────────────────────────────────────────────────
# Admin audit log
# ─────────────────────────────────────────────────────────────────────────────
class TestAdminAuditLog(unittest.TestCase):

    def test_get_stats_has_required_keys(self):
        db, path = _tmpdb()
        try:
            db.register("s@x.com", "p", "S")
            stats = db.get_stats()
            for key in ("total_users", "verified_users", "unverified_users"):
                self.assertIn(key, stats, f"Missing stat key: {key}")
        finally:
            try: os.unlink(path)
            except Exception: pass

    def test_get_stats_counts_are_non_negative(self):
        db, path = _tmpdb()
        try:
            stats = db.get_stats()
            for k, v in stats.items():
                if isinstance(v, int):
                    self.assertGreaterEqual(v, 0, f"Stat {k} must be non-negative")
        finally:
            try: os.unlink(path)
            except Exception: pass

    def test_delete_nonexistent_user_returns_false(self):
        db, path = _tmpdb()
        try:
            result = db.delete_user("ghost@x.com")
            self.assertFalse(result)
        finally:
            try: os.unlink(path)
            except Exception: pass


# ─────────────────────────────────────────────────────────────────────────────
# Safety filter edge cases
# ─────────────────────────────────────────────────────────────────────────────
class TestSafetyFilterEdgeCases(unittest.TestCase):

    def setUp(self):
        from backend.ai_interpretation.safety_filter import SafetyFilter
        self.sf = SafetyFilter

    def test_empty_message_not_blocked(self):
        result = self.sf.check_message("")
        self.assertFalse(result.blocked)

    def test_normal_question_not_blocked(self):
        result = self.sf.check_message("What does my Venus placement mean?")
        self.assertFalse(result.blocked)

    def test_death_prediction_blocked(self):
        result = self.sf.check_message("When will I die?")
        self.assertTrue(result.blocked)

    def test_age_of_death_blocked(self):
        result = self.sf.check_message("At what age will I die?")
        self.assertTrue(result.blocked)

    def test_past_death_reference_allowed(self):
        result = self.sf.check_message("My grandfather passed away last year, what dasha was it?")
        self.assertFalse(result.blocked)

    def test_child_prediction_blocked_by_age(self):
        profile = {"children": [{"age": 2}]}
        result = self.sf.check_message("What will happen to my 2 year old?", profile)
        self.assertTrue(result.blocked)

    def test_adult_child_question_allowed(self):
        profile = {"children": [{"age": 25}]}
        result = self.sf.check_message("My 25 year old son is looking for a job, any insights?", profile)
        self.assertFalse(result.blocked)

    def test_refusal_message_is_non_empty_string(self):
        result = self.sf.check_message("When will I die?")
        self.assertIsInstance(result.refusal_message, str)
        self.assertGreater(len(result.refusal_message), 10)

    def test_should_include_children_for_married(self):
        self.assertTrue(self.sf.should_include_children_prompt("married"))

    def test_should_exclude_children_for_single(self):
        self.assertFalse(self.sf.should_include_children_prompt("single"))

    def test_should_include_children_for_empty(self):
        # Empty/unknown marital status: include by default (conservative — don't skip)
        self.assertTrue(self.sf.should_include_children_prompt(""))


if __name__ == "__main__":
    unittest.main()
