"""
backend/auth/mfa.py
====================
TOTP-based Multi-Factor Authentication (MFA/2FA) for NarayanAstroReader.

Uses pyotp for RFC 6238 time-based one-time passwords (TOTP).
Compatible with Google Authenticator, Authy, and any TOTP app.

Public API:
    generate_mfa_setup(email)  -> {"secret": str, "otpauth_url": str, "qr_data_url": str}
    verify_totp(secret, code)  -> bool
    generate_backup_codes()    -> list[str]  (10 plain codes, store hashed)
    hash_backup_code(code)     -> str
    check_backup_code(code, hashed_list) -> int | None  (returns index if matched)
"""
from __future__ import annotations

import hashlib
import os
import secrets
import string
from typing import Optional


_APP_NAME = os.environ.get("MFA_APP_NAME", "NarayanAstroReader")
_TOTP_ISSUER = os.environ.get("MFA_ISSUER", _APP_NAME)


def _has_pyotp() -> bool:
    try:
        import pyotp  # noqa: F401
        return True
    except ImportError:
        return False


def generate_mfa_setup(email: str) -> dict:
    """
    Generate a new TOTP secret and provisioning URI for the given user.

    Returns::
        {
            "secret":       "BASE32SECRET...",   # store encrypted in DB
            "otpauth_url":  "otpauth://totp/...",
            "qr_data_url":  "data:image/svg+xml,...",  # inline SVG QR (or empty if lib missing)
        }

    Raises:
        RuntimeError if pyotp is not installed.
    """
    if not _has_pyotp():
        raise RuntimeError(
            "pyotp is required for MFA. Install it with: pip install pyotp"
        )
    import pyotp

    secret = pyotp.random_base32()
    totp   = pyotp.TOTP(secret)
    uri    = totp.provisioning_uri(name=email, issuer_name=_TOTP_ISSUER)

    # Try to generate a QR code SVG (requires qrcode library — optional)
    qr_data_url = _make_qr(uri)

    return {
        "secret":      secret,
        "otpauth_url": uri,
        "qr_data_url": qr_data_url,
    }


def verify_totp(secret: str, code: str) -> bool:
    """
    Verify a 6-digit TOTP code against the given base32 secret.
    Allows ±1 time-step (30s window) to account for clock skew.

    Returns True if valid, False otherwise.
    """
    if not _has_pyotp():
        return False
    if not secret or not code:
        return False
    import pyotp
    try:
        totp = pyotp.TOTP(secret)
        return totp.verify(code.strip(), valid_window=1)
    except Exception:
        return False


def generate_backup_codes(n: int = 10) -> list[str]:
    """
    Generate n single-use backup codes (8 chars each, alphanumeric).
    Store the hashed versions; return the plain codes to show the user ONCE.
    """
    alphabet = string.ascii_uppercase + string.digits
    return ["".join(secrets.choice(alphabet) for _ in range(8)) for _ in range(n)]


def hash_backup_code(code: str) -> str:
    """Hash a backup code for safe storage."""
    return hashlib.sha256(code.strip().upper().encode()).hexdigest()


def check_backup_code(plain_code: str, hashed_codes: list[str]) -> Optional[int]:
    """
    Check a plain backup code against a list of hashed codes.
    Returns the index of the matched code (so caller can remove it), or None.
    """
    h = hash_backup_code(plain_code)
    for i, stored in enumerate(hashed_codes):
        if secrets.compare_digest(h, stored):
            return i
    return None


def _make_qr(uri: str) -> str:
    """Try to render a QR code as a data: URL. Returns empty string if unavailable."""
    try:
        import qrcode
        import io, base64
        img = qrcode.make(uri)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        b64 = base64.b64encode(buf.getvalue()).decode()
        return f"data:image/png;base64,{b64}"
    except Exception:
        return ""
