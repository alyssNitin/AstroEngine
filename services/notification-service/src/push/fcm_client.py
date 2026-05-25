"""
push/fcm_client.py
==================
Firebase Cloud Messaging (FCM) push notification client.

Status: Phase 2 stub — interface is defined; real FCM calls are
        activated when FCM_SERVER_KEY env var is set.

Usage::

    from services.notification-service.src.push.fcm_client import FCMClient
    fcm = FCMClient()
    fcm.send(device_token="...", title="Low Credits", body="Top up now")
"""
from __future__ import annotations
import os, logging

log = logging.getLogger(__name__)

_FCM_KEY = os.environ.get("FCM_SERVER_KEY", "")
_FCM_URL = "https://fcm.googleapis.com/fcm/send"


class FCMClient:
    """
    Sends push notifications via Firebase Cloud Messaging.
    Falls back to a console log when FCM_SERVER_KEY is not configured.
    """

    def send(
        self,
        device_token: str,
        title: str,
        body: str,
        data: dict | None = None,
    ) -> bool:
        """
        Send a push notification to a single device.

        Args:
            device_token: FCM registration token for the target device.
            title:        Notification title.
            body:         Notification body text.
            data:         Optional key-value data payload.

        Returns:
            True on success or stub mode; False on FCM error.
        """
        if not _FCM_KEY:
            print(f"[FCM STUB] To={device_token!r} Title={title!r} Body={body!r}")
            return True

        try:
            import httpx
            payload = {
                "to": device_token,
                "notification": {"title": title, "body": body},
                "data": data or {},
            }
            resp = httpx.post(
                _FCM_URL,
                json=payload,
                headers={
                    "Authorization": f"key={_FCM_KEY}",
                    "Content-Type": "application/json",
                },
                timeout=10,
            )
            resp.raise_for_status()
            log.info("fcm_sent", extra={"token": device_token[:8] + "...", "title": title})
            return True
        except Exception as exc:
            log.error("fcm_failed", extra={"error": str(exc), "title": title})
            return False

    def send_bulk(self, tokens: list[str], title: str, body: str,
                  data: dict | None = None) -> dict[str, bool]:
        """Send to multiple devices; returns {token: success} dict."""
        return {t: self.send(t, title, body, data) for t in tokens}
