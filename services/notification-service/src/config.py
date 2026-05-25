"""
notification-service/src/config.py
====================================
All runtime configuration for the notification microservice.

Environment variables
---------------------
PORT            TCP port              (default: 8002)
EMAIL_PROVIDER  'smtp' | 'ses'        (default: smtp)
EMAIL_HOST      SMTP server hostname
EMAIL_PORT      SMTP server port      (default: 587)
EMAIL_USER      SMTP login username
EMAIL_PASSWORD  SMTP login password
EMAIL_FROM_NAME Sender display name   (default: NarayanAstroReader)
APP_BASE_URL    Public app URL for email links
AWS_REGION      AWS region for SES    (default: ap-south-1)
FCM_SERVER_KEY  Firebase server key for push notifications
"""
from __future__ import annotations

from pydantic import Field
from shared.config import BaseServiceConfig


class NotificationConfig(BaseServiceConfig):
    """Notification-service settings (extends BaseServiceConfig)."""

    port: int = Field(default=8002, description="Notification service listen port")

    # ── Email provider selection ──────────────────────────────────────────────
    email_provider: str = Field(
        default="smtp",
        description="Email backend: 'smtp' (default) or 'ses' (AWS SES).",
    )

    # ── SMTP settings ─────────────────────────────────────────────────────────
    email_host: str     = Field(default="",    description="SMTP server hostname (EMAIL_HOST)")
    email_port: int     = Field(default=587,   description="SMTP server port (EMAIL_PORT)")
    email_user: str     = Field(default="",    description="SMTP username (EMAIL_USER)")
    email_password: str = Field(default="",    description="SMTP password / App Password (EMAIL_PASSWORD)")

    # ── Sender identity ───────────────────────────────────────────────────────
    email_from_name: str = Field(
        default="NarayanAstroReader",
        description="Display name shown in From: header",
    )
    app_base_url: str = Field(
        default="http://localhost:8000",
        description="Public app URL — used to build verification / reset links",
    )

    # ── AWS SES (alternative backend) ─────────────────────────────────────────
    aws_region: str = Field(default="ap-south-1", description="AWS region for SES")

    # ── FCM push notifications ────────────────────────────────────────────────
    fcm_server_key: str = Field(default="", description="Firebase Cloud Messaging server key")

    @property
    def smtp_configured(self) -> bool:
        """True when all SMTP credentials are present."""
        return bool(self.email_host and self.email_user and self.email_password)

    @property
    def ses_configured(self) -> bool:
        """True when SES is selected and AWS credentials are available via boto3."""
        return self.email_provider.lower() == "ses"


settings = NotificationConfig()
