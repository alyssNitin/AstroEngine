"""
tests/conftest.py
=================
Global pytest configuration for NarayanAstroReader.

Sets up sys.path, mandatory environment variables, and shared fixtures
so every test module can import project code without boilerplate.

Executed automatically by pytest before any test collection.
"""
from __future__ import annotations

import os
import sys

# ── 1. Resolve project root ───────────────────────────────────────────────────
# tests/ lives one level below the project root.
_TESTS_DIR   = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_TESTS_DIR)

# Insert project root so `import backend.xxx`, `import payment.xxx`, etc. work.
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

# ── 2. Mandatory environment variables (safe test defaults) ───────────────────
# These must be set BEFORE any project module is imported because several
# modules read env vars at import time (e.g. jwt_utils.py, security.py).
_TEST_ENV = {
    # Auth
    "JWT_SECRET":       "test_secret_for_critical_tests_min_32_chars_ok",
    "ADMIN_PASSWORD":   "test_admin_password_for_ci_min_32_chars_abcd",
    # Runtime environment — never "production" in tests
    "ENVIRONMENT":      "test",
    # Payment
    "PAYMENT_GATEWAY":  "razorpay",
    "RAZORPAY_KEY_ID":  "rzp_test_key_id_placeholder",
    "RAZORPAY_SECRET_KEY": "test_razorpay_secret",
    # AI (no real calls in unit tests)
    "ANTHROPIC_API_KEY": "sk-ant-test-placeholder",
    # Database (SQLite in-memory for unit tests)
    "DATABASE_URL":     "sqlite:///./test.db",
    # CORS
    "ALLOWED_ORIGINS":  "http://localhost:3000",
    # Email (disabled)
    "SMTP_HOST":        "localhost",
    "SMTP_PORT":        "25",
}

for key, value in _TEST_ENV.items():
    os.environ.setdefault(key, value)

# ── 3. dasha-engine Python-path shim ────────────────────────────────────────
# services/dasha-engine has a hyphen — not importable as a Python module name.
# The shim at services/dasha_engine/ re-exports from the real directory.
# Ensure the shim package is discoverable (already covered by _PROJECT_ROOT
# being in sys.path, but make it explicit here for clarity).
_DASHA_ENGINE_SRC = os.path.join(_PROJECT_ROOT, "services", "dasha-engine", "src")
if _DASHA_ENGINE_SRC not in sys.path:
    # Add so tests that import 'systems.vimshottari' directly also work.
    sys.path.insert(1, _DASHA_ENGINE_SRC)
