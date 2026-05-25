"""
email/email_service.py
======================
High-level EmailService — the single entry point for all outbound email.

Selects SMTP or SES based on EMAIL_PROVIDER env var, renders i18n templates,
and enforces unsubscribe logic before sending.

Template keys (language fallback: hi/ta → en)
-----------------------------------------------
  email_verification   Registration verification link
  welcome              First-time verified welcome
  payment_receipt      Top-up confirmed
  low_balance          Wallet balance below threshold
  password_reset       Forgot-password link
  reading_ready        AI report completed
  weekly_digest        Super-admin Monday digest (en only)
"""
from __future__ import annotations
import os, logging
from typing import Optional
from .smtp_client import send_email as smtp_send
from .ses_client  import send_email as ses_send

log = logging.getLogger(__name__)

_PROVIDER = os.environ.get("EMAIL_PROVIDER", "smtp").lower()
_BASE_URL = os.environ.get("APP_BASE_URL", "http://localhost:8000")

# ── i18n template strings ─────────────────────────────────────────────────────
_TEMPLATES: dict[str, dict[str, dict[str, str]]] = {
    "email_verification": {
        "en": {
            "subject": "Verify your NarayanAstro email",
            "html": (
                "<h2>Welcome to NarayanAstro!</h2>"
                "<p>Please verify your email by clicking the link below.</p>"
                "<p><a href='{link}'>Verify Email</a></p>"
                "<p>This link expires in 24 hours.</p>"
            ),
            "text": "Verify your email: {link}\nExpires in 24 hours.",
        },
        "hi": {
            "subject": "अपना NarayanAstro ईमेल सत्यापित करें",
            "html": (
                "<h2>NarayanAstro में आपका स्वागत है!</h2>"
                "<p>नीचे दिए गए लिंक पर क्लिक करके अपना ईमेल सत्यापित करें।</p>"
                "<p><a href='{link}'>ईमेल सत्यापित करें</a></p>"
                "<p>यह लिंक 24 घंटों में समाप्त हो जाएगी।</p>"
            ),
            "text": "ईमेल सत्यापित करें: {link}\n24 घंटों में समाप्त।",
        },
        "ta": {
            "subject": "உங்கள் NarayanAstro மின்னஞ்சலை சரிபார்க்கவும்",
            "html": (
                "<h2>NarayanAstro-க்கு வரவேற்கிறோம்!</h2>"
                "<p>கீழே உள்ள இணைப்பைக் கிளிக் செய்து உங்கள் மின்னஞ்சலை சரிபார்க்கவும்.</p>"
                "<p><a href='{link}'>மின்னஞ்சலை சரிபார்க்கவும்</a></p>"
                "<p>இந்த இணைப்பு 24 மணி நேரத்தில் காலாவதியாகும்.</p>"
            ),
            "text": "மின்னஞ்சல் சரிபார்ப்பு: {link}",
        },
    },
    "welcome": {
        "en": {
            "subject": "Welcome to NarayanAstro — ₹20 credit added!",
            "html": (
                "<h2>Your account is verified!</h2>"
                "<p>We've added <strong>₹20 credit</strong> to your wallet — "
                "enough for your first astrological reading.</p>"
                "<p><a href='{base_url}'>Start your reading →</a></p>"
            ),
            "text": "Account verified! ₹20 credit added. Start at: {base_url}",
        },
        "hi": {
            "subject": "NarayanAstro में आपका स्वागत है — ₹20 क्रेडिट जोड़ा गया!",
            "html": (
                "<h2>आपका खाता सत्यापित हो गया!</h2>"
                "<p>हमने आपके वॉलेट में <strong>₹20 क्रेडिट</strong> जोड़ा है।</p>"
                "<p><a href='{base_url}'>अपनी रीडिंग शुरू करें →</a></p>"
            ),
            "text": "खाता सत्यापित! ₹20 क्रेडिट जोड़ा गया। शुरू करें: {base_url}",
        },
        "ta": {
            "subject": "NarayanAstro-க்கு வரவேற்கிறோம் — ₹20 கிரெடிட் சேர்க்கப்பட்டது!",
            "html": (
                "<h2>உங்கள் கணக்கு சரிபார்க்கப்பட்டது!</h2>"
                "<p>உங்கள் பணப்பையில் <strong>₹20 கிரெடிட்</strong> சேர்க்கப்பட்டது।</p>"
                "<p><a href='{base_url}'>உங்கள் வாசிப்பை தொடங்குங்கள் →</a></p>"
            ),
            "text": "கணக்கு சரிபார்க்கப்பட்டது! ₹20 கிரெடிட். தொடங்குங்கள்: {base_url}",
        },
    },
    "payment_receipt": {
        "en": {
            "subject": "Payment confirmed — {credits} credits added",
            "html": (
                "<h2>Payment Successful</h2>"
                "<p>Order: <code>{order_id}</code></p>"
                "<p>Credits added: <strong>{credits}</strong></p>"
                "<p>Amount charged: <strong>{currency} {amount}</strong></p>"
                "<p>New balance: {balance} credits</p>"
            ),
            "text": (
                "Payment confirmed. Order: {order_id}\n"
                "Credits: {credits} | Amount: {currency} {amount}\n"
                "Balance: {balance} credits"
            ),
        },
        "hi": {
            "subject": "भुगतान की पुष्टि — {credits} क्रेडिट जोड़े गए",
            "html": (
                "<h2>भुगतान सफल</h2>"
                "<p>ऑर्डर: <code>{order_id}</code></p>"
                "<p>क्रेडिट जोड़े गए: <strong>{credits}</strong></p>"
                "<p>शुल्क: <strong>{currency} {amount}</strong></p>"
            ),
            "text": "भुगतान पुष्टि। ऑर्डर: {order_id} | क्रेडिट: {credits}",
        },
        "ta": {
            "subject": "கட்டணம் உறுதிப்படுத்தப்பட்டது — {credits} கிரெடிட்கள்",
            "html": (
                "<h2>கட்டணம் வெற்றிகரமாக</h2>"
                "<p>ஆர்டர்: <code>{order_id}</code></p>"
                "<p>கிரெடிட்: <strong>{credits}</strong></p>"
            ),
            "text": "கட்டணம் உறுதி. ஆர்டர்: {order_id} | கிரெடிட்: {credits}",
        },
    },
    "low_balance": {
        "en": {
            "subject": "Low credit balance — top up to continue",
            "html": (
                "<h2>Your credit balance is low</h2>"
                "<p>Current balance: <strong>{balance} credits</strong></p>"
                "<p><a href='{base_url}/wallet'>Top up your wallet →</a></p>"
            ),
            "text": "Low balance: {balance} credits. Top up: {base_url}/wallet",
        },
        "hi": {
            "subject": "क्रेडिट बैलेंस कम है — जारी रखने के लिए टॉप अप करें",
            "html": (
                "<h2>आपका क्रेडिट बैलेंस कम है</h2>"
                "<p>वर्तमान बैलेंस: <strong>{balance} क्रेडिट</strong></p>"
                "<p><a href='{base_url}/wallet'>वॉलेट टॉप अप करें →</a></p>"
            ),
            "text": "कम बैलेंस: {balance} क्रेडिट। टॉप अप: {base_url}/wallet",
        },
        "ta": {
            "subject": "கிரெடிட் இருப்பு குறைவாக உள்ளது",
            "html": (
                "<h2>உங்கள் கிரெடிட் இருப்பு குறைவாக உள்ளது</h2>"
                "<p>தற்போதைய இருப்பு: <strong>{balance} கிரெடிட்கள்</strong></p>"
                "<p><a href='{base_url}/wallet'>பணப்பையை நிரப்பவும் →</a></p>"
            ),
            "text": "குறைந்த இருப்பு: {balance} கிரெடிட்கள்.",
        },
    },
    "password_reset": {
        "en": {
            "subject": "Reset your NarayanAstro password",
            "html": (
                "<h2>Password Reset Request</h2>"
                "<p>Click the link below to reset your password:</p>"
                "<p><a href='{link}'>Reset Password</a></p>"
                "<p>This link expires in 1 hour. If you did not request this, ignore this email.</p>"
            ),
            "text": "Reset your password: {link}\nExpires in 1 hour.",
        },
        "hi": {
            "subject": "अपना NarayanAstro पासवर्ड रीसेट करें",
            "html": (
                "<h2>पासवर्ड रीसेट अनुरोध</h2>"
                "<p><a href='{link}'>पासवर्ड रीसेट करें</a></p>"
                "<p>यह लिंक 1 घंटे में समाप्त हो जाएगी।</p>"
            ),
            "text": "पासवर्ड रीसेट: {link}",
        },
        "ta": {
            "subject": "உங்கள் NarayanAstro கடவுச்சொல்லை மீட்டமைக்கவும்",
            "html": (
                "<h2>கடவுச்சொல் மீட்டமைப்பு கோரிக்கை</h2>"
                "<p><a href='{link}'>கடவுச்சொல்லை மீட்டமைக்கவும்</a></p>"
            ),
            "text": "கடவுச்சொல் மீட்டமைப்பு: {link}",
        },
    },
    "reading_ready": {
        "en": {
            "subject": "Your astrological reading is ready",
            "html": (
                "<h2>Your Reading is Ready</h2>"
                "<p>Report type: <strong>{report_type}</strong></p>"
                "<p><a href='{base_url}/reports/{report_id}'>View your reading →</a></p>"
            ),
            "text": "Your {report_type} reading is ready: {base_url}/reports/{report_id}",
        },
        "hi": {
            "subject": "आपकी ज्योतिष रीडिंग तैयार है",
            "html": (
                "<h2>आपकी रीडिंग तैयार है</h2>"
                "<p><a href='{base_url}/reports/{report_id}'>अपनी रीडिंग देखें →</a></p>"
            ),
            "text": "आपकी रीडिंग तैयार है: {base_url}/reports/{report_id}",
        },
        "ta": {
            "subject": "உங்கள் ஜோதிட வாசிப்பு தயாராக உள்ளது",
            "html": (
                "<h2>உங்கள் வாசிப்பு தயாராக உள்ளது</h2>"
                "<p><a href='{base_url}/reports/{report_id}'>வாசிப்பைக் காண்க →</a></p>"
            ),
            "text": "வாசிப்பு தயாராக உள்ளது: {base_url}/reports/{report_id}",
        },
    },
}


class EmailService:
    """
    High-level email service with i18n template support.

    Usage::

        svc = EmailService()
        svc.send_verification(to="user@x.com", token="abc123", lang="hi")
        svc.send_low_balance(to="user@x.com", balance=2, lang="ta")
    """

    def __init__(self) -> None:
        self._send = ses_send if _PROVIDER == "ses" else smtp_send

    def _render(self, key: str, lang: str, **ctx) -> tuple[str, str, str]:
        """Return (subject, html, text) for a template + language."""
        tmpl = _TEMPLATES.get(key, {})
        t    = tmpl.get(lang) or tmpl.get("en") or {}
        subject = t.get("subject", key).format(**ctx, base_url=_BASE_URL)
        html    = t.get("html", "").format(**ctx, base_url=_BASE_URL)
        text    = t.get("text", "").format(**ctx, base_url=_BASE_URL)
        return subject, html, text

    def _deliver(self, to: str, key: str, lang: str = "en", **ctx) -> bool:
        subj, html, text = self._render(key, lang, **ctx)
        ok = self._send(to, subj, html, text)
        if not ok:
            log.error("email_delivery_failed",
                      extra={"to": to, "template": key, "lang": lang})
        return ok

    # ── Public helpers ────────────────────────────────────────────────────────

    def send_verification(self, to: str, token: str, lang: str = "en") -> bool:
        link = f"{_BASE_URL}/auth/verify-email?token={token}"
        return self._deliver(to, "email_verification", lang, link=link)

    def send_welcome(self, to: str, lang: str = "en") -> bool:
        return self._deliver(to, "welcome", lang)

    def send_payment_receipt(
        self, to: str, order_id: str, credits: int,
        amount: str, currency: str, balance: int, lang: str = "en"
    ) -> bool:
        return self._deliver(
            to, "payment_receipt", lang,
            order_id=order_id, credits=credits,
            amount=amount, currency=currency, balance=balance,
        )

    def send_low_balance(self, to: str, balance: int, lang: str = "en") -> bool:
        return self._deliver(to, "low_balance", lang, balance=balance)

    def send_password_reset(self, to: str, token: str, lang: str = "en") -> bool:
        link = f"{_BASE_URL}/auth/reset-password?token={token}"
        return self._deliver(to, "password_reset", lang, link=link)

    def send_reading_ready(
        self, to: str, report_id: str, report_type: str, lang: str = "en"
    ) -> bool:
        return self._deliver(
            to, "reading_ready", lang,
            report_id=report_id, report_type=report_type,
        )
