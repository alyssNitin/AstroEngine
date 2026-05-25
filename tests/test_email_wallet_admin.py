"""
tests/test_email_wallet_admin.py
==================================
Tests for Scenario 1 (Email Verification, Wallet Cents, Chat Billing)
and Scenario 2 (Super Admin helpers).
"""
import os, sys, tempfile, unittest
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
os.environ.setdefault("ANTHROPIC_API_KEY", "sk-ant-test")

from backend.persistence.database import Database, WELCOME_CREDIT_CENTS, CHAT_COST_CENTS, REPORT_COST_CENTS
from backend.auth.email_service import EmailService
from payment.wallet import WalletService


def _tmpdb():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    return Database(path), path


# ─────────────────────────────────────────────────────────────────────────────
# Email Verification
# ─────────────────────────────────────────────────────────────────────────────
class TestEmailVerification(unittest.TestCase):

    def setUp(self):
        self.db, self.path = _tmpdb()

    def tearDown(self):
        try: os.unlink(self.path)
        except Exception: pass

    def test_register_creates_token_unverified(self):
        r = self.db.register("t@x.com", "pass123", "Test")
        self.assertTrue(r["success"])
        p = self.db.get_profile("t@x.com")
        self.assertEqual(p["email_verified"], 0)
        self.assertIsNotNone(p["verification_token"])
        self.assertEqual(p["wallet_balance_cents"], 0)

    def test_verify_valid_token_credits_wallet(self):
        r  = self.db.register("v@x.com", "pass123", "V")
        tok = r["verification_token"]
        rv  = self.db.verify_email(tok)
        self.assertTrue(rv["success"])
        p = self.db.get_profile("v@x.com")
        self.assertEqual(p["email_verified"], 1)
        self.assertEqual(p["wallet_balance_cents"], WELCOME_CREDIT_CENTS)
        self.assertIsNone(p["verification_token"])

    def test_verify_invalid_token_returns_error(self):
        rv = self.db.verify_email("not-a-real-token")
        self.assertFalse(rv["success"])
        self.assertEqual(rv["error"], "invalid_token")

    def test_verify_already_verified_blocked(self):
        r   = self.db.register("av@x.com", "pass123")
        tok = r["verification_token"]
        self.db.verify_email(tok)
        rv2 = self.db.verify_email(tok)
        # token is now NULL, so returns invalid_token (already cleared)
        self.assertFalse(rv2["success"])

    def test_no_double_credit_on_second_verify(self):
        r   = self.db.register("dc@x.com", "pass123")
        tok = r["verification_token"]
        self.db.verify_email(tok)
        # Manually try to call verify again with dummy token — should not add more
        self.db.verify_email("dummy")
        p = self.db.get_profile("dc@x.com")
        self.assertEqual(p["wallet_balance_cents"], WELCOME_CREDIT_CENTS)

    def test_resend_generates_new_token(self):
        r    = self.db.register("rs@x.com", "pass123", "Rs")
        old  = r["verification_token"]
        rv   = self.db.resend_verification("rs@x.com")
        self.assertTrue(rv["success"])
        new  = rv["token"]
        self.assertNotEqual(old, new)
        # Old token no longer valid
        chk = self.db.verify_email(old)
        self.assertFalse(chk["success"])

    def test_resend_rate_limit(self):
        self.db.register("rl@x.com", "pass123")
        for _ in range(3):
            self.db.resend_verification("rl@x.com")
        rv = self.db.resend_verification("rl@x.com")
        self.assertFalse(rv["success"])
        self.assertEqual(rv["error"], "rate_limited")

    def test_resend_already_verified(self):
        r   = self.db.register("rav@x.com", "pass123")
        tok = r["verification_token"]
        self.db.verify_email(tok)
        rv = self.db.resend_verification("rav@x.com")
        self.assertFalse(rv["success"])
        self.assertEqual(rv["error"], "already_verified")

    def test_email_service_mock_mode(self):
        """Mock mode should not raise and should return True."""
        import backend.auth.email_service as _es
        original = _es._SMTP_CONFIGURED
        _es._SMTP_CONFIGURED = False   # Force mock mode regardless of .env
        try:
            ok = EmailService.send_verification("t@x.com", "T", "fake-token")
            self.assertTrue(ok)
        finally:
            _es._SMTP_CONFIGURED = original


# ─────────────────────────────────────────────────────────────────────────────
# Wallet — cent model
# ─────────────────────────────────────────────────────────────────────────────
class TestWalletCents(unittest.TestCase):

    def setUp(self):
        self.db, self.path = _tmpdb()
        self.db.register("w@x.com", "pass123", "W")

    def tearDown(self):
        try: os.unlink(self.path)
        except Exception: pass

    def test_initial_balance_zero(self):
        self.assertEqual(WalletService.get_balance(self.db, "w@x.com"), 0)

    def test_credit_adds_cents(self):
        WalletService.credit(self.db, "w@x.com", 20, "test")
        self.assertEqual(WalletService.get_balance(self.db, "w@x.com"), 20)

    def test_debit_success(self):
        WalletService.credit(self.db, "w@x.com", 50)
        ok, rem = WalletService.debit(self.db, "w@x.com", 20, "test")
        self.assertTrue(ok)
        self.assertEqual(rem, 30)

    def test_debit_fails_insufficient(self):
        WalletService.credit(self.db, "w@x.com", 10)
        ok, rem = WalletService.debit(self.db, "w@x.com", 20, "test")
        self.assertFalse(ok)
        self.assertEqual(rem, 10)

    def test_balance_never_negative(self):
        ok, rem = WalletService.debit(self.db, "w@x.com", 20)
        self.assertFalse(ok)
        self.assertEqual(rem, 0)

    def test_refund_restores_balance(self):
        WalletService.credit(self.db, "w@x.com", 20)
        WalletService.debit(self.db, "w@x.com", 5)
        WalletService.refund(self.db, "w@x.com", 5)
        self.assertEqual(WalletService.get_balance(self.db, "w@x.com"), 20)

    def test_welcome_credit_via_verify(self):
        r   = self.db.register("wc@x.com", "pass123")
        tok = r["verification_token"]
        rv  = self.db.verify_email(tok)
        self.assertEqual(rv["wallet_balance_cents"], WELCOME_CREDIT_CENTS)

    def test_report_cost_cents_constant(self):
        self.assertEqual(REPORT_COST_CENTS, 20)

    def test_chat_cost_cents_constant(self):
        self.assertEqual(CHAT_COST_CENTS, 5)

    def test_format_dollars(self):
        self.assertEqual(WalletService.format_dollars(20),  "$0.20")
        self.assertEqual(WalletService.format_dollars(100), "$1.00")
        self.assertEqual(WalletService.format_dollars(5),   "$0.05")
        self.assertEqual(WalletService.format_dollars(0),   "$0.00")

    def test_topup_adds_credits(self):
        new_bal = WalletService.topup(self.db, "w@x.com", 100)
        self.assertEqual(new_bal, 100)

    def test_can_afford_report(self):
        WalletService.credit(self.db, "w@x.com", 20)
        self.assertTrue(WalletService.can_afford_report(self.db, "w@x.com"))

    def test_cannot_afford_report(self):
        WalletService.credit(self.db, "w@x.com", 10)
        self.assertFalse(WalletService.can_afford_report(self.db, "w@x.com"))

    def test_can_afford_chat(self):
        WalletService.credit(self.db, "w@x.com", 5)
        self.assertTrue(WalletService.can_afford_chat(self.db, "w@x.com"))

    def test_cannot_afford_chat(self):
        self.assertFalse(WalletService.can_afford_chat(self.db, "w@x.com"))


# ─────────────────────────────────────────────────────────────────────────────
# Admin helpers
# ─────────────────────────────────────────────────────────────────────────────
class TestAdminHelpers(unittest.TestCase):

    def setUp(self):
        self.db, self.path = _tmpdb()
        self.db.register("a@x.com", "pass123", "A")
        self.db.register("b@x.com", "pass123", "B")

    def tearDown(self):
        try: os.unlink(self.path)
        except Exception: pass

    def test_get_stats_counts_users(self):
        stats = self.db.get_stats()
        self.assertGreaterEqual(stats["total_users"], 2)

    def test_get_stats_verified_count(self):
        r   = self.db.register("sv@x.com", "pass123")
        tok = r["verification_token"]
        self.db.verify_email(tok)
        stats = self.db.get_stats()
        self.assertGreaterEqual(stats["verified_users"], 1)

    def test_force_verify_grants_credit(self):
        ok = self.db.force_verify_email("a@x.com")
        self.assertTrue(ok)
        p  = self.db.get_profile("a@x.com")
        self.assertEqual(p["email_verified"], 1)
        self.assertEqual(p["wallet_balance_cents"], WELCOME_CREDIT_CENTS)

    def test_force_verify_already_verified_idempotent(self):
        r   = self.db.register("fv2@x.com", "pass123")
        tok = r["verification_token"]
        self.db.verify_email(tok)
        ok = self.db.force_verify_email("fv2@x.com")
        self.assertTrue(ok)
        p  = self.db.get_profile("fv2@x.com")
        # Should not double-credit
        self.assertEqual(p["wallet_balance_cents"], WELCOME_CREDIT_CENTS)

    def test_run_query_select_allowed(self):
        rows = self.db.run_query("SELECT email FROM users")
        self.assertIsInstance(rows, list)
        self.assertTrue(any(r["email"] == "a@x.com" for r in rows))

    def test_run_query_delete_blocked(self):
        with self.assertRaises(ValueError):
            self.db.run_query("DELETE FROM users")

    def test_run_query_insert_blocked(self):
        with self.assertRaises(ValueError):
            self.db.run_query("INSERT INTO users (email) VALUES ('hack@x.com')")

    def test_run_query_drop_blocked(self):
        with self.assertRaises(ValueError):
            self.db.run_query("SELECT * FROM users; DROP TABLE users")

    def test_get_all_users_returns_list(self):
        users = self.db.get_all_users()
        self.assertIsInstance(users, list)
        self.assertGreaterEqual(len(users), 2)

    def test_get_all_users_search(self):
        users = self.db.get_all_users(search="a@x.com")
        emails = [u["email"] for u in users]
        self.assertIn("a@x.com", emails)

    def test_admin_wallet_credit(self):
        self.db.credit_wallet_cents("a@x.com", 50, "admin: test credit reason")
        self.assertEqual(self.db.get_wallet_balance_cents("a@x.com"), 50)

    def test_admin_wallet_debit(self):
        self.db.credit_wallet_cents("a@x.com", 50)
        ok, rem = self.db.debit_wallet_cents("a@x.com", 30, "admin: test debit reason")
        self.assertTrue(ok)
        self.assertEqual(rem, 20)

    def test_delete_user(self):
        self.db.register("del@x.com", "pass123")
        deleted = self.db.delete_user("del@x.com")
        self.assertTrue(deleted)
        self.assertIsNone(self.db.get_profile("del@x.com"))


if __name__ == "__main__":
    unittest.main()
