"""
email/ses_client.py
===================
AWS SES email sender for production deployments.

Uses boto3 send_email API. Falls back to smtp_client when boto3 is not
available (e.g. in development without AWS credentials).

Set EMAIL_PROVIDER=ses in production .env to activate.
"""
from __future__ import annotations
import os, logging
from typing import Optional

log = logging.getLogger(__name__)

_REGION   = os.environ.get("AWS_SES_REGION", "ap-south-1")
_FROM     = os.environ.get("FROM_EMAIL", "noreply@example.com")
_PROVIDER = os.environ.get("EMAIL_PROVIDER", "smtp").lower()


def send_email(
    to: str,
    subject: str,
    html_body: str,
    text_body: Optional[str] = None,
) -> bool:
    """
    Send via AWS SES. Returns True on success, False on error.
    Automatically falls back to smtp_client if boto3 is missing.
    """
    if _PROVIDER != "ses":
        from .smtp_client import send_email as smtp_send
        return smtp_send(to, subject, html_body, text_body)

    try:
        import boto3
        client = boto3.client("ses", region_name=_REGION)
        body: dict = {"Html": {"Charset": "UTF-8", "Data": html_body}}
        if text_body:
            body["Text"] = {"Charset": "UTF-8", "Data": text_body}

        client.send_email(
            Source=_FROM,
            Destination={"ToAddresses": [to]},
            Message={
                "Subject": {"Charset": "UTF-8", "Data": subject},
                "Body": body,
            },
        )
        log.info("ses_email_sent", extra={"to": to, "subject": subject})
        return True
    except ImportError:
        log.warning("boto3_not_installed_falling_back_to_smtp")
        from .smtp_client import send_email as smtp_send
        return smtp_send(to, subject, html_body, text_body)
    except Exception as exc:
        log.error("ses_send_failed", extra={"to": to, "error": str(exc)})
        return False
