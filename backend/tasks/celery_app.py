"""
backend/tasks/celery_app.py
============================
Celery application factory for NarayanAstroReader.

B8: Async PDF generation task queue.

Environment variables
---------------------
  CELERY_BROKER_URL    : broker (default: redis://localhost:6379/1)
  CELERY_RESULT_BACKEND: result store (default: redis://localhost:6379/2)
  CELERY_TASK_ALWAYS_EAGER : "true" in tests / dev — tasks run synchronously
                             without a worker process (default: false)

Worker startup
--------------
  celery -A backend.tasks.celery_app.celery worker --loglevel=info -Q pdf_queue

Architecture §8: The main FastAPI process never imports Celery workers directly.
Tasks are submitted via .delay() / .apply_async(); results are polled through
the Redis result backend.
"""
from __future__ import annotations

import os

# ── Celery import (soft dependency) ──────────────────────────────────────────
try:
    from celery import Celery  # type: ignore
    _CELERY_AVAILABLE = True
except ImportError:
    _CELERY_AVAILABLE = False
    Celery = None  # type: ignore


BROKER_URL       = os.environ.get("CELERY_BROKER_URL",     "redis://localhost:6379/1")
RESULT_BACKEND   = os.environ.get("CELERY_RESULT_BACKEND", "redis://localhost:6379/2")
ALWAYS_EAGER     = os.environ.get("CELERY_TASK_ALWAYS_EAGER", "false").lower() == "true"


def _make_celery() -> object:
    """Create and configure the Celery app, or return a stub if Celery is not installed."""
    if not _CELERY_AVAILABLE:
        return _CelerySyncStub()

    app = Celery(
        "narayan_astro",
        broker=BROKER_URL,
        backend=RESULT_BACKEND,
    )
    app.conf.update(
        task_serializer="json",
        result_serializer="json",
        accept_content=["json"],
        task_track_started=True,
        task_acks_late=True,              # re-queue on worker crash
        worker_prefetch_multiplier=1,     # fair dispatch — PDF tasks are heavy
        task_routes={
            "backend.tasks.pdf_tasks.*": {"queue": "pdf_queue"},
        },
        task_always_eager=ALWAYS_EAGER,   # synchronous in test/dev
        result_expires=3600 * 24,         # keep results 24h
    )
    return app


# ── Synchronous stub (no Celery installed) ────────────────────────────────────
# Falls back to running the task inline (blocking). This keeps the API functional
# in development without requiring a Celery worker or Redis.

class _AsyncResult:
    """Minimal AsyncResult lookalike returned by the sync stub."""

    def __init__(self, task_id: str, result=None, state: str = "SUCCESS", error=None):
        self.id = task_id
        self._result = result
        self._state  = state
        self._error  = error

    @property
    def state(self):
        return self._state

    def ready(self) -> bool:
        return self._state in ("SUCCESS", "FAILURE")

    def successful(self) -> bool:
        return self._state == "SUCCESS"

    def failed(self) -> bool:
        return self._state == "FAILURE"

    def get(self, timeout=None, propagate=True):
        if self._error and propagate:
            raise self._error
        return self._result

    def forget(self):
        pass


class _TaskStub:
    """Mimics a Celery task's .delay() / .apply_async() interface."""

    def __init__(self, fn):
        self._fn = fn

    def delay(self, *args, **kwargs):
        return self.apply_async(args=args, kwargs=kwargs)

    def apply_async(self, args=(), kwargs=None, task_id=None, **_):
        import uuid
        tid = task_id or str(uuid.uuid4())
        try:
            result = self._fn(*(args or ()), **(kwargs or {}))
            return _AsyncResult(tid, result=result, state="SUCCESS")
        except Exception as exc:
            return _AsyncResult(tid, state="FAILURE", error=exc)

    def AsyncResult(self, task_id: str):  # noqa: N802
        return _AsyncResult(task_id, state="PENDING")


class _CelerySyncStub:
    """Drop-in replacement for the Celery app object when celery is not installed."""

    def task(self, *args, **kwargs):
        """Decorator: wraps the function in a _TaskStub."""
        def decorator(fn):
            return _TaskStub(fn)
        # Support both @celery.task and @celery.task(name=...) syntax
        if args and callable(args[0]):
            return decorator(args[0])
        return decorator

    def AsyncResult(self, task_id: str):  # noqa: N802
        return _AsyncResult(task_id, state="PENDING")

    def send_task(self, name, args=(), kwargs=None, **_):
        import uuid
        return _AsyncResult(str(uuid.uuid4()), state="PENDING")


# Singleton — import this in pdf_tasks.py and in main.py
celery: object = _make_celery()
