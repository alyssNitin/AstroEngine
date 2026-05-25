"""
backend/cache/redis_cache.py
==============================
Redis-backed cache layer used by wallet balance reads (B5) and
AI LLM response caching (B6).

Architecture §11 / Arch §8:
  - Wallet balance: p95 ≤ 20ms read latency (requires Redis hot cache)
  - AI responses: identical chart+report_type requests served from cache
    to avoid redundant LLM calls (24h TTL)

Falls back transparently to pass-through (no caching) when Redis is
unavailable, so the app runs fine without Redis in dev/CI.

Environment variables
---------------------
  REDIS_URL        : Redis connection URL (default: redis://localhost:6379/0)
  WALLET_CACHE_TTL : seconds, default 30  — wallet balance cache TTL
  AI_CACHE_TTL     : seconds, default 86400 (24h) — AI response cache TTL
  CACHE_ENABLED    : "false" to disable caching entirely (useful in tests)
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
from typing import Any, Optional

logger = logging.getLogger(__name__)

_REDIS_URL        = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
_WALLET_CACHE_TTL = int(os.environ.get("WALLET_CACHE_TTL", "30"))
_AI_CACHE_TTL     = int(os.environ.get("AI_CACHE_TTL", str(60 * 60 * 24)))
_CACHE_ENABLED    = os.environ.get("CACHE_ENABLED", "true").lower() != "false"

_WALLET_KEY_PREFIX = "nar:wallet:bal:"
_AI_KEY_PREFIX     = "nar:ai:resp:"


# ── Redis client (lazy init, singleton) ───────────────────────────────────────

_redis_client: Optional[object] = None
_redis_available = False


def _get_redis():
    """Return a Redis client, or None if unavailable."""
    global _redis_client, _redis_available
    if not _CACHE_ENABLED:
        return None
    if _redis_client is not None:
        return _redis_client if _redis_available else None
    try:
        import redis as _redis
        client = _redis.from_url(_REDIS_URL, decode_responses=True, socket_timeout=0.5)
        client.ping()
        _redis_client = client
        _redis_available = True
        logger.info("Redis cache connected: %s", _REDIS_URL)
    except Exception as e:
        _redis_client = None
        _redis_available = False
        logger.warning("Redis unavailable (%s) — caching disabled, falling back to DB", e)
    return _redis_client if _redis_available else None


# ── Wallet balance cache ──────────────────────────────────────────────────────

def get_wallet_balance_cached(email: str) -> Optional[dict]:
    """
    Return cached wallet balance dict for the user, or None if not cached.

    The cached value is a JSON dict:
      {"total": int, "paid": int, "promo": int, "balance_display": str}
    """
    r = _get_redis()
    if r is None:
        return None
    key = _WALLET_KEY_PREFIX + email
    try:
        raw = r.get(key)
        if raw:
            return json.loads(raw)
    except Exception as e:
        logger.debug("Wallet cache GET failed for %s: %s", email, e)
    return None


def set_wallet_balance_cache(email: str, balance_data: dict) -> None:
    """Cache wallet balance for the user (TTL = WALLET_CACHE_TTL seconds)."""
    r = _get_redis()
    if r is None:
        return
    key = _WALLET_KEY_PREFIX + email
    try:
        r.setex(key, _WALLET_CACHE_TTL, json.dumps(balance_data))
    except Exception as e:
        logger.debug("Wallet cache SET failed for %s: %s", email, e)


def invalidate_wallet_cache(email: str) -> None:
    """
    Invalidate cached wallet balance for the user.
    Must be called on every debit, credit, or topup operation.
    """
    r = _get_redis()
    if r is None:
        return
    key = _WALLET_KEY_PREFIX + email
    try:
        r.delete(key)
    except Exception as e:
        logger.debug("Wallet cache DEL failed for %s: %s", email, e)


# ── AI response cache ─────────────────────────────────────────────────────────

def _ai_cache_key(chart_data: dict, report_type: str, language: str) -> str:
    """
    Deterministic cache key for an AI report request.
    SHA-256 of (chart_data JSON sorted + report_type + language).
    Truncated to 48 chars for Redis key friendliness.
    """
    payload = json.dumps(
        {"chart": chart_data, "type": report_type, "lang": language},
        sort_keys=True,
        ensure_ascii=True,
    )
    digest = hashlib.sha256(payload.encode()).hexdigest()[:48]
    return _AI_KEY_PREFIX + digest


def get_ai_response_cached(
    chart_data: dict,
    report_type: str,
    language: str = "English",
) -> Optional[str]:
    """
    Return cached AI response text, or None if not in cache.

    Parameters
    ----------
    chart_data  : dict — kundli chart output (used as cache key)
    report_type : str  — e.g. "kundli_reading", "career", "compatibility"
    language    : str  — "English" | "Hindi" | "Tamil"
    """
    r = _get_redis()
    if r is None:
        return None
    key = _ai_cache_key(chart_data, report_type, language)
    try:
        return r.get(key)    # returns str or None
    except Exception as e:
        logger.debug("AI cache GET failed: %s", e)
    return None


def set_ai_response_cache(
    chart_data: dict,
    report_type: str,
    language: str,
    response_text: str,
) -> None:
    """Cache an AI response with 24h TTL."""
    r = _get_redis()
    if r is None:
        return
    key = _ai_cache_key(chart_data, report_type, language)
    try:
        r.setex(key, _AI_CACHE_TTL, response_text)
        logger.debug("AI response cached: key=%s ttl=%ds", key, _AI_CACHE_TTL)
    except Exception as e:
        logger.debug("AI cache SET failed: %s", e)


def invalidate_ai_cache(chart_data: dict, report_type: str, language: str) -> None:
    """Force-invalidate a specific AI cache entry (e.g. on user request to regenerate)."""
    r = _get_redis()
    if r is None:
        return
    key = _ai_cache_key(chart_data, report_type, language)
    try:
        r.delete(key)
    except Exception as e:
        logger.debug("AI cache DEL failed: %s", e)


def cache_health() -> dict:
    """Return Redis cache health status for /health endpoint."""
    r = _get_redis()
    if r is None:
        return {"redis": "unavailable", "caching": False}
    try:
        r.ping()
        return {"redis": "ok", "caching": True, "url": _REDIS_URL.split("@")[-1]}
    except Exception as e:
        return {"redis": f"error: {e}", "caching": False}
