"""email sub-package — SMTP and SES senders."""
from .smtp_client import send_email as smtp_send
from .ses_client  import send_email as ses_send
from .email_service import EmailService

__all__ = ["EmailService", "smtp_send", "ses_send"]
