"""
notification-service/src/api/main.py
=====================================
FastAPI application for the notification microservice.

This service is an INTERNAL service — not exposed to end users.
It is called by other microservices (auth-service, credit-wallet-service)
via the X-Service-Secret header.

Responsibilities (Single Responsibility)
-----------------------------------------
- HTTP request/response mapping only
- Delegates email rendering + delivery to EmailService
- Delegates push delivery to FCMClient

SOLID
-----
- O/C : new notification templates require zero changes here — add to
        EmailService.TEMPLATES and register a handler in the dispatch map
- D   : EmailService and FCMClient are injected at startup (lifespan),
        not instantiated per-request
"""
from __future__ import annotations

import secrets
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Header, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr, Field

from ..email.email_service import EmailService
from ..push.fcm_client import FCMClient
from ..config import settings
from shared.logging import configure_logging, get_logger
from shared.health import HealthResponse

log = get_logger(__name__)

# ── Shared service instances (created once, reused across requests) ───────────
_email_svc: EmailService | None = None
_fcm_client: FCMClient | None   = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialise shared service instances on startup."""
    global _email_svc, _fcm_client
    configure_logging(log_level=settings.log_level, json=settings.is_production)
    # EmailService and FCMClient read their config from env vars directly;
    # they are stateless singletons that take no constructor arguments.
    _email_svc  = EmailService()
    _fcm_client = FCMClient()
    log.info(
        "notification_service_ready",
        smtp_configured=settings.smtp_configured,
        fcm_configured=bool(settings.fcm_server_key),
    )
    yield
    log.info("notification_service_shutdown")


app = FastAPI(
    title="NarayanAstro Notification Service",
    description=(
        "Internal microservice for email and push notifications.\n\n"
        "Not exposed via the public API Gateway — called only by other services."
    ),
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "X-Service-Secret"],
)


# ── Auth dependency ───────────────────────────────────────────────────────────

def _verify_service_secret(x_service_secret: str | None = Header(default=None)) -> None:
    if not settings.service_secret:
        return
    if not x_service_secret or not secrets.compare_digest(
        x_service_secret, settings.service_secret
    ):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid X-Service-Secret.")


# ── Schemas ───────────────────────────────────────────────────────────────────

class EmailRequest(BaseModel):
    """
    Request body for POST /notify/email.

    `template` selects the email template; `context` supplies
    template-specific variables.  Supported templates:
      email_verification, welcome, payment_receipt,
      low_balance, password_reset, reading_ready
    """
    to:       str  = Field(..., description="Recipient email address")
    template: str  = Field(..., description="Template key")
    lang:     str  = Field(default="en", description="Language: en | hi | ta")
    context:  dict = Field(default_factory=dict, description="Template variables")

    model_config = {"json_schema_extra": {"example": {
        "to": "user@example.com",
        "template": "email_verification",
        "lang": "en",
        "context": {"token": "abc123", "name": "Ravi"},
    }}}


class PushRequest(BaseModel):
    """Request body for POST /notify/push."""
    device_token: str  = Field(..., description="FCM device registration token")
    title:        str  = Field(..., description="Notification title")
    body:         str  = Field(..., description="Notification body text")
    data:         dict = Field(default_factory=dict, description="Custom key-value payload")


# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/health", response_model=HealthResponse, tags=["system"])
def health() -> HealthResponse:
    """Liveness probe."""
    return HealthResponse(
        service="notification-service",
        status="healthy",
        version=app.version,
        meta={
            "smtp_configured": settings.smtp_configured,
            "fcm_configured":  bool(settings.fcm_server_key),
            "email_provider":  settings.email_provider,
        },
    )


@app.post("/notify/email", tags=["email"], summary="Send a templated email")
def send_email(req: EmailRequest) -> dict:
    """
    Send a transactional email using the specified template.

    New templates can be added to EmailService.TEMPLATES without
    changing this endpoint (Open/Closed Principle).
    """
    if _email_svc is None:
        raise HTTPException(503, "Email service not initialised.")

    # Dispatch table — each template maps to a bound EmailService method.
    # Adding a new template = adding one entry here + implementing in EmailService.
    dispatch: dict = {
        "email_verification": lambda: _email_svc.send_verification(
            req.to, req.context.get("token", ""), req.lang
        ),
        "welcome": lambda: _email_svc.send_welcome(req.to, req.lang),
        "payment_receipt": lambda: _email_svc.send_payment_receipt(
            req.to,
            order_id=req.context.get("order_id", ""),
            credits=req.context.get("credits", 0),
            amount=req.context.get("amount", "0"),
            currency=req.context.get("currency", "INR"),
            balance=req.context.get("balance", 0),
            lang=req.lang,
        ),
        "low_balance":    lambda: _email_svc.send_low_balance(
            req.to, req.context.get("balance", 0), req.lang
        ),
        "password_reset": lambda: _email_svc.send_password_reset(
            req.to, req.context.get("token", ""), req.lang
        ),
        "reading_ready":  lambda: _email_svc.send_reading_ready(
            req.to,
            report_id=req.context.get("report_id", ""),
            report_type=req.context.get("report_type", ""),
            lang=req.lang,
        ),
    }

    handler = dispatch.get(req.template)
    if handler is None:
        raise HTTPException(
            status_code=400,
            detail={
                "error": f"Unknown template: '{req.template}'",
                "available": list(dispatch.keys()),
            },
        )

    success = handler()
    log.info("email_sent", template=req.template, to=req.to, success=success)
    return {"sent": success, "template": req.template, "to": req.to}


@app.post("/notify/push", tags=["push"], summary="Send FCM push notification")
def send_push(req: PushRequest) -> dict:
    """
    Send a Firebase Cloud Messaging (FCM) push notification.

    Returns `sent: false` with a detail message if FCM is not configured
    (no FCM_SERVER_KEY env var) rather than raising an error — push is
    optional and should not break the caller's flow.
    """
    if _fcm_client is None:
        raise HTTPException(503, "FCM client not initialised.")
    success = _fcm_client.send(
        device_token = req.device_token,
        title        = req.title,
        body         = req.body,
        data         = req.data,
    )
    if not success:
        return {"sent": False, "detail": "FCM not configured — push skipped (console logged)."}
    log.info("push_sent", token_prefix=req.device_token[:8], title=req.title)
    return {"sent": True}


@app.get("/health", response_model=HealthResponse, tags=["ops"])
def health() -> HealthResponse:
    """Liveness + readiness probe.

    Returns the service status and whether SMTP / FCM are configured.
    Kubernetes / Docker health-checks hit this endpoint.
    """
    return HealthResponse(
        service  = "notification-service",
        status   = "ok",
        version  = "1.0.0",
        dependencies = {
            "smtp": "configured" if (_email_svc is not None) else "missing",
            "fcm":  "configured" if (_fcm_client is not None) else "missing",
        },
    )
