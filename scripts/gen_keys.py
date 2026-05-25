#!/usr/bin/env python3
"""
scripts/gen_keys.py
===================
Generate all required secret keys for NarayanAstroReader.
Prints ready-to-paste .env lines. Never commit these to version control.

Usage:
    python3 scripts/gen_keys.py
"""
import secrets
import base64

try:
    from cryptography.fernet import Fernet
    fernet_key = Fernet.generate_key().decode()
except ImportError:
    # Fallback: generate a valid 32-byte base64url key manually
    raw = secrets.token_bytes(32)
    fernet_key = base64.urlsafe_b64encode(raw).decode()

jwt_secret   = secrets.token_hex(48)   # 96 hex chars = 384-bit key
admin_secret = secrets.token_hex(48)

print("# ── Copy these lines into your .env file ──────────────────────────")
print(f"JWT_SECRET={jwt_secret}")
print(f"ADMIN_SECRET={admin_secret}")
print(f"FIELD_ENCRYPTION_KEY={fernet_key}")
print("# ───────────────────────────────────────────────────────────────────")
print()
print("[OK] Keys generated. Keep these secret — never commit to git.")
