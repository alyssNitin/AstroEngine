"""
backend/services/clients/base.py
==================================
Abstract base class for all HTTP service clients.

Design (SOLID)
--------------
- Single Responsibility : HTTP transport only; no business logic.
- Open / Closed         : subclass to add service-specific methods;
                          never modify this base.
- Dependency Inversion  : callers depend on the abstract interface,
                          not the concrete httpx implementation.

Every concrete client inherits _post() and _get() which handle:
  - Authorization header injection (X-Service-Secret)
  - Timeout enforcement
  - Structured error logging
  - HTTPError → readable exception conversion
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

try:
    import httpx
    _HTTPX_AVAILABLE = True
except ImportError:
    _HTTPX_AVAILABLE = False


class ServiceClientError(RuntimeError):
    """Raised when an HTTP service call fails."""

    def __init__(self, service: str, status_code: int, detail: str) -> None:
        self.service     = service
        self.status_code = status_code
        self.detail      = detail
        super().__init__(f"[{service}] HTTP {status_code}: {detail}")


class BaseServiceClient:
    """
    Base class providing authenticated HTTP helpers for microservice calls.

    Attributes
    ----------
    base_url       : Root URL of the target service (e.g. http://localhost:8001)
    service_secret : Injected into X-Service-Secret header on every request
    timeout        : Request timeout in seconds (default 30)
    """

    def __init__(
        self,
        base_url: str,
        service_secret: str = "",
        timeout: float = 30.0,
    ) -> None:
        if not _HTTPX_AVAILABLE:
            raise RuntimeError(
                "httpx is required for microservice HTTP clients. "
                "Run: pip install httpx"
            )
        self._base_url = base_url.rstrip("/")
        self._headers  = {"X-Service-Secret": service_secret} if service_secret else {}
        self._timeout  = timeout

    # ── Protected helpers (used by subclasses) ────────────────────────────────

    def _post(self, path: str, payload: dict) -> dict:
        """
        POST JSON payload to the service and return the parsed response.

        Raises
        ------
        ServiceClientError on any non-2xx response.
        """
        url = f"{self._base_url}{path}"
        try:
            resp = httpx.post(
                url, json=payload, headers=self._headers, timeout=self._timeout
            )
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPStatusError as exc:
            detail = _extract_detail(exc.response)
            logger.error("service_post_error", extra={"url": url, "status": exc.response.status_code, "detail": detail})
            raise ServiceClientError(self._service_name, exc.response.status_code, detail) from exc
        except httpx.RequestError as exc:
            logger.error("service_post_network_error", extra={"url": url, "error": str(exc)})
            raise ServiceClientError(self._service_name, 503, str(exc)) from exc

    def _get(self, path: str, params: dict | None = None) -> dict:
        """
        GET a resource from the service and return the parsed response.

        Raises
        ------
        ServiceClientError on any non-2xx response.
        """
        url = f"{self._base_url}{path}"
        try:
            resp = httpx.get(
                url, params=params, headers=self._headers, timeout=self._timeout
            )
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPStatusError as exc:
            detail = _extract_detail(exc.response)
            raise ServiceClientError(self._service_name, exc.response.status_code, detail) from exc
        except httpx.RequestError as exc:
            raise ServiceClientError(self._service_name, 503, str(exc)) from exc

    @property
    def _service_name(self) -> str:
        """Derived service name for error messages."""
        return self.__class__.__name__


def _extract_detail(response: Any) -> str:
    """Best-effort extraction of a human-readable error from an HTTP response."""
    try:
        body = response.json()
        return body.get("detail") or str(body)
    except Exception:
        return response.text[:200]
