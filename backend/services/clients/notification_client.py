"""
backend/services/clients/notification_client.py
================================================
HTTP client for the notification microservice.

Usage::

    from backend.services.clients.notification_client import NotificationServiceClient

    client = NotificationServiceClient(base_url="http://localhost:8002")
    client.send_verification_email(to="user@example.com", token="abc123")
"""
from __future__ import annotations

from .base import BaseServiceClient


class NotificationServiceClient(BaseServiceClient):
    """
    HTTP client wrapping the notification microservice REST API.

    Each method corresponds to one email template, providing a
    typed Python interface over the generic POST /notify/email endpoint
    (Interface Segregation — callers only see what they need).
    """

    def _send_email(self, to: str, template: str, lang: str = "en", **context) -> bool:
        """Internal helper: POST to /notify/email and return success flag."""
        resp = self._post("/notify/email", {
            "to":       to,
            "template": template,
            "lang":     lang,
            "context":  context,
        })
        return bool(resp.get("sent", False))

    def send_verification_email(self, to: str, token: str, lang: str = "en") -> bool:
        """Send the email-verification link to a newly registered user."""
        return self._send_email(to, "email_verification", lang, token=token)

    def send_welcome(self, to: str, lang: str = "en") -> bool:
        """Send the welcome email after first login."""
        return self._send_email(to, "welcome", lang)

    def send_password_reset(self, to: str, token: str, lang: str = "en") -> bool:
        """Send a password-reset link."""
        return self._send_email(to, "password_reset", lang, token=token)

    def send_payment_receipt(
        self,
        to: str,
        order_id: str,
        credits: int,
        amount: str,
        currency: str = "INR",
        balance: int = 0,
        lang: str = "en",
    ) -> bool:
        """Send a payment receipt after a successful wallet top-up."""
        return self._send_email(
            to, "payment_receipt", lang,
            order_id=order_id, credits=credits,
            amount=amount, currency=currency, balance=balance,
        )

    def send_low_balance(self, to: str, balance: int, lang: str = "en") -> bool:
        """Send a low-balance warning when wallet drops below threshold."""
        return self._send_email(to, "low_balance", lang, balance=balance)

    def send_reading_ready(
        self, to: str, report_id: str, report_type: str, lang: str = "en"
    ) -> bool:
        """Notify user when their AI reading report is ready."""
        return self._send_email(
            to, "reading_ready", lang,
            report_id=report_id, report_type=report_type,
        )

    def health(self) -> dict:
        """Ping the notification service health endpoint."""
        return self._get("/health")
