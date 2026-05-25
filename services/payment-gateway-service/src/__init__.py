"""
payment-gateway-service
=======================
PCI-DSS-scoped microservice for payment processing.

Supports Razorpay (India/UPI) and Stripe (International).
Card data never touches this service — gateway-hosted checkout only.

Modules:
  adapters/gateway.py           — Provider dispatcher
  adapters/razorpay_adapter.py  — Razorpay SDK integration (Phase 1-C)
  adapters/stripe_adapter.py    — Stripe SDK integration (Phase 1-C)
  upi/                          — UPI VPA, QR code, deep-link
  webhooks/                     — HMAC-verified idempotent webhook handler
  geo_pricing/pricing.py        — Region-aware credit pack definitions
  api/main.py                   — FastAPI routes
"""
