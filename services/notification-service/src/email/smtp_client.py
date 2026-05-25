"""
email/smtp_client.py
====================
Thin SMTP connection wrapper using stdlib smtplib.

Falls back to console output when EMAIL_HOST is not configured (dev mode).
Supports Gmail App Passwords and standard TLS-on-587 configurations.

Environment variables
---------------------
EMAIL_HOST      SMTP server hostname
EMAIL_PORT      SMTP server port (default: 587)
EMAIL_USER      SMTP login username
EMAIL_PASSWORD  SMTP login password / App Password
FROM_EMAIL      Sender address (defaults to EMAIL_USER)
"""
from __future__ import annotations
import os, smtplib, logging
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional

log = logging.getLogger(__name__)

_HOST     = os.environ.get("EMAIL_HOST", "")
_PORT     = int(os.environ.get("EMAIL_PORT", "587"))
_USER     = os.environ.get("EMAIL_USER", "")
_PASSWORD = os.environ.get("EMAIL_PASSWORD", "")
_FROM     = os.environ.get("FROM_EMAIL", _USER or "noreply@example.com")


def send_email(
    to: str,
    subject: str,
    html_body: str,
    text_body: Optional[str] = None,
) -> bool:
    """
    Send an HTML email. Returns True on success, False on failure.
    Prints to stdout when SMTP is not configured (dev/CI mode).
    """
    if not _HOST:
        # Console fallback - dev / CI mode
        print("\n[EMAIL CONSOLE FALLBACK]")
        print(f"  To      : {to}")
        print(f"  Subject : {subject}")
        print(f"  Body    : {text_body or html_body[:200]}")
        return True

    msg = MIMEMultipart("alternative")
    msg["From"]    = _FROM
    msg["To"]      = to
    msg["Subject"] = subject
    if text_body:
        msg.attach(MIMEText(text_body, "plain", "utf-8"))
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    try:
        with smtplib.SMTP(_HOST, _PORT, timeout=10) as server:
            server.ehlo()
            server.starttls()
            server.login(_USER, _PASSWORD)
            server.sendmail(_FROM, [to], msg.as_string())
        log.info("email_sent", extra={"to": to, "subject": subject})
        return True
    except Exception as exc:
        log.error("email_send_failed", extra={"to": to, "error": str(exc)})
        return False
