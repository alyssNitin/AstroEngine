"""
tests/test_pending_features.py
================================
Unit tests for all features implemented in the "pending → done" session:

  1.  Yogini Dasha system
  2.  Chara Dasha system (Jaimini)
  3.  Kalachakra Dasha system
  4.  Narayana Dasha system
  5.  Moola Dasha system
  6.  Dasha registry — all 6 systems registered
  7.  Structlog / backend core logging module
  8.  Notification service — EmailService templates
  9.  Notification service — SMTP console fallback
  10. Notification service — FCM stub
  11. Analytics — EventCollector (in-memory)
  12. Analytics — LlmCostCollector sample mode
  13. Analytics — TrafficAggregator sample mode
  14. Analytics — RevenueAggregator sample mode
  15. Analytics — HealthAggregator sample mode
  16. Syntax check all new files
"""
from __future__ import annotations

import ast
import os
import sys
import types
import unittest
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch, MagicMock

# ── Path setup ────────────────────────────────────────────────────────────────
ROOT    = Path(__file__).parent.parent
DASHA  = ROOT / "services" / "dasha-engine"
NOTIF  = ROOT / "services" / "notification-service"
ANALYT = ROOT / "services" / "analytics-service"

# ROOT always in sys.path for backend.* imports
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _use_service(service_dir: Path) -> None:
    """Switch the active service src for import resolution.

    Removes all three service dirs from sys.path, evicts cached src.* modules,
    then inserts service_dir at position 0. Subsequent 'from src.X import Y'
    calls will resolve to service_dir/src/X — no namespace collision.
    """
    for d in (DASHA, NOTIF, ANALYT):
        s = str(d)
        while s in sys.path:
            sys.path.remove(s)
    # Evict cached src.* so Python re-resolves from the new sys.path
    for key in list(sys.modules):
        if key == "src" or key.startswith("src."):
            del sys.modules[key]
    sys.path.insert(0, str(service_dir))

# Stub env vars so no real credentials needed
os.environ.setdefault("DATABASE_URL",     "")
os.environ.setdefault("SMTP_HOST",        "")
os.environ.setdefault("FCM_SERVER_KEY",   "")
os.environ.setdefault("EMAIL_PROVIDER",   "smtp")
os.environ.setdefault("APP_BASE_URL",     "http://localhost:8000")
os.environ.setdefault("ENVIRONMENT",      "development")
os.environ.setdefault("FIELD_ENCRYPTION_KEY",
    "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=")


# ─────────────────────────────────────────────────────────────────────────────
# Shared fixture: a minimal birth_chart dict all dasha systems accept
# ─────────────────────────────────────────────────────────────────────────────
_BIRTH_CHART = {
    "birth_info": {"date": "1990-03-15"},
    "lagna":      {"sign": "Virgo"},
    "planets":    {
        "Moon":    {"longitude": 45.5, "sign": "Taurus", "degree_in_sign": 15.5},
        "Sun":     {"longitude": 330.0, "sign": "Pisces", "degree_in_sign": 0.0},
        "Mars":    {"longitude": 270.0, "sign": "Capricorn", "degree_in_sign": 0.0},
        "Mercury": {"longitude": 315.0, "sign": "Aquarius", "degree_in_sign": 15.0},
        "Jupiter": {"longitude": 90.0,  "sign": "Cancer", "degree_in_sign": 0.0},
        "Venus":   {"longitude": 0.0,   "sign": "Aries", "degree_in_sign": 0.0},
        "Saturn":  {"longitude": 180.0, "sign": "Libra", "degree_in_sign": 0.0},
    },
}


# =============================================================================
# 1–5. Individual Dasha Systems
# =============================================================================

class TestYoginiDasha(unittest.TestCase):
    """Tests for services/dasha-engine/src/systems/yogini.py"""

    def setUp(self):
        _use_service(DASHA)
        from src.systems.yogini import YoginiDasha
        self.dasha = YoginiDasha()

    def test_name_and_display_name(self):
        self.assertEqual(self.dasha.name, "yogini")
        self.assertIn("Yogini", self.dasha.display_name)

    def test_total_years_is_36(self):
        self.assertEqual(self.dasha.total_years, 36)

    def test_calculate_returns_8_periods(self):
        result = self.dasha.calculate(_BIRTH_CHART, "", "", depth=1)
        self.assertEqual(len(result["timeline"]), 8)

    def test_each_period_has_yogini_and_lord(self):
        result = self.dasha.calculate(_BIRTH_CHART, "", "", depth=1)
        for p in result["timeline"]:
            self.assertIn("yogini", p)
            self.assertIn("lord",   p)

    def test_periods_are_chronological(self):
        result = self.dasha.calculate(_BIRTH_CHART, "", "", depth=2)
        dates = [p["start"] for p in result["timeline"]]
        self.assertEqual(dates, sorted(dates))

    def test_sub_periods_present_at_depth2(self):
        result = self.dasha.calculate(_BIRTH_CHART, "", "", depth=2)
        for p in result["timeline"]:
            self.assertIn("sub_periods", p)
            self.assertGreater(len(p["sub_periods"]), 0)

    def test_get_current_returns_dict(self):
        cur = self.dasha.get_current(_BIRTH_CHART)
        self.assertIsInstance(cur, dict)
        self.assertIn("mahadasha", cur)

    def test_list_periods_has_8_entries(self):
        self.assertEqual(len(self.dasha.list_periods()), 8)

    def test_balance_at_birth_present(self):
        result = self.dasha.calculate(_BIRTH_CHART, "", "", depth=1)
        self.assertIn("balance_at_birth", result)

    def test_no_recursion_error(self):
        """calculate() must not call get_current() which calls calculate() again."""
        try:
            self.dasha.calculate(_BIRTH_CHART, "", "", depth=2)
        except RecursionError:
            self.fail("RecursionError detected — mutual recursion bug not fixed")


class TestCharaDasha(unittest.TestCase):
    """Tests for services/dasha-engine/src/systems/chara.py"""

    def setUp(self):
        _use_service(DASHA)
        from src.systems.chara import CharaDasha
        self.dasha = CharaDasha()

    def test_name(self):
        self.assertEqual(self.dasha.name, "chara")

    def test_calculate_returns_12_periods(self):
        result = self.dasha.calculate(_BIRTH_CHART, "", "", depth=1)
        self.assertEqual(len(result["timeline"]), 12)

    def test_each_period_has_sign(self):
        result = self.dasha.calculate(_BIRTH_CHART, "", "", depth=1)
        for p in result["timeline"]:
            self.assertIn("sign", p)

    def test_periods_are_chronological(self):
        result = self.dasha.calculate(_BIRTH_CHART, "", "", depth=1)
        starts = [p["start"] for p in result["timeline"]]
        self.assertEqual(starts, sorted(starts))

    def test_sub_periods_at_depth2(self):
        result = self.dasha.calculate(_BIRTH_CHART, "", "", depth=2)
        self.assertIn("sub_periods", result["timeline"][0])

    def test_atmakaraka_sign_in_result(self):
        result = self.dasha.calculate(_BIRTH_CHART, "", "", depth=1)
        self.assertIn("atmakaraka_sign", result)

    def test_list_periods_is_12_signs(self):
        self.assertEqual(len(self.dasha.list_periods()), 12)

    def test_no_recursion_error(self):
        try:
            self.dasha.calculate(_BIRTH_CHART, "", "", depth=1)
        except RecursionError:
            self.fail("RecursionError in CharaDasha")


class TestKalachakraDasha(unittest.TestCase):
    """Tests for services/dasha-engine/src/systems/kalachakra.py"""

    def setUp(self):
        _use_service(DASHA)
        from src.systems.kalachakra import KalachakraDasha
        self.dasha = KalachakraDasha()

    def test_name(self):
        self.assertEqual(self.dasha.name, "kalachakra")

    def test_calculate_returns_8_periods(self):
        result = self.dasha.calculate(_BIRTH_CHART, "", "", depth=1)
        self.assertEqual(len(result["timeline"]), 8)

    def test_group_is_savya_or_apasavya(self):
        result = self.dasha.calculate(_BIRTH_CHART, "", "", depth=1)
        self.assertIn(result["group"], ("savya", "apasavya"))

    def test_nakshatra_present(self):
        result = self.dasha.calculate(_BIRTH_CHART, "", "", depth=1)
        self.assertIn("nakshatra", result)

    def test_pada_between_1_and_4(self):
        result = self.dasha.calculate(_BIRTH_CHART, "", "", depth=1)
        self.assertIn(result["pada"], (1, 2, 3, 4))

    def test_no_recursion_error(self):
        try:
            self.dasha.calculate(_BIRTH_CHART, "", "", depth=1)
        except RecursionError:
            self.fail("RecursionError in KalachakraDasha")

    def test_sub_periods_at_depth2(self):
        result = self.dasha.calculate(_BIRTH_CHART, "", "", depth=2)
        self.assertIn("sub_periods", result["timeline"][0])


class TestNarayanaDasha(unittest.TestCase):
    """Tests for services/dasha-engine/src/systems/narayana.py"""

    def setUp(self):
        _use_service(DASHA)
        from src.systems.narayana import NarayanaDasha
        self.dasha = NarayanaDasha()

    def test_name(self):
        self.assertEqual(self.dasha.name, "narayana")

    def test_returns_12_periods(self):
        result = self.dasha.calculate(_BIRTH_CHART, "", "", depth=1)
        self.assertEqual(len(result["timeline"]), 12)

    def test_lagna_sign_in_result(self):
        result = self.dasha.calculate(_BIRTH_CHART, "", "", depth=1)
        self.assertIn("lagna_sign", result)
        self.assertEqual(result["lagna_sign"], "Virgo")

    def test_each_period_has_lord(self):
        result = self.dasha.calculate(_BIRTH_CHART, "", "", depth=1)
        for p in result["timeline"]:
            self.assertIn("lord", p)

    def test_no_recursion_error(self):
        try:
            self.dasha.calculate(_BIRTH_CHART, "", "", depth=2)
        except RecursionError:
            self.fail("RecursionError in NarayanaDasha")


class TestMoolaDasha(unittest.TestCase):
    """Tests for services/dasha-engine/src/systems/moola.py"""

    def setUp(self):
        _use_service(DASHA)
        from src.systems.moola import MoolaDasha
        self.dasha = MoolaDasha()

    def test_name(self):
        self.assertEqual(self.dasha.name, "moola")

    def test_total_years_100(self):
        self.assertEqual(self.dasha.total_years, 100)

    def test_returns_9_periods(self):
        result = self.dasha.calculate(_BIRTH_CHART, "", "", depth=1)
        self.assertEqual(len(result["timeline"]), 9)

    def test_each_period_has_planet(self):
        result = self.dasha.calculate(_BIRTH_CHART, "", "", depth=1)
        for p in result["timeline"]:
            self.assertIn("planet", p)

    def test_nakshatra_present(self):
        result = self.dasha.calculate(_BIRTH_CHART, "", "", depth=1)
        self.assertIn("nakshatra", result)

    def test_balance_at_birth_present(self):
        result = self.dasha.calculate(_BIRTH_CHART, "", "", depth=1)
        self.assertIn("balance_at_birth", result)

    def test_list_periods_returns_9(self):
        self.assertEqual(len(self.dasha.list_periods()), 9)

    def test_no_recursion_error(self):
        try:
            self.dasha.calculate(_BIRTH_CHART, "", "", depth=2)
        except RecursionError:
            self.fail("RecursionError in MoolaDasha")


# =============================================================================
# 6. Dasha Registry
# =============================================================================

class TestDashaRegistry(unittest.TestCase):
    """All 6 systems registered and instantiable."""

    def setUp(self):
        _use_service(DASHA)
        from src.systems import DASHA_SYSTEMS
        self.registry = DASHA_SYSTEMS

    def test_all_6_systems_registered(self):
        expected = {"vimshottari", "yogini", "chara", "kalachakra", "narayana", "moola"}
        self.assertEqual(set(self.registry.keys()), expected)

    def test_all_systems_have_name_attr(self):
        for name, cls in self.registry.items():
            obj = cls()
            self.assertEqual(obj.name, name, f"{cls.__name__}.name mismatch")

    def test_all_systems_have_description(self):
        for name, cls in self.registry.items():
            obj = cls()
            self.assertIsInstance(obj.description, str, f"{name} missing description")
            self.assertGreater(len(obj.description), 10)

    def test_all_non_vimshottari_can_calculate(self):
        for name, cls in self.registry.items():
            if name == "vimshottari":
                continue
            obj    = cls()
            result = obj.calculate(_BIRTH_CHART, "", "", depth=1)
            self.assertIn("timeline", result, f"{name} missing timeline key")
            self.assertIn("current",  result, f"{name} missing current key")


# =============================================================================
# 7. Structlog / backend core logging
# =============================================================================

class TestCoreLogging(unittest.TestCase):
    """Tests for backend/core/logging.py"""

    def setUp(self):
        from backend.core.logging import get_logger, configure_logging
        self.get_logger        = get_logger
        self.configure_logging = configure_logging

    def test_get_logger_returns_object(self):
        log = self.get_logger("test.module")
        self.assertIsNotNone(log)

    def test_logger_has_info_method(self):
        log = self.get_logger("test.module")
        self.assertTrue(hasattr(log, "info"))

    def test_logger_has_error_method(self):
        log = self.get_logger("test.module")
        self.assertTrue(hasattr(log, "error"))

    def test_logger_has_warning_method(self):
        log = self.get_logger("test.module")
        self.assertTrue(hasattr(log, "warning"))

    def test_configure_logging_runs_without_error(self):
        try:
            self.configure_logging()
        except Exception as e:
            self.fail(f"configure_logging() raised {e}")

    def test_get_logger_different_names_independent(self):
        log_a = self.get_logger("module.a")
        log_b = self.get_logger("module.b")
        # They must be usable without interfering
        log_a.info("msg from a")
        log_b.info("msg from b")

    def test_bind_request_context_importable(self):
        from backend.core.logging import bind_request_context
        # Should not raise
        bind_request_context(request_id="test-123")

    def test_clear_request_context_importable(self):
        from backend.core.logging import clear_request_context
        clear_request_context()


# =============================================================================
# 8. Notification service — EmailService templates
# =============================================================================

class TestEmailServiceTemplates(unittest.TestCase):
    """Tests for notification-service email_service.py"""

    def setUp(self):
        _use_service(NOTIF)
        from src.email.email_service import EmailService, _TEMPLATES
        self.svc       = EmailService()
        self.templates = _TEMPLATES

    def test_all_required_templates_present(self):
        required = {
            "email_verification", "welcome", "payment_receipt",
            "low_balance", "password_reset", "reading_ready",
        }
        self.assertEqual(set(self.templates.keys()), required)

    def test_each_template_has_en_hi_ta(self):
        for key, langs in self.templates.items():
            for lang in ("en", "hi", "ta"):
                self.assertIn(lang, langs, f"{key} missing lang={lang}")

    def test_each_lang_has_subject_html_text(self):
        for key, langs in self.templates.items():
            for lang, t in langs.items():
                self.assertIn("subject", t, f"{key}/{lang} missing subject")
                self.assertIn("html",    t, f"{key}/{lang} missing html")
                self.assertIn("text",    t, f"{key}/{lang} missing text")

    def test_verification_link_in_rendered_html(self):
        _, html, _ = self.svc._render(
            "email_verification", "en", link="http://test/verify?token=abc")
        self.assertIn("http://test/verify?token=abc", html)

    def test_welcome_renders_all_langs(self):
        for lang in ("en", "hi", "ta"):
            subj, html, text = self.svc._render("welcome", lang)
            self.assertTrue(len(subj) > 5)
            self.assertTrue(len(html) > 20)

    def test_payment_receipt_interpolates_values(self):
        _, html, _ = self.svc._render(
            "payment_receipt", "en",
            order_id="ord_123", credits=20, amount="99.00",
            currency="INR", balance=40)
        self.assertIn("ord_123", html)
        self.assertIn("20", html)

    def test_low_balance_shows_balance(self):
        _, html, _ = self.svc._render("low_balance", "en", balance=3)
        self.assertIn("3", html)

    def test_password_reset_link_contains_token(self):
        _, html, _ = self.svc._render(
            "password_reset", "en", link="http://test/reset?token=xyz")
        self.assertIn("xyz", html)

    def test_reading_ready_contains_report_id(self):
        _, html, _ = self.svc._render(
            "reading_ready", "en",
            report_id="rpt-999", report_type="personal")
        self.assertIn("rpt-999", html)


# =============================================================================
# 9. Notification service — SMTP console fallback
# =============================================================================

class TestSmtpConsoleFallback(unittest.TestCase):
    """When SMTP_HOST is empty, send_email prints to stdout (dev mode)."""

    def setUp(self):
        _use_service(NOTIF)

    def test_send_returns_true_without_smtp_config(self):
        with patch.dict(os.environ, {"SMTP_HOST": ""}):
            # Re-import to pick up empty SMTP_HOST
            import importlib
            import src.email.smtp_client as mod
            importlib.reload(mod)
            result = mod.send_email(
                to="test@example.com",
                subject="Test",
                html_body="<p>Hello</p>",
            )
            self.assertTrue(result)

    def test_send_verification_returns_bool(self):
        from src.email.email_service import EmailService
        svc = EmailService()
        # SMTP not configured → should use console fallback → True
        result = svc.send_verification("x@test.com", "tok123", lang="en")
        self.assertIsInstance(result, bool)

    def test_send_welcome_returns_bool(self):
        from src.email.email_service import EmailService
        svc = EmailService()
        result = svc.send_welcome("x@test.com", lang="hi")
        self.assertIsInstance(result, bool)

    def test_send_low_balance_returns_bool(self):
        from src.email.email_service import EmailService
        svc = EmailService()
        result = svc.send_low_balance("x@test.com", balance=2, lang="ta")
        self.assertIsInstance(result, bool)

    def test_send_password_reset_returns_bool(self):
        from src.email.email_service import EmailService
        svc = EmailService()
        result = svc.send_password_reset("x@test.com", token="reset_tok")
        self.assertIsInstance(result, bool)


# =============================================================================
# 10. Notification service — FCM client stub
# =============================================================================

class TestFcmClientStub(unittest.TestCase):
    """FCM client stub mode (no FCM_SERVER_KEY configured)."""

    def setUp(self):
        _use_service(NOTIF)
        with patch.dict(os.environ, {"FCM_SERVER_KEY": ""}):
            import importlib
            import src.push.fcm_client as mod
            importlib.reload(mod)
            from src.push.fcm_client import FCMClient
            self.fcm = FCMClient()

    def test_send_returns_true_in_stub_mode(self):
        result = self.fcm.send("fake-token", "Title", "Body")
        self.assertTrue(result)

    def test_send_bulk_returns_dict(self):
        tokens = ["tok1", "tok2", "tok3"]
        result = self.fcm.send_bulk(tokens, "Bulk", "Message")
        self.assertIsInstance(result, dict)
        self.assertEqual(set(result.keys()), set(tokens))

    def test_send_bulk_all_true_in_stub(self):
        tokens = ["a", "b"]
        result = self.fcm.send_bulk(tokens, "T", "B")
        self.assertTrue(all(result.values()))


# =============================================================================
# 11. Analytics — EventCollector (in-memory mode)
# =============================================================================

class TestEventCollectorInMemory(unittest.TestCase):
    """Tests for analytics-service EventCollector without a real DB."""

    def setUp(self):
        # Force in-memory mode: clear DATABASE_URL so EventCollector skips DB.
        # Other test modules (test_new_features) set DATABASE_URL via setdefault;
        # we must temporarily remove it so the module re-initialises correctly.
        self._saved_db_url = os.environ.pop("DATABASE_URL", None)
        _use_service(ANALYT)
        # Patch the module-level _DB_URL to empty string so existing singletons
        # also use in-memory storage even if module was already loaded.
        import src.collectors.events as _ev_mod
        self._ev_mod = _ev_mod
        self._saved_module_db_url = _ev_mod._DB_URL
        _ev_mod._DB_URL = ""
        _ev_mod._EVENTS.clear()
        self.collector = _ev_mod.EventCollector()

    def tearDown(self):
        # Restore DATABASE_URL and module state after each test.
        self._ev_mod._DB_URL = self._saved_module_db_url
        self._ev_mod._EVENTS.clear()
        if self._saved_db_url is not None:
            os.environ["DATABASE_URL"] = self._saved_db_url

    def test_record_returns_uuid_string(self):
        eid = self.collector.record("KUNDLI_VIEW", "user-uuid-1")
        self.assertIsInstance(eid, str)
        self.assertEqual(len(eid), 36)  # UUID4 format

    def test_record_stores_event_in_memory(self):
        self._ev_mod._EVENTS.clear()
        self.collector.record("REPORT_GENERATED", "user-uuid-2",
                              {"report_type": "personal"})
        self.assertEqual(len(self._ev_mod._EVENTS), 1)
        self.assertEqual(self._ev_mod._EVENTS[0]["event_type"], "REPORT_GENERATED")

    def test_record_does_not_store_pii(self):
        self._ev_mod._EVENTS.clear()
        self.collector.record("LOGIN", "user-uuid-3",
                              {"email": "SHOULD_NOT_STORE", "name": "Real Name"})
        # The event object stores user_id (UUID) not the raw PII values
        event = self._ev_mod._EVENTS[0]
        self.assertNotIn("email", event)
        self.assertNotIn("name",  event)

    def test_query_filters_by_date(self):
        self._ev_mod._EVENTS.clear()
        today = str(date.today())
        self.collector.record("CHAT_MSG", "user-1")
        results = self.collector.query(today, today)
        self.assertEqual(len(results), 1)

    def test_query_filters_by_event_type(self):
        self._ev_mod._EVENTS.clear()
        today = str(date.today())
        self.collector.record("LOGIN",         "u1")
        self.collector.record("KUNDLI_VIEW",   "u2")
        results = self.collector.query(today, today, event_type="LOGIN")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["event_type"], "LOGIN")

    def test_count_by_type(self):
        self._ev_mod._EVENTS.clear()
        today = str(date.today())
        self.collector.record("LOGIN", "u1")
        self.collector.record("LOGIN", "u2")
        self.collector.record("KUNDLI_VIEW", "u3")
        counts = self.collector.count_by_type(today, today)
        self.assertEqual(counts["LOGIN"], 2)
        self.assertEqual(counts["KUNDLI_VIEW"], 1)


# =============================================================================
# 12. Analytics — LlmCostCollector sample mode
# =============================================================================

class TestLlmCostCollectorSample(unittest.TestCase):

    def setUp(self):
        _use_service(ANALYT)
        from src.collectors.llm_costs import LlmCostCollector, estimate_cost
        self.collector    = LlmCostCollector()
        self.estimate_cost = estimate_cost

    def test_get_metrics_returns_dict(self):
        m = self.collector.get_metrics("2026-01-01", "2026-01-31")
        self.assertIsInstance(m, dict)

    def test_required_keys_present(self):
        m = self.collector.get_metrics("2026-01-01", "2026-01-31")
        for key in ("total_calls", "total_cost_usd", "by_report_type"):
            self.assertIn(key, m)

    def test_by_report_type_is_dict(self):
        m = self.collector.get_metrics("2026-01-01", "2026-01-31")
        self.assertIsInstance(m["by_report_type"], dict)

    def test_estimate_cost_positive(self):
        cost = self.estimate_cost(1000, 2000)
        self.assertGreater(cost, 0)

    def test_estimate_cost_output_more_expensive(self):
        # Output tokens cost more than input tokens
        input_cost  = self.estimate_cost(1000, 0)
        output_cost = self.estimate_cost(0, 1000)
        self.assertGreater(output_cost, input_cost)


# =============================================================================
# 13. Analytics — TrafficAggregator sample mode
# =============================================================================

class TestTrafficAggregatorSample(unittest.TestCase):

    def setUp(self):
        _use_service(ANALYT)
        from src.aggregators.traffic import TrafficAggregator
        self.agg = TrafficAggregator()

    def test_returns_dict_with_required_keys(self):
        m = self.agg.get_metrics("2026-01-01", "2026-01-31")
        for k in ("total_users", "new_users", "active_users",
                  "total_sessions", "daily_breakdown"):
            self.assertIn(k, m)

    def test_total_users_positive_integer(self):
        m = self.agg.get_metrics("2026-01-01", "2026-01-31")
        self.assertIsInstance(m["total_users"], int)
        self.assertGreater(m["total_users"], 0)

    def test_daily_breakdown_is_list(self):
        m = self.agg.get_metrics("2026-01-01", "2026-01-31")
        self.assertIsInstance(m["daily_breakdown"], list)

    def test_daily_breakdown_each_has_date(self):
        m = self.agg.get_metrics("2026-01-01", "2026-01-07")
        for row in m["daily_breakdown"]:
            self.assertIn("date", row)

    def test_date_range_respected(self):
        m = self.agg.get_metrics("2026-01-01", "2026-01-03")
        # 3-day range → at most 3 days in breakdown
        self.assertLessEqual(len(m["daily_breakdown"]), 3)


# =============================================================================
# 14. Analytics — RevenueAggregator sample mode
# =============================================================================

class TestRevenueAggregatorSample(unittest.TestCase):

    def setUp(self):
        _use_service(ANALYT)
        from src.aggregators.revenue import RevenueAggregator
        self.agg = RevenueAggregator()

    def test_returns_dict_with_required_keys(self):
        m = self.agg.get_metrics("2026-01-01", "2026-01-31")
        for k in ("total_revenue_cents", "by_pack", "by_method", "by_region"):
            self.assertIn(k, m)

    def test_total_revenue_is_integer(self):
        m = self.agg.get_metrics("2026-01-01", "2026-01-31")
        self.assertIsInstance(m["total_revenue_cents"], int)

    def test_by_pack_is_dict(self):
        m = self.agg.get_metrics("2026-01-01", "2026-01-31")
        self.assertIsInstance(m["by_pack"], dict)

    def test_by_method_has_upi_or_card(self):
        m = self.agg.get_metrics("2026-01-01", "2026-01-31")
        by_method = m["by_method"]
        self.assertTrue("upi" in by_method or "card" in by_method)


# =============================================================================
# 15. Analytics — HealthAggregator sample mode
# =============================================================================

class TestHealthAggregatorSample(unittest.TestCase):

    def setUp(self):
        _use_service(ANALYT)
        from src.aggregators.health import HealthAggregator
        self.agg = HealthAggregator()

    def test_returns_dict_with_latency_keys(self):
        m = self.agg.get_metrics()
        for k in ("p50_ms", "p95_ms", "p99_ms", "error_rate", "uptime_pct"):
            self.assertIn(k, m)

    def test_latency_p50_less_than_p95(self):
        m = self.agg.get_metrics()
        self.assertLess(m["p50_ms"], m["p95_ms"])

    def test_latency_p95_less_than_p99(self):
        m = self.agg.get_metrics()
        self.assertLess(m["p95_ms"], m["p99_ms"])

    def test_error_rate_between_0_and_1(self):
        m = self.agg.get_metrics()
        self.assertGreaterEqual(m["error_rate"], 0.0)
        self.assertLessEqual(m["error_rate"], 1.0)

    def test_uptime_near_100(self):
        m = self.agg.get_metrics()
        self.assertGreater(m["uptime_pct"], 99.0)

    def test_checked_at_is_string(self):
        m = self.agg.get_metrics()
        self.assertIsInstance(m["checked_at"], str)


# =============================================================================
# 16. Syntax check all new files
# =============================================================================

class TestAllNewFilesSyntaxClean(unittest.TestCase):
    """AST-parse every new .py file to catch syntax errors before deploy."""

    def _check(self, path: Path):
        src = path.read_text(encoding="utf-8")
        try:
            ast.parse(src)
        except SyntaxError as e:
            self.fail(f"SyntaxError in {path.relative_to(ROOT)}: {e}")

    def test_dasha_engine_systems(self):
        for name in ("yogini", "chara", "kalachakra", "narayana", "moola"):
            self._check(DASHA / "src" / "systems" / f"{name}.py")
        self._check(DASHA / "src" / "systems" / "__init__.py")

    def test_backend_core_logging(self):
        self._check(ROOT / "backend" / "core" / "logging.py")

    def test_notification_service_files(self):
        for rel in (
            "src/email/smtp_client.py",
            "src/email/ses_client.py",
            "src/email/email_service.py",
            "src/push/fcm_client.py",
            "src/api/main.py",
        ):
            self._check(NOTIF / rel)

    def test_analytics_service_files(self):
        for rel in (
            "src/collectors/events.py",
            "src/collectors/llm_costs.py",
            "src/aggregators/traffic.py",
            "src/aggregators/revenue.py",
            "src/aggregators/health.py",
            "src/api/schemas.py",
            "src/api/main.py",
        ):
            self._check(ANALYT / rel)


if __name__ == "__main__":
    unittest.main()
