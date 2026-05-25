"""
backend/api/rate_limiter.py
============================
Lightweight in-process rate limiter for NarayanAstroReader.

Uses a sliding-window counter per (IP, endpoint) key.  Redis-backed when
available; falls back to an in-memory dict for single-instance dev mode.

Usage (FastAPI dependency)::

    from backend.api.rate_limiter import rate_limit

    @app.post("/auth/login")
    def login(req: LoginRequest, _=Depends(rate_limit("login", max_calls=5, window=60))):
        ...

The dependency raises HTTP 429 when the caller exceeds the limit.
The Retry-After header is set to the remaining window seconds.
"""
from __future__ import annotations

import os
import time
from collections import defaultdict
from threading import Lock
from typing import Callable

from fastapi import Depends, HTTPException, Request, status

# Try to use Redis for distributed rate limiting
_REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
_redis_client = None
try:
    import redis as _redis_lib
    _c = _redis_lib.from_url(_REDIS_URL, decode_responses=True,
                              socket_connect_timeout=1, socket_timeout=1)
    _c.ping()
    _redis_client = _c
except Exception:
    pass   # Fall back to in-memory

# In-memory sliding window store: {key: [(timestamp, count), ...]}
_mem_store: dict[str, list[float]] = defaultdict(list)
_mem_lock  = Lock()


def _ip(request: Request) -> str:
    """Extract client IP, respecting X-Forwarded-For."""
    xff = request.headers.get("X-Forwarded-For")
    if xff:
        return xff.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _check_redis(key: str, max_calls: int, window: int) -> tuple[bool, int]:
    """Sliding-window check via Redis. Returns (allowed, retry_after)."""
    try:
        pipe = _redis_client.pipeline()
        now  = time.time()
        pipe.zremrangebyscore(key, 0, now - window)
        pipe.zadd(key, {str(now): now})
        pipe.zcard(key)
        pipe.expire(key, window)
        results = pipe.execute()
        count = results[2]
        if count > max_calls:
            oldest = _redis_client.zrange(key, 0, 0, withscores=True)
            retry  = int(window - (now - oldest[0][1])) + 1 if oldest else window
            return False, retry
        return True, 0
    except Exception:
        return True, 0   # Redis error → fail open


def _check_memory(key: str, max_calls: int, window: int) -> tuple[bool, int]:
    """Sliding-window check via in-memory list."""
    now = time.time()
    with _mem_lock:
        calls = [t for t in _mem_store[key] if now - t < window]
        if len(calls) >= max_calls:
            retry = int(window - (now - min(calls))) + 1
            _mem_store[key] = calls
            return False, retry
        calls.append(now)
        _mem_store[key] = calls
        return True, 0


def rate_limit(endpoint: str, max_calls: int = 10, window: int = 60) -> Callable:
    """
    Return a FastAPI dependency that enforces a rate limit.

    Args:
        endpoint:  Label used as part of the Redis/memory key (e.g. "login").
        max_calls: Maximum allowed requests in the window.
        window:    Sliding window size in seconds.
    """
    def _dependency(request: Request) -> None:
        ip  = _ip(request)
        key = f"rl:{endpoint}:{ip}"

        if _redis_client:
            allowed, retry_after = _check_redis(key, max_calls, window)
        else:
            allowed, retry_after = _check_memory(key, max_calls, window)

        if not allowed:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Too many requests. Please wait {retry_after} seconds.",
                headers={"Retry-After": str(retry_after)},
            )

    return _dependency


# ── Pre-built limits ──────────────────────────────────────────────────────────

# Sensitive auth endpoints — 5 attempts / 60 s
limit_login          = Depends(rate_limit("login",           max_calls=5,  window=60))
limit_register       = Depends(rate_limit("register",        max_calls=5,  window=60))
limit_forgot_pass    = Depends(rate_limit("forgot_password", max_calls=3,  window=300))
limit_resend_verify  = Depends(rate_limit("resend_verify",   max_calls=3,  window=300))

# General API — 60 req / min per IP
limit_api            = Depends(rate_limit("api",             max_calls=60, window=60))

# Heavy AI endpoints — 10 req / min
limit_ai             = Depends(rate_limit("ai",              max_calls=10, window=60))

# Payment / wallet — 5 topup orders per 5 min per IP (fraud prevention)
limit_topup          = Depends(rate_limit("topup",           max_calls=5,  window=300))
