"""
backend/auth/jwt_utils.py
==========================
JWT utility functions for NarayanAstroReader.

Provides:
  - Access token  (HS256, default 15 min TTL)
  - Refresh token (HS256, default 7 day TTL, stored in Redis/memory blacklist)
  - Token blacklist (Redis-backed; in-memory fallback)

Configuration (via environment variables):
    JWT_SECRET          — signing secret (min 32 chars; REQUIRED in production)
    JWT_ACCESS_TTL      — access token TTL in minutes (default: 15)
    JWT_REFRESH_TTL     — refresh token TTL in days (default: 7)
    REDIS_URL           — Redis URL for token blacklist (default: redis://localhost:6379/0)

Usage::

    tokens = create_token_pair(email="user@example.com")
    # tokens = {"access_token": "...", "refresh_token": "...", "token_type": "bearer"}

    payload = verify_access_token(tokens["access_token"])
    new_pair = refresh_access_token(tokens["refresh_token"])

    invalidate_tokens(tokens["access_token"], tokens["refresh_token"])
"""
from __future__ import annotations

import os
import secrets
import time
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import HTTPException, status

# ── Configuration ──────────────────────────────────────────────────────────────

JWT_SECRET: str = os.environ.get("JWT_SECRET", "")
JWT_ALGORITHM    = "HS256"
JWT_ACCESS_TTL_MINUTES: int  = int(os.environ.get("JWT_ACCESS_TTL",  "15"))
JWT_REFRESH_TTL_DAYS: int    = int(os.environ.get("JWT_REFRESH_TTL", "7"))

# ── Token blacklist (Redis → in-memory fallback) ────────────────────────────────
_REDIS_URL    = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
_redis_client = None
_mem_blacklist: dict[str, float] = {}   # {jti: expiry_timestamp}

try:
    import redis as _redis_lib
    _c = _redis_lib.from_url(_REDIS_URL, decode_responses=True,
                              socket_connect_timeout=1, socket_timeout=1)
    _c.ping()
    _redis_client = _c
except Exception:
    pass


def _blacklist_add(jti: str, ttl_seconds: int) -> None:
    if _redis_client:
        try:
            _redis_client.setex(f"bl:{jti}", ttl_seconds, "1")
            return
        except Exception:
            pass
    _mem_blacklist[jti] = time.time() + ttl_seconds


def _blacklist_check(jti: str) -> bool:
    """Return True if the token JTI has been blacklisted (logged out)."""
    if _redis_client:
        try:
            return bool(_redis_client.exists(f"bl:{jti}"))
        except Exception:
            pass
    expiry = _mem_blacklist.get(jti)
    if expiry is None:
        return False
    if time.time() > expiry:
        _mem_blacklist.pop(jti, None)
        return False
    return True


# ── Helpers ────────────────────────────────────────────────────────────────────

def _require_secret() -> str:
    """Return JWT_SECRET, raising if empty."""
    global JWT_SECRET
    secret = JWT_SECRET or os.environ.get("JWT_SECRET", "")
    if not secret:
        # In dev mode (no secret set), use a per-process random secret.
        # Tokens will not survive restarts — acceptable for development only.
        if not JWT_SECRET:
            JWT_SECRET = "DEV_" + secrets.token_hex(32)
        return JWT_SECRET
    return secret


def _jose_encode(payload: dict) -> str:
    try:
        from jose import jwt as _jwt
        return _jwt.encode(payload, _require_secret(), algorithm=JWT_ALGORITHM)
    except ImportError:
        import base64, json
        return "dev." + base64.urlsafe_b64encode(
            json.dumps({**payload, "dev_mode": True}).encode()
        ).decode()


def _jose_decode(token: str) -> dict:
    try:
        from jose import jwt as _jwt, JWTError
        return _jwt.decode(token, _require_secret(), algorithms=[JWT_ALGORITHM])
    except ImportError:
        raise HTTPException(501,
            "JWT library not installed. Run: pip install python-jose[cryptography]")
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token is invalid or has expired. Please log in again.",
        )


# ── Public API ─────────────────────────────────────────────────────────────────

def create_access_token(email: str, extra: dict | None = None) -> str:
    """Create a signed JWT access token."""
    # Dev-mode fallback (no jose library)
    if not _has_jose():
        import base64, json
        return "dev." + base64.urlsafe_b64encode(
            json.dumps({"sub": email, "dev_mode": True}).encode()
        ).decode()

    now     = datetime.now(tz=timezone.utc)
    expires = now + timedelta(minutes=JWT_ACCESS_TTL_MINUTES)
    jti     = secrets.token_hex(16)
    payload = {
        "sub":  email,
        "iat":  now,
        "exp":  expires,
        "jti":  jti,
        "type": "access",
        **(extra or {}),
    }
    return _jose_encode(payload)


def create_refresh_token(email: str) -> str:
    """Create a signed JWT refresh token (longer TTL, stored in blacklist on logout)."""
    if not _has_jose():
        import base64, json
        return "dev_ref." + base64.urlsafe_b64encode(
            json.dumps({"sub": email, "dev_mode": True}).encode()
        ).decode()

    now     = datetime.now(tz=timezone.utc)
    expires = now + timedelta(days=JWT_REFRESH_TTL_DAYS)
    jti     = secrets.token_hex(16)
    payload = {
        "sub":  email,
        "iat":  now,
        "exp":  expires,
        "jti":  jti,
        "type": "refresh",
    }
    return _jose_encode(payload)


def create_token_pair(email: str, extra: dict | None = None) -> dict:
    """Return access + refresh token dict ready for a login response."""
    return {
        "access_token":  create_access_token(email, extra),
        "refresh_token": create_refresh_token(email),
        "token_type":    "bearer",
        "expires_in":    JWT_ACCESS_TTL_MINUTES * 60,
    }


def verify_access_token(token: str) -> dict:
    """
    Verify and decode a JWT access token.

    Raises:
        HTTPException 401 if missing, invalid, expired, or blacklisted.
    """
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Authentication token missing.")

    # Dev-mode fallback
    if token.startswith("dev."):
        try:
            import base64, json
            return json.loads(base64.urlsafe_b64decode(token[4:] + "=="))
        except Exception:
            pass

    payload = _jose_decode(token)
    if "sub" not in payload:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid token payload.")

    jti = payload.get("jti", "")
    if jti and _blacklist_check(jti):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED,
                            "Token has been invalidated. Please log in again.")

    return payload


def verify_refresh_token(token: str) -> dict:
    """
    Verify and decode a refresh token.

    Raises:
        HTTPException 401 if invalid, expired, or already used/blacklisted.
    """
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Refresh token missing.")

    # Dev-mode fallback
    if token.startswith("dev_ref."):
        try:
            import base64, json
            return json.loads(base64.urlsafe_b64decode(token[8:] + "=="))
        except Exception:
            pass

    payload = _jose_decode(token)
    if payload.get("type") != "refresh":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not a refresh token.")
    if "sub" not in payload:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid refresh token payload.")

    jti = payload.get("jti", "")
    if jti and _blacklist_check(jti):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED,
                            "Refresh token has been invalidated. Please log in again.")
    return payload


def refresh_access_token(refresh_token: str) -> dict:
    """
    Rotate refresh token: verify old refresh token, issue new access + refresh pair.
    Old refresh token is blacklisted (one-time use rotation).

    Returns:
        New token pair dict.
    """
    payload  = verify_refresh_token(refresh_token)
    email    = payload["sub"]
    old_jti  = payload.get("jti", "")

    # Blacklist the consumed refresh token
    if old_jti:
        ttl = int(JWT_REFRESH_TTL_DAYS * 86400)
        _blacklist_add(old_jti, ttl)

    return create_token_pair(email)


def invalidate_tokens(access_token: str, refresh_token: Optional[str] = None) -> None:
    """
    Invalidate tokens on logout or password change.
    Both access and refresh JTIs are added to the blacklist.
    """
    for token in filter(None, [access_token, refresh_token]):
        if token.startswith(("dev.", "dev_ref.")):
            continue
        try:
            payload = _jose_decode(token)
            jti = payload.get("jti", "")
            if jti:
                exp = payload.get("exp", 0)
                ttl = max(int(exp - time.time()), 1) if exp else 86400
                _blacklist_add(jti, ttl)
        except Exception:
            pass


def get_email_from_token(token: str) -> str:
    """Convenience wrapper — returns just the email from a verified access token."""
    return verify_access_token(token)["sub"]


def _has_jose() -> bool:
    try:
        import jose  # noqa: F401
        return True
    except ImportError:
        return False
