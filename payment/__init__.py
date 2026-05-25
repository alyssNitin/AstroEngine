"""
payment/
========
Modular payment gateway and wallet system.
Currently supports: Razorpay (India), Stripe (international).
Gateway selection is driven by PAYMENT_GATEWAY env var.
"""
from payment.wallet import WalletService
from payment.gateway import PaymentGateway

__all__ = ["WalletService", "PaymentGateway"]
