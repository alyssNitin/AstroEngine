"""
backend/api/main.py
====================
FastAPI application — all routes.
Serves: Kundli API, Auth, Wallet, Super Admin panel, and static frontend.
"""
from __future__ import annotations
import json
import logging
from backend.core.logging import get_logger
import os
import secrets
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

logger = get_logger(__name__)

# ── Lazy FastAPI import ───────────────────────────────────────────────────────
try:
    from fastapi import (
        FastAPI, HTTPException, Query, Depends,
        Request, Response, BackgroundTasks, Body, Cookie,
    )
    from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse, FileResponse
    from fastapi.staticfiles import StaticFiles
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
    from pydantic import BaseModel, field_validator
except ImportError as _e:
    raise RuntimeError(
        f"[ERROR] Missing dependency: {_e}\n"
        "  Run: pip install fastapi uvicorn pydantic"
    )

# ── Project imports ───────────────────────────────────────────────────────────
from backend.persistence.database import Database, REPORT_COST_CENTS, CHAT_COST_CENTS
from backend.persistence.session_store import get_session_store
from backend.kundli_engine import KundliEngine, format_for_claude_compact
from backend.ai_interpretation.agent import AstroAgent
from backend.ai_interpretation.safety_filter import SafetyFilter
from backend.auth.email_service import EmailService
from backend.auth.jwt_utils import (
    create_access_token, create_token_pair,
    verify_refresh_token, refresh_access_token, invalidate_tokens,
)
from backend.api.security import (
    get_current_user, get_current_email,
    get_optional_user, get_optional_email,
    admin_auth, ADMIN_SECRET, validate_secrets_for_production,
    validate_production_blockers, add_security_middleware,
)
from backend.api.rate_limiter import (
    limit_login, limit_register, limit_forgot_pass, limit_resend_verify,
    limit_ai, limit_topup,
)
from payment.wallet import (
    WalletService, GUEST_FREE_CHAT_LIMIT,
    get_pricing, format_amount, label_txn_reason, calculate_tax,
)
from payment.gateway import PaymentGateway

# ── Config ────────────────────────────────────────────────────────────────────
_HERE           = Path(__file__).parent
_FRONT_DIR      = _HERE.parent.parent / "frontend"                      # legacy HTML/JS
_REACT_DIST     = _HERE.parent.parent / "frontend-react" / "dist"       # Vite React build
# Prefer the React build when it has been compiled (npm run build)
_ACTIVE_FRONT   = _REACT_DIST if (_REACT_DIST / "index.html").exists() else _FRONT_DIR
_db = Database()   # PostgreSQL — configured via DATABASE_URL env var

ADMIN_LOG_PATH = os.environ.get("ADMIN_LOG_PATH", str(_HERE.parent.parent / "narayan_astro.log"))
ADMIN_AUDIT_LOG= os.environ.get("ADMIN_AUDIT_LOG", str(_HERE.parent.parent / "admin_audit.log"))

# ── FastAPI app ───────────────────────────────────────────────────────────────
app = FastAPI(
    title="NarayanAstroReader API",
    description="Vedic AI Astrology platform API",
    version="1.2.0",
)
# Bearer token extractor (auto_error=False so logout works without a valid token)
_bearer = HTTPBearer(auto_error=False)

# ── Environment ───────────────────────────────────────────────────────────────
# Defined FIRST — referenced by CORS setup and startup validation below.
_ENVIRONMENT = os.environ.get("ENVIRONMENT", "development").lower()

# CORS — restrict to configured origin(s) in production.
# Set ALLOWED_ORIGINS=https://yourapp.com,https://www.yourapp.com in production .env
_raw_origins = os.environ.get("ALLOWED_ORIGINS", "")
_ALLOWED_ORIGINS: list[str] = (
    [o.strip() for o in _raw_origins.split(",") if o.strip()]
    if _raw_origins and _ENVIRONMENT == "production"
    else ["*"]
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=_ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Admin-Secret"],
)
add_security_middleware(app)

# ── B11: Prometheus metrics middleware + /metrics endpoint ────────────────────
from backend.monitoring.metrics import MetricsMiddleware, setup_metrics_endpoint
app.add_middleware(MetricsMiddleware)
setup_metrics_endpoint(app)

# ── B12: PagerDuty alerting ───────────────────────────────────────────────────
from backend.monitoring.alerting import wire_alerting_to_app
wire_alerting_to_app(app)

# ── Startup secrets validation ────────────────────────────────────────────────

@app.on_event("startup")
async def _startup_secrets_check() -> None:
    """
    Validate required secrets on startup.
    B-SEC-1/B-SEC-2: Hard-fail in production if JWT_SECRET or CORS is misconfigured.
    """
    import sys
    # Hard-fail immediately for BLOCKER security issues in production.
    validate_production_blockers()

    # In dev mode: show warnings but keep running.
    errors = validate_secrets_for_production()
    if errors and _ENVIRONMENT != "production":
        print("\n[security] ⚠ Development-mode security warnings:", file=sys.stderr)
        for e in errors:
            print(f"  • {e}", file=sys.stderr)
        print("[security] These would be FATAL errors in production.\n", file=sys.stderr)

    # B17: Start promotional credit expiry scheduler (nightly at 02:00 UTC)
    try:
        from backend.scheduler.promo_expiry import setup_scheduler, migrate_promo_schema
        migrate_promo_schema(_db)
        _promo_scheduler = setup_scheduler(_db)
        if _promo_scheduler:
            app.state.promo_scheduler = _promo_scheduler
    except Exception as _sched_err:
        print(f"[scheduler] WARNING: Could not start promo expiry scheduler: {_sched_err}", file=sys.stderr)


@app.on_event("shutdown")
async def _shutdown_scheduler() -> None:
    """Gracefully shut down background schedulers on app exit."""
    scheduler = getattr(app.state, "promo_scheduler", None)
    if scheduler:
        try:
            scheduler.shutdown(wait=False)
        except Exception:
            pass

# ── Health check ─────────────────────────────────────────────────────────────
@app.get("/health", summary="Health check for load balancer / Kubernetes probes", tags=["ops"])
def health_check():
    """
    Returns 200 OK when the application is running.
    A shallow DB ping is included so the load balancer can detect broken DB connections.
    """
    db_ok = True
    try:
        _db.health_ping()
    except Exception:
        db_ok = False

    payload = {
        "status":      "ok" if db_ok else "degraded",
        "db":          "ok" if db_ok else "error",
        "environment": _ENVIRONMENT,
        "version":     "1.2.0",
    }
    status_code = 200 if db_ok else 503
    return JSONResponse(content=payload, status_code=status_code)

# ── Session store (Redis-backed with in-memory fallback) ─────────────────────
_store = get_session_store()

# Convenience shim so legacy code that does _sessions[sid] still works
class _SessionsProxy:
    """Thin proxy making _store look like a plain dict for legacy callers."""
    def get(self, sid, default=None):      return _store.get(sid) or default
    def __getitem__(self, sid):            return _store.get(sid) or {}
    def __setitem__(self, sid, val):       _store.set(sid, val)
    def __contains__(self, sid):           return _store.exists(sid)
    def __delitem__(self, sid):            _store.delete(sid)
    def pop(self, sid, *args):
        v = _store.get(sid)
        _store.delete(sid)
        return v if v is not None else (args[0] if args else None)

_sessions = _SessionsProxy()
_guest_chat_counts: dict[str, int] = {}  # kept in-memory; low-stakes counter

# ── Request / Response models ─────────────────────────────────────────────────

class RegisterRequest(BaseModel):
    email:     str
    password:  str
    name:      str = ""
    user_type: str = "general"   # "general" or "astrologer"
    region:    str = "India"     # "India" or "International"

class LoginRequest(BaseModel):
    email:    str
    password: str

class ResendVerifyRequest(BaseModel):
    email: str

class TopupOrderRequest(BaseModel):
    email:   str
    tier:    int = 1   # 1 or 2
    credits: int = 0   # legacy field, ignored if tier present

class TopupVerifyRequest(BaseModel):
    email:        str
    tier:         int
    payment_data: dict = {}

class WalletAdjustRequest(BaseModel):
    email:       str
    delta_cents: int
    reason:      str

class AdminVerifyRequest(BaseModel):
    email: str

class AdminQueryRequest(BaseModel):
    sql: str

class StartRequest(BaseModel):
    email:          str = ""
    name:           str = ""
    date_of_birth:  str
    time_of_birth:  str
    place_of_birth: str
    latitude:       float | None = None   # optional — backend geocodes from place_of_birth
    longitude:      float | None = None
    timezone_offset:float | None = None
    marital_status: str = ""
    language:       str = "English"

    @field_validator("date_of_birth")
    @classmethod
    def _vdate(cls, v):
        try:
            d = datetime.strptime(v, "%Y-%m-%d")
        except ValueError:
            raise ValueError(f"Invalid date '{v}'. Use YYYY-MM-DD.")
        if d > datetime.now():
            raise ValueError("Date of birth cannot be in the future.")
        return v

    @field_validator("time_of_birth")
    @classmethod
    def _vtime(cls, v):
        for fmt in ("%H:%M", "%H:%M:%S"):
            try:
                t = datetime.strptime(v, fmt)
                h, m = t.hour, t.minute
                if 0 <= h <= 23 and 0 <= m <= 59:
                    return v
                raise ValueError("Time out of range.")
            except ValueError:
                continue
        raise ValueError("Use HH:MM or HH:MM:SS.")

class RefineRequest(BaseModel):
    email:       str = ""
    corrections: dict = {}
    language:    str = "English"

class ChatRequest(BaseModel):
    message:  str
    email:    str = ""
    language: str = "English"

class LookupRequest(BaseModel):
    email: str

class SaveRequest(BaseModel):
    data: dict

class EmailReportRequest(BaseModel):
    email: str
    session_id: str = ""

# ── Helpers ───────────────────────────────────────────────────────────────────



# ── Report storage helper ─────────────────────────────────────────────────────

def _save_report(
    email:       str,
    session_id:  str,
    report_type: str,
    content:     str,
    language:    str = "English",
    metadata:    dict | None = None,
) -> str:
    """
    Persist a completed AI report to the object store (S3 or local)
    and record its metadata in the ai_reports DB table.

    Called from SSE streaming endpoints after the 'done' event fires.
    Silently swallows errors so a storage failure never breaks the stream.

    Returns the report_id (empty string on failure).
    """
    try:
        from backend.storage.report_store import get_report_store
        store   = get_report_store()
        key     = store.save(report_type, email or "anonymous", content, metadata)
        meta    = metadata or {}
        meta["storage_backend"] = store.backend
        report_id = _db.save_ai_report(
            email           = email or "",
            session_id      = session_id,
            report_type     = report_type,
            storage_key     = key,
            storage_backend = store.backend,
            language        = language,
            content_preview = content[:500],
            metadata        = meta,
        )
        return report_id
    except Exception as _exc:
        import sys
        print(f"[report_store] Warning: could not persist report: {_exc}", file=sys.stderr)
        return ""

def _get_agent() -> AstroAgent:
    try:
        return AstroAgent()
    except ValueError as e:
        raise HTTPException(status_code=503, detail=str(e))

def _restore_session(profile: dict) -> str:
    sid = str(uuid.uuid4())
    kundli = profile.get("kundli_json", {})
    if kundli:
        from backend.kundli_engine.formatter import format_for_claude_compact as fmt
        try:
            kundli_prompt = fmt(kundli)
        except Exception:
            kundli_prompt = ""
        sess_data = {
            "email":          profile.get("email", ""),
            "kundli":         kundli,
            "kundli_prompt":  kundli_prompt,
            "predictions":    profile.get("predictions_json", {}),
            "overall_theme":  profile.get("overall_theme", ""),
            "messages":       [],
            "planet_knowledge": None,
            "marital_status": profile.get("marital_status", ""),
            "language":       profile.get("preferred_language", "English"),
        }
        if profile.get("refined_analysis"):
            sess_data["messages"] = [
                {"role": "user",      "content": "[Prior session restored]"},
                {"role": "assistant", "content": profile["refined_analysis"]},
            ]
        _store.set(sid, sess_data)
    return sid

def _audit_log(action: str, target: str = "", detail: str = "") -> None:
    try:
        entry = f"{datetime.now(timezone.utc).isoformat()} | {action} | target={target} | {detail}\n"
        with open(ADMIN_AUDIT_LOG, "a", encoding="utf-8") as f:
            f.write(entry)
    except Exception:
        pass

def _user_region(email: str) -> str:
    """Return the region ('India' or 'International') for a registered user."""
    if not email:
        return "India"
    profile = _db.get_profile(email) or {}
    return profile.get("region", "India")


def _cents_to_dollars(cents: int, region: str = "India") -> str:
    """Format minor-unit amount as a display string for the given region."""
    if region == "India":
        rupees = cents / 100
        if rupees == int(rupees):
            return f"₹{int(rupees):,}"
        return f"₹{rupees:,.2f}"
    return f"${cents / 100:.2f}"

# ── Auth endpoints ────────────────────────────────────────────────────────────

@app.post("/auth/register", summary="Register new user account")
def register(req: RegisterRequest, background_tasks: BackgroundTasks, _rl=limit_register):
    if not req.email or not req.password:
        raise HTTPException(400, "Email and password required.")
    if len(req.password) < 6:
        raise HTTPException(400, "Password must be at least 6 characters.")
    region   = req.region if req.region in ("India", "International") else "India"
    currency = "INR" if region == "India" else "USD"
    result = _db.register(req.email, req.password, req.name, req.user_type)
    if not result["success"]:
        if result.get("error") == "email_taken":
            raise HTTPException(409, "An account with this email already exists. Please login.")
        raise HTTPException(500, "Registration failed.")
    # Send verification email in background — never blocks the response
    _db.save_profile({"email": req.email, "region": region, "currency": currency})
    background_tasks.add_task(
        EmailService.send_verification,
        req.email, req.name or req.email, result["verification_token"]
    )
    tokens = create_token_pair(req.email)
    return {
        "success":        True,
        "user_id":        result["user_id"],
        "email_verified": False,
        "wallet_balance_cents": 0,
        "wallet_display": "₹0" if region == "India" else "$0.00",
        "region": region,
        "currency": currency,
        **tokens,
        "email_sent":     True,   # optimistic — will print to console if SMTP fails
        "message": "Account created. A verification link has been sent to your email.",
    }

@app.post("/auth/login", summary="Login with email and password")
def login(req: LoginRequest, _rl=limit_login):
    result = _db.login(req.email, req.password)
    if not result["success"]:
        err = result.get("error", "invalid_credentials")
        if err == "account_locked":
            mins = result.get("retry_after_minutes", 15)
            raise HTTPException(
                status_code=429,
                detail=f"Account temporarily locked due to too many failed attempts. "
                       f"Try again in {mins} minute(s).",
            )
        raise HTTPException(status_code=401, detail="Invalid email or password.")
    profile = result["profile"]
    sid     = _restore_session(profile)
    bal     = profile.get("wallet_balance_cents", 0)
    # Include reading data so frontend can restore the session without extra round-trip
    region    = profile.get("region", "India")
    currency  = profile.get("currency", "INR")
    preds     = profile.get("predictions_json", {})
    if isinstance(preds, str):
        import json as _j
        try: preds = _j.loads(preds)
        except Exception: preds = {}
    pk_json   = profile.get("planet_knowledge_json", {})
    if isinstance(pk_json, str):
        import json as _j
        try: pk_json = _j.loads(pk_json)
        except Exception: pk_json = {}
    refined   = profile.get("refined_analysis", "")
    tokens = create_token_pair(profile.get("email", req.email))
    return {
        "success":        True,
        "session_id":     sid,
        **tokens,
        "name":           profile.get("name", ""),
        "email":          profile.get("email", ""),
        "email_verified": bool(profile.get("email_verified", False)),
        "user_type":      profile.get("user_type", "general"),
        "wallet_balance_cents": bal,
        "wallet_display": _cents_to_dollars(bal, region),
        "has_reading":    bool(profile.get("kundli_json")),
        "has_readings":   bool(profile.get("kundli_json")),
        "preferred_language": profile.get("preferred_language", "English"),
        "region": region,
        "currency": currency,
        # Reading restoration fields
        "refined_analysis":  refined,
        "planet_knowledge":  pk_json,
        "predictions":       preds.get("predictions", []) if isinstance(preds, dict) else [],
        "overall_theme":     preds.get("overall_theme", "") if isinstance(preds, dict) else "",
        "has_deep_reading":  bool(refined),
    }

@app.get("/auth/me", summary="Get the currently authenticated user's profile")
def auth_me(current_email: str = Depends(get_current_email)):
    """
    Return the authenticated user's profile.
    Called by the React frontend on every page load to rehydrate the session.
    Returns the same flat shape as /auth/login so the frontend normaliser works.
    """
    profile = _db.get_profile(current_email)
    if not profile:
        raise HTTPException(404, "User profile not found.")
    bal    = profile.get("wallet_balance_cents", 0)
    region = profile.get("region", "India")
    return {
        "email":                current_email,
        "name":                 profile.get("name", ""),
        "email_verified":       bool(profile.get("email_verified", False)),
        "user_type":            profile.get("user_type", "general"),
        "wallet_balance_cents": bal,
        "wallet_display":       _cents_to_dollars(bal, region),
        "region":               region,
        "currency":             profile.get("currency", "INR" if region == "India" else "USD"),
        "preferred_language":   profile.get("preferred_language", "English"),
        "has_reading":          bool(profile.get("kundli_json")),
    }


class RefreshRequest(BaseModel):
    refresh_token: str

class LogoutRequest(BaseModel):
    refresh_token: Optional[str] = None

@app.post("/auth/refresh", summary="Refresh access token using refresh token")
def auth_refresh(req: RefreshRequest):
    """Issue a new access + refresh token pair, invalidating the old refresh token."""
    try:
        new_tokens = refresh_access_token(req.refresh_token)
        return {"success": True, **new_tokens}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(401, f"Failed to refresh token: {e}")

@app.post("/auth/logout", summary="Logout — invalidate access and refresh tokens")
def auth_logout(req: LogoutRequest,
                credentials: HTTPAuthorizationCredentials | None = Depends(_bearer)):
    """Blacklist both tokens so they cannot be reused after logout."""
    access_token = credentials.credentials if credentials else None
    try:
        invalidate_tokens(
            access_token  or "",
            req.refresh_token or "",
        )
    except Exception:
        pass   # Best-effort — always succeed
    return {"success": True, "message": "Logged out successfully."}

# ── MFA endpoints ─────────────────────────────────────────────────────────────

class MfaVerifyRequest(BaseModel):
    code: str   # 6-digit TOTP or 8-char backup code

@app.get("/auth/mfa/setup", summary="Generate TOTP secret + QR code for setup")
def mfa_setup(current_email: str = Depends(get_current_email)):
    """Return a new TOTP secret and provisioning QR for the authenticated user."""
    from backend.auth.mfa import generate_mfa_setup
    try:
        data = generate_mfa_setup(current_email)
    except RuntimeError as e:
        raise HTTPException(503, str(e))
    # Do NOT save to DB yet — user must confirm with a valid code first
    # Store pending secret in session-store temporarily
    _store.set(f"mfa_pending:{current_email}", {"secret": data["secret"]}, ttl=600)
    return {
        "success":      True,
        "otpauth_url":  data["otpauth_url"],
        "qr_data_url":  data["qr_data_url"],
        # Return secret so user can type it manually if QR fails
        "secret":       data["secret"],
    }

@app.post("/auth/mfa/confirm", summary="Confirm TOTP code to activate MFA")
def mfa_confirm(req: MfaVerifyRequest, current_email: str = Depends(get_current_email)):
    """Verify the first TOTP code from the authenticator app to activate MFA."""
    from backend.auth.mfa import verify_totp, generate_backup_codes, hash_backup_code
    pending = _store.get(f"mfa_pending:{current_email}") or {}
    secret  = pending.get("secret")
    if not secret:
        raise HTTPException(400, "No pending MFA setup. Call /auth/mfa/setup first.")
    if not verify_totp(secret, req.code):
        raise HTTPException(400, "Invalid TOTP code. Please try again.")
    # Generate backup codes and store hashed versions
    plain_codes  = generate_backup_codes(10)
    hashed_codes = [hash_backup_code(c) for c in plain_codes]
    _db.enable_mfa(current_email, secret, hashed_codes)
    _store.delete(f"mfa_pending:{current_email}")
    return {
        "success":      True,
        "message":      "MFA enabled. Save your backup codes — they will not be shown again.",
        "backup_codes": plain_codes,
    }

@app.post("/auth/mfa/verify", summary="Verify TOTP during login (MFA challenge)")
def mfa_verify_login(req: MfaVerifyRequest, current_email: str = Depends(get_current_email)):
    """Verify a TOTP or backup code for an already-authenticated session."""
    from backend.auth.mfa import verify_totp, check_backup_code
    mfa = _db.get_mfa_data(current_email)
    if not mfa or not mfa["mfa_enabled"]:
        return {"success": True, "message": "MFA not enabled for this account."}
    secret = mfa.get("mfa_secret") or ""
    # Try TOTP first
    if verify_totp(secret, req.code):
        return {"success": True, "method": "totp"}
    # Try backup codes
    idx = check_backup_code(req.code, mfa.get("mfa_backup_codes") or [])
    if idx is not None:
        _db.consume_mfa_backup_code(current_email, idx)
        return {"success": True, "method": "backup_code",
                "message": "Backup code used and consumed."}
    raise HTTPException(401, "Invalid MFA code.")

@app.delete("/auth/mfa/disable", summary="Disable MFA for the authenticated user")
def mfa_disable(req: MfaVerifyRequest, current_email: str = Depends(get_current_email)):
    """Disable MFA. Requires a valid TOTP code to confirm identity."""
    from backend.auth.mfa import verify_totp
    mfa = _db.get_mfa_data(current_email)
    if not mfa or not mfa["mfa_enabled"]:
        return {"success": True, "message": "MFA was not enabled."}
    if not verify_totp(mfa.get("mfa_secret") or "", req.code):
        raise HTTPException(401, "Invalid TOTP code — MFA not disabled.")
    _db.disable_mfa(current_email)
    return {"success": True, "message": "MFA has been disabled."}

@app.get("/auth/mfa/status", summary="Check MFA status for the authenticated user")
def mfa_status(current_email: str = Depends(get_current_email)):
    mfa = _db.get_mfa_data(current_email)
    enabled = mfa["mfa_enabled"] if mfa else False
    return {"mfa_enabled": enabled}


# ── Google OAuth endpoint ─────────────────────────────────────────────────────

class GoogleAuthRequest(BaseModel):
    credential: str   # Google ID token from GSI JS library

@app.post("/auth/oauth/google", summary="Sign in / register with Google OAuth")
def google_oauth(req: GoogleAuthRequest):
    """
    Verify a Google ID token and return our JWT token pair.
    If no account exists for the email, one is auto-created (email pre-verified).
    """
    from backend.auth.oauth_google import verify_google_id_token, is_google_oauth_configured
    if not is_google_oauth_configured():
        raise HTTPException(501, "Google OAuth is not configured on this server. "
                                 "Set GOOGLE_CLIENT_ID in .env")
    try:
        info = verify_google_id_token(req.credential)
    except (ValueError, RuntimeError) as e:
        raise HTTPException(401, str(e))

    email = info["email"].lower().strip()
    if not email:
        raise HTTPException(400, "Google account has no email address.")

    # Upsert user — create if not exists
    profile = _db.get_profile(email)
    if not profile:
        result = _db.register(
            email     = email,
            password  = secrets.token_hex(32),   # random unusable password
            name      = info.get("name", ""),
            user_type = "general",
            region    = "India",
        )
        if not result.get("success") and result.get("error") != "email_taken":
            raise HTTPException(500, "Could not create account.")
        # Mark email verified immediately (Google has already verified it)
        _db.force_verify_email(email)
        # Issue welcome credit
        try:
            _db.credit_wallet_cents(email, 10000, is_paid=False, reference_id="google_oauth_welcome")
        except Exception:
            pass
    elif not profile.get("email_verified"):
        _db.force_verify_email(email)

    tokens = create_token_pair(email)
    return {
        "success": True,
        "email":   email,
        "name":    info.get("name", ""),
        **tokens,
    }

@app.get("/auth/oauth/google/config", summary="Return Google Client ID for frontend")
def google_oauth_config():
    """Return the Google Client ID so the frontend can initialise GSI."""
    from backend.auth.oauth_google import GOOGLE_CLIENT_ID
    return {"client_id": GOOGLE_CLIENT_ID or None, "enabled": bool(GOOGLE_CLIENT_ID)}


# ── B7: Apple OAuth endpoint ──────────────────────────────────────────────────

class AppleAuthRequest(BaseModel):
    identity_token: str        # JWT from Apple Sign In
    authorization_code: str = ""
    first_name: str = ""       # only sent on very first sign-in
    last_name:  str = ""

@app.post("/auth/oauth/apple", summary="Sign in / register with Apple OAuth (Sign in with Apple)")
def apple_oauth(req: AppleAuthRequest):
    """
    Verify an Apple identity_token and return our JWT token pair.
    If no account exists for the email, one is auto-created (email pre-verified).
    Satisfies SRS §3 / Arch §3 — both Google AND Apple OAuth required.

    Configuration: set APPLE_CLIENT_ID, APPLE_TEAM_ID, APPLE_KEY_ID,
    APPLE_PRIVATE_KEY (or APPLE_PRIVATE_KEY_PATH) in .env
    """
    from backend.auth.oauth_apple import verify_apple_identity_token, APPLE_CLIENT_ID
    if not APPLE_CLIENT_ID:
        raise HTTPException(501, "Apple Sign In is not configured on this server. "
                                 "Set APPLE_CLIENT_ID, APPLE_TEAM_ID, APPLE_KEY_ID, "
                                 "APPLE_PRIVATE_KEY in .env")
    try:
        info = verify_apple_identity_token(req.identity_token)
    except (ValueError, ImportError, RuntimeError) as e:
        raise HTTPException(401, f"Apple token verification failed: {e}")

    email = (info.get("email") or "").lower().strip()
    if not email:
        # Apple allows users to hide their email — generate a proxy address
        apple_user_id = info.get("apple_user_id", "")
        email = f"apple_{apple_user_id[:16]}@privaterelay.appleid.com"

    # Build display name from Apple's name payload (only on first sign-in)
    name = (
        f"{req.first_name} {req.last_name}".strip()
        or info.get("name", "")
        or email.split("@")[0]
    )

    # Upsert user — create if not exists
    profile = _db.get_profile(email)
    if not profile:
        result = _db.register(
            email     = email,
            password  = secrets.token_hex(32),   # random unusable password
            name      = name,
            user_type = "general",
            region    = "India",
        )
        if not result.get("success") and result.get("error") != "email_taken":
            raise HTTPException(500, "Could not create Apple Sign In account.")
        # Mark email verified immediately (Apple has already verified it)
        _db.force_verify_email(email)
        # Issue welcome credit
        try:
            _db.credit_wallet_cents(
                email, 10000, is_paid=False,
                reference_id=f"apple_oauth_welcome_{info.get('apple_user_id','')[:16]}"
            )
        except Exception:
            pass
    elif not profile.get("email_verified"):
        _db.force_verify_email(email)

    tokens = create_token_pair(email)
    return {
        "success": True,
        "email":   email,
        "name":    name,
        **tokens,
    }


@app.get("/auth/oauth/apple/config", summary="Return Apple Client ID for frontend")
def apple_oauth_config():
    """Return Apple Sign In configuration for the frontend SDK."""
    from backend.auth.oauth_apple import APPLE_CLIENT_ID
    return {"client_id": APPLE_CLIENT_ID or None, "enabled": bool(APPLE_CLIENT_ID)}


@app.post("/auth/guest", summary="Create anonymous guest session")
def guest_session():
    sid = str(uuid.uuid4())
    _sessions[sid] = {
        "email": "", "kundli": {}, "kundli_prompt": "",
        "predictions": {}, "overall_theme": "", "messages": [],
        "planet_knowledge": None, "marital_status": "", "language": "English",
        "is_guest": True,
    }
    _guest_chat_counts[sid] = 0
    return {"success": True, "session_id": sid, "is_guest": True,
            "wallet_balance_cents": 0, "wallet_display": "$0.00"}

@app.get("/auth/verify-email", summary="Verify email via token link")
def verify_email(token: str = Query(...)):
    try:
        result = _db.verify_email(token)
    except Exception as exc:
        logger.error("verify_email exception: %s", exc, exc_info=True)
        return HTMLResponse(
            content=_verify_html(False, "A server error occurred. Please try again or contact support."),
            status_code=500,
        )
    if not result["success"]:
        err = result.get("error", "unknown")
        msgs = {
            "invalid_token":   "This verification link is invalid. Please register again or request a new link.",
            "already_verified":"✅ Your email is already verified! Please log in to continue.",
            "token_expired":   "This verification link has expired. Please click 'Resend Verification Email' to get a new one.",
        }
        msg = msgs.get(err, "Verification failed. Please try again.")
        # already_verified is not really an error — treat it as a soft success
        if err == "already_verified":
            return HTMLResponse(content=_verify_html(False, msg, is_soft=True), status_code=200)
        return HTMLResponse(content=_verify_html(False, msg), status_code=400)
    bal    = result.get("wallet_balance_cents", WELCOME_CREDIT_CENTS)
    region = result.get("region", "India")
    return HTMLResponse(content=_verify_html(True, "", bal, region=region))

@app.post("/auth/resend-verification", summary="Resend email verification link")
def resend_verification(req: ResendVerifyRequest, background_tasks: BackgroundTasks, _rl=limit_resend_verify):
    result = _db.resend_verification(req.email)
    if not result["success"]:
        err = result.get("error", "")
        if err == "already_verified":
            raise HTTPException(400, "Email already verified.")
        if err == "not_found":
            raise HTTPException(404, "No account found with this email.")
        if err == "rate_limited":
            raise HTTPException(429, "Too many resend attempts. Please try again later.")
        raise HTTPException(500, "Could not resend verification.")
    # Send in background — response is instant
    background_tasks.add_task(
        EmailService.send_verification,
        result["email"], result.get("name", ""), result["token"]
    )
    return {
        "success":    True,
        "email_sent": True,
        "message":    "Verification email sent. Please check your inbox.",
    }


@app.post("/auth/forgot-password", summary="Request a password reset email")
def forgot_password(req: ForgotPasswordRequest, background_tasks: BackgroundTasks, _rl=limit_forgot_pass):
    """
    Send a password-reset link to the user's email address.
    Always returns 200 to avoid revealing whether the email is registered.
    """
    result = _db.create_password_reset_token(req.email)
    if result["success"]:
        background_tasks.add_task(
            EmailService.send_password_reset,
            req.email, result.get("name", ""), result["token"]
        )
    return {
        "success": True,
        "message": "If an account exists for this email, a reset link has been sent.",
    }

@app.post("/auth/reset-password", summary="Reset password using token from email")
def reset_password(req: ResetPasswordRequest):
    """
    Consume a password-reset token and set the new password.
    Token is valid for 1 hour.
    """
    if len(req.new_password) < 6:
        raise HTTPException(400, "Password must be at least 6 characters.")
    result = _db.reset_password(req.token, req.new_password)
    if not result["success"]:
        err = result.get("error", "")
        if err == "token_expired":
            raise HTTPException(400, "Reset link has expired. Please request a new one.")
        raise HTTPException(400, "Invalid or already-used reset link.")
    return {
        "success": True,
        "email":   result["email"],
        "message": "Password updated successfully. Please log in with your new password.",
    }

# ── Wallet endpoints ──────────────────────────────────────────────────────────

@app.get("/wallet/balance", summary="Get wallet balance")
def wallet_balance(current_email: str = Depends(get_current_email)):
    """
    Return the authenticated user's wallet balance.
    B5: Redis-cached with 30s TTL for p95 ≤ 20ms read latency.
    Authenticated via Bearer JWT — no email query param needed.
    """
    from backend.cache.redis_cache import get_wallet_balance_cached, set_wallet_balance_cache
    # B5: Try Redis cache first
    cached = get_wallet_balance_cached(current_email)
    if cached:
        return cached

    profile = _db.get_profile(current_email)
    if not profile:
        raise HTTPException(404, "User not found.")
    bal    = profile.get("wallet_balance_cents", 0)
    region = profile.get("region", "India")
    result = {
        "email":           current_email,
        "balance_cents":   bal,
        "balance_display": _cents_to_dollars(bal, region),
        "region":          region,
        "currency":        profile.get("currency", "INR" if region == "India" else "USD"),
    }
    set_wallet_balance_cache(current_email, result)
    return result

# ── B1: GET /payment/packs — Arch §7.6 ────────────────────────────────────────
@app.get(
    "/payment/packs",
    summary="List geo-priced credit packs with tax breakdown",
    description=(
        "Returns all available credit packs with localised pricing, tax breakdown, "
        "and display labels. Region is inferred from the authenticated user's profile. "
        "India users see INR + 18% GST; International users see USD + 0% tax. "
        "Arch §7.6 / SRS §5.5."
    ),
    tags=["payment"],
)
def get_payment_packs(current_email: str = Depends(get_current_email)):
    """B1 — Geo-priced credit packs with full tax breakdown (Arch §7.6)."""
    region  = _user_region(current_email)
    pricing = get_pricing(region)

    packs = []
    for tier, (price_key, credit_key, label) in enumerate(
        [
            ("tier1_price", "tier1_credit", "Starter"),
            ("tier2_price", "tier2_credit", "Popular"),
        ],
        start=1,
    ):
        price_units = pricing[price_key]
        credits     = pricing[credit_key]
        tax         = calculate_tax(price_units, region)
        packs.append({
            "tier":              tier,
            "label":             label,
            "credits":           credits,
            "credit_display":    _cents_to_dollars(credits, region),
            "subtotal":          price_units,
            "subtotal_display":  tax["subtotal_display"],
            "tax_amount":        tax["tax_amount"],
            "tax_display":       tax["tax_display"],
            "tax_label":         tax["tax_label"],
            "tax_rate":          tax["tax_rate"],
            "total":             tax["total"],
            "total_display":     tax["total_display"],
            "region":            region,
        })
    return {"packs": packs, "region": region, "currency": "INR" if region == "India" else "USD"}


# ── B1: GET /payment/history — Arch §7.6 ─────────────────────────────────────
@app.get(
    "/payment/history",
    summary="Purchase history with receipts",
    description=(
        "Returns a paginated list of the authenticated user's top-up transactions. "
        "Each entry includes gateway order id, credits purchased, amount paid, "
        "tax breakdown, and a timestamp. Arch §7.6 / SRS §5.5."
    ),
    tags=["payment"],
)
def get_payment_history(
    page: int = 1,
    per_page: int = 20,
    current_email: str = Depends(get_current_email),
):
    """B1 — Purchase history with receipts (Arch §7.6)."""
    per_page = min(max(per_page, 1), 100)
    offset   = (page - 1) * per_page
    region   = _user_region(current_email)
    raw_rows = _db.get_wallet_transactions(current_email, limit=per_page, offset=offset)
    entries  = []
    for row in (raw_rows or []):
        amount = row.get("amount_cents", row.get("amount", 0))
        entries.append({
            **row,
            "amount_display": _cents_to_dollars(abs(amount), region),
        })
    return {
        "page":     page,
        "per_page": per_page,
        "entries":  entries,
        "region":   region,
    }


@app.post("/wallet/topup/order", summary="Create payment order with GST/tax breakdown")
def wallet_topup_order(req: TopupOrderRequest, _rl=limit_topup):
    region   = _user_region(req.email)
    pricing  = get_pricing(region)
    if req.tier == 2:
        price_units = pricing["tier2_price"]
        credits     = pricing["tier2_credit"]
    else:
        price_units = pricing["tier1_price"]
        credits     = pricing["tier1_credit"]

    # Calculate tax breakdown
    tax = calculate_tax(price_units, region)

    try:
        # Create payment order with the TOTAL amount (subtotal + tax)
        order = PaymentGateway.create_order(tax["total"], req.email, credits)
        return {
            **order,
            "region":            region,
            "credits":           credits,
            "display":           _cents_to_dollars(credits, region),
            # Tax breakdown for invoice display in UI
            "subtotal":          price_units,
            "subtotal_display":  tax["subtotal_display"],
            "tax_amount":        tax["tax_amount"],
            "tax_display":       tax["tax_display"],
            "tax_label":         tax["tax_label"],
            "tax_rate":          tax["tax_rate"],
            "total":             tax["total"],
            "total_display":     tax["total_display"],
        }
    except Exception as e:
        raise HTTPException(500, f"Could not create payment order: {e}")

@app.post("/wallet/topup/verify", summary="Verify payment and credit wallet")
def wallet_topup_verify(req: TopupVerifyRequest, _rl=limit_topup):
    from backend.cache.redis_cache import invalidate_wallet_cache
    if not PaymentGateway.verify_payment(req.payment_data):
        raise HTTPException(400, "Payment verification failed.")
    region  = _user_region(req.email)
    pricing = get_pricing(region)
    credits = pricing["tier2_credit"] if req.tier == 2 else pricing["tier1_credit"]
    new_bal = WalletService.topup(_db, req.email, credits)
    invalidate_wallet_cache(req.email)   # B5: bust cache after topup
    return {"success": True, "new_balance_cents": new_bal,
            "new_balance_display": _cents_to_dollars(new_bal, region)}


# ── B3: SSE wallet balance stream ─────────────────────────────────────────────

@app.get(
    "/wallet/balance-stream",
    summary="SSE stream for real-time wallet balance updates",
    description=(
        "Server-Sent Events stream that pushes wallet balance updates to the client. "
        "Frontend subscribes immediately after initiating payment; balance is pushed "
        "within 5 seconds of the payment webhook crediting the wallet. "
        "Arch §5.2 / §10: real-time balance push ≤ 5s after webhook."
    ),
    tags=["wallet"],
    include_in_schema=True,
)
async def wallet_balance_stream(current_email: str = Depends(get_current_email)):
    """
    B3 — SSE endpoint.  Client connects with Authorization: Bearer <token>.
    Stream format (text/event-stream):
      data: {"balance_cents": 1500, "balance_display": "₹15.00"}\n\n
      ...
      data: {"close": true}\n\n   (after max_duration seconds)

    Polling interval  : 3 s
    Max stream duration: 120 s (configurable via SSE_MAX_DURATION env var)
    Sends update only when balance changes, plus an initial snapshot.
    """
    import asyncio
    import json as _json

    max_seconds = int(os.environ.get("SSE_MAX_DURATION", "120"))
    poll_interval = 3  # seconds

    async def event_generator():
        last_balance: int = -1
        iterations = max(1, max_seconds // poll_interval)
        for _ in range(iterations):
            try:
                profile = _db.get_profile(current_email)
                bal = int(profile.get("wallet_balance_cents", 0)) if profile else 0
                region = profile.get("region", "India") if profile else "India"
            except Exception:
                bal = last_balance if last_balance >= 0 else 0
                region = "India"

            if bal != last_balance:
                last_balance = bal
                payload = _json.dumps({
                    "balance_cents": bal,
                    "balance_display": _cents_to_dollars(bal, region),
                })
                yield f"data: {payload}\n\n"

            await asyncio.sleep(poll_interval)

        # Signal client that stream is done
        yield 'data: {"close": true}\n\n'

    from fastapi.responses import StreamingResponse
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",      # Disable nginx buffering
            "Connection": "keep-alive",
        },
    )


@app.get("/wallet/transactions", summary="Get wallet transaction history (ledger)")
def wallet_transactions(email: str = Query(...), limit: int = Query(50, ge=1, le=200),
                        offset: int = Query(0, ge=0)):
    email = email.strip().lower()
    if not email:
        raise HTTPException(400, "Email required.")
    profile = _db.get_profile(email)
    if not profile:
        raise HTTPException(404, "User not found.")
    region   = profile.get("region", "India")
    raw_rows = _db.get_wallet_transactions(email, limit=limit, offset=offset)
    txns     = []
    for r in raw_rows:
        ttype = r.get("txn_type") or r.get("type", "")
        ts    = str(r.get("created_at") or r.get("ts", ""))[:19].replace("T", " ")
        amt   = r.get("amount_cents", 0)
        bal   = r.get("total_after") or 0
        txns.append({
            "date":         ts,
            "type":         ttype,
            "balance_type": r.get("balance_type", ""),
            "label":        label_txn_reason(r.get("reason", ""), region),
            "amount":       _cents_to_dollars(amt, region),
            "balance":      _cents_to_dollars(bal, region),
            "sign":         "-" if ttype == "debit" else "+",
            "reference_id": r.get("reference_id", ""),
        })
    detail = _db.get_wallet_balance_detail(email)
    return {
        "transactions":        txns,
        "balance_cents":       detail["total"],
        "paid_balance_cents":  detail["paid"],
        "promo_balance_cents": detail["promo"],
        "balance":             _cents_to_dollars(detail["total"], region),
        "paid_balance":        _cents_to_dollars(detail["paid"],  region),
        "promo_balance":       _cents_to_dollars(detail["promo"], region),
        "region":              region,
        "currency":            profile.get("currency", "INR"),
    }

@app.get("/wallet/balance-detail", summary="Get paid/promo/total wallet breakdown")
def wallet_balance_detail(email: str = Query(...)):
    email = email.strip().lower()
    if not email:
        raise HTTPException(400, "Email required.")
    profile = _db.get_profile(email)
    if not profile:
        raise HTTPException(404, "User not found.")
    region = profile.get("region", "India")
    detail = _db.get_wallet_balance_detail(email)
    return {
        "email":               email,
        "balance_cents":       detail["total"],
        "paid_balance_cents":  detail["paid"],
        "promo_balance_cents": detail["promo"],
        "balance":             _cents_to_dollars(detail["total"], region),
        "paid_balance":        _cents_to_dollars(detail["paid"],  region),
        "promo_balance":       _cents_to_dollars(detail["promo"], region),
        "region":              region,
        "currency":            profile.get("currency", "INR" if region == "India" else "USD"),
    }

# ── Kundli endpoints ──────────────────────────────────────────────────────────

@app.post("/kundli/start", summary="Step 1 — Generate kundli + initial predictions")
def start_reading(req: StartRequest):
    email   = req.email.strip().lower() if req.email else ""
    is_guest = not email

    # Wallet check for registered users
    if not is_guest:
        ok, remaining = WalletService.debit(_db, email, REPORT_COST_CENTS, "kundli_report")
        if not ok:
            raise HTTPException(
                status_code=402,
                detail=(
                    f"Insufficient balance. You have {_cents_to_dollars(remaining)} "
                    f"but a reading costs {_cents_to_dollars(REPORT_COST_CENTS)}. "
                    "Please top up your wallet."
                )
            )
    try:
        engine = KundliEngine()
        kundli = engine.generate(
            place_name=req.place_of_birth,
            date_of_birth=req.date_of_birth,
            time_of_birth=req.time_of_birth,
            latitude=req.latitude,
            longitude=req.longitude,
            timezone_offset=req.timezone_offset,
            name=req.name,
        )
    except ValueError as e:
        if not is_guest:
            WalletService.refund(_db, email, WalletService.get_pricing_for_user(_db, email)['report'] if email else 0)
        raise HTTPException(422, str(e))
    except Exception as e:
        if not is_guest:
            WalletService.refund(_db, email, WalletService.get_pricing_for_user(_db, email)['report'] if email else 0)
        raise HTTPException(500, f"Calculation error: {e}")

    kundli_prompt = format_for_claude_compact(kundli)

    try:
        agent       = _get_agent()
        predictions = agent.generate_predictions(
            kundli_prompt    = kundli_prompt,
            marital_status   = req.marital_status,
            language         = req.language,
        )
    except Exception as e:
        if not is_guest:
            WalletService.refund(_db, email, WalletService.get_pricing_for_user(_db, email)['report'] if email else 0)
        raise HTTPException(500, f"AI prediction error: {e}")

    # If predictions couldn't be parsed, refund and surface the error properly
    if predictions.get("_parse_error"):
        if not is_guest:
            WalletService.refund(_db, email, WalletService.get_pricing_for_user(_db, email)['report'] if email else 0)
            logger.error("Prediction parse failed for %s; wallet refunded. Raw: %s",
                         email, predictions.get("_raw", "")[:300])
        raise HTTPException(
            status_code=500,
            detail="AI could not generate structured predictions. Your wallet has been refunded. Please try again."
        )

    sid = str(uuid.uuid4())
    _sessions[sid] = {
        "email":          email,
        "kundli":         kundli,
        "kundli_prompt":  kundli_prompt,
        "predictions":    predictions,
        "overall_theme":  predictions.get("overall_theme", ""),
        "messages":       [],
        "planet_knowledge": None,
        "marital_status": req.marital_status,
        "language":       req.language,
        "is_guest":       is_guest,
    }
    if sid not in _guest_chat_counts:
        _guest_chat_counts[sid] = 0

    # Persist for registered users
    if email:
        bal = _db.get_wallet_balance_cents(email)
        _region_s = _user_region(email)
        _db.save_profile({
            "email": email, "name": req.name,
            "date_of_birth": req.date_of_birth, "time_of_birth": req.time_of_birth,
            "place_of_birth": req.place_of_birth,
            "latitude": req.latitude or kundli.get("birth_info", {}).get("latitude", 0.0),
            "longitude": req.longitude or kundli.get("birth_info", {}).get("longitude", 0.0),
            "timezone_offset": req.timezone_offset or kundli.get("birth_info", {}).get("timezone_offset", 0.0),
            "kundli_json": kundli, "predictions_json": predictions,
            "overall_theme": predictions.get("overall_theme", ""),
            "marital_status": req.marital_status,
            "preferred_language": req.language,
            "session_id": sid,
        })
    else:
        bal = 0

    _kundli_region = _user_region(email) if email else "India"
    return {
        "session_id":    sid,
        "predictions":   predictions.get("predictions", []),
        "overall_theme": predictions.get("overall_theme", ""),
        "lagna":         kundli.get("lagna", {}),
        "birth_info":    kundli.get("birth_info", {}),
        "wallet_balance_cents": bal,
        "wallet_display": _cents_to_dollars(bal, _kundli_region),
    }

@app.post("/kundli/refine/{session_id}", summary="Step 2 — User feedback → deep analysis (SSE streaming)")
def refine_reading(session_id: str, req: RefineRequest):
    """
    Streams Claude's deep reading via Server-Sent Events so the browser never times out.
    Events:
      data: {"chunk": "<text>"}          — incremental text arriving
      data: {"done": true, ...metadata}  — final event with wallet balance + planet knowledge
      data: {"error": "<msg>", "refunded": bool}  — on failure
    """
    sess = _sessions.get(session_id)
    if not sess:
        raise HTTPException(404, "Session not found.")

    email          = req.email.strip().lower() if req.email else sess.get("email", "")
    already_refined = bool(sess.get("refined_analysis"))

    def generate():
        full_text      = ""
        planet_knowledge = None

        try:
            agent  = _get_agent()
            for event in agent.stream_refine(
                kundli        = sess["kundli"],
                kundli_prompt = sess["kundli_prompt"],
                corrections   = req.corrections,
                prior_messages= sess["messages"],
                language      = req.language,
            ):
                if event["type"] == "chunk":
                    full_text += event["text"]
                    yield "data: " + json.dumps({"chunk": event["text"]}) + "\n\n"

                elif event["type"] == "done":
                    planet_knowledge = event["planet_knowledge"]
                    # Persist to session
                    sess["refined_analysis"] = full_text
                    sess["planet_knowledge"] = planet_knowledge
                    sess["messages"].extend([
                        {"role": "user",      "content": json.dumps(req.corrections)},
                        {"role": "assistant", "content": full_text},
                    ])
                    bal = 0
                    if email:
                        _db.save_profile({
                            "email": email,
                            "session_id": session_id,
                            "refined_analysis": full_text,
                            "planet_knowledge_json": planet_knowledge.to_dict() if hasattr(planet_knowledge, "to_dict") else {},
                        })
                        bal = _db.get_wallet_balance_cents(email)
                    pk_dict = planet_knowledge.to_dict() if hasattr(planet_knowledge, "to_dict") else {}
                    _refine_region = _user_region(email) if email else "India"
                    yield "data: " + json.dumps({
                        "done": True,
                        "wallet_balance_cents": bal,
                        "wallet_display": _cents_to_dollars(bal, _refine_region),
                        "planet_knowledge": pk_dict,
                    }) + "\n\n"

                elif event["type"] == "error":
                    raise RuntimeError(event["message"])

        except Exception as exc:
            logger.error("Refine stream failed for session %s: %s", session_id, exc)
            refunded = False
            if email and not already_refined:
                try:
                    WalletService.refund(_db, email, WalletService.get_pricing_for_user(_db, email)['report'] if email else 0)
                    refunded = True
                    logger.info("Refunded %d cents to %s after stream failure", REPORT_COST_CENTS, email)
                except Exception as ref_err:
                    logger.error("Refund also failed for %s: %s", email, ref_err)
            yield "data: " + json.dumps({
                "error": str(exc),
                "refunded": refunded,
                "refunded_display": _cents_to_dollars(REPORT_COST_CENTS) if refunded else None,
            }) + "\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control":    "no-cache",
            "X-Accel-Buffering": "no",   # Disable nginx buffering if behind a proxy
            "Connection":       "keep-alive",
        },
    )

@app.post("/kundli/chat/{session_id}", summary="Step 3+ — Q&A")
def chat(session_id: str, req: ChatRequest):
    sess = _sessions.get(session_id)
    if not sess:
        raise HTTPException(404, "Session not found.")

    email    = req.email.strip().lower() if req.email else sess.get("email", "")
    is_guest = sess.get("is_guest", not bool(email))

    # Guest chat limit
    if is_guest:
        count = _guest_chat_counts.get(session_id, 0)
        if count >= GUEST_FREE_CHAT_LIMIT:
            raise HTTPException(
                status_code=402,
                detail="You've used your free AI questions. Register to continue chatting."
            )

    # Safety check first (no charge if blocked)
    safety_result = SafetyFilter.check_message(req.message,
        {"marital_status": sess.get("marital_status", "")})
    if safety_result.blocked:
        bal = _db.get_wallet_balance_cents(email) if email else 0
        _blocked_region = _user_region(email) if email else "India"
        return {"response": safety_result.refusal_message, "was_blocked": True,
                "wallet_balance_cents": bal, "wallet_display": _cents_to_dollars(bal, _blocked_region)}

    # Deduct chat cost for registered users
    bal_before = 0
    if not is_guest and email:
        _chat_pricing = WalletService.get_pricing_for_user(_db, email)
        _chat_region  = _user_region(email)
        _chat_cost    = _chat_pricing["chat"]
        ok, remaining = WalletService.debit(_db, email, _chat_cost, "chat_message")
        if not ok:
            raise HTTPException(
                status_code=402,
                detail=(
                    f"Insufficient balance. You have {_cents_to_dollars(remaining, _chat_region)} "
                    f"but each AI question costs {_cents_to_dollars(_chat_cost, _chat_region)}. "
                    "Please top up your wallet."
                )
            )
        bal_before = remaining + _chat_cost

    try:
        agent = _get_agent()
        # Pass safety_filter bypass — already checked above
        from backend.ai_interpretation.agent import DEFAULT_LANGUAGE
        pk = sess.get("planet_knowledge")
        response = agent._call_claude(
            messages=sess["messages"][-10:] + [{"role": "user", "content": req.message}],
            system=_build_chat_system(sess, req.language),
            max_tokens=8192,
        )
        sess["messages"].extend([
            {"role": "user",      "content": req.message},
            {"role": "assistant", "content": response},
        ])

        # Update guest counter
        if is_guest:
            _guest_chat_counts[session_id] = _guest_chat_counts.get(session_id, 0) + 1

        # Persist chat messages to DB so they survive logout/login
        if email:
            # Store only user↔assistant turns (skip restored-session marker)
            chat_msgs = [m for m in sess["messages"]
                         if not (m.get("content") == "[Prior session restored]")]
            _db.save_profile({"email": email, "chat_messages_json": chat_msgs})

        bal = _db.get_wallet_balance_cents(email) if email else 0
        _chat_resp_region = _user_region(email) if email else "India"
        return {"response": response, "was_blocked": False,
                "wallet_balance_cents": bal, "wallet_display": _cents_to_dollars(bal, _chat_resp_region)}

    except Exception as e:
        # Refund on AI error
        if not is_guest and email:
            WalletService.refund(_db, email, WalletService.get_pricing_for_user(_db, email)['chat'] if email else 0)
        raise HTTPException(500, f"Chat error: {e}")


def _build_chat_system(sess: dict, language: str) -> str:
    from backend.ai_interpretation.prompts import CHAT_SYSTEM, SAFETY_REMINDER_DEFAULT, LANGUAGE_INSTRUCTION
    pk = sess.get("planet_knowledge")
    pk_str = pk.for_prompt() if pk and hasattr(pk, "for_prompt") else "No calibration yet."
    lang_instr = LANGUAGE_INSTRUCTION.format(language=language) if language != "English" else ""
    return (
        CHAT_SYSTEM.format(
            planet_knowledge=pk_str,
            safety_reminder=SAFETY_REMINDER_DEFAULT,
            language_instruction=lang_instr,
        )
        + f"\n\nKundli data:\n{sess.get('kundli_prompt', '')}"
    )

# ── User profile endpoints ────────────────────────────────────────────────────

@app.post("/user/email-report", summary="Generate PDF report and email it to the user")
def email_report(req: EmailReportRequest, background_tasks: BackgroundTasks):
    email = req.email.strip().lower()
    if not email:
        raise HTTPException(400, "Email required.")
    profile = _db.get_profile(email)
    if not profile:
        raise HTTPException(404, "User not found.")

    refined = profile.get("refined_analysis", "")
    if not refined:
        raise HTTPException(400, "No deep reading found for this account yet.")

    # Prefer live session messages (in memory), fall back to DB-persisted ones
    chat_msgs: list = []
    sid = req.session_id or profile.get("session_id", "")
    if sid and sid in _sessions:
        chat_msgs = [m for m in _sessions[sid].get("messages", [])
                     if m.get("content") != "[Prior session restored]"]
    if not chat_msgs:
        chat_msgs = profile.get("chat_messages_json") or []

    name = profile.get("name", "Seeker")
    dob  = profile.get("date_of_birth", "")
    tob  = profile.get("time_of_birth", "")
    pob  = profile.get("place_of_birth", "")
    birth_info = ", ".join(filter(None, [dob, tob, pob]))

    from backend.reports.pdf_generator import generate_report_pdf
    pdf_bytes, content_type = generate_report_pdf(name, birth_info, refined, chat_msgs)

    def _send():
        EmailService.send_report(email, name, pdf_bytes, content_type)

    background_tasks.add_task(_send)
    return {"success": True, "message": f"Report is being emailed to {email}."}


@app.get("/export/{session_id}/docx", summary="Download reading as Word (.docx) document")
def export_docx(session_id: str, email: str = Query("")):
    """
    Generate and return a .docx report for the given session.

    Falls back to plain-text if python-docx is not installed.
    Query param ``email`` is used to look up the user profile for
    name / birth-info enrichment.
    """
    sess = _sessions.get(session_id)
    if not sess:
        raise HTTPException(404, "Session not found or expired.")

    email = (email or sess.get("email", "")).strip().lower()
    profile = _db.get_profile(email) if email else {}

    from backend.reports.docx_generator import build_report_bytes
    file_bytes, filename = build_report_bytes(session_id, _db, _sessions)

    # Determine content-type: .docx is a zip (PK magic); otherwise plain text
    if file_bytes[:4] == b"PK\x03\x04":
        media_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    else:
        media_type = "text/plain; charset=utf-8"
        filename   = filename.replace(".docx", ".txt")

    return Response(
        content=file_bytes,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.get("/export/{session_id}/pdf", summary="Download reading as PDF document")
def export_pdf(session_id: str, email: str = Query("")):
    """Download a PDF version of the reading (alias for the email-report PDF generation)."""
    sess = _sessions.get(session_id)
    if not sess:
        raise HTTPException(404, "Session not found or expired.")

    email = (email or sess.get("email", "")).strip().lower()
    profile = _db.get_profile(email) if email else {}

    refined = sess.get("refined_analysis") or (profile or {}).get("refined_analysis", "")
    if not refined:
        raise HTTPException(400, "No deep reading available to export.")

    name = (profile or {}).get("name", sess.get("name", "Seeker"))
    dob  = (profile or {}).get("date_of_birth", "")
    tob  = (profile or {}).get("time_of_birth", "")
    pob  = (profile or {}).get("place_of_birth", "")
    birth_info = ", ".join(filter(None, [dob, tob, pob]))
    chat_msgs  = [m for m in sess.get("messages", [])
                  if m.get("content") != "[Prior session restored]"]

    from backend.reports.pdf_generator import generate_report_pdf
    pdf_bytes, content_type = generate_report_pdf(name, birth_info, refined, chat_msgs)

    safe_name = re.sub(r"[^a-zA-Z0-9_-]", "_", name or "reading")
    filename  = f"vedic_reading_{safe_name}_{datetime.now(timezone.utc).strftime('%Y%m%d')}.pdf"
    return Response(
        content=pdf_bytes,
        media_type=content_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ── B8: Async PDF generation (Celery task queue) ──────────────────────────────

@app.post(
    "/export/{session_id}/pdf/async",
    summary="Submit async PDF generation job (B8)",
    description=(
        "Submit PDF generation as a background task via Celery. "
        "Returns 202 Accepted immediately with a task_id. "
        "Poll GET /export/status/{task_id} for progress; "
        "download via GET /export/download/{task_id} when complete. "
        "Arch §8 / SRS §4.2: non-blocking export."
    ),
    status_code=202,
    tags=["export"],
)
def export_pdf_async(session_id: str, email: str = Query("")):
    """
    B8 — Submit PDF generation as a Celery background task.
    Returns 202 {"task_id": "<uuid>"} immediately.
    """
    sess = _sessions.get(session_id)
    if not sess:
        raise HTTPException(404, "Session not found or expired.")

    email = (email or sess.get("email", "")).strip().lower()
    profile = _db.get_profile(email) if email else {}

    refined = sess.get("refined_analysis") or (profile or {}).get("refined_analysis", "")
    if not refined:
        raise HTTPException(400, "No deep reading available to export.")

    name       = (profile or {}).get("name", sess.get("name", "Seeker"))
    dob        = (profile or {}).get("date_of_birth", "")
    tob        = (profile or {}).get("time_of_birth", "")
    pob        = (profile or {}).get("place_of_birth", "")
    birth_info = ", ".join(filter(None, [dob, tob, pob]))
    chat_msgs  = [m for m in sess.get("messages", [])
                  if m.get("content") != "[Prior session restored]"]

    from backend.tasks.pdf_tasks import submit_pdf_task
    task_id = submit_pdf_task(session_id, email, name, birth_info, refined, chat_msgs)
    return JSONResponse(
        status_code=202,
        content={
            "task_id":    task_id,
            "status":     "pending",
            "status_url": f"/export/status/{task_id}",
            "download_url": f"/export/download/{task_id}",
        },
    )


@app.get(
    "/export/status/{task_id}",
    summary="Poll async PDF generation status (B8)",
    tags=["export"],
)
def export_pdf_status(task_id: str):
    """
    B8 — Poll the status of an async PDF generation task.

    Returns
    -------
    JSON:
      status    : "pending" | "started" | "success" | "failure"
      progress  : 0–100
      download_url : present when status == "success"
      error     : present when status == "failure"
    """
    from backend.tasks.pdf_tasks import get_pdf_task_result
    result = get_pdf_task_result(task_id)
    resp: dict = {
        "task_id":  task_id,
        "status":   result["status"],
        "progress": result.get("progress", 0),
    }
    if result["status"] == "success":
        resp["download_url"] = f"/export/download/{task_id}"
    if result["status"] == "failure":
        resp["error"] = result.get("error", "PDF generation failed")
    return resp


@app.get(
    "/export/download/{task_id}",
    summary="Download completed async PDF (B8)",
    tags=["export"],
)
def export_pdf_download(task_id: str):
    """
    B8 — Download the completed PDF for a given task_id.

    Returns the PDF binary as an attachment.
    Returns 404 if the task is still pending, 500 if it failed.
    """
    from backend.tasks.pdf_tasks import get_pdf_task_result
    result = get_pdf_task_result(task_id)

    if result["status"] == "failure":
        raise HTTPException(500, f"PDF generation failed: {result.get('error')}")
    if result["status"] in ("pending", "started"):
        raise HTTPException(
            404,
            f"PDF not ready yet (status={result['status']}). "
            "Poll /export/status/{task_id} and retry when status=success.",
        )
    if result["status"] == "success" and result.get("pdf_bytes"):
        safe_tid = re.sub(r"[^a-zA-Z0-9_-]", "_", task_id)[:32]
        filename = f"vedic_reading_{safe_tid}.pdf"
        return Response(
            content=result["pdf_bytes"],
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    raise HTTPException(404, "PDF result not found. It may have expired.")


# ── Debug / introspection endpoints ───────────────────────────────────────────

@app.get(
    "/debug/ai-payload/{session_id}",
    summary="Inspect exact data sent to Claude for a reading session",
    description=(
        "Returns the kundli_prompt text, dasha data, and AI message structure that "
        "were (or would be) sent to Claude for analysis. Useful for verifying what "
        "the AI actually sees. Requires authentication — you can only inspect your own sessions."
    ),
    tags=["debug"],
)
def debug_ai_payload(
    session_id: str,
    current_email: str = Depends(get_current_email),
):
    """
    Mechanism to inspect exactly what kundli + dasha data was passed to Claude.

    Response fields
    ---------------
    kundli_prompt       : str   — The full formatted text block sent as context to Claude.
                                  Produced by format_for_claude_compact() from the kundli engine.
    kundli_raw          : dict  — Raw chart dict before text formatting (planets, houses, dashas…)
    dasha_data          : dict  — Vimshottari + other dasha systems from the session
    birth_info          : dict  — DOB / TOB / place used to compute the chart
    system_prompt_intro : str   — First 500 chars of the system prompt Claude received
    session_has_*       : bool  — Whether predictions / refined reading exist
    formatter_source    : str   — Whether PyJHora or built-in fallback formatter was used
    note                : str   — Human-readable explanation
    """
    sess = _sessions.get(session_id)
    if not sess:
        raise HTTPException(status_code=404, detail="Session not found or expired.")

    # Ownership check — users can only see their own sessions
    sess_email = sess.get("email", "")
    if sess_email and sess_email != current_email:
        raise HTTPException(status_code=403, detail="You can only inspect your own sessions.")

    kundli = sess.get("kundli", {})
    kundli_prompt = sess.get("kundli_prompt", "")

    # Detect which formatter was used
    try:
        from backend.kundli_engine.formatter import format_for_claude_compact  # noqa: PLC0415
        import sys
        formatter_source = "PyJHora claude_formatter" if "claude_formatter" in sys.modules else "built-in fallback formatter"
    except Exception:
        formatter_source = "unknown"

    # Build sample system prompt intro (first 500 chars, no PII scrubbing for debug)
    from backend.ai_interpretation.prompts import SYSTEM_ASTROLOGER  # noqa: PLC0415
    system_intro = SYSTEM_ASTROLOGER[:500] + "…" if len(SYSTEM_ASTROLOGER) > 500 else SYSTEM_ASTROLOGER

    # Sample user message structure (what would be sent to Claude)
    sample_message_structure = {
        "role": "user",
        "content": "[PREDICTIONS_PROMPT.format(kundli_prompt=<kundli_prompt below>, ...)]",
    }

    return {
        "session_id":           session_id,
        "note": (
            "This is the exact formatted text sent to Claude as context for your reading. "
            "The 'kundli_prompt' field is verbatim what the AI sees. "
            "Use GET /dasha/{session_id} to inspect the raw dasha timeline."
        ),
        "formatter_source":     formatter_source,
        "kundli_prompt":        kundli_prompt,
        "kundli_prompt_length": len(kundli_prompt),
        "kundli_raw": {
            "birth_info":        kundli.get("birth_info", {}),
            "lagna":             kundli.get("lagna", {}),
            "rasi_chart":        kundli.get("rasi_chart", {}),
            "divisional_charts": {
                k: v for k, v in kundli.get("divisional_charts", {}).items()
                if "error" not in v
            },
            "dashas":            kundli.get("dashas", {}),
            "ashtakavarga":      kundli.get("ashtakavarga", {}),
        },
        "session_has_predictions":     bool(sess.get("predictions")),
        "session_has_refined_reading": bool(sess.get("refined_reading")),
        "session_language":            sess.get("language", "English"),
        "system_prompt_intro":         system_intro,
        "sample_message_structure":    sample_message_structure,
    }


# ── Dasha endpoints ───────────────────────────────────────────────────────────

class DashaNarrativeRequest(BaseModel):
    email:    str = ""
    language: str = "English"

@app.get("/dasha/{session_id}", summary="Get raw dasha timeline from session kundli")
def get_dasha(session_id: str):
    """Return the Vimshottari dasha periods calculated from the session's birth chart."""
    sess = _sessions.get(session_id)
    if not sess:
        raise HTTPException(404, "Session not found or expired.")
    kundli = sess.get("kundli", {})
    if not kundli:
        raise HTTPException(400, "No kundli data in session yet.")
    try:
        dashas = kundli.get("vimshottari_dasha") or kundli.get("dashas") or {}
        current = kundli.get("current_dasha") or {}
        return {
            "session_id":    session_id,
            "dasha_system":  "vimshottari",
            "current_dasha": current,
            "timeline":      dashas,
        }
    except Exception as e:
        raise HTTPException(500, f"Dasha extraction failed: {e}")

@app.post("/dasha/{session_id}/narrative", summary="Generate AI dasha narrative for the session")
def dasha_narrative(session_id: str, req: DashaNarrativeRequest):
    """Call Claude to write a personalised narrative for the dasha timeline."""
    sess = _sessions.get(session_id)
    if not sess:
        raise HTTPException(404, "Session not found or expired.")
    kundli       = sess.get("kundli", {})
    kundli_prompt = sess.get("kundli_prompt", "")
    if not kundli_prompt:
        raise HTTPException(400, "No kundli data in session yet.")

    dashas = kundli.get("vimshottari_dasha") or kundli.get("dashas") or {}
    dasha_str = json.dumps(dashas, indent=2) if dashas else "Dasha data not yet computed."

    agent    = _get_agent()
    language = req.language or sess.get("language", "English")
    try:
        narrative = agent.generate_dasha_narrative(kundli_prompt, dasha_str, language)
        sess["dasha_text"] = narrative   # store for DOCX export
        return {"session_id": session_id, "narrative": narrative}
    except Exception as e:
        raise HTTPException(500, f"Dasha narrative generation failed: {e}")




@app.get("/dasha/{session_id}/{system}",
         summary="Calculate additional dasha system (yogini|chara|kalachakra|narayana|moola)")
def get_extra_dasha(session_id: str, system: str):
    """
    Calculate one of the additional Vedic dasha systems for the session's chart.

    system: yogini | chara | kalachakra | narayana | moola

    Returns:
        {session_id, dasha_system, name, total_years, balance_at_birth, periods}
    """
    valid = {"yogini", "chara", "kalachakra", "narayana", "moola"}
    system = system.lower().strip()
    if system not in valid:
        raise HTTPException(400, f"Unknown system '{system}'. Valid: {', '.join(sorted(valid))}")

    sess = _sessions.get(session_id)
    if not sess:
        raise HTTPException(404, "Session not found or expired.")

    kundli = sess.get("kundli_data") or sess.get("kundli", {})
    if not kundli:
        raise HTTPException(400, "No kundli data in session yet. Run /kundli/calculate first.")

    try:
        from backend.config import inject_pyjhora_path
        inject_pyjhora_path()
        engine = KundliEngine()
        result = engine.get_dasha(system, kundli)
        return {
            "session_id":   session_id,
            "dasha_system": system,
            **result,
        }
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(500, f"Dasha calculation failed: {e}")

# ── Career Report endpoints ───────────────────────────────────────────────────

class CareerReportRequest(BaseModel):
    email:    str = ""
    language: str = "English"

@app.post("/report/career/{session_id}", summary="Generate Career deep-dive report (SSE streaming)")
def career_report(session_id: str, req: CareerReportRequest):
    """
    Stream a career-focused AI report (D10, 10th house analysis).
    Returns Server-Sent Events:
      data: {"type": "chunk", "text": "..."}
      data: {"type": "done", "full_text": "..."}
      data: {"type": "error", "message": "..."}
    """
    sess = _sessions.get(session_id)
    if not sess:
        raise HTTPException(404, "Session not found or expired.")
    kundli_prompt = sess.get("kundli_prompt", "")
    if not kundli_prompt:
        raise HTTPException(400, "No kundli data in session yet.")

    refined   = sess.get("refined_analysis", "")
    language  = req.language or sess.get("language", "English")
    agent     = _get_agent()

    def _event_stream():
        full = ""
        try:
            for event in agent.stream_career_report(kundli_prompt, refined, language):
                if event.get("type") == "chunk":
                    full += event["text"]
                    yield f'data: {json.dumps(event)}\n\n'
                elif event.get("type") == "done":
                    sess["career_report"] = full
                    _save_report(req.email, session_id, "career", full, req.language)
                    yield f'data: {json.dumps({"type": "done", "full_text": full})}\n\n'
                elif event.get("type") == "error":
                    yield f'data: {json.dumps(event)}\n\n'
        except Exception as exc:
            yield f'data: {json.dumps({"type": "error", "message": str(exc)})}\n\n'

    return StreamingResponse(_event_stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


# ── Compatibility Report endpoints ────────────────────────────────────────────

class CompatibilityRequest(BaseModel):
    session_id_1: str
    person2_name:           str = ""
    person2_date_of_birth:  str = ""
    person2_time_of_birth:  str = ""
    person2_place_of_birth: str = ""
    person2_latitude:       float | None = None
    person2_longitude:      float | None = None
    person2_timezone_offset:float | None = None
    language:               str = "English"

@app.post("/report/compatibility", summary="Generate Vedic compatibility report (SSE streaming)")
def compatibility_report(req: CompatibilityRequest):
    """
    Build kundli for person 2 (provided inline) and stream a compatibility report
    against person 1 (from an existing session).

    Returns Server-Sent Events identical to the career report endpoint.
    """
    sess1 = _sessions.get(req.session_id_1)
    if not sess1:
        raise HTTPException(404, "Session for person 1 not found or expired.")
    p1_prompt = sess1.get("kundli_prompt", "")
    if not p1_prompt:
        raise HTTPException(400, "No kundli data in session 1 yet.")

    # Build kundli for person 2
    from backend.config import inject_pyjhora_path
    inject_pyjhora_path()
    engine = KundliEngine()
    try:
        kundli2 = engine.calculate(
            name            = req.person2_name or "Partner",
            date_of_birth   = req.person2_date_of_birth,
            time_of_birth   = req.person2_time_of_birth,
            place_of_birth  = req.person2_place_of_birth,
            latitude        = req.person2_latitude,
            longitude       = req.person2_longitude,
            timezone_offset = req.person2_timezone_offset,
        )
        p2_prompt = format_for_claude_compact(kundli2)
    except Exception as e:
        raise HTTPException(400, f"Could not calculate kundli for person 2: {e}")

    agent    = _get_agent()
    language = req.language

    def _event_stream():
        full = ""
        try:
            for event in agent.stream_compatibility_report(p1_prompt, p2_prompt, language):
                if event.get("type") == "chunk":
                    full += event["text"]
                    yield f'data: {json.dumps(event)}\n\n'
                elif event.get("type") == "done":
                    _save_report("", req.session_id_1, "compatibility", full, req.language)
                elif event.get("type") == "error":
                    yield f'data: {json.dumps(event)}\n\n'
        except Exception as exc:
            yield f'data: {json.dumps({"type": "error", "message": str(exc)})}\n\n'

    return StreamingResponse(_event_stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})





# ── Shadbala & Ashtakavarga endpoints ─────────────────────────────────────────

@app.get("/kundli/{session_id}/shadbala",
         summary="Calculate Shadbala (six-fold planetary strength)")
def get_shadbala(session_id: str):
    """
    Calculate Shadbala for the 7 classical planets in the session's kundli.

    Returns per-planet scores for all 6 bala components, totals,
    minimum required thresholds, and strongest/weakest planet rankings.
    """
    sess = _sessions.get(session_id)
    if not sess:
        raise HTTPException(404, "Session not found or expired.")

    kundli = sess.get("kundli_data") or sess.get("kundli", {})
    if not kundli:
        raise HTTPException(400, "No kundli data in session. Run /kundli/calculate first.")

    try:
        from backend.config import inject_pyjhora_path
        inject_pyjhora_path()
        engine = KundliEngine()
        result = engine.get_shadbala(kundli)
        return {"session_id": session_id, **result}
    except Exception as e:
        raise HTTPException(500, f"Shadbala calculation failed: {e}")


@app.get("/kundli/{session_id}/ashtakavarga",
         summary="Calculate Ashtakavarga (eight-source benefic points)")
def get_ashtakavarga(session_id: str):
    """
    Calculate complete Ashtakavarga for the session's kundli.

    Returns:
    - bhinnashtakavarga: per-planet rekhas in each of the 12 signs
    - sarvashtakavarga: total rekhas per sign
    - transit_strength: named sign → rekha count
    - strong_signs (≥30 rekhas), weak_signs (<25 rekhas)
    - total_rekhas (should be ~337 for a standard chart)
    """
    sess = _sessions.get(session_id)
    if not sess:
        raise HTTPException(404, "Session not found or expired.")

    kundli = sess.get("kundli_data") or sess.get("kundli", {})
    if not kundli:
        raise HTTPException(400, "No kundli data in session. Run /kundli/calculate first.")

    try:
        from backend.config import inject_pyjhora_path
        inject_pyjhora_path()
        engine = KundliEngine()
        result = engine.get_ashtakavarga(kundli)
        return {"session_id": session_id, **result}
    except Exception as e:
        raise HTTPException(500, f"Ashtakavarga calculation failed: {e}")


@app.get("/kundli/{session_id}/ashtakavarga/transit",
         summary="Score a planet's transit using Ashtakavarga")
def get_ashtakavarga_transit(
    session_id: str,
    planet: str = Query(..., description="Planet name e.g. Saturn"),
    sign:   str = Query(..., description="Transit sign e.g. Aquarius"),
):
    """
    Score the quality of a planet transiting a specific sign,
    using the Bhinnashtakavarga and Sarvashtakavarga rekhas.

    quality values: excellent | good | neutral | weak | challenging
    """
    sess = _sessions.get(session_id)
    if not sess:
        raise HTTPException(404, "Session not found or expired.")

    kundli = sess.get("kundli_data") or sess.get("kundli", {})
    if not kundli:
        raise HTTPException(400, "No kundli data in session. Run /kundli/calculate first.")

    valid_planets = {"Sun","Moon","Mars","Mercury","Jupiter","Venus","Saturn"}
    if planet.strip().title() not in valid_planets:
        raise HTTPException(400, f"Invalid planet. Choose from: {', '.join(sorted(valid_planets))}")

    try:
        from backend.config import inject_pyjhora_path
        inject_pyjhora_path()
        engine = KundliEngine()
        result = engine.get_ashtakavarga_transit(planet.strip().title(), sign.strip().title(), kundli)
        return {"session_id": session_id, **result}
    except Exception as e:
        raise HTTPException(500, f"Transit score calculation failed: {e}")


# ── B19: Divisional charts D1–D16 ─────────────────────────────────────────────

@app.get(
    "/kundli/{session_id}/divisional/{division}",
    summary="Get a single divisional chart (Varga) — B19",
    tags=["kundli"],
)
def get_divisional_chart(
    session_id: str,
    division: int,
):
    """
    B19 — Calculate a single Parashari divisional chart.

    **division** must be one of: 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 12, 16

    | D  | Name           | Domain                              |
    |----|----------------|-------------------------------------|
    | 1  | Rasi           | Birth chart (all-round)             |
    | 2  | Hora           | Wealth, finances                    |
    | 3  | Drekkana       | Siblings, courage                   |
    | 4  | Chaturthamsa   | Property, fixed assets              |
    | 5  | Panchamsa      | Past deeds, authority               |
    | 6  | Shashthamsa    | Health, enemies                     |
    | 7  | Saptamsha      | Children                            |
    | 8  | Ashtamsha      | Sudden events, longevity            |
    | 9  | Navamsa        | Spouse, dharma (most important!)    |
    | 10 | Dasamsa        | Career, livelihood                  |
    | 12 | Dwadasamsa     | Parents, ancestors                  |
    | 16 | Shodasamsa     | Vehicles, comforts                  |
    """
    sess = _sessions.get(session_id)
    if not sess:
        raise HTTPException(404, "Session not found or expired.")
    kundli = sess.get("kundli_data") or sess.get("kundli", {})
    if not kundli:
        raise HTTPException(400, "No kundli data in session. Run /kundli/start first.")

    supported = {1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 12, 16}
    if division not in supported:
        raise HTTPException(
            400,
            f"D{division} not supported. Supported divisions: {sorted(supported)}"
        )

    try:
        from backend.kundli_engine.divisional_charts import calculate_divisional_chart
        result = calculate_divisional_chart(kundli, division)
        return {"session_id": session_id, **result}
    except Exception as exc:
        raise HTTPException(500, f"Divisional chart D{division} calculation failed: {exc}")


@app.get(
    "/kundli/{session_id}/divisional",
    summary="Get all divisional charts D1–D16 (Vargas) — B19",
    tags=["kundli"],
)
def get_all_divisional_charts(session_id: str):
    """
    B19 — Calculate all supported Parashari divisional charts in one call.

    Returns a dict keyed by "D{N}_{Name}" e.g.:
    - "D2_Hora" — wealth
    - "D3_Drekkana" — siblings
    - "D9_Navamsa" — spouse/dharma (most important)
    - "D10_Dasamsa" — career
    - "D12_Dwadasamsa" — parents
    - "D16_Shodasamsa" — vehicles/comforts
    """
    sess = _sessions.get(session_id)
    if not sess:
        raise HTTPException(404, "Session not found or expired.")
    kundli = sess.get("kundli_data") or sess.get("kundli", {})
    if not kundli:
        raise HTTPException(400, "No kundli data in session. Run /kundli/start first.")

    try:
        from backend.kundli_engine.divisional_charts import calculate_all_divisional_charts
        result = calculate_all_divisional_charts(kundli)
        return {"session_id": session_id, "divisional_charts": result}
    except Exception as exc:
        raise HTTPException(500, f"Divisional charts calculation failed: {exc}")


@app.get(
    "/kundli/{session_id}/varga-strength/{planet}",
    summary="Get Vaiseshikamsa (Varga strength) for a planet — B19",
    tags=["kundli"],
)
def get_varga_strength(session_id: str, planet: str):
    """
    B19 — Compute the Vaiseshikamsa (Varga strength) of a planet.

    Counts how many of the 12 Vargas the planet occupies in its
    own sign or exaltation sign. Classical categories:

    - Vargottama (same sign in D1 + D9)
    - Parijata (2), Uttama (3), Gopura (4), Simhasana (5)
    - Paravata (6), Devaloka (7), Brahmaloka (8), Sridhama (10)
    """
    sess = _sessions.get(session_id)
    if not sess:
        raise HTTPException(404, "Session not found or expired.")
    kundli = sess.get("kundli_data") or sess.get("kundli", {})
    if not kundli:
        raise HTTPException(400, "No kundli data in session. Run /kundli/start first.")

    valid = {"Sun","Moon","Mars","Mercury","Jupiter","Venus","Saturn","Rahu","Ketu"}
    p = planet.strip().title()
    if p not in valid:
        raise HTTPException(400, f"Invalid planet. Choose from: {', '.join(sorted(valid))}")

    try:
        from backend.kundli_engine.divisional_charts import get_varga_strength
        result = get_varga_strength(p, kundli)
        return {"session_id": session_id, **result}
    except Exception as exc:
        raise HTTPException(500, f"Varga strength calculation failed: {exc}")


# ── Yearly Forecast & Remedies Reports ────────────────────────────────────────

class YearlyForecastRequest(BaseModel):
    email:    str = ""
    year:     int | None = None   # defaults to current year inside agent
    language: str = "English"


class RemediesRequest(BaseModel):
    email:    str = ""
    area:     str = "general"     # general|career|health|relationships|finance
    language: str = "English"


@app.post("/report/yearly-forecast/{session_id}",
          summary="Generate 12-month Vedic yearly forecast (SSE streaming)")
def report_yearly_forecast(session_id: str, req: YearlyForecastRequest):
    """
    Stream a month-by-month Vedic yearly forecast for the session's chart.
    Uses Dasha periods and planetary transits for the requested year.
    Returns Server-Sent Events identical to the career report endpoint.
    """
    sess = _sessions.get(session_id)
    if not sess:
        raise HTTPException(404, "Session not found or expired.")

    profile: dict = {}
    if req.email:
        _email = req.email.strip().lower()
        db_profile = _db.get_profile(_email)
        if db_profile:
            profile = db_profile

    if sess.get("kundli_data"):
        profile["kundli_data"] = sess["kundli_data"]
    if sess.get("kundli_prompt"):
        profile["kundli_prompt"] = sess["kundli_prompt"]
    if sess.get("planet_knowledge"):
        _pk = sess["planet_knowledge"]
        profile["planet_knowledge"] = _pk.to_dict() if hasattr(_pk, "to_dict") else _pk

    if not profile.get("kundli_prompt") and not profile.get("kundli_data"):
        raise HTTPException(400, "No kundli data in session. Run /kundli/calculate first.")

    agent    = _get_agent()
    _year    = req.year
    language = req.language

    def _event_stream():
        full = ""
        try:
            for event in agent.stream_yearly_forecast(profile, _year, language):
                if event.get("type") == "chunk":
                    full += event["text"]
                    yield f"data: {json.dumps(event)}\n\n"
                elif event.get("type") == "done":
                    _save_report(req.email, session_id, "yearly_forecast", full, req.language)
                elif event.get("type") == "error":
                    yield f"data: {json.dumps(event)}\n\n"
        except Exception as exc:
            yield f"data: {json.dumps({'type': 'error', 'message': str(exc)})}\n\n"

    return StreamingResponse(
        _event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.post("/report/remedies/{session_id}",
          summary="Generate Vedic remedies report (SSE streaming)")
def report_remedies(session_id: str, req: RemediesRequest):
    """
    Stream personalised Vedic remedies for the session's chart.
    area choices: general | career | health | relationships | finance
    Returns Server-Sent Events identical to the career report endpoint.
    """
    sess = _sessions.get(session_id)
    if not sess:
        raise HTTPException(404, "Session not found or expired.")

    profile: dict = {}
    if req.email:
        _email = req.email.strip().lower()
        db_profile = _db.get_profile(_email)
        if db_profile:
            profile = db_profile

    if sess.get("kundli_data"):
        profile["kundli_data"] = sess["kundli_data"]
    if sess.get("kundli_prompt"):
        profile["kundli_prompt"] = sess["kundli_prompt"]
    if sess.get("planet_knowledge"):
        _pk = sess["planet_knowledge"]
        profile["planet_knowledge"] = _pk.to_dict() if hasattr(_pk, "to_dict") else _pk

    if not profile.get("kundli_prompt") and not profile.get("kundli_data"):
        raise HTTPException(400, "No kundli data in session. Run /kundli/calculate first.")

    valid_areas = {"general", "career", "health", "relationships", "finance"}
    area = (req.area or "general").lower().strip()
    if area not in valid_areas:
        raise HTTPException(400, f"Invalid area '{area}'. Choose from: {', '.join(sorted(valid_areas))}")

    agent    = _get_agent()
    language = req.language

    def _event_stream():
        full = ""
        try:
            for event in agent.stream_remedies_report(profile, area, language):
                if event.get("type") == "chunk":
                    full += event["text"]
                    yield f"data: {json.dumps(event)}\n\n"
                elif event.get("type") == "done":
                    _save_report(req.email, session_id, "remedies", full, req.language)
                elif event.get("type") == "error":
                    yield f"data: {json.dumps(event)}\n\n"
        except Exception as exc:
            yield f"data: {json.dumps({'type': 'error', 'message': str(exc)})}\n\n"

    return StreamingResponse(
        _event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ── Reading History endpoints ──────────────────────────────────────────────────

@app.post("/kundli/archive/{session_id}", summary="Archive current reading to history before starting new")
def archive_reading(session_id: str, req: EmailReportRequest):
    """Save the current completed reading to the user's reading history."""
    email = req.email.strip().lower()
    if not email:
        raise HTTPException(400, "Email required.")
    sess = _sessions.get(session_id)
    profile = _db.get_profile(email)
    if not profile:
        raise HTTPException(404, "User not found.")

    refined = (sess or {}).get("refined_analysis") or profile.get("refined_analysis", "")
    if not refined:
        return {"success": True, "archived": False, "reason": "no_reading"}

    chat_msgs = []
    if sess:
        chat_msgs = [m for m in sess.get("messages", [])
                     if m.get("content") != "[Prior session restored]"]
    if not chat_msgs:
        chat_msgs = profile.get("chat_messages_json") or []

    pk = {}
    if sess and sess.get("planet_knowledge"):
        pk_obj = sess["planet_knowledge"]
        pk = pk_obj.to_dict() if hasattr(pk_obj, "to_dict") else {}
    if not pk:
        pk = profile.get("planet_knowledge_json") or {}

    reading = {
        "name":                 profile.get("name", ""),
        "date_of_birth":        profile.get("date_of_birth", ""),
        "time_of_birth":        profile.get("time_of_birth", ""),
        "place_of_birth":       profile.get("place_of_birth", ""),
        "overall_theme":        profile.get("overall_theme", ""),
        "refined_analysis":     refined,
        "chat_messages_json":   chat_msgs,
        "planet_knowledge_json": pk,
        "session_id":           session_id,
    }
    rid = _db.save_reading_to_history(email, reading)
    return {"success": True, "archived": True, "reading_id": rid}


@app.get("/user/readings", summary="List all past readings for a user")
def list_readings(email: str = Query(...)):
    email = email.strip().lower()
    if not email:
        raise HTTPException(400, "Email required.")
    history = _db.get_reading_history(email)
    return {"readings": history, "count": len(history)}


@app.get("/user/readings/{reading_id}", summary="Get full reading by id")
def get_reading(reading_id: str, email: str = Query(...)):
    email = email.strip().lower()
    reading = _db.get_reading_by_id(reading_id, email)
    if not reading:
        raise HTTPException(404, "Reading not found.")
    return reading


@app.post("/user/lookup", include_in_schema=True)
def user_lookup(req: LookupRequest):
    profile = _db.get_profile(req.email)
    if not profile:
        raise HTTPException(404, "Session not found.")
    return {"found": True, "profile": profile}

@app.post("/user/save", include_in_schema=True)
def user_save(req: SaveRequest):
    result = _db.save_profile(req.data)
    return result

@app.delete("/user/{email}", include_in_schema=True)
def user_delete(email: str):
    deleted = _db.delete_user(email)
    return {"deleted": deleted}


# ── GDPR: Self-service data export ───────────────────────────────────────────

@app.get("/user/data-export", summary="GDPR: Export all personal data (authenticated user)")
def user_data_export(current_email: str = Depends(get_current_email)):
    """
    Return a complete JSON export of all data held for the authenticated user.
    Includes: profile, kundli profiles, wallet ledger, reading history, AI reports metadata.
    Fulfils GDPR Article 20 (Data Portability) right.
    """
    import datetime as _dt

    profile    = _db.get_profile(current_email) or {}
    profiles   = _db.list_kundli_profiles(current_email)
    ledger     = _db.get_wallet_transactions(current_email, limit=1000)
    readings   = _db.list_ai_reports(current_email, limit=500)
    # Remove sensitive auth columns from profile export
    safe_profile = {k: v for k, v in profile.items()
                    if k not in ("password_hash", "mfa_secret", "verification_token",
                                 "reset_token", "reset_token_expires")}

    export = {
        "export_generated_at":  _dt.datetime.utcnow().isoformat() + "Z",
        "gdpr_article":         "Article 20 — Right to Data Portability",
        "email":                current_email,
        "account":              safe_profile,
        "kundli_profiles":      profiles,
        "wallet_ledger":        ledger,
        "ai_reports_metadata":  readings,
    }

    # Log the export request for GDPR audit trail
    try:
        _db._execute_query(
            "UPDATE users SET data_export_requested_at = NOW() WHERE email = %s",
            (current_email,)
        )
    except Exception:
        pass   # Non-critical; don't fail the export if logging fails

    return export


# ── GDPR: Self-service account deletion ──────────────────────────────────────

class DeleteAccountRequest(BaseModel):
    confirmation: str   # Must equal "DELETE MY ACCOUNT" to confirm intent


@app.delete("/user/account", summary="GDPR: Permanently delete authenticated user account")
def delete_own_account(
    req: DeleteAccountRequest,
    current_email: str = Depends(get_current_email),
):
    """
    Soft-delete and anonymise the authenticated user's account.

    The user must send { "confirmation": "DELETE MY ACCOUNT" } to confirm intent.
    PII fields are replaced with anonymised values; financial ledger is retained
    for tax/audit purposes (GDPR Recital 65 — legal obligation exemption).

    This action is IRREVERSIBLE.
    """
    if req.confirmation != "DELETE MY ACCOUNT":
        raise HTTPException(
            status_code=422,
            detail="Confirmation text must be exactly: DELETE MY ACCOUNT"
        )

    import datetime as _dt
    import uuid as _uuid

    anon_id   = str(_uuid.uuid4())[:8]
    anon_email = f"deleted-{anon_id}@deleted.invalid"
    now        = _dt.datetime.utcnow().isoformat()

    try:
        # 1. Anonymise the user's PII in the users table
        _db._execute_query(
            """UPDATE users SET
                email             = %s,
                password_hash     = 'DELETED',
                mfa_secret        = NULL,
                mfa_enabled       = FALSE,
                verification_token = NULL,
                reset_token       = NULL,
                is_deleted        = TRUE,
                deleted_at        = NOW(),
                anonymised_at     = NOW()
               WHERE email = %s""",
            (anon_email, current_email)
        )

        # 2. Anonymise name in kundli_profiles (keep DOB/location for astrological integrity)
        _db._execute_query(
            "UPDATE kundli_profiles SET name = %s WHERE user_email = %s",
            ("deleted-user", current_email)
        )

        # 3. Invalidate all active sessions for this user (security)
        try:
            from backend.persistence.session_store import _store as _session_store
            _session_store.delete(current_email)
        except Exception:
            pass

        _audit_log(action="gdpr_account_deletion", target=current_email)
        return {
            "success":    True,
            "message":    "Your account has been permanently deleted and all PII anonymised.",
            "anonymised_as": anon_email,
            "deleted_at": now,
        }

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Account deletion failed: {exc}. Please contact support."
        )


# ── AI Reports management endpoints ──────────────────────────────────────────

@app.get("/reports", summary="List AI reports for the authenticated user")
def list_reports(
    report_type: str = Query("", description="Filter: career|yearly_forecast|remedies|compatibility"),
    limit:       int = Query(50, ge=1, le=200),
    email: str = Depends(get_current_email),
):
    """
    Return metadata records for all AI reports generated by the user.
    Does NOT return full content — use GET /reports/{report_id} for that.
    """
    records = _db.list_ai_reports(email, report_type=report_type, limit=limit)
    return {"reports": records, "count": len(records)}


@app.get("/reports/{report_id}", summary="Get a single AI report with full content")
def get_report(
    report_id: str,
    email: str = Depends(get_current_email),
):
    """
    Fetch a report record and its full text content from storage.
    Returns 404 if not found or not owned by the authenticated user.
    """
    record = _db.get_ai_report(report_id, email)
    if not record:
        raise HTTPException(404, "Report not found.")

    # Fetch full content from object store
    key = record.get("storage_key", "")
    full_content = None
    if key:
        try:
            from backend.storage.report_store import get_report_store
            full_content = get_report_store().load(key)
        except Exception:
            pass

    return {
        **record,
        "content": full_content or record.get("content_preview", ""),
        "has_full_content": full_content is not None,
    }


@app.get("/reports/{report_id}/download-url",
         summary="Get a presigned or local download URL for a report")
def get_report_download_url(
    report_id: str,
    expires:   int = Query(3600, ge=60, le=86400, description="URL expiry seconds"),
    email: str = Depends(get_current_email),
):
    """
    Generate a temporary download link for the report file.
    For S3 storage: returns a presigned URL (valid for `expires` seconds).
    For local storage: returns a /reports/download?key=... path.
    """
    record = _db.get_ai_report(report_id, email)
    if not record:
        raise HTTPException(404, "Report not found.")

    key = record.get("storage_key", "")
    if not key:
        raise HTTPException(400, "No storage key found for this report.")

    try:
        from backend.storage.report_store import get_report_store
        store = get_report_store()
        url   = store.presigned_url(key, expires=expires)
        return {
            "report_id": report_id,
            "url":       url,
            "backend":   store.backend,
            "expires_in_seconds": expires,
        }
    except Exception as e:
        raise HTTPException(500, f"Could not generate download URL: {e}")


@app.get("/reports/download", include_in_schema=False)
def download_report_local(key: str = Query(...)):
    """
    Serve a locally stored report file by its storage key.
    Only works when REPORT_LOCAL_DIR storage is in use.
    This endpoint is referenced by local presigned_url() returns.
    """
    try:
        from backend.storage.report_store import get_report_store, _local_path
        store = get_report_store()
        if store.backend == "s3":
            raise HTTPException(400, "Use the presigned S3 URL for S3-backed reports.")
        content = store.load(key)
        if content is None:
            raise HTTPException(404, "Report file not found.")
        from fastapi.responses import PlainTextResponse
        return PlainTextResponse(content, media_type="text/plain; charset=utf-8")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Could not serve report: {e}")


@app.delete("/reports/{report_id}", summary="Delete an AI report record and its stored file")
def delete_report(
    report_id: str,
    email: str = Depends(get_current_email),
):
    """
    Delete the DB record and the stored report file for the given report ID.
    Returns 404 if the report is not found or not owned by the user.
    """
    record = _db.get_ai_report(report_id, email)
    if not record:
        raise HTTPException(404, "Report not found.")

    # Delete from object store
    key = record.get("storage_key", "")
    store_deleted = False
    if key:
        try:
            from backend.storage.report_store import get_report_store
            store_deleted = get_report_store().delete(key)
        except Exception:
            pass

    # Delete DB record
    _db.delete_ai_report(report_id, email)

    return {"success": True, "report_id": report_id, "file_deleted": store_deleted}


# ── Kundli Profiles (multi-profile support) ───────────────────────────────────

class ProfileCreateRequest(BaseModel):
    label:          str  = "Me"
    name:           str  = ""
    date_of_birth:  str  = ""
    time_of_birth:  str  = ""
    place_of_birth: str  = ""
    latitude:       float = 0.0
    longitude:      float = 0.0
    timezone_offset: float = 0.0
    gender:         str | None = None   # "M" | "F" | "Other" | None
    kundli_json:    dict  = {}
    refined_analysis: str = ""
    planet_knowledge_json: dict = {}


class ProfileUpdateRequest(BaseModel):
    label:          str | None = None
    name:           str | None = None
    date_of_birth:  str | None = None
    time_of_birth:  str | None = None
    place_of_birth: str | None = None
    latitude:       float | None = None
    longitude:      float | None = None
    timezone_offset: float | None = None
    gender:         str | None = None   # "M" | "F" | "Other" | None
    kundli_json:    dict | None = None
    refined_analysis: str | None = None
    planet_knowledge_json: dict | None = None


@app.post("/profiles", summary="Create a new kundli profile for the authenticated user")
def create_profile(
    req: ProfileCreateRequest,
    email: str = Depends(get_current_email),
):
    """
    Create a new kundli profile (e.g. self, spouse, child).
    The first profile created is automatically set as active.
    """
    data = req.dict()
    profile = _db.create_kundli_profile(email, data)
    return {"success": True, "profile": profile}


@app.get("/profiles", summary="List all kundli profiles for the authenticated user")
def list_profiles(email: str = Depends(get_current_email)):
    """Return all kundli profiles owned by the authenticated user."""
    profiles = _db.list_kundli_profiles(email)
    return {"profiles": profiles, "count": len(profiles)}


@app.get("/profiles/active", summary="Get the currently active kundli profile")
def get_active_profile(email: str = Depends(get_current_email)):
    """Return the active kundli profile, or 404 if none exists yet."""
    profile = _db.get_active_kundli_profile(email)
    if not profile:
        raise HTTPException(404, "No active kundli profile found. Create one first.")
    return {"profile": profile}


@app.get("/profiles/{profile_id}", summary="Get a single kundli profile by ID")
def get_profile(
    profile_id: str,
    email: str = Depends(get_current_email),
):
    """Fetch a specific profile by ID, scoped to the authenticated user."""
    profile = _db.get_kundli_profile(profile_id, email)
    if not profile:
        raise HTTPException(404, "Profile not found.")
    return {"profile": profile}


@app.put("/profiles/{profile_id}", summary="Update a kundli profile")
def update_profile(
    profile_id: str,
    req: ProfileUpdateRequest,
    email: str = Depends(get_current_email),
):
    """Update mutable fields of a kundli profile. Only provided fields are changed."""
    data = {k: v for k, v in req.dict().items() if v is not None}
    updated = _db.update_kundli_profile(profile_id, email, data)
    if not updated:
        raise HTTPException(404, "Profile not found.")
    return {"success": True, "profile": updated}


@app.post("/profiles/{profile_id}/activate",
          summary="Set a profile as active and load it into a new session")
def activate_profile(
    profile_id: str,
    email: str = Depends(get_current_email),
):
    """
    Mark the given profile as active (deactivates all others).
    Returns the activated profile and a fresh session_id pre-loaded with its data,
    so the frontend can immediately start a kundli session for the selected person.
    """
    ok = _db.set_active_kundli_profile(profile_id, email)
    if not ok:
        raise HTTPException(404, "Profile not found.")

    profile = _db.get_kundli_profile(profile_id, email)

    # Spin up a fresh in-memory session pre-loaded with this profile's data
    import uuid as _uuid
    new_session_id = str(_uuid.uuid4())
    sess_data: dict = {
        "email":      email,
        "profile_id": profile_id,
        "messages":   [],
    }
    if profile.get("kundli_json"):
        sess_data["kundli_data"] = profile["kundli_json"]
    if profile.get("refined_analysis"):
        sess_data["refined_analysis"] = profile["refined_analysis"]
    if profile.get("planet_knowledge_json"):
        from backend.ai_interpretation.planet_knowledge import PlanetKnowledge
        try:
            sess_data["planet_knowledge"] = PlanetKnowledge.from_dict(
                profile["planet_knowledge_json"]
            )
        except Exception:
            pass
    _sessions[new_session_id] = sess_data

    return {
        "success":    True,
        "session_id": new_session_id,
        "profile":    profile,
    }


@app.delete("/profiles/{profile_id}", summary="Delete a kundli profile")
def delete_profile(
    profile_id: str,
    email: str = Depends(get_current_email),
):
    """
    Delete a kundli profile. If it was the active profile, the next most-recently-
    updated profile is automatically activated.
    """
    deleted = _db.delete_kundli_profile(profile_id, email)
    if not deleted:
        raise HTTPException(404, "Profile not found.")
    return {"success": True, "deleted_id": profile_id}


# ── Shareable Reading Links ───────────────────────────────────────────────────

class ShareReadingRequest(BaseModel):
    email:    str
    pin:      str            # exactly 4 digits
    ttl_hours: int = 72     # default 72h expiry

class AccessShareRequest(BaseModel):
    pin: str


@app.post("/reading/share/{session_id}", summary="Create a PIN-protected shareable reading link")
def create_share_link(session_id: str, req: ShareReadingRequest):
    """
    Snapshot the current session's reading and create a 72-hour shareable link.
    The link is protected by a 4-digit PIN the owner sets at share time.

    Returns:
        {"token": str, "share_url": str, "expires_at": str, "pin_hint": "****"}
    """
    if not req.email:
        raise HTTPException(400, "Email required.")
    if not req.pin.isdigit() or len(req.pin) != 4:
        raise HTTPException(400, "PIN must be exactly 4 digits.")

    sess = _sessions.get(session_id)
    profile = _db.get_profile(req.email)
    if not profile:
        raise HTTPException(404, "User not found.")

    # Pull content from session (live) or profile (persisted)
    refined = (sess or {}).get("refined_analysis") or profile.get("refined_analysis", "")
    if not refined:
        raise HTTPException(400, "No deep reading found. Please complete Step 2 first.")

    overall_theme = (sess or {}).get("overall_theme") or profile.get("overall_theme", "")
    lagna_info    = (sess or {}).get("lagna_info") or {}

    result = _db.create_shared_reading(
        email      = req.email,
        pin        = req.pin,
        session_id = session_id,
        content    = {
            "name":             profile.get("name", ""),
            "date_of_birth":    profile.get("date_of_birth", ""),
            "time_of_birth":    profile.get("time_of_birth", ""),
            "place_of_birth":   profile.get("place_of_birth", ""),
            "overall_theme":    overall_theme,
            "refined_analysis": refined,
            "lagna_info":       lagna_info,
        },
        ttl_hours  = req.ttl_hours,
    )
    if not result.get("success"):
        raise HTTPException(400, result.get("error", "Could not create share link."))
    token     = result["token"]
    share_url = f"/reading/shared/{token}"
    return {
        "token":      token,
        "share_url":  share_url,
        "expires_at": result["expires_at"],
        "pin_hint":   "****",
    }


@app.get("/reading/shared/{token}", summary="View shared reading metadata")
def get_shared_reading_meta(token: str):
    """Return metadata for a shared reading (no content without PIN)."""
    reading = _db.get_shared_reading(token)
    if not reading:
        raise HTTPException(404, "Share link not found or expired.")
    return {
        "token":      token,
        "name":       reading.get("name", ""),
        "expires_at": str(reading.get("expires_at", "")),
        "view_count": reading.get("view_count", 0),
    }


@app.post("/reading/shared/{token}/access", summary="Access shared reading with PIN")
def access_shared_reading(token: str, req: AccessShareRequest):
    """Verify PIN and return the full shared reading content."""
    reading = _db.access_shared_reading(token, req.pin)
    if not reading:
        raise HTTPException(403, "Invalid PIN or link expired.")
    return reading


@app.delete("/reading/shared/{token}", summary="Delete a shared reading link")
def delete_shared_reading(
    token: str,
    email: str = Query(..., description="Owner email for verification"),
    _auth: dict = Depends(get_current_user),
):
    """Delete a shared reading. Only the creator can delete."""
    deleted = _db.delete_shared_reading(token, email)
    if not deleted:
        raise HTTPException(404, "Share link not found or not owned by this account.")
    return {"success": True}


# ── Frontend static files ──────────────────────────────────────────────────────

# ═══════════════════════════════════════════════════════════════════════════════
# Admin Panel  —  GET /admin  |  POST /admin/login  |  POST /admin/logout
# ═══════════════════════════════════════════════════════════════════════════════
# Auth uses ADMIN_PASSWORD (or ADMIN_SECRET) from .env — see backend/api/security.py
# On success, an HttpOnly cookie "admin_token" is set so the browser stays logged in.

from backend.api.security import ADMIN_USERNAME as _ADMIN_USERNAME

_ADMIN_PANEL_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>NarayanAstroReader — Admin</title>
<style>
  :root{--bg:#0f0f1a;--card:#1a1a2e;--accent:#7c3aed;--text:#e0e0ff;--sub:#9090b0;--danger:#ef4444;--ok:#22c55e}
  *{box-sizing:border-box;margin:0;padding:0}
  body{background:var(--bg);color:var(--text);font-family:system-ui,sans-serif;min-height:100vh;display:flex;flex-direction:column;align-items:center;padding:2rem 1rem}
  h1{font-size:1.6rem;margin-bottom:.3rem}
  .sub{color:var(--sub);font-size:.9rem;margin-bottom:2rem}
  .card{background:var(--card);border-radius:12px;padding:2rem;width:100%;max-width:480px;box-shadow:0 4px 32px #0008}
  label{display:block;font-size:.85rem;color:var(--sub);margin-bottom:.3rem;margin-top:1rem}
  input{width:100%;padding:.7rem 1rem;border-radius:8px;border:1px solid #333;background:#0f0f1a;color:var(--text);font-size:1rem}
  input:focus{outline:2px solid var(--accent);border-color:var(--accent)}
  button{margin-top:1.5rem;width:100%;padding:.85rem;border-radius:8px;border:none;background:var(--accent);color:#fff;font-size:1rem;font-weight:600;cursor:pointer}
  button:hover{opacity:.88}
  .err{color:var(--danger);font-size:.85rem;margin-top:.8rem;display:none}
  .err.show{display:block}
</style>
</head>
<body>
<h1>🪐 Admin Panel</h1>
<p class="sub">NarayanAstroReader — Super Admin</p>
<div class="card">
  <form id="loginForm">
    <label>Username</label>
    <input id="uname" type="text" autocomplete="username" value="admin">
    <label>Password</label>
    <input id="pwd" type="password" autocomplete="current-password" placeholder="Your ADMIN_PASSWORD">
    <label>Authenticator Code <span style="color:var(--sub);font-weight:400">(required in production)</span></label>
    <input id="totp" type="text" inputmode="numeric" pattern="[0-9]{6}" maxlength="6" autocomplete="one-time-code" placeholder="6-digit TOTP code">
    <button type="submit">Login</button>
    <p class="err" id="err">Invalid credentials.</p>
  </form>
</div>
<script>
document.getElementById('loginForm').addEventListener('submit', async e => {
  e.preventDefault();
  const err = document.getElementById('err');
  err.classList.remove('show');
  const res = await fetch('/admin/login', {
    method: 'POST',
    headers: {'Content-Type':'application/json'},
    body: JSON.stringify({
      username:  document.getElementById('uname').value,
      password:  document.getElementById('pwd').value,
      totp_code: document.getElementById('totp').value.trim()
    })
  });
  if (res.ok) { location.reload(); }
  else { err.textContent = (await res.json()).detail || 'Login failed.'; err.classList.add('show'); }
});
</script>
</body>
</html>"""

_ADMIN_DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Admin Dashboard — NarayanAstroReader</title>
<style>
  :root{--bg:#0f0f1a;--card:#1a1a2e;--accent:#7c3aed;--text:#e0e0ff;--sub:#9090b0;--danger:#ef4444;--ok:#22c55e}
  *{box-sizing:border-box;margin:0;padding:0}
  body{background:var(--bg);color:var(--text);font-family:system-ui,sans-serif;min-height:100vh;padding:2rem 1rem}
  header{display:flex;align-items:center;justify-content:space-between;margin-bottom:2rem;max-width:1000px;margin-left:auto;margin-right:auto}
  h1{font-size:1.4rem}
  .logout-btn{background:var(--danger);color:#fff;border:none;padding:.5rem 1.2rem;border-radius:8px;cursor:pointer;font-size:.9rem}
  .grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:1rem;max-width:1000px;margin:0 auto 2rem}
  .stat{background:var(--card);border-radius:10px;padding:1.2rem;text-align:center}
  .stat .num{font-size:2rem;font-weight:700;color:var(--accent)}
  .stat .lbl{font-size:.8rem;color:var(--sub);margin-top:.3rem}
  .section{max-width:1000px;margin:0 auto 2rem}
  .section h2{font-size:1rem;color:var(--sub);margin-bottom:.8rem;text-transform:uppercase;letter-spacing:.05em}
  table{width:100%;border-collapse:collapse;font-size:.85rem}
  th{text-align:left;padding:.5rem .8rem;border-bottom:1px solid #333;color:var(--sub)}
  td{padding:.5rem .8rem;border-bottom:1px solid #1a1a2e}
  tr:hover td{background:#1a1a2e}
  .badge{display:inline-block;padding:.1rem .5rem;border-radius:4px;font-size:.75rem}
  .badge.ok{background:#166534;color:#bbf7d0}
  .badge.no{background:#7f1d1d;color:#fecaca}
  .btn{padding:.3rem .8rem;border-radius:6px;border:none;cursor:pointer;font-size:.8rem}
  .btn-verify{background:#1e3a5f;color:#93c5fd}
  .btn-delete{background:#7f1d1d;color:#fca5a5}
  .err{color:var(--danger);font-size:.85rem}
</style>
</head>
<body>
<header>
  <h1>🪐 Admin Dashboard</h1>
  <button class="logout-btn" onclick="logout()">Logout</button>
</header>
<div class="grid" id="stats"><p style="color:var(--sub);text-align:center;grid-column:1/-1">Loading stats…</p></div>
<div class="section">
  <h2>Recent Users</h2>
  <table id="usersTable">
    <thead><tr><th>Email</th><th>Name</th><th>Verified</th><th>Wallet (₹)</th><th>Region</th><th>Joined</th><th>Actions</th></tr></thead>
    <tbody id="usersBody"><tr><td colspan="7" style="color:var(--sub)">Loading…</td></tr></tbody>
  </table>
</div>
<script>
async function api(path, opts){
  const r = await fetch(path, {credentials:'include', ...opts});
  if (!r.ok) throw new Error(await r.text());
  return r.json();
}
async function load(){
  try {
    const d = await api('/admin/stats');
    document.getElementById('stats').innerHTML =
      `<div class="stat"><div class="num">${d.total_users}</div><div class="lbl">Total Users</div></div>
       <div class="stat"><div class="num">${d.verified_users}</div><div class="lbl">Verified</div></div>
       <div class="stat"><div class="num">${d.total_readings}</div><div class="lbl">Readings</div></div>
       <div class="stat"><div class="num">₹${(d.total_wallet_paise/100).toFixed(0)}</div><div class="lbl">Wallet Funds</div></div>`;
  } catch(e){ document.getElementById('stats').innerHTML = '<p class="err">Stats unavailable: '+e.message+'</p>'; }
  try {
    const users = await api('/admin/users?limit=50');
    document.getElementById('usersBody').innerHTML = users.map(u =>
      `<tr>
        <td>${u.email}</td>
        <td>${u.name||'—'}</td>
        <td><span class="badge ${u.email_verified?'ok':'no'}">${u.email_verified?'✓':'✗'}</span></td>
        <td>${(u.wallet_balance_cents/100).toFixed(2)}</td>
        <td>${u.region||'India'}</td>
        <td>${u.created_at?u.created_at.substring(0,10):'—'}</td>
        <td>
          ${!u.email_verified?`<button class="btn btn-verify" onclick="verify('${u.email}')">Verify</button> `:''}
          <button class="btn btn-delete" onclick="del('${u.email}')">Delete</button>
        </td>
      </tr>`).join('');
  } catch(e){ document.getElementById('usersBody').innerHTML = `<tr><td colspan="7" class="err">${e.message}</td></tr>`; }
}
async function verify(email){
  if(!confirm('Force-verify '+email+'?')) return;
  await api('/admin/verify-user', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({email})});
  load();
}
async function del(email){
  if(!confirm('Delete user '+email+'? This is irreversible.')) return;
  await api('/admin/delete-user', {method:'DELETE', headers:{'Content-Type':'application/json'}, body:JSON.stringify({email})});
  load();
}
async function logout(){
  await fetch('/admin/logout', {method:'POST', credentials:'include'});
  location.reload();
}
load();
</script>
</body>
</html>"""


class AdminLoginRequest(BaseModel):
    username: str
    password: str
    totp_code: str = ""   # B2: Required when ADMIN_TOTP_SECRET is configured


@app.get("/admin", include_in_schema=False)
def admin_panel(request: Request, admin_token: str | None = Cookie(default=None)):
    """
    Admin panel entry point.
    — No valid cookie  → show the login page.
    — Valid cookie     → show the dashboard.
    """
    import secrets as _sec
    token = admin_token or request.headers.get("X-Admin-Secret", "")
    authenticated = bool(token and _sec.compare_digest(token, ADMIN_SECRET))
    html = _ADMIN_DASHBOARD_HTML if authenticated else _ADMIN_PANEL_HTML
    return HTMLResponse(content=html)


@app.post("/admin/login", include_in_schema=False)
def admin_login(req: AdminLoginRequest, response: Response, request: Request):
    """Validate admin username + password, issue HttpOnly session cookie."""
    import secrets as _sec
    import time as _time

    ip = request.client.host if request.client else "unknown"
    now = _time.time()

    # Brute-force guard (reuse the tracker from security.py)
    from backend.api.security import _admin_fails, _ADMIN_LOCKOUT_WINDOW, _ADMIN_MAX_FAILS
    fails = [t for t in _admin_fails.get(ip, []) if now - t < _ADMIN_LOCKOUT_WINDOW]
    if len(fails) >= _ADMIN_MAX_FAILS:
        raise HTTPException(429, "Too many failed attempts. Try again in 15 minutes.")

    username_ok = _sec.compare_digest(req.username, _ADMIN_USERNAME)
    password_ok = _sec.compare_digest(req.password, ADMIN_SECRET)

    if not (username_ok and password_ok):
        fails.append(now)
        _admin_fails[ip] = fails
        raise HTTPException(401, "Invalid admin credentials.")

    # ── B2: Enforce MFA for admin accounts ────────────────────────────────────
    # ADMIN_TOTP_SECRET must be a pyotp-compatible base32 secret set in .env.
    # Generate one with: python -c "import pyotp; print(pyotp.random_base32())"
    # If not set in production (ENVIRONMENT=production), login is blocked to
    # prevent unprotected admin access. In dev/staging, warn but allow.
    admin_totp_secret: str = os.environ.get("ADMIN_TOTP_SECRET", "")
    _env = os.environ.get("ENVIRONMENT", "development").lower()

    if admin_totp_secret:
        from backend.auth.mfa import verify_totp as _verify_totp
        if not req.totp_code:
            raise HTTPException(
                401,
                "MFA required for admin login. Provide 'totp_code' from your authenticator app.",
            )
        if not _verify_totp(admin_totp_secret, req.totp_code):
            fails.append(now)
            _admin_fails[ip] = fails
            raise HTTPException(401, "Invalid MFA code.")
    elif _env == "production":
        # No TOTP secret configured but we're in production — block login entirely.
        # Admin must configure ADMIN_TOTP_SECRET before production access is allowed.
        import logging as _log
        _log.getLogger(__name__).critical(
            "SECURITY: Admin login blocked — ADMIN_TOTP_SECRET not configured in production. "
            "Set ADMIN_TOTP_SECRET in .env to enable admin access."
        )
        raise HTTPException(
            503,
            "Admin MFA is not configured. Set ADMIN_TOTP_SECRET in environment before "
            "attempting admin login in production.",
        )
    else:
        # Dev/staging: allow login but emit a clear warning
        import logging as _log
        _log.getLogger(__name__).warning(
            "SECURITY WARNING: Admin logged in WITHOUT MFA (ADMIN_TOTP_SECRET not set). "
            "This is only acceptable in development/staging."
        )
    # ── End B2 ────────────────────────────────────────────────────────────────

    _admin_fails.pop(ip, None)
    # Set HttpOnly cookie so the dashboard JS can make credentialed requests
    response.set_cookie(
        key="admin_token",
        value=ADMIN_SECRET,
        httponly=True,
        samesite="lax",
        max_age=3600 * 8,   # 8-hour session
    )
    return {"success": True}


@app.post("/admin/logout", include_in_schema=False)
def admin_logout(response: Response):
    """Clear the admin session cookie."""
    response.delete_cookie("admin_token")
    return {"success": True}


@app.get("/admin/mfa/setup", include_in_schema=False, dependencies=[Depends(admin_auth)])
def admin_mfa_setup():
    """
    B2 — Generate a new TOTP secret for admin MFA setup.
    Returns the base32 secret + otpauth:// URL + QR code data URL.

    Steps:
      1. Call this endpoint to get a new secret.
      2. Scan the QR code (or enter the secret) in your authenticator app.
      3. Add ADMIN_TOTP_SECRET=<secret> to your .env file.
      4. Restart the server — admin login now requires the TOTP code.
    """
    from backend.auth.mfa import generate_mfa_setup
    try:
        data = generate_mfa_setup("admin@narayan-astro")
        return {
            "secret":       data["secret"],
            "otpauth_url":  data["otpauth_url"],
            "qr_data_url":  data["qr_data_url"],
            "instructions": (
                "1. Scan the QR code in Google Authenticator / Authy. "
                "2. Add ADMIN_TOTP_SECRET=" + data["secret"] + " to your .env. "
                "3. Restart the server. Admin login will now require the 6-digit code."
            ),
        }
    except RuntimeError as exc:
        raise HTTPException(503, f"pyotp not installed: {exc}")


@app.get("/admin/stats", include_in_schema=False, dependencies=[Depends(admin_auth)])
def admin_stats():
    """Quick summary stats for the dashboard."""
    try:
        from backend.persistence.database import _get_conn, _cursor
        with _get_conn() as conn:
            with _cursor(conn) as cur:
                cur.execute("SELECT COUNT(*) AS n FROM users")
                total = (cur.fetchone() or {}).get("n", 0)
                cur.execute("SELECT COUNT(*) AS n FROM users WHERE email_verified=TRUE")
                verified = (cur.fetchone() or {}).get("n", 0)
                cur.execute("SELECT COUNT(*) AS n FROM reading_history")
                readings = (cur.fetchone() or {}).get("n", 0)
                cur.execute("SELECT COALESCE(SUM(wallet_balance_cents),0) AS s FROM users")
                wallet = (cur.fetchone() or {}).get("s", 0)
        return {"total_users": total, "verified_users": verified,
                "total_readings": readings, "total_wallet_paise": wallet}
    except Exception as exc:
        raise HTTPException(500, f"Stats query failed: {exc}")


@app.get("/admin/users", include_in_schema=False, dependencies=[Depends(admin_auth)])
def admin_list_users(limit: int = Query(50, le=200), offset: int = Query(0)):
    """Return the most recent users for the admin dashboard table."""
    try:
        from backend.persistence.database import _get_conn, _cursor, decrypt_pii
        with _get_conn() as conn:
            with _cursor(conn) as cur:
                cur.execute(
                    """SELECT id, email, name, email_verified,
                              wallet_balance_cents, region, created_at, user_type
                       FROM users
                       ORDER BY created_at DESC
                       LIMIT %s OFFSET %s""",
                    (limit, offset),
                )
                rows = cur.fetchall()
        result = []
        for r in rows:
            d = dict(r)
            d["name"] = decrypt_pii(d.get("name") or "") or ""
            result.append(d)
        return result
    except Exception as exc:
        raise HTTPException(500, f"User list query failed: {exc}")


class AdminEmailBody(BaseModel):
    email: str


@app.post("/admin/verify-user", include_in_schema=False, dependencies=[Depends(admin_auth)])
def admin_verify_user(req: AdminEmailBody):
    """Force-verify a user's email (admin action — skips the normal token flow)."""
    try:
        from backend.persistence.database import _get_conn, _cursor
        with _get_conn() as conn:
            with _cursor(conn) as cur:
                cur.execute(
                    "UPDATE users SET email_verified=TRUE, verification_token=NULL WHERE email=%s",
                    (req.email.lower().strip(),),
                )
                if cur.rowcount == 0:
                    raise HTTPException(404, "User not found.")
            conn.commit()
        return {"success": True, "email": req.email}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(500, f"Verify failed: {exc}")


@app.delete("/admin/delete-user", include_in_schema=False, dependencies=[Depends(admin_auth)])
def admin_delete_user(req: AdminEmailBody):
    """Hard-delete a user by email (admin action)."""
    try:
        from backend.persistence.database import _get_conn, _cursor
        with _get_conn() as conn:
            with _cursor(conn) as cur:
                cur.execute("DELETE FROM users WHERE email=%s",
                            (req.email.lower().strip(),))
                if cur.rowcount == 0:
                    raise HTTPException(404, "User not found.")
            conn.commit()
        return {"success": True, "email": req.email}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(500, f"Delete failed: {exc}")


@app.post("/admin/wallet-adjust", include_in_schema=False, dependencies=[Depends(admin_auth)])
def admin_wallet_adjust(req: WalletAdjustRequest):
    """Manually credit or debit a user's wallet (admin action)."""
    try:
        ws = WalletService(_db)
        ws.adjust_balance(req.email, req.delta_cents, req.reason)
        bal = _db.get_wallet_balance(req.email)
        return {"success": True, "new_balance_cents": bal}
    except Exception as exc:
        raise HTTPException(500, f"Wallet adjust failed: {exc}")


@app.post("/admin/test-email", include_in_schema=False, dependencies=[Depends(admin_auth)])
def admin_test_email(req: AdminEmailBody):
    """Send a test email synchronously and return success/error detail."""
    import smtplib
    from backend.auth.email_service import (
        EMAIL_HOST, EMAIL_PORT, EMAIL_USER, EMAIL_PASSWORD,
        EMAIL_FROM_NAME, _SMTP_CONFIGURED,
    )
    if not _SMTP_CONFIGURED:
        return {
            "success": False,
            "error": "SMTP not configured",
        }
    try:
        from email.mime.text import MIMEText
        msg = MIMEText("This is a test email from NarayanAstroReader admin panel.", "plain")
        msg["Subject"] = "NarayanAstroReader SMTP Test"
        msg["From"]    = f"{EMAIL_FROM_NAME} <{EMAIL_USER}>"
        msg["To"]      = req.email
        with smtplib.SMTP(EMAIL_HOST, EMAIL_PORT, timeout=10) as server:
            server.ehlo(); server.starttls(); server.ehlo()
            server.login(EMAIL_USER, EMAIL_PASSWORD)
            server.sendmail(EMAIL_USER, req.email, msg.as_string())
        return {"success": True, "message": f"Test email sent to {req.email}"}
    except Exception as exc:
        return {"success": False, "error": str(exc)}

# Static file mounting
if (_REACT_DIST / "assets").exists():
    app.mount("/assets", StaticFiles(directory=str(_REACT_DIST / "assets")), name="react-assets")

if _FRONT_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(_FRONT_DIR)), name="static")


@app.get("/", include_in_schema=False)
def serve_root():
    index = _ACTIVE_FRONT / "index.html"
    if index.exists():
        return HTMLResponse(
            content=index.read_text(encoding="utf-8"),
            headers={
                "Cache-Control": "no-cache, no-store, must-revalidate",
                "Pragma":        "no-cache",
                "Expires":       "0",
            },
        )
    raise HTTPException(404, "Frontend not found. Run npm run build inside frontend-react/.")

@app.get("/kundli_chart.js", include_in_schema=False)
def serve_kundli_chart():
    p = _FRONT_DIR / "kundli_chart.js"
    if p.exists():
        return FileResponse(str(p), media_type="application/javascript")
    raise HTTPException(404, "kundli_chart.js not found")


@app.get("/vite.svg", include_in_schema=False)
def serve_vite_svg():
    for candidate in [
        _REACT_DIST / "vite.svg",
        _HERE.parent.parent / "frontend-react" / "public" / "vite.svg",
    ]:
        if candidate.exists():
            return FileResponse(str(candidate), media_type="image/svg+xml")
    raise HTTPException(404)


@app.get("/favicon.ico", include_in_schema=False)
def favicon():
    raise HTTPException(404)


@app.get("/{full_path:path}", include_in_schema=False)
def serve_frontend(full_path: str):
    """SPA catch-all."""
    index = _ACTIVE_FRONT / "index.html"
    if index.exists():
        return HTMLResponse(
            content=index.read_text(encoding="utf-8"),
            headers={
                "Cache-Control": "no-cache, no-store, must-revalidate",
                "Pragma":        "no-cache",
                "Expires":       "0",
            },
        )
    raise HTTPException(404, "Frontend not found.")
