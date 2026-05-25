"""
backend/persistence/session_store.py
======================================
Redis-backed session store for NarayanAstroReader.

Stores per-session astrological context (kundli, predictions, chat history)
in Redis with a configurable TTL. Falls back to an in-process dict when
Redis is unavailable (development / no-Redis environments).

Usage::

    store = SessionStore()
    store.set(session_id, {"email": "a@b.com", "kundli": {...}})
    data = store.get(session_id)
    store.delete(session_id)

Configuration (environment variables):
    REDIS_URL   — Redis connection URL (default: redis://localhost:6379/0)
    SESSION_TTL — Session lifetime in seconds (default: 86400 = 24 h)
"""
from __future__ import annotations

import json
import logging
from backend.core.logging import get_logger
import os
from typing import Any

logger = get_logger(__name__)

REDIS_URL   : str = os.environ.get("REDIS_URL",   "redis://localhost:6379/0")
SESSION_TTL : int = int(os.environ.get("SESSION_TTL", str(24 * 3600)))  # 24 h


class SessionStore:
    """
    Unified session store that prefers Redis and falls back to an in-memory dict.

    Thread-safe for the in-memory fallback (GIL-protected dict operations).
    Redis operations use connection-pool-backed redis.Redis client.
    """

    def __init__(self) -> None:
        self._redis  = None
        self._memory : dict[str, dict] = {}   # fallback
        self._connect()

    # ── Connection ────────────────────────────────────────────────────────────

    def _connect(self) -> None:
        try:
            import redis as _redis_lib
            client = _redis_lib.from_url(
                REDIS_URL,
                decode_responses=True,
                socket_connect_timeout=2,
                socket_timeout=2,
            )
            client.ping()
            self._redis = client
            logger.info("[SessionStore] Connected to Redis at %s", REDIS_URL)
        except Exception as exc:
            logger.warning(
                "[SessionStore] Redis unavailable (%s). "
                "Using in-memory fallback — NOT suitable for multi-instance deployment.",
                exc,
            )
            self._redis = None

    @property
    def using_redis(self) -> bool:
        return self._redis is not None

    # ── Public API ────────────────────────────────────────────────────────────

    def get(self, session_id: str) -> dict[str, Any] | None:
        """Return session data or None if not found / expired."""
        if self._redis:
            try:
                raw = self._redis.get(f"sess:{session_id}")
                return json.loads(raw) if raw else None
            except Exception as exc:
                logger.warning("[SessionStore] Redis GET failed: %s", exc)
                return self._memory.get(session_id)
        return self._memory.get(session_id)

    def set(self, session_id: str, data: dict[str, Any]) -> None:
        """Store session data with TTL."""
        if self._redis:
            try:
                self._redis.setex(
                    f"sess:{session_id}",
                    SESSION_TTL,
                    json.dumps(data, default=str),
                )
                return
            except Exception as exc:
                logger.warning("[SessionStore] Redis SET failed: %s", exc)
        self._memory[session_id] = data

    def update(self, session_id: str, partial: dict[str, Any]) -> None:
        """Merge partial dict into existing session, refreshing TTL."""
        existing = self.get(session_id) or {}
        existing.update(partial)
        self.set(session_id, existing)

    def delete(self, session_id: str) -> None:
        """Remove a session."""
        if self._redis:
            try:
                self._redis.delete(f"sess:{session_id}")
            except Exception as exc:
                logger.warning("[SessionStore] Redis DELETE failed: %s", exc)
        self._memory.pop(session_id, None)

    def exists(self, session_id: str) -> bool:
        """Return True if the session exists."""
        if self._redis:
            try:
                return bool(self._redis.exists(f"sess:{session_id}"))
            except Exception:
                pass
        return session_id in self._memory

    # ── Guest chat counter (separate namespace) ───────────────────────────────

    def get_guest_count(self, session_id: str) -> int:
        if self._redis:
            try:
                v = self._redis.get(f"guest_chat:{session_id}")
                return int(v) if v else 0
            except Exception:
                pass
        return self._memory.get(f"__guest__{session_id}", 0)

    def increment_guest_count(self, session_id: str) -> int:
        if self._redis:
            try:
                count = self._redis.incr(f"guest_chat:{session_id}")
                self._redis.expire(f"guest_chat:{session_id}", SESSION_TTL)
                return count
            except Exception:
                pass
        key = f"__guest__{session_id}"
        self._memory[key] = self._memory.get(key, 0) + 1
        return self._memory[key]

    def reset_guest_count(self, session_id: str) -> None:
        if self._redis:
            try:
                self._redis.delete(f"guest_chat:{session_id}")
            except Exception:
                pass
        self._memory.pop(f"__guest__{session_id}", None)


# ── Singleton ─────────────────────────────────────────────────────────────────
_store: SessionStore | None = None


def get_session_store() -> SessionStore:
    """Return the process-wide SessionStore singleton."""
    global _store
    if _store is None:
        _store = SessionStore()
    return _store
