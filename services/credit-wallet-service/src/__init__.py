"""
credit-wallet-service
=====================
Microservice for credit wallet management, atomic balance operations,
and immutable ledger tracking.

All amounts are stored as integer minor units to avoid floating-point errors:
  India:         paise  (₹1 = 100 paise)
  International: cents  ($1 = 100 cents)

Modules:
  wallet/wallet.py   — WalletService: balance, deduct, credit, refund
  ledger/database.py — Database access layer (SQLite now; PostgreSQL target)
  alerts/            — Low-balance threshold checks + notification triggers
  api/main.py        — FastAPI routes
"""
