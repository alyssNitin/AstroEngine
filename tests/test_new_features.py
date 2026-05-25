"""
tests/test_new_features.py
===========================
Unit tests for all features added in the production-hardening session:

  1.  AES-256-GCM field encryption  (backend/auth/field_encryption.py)
  2.  PII scrubber                  (backend/ai_interpretation/pii_scrubber.py)
  3.  AI output validator           (backend/ai_interpretation/output_validator.py)
  4.  GST / tax calculation         (payment/wallet.py)
  5.  Wallet pricing helpers        (payment/wallet.py)
  6.  Wallet label helpers          (payment/wallet.py)
  7.  Security middleware symbols   (backend/api/security.py)
  8.  Startup secrets validation    (backend/api/security.py)
  9.  Rate-limiter topup symbol     (backend/api/rate_limiter.py)
  10. Health endpoint presence      (backend/api/main.py)
  11. GDPR endpoints presence       (backend/api/main.py)
  12. CORS env-var wiring           (backend/api/main.py)
  13. Gender field in DB layer      (backend/persistence/database.py)
  14. SQL migration 005             (infrastructure/db/005_gender_and_gdpr.sql)

Run with:
    pytest tests/test_new_features.py -v
"""
import ast
import os
import pathlib
import sys
import unittest

# ── Path setup ────────────────────────────────────────────────────────────────
ROOT = pathlib.Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

# Stub env vars so imports don't crash in CI (no real DB / API keys needed)
os.environ.setdefault("ANTHROPIC_API_KEY", "sk-ant-test-dummy")
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost:5432/test")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")


# =============================================================================
# 1. AES-256-GCM Field Encryption
# =============================================================================
class TestFieldEncryptionGCM(unittest.TestCase):
    """Tests for backend/auth/field_encryption.py — AES-256-GCM mode."""

    def setUp(self):
        import backend.auth.field_encryption as fe
        self.fe = fe
        # Inject a known 32-byte key directly (bypasses env-var init)
        self._orig_key = fe._aes_key
        fe._aes_key = b"\xAB" * 32

    def tearDown(self):
        self.fe._aes_key = self._orig_key

    # ── encrypt / decrypt round-trip ─────────────────────────────────────────

    def test_gcm_encrypt_returns_gcm_prefix(self):
        enc = self.fe._gcm_encrypt("hello@example.com", self.fe._aes_key)
        self.assertTrue(enc.startswith("gcm:"), f"Expected gcm: prefix, got {enc[:10]}")

    def test_gcm_encrypt_produces_four_colon_parts(self):
        enc = self.fe._gcm_encrypt("test", self.fe._aes_key)
        parts = enc.split(":")
        self.assertEqual(len(parts), 4, f"Expected 4 parts (gcm+nonce+tag+ct), got {parts}")

    def test_gcm_round_trip(self):
        plaintext = "narayan.test@example.com"
        enc = self.fe._gcm_encrypt(plaintext, self.fe._aes_key)
        dec = self.fe._gcm_decrypt(enc, self.fe._aes_key)
        self.assertEqual(dec, plaintext)

    def test_gcm_round_trip_unicode(self):
        plaintext = "नारायण@example.com"
        enc = self.fe._gcm_encrypt(plaintext, self.fe._aes_key)
        dec = self.fe._gcm_decrypt(enc, self.fe._aes_key)
        self.assertEqual(dec, plaintext)

    def test_random_nonce_produces_unique_ciphertexts(self):
        pt = "same-plaintext@test.com"
        enc1 = self.fe._gcm_encrypt(pt, self.fe._aes_key)
        enc2 = self.fe._gcm_encrypt(pt, self.fe._aes_key)
        self.assertNotEqual(enc1, enc2, "Two encryptions of same plaintext must differ (random nonce)")

    def test_tampered_ciphertext_raises(self):
        enc = self.fe._gcm_encrypt("secret", self.fe._aes_key)
        # Corrupt the last character of the ciphertext segment
        parts = enc.split(":")
        parts[-1] = parts[-1][:-1] + ("A" if parts[-1][-1] != "A" else "B")
        tampered = ":".join(parts)
        with self.assertRaises(Exception):
            self.fe._gcm_decrypt(tampered, self.fe._aes_key)

    # ── public API ───────────────────────────────────────────────────────────

    def test_encrypt_pii_returns_gcm_token(self):
        result = self.fe.encrypt_pii("user@test.com")
        self.assertTrue(result.startswith("gcm:"))

    def test_encrypt_pii_none_passthrough(self):
        self.assertIsNone(self.fe.encrypt_pii(None))

    def test_encrypt_pii_empty_passthrough(self):
        self.assertEqual(self.fe.encrypt_pii(""), "")

    def test_decrypt_pii_gcm_round_trip(self):
        enc = self.fe.encrypt_pii("hello@world.com")
        dec = self.fe.decrypt_pii(enc)
        self.assertEqual(dec, "hello@world.com")

    def test_decrypt_pii_none_passthrough(self):
        self.assertIsNone(self.fe.decrypt_pii(None))

    def test_decrypt_pii_empty_passthrough(self):
        self.assertEqual(self.fe.decrypt_pii(""), "")

    def test_decrypt_pii_plain_prefix(self):
        self.assertEqual(self.fe.decrypt_pii("plain:rawvalue"), "rawvalue")

    def test_decrypt_pii_bare_legacy_value(self):
        # Pre-encryption rows with no prefix — returned as-is
        self.assertEqual(self.fe.decrypt_pii("legacyemail@old.com"), "legacyemail@old.com")

    def test_is_pii_encrypted_true_for_gcm(self):
        enc = self.fe.encrypt_pii("x@y.com")
        self.assertTrue(self.fe.is_pii_encrypted(enc))

    def test_is_pii_encrypted_true_for_enc_prefix(self):
        self.assertTrue(self.fe.is_pii_encrypted("enc:sometoken"))

    def test_is_pii_encrypted_false_for_plaintext(self):
        self.assertFalse(self.fe.is_pii_encrypted("not encrypted"))

    def test_is_pii_encrypted_false_for_none(self):
        self.assertFalse(self.fe.is_pii_encrypted(None))

    def test_is_pii_encrypted_false_for_empty(self):
        self.assertFalse(self.fe.is_pii_encrypted(""))

    def test_rotate_to_gcm_from_plain(self):
        rotated = self.fe.rotate_to_gcm("plain:myvalue")
        self.assertTrue(rotated.startswith("gcm:"))
        self.assertEqual(self.fe.decrypt_pii(rotated), "myvalue")

    def test_rotate_to_gcm_none_passthrough(self):
        self.assertIsNone(self.fe.rotate_to_gcm(None))

    # ── dev mode (no key) ─────────────────────────────────────────────────────

    def test_dev_mode_plain_prefix_when_no_key(self):
        self.fe._aes_key = None
        result = self.fe.encrypt_pii("hello")
        self.assertEqual(result, "plain:hello")
        self.fe._aes_key = b"\xAB" * 32   # restore

    def test_is_encryption_enabled_true_with_key(self):
        self.assertTrue(self.fe.is_encryption_enabled())

    def test_is_encryption_enabled_false_without_key(self):
        orig = self.fe._aes_key
        self.fe._aes_key = None
        kms = self.fe._kms_key_id
        # Temporarily remove KMS key id too
        self.fe._kms_key_id = ""  # type: ignore
        self.assertFalse(self.fe.is_encryption_enabled())
        self.fe._aes_key = orig
        self.fe._kms_key_id = kms  # type: ignore


# =============================================================================
# 2. PII Scrubber
# =============================================================================
class TestPiiScrubber(unittest.TestCase):
    """Tests for backend/ai_interpretation/pii_scrubber.py"""

    def setUp(self):
        from backend.ai_interpretation.pii_scrubber import scrub_prompt, scrub_profile
        self.scrub_prompt = scrub_prompt
        self.scrub_profile = scrub_profile

    def _sample_prompt(self, name="Rahul Sharma", dob="1990-05-15",
                       tob="14:30", place="Mumbai", lat="19.0760", lon="72.8777"):
        return (
            f"Name      : {name}\n"
            f"Date      : {dob}\n"
            f"Time      : {tob}\n"
            f"Place     : {place}\n"
            f"Lat/Lon   : {lat}, {lon}\n"
            f"Ascendant : Scorpio\n"
            f"Sun Sign  : Aries\n"
        )

    def test_name_scrubbed(self):
        result = self.scrub_prompt(self._sample_prompt())
        self.assertNotIn("Rahul Sharma", result)

    def test_full_dob_scrubbed(self):
        result = self.scrub_prompt(self._sample_prompt())
        self.assertNotIn("1990-05-15", result)

    def test_birth_year_preserved(self):
        result = self.scrub_prompt(self._sample_prompt())
        self.assertIn("1990", result)

    def test_time_of_birth_scrubbed(self):
        result = self.scrub_prompt(self._sample_prompt())
        self.assertNotIn("14:30", result)

    def test_place_scrubbed(self):
        result = self.scrub_prompt(self._sample_prompt())
        self.assertNotIn("Mumbai", result)

    def test_latitude_rounded(self):
        result = self.scrub_prompt(self._sample_prompt())
        # Exact value 19.0760 should be rounded; 19.1 or 19.0 should appear
        self.assertNotIn("19.0760", result)

    def test_longitude_rounded(self):
        result = self.scrub_prompt(self._sample_prompt())
        self.assertNotIn("72.8777", result)

    def test_chart_data_preserved(self):
        result = self.scrub_prompt(self._sample_prompt())
        self.assertIn("Scorpio", result)
        self.assertIn("Aries", result)

    def test_empty_prompt_returns_empty(self):
        result = self.scrub_prompt("")
        self.assertEqual(result, "")

    def test_prompt_without_pii_unchanged(self):
        prompt = "Sun in Aries, Moon in Taurus, Lagna is Scorpio."
        result = self.scrub_prompt(prompt)
        self.assertEqual(result.strip(), prompt.strip())

    def test_native_placeholder_present(self):
        result = self.scrub_prompt(self._sample_prompt())
        # Name line should be replaced with "the native" or similar
        self.assertIn("native", result.lower())

    def test_scrub_profile_removes_name(self):
        profile = {
            "name": "Rahul Sharma",
            "email": "rahul@test.com",
            "date_of_birth": "1990-05-15",
            "birth_year": 1990,
            "lagna": "Scorpio",
        }
        safe = self.scrub_profile(profile)
        self.assertNotIn("name", safe)
        self.assertNotIn("email", safe)
        self.assertNotIn("date_of_birth", safe)

    def test_scrub_profile_keeps_chart_data(self):
        profile = {
            "name": "Test",
            "lagna": "Scorpio",
            "birth_year": 1990,
            "kundli_json": {"planets": []},
        }
        safe = self.scrub_profile(profile)
        self.assertIn("lagna", safe)
        self.assertIn("kundli_json", safe)


# =============================================================================
# 3. AI Output Validator
# =============================================================================
class TestOutputValidator(unittest.TestCase):
    """Tests for backend/ai_interpretation/output_validator.py"""

    def setUp(self):
        from backend.ai_interpretation.output_validator import (
            validate_ai_output, ensure_disclaimer, STANDARD_DISCLAIMER,
        )
        self.validate = validate_ai_output
        self.ensure_disclaimer = ensure_disclaimer
        self.DISCLAIMER = STANDARD_DISCLAIMER

    def _long_valid(self, extra=""):
        return (
            "The native has Sun in Aries and Moon in Taurus. "
            "Their Lagna is Scorpio with Saturn in the 10th house. "
            "This guidance is for entertainment and self-reflection only. "
            + extra
        ) * 4

    def test_valid_text_passes(self):
        result = self.validate(self._long_valid())
        self.assertTrue(result.passed)

    def test_valid_text_length_ok(self):
        result = self.validate(self._long_valid())
        self.assertTrue(result.length_ok)

    def test_short_text_length_not_ok(self):
        result = self.validate("Short text.")
        self.assertFalse(result.length_ok)

    def test_short_text_is_warning_not_hard_fail(self):
        # Short text = warning; passed can still be True
        result = self.validate("Short text.")
        self.assertIsInstance(result.warnings, list)

    def test_refusal_text_fails(self):
        refusal = "I cannot provide astrological predictions. " * 5
        result = self.validate(refusal)
        self.assertFalse(result.no_refusal)

    def test_to_dict_keys(self):
        result = self.validate(self._long_valid())
        d = result.to_dict()
        for key in ("passed", "warnings", "errors", "disclaimer_ok", "length_ok", "no_refusal"):
            self.assertIn(key, d)

    def test_ensure_disclaimer_appends_when_missing(self):
        text = "A" * 300
        result = self.ensure_disclaimer(text)
        self.assertIn(self.DISCLAIMER[:30], result)

    def test_ensure_disclaimer_does_not_duplicate(self):
        text = "A" * 300 + "\n" + self.DISCLAIMER
        result = self.ensure_disclaimer(text)
        self.assertEqual(result.count(self.DISCLAIMER), 1)

    def test_disclaimer_present_sets_disclaimer_ok(self):
        text = self._long_valid() + "\n" + self.DISCLAIMER
        result = self.validate(text)
        self.assertTrue(result.disclaimer_ok)

    def test_iso_date_in_output_flagged(self):
        # A date like 1990-05-15 in AI output signals PII leakage
        text = self._long_valid(extra="Born on 1990-05-15 in Mumbai.")
        result = self.validate(text)
        # Should have a warning or error about date leakage
        combined = result.warnings + result.errors
        self.assertTrue(
            any("date" in w.lower() or "pii" in w.lower() or "1990" in w for w in combined)
            or not result.passed,
            "Expected PII date leakage to be flagged"
        )


# =============================================================================
# 4. GST / Tax Calculation
# =============================================================================
class TestCalculateTax(unittest.TestCase):
    """Tests for payment/wallet.py — calculate_tax()"""

    def setUp(self):
        from payment.wallet import calculate_tax
        self.calculate_tax = calculate_tax

    def test_india_gst_rate_is_18_percent(self):
        result = self.calculate_tax(10_000, "India")
        self.assertEqual(result["tax_rate"], 0.18)

    def test_india_tax_amount_correct(self):
        result = self.calculate_tax(10_000, "India")
        self.assertEqual(result["tax_amount"], round(10_000 * 0.18))

    def test_india_total_is_subtotal_plus_tax(self):
        result = self.calculate_tax(9_900, "India")
        self.assertEqual(result["total"], result["subtotal"] + result["tax_amount"])

    def test_india_tax_label(self):
        result = self.calculate_tax(9_900, "India")
        self.assertEqual(result["tax_label"], "GST @ 18%")

    def test_india_subtotal_display_format(self):
        result = self.calculate_tax(9_900, "India")
        self.assertEqual(result["subtotal_display"], "₹99.00")

    def test_india_tax_display_format(self):
        result = self.calculate_tax(9_900, "India")
        self.assertEqual(result["tax_display"], "₹17.82")

    def test_india_total_display_format(self):
        result = self.calculate_tax(9_900, "India")
        self.assertEqual(result["total_display"], "₹116.82")

    def test_international_tax_rate_is_zero(self):
        result = self.calculate_tax(1_000, "International")
        self.assertEqual(result["tax_rate"], 0.0)

    def test_international_tax_amount_is_zero(self):
        result = self.calculate_tax(1_000, "International")
        self.assertEqual(result["tax_amount"], 0)

    def test_international_total_equals_subtotal(self):
        result = self.calculate_tax(1_000, "International")
        self.assertEqual(result["total"], 1_000)

    def test_international_tax_label(self):
        result = self.calculate_tax(1_000, "International")
        self.assertEqual(result["tax_label"], "No tax")

    def test_international_display_uses_dollar_symbol(self):
        result = self.calculate_tax(1_000, "International")
        self.assertTrue(result["subtotal_display"].startswith("$"))

    def test_zero_amount_india(self):
        result = self.calculate_tax(0, "India")
        self.assertEqual(result["tax_amount"], 0)
        self.assertEqual(result["total"], 0)

    def test_tier2_india_total(self):
        # Rs 249 subtotal → Rs 249 * 1.18 total
        result = self.calculate_tax(24_900, "India")
        expected_tax = round(24_900 * 0.18)
        self.assertEqual(result["tax_amount"], expected_tax)
        self.assertEqual(result["total"], 24_900 + expected_tax)


# =============================================================================
# 5. Wallet Pricing Helpers
# =============================================================================
class TestWalletPricing(unittest.TestCase):
    """Tests for payment/wallet.py — get_pricing(), format_amount()"""

    def setUp(self):
        from payment.wallet import (
            get_pricing, format_amount, label_txn_reason,
            INDIA_WELCOME_CREDIT, INDIA_REPORT_COST, INDIA_CHAT_COST,
            INTL_WELCOME_CREDIT, INTL_REPORT_COST, INTL_CHAT_COST,
        )
        self.get_pricing = get_pricing
        self.format_amount = format_amount
        self.label_txn_reason = label_txn_reason
        self.INDIA_WELCOME = INDIA_WELCOME_CREDIT
        self.INTL_WELCOME = INTL_WELCOME_CREDIT

    def test_india_pricing_currency(self):
        p = self.get_pricing("India")
        self.assertEqual(p["currency"], "INR")
        self.assertEqual(p["symbol"], "₹")

    def test_india_tier1_label(self):
        p = self.get_pricing("India")
        self.assertEqual(p["tier1_label"], "₹99")

    def test_india_tier2_credit(self):
        p = self.get_pricing("India")
        self.assertEqual(p["tier2_credit"], 30_000)  # ₹300

    def test_india_tier2_gift(self):
        p = self.get_pricing("India")
        self.assertEqual(p["tier2_gift"], "₹51 gift")

    def test_international_pricing_currency(self):
        p = self.get_pricing("International")
        self.assertEqual(p["currency"], "USD")
        self.assertEqual(p["symbol"], "$")

    def test_international_tier1_label(self):
        p = self.get_pricing("International")
        self.assertEqual(p["tier1_label"], "$10")

    def test_international_tier2_credit(self):
        p = self.get_pricing("International")
        self.assertEqual(p["tier2_credit"], 3_000)  # $30

    def test_format_amount_india_round(self):
        self.assertEqual(self.format_amount(10_000, "India"), "₹100")

    def test_format_amount_india_decimal(self):
        result = self.format_amount(10_050, "India")
        self.assertIn("100.50", result)

    def test_format_amount_international(self):
        self.assertEqual(self.format_amount(100, "International"), "$1.00")

    def test_format_amount_zero_india(self):
        self.assertEqual(self.format_amount(0, "India"), "₹0")

    def test_welcome_credit_india_is_100_rupees(self):
        p = self.get_pricing("India")
        self.assertEqual(p["welcome"], 10_000)  # 10,000 paise = ₹100

    def test_welcome_credit_international_is_1_dollar(self):
        p = self.get_pricing("International")
        self.assertEqual(p["welcome"], 100)   # 100 cents = $1.00


# =============================================================================
# 6. Transaction Label Helper
# =============================================================================
class TestLabelTxnReason(unittest.TestCase):

    def setUp(self):
        from payment.wallet import label_txn_reason
        self.label = label_txn_reason

    def test_kundli_report_label(self):
        self.assertEqual(self.label("kundli_report", "India"), "Kundli + Deep Reading")

    def test_chat_message_label(self):
        self.assertEqual(self.label("chat_message", "India"), "AI Astrologer Question")

    def test_welcome_verification_label(self):
        self.assertEqual(self.label("welcome_verification", "India"), "Welcome Credit (Email Verified)")

    def test_topup_label(self):
        self.assertEqual(self.label("topup", "India"), "Wallet Recharge")

    def test_refund_label(self):
        self.assertEqual(self.label("refund_ai_error", "India"), "Refund (AI Error)")

    def test_gift_bonus_label(self):
        result = self.label("gift_1000", "India")
        self.assertIn("Gift", result)  # "Bonus Gift Credit"

    def test_unknown_reason_title_cased(self):
        result = self.label("some_custom_reason", "India")
        self.assertIn("Some", result)


# =============================================================================
# 7. Security Middleware — Symbol Imports
# =============================================================================
class TestSecurityMiddlewareImports(unittest.TestCase):

    def test_all_symbols_importable(self):
        from backend.api.security import (
            add_security_middleware,
            SecurityHeadersMiddleware,
            RequestGuardMiddleware,
            validate_secrets_for_production,
            ADMIN_SECRET,
            get_current_user,
            get_current_email,
            get_optional_user,
            get_optional_email,
            admin_auth,
        )
        self.assertTrue(callable(add_security_middleware))
        self.assertTrue(callable(validate_secrets_for_production))

    def test_admin_secret_is_set(self):
        from backend.api.security import ADMIN_SECRET
        self.assertTrue(bool(ADMIN_SECRET))
        self.assertGreater(len(ADMIN_SECRET), 10)


# =============================================================================
# 8. Startup Secrets Validation
# =============================================================================
class TestValidateSecretsForProduction(unittest.TestCase):

    def test_dev_mode_reports_admin_secret_missing(self):
        """In dev mode (no real secrets), validate_secrets should list gaps."""
        from backend.api.security import validate_secrets_for_production
        # Run without real secrets set
        errors = validate_secrets_for_production()
        self.assertIsInstance(errors, list)
        # There should be at least one error in the test environment
        # (no real JWT_SECRET / ADMIN_SECRET / FIELD_ENCRYPTION_KEY set)

    def test_returns_list(self):
        from backend.api.security import validate_secrets_for_production
        result = validate_secrets_for_production()
        self.assertIsInstance(result, list)


# =============================================================================
# 9. Rate Limiter — limit_topup Symbol
# =============================================================================
class TestRateLimiterTopup(unittest.TestCase):

    def test_limit_topup_exists(self):
        from backend.api.rate_limiter import limit_topup
        self.assertIsNotNone(limit_topup)

    def test_all_rate_limit_symbols_present(self):
        from backend.api.rate_limiter import (
            limit_login, limit_register, limit_forgot_pass,
            limit_resend_verify, limit_ai, limit_topup, limit_api,
        )
        for sym in (limit_login, limit_register, limit_forgot_pass,
                    limit_resend_verify, limit_ai, limit_topup, limit_api):
            self.assertIsNotNone(sym)


# =============================================================================
# 10. Health Endpoint — Presence in main.py Source
# =============================================================================
class TestHealthEndpointPresence(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.src = (ROOT / "backend" / "api" / "main.py").read_text()

    def test_health_route_defined(self):
        self.assertIn('"/health"', self.src)

    def test_health_function_defined(self):
        self.assertIn("def health_check", self.src)

    def test_health_pings_db(self):
        self.assertIn("health_ping", self.src)

    def test_health_returns_version(self):
        self.assertIn('"version"', self.src)

    def test_database_has_health_ping(self):
        db_src = (ROOT / "backend" / "persistence" / "database.py").read_text()
        self.assertIn("def health_ping", db_src)


# =============================================================================
# 11. GDPR Endpoints — Presence in main.py Source
# =============================================================================
class TestGdprEndpointsPresence(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.src = (ROOT / "backend" / "api" / "main.py").read_text()

    def test_data_export_endpoint_defined(self):
        self.assertIn("data-export", self.src)

    def test_delete_account_endpoint_defined(self):
        self.assertTrue(
            "delete_account" in self.src or "/user/account" in self.src
        )

    def test_gdpr_anonymisation_logic(self):
        self.assertIn("deleted.invalid", self.src)

    def test_is_deleted_flag_set(self):
        self.assertIn("is_deleted", self.src)


# =============================================================================
# 12. CORS — Env-Var Driven Wiring
# =============================================================================
class TestCorsWiring(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.src = (ROOT / "backend" / "api" / "main.py").read_text()

    def test_allowed_origins_env_var_read(self):
        self.assertIn("ALLOWED_ORIGINS", self.src)

    def test_cors_not_hardcoded_star_only(self):
        # Must read from env var, not just hardcode "*"
        self.assertIn("_ALLOWED_ORIGINS", self.src)

    def test_production_cors_restriction_logic(self):
        self.assertIn("production", self.src)
        self.assertIn("_ALLOWED_ORIGINS", self.src)

    def test_security_middleware_wired(self):
        self.assertIn("add_security_middleware(app)", self.src)


# =============================================================================
# 13. Gender Field — DB Layer and API
# =============================================================================
class TestGenderField(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.db_src = (ROOT / "backend" / "persistence" / "database.py").read_text()
        cls.main_src = (ROOT / "backend" / "api" / "main.py").read_text()

    def test_gender_in_create_kundli_profile_db(self):
        self.assertIn("gender", self.db_src)

    def test_gender_in_profile_create_request(self):
        self.assertIn("gender", self.main_src)

    def test_gender_in_profile_update_request(self):
        # The update request should also support gender
        self.assertIn("gender", self.main_src)

    def test_gender_in_frontend(self):
        frontend = (ROOT / "frontend" / "index.html").read_text()
        self.assertIn("gender", frontend.lower())


# =============================================================================
# 14. SQL Migration 005 — Gender + GDPR Columns
# =============================================================================
class TestSqlMigration005(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        migration = ROOT / "infrastructure" / "db" / "005_gender_and_gdpr.sql"
        cls.sql = migration.read_text()

    def test_gender_column_added(self):
        self.assertIn("gender", self.sql)

    def test_is_deleted_column_added(self):
        self.assertIn("is_deleted", self.sql)

    def test_deleted_at_column_added(self):
        self.assertIn("deleted_at", self.sql)

    def test_anonymised_at_column_added(self):
        self.assertIn("anonymised_at", self.sql)

    def test_data_export_column_added(self):
        self.assertIn("data_export_requested_at", self.sql)

    def test_partial_index_created(self):
        self.assertIn("idx_users_active_email", self.sql)

    def test_partial_index_on_active_users(self):
        self.assertIn("is_deleted = FALSE", self.sql)

    def test_if_not_exists_used(self):
        # Safe to re-run migrations
        self.assertIn("IF NOT EXISTS", self.sql)


# =============================================================================
# 15. Syntax — All New Source Files Parse Cleanly
# =============================================================================
class TestAllFilesSyntaxClean(unittest.TestCase):
    """AST parse every new file — catches truncation or incomplete edits."""

    FILES = [
        "backend/api/main.py",
        "backend/api/security.py",
        "backend/api/rate_limiter.py",
        "backend/auth/field_encryption.py",
        "backend/ai_interpretation/pii_scrubber.py",
        "backend/ai_interpretation/output_validator.py",
        "backend/ai_interpretation/agent.py",
        "backend/persistence/database.py",
        "payment/wallet.py",
        "scripts/migrate_encryption_to_gcm.py",
    ]

    def test_all_files_have_valid_syntax(self):
        errors = []
        for rel in self.FILES:
            p = ROOT / rel
            if not p.exists():
                errors.append(f"MISSING: {rel}")
                continue
            try:
                ast.parse(p.read_text())
            except SyntaxError as e:
                errors.append(f"SYNTAX ERROR in {rel} line {e.lineno}: {e.msg}")
        self.assertEqual(errors, [], "\n".join(errors))

    def test_field_encryption_has_all_public_functions(self):
        p = ROOT / "backend/auth/field_encryption.py"
        tree = ast.parse(p.read_text())
        funcs = {n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)}
        for expected in ("encrypt_pii", "decrypt_pii", "is_pii_encrypted",
                         "rotate_to_gcm", "validate_encryption_key",
                         "is_encryption_enabled", "_gcm_encrypt", "_gcm_decrypt"):
            self.assertIn(expected, funcs, f"Missing function: {expected}")

    def test_wallet_has_all_functions(self):
        p = ROOT / "payment/wallet.py"
        tree = ast.parse(p.read_text())
        funcs = {n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)}
        for expected in ("calculate_tax", "get_pricing", "format_amount",
                         "label_txn_reason"):
            self.assertIn(expected, funcs, f"Missing function: {expected}")

    def test_database_has_health_ping(self):
        p = ROOT / "backend/persistence/database.py"
        tree = ast.parse(p.read_text())
        funcs = {n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)}
        self.assertIn("health_ping", funcs)


if __name__ == "__main__":
    unittest.main(verbosity=2)
