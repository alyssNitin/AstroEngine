"""
backend/api/security.py
========================
Centralised security utilities for NarayanAstroReader FastAPI app.

Provides:
  - get_current_user              : FastAPI Depends — validates Bearer JWT
  - get_current_email             : Convenience — extracts email from token
  - get_optional_user / email     : Returns None for unauthenticated requests
  - admin_auth                    : FastAPI Depends — validates admin secret
  - validate_secrets_for_production: Startup health check for all secrets
  - ADMIN_SECRET                  : env-var-driven admin secret key
"""
from __future__ import annotations

import os
import secrets
import time

from fastapi import Cookie, Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from backend.auth.jwt_utils import verify_access_token

# ── Admin secret ──────────────────────────────────────────────────────────────
_KNOWN_WEAK_ADMIN_SECRETS = {
    "",
    "narayan-admin-dev-secret-change-me",
    "changeme",
    "secret",
    "admin",
    "password",
}

_raw_admin_secret: str = (
    os.environ.get("ADMIN_SECRET", "")
    or os.environ.get("ADMIN_PASSWORD", "")
)

if not _raw_admin_secret:
    import sys as _sys
    _raw_admin_secret = "DEV_ADMIN_" + secrets.token_hex(24)
    print(
        f"\n[security] WARNING: Neither ADMIN_SECRET nor ADMIN_PASSWORD is set.\n"
        f"           Using per-process random secret (dev only).\n",
        file=_sys.stderr,
    )
else:
    import sys as _sys
    src = "ADMIN_SECRET" if os.environ.get("ADMIN_SECRET") else "ADMIN_PASSWORD"
    print(f"[security] Admin secret loaded from {src}.", file=_sys.stderr)

ADMIN_SECRET: str = _raw_admin_secret
ADMIN_USERNAME: str = os.environ.get("ADMIN_USERNAME", "admin")


def validate_secrets_for_production() -> list[str]:
    """
    Check that all required secrets are properly configured.
    Returns a list of error strings (empty = all good).
    """
    errors: list[str] = []

    if ADMIN_SECRET.startswith("DEV_ADMIN_"):
        errors.append("ADMIN_SECRET not set — set a strong random value in .env")
    elif ADMIN_SECRET.lower() in _KNOWN_WEAK_ADMIN_SECRETS:
        errors.append("ADMIN_SECRET is a weak/example value — set a strong random value")
    elif len(ADMIN_SECRET) < 32:
        errors.append("ADMIN_SECRET is too short — must be at least 32 characters")

    try:
        from backend.auth.jwt_utils import JWT_SECRET as _jwt_secret
        _weak_jwt = {"", "changeme", "secret", "dev", "test", "narayan", "password"}
        if not _jwt_secret or _jwt_secret.startswith("DEV_"):
            errors.append(
                "JWT_SECRET not set — CRITICAL: all tokens are trivially forgeable. "
                "Generate with: python -c \"import secrets; print(secrets.token_hex(32))\""
            )
        elif _jwt_secret.lower() in _weak_jwt:
            errors.append("JWT_SECRET is a well-known weak value — set a cryptographically random value (>=32 chars)")
        elif len(_jwt_secret) < 32:
            errors.append(f"JWT_SECRET is too short ({len(_jwt_secret)} chars) — must be at least 32 characters")
    except Exception as exc:
        errors.append(f"Could not check JWT_SECRET: {exc}")

    _env = os.environ.get("ENVIRONMENT", "development").lower()
    _allowed_origins = os.environ.get("ALLOWED_ORIGINS", "")
    if _env == "production":
        if not _allowed_origins or _allowed_origins.strip() == "*":
            errors.append(
                "ALLOWED_ORIGINS is not set or is wildcard '*' in production — "
                "set ALLOWED_ORIGINS=https://yourdomain.com in .env to restrict CORS"
            )
        else:
            for origin in [o.strip() for o in _allowed_origins.split(",") if o.strip()]:
                if not (origin.startswith("https://") or origin.startswith("http://localhost")):
                    errors.append(
                        f"ALLOWED_ORIGINS contains non-HTTPS origin '{origin}' — "
                        "production origins must use HTTPS"
                    )

    try:
        from backend.auth.field_encryption import validate_encryption_key
        errors.extend(validate_encryption_key())
    except Exception as exc:
        errors.append(f"Could not check FIELD_ENCRYPTION_KEY: {exc}")

    return errors


def validate_production_blockers() -> None:
    """
    Hard-fail the process if any BLOCKER-level security configuration is wrong.
    Raises SystemExit(1) in production if secrets are misconfigured.
    Satisfies Arch §9.2 B-SEC-1 and Arch §9.3 B-SEC-2.
    """
    import sys
    _env = os.environ.get("ENVIRONMENT", "development").lower()
    if _env != "production":
        return

    errors = validate_secrets_for_production()
    if errors:
        print("\n" + "=" * 70, file=sys.stderr)
        print("FATAL: Production security configuration is INVALID.", file=sys.stderr)
        print("The application will NOT start until these are resolved:", file=sys.stderr)
        for i, e in enumerate(errors, 1):
            print(f"  [{i}] {e}", file=sys.stderr)
        print("=" * 70 + "\n", file=sys.stderr)
        sys.exit(1)


# ── Bearer scheme ─────────────────────────────────────────────────────────────
_bearer = HTTPBearer(auto_error=False)

# ── Brute-force tracker for admin endpoints ───────────────────────────────────
_admin_fails: dict[str, list[float]] = {}
_ADMIN_LOCKOUT_WINDOW = 900   # 15 minutes
_ADMIN_MAX_FAILS      = 5


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> dict:
    """FastAPI dependency — verifies Bearer JWT and returns decoded payload."""
    if credentials is None or not credentials.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required. Please log in.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return verify_access_token(credentials.credentials)


def get_current_email(payload: dict = Depends(get_current_user)) -> str:
    """Convenience dependency — returns just the email string from the token."""
    return payload["sub"]


def get_optional_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> dict | None:
    """Like get_current_user but returns None instead of raising 401."""
    if credentials is None or not credentials.credentials:
        return None
    try:
        return verify_access_token(credentials.credentials)
    except HTTPException:
        return None


def get_optional_email(payload: dict | None = Depends(get_optional_user)) -> str:
    """Returns email or empty string for optional-auth endpoints."""
    return payload["sub"] if payload else ""


def admin_auth(
    request: Request,
    admin_token: str | None = Cookie(default=None, alias="admin_token"),
) -> None:
    """
    FastAPI dependency — authenticates admin requests.
    Accepts ADMIN_SECRET via Cookie (admin_token) or X-Admin-Secret header.
    Applies brute-force lockout: 5 failed attempts -> 15-minute block per IP.
    """
    ip = request.client.host if request.client else "unknown"
    now = time.time()

    fails = [t for t in _admin_fails.get(ip, []) if now - t < _ADMIN_LOCKOUT_WINDOW]
    if len(fails) >= _ADMIN_MAX_FAILS:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many failed admin attempts. Try again in 15 minutes.",
        )

    provided = admin_token or request.headers.get("X-Admin-Secret", "")

    if not provided or not secrets.compare_digest(provided, ADMIN_SECRET):
        fails.append(now)
        _admin_fails[ip] = fails
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid admin credentials.",
        )

    _admin_fails.pop(ip, None)


# ─────────────────────────────────────────────────────────────────────────────
# HTTP Security Middlewares
# ─────────────────────────────────────────────────────────────────────────────
import re as _re

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request as _StarletteRequest
from starlette.responses import Response as _StarletteResponse

_ENV = os.environ.get("ENVIRONMENT", "development").lower()
_IS_PROD = _ENV == "production"

_ADMIN_IP_ALLOWLIST_RAW = os.environ.get("ADMIN_IP_ALLOWLIST", "")
_ADMIN_IP_ALLOWLIST: list[str] = (
    [ip.strip() for ip in _ADMIN_IP_ALLOWLIST_RAW.split(",") if ip.strip()]
    if _ADMIN_IP_ALLOWLIST_RAW
    else []
)

MAX_REQUEST_BYTES = int(os.environ.get("MAX_REQUEST_BYTES", str(1 * 1024 * 1024)))

_SCANNER_UA_RE = _re.compile(
    r"(sqlmap|nikto|nmap|masscan|zgrab|nuclei|dirbuster|gobuster|wfuzz|"
    r"burpsuite|hydra|acunetix|netsparker|havij|openvas|metasploit|"
    r"python-requests/2\.[01]\.|go-http-client/1\.1|curl/7\.[0-5])",
    _re.IGNORECASE,
)

# Covers: ../ (Unix), ..\ (Windows), %2e%2e (URL-encoded), %252e (double-encoded),
# ..%5c (URL-encoded backslash — e.g. /..%5cetc), case-insensitive.
_PATH_TRAVERSAL_RE = _re.compile(r"(\.\./|\.\.\\|%2e%2e|%252e|\.\.%5c)", _re.IGNORECASE)


def _client_ip(request: _StarletteRequest) -> str:
    """Return the real client IP, honouring X-Forwarded-For when trusted."""
    xff = request.headers.get("x-forwarded-for", "")
    if xff:
        return xff.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """
    Adds hardened HTTP security headers to every response and removes
    server-fingerprinting headers (Server, X-Powered-By).
    """

    async def dispatch(
        self, request: _StarletteRequest, call_next
    ) -> _StarletteResponse:
        response: _StarletteResponse = await call_next(request)

        if _IS_PROD:
            response.headers["Strict-Transport-Security"] = (
                "max-age=31536000; includeSubDomains; preload"
            )

        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' https://accounts.google.com; "
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
            "font-src 'self' https://fonts.gstatic.com; "
            "img-src 'self' data: https:; "
            "connect-src 'self' https://accounts.google.com; "
            "frame-src https://accounts.google.com; "
            "frame-ancestors 'none'; "
            "base-uri 'self'; "
            "form-action 'self';"
        )

        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = (
            "geolocation=(), microphone=(), camera=(), "
            "payment=(), usb=(), magnetometer=(), gyroscope=()"
        )

        for _hdr in ("Server", "X-Powered-By"):
            if _hdr in response.headers:
                del response.headers[_hdr]

        return response


class RequestGuardMiddleware(BaseHTTPMiddleware):
    """
    Lightweight WAF-level request filtering:
      1. Blocks path-traversal attempts (../  %2e%2e  ..%5c  etc.)
      2. Blocks known scanner / bad-bot User-Agent strings
      3. Enforces admin IP allowlist for /admin/* paths
      4. Rejects request bodies larger than MAX_REQUEST_BYTES
    """

    async def dispatch(
        self, request: _StarletteRequest, call_next
    ) -> _StarletteResponse:
        from starlette.responses import JSONResponse

        path = request.url.path
        ua = request.headers.get("user-agent", "")

        if _PATH_TRAVERSAL_RE.search(path):
            return JSONResponse(
                {"detail": "Invalid request path."},
                status_code=400,
            )

        if ua and _SCANNER_UA_RE.search(ua):
            return JSONResponse(
                {"detail": "Forbidden."},
                status_code=403,
            )

        if path.startswith("/admin") and _ADMIN_IP_ALLOWLIST:
            client_ip = _client_ip(request)
            if client_ip not in _ADMIN_IP_ALLOWLIST:
                return JSONResponse(
                    {"detail": "Access denied."},
                    status_code=403,
                )

        content_length = request.headers.get("content-length")
        if content_length and int(content_length) > MAX_REQUEST_BYTES:
            return JSONResponse(
                {"detail": "Request body too large."},
                status_code=413,
            )

        return await call_next(request)


class HTTPSEnforcementMiddleware(BaseHTTPMiddleware):
    """
    BLOCKER B-SEC-3 — Enforce HTTPS in production.

    In production: HTTP requests receive a permanent 301 redirect to HTTPS.
    Health check (/health) is exempt so load-balancer probes work.
    In development: no-op (allows plain HTTP localhost workflows).

    Behind reverse proxy (nginx/ALB): honours X-Forwarded-Proto: https header.
    """

    _EXEMPT_PATHS = {"/health", "/health/"}

    async def dispatch(
        self, request: _StarletteRequest, call_next
    ) -> _StarletteResponse:
        if not _IS_PROD:
            return await call_next(request)

        if request.url.path in self._EXEMPT_PATHS:
            return await call_next(request)

        proto = request.headers.get("x-forwarded-proto", "").lower()
        scheme = proto or request.url.scheme

        if scheme != "https":
            https_url = request.url.replace(scheme="https")
            from starlette.responses import RedirectResponse
            return RedirectResponse(url=str(https_url), status_code=301)

        return await call_next(request)


def add_security_middleware(app) -> None:
    """
    Register all security middlewares onto a FastAPI / Starlette app.

    Middleware stack (outermost to innermost — Starlette LIFO order):
      1. HTTPSEnforcementMiddleware  — redirect HTTP to HTTPS in production (B-SEC-3)
      2. RequestGuardMiddleware      — WAF filtering (path traversal, scanner UA, body size)
      3. SecurityHeadersMiddleware   — HSTS, CSP, X-Frame-Options, etc.

    Call once during app initialisation, after creating the app but before
    including routers:

        app = FastAPI(...)
        add_security_middleware(app)
        app.include_router(...)
    """
    # LIFO: last-added runs first. HTTPS enforcement must be outermost -> add last.
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(RequestGuardMiddleware)
    app.add_middleware(HTTPSEnforcementMiddleware)
