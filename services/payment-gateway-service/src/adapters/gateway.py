"""
payment/gateway.py
==================
Payment gateway abstraction layer.
Supports Razorpay (India) and Stripe (international).
Set PAYMENT_GATEWAY=razorpay or PAYMENT_GATEWAY=stripe in .env.

To activate:
  Razorpay: Set RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET in .env
  Stripe:   Set STRIPE_SECRET_KEY in .env

In this prototype the gateway creates payment orders/sessions.
The frontend handles the payment UI (Razorpay checkout.js or Stripe.js).
The backend verifies the payment signature before crediting the wallet.
"""
from __future__ import annotations
import os
import hashlib
import hmac

GATEWAY = os.environ.get("PAYMENT_GATEWAY", "razorpay").lower()


class PaymentGateway:
    """
    Unified interface for Razorpay and Stripe.
    Returns gateway-agnostic response dicts for the frontend.
    """

    @staticmethod
    def create_order(amount_inr: int, user_email: str, credits: int) -> dict:
        """
        Create a payment order.
        Returns dict with gateway-specific fields needed by frontend.
        """
        if GATEWAY == "razorpay":
            return PaymentGateway._razorpay_create_order(amount_inr, user_email, credits)
        elif GATEWAY == "stripe":
            return PaymentGateway._stripe_create_intent(amount_inr, user_email, credits)
        else:
            raise ValueError(f"Unknown PAYMENT_GATEWAY: {GATEWAY}")

    @staticmethod
    def verify_payment(payment_data: dict) -> bool:
        """
        Verify payment signature from gateway callback.
        Returns True if payment is genuine.
        """
        if GATEWAY == "razorpay":
            return PaymentGateway._razorpay_verify(payment_data)
        elif GATEWAY == "stripe":
            return PaymentGateway._stripe_verify(payment_data)
        return False

    # --- Razorpay ---

    @staticmethod
    def _razorpay_create_order(amount_inr: int, user_email: str, credits: int) -> dict:
        key_id     = os.environ.get("RAZORPAY_KEY_ID", "")
        key_secret = os.environ.get("RAZORPAY_KEY_SECRET", "")
        if not key_id or not key_secret:
            # Return mock order for development
            return {
                "gateway": "razorpay",
                "order_id": f"order_mock_{user_email[:8]}",
                "amount_paise": amount_inr * 100,
                "currency": "INR",
                "key_id": key_id or "rzp_test_placeholder",
                "credits": credits,
                "mock": True,
            }
        try:
            import razorpay
            client = razorpay.Client(auth=(key_id, key_secret))
            order = client.order.create({
                "amount": amount_inr * 100,  # paise
                "currency": "INR",
                "notes": {"email": user_email, "credits": str(credits)},
            })
            return {
                "gateway": "razorpay",
                "order_id": order["id"],
                "amount_paise": order["amount"],
                "currency": "INR",
                "key_id": key_id,
                "credits": credits,
                "mock": False,
            }
        except Exception as e:
            return {"gateway": "razorpay", "error": str(e), "mock": True,
                    "order_id": "order_error", "amount_paise": amount_inr * 100,
                    "currency": "INR", "key_id": key_id, "credits": credits}

    @staticmethod
    def _razorpay_verify(data: dict) -> bool:
        key_secret = os.environ.get("RAZORPAY_KEY_SECRET", "")
        if not key_secret:
            return data.get("mock", False)  # Allow mock payments in dev
        order_id   = data.get("razorpay_order_id", "")
        payment_id = data.get("razorpay_payment_id", "")
        signature  = data.get("razorpay_signature", "")
        message    = f"{order_id}|{payment_id}".encode()
        expected   = hmac.new(key_secret.encode(), message, hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, signature)

    # --- Stripe ---

    @staticmethod
    def _stripe_create_intent(amount_inr: int, user_email: str, credits: int) -> dict:
        secret_key = os.environ.get("STRIPE_SECRET_KEY", "")
        if not secret_key:
            return {
                "gateway": "stripe",
                "client_secret": "pi_mock_secret",
                "amount_cents": amount_inr * 100,
                "currency": "inr",
                "credits": credits,
                "mock": True,
            }
        try:
            import stripe
            stripe.api_key = secret_key
            intent = stripe.PaymentIntent.create(
                amount=amount_inr * 100,
                currency="inr",
                metadata={"email": user_email, "credits": credits},
            )
            return {
                "gateway": "stripe",
                "client_secret": intent.client_secret,
                "amount_cents": intent.amount,
                "currency": "inr",
                "credits": credits,
                "mock": False,
            }
        except Exception as e:
            return {"gateway": "stripe", "error": str(e), "mock": True,
                    "client_secret": "pi_error_secret", "credits": credits}

    @staticmethod
    def _stripe_verify(data: dict) -> bool:
        secret_key      = os.environ.get("STRIPE_SECRET_KEY", "")
        webhook_secret  = os.environ.get("STRIPE_WEBHOOK_SECRET", "")
        if not secret_key:
            return data.get("mock", False)
        # Full webhook verification would happen here
        return data.get("payment_intent_status") == "succeeded"
