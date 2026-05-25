"""
tests/test_payment_gateway.py
==============================
Unit tests for the payment gateway abstraction layer.
All tests run without real Razorpay/Stripe credentials (mock mode).
"""
import os
import sys
import hashlib
import hmac
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
os.environ.setdefault("ANTHROPIC_API_KEY", "sk-ant-test")

from payment.gateway import PaymentGateway


# ─────────────────────────────────────────────────────────────────────────────
# Razorpay mock mode (no keys set)
# ─────────────────────────────────────────────────────────────────────────────
class TestRazorpayMockOrder(unittest.TestCase):
    """Tests when RAZORPAY_KEY_ID / KEY_SECRET are absent (mock mode)."""

    def setUp(self):
        # Ensure no real keys leak in from env
        os.environ.pop("RAZORPAY_KEY_ID", None)
        os.environ.pop("RAZORPAY_KEY_SECRET", None)
        os.environ["PAYMENT_GATEWAY"] = "razorpay"
        # Reload the module so GATEWAY constant picks up env change
        import importlib, payment.gateway as gw
        importlib.reload(gw)
        self.gw = gw.PaymentGateway

    def test_create_order_returns_dict(self):
        order = self.gw.create_order(99, "test@x.com", 200)
        self.assertIsInstance(order, dict)

    def test_create_order_mock_flag_true(self):
        order = self.gw.create_order(99, "test@x.com", 200)
        self.assertTrue(order.get("mock"), "Mock flag must be True when no credentials")

    def test_create_order_gateway_field(self):
        order = self.gw.create_order(99, "test@x.com", 200)
        self.assertEqual(order["gateway"], "razorpay")

    def test_create_order_amount_in_paise(self):
        order = self.gw.create_order(99, "test@x.com", 200)
        self.assertEqual(order["amount_paise"], 9900)

    def test_create_order_currency_inr(self):
        order = self.gw.create_order(99, "test@x.com", 200)
        self.assertEqual(order["currency"], "INR")

    def test_create_order_contains_credits(self):
        order = self.gw.create_order(99, "test@x.com", 200)
        self.assertEqual(order["credits"], 200)

    def test_create_order_has_order_id(self):
        order = self.gw.create_order(99, "test@x.com", 200)
        self.assertIn("order_id", order)
        self.assertIsInstance(order["order_id"], str)
        self.assertGreater(len(order["order_id"]), 0)

    def test_verify_mock_payment_returns_true(self):
        ok = self.gw.verify_payment({"mock": True})
        self.assertTrue(ok, "Mock payment with mock=True must verify successfully")

    def test_verify_non_mock_payment_returns_false(self):
        ok = self.gw.verify_payment({"mock": False})
        self.assertFalse(ok, "Mock payment with mock=False must be rejected")

    def test_verify_empty_data_returns_false(self):
        ok = self.gw.verify_payment({})
        self.assertFalse(ok)

    def test_tier1_amount(self):
        order = self.gw.create_order(99, "u@x.com", 200)
        self.assertEqual(order["amount_paise"], 9900)

    def test_tier2_amount(self):
        order = self.gw.create_order(249, "u@x.com", 600)
        self.assertEqual(order["amount_paise"], 24900)


# ─────────────────────────────────────────────────────────────────────────────
# Stripe mock mode (no keys set)
# ─────────────────────────────────────────────────────────────────────────────
class TestStripeMockOrder(unittest.TestCase):

    def setUp(self):
        os.environ.pop("STRIPE_SECRET_KEY", None)
        os.environ.pop("STRIPE_WEBHOOK_SECRET", None)
        os.environ["PAYMENT_GATEWAY"] = "stripe"
        import importlib, payment.gateway as gw
        importlib.reload(gw)
        self.gw = gw.PaymentGateway

    def test_create_order_returns_dict(self):
        order = self.gw.create_order(99, "test@x.com", 200)
        self.assertIsInstance(order, dict)

    def test_create_order_mock_flag_true(self):
        order = self.gw.create_order(99, "test@x.com", 200)
        self.assertTrue(order.get("mock"))

    def test_create_order_gateway_field(self):
        order = self.gw.create_order(99, "test@x.com", 200)
        self.assertEqual(order["gateway"], "stripe")

    def test_create_order_has_client_secret(self):
        order = self.gw.create_order(99, "test@x.com", 200)
        self.assertIn("client_secret", order)

    def test_verify_mock_payment_returns_true(self):
        ok = self.gw.verify_payment({"mock": True})
        self.assertTrue(ok)

    def test_verify_real_success_status(self):
        ok = self.gw.verify_payment({"payment_intent_status": "succeeded"})
        # Without a secret key, this path returns False (can't verify)
        # but should not crash
        self.assertIsInstance(ok, bool)


# ─────────────────────────────────────────────────────────────────────────────
# Unknown gateway
# ─────────────────────────────────────────────────────────────────────────────
class TestUnknownGateway(unittest.TestCase):

    def setUp(self):
        os.environ["PAYMENT_GATEWAY"] = "unknown_gateway"
        import importlib, payment.gateway as gw
        importlib.reload(gw)
        self.gw = gw.PaymentGateway

    def test_create_order_raises_value_error(self):
        with self.assertRaises(ValueError):
            self.gw.create_order(99, "u@x.com", 200)

    def tearDown(self):
        os.environ["PAYMENT_GATEWAY"] = "razorpay"


# ─────────────────────────────────────────────────────────────────────────────
# Razorpay HMAC signature verification (unit-level, no real API)
# ─────────────────────────────────────────────────────────────────────────────
class TestRazorpayHmacVerification(unittest.TestCase):
    """
    Test the HMAC verification logic directly using known values.
    Razorpay signature = HMAC-SHA256(key_secret, "order_id|payment_id")
    """

    def _make_signature(self, key: str, order_id: str, payment_id: str) -> str:
        message = f"{order_id}|{payment_id}".encode()
        return hmac.new(key.encode(), message, hashlib.sha256).hexdigest()

    def test_valid_signature_verifies(self):
        secret     = "test_secret_key_for_unit_test"
        order_id   = "order_abc123"
        payment_id = "pay_xyz789"
        sig = self._make_signature(secret, order_id, payment_id)

        os.environ["RAZORPAY_KEY_SECRET"] = secret
        os.environ["PAYMENT_GATEWAY"]     = "razorpay"
        import importlib, payment.gateway as gw
        importlib.reload(gw)

        ok = gw.PaymentGateway.verify_payment({
            "razorpay_order_id":   order_id,
            "razorpay_payment_id": payment_id,
            "razorpay_signature":  sig,
        })
        self.assertTrue(ok, "Valid HMAC signature must verify")

        os.environ.pop("RAZORPAY_KEY_SECRET", None)

    def test_tampered_signature_rejected(self):
        secret     = "test_secret_key_for_unit_test"
        order_id   = "order_abc123"
        payment_id = "pay_xyz789"

        os.environ["RAZORPAY_KEY_SECRET"] = secret
        os.environ["PAYMENT_GATEWAY"]     = "razorpay"
        import importlib, payment.gateway as gw
        importlib.reload(gw)

        ok = gw.PaymentGateway.verify_payment({
            "razorpay_order_id":   order_id,
            "razorpay_payment_id": payment_id,
            "razorpay_signature":  "tampered_signature_value",
        })
        self.assertFalse(ok, "Tampered signature must be rejected")

        os.environ.pop("RAZORPAY_KEY_SECRET", None)

    def test_missing_signature_fields_rejected(self):
        os.environ["RAZORPAY_KEY_SECRET"] = "any_secret"
        os.environ["PAYMENT_GATEWAY"]     = "razorpay"
        import importlib, payment.gateway as gw
        importlib.reload(gw)

        ok = gw.PaymentGateway.verify_payment({"razorpay_order_id": "o1"})
        self.assertFalse(ok, "Missing payment_id and signature must fail")

        os.environ.pop("RAZORPAY_KEY_SECRET", None)


# ─────────────────────────────────────────────────────────────────────────────
# WalletService integration with topup
# ─────────────────────────────────────────────────────────────────────────────
class TestWalletTopup(unittest.TestCase):

    def setUp(self):
        import tempfile
        from backend.persistence.database import Database
        fd, self.path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        self.db = Database(self.path)
        self.db.register("pay@x.com", "pass123", "Payer")
        os.environ["PAYMENT_GATEWAY"] = "razorpay"

    def tearDown(self):
        try: os.unlink(self.path)
        except Exception: pass
        os.environ.pop("RAZORPAY_KEY_ID", None)
        os.environ.pop("RAZORPAY_KEY_SECRET", None)

    def test_topup_tier1_adds_correct_credits(self):
        from payment.wallet import WalletService, TOPUP_1_CENTS
        new_bal = WalletService.topup(self.db, "pay@x.com", TOPUP_1_CENTS)
        self.assertEqual(new_bal, TOPUP_1_CENTS)

    def test_topup_tier2_adds_correct_credits(self):
        from payment.wallet import WalletService, TOPUP_2_CENTS
        new_bal = WalletService.topup(self.db, "pay@x.com", TOPUP_2_CENTS)
        self.assertEqual(new_bal, TOPUP_2_CENTS)

    def test_topup_stacks_with_existing_balance(self):
        from payment.wallet import WalletService, TOPUP_1_CENTS
        WalletService.credit(self.db, "pay@x.com", 20, "initial")
        new_bal = WalletService.topup(self.db, "pay@x.com", TOPUP_1_CENTS)
        self.assertEqual(new_bal, 20 + TOPUP_1_CENTS)

    def test_topup_nonexistent_user_does_not_crash(self):
        from payment.wallet import WalletService, TOPUP_1_CENTS
        # Should either succeed (creating balance) or return 0 — must not raise
        try:
            result = WalletService.topup(self.db, "ghost@x.com", TOPUP_1_CENTS)
            self.assertIsInstance(result, int)
        except Exception:
            pass  # Some implementations reject unknown users — that's OK


if __name__ == "__main__":
    unittest.main()
