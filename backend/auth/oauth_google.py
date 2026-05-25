"""
backend/auth/oauth_google.py
==============================
Google OAuth2 sign-in for NarayanAstroReader.

Flow:
  1. Frontend loads Google Identity Services (GSI) and calls google.accounts.id.prompt()
  2. Google returns a JWT credential (ID token) to a JS callback
  3. Frontend POSTs the ID token to POST /auth/oauth/google
  4. Backend verifies the token with Google's public keys (via google-auth library)
  5. Backend upserts the user and returns our own JWT access+refresh token pair

Configuration (in .env):
    GOOGLE_CLIENT_ID     — OAuth 2.0 Client ID from Google Cloud Console
    GOOGLE_CLIENT_SECRET — Client secret (not needed for ID-token verification)

Install:
    pip install google-auth

Usage::
    from backend.auth.oauth_google import verify_google_id_token
    info = verify_google_id_token(credential)  # raises ValueError on failure
    # info: {"email": str, "name": str, "google_id": str, "picture": str}
"""
from __future__ import annotations

import os
from typing import Optional

GOOGLE_CLIENT_ID: str = os.environ.get("GOOGLE_CLIENT_ID", "")


def verify_google_id_token(credential: str) -> dict:
    """
    Verify a Google ID token (credential from GSI JS library).

    Returns::
        {"email": str, "name": str, "google_id": str, "picture": str,
         "email_verified": bool}

    Raises:
        ValueError  — token invalid, expired, or wrong audience
        RuntimeError — google-auth library not installed
    """
    if not GOOGLE_CLIENT_ID:
        raise ValueError(
            "GOOGLE_CLIENT_ID not configured. Set it in .env to enable Google sign-in."
        )
    try:
        from google.oauth2 import id_token as _id_token
        from google.auth.transport import requests as _requests
    except ImportError:
        raise RuntimeError(
            "google-auth is required for Google OAuth. "
            "Install with: pip install google-auth"
        )

    try:
        idinfo = _id_token.verify_oauth2_token(
            credential,
            _requests.Request(),
            GOOGLE_CLIENT_ID,
        )
    except Exception as exc:
        raise ValueError(f"Google token verification failed: {exc}") from exc

    if idinfo.get("aud") != GOOGLE_CLIENT_ID:
        raise ValueError("Token audience mismatch.")

    return {
        "email":          idinfo.get("email", ""),
        "name":           idinfo.get("name", ""),
        "google_id":      idinfo.get("sub", ""),
        "picture":        idinfo.get("picture", ""),
        "email_verified": bool(idinfo.get("email_verified", False)),
    }


def is_google_oauth_configured() -> bool:
    """Return True if GOOGLE_CLIENT_ID is set."""
    return bool(GOOGLE_CLIENT_ID)
