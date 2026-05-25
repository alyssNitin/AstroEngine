"""
Local fallback for the notification service — delegates to backend.auth.email_service.
Used when USE_MICROSERVICES=false (default monolith mode).
"""
from __future__ import annotations
import logging

logger = logging.getLogger(__name__)


class NotificationLocalFallback:
    """Wraps the local EmailService with the same interface as NotificationServiceClient."""

    def _svc(self):
        from backend.auth.email_service import EmailService
        return EmailService

    def send_verification_email(self, to: str, token: str, lang: str = "en") -> bool:
        return self._svc().send_verification(to, to, token)

    def send_password_reset(self, to: str, token: str, lang: str = "en") -> bool:
        return self._svc().send_password_reset(to, to, token)

    def send_welcome(self, to: str, lang: str = "en") -> bool:
        logger.info("[notification-local] Welcome email to %s (no-op)", to)
        return True

    def send_payment_receipt(self, to, order_id, credits, amount,
                              currency="INR", balance=0, lang="en") -> bool:
        logger.info("[notification-local] Payment receipt to %s order=%s", to, order_id)
        return True

    def send_low_balance(self, to: str, balance: int, lang: str = "en") -> bool:
        logger.info("[notification-local] Low balance warning to %s balance=%s", to, balance)
        return True

    def send_reading_ready(self, to, report_id, report_type, lang="en") -> bool:
        logger.info("[notification-local] Reading ready to %s report=%s", to, report_id)
        return True

    def health(self) -> dict:
        return {"service": "notification-service", "status": "local-fallback"}
