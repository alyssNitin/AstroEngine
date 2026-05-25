"""
backend/auth/oauth_apple.py
==============================
Apple Sign In for NarayanAstroReader.

Flow (server-side token verification):
  1. Frontend triggers Sign in with Apple (native or JS SDK)
  2. Apple returns an identity_token (JWT) to the frontend
  3. Frontend POSTs the identity_token to POST /auth/oauth/apple
  4. Backend fetches Apple's public keys, verifies the JWT signature + claims
  5. Backend upserts the user and returns our own JWT access+refresh token pair

Architecture §3 / SRS §3: Both Google OAuth and Apple OAuth are required.
Apple Sign In is mandatory for any app distributed through the App Store
(Apple Developer Program guidelines §4.8).

Configuration (in .env):
  APPLE_CLIENT_ID   — "Service ID" from Apple Developer Console
                      (for web: your Services ID, e.g. com.yourcompany.app.signin)
  APPLE_TEAM_ID     — 10-char Apple Team ID (found in Apple Developer account)
  APPLE_KEY_ID      — Key ID of your private key from Apple Developer Console
  APPLE_PRIVATE_KEY — PKCS#8 private key PEM string (for generating client_secret)
                      or set APPLE_PRIVATE_KEY_PATH to a file path

Install:
  pip install PyJWT cryptography requests

Usage::
  from backend.auth.oauth_apple import verify_apple_identity_token
  info = verify_apple_identity_token(identity_token)
  # info: {"email": str, "apple_user_id": str, "email_verified": bool}
"""
from __future__ import annotations

import json
import os
import time
import urllib.request
from typing import Optional

# ── Configuration ─────────────────────────────────────────────────────────────
APPLE_CLIENT_ID:   str = os.environ.get("APPLE_CLIENT_ID", "")
APPLE_TEAM_ID:     str = os.environ.get("APPLE_TEAM_ID", "")
APPLE_KEY_ID:      str = os.environ.get("APPLE_KEY_ID", "")
APPLE_PRIVATE_KEY: str = os.environ.get("APPLE_PRIVATE_KEY", "")
_APPLE_KEY_PATH:   str = os.environ.get("APPLE_PRIVATE_KEY_PATH", "")

# Apple's public keys endpoint (JWKS)
_APPLE_KEYS_URL = "https://appleid.apple.com/auth/keys"
_APPLE_ISSUER   = "https://appleid.apple.com"

# Cache Apple's public keys in-process (they rotate infrequently)
_key_cache: dict = {"keys": None, "fetched_at": 0.0}
_KEY_CACHE_TTL = 3600   # 1 hour


def _fetch_apple_public_keys() -> list[dict]:
    """Fetch Apple's JWKS public keys, with in-process caching."""
    now = time.time()
    if _key_cache["keys"] and now - _key_cache["fetched_at"] < _KEY_CACHE_TTL:
        return _key_cache["keys"]

    try:
        with urllib.request.urlopen(_APPLE_KEYS_URL, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            keys = data.get("keys", [])
            _key_cache["keys"] = keys
            _key_cache["fetched_at"] = now
            return keys
    except Exception as e:
        raise ValueError(f"Failed to fetch Apple public keys: {e}") from e


def _get_private_key() -> str:
    """Return Apple private key PEM string from env or file."""
    if APPLE_PRIVATE_KEY:
        return APPLE_PRIVATE_KEY.replace("\\n", "\n")
    if _APPLE_KEY_PATH and os.path.exists(_APPLE_KEY_PATH):
        with open(_APPLE_KEY_PATH) as f:
            return f.read()
    return ""


def verify_apple_identity_token(identity_token: str) -> dict:
    """
    Verify an Apple identity_token JWT and extract user information.

    Parameters
    ----------
    identity_token : str
        The JWT identity_token returned by Apple Sign In.

    Returns
    -------
    dict with keys:
      - apple_user_id : str  (Apple's stable user identifier — "sub" claim)
      - email         : str  (may be empty if user chose to hide email)
      - email_verified: bool
      - name          : str  (only present on first sign-in)

    Raises
    ------
    ValueError
        If the token is invalid, expired, or the signature cannot be verified.
    """
    try:
        import jwt as _jwt
        from jwt.algorithms import RSAAlgorithm
    except ImportError:
        raise ImportError(
            "PyJWT and cryptography are required for Apple OAuth. "
            "Install with: pip install PyJWT cryptography"
        )

    # Step 1: Decode header to get kid (key ID) without verification
    try:
        unverified_header = _jwt.get_unverified_header(identity_token)
    except Exception as e:
        raise ValueError(f"Could not decode Apple token header: {e}") from e

    kid = unverified_header.get("kid")
    if not kid:
        raise ValueError("Apple identity_token missing 'kid' header")

    # Step 2: Fetch Apple's public keys and find the matching key
    apple_keys = _fetch_apple_public_keys()
    matching_key = next((k for k in apple_keys if k.get("kid") == kid), None)
    if not matching_key:
        # Key might have rotated — clear cache and retry once
        _key_cache["keys"] = None
        apple_keys = _fetch_apple_public_keys()
        matching_key = next((k for k in apple_keys if k.get("kid") == kid), None)

    if not matching_key:
        raise ValueError(f"Apple public key with kid={kid!r} not found in JWKS")

    # Step 3: Convert JWK → RSA public key
    try:
        public_key = RSAAlgorithm.from_jwk(json.dumps(matching_key))
    except Exception as e:
        raise ValueError(f"Failed to construct Apple public key: {e}") from e

    # Step 4: Verify the JWT
    audience = APPLE_CLIENT_ID or None   # None disables audience check in dev
    try:
        payload = _jwt.decode(
            identity_token,
            public_key,
            algorithms=["RS256"],
            audience=audience,
            issuer=_APPLE_ISSUER,
            options={
                "verify_exp": True,
                "verify_aud": bool(audience),
            },
        )
    except _jwt.ExpiredSignatureError:
        raise ValueError("Apple identity_token has expired")
    except _jwt.InvalidAudienceError:
        raise ValueError(
            f"Apple token audience mismatch. "
            f"Expected APPLE_CLIENT_ID={APPLE_CLIENT_ID!r}"
        )
    except _jwt.InvalidIssuerError:
        raise ValueError("Apple token issuer mismatch")
    except _jwt.PyJWTError as e:
        raise ValueError(f"Apple token verification failed: {e}") from e

    # Step 5: Extract and validate claims
    apple_user_id = payload.get("sub", "")
    if not apple_user_id:
        raise ValueError("Apple token missing 'sub' claim")

    email          = payload.get("email", "")
    email_verified = payload.get("email_verified", False)
    # Apple sometimes returns email_verified as a string "true"
    if isinstance(email_verified, str):
        email_verified = email_verified.lower() == "true"

    return {
        "apple_user_id": apple_user_id,
        "email":         email,
        "email_verified": bool(email_verified),
        "name":          payload.get("name", ""),   # only on first sign-in
    }


def generate_apple_client_secret(ttl_seconds: int = 86400 * 180) -> str:
    """
    Generate a client_secret JWT for Apple's token endpoint.
    Required for server-side token exchange (not needed for identity_token verification).

    The client_secret is a JWT signed with your Apple private key (ES256).
    It expires after at most 6 months (Apple's max TTL).

    Parameters
    ----------
    ttl_seconds : int, default 180 days (Apple maximum)

    Returns
    -------
    str — signed JWT to use as client_secret in Apple token requests
    """
    try:
        import jwt as _jwt
    except ImportError:
        raise ImportError("PyJWT required: pip install PyJWT cryptography")

    private_key_pem = _get_private_key()
    if not private_key_pem:
        raise ValueError(
            "Apple private key not configured. "
            "Set APPLE_PRIVATE_KEY or APPLE_PRIVATE_KEY_PATH in .env"
        )
    if not APPLE_TEAM_ID:
        raise ValueError("APPLE_TEAM_ID not set in .env")
    if not APPLE_KEY_ID:
        raise ValueError("APPLE_KEY_ID not set in .env")
    if not APPLE_CLIENT_ID:
        raise ValueError("APPLE_CLIENT_ID not set in .env")

    now = int(time.time())
    headers = {"kid": APPLE_KEY_ID, "alg": "ES256"}
    claims = {
        "iss": APPLE_TEAM_ID,
        "iat": now,
        "exp": now + ttl_seconds,
        "aud": _APPLE_ISSUER,
        "sub": APPLE_CLIENT_ID,
    }

    return _jwt.encode(claims, private_key_pem, algorithm="ES256", headers=headers)
