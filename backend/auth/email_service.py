"""
backend/auth/email_service.py
==============================
SMTP email service for verification emails.
Falls back to console logging when SMTP credentials are not configured.
"""
from __future__ import annotations
import logging
from backend.core.logging import get_logger
import os
import smtplib
import textwrap
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email import encoders

logger = get_logger(__name__)

EMAIL_HOST      = os.environ.get("EMAIL_HOST", "")
EMAIL_PORT      = int(os.environ.get("EMAIL_PORT", "587"))
EMAIL_USER      = os.environ.get("EMAIL_USER", "")
EMAIL_PASSWORD  = os.environ.get("EMAIL_PASSWORD", "")
EMAIL_FROM_NAME = os.environ.get("EMAIL_FROM_NAME", "NarayanAstroReader")
APP_BASE_URL    = os.environ.get("APP_BASE_URL", "http://localhost:8000")

_SMTP_CONFIGURED = bool(EMAIL_HOST and EMAIL_USER and EMAIL_PASSWORD)


class EmailService:
    """Send transactional emails; mock-mode logs to stdout when SMTP absent."""

    @classmethod
    def send_verification(cls, to_email: str, name: str, token: str) -> bool:
        """Send verification email. Returns True on success or mock mode."""
        verify_url = f"{APP_BASE_URL}/auth/verify-email?token={token}"
        subject    = "Verify your NarayanAstroReader account"
        html_body  = cls._verification_html(name, verify_url)
        text_body  = cls._verification_text(name, verify_url)
        return cls._send(to_email, subject, html_body, text_body)

    @classmethod
    def send_resend_verification(cls, to_email: str, name: str, token: str) -> bool:
        """Re-send a new verification link."""
        verify_url = f"{APP_BASE_URL}/auth/verify-email?token={token}"
        subject    = "Your new verification link — NarayanAstroReader"
        html_body  = cls._verification_html(name, verify_url, resend=True)
        text_body  = cls._verification_text(name, verify_url, resend=True)
        return cls._send(to_email, subject, html_body, text_body)

    @classmethod
    def send_report(
        cls,
        to_email: str,
        name: str,
        pdf_bytes: bytes,
        content_type: str = "application/pdf",
    ) -> bool:
        """Email the reading report as an attachment."""
        is_pdf = "pdf" in content_type
        filename = "NarayanAstroReader_Report.pdf" if is_pdf else "NarayanAstroReader_Report.txt"
        subject  = "Your Vedic Reading Report — NarayanAstroReader"
        text_body = (
            f"Hello {name},\n\n"
            "Your personalised Vedic reading report is attached to this email.\n"
            "It contains your deep reading and your Q&A session with the AI Jyotish.\n\n"
            "Warm regards,\nNarayanAstroReader"
        )
        html_body = (
            "<html><body style='font-family:Arial,sans-serif;color:#2c2416;max-width:520px;margin:auto'>"
            "<h2 style='color:#5b3dc8'>NarayanAstroReader</h2>"
            f"<p>Hello {name},</p>"
            "<p>Your personalised Vedic reading report is attached to this email.</p>"
            "<p>It contains your <strong>deep reading</strong> and your "
            "<strong>Q&amp;A session</strong> with the AI Jyotish.</p>"
            "<p style='color:#888;font-size:12px'>This report is for personal use only.</p>"
            "</body></html>"
        )
        if not _SMTP_CONFIGURED:
            print("\n" + "=" * 60)
            print(f"[EMAIL MOCK] To: {to_email}")
            print(f"[EMAIL MOCK] Subject: {subject}")
            print(f"[EMAIL MOCK] Attachment: {filename} ({len(pdf_bytes)} bytes)")
            print("=" * 60 + "\n")
            return True
        try:
            msg = MIMEMultipart("mixed")
            msg["Subject"] = subject
            msg["From"]    = f"{EMAIL_FROM_NAME} <{EMAIL_USER}>"
            msg["To"]      = to_email
            alt = MIMEMultipart("alternative")
            alt.attach(MIMEText(text_body, "plain"))
            alt.attach(MIMEText(html_body, "html"))
            msg.attach(alt)
            part = MIMEBase(*content_type.split("/", 1))
            part.set_payload(pdf_bytes)
            encoders.encode_base64(part)
            part.add_header("Content-Disposition", f'attachment; filename="{filename}"')
            msg.attach(part)
            with smtplib.SMTP(EMAIL_HOST, EMAIL_PORT, timeout=10) as server:
                server.ehlo(); server.starttls(); server.ehlo()
                server.login(EMAIL_USER, EMAIL_PASSWORD)
                server.sendmail(EMAIL_USER, to_email, msg.as_string())
            logger.info("Report emailed to %s (%d bytes)", to_email, len(pdf_bytes))
            return True
        except Exception as exc:
            logger.error("Failed to send report to %s: %s", to_email, exc)
            return False

    @classmethod
    def _send(cls, to_email: str, subject: str, html_body: str, text_body: str) -> bool:
        # Always print to console — acts as a safety net if email fails or goes to spam
        print("\n" + "=" * 60)
        if _SMTP_CONFIGURED:
            print(f"[EMAIL] Sending to: {to_email} | Subject: {subject}")
        else:
            print(f"[EMAIL MOCK] To: {to_email} | Subject: {subject}")
        print(text_body.strip())
        print("=" * 60 + "\n")

        if not _SMTP_CONFIGURED:
            return True
        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"]    = f"{EMAIL_FROM_NAME} <{EMAIL_USER}>"
            msg["To"]      = to_email
            msg.attach(MIMEText(text_body, "plain"))
            msg.attach(MIMEText(html_body, "html"))
            with smtplib.SMTP(EMAIL_HOST, EMAIL_PORT, timeout=10) as server:
                server.ehlo(); server.starttls(); server.ehlo()
                server.login(EMAIL_USER, EMAIL_PASSWORD)
                server.sendmail(EMAIL_USER, to_email, msg.as_string())
            logger.info("Email sent to %s", to_email)
            return True
        except Exception as exc:
            logger.error("Failed to send email to %s: %s", to_email, exc)
            print(f"[EMAIL FAILED — SMTP ERROR] {exc}")
            print(f"[MANUAL ACTION REQUIRED] Copy the link above and open it in your browser.")
            return False

    @staticmethod
    def _verification_html(name: str, url: str, resend: bool = False) -> str:
        action_msg = (
            "You requested a new verification link."
            if resend else "Thank you for registering."
        )
        return (
            "<html><body style='font-family:Arial,sans-serif;color:#2c2416;max-width:520px;margin:auto'>"
            "<h2 style='color:#5b3dc8'>NarayanAstroReader</h2>"
            f"<p>Hello {name},</p>"
            f"<p>{action_msg} Please verify your email by clicking below.</p>"
            "<p style='margin:28px 0'>"
            f"<a href='{url}' style='background:#5b3dc8;color:#fff;padding:12px 28px;"
            "border-radius:6px;text-decoration:none;font-weight:bold'>Verify My Email</a>"
            "</p>"
            "<p style='color:#888;font-size:12px'>This link expires in 24 hours.</p>"
            f"<p style='color:#888;font-size:11px'>Or copy this link: {url}</p>"
            "</body></html>"
        )

    @staticmethod
    def _verification_text(name: str, url: str, resend: bool = False) -> str:
        action_msg = (
            "You requested a new verification link."
            if resend else "Thank you for registering."
        )
        lines = [
            f"Hello {name},",
            "",
            action_msg,
            "",
            "Verify your email by visiting:",
            url,
            "",
            "This link expires in 24 hours.",
        ]
        return "\n".join(lines)

    @staticmethod
    def send_password_reset(to_email: str, name: str, token: str) -> bool:
        """
        Send a password-reset email.

        Args:
            to_email: Recipient email address.
            name: User's display name for personalisation.
            token: The raw reset token (not URL-encoded).

        Returns:
            True if sent (or console-logged); False on hard failure.
        """
        base_url = os.environ.get("VERIFICATION_BASE_URL", "http://localhost:8000")
        reset_url = f"{base_url}/reset-password?token={token}"
        greeting  = f"Hi {name or 'there'},"
        subject   = "Reset your NarayanAstroReader password"
        body = (
            f"{greeting}\n\n"
            "We received a request to reset your password.\n\n"
            f"Click the link below to set a new password (valid for 1 hour):\n\n"
            f"{reset_url}\n\n"
            "If you did not request this, you can safely ignore this email.\n\n"
            "— The NarayanAstroReader Team"
        )
        return EmailService._send(to_email, subject, body, body)
