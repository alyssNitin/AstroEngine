"""
backend/tasks/pdf_tasks.py
============================
Celery tasks for asynchronous PDF report generation.

B8: PDF rendering can take 5–30 seconds (fpdf2 + large readings).
    These tasks run in a Celery worker process so FastAPI stays responsive.

Public API
----------
  generate_pdf_async(session_id, email, name, birth_info, refined, chat_msgs)
    → Celery AsyncResult; result is the PDF bytes (b64-encoded for JSON transport)

  get_pdf_task_result(task_id)
    → dict: {"status": str, "pdf_bytes": bytes | None, "error": str | None}

Fallback
--------
  If Celery is not installed, the task runs synchronously (blocking) but the
  HTTP interface is identical — the caller still gets a task_id back and can
  poll /export/status/{task_id}.

In-memory result store (no Celery)
-----------------------------------
  When using the sync stub, PDF bytes are stored in _RESULT_STORE (in-process
  dict) keyed by task_id so the download endpoint can retrieve them.
  This is cleared on restart — acceptable for dev/single-process deployments.

Environment variables
---------------------
  PDF_RESULT_TTL_SECONDS : how long to keep results in-memory store (default 3600)
"""
from __future__ import annotations

import base64
import logging
import os
import time
import uuid
from typing import Any, Dict, Optional

from backend.tasks.celery_app import celery

logger = logging.getLogger(__name__)

_PDF_RESULT_TTL = int(os.environ.get("PDF_RESULT_TTL_SECONDS", "3600"))

# ── In-memory result store (used when Celery is not running) ─────────────────
# Stores: {task_id: {"status": str, "pdf_b64": str|None, "error": str|None, "ts": float}}
_RESULT_STORE: Dict[str, Any] = {}


def _prune_result_store():
    """Remove stale entries from the in-memory store."""
    now = time.time()
    stale = [k for k, v in _RESULT_STORE.items() if now - v.get("ts", 0) > _PDF_RESULT_TTL]
    for k in stale:
        del _RESULT_STORE[k]


# ── Celery task ───────────────────────────────────────────────────────────────

@celery.task(
    name="backend.tasks.pdf_tasks.generate_pdf",
    bind=True,
    max_retries=2,
    default_retry_delay=10,
    acks_late=True,
    track_started=True,
)
def generate_pdf(
    self,
    session_id: str,
    email: str,
    name: str,
    birth_info: str,
    refined: str,
    chat_msgs: list,
) -> str:
    """
    Generate a PDF report and return its content as a base64-encoded string.

    Parameters
    ----------
    session_id : str   — reading session ID (used for file naming)
    email      : str   — user's email (used for file naming / audit)
    name       : str   — user's name shown in the report
    birth_info : str   — birth details string
    refined    : str   — AI-generated deep reading text
    chat_msgs  : list  — list of {"role": str, "content": str} chat messages

    Returns
    -------
    str — base64-encoded PDF bytes

    The result is stored in Celery's result backend (Redis) so the download
    endpoint can retrieve it by task_id.
    """
    task_id = self.request.id or str(uuid.uuid4())
    logger.info("PDF task started: session=%s email=%s task_id=%s", session_id, email, task_id)

    try:
        from backend.reports.pdf_generator import generate_report_pdf
        pdf_bytes, _content_type = generate_report_pdf(name, birth_info, refined, chat_msgs)
        pdf_b64 = base64.b64encode(pdf_bytes).decode("ascii")
        # Also cache in-memory so single-process / stub deployments can serve it
        _prune_result_store()
        _RESULT_STORE[task_id] = {
            "status": "success",
            "pdf_b64": pdf_b64,
            "error": None,
            "ts": time.time(),
        }
        logger.info("PDF task done: session=%s size=%d bytes", session_id, len(pdf_bytes))
        return pdf_b64
    except Exception as exc:
        logger.error("PDF task failed: session=%s error=%s", session_id, exc, exc_info=True)
        _RESULT_STORE[task_id] = {
            "status": "failure",
            "pdf_b64": None,
            "error": str(exc),
            "ts": time.time(),
        }
        try:
            raise self.retry(exc=exc)
        except Exception:
            raise


# ── Helper used by FastAPI endpoints ─────────────────────────────────────────

def submit_pdf_task(
    session_id: str,
    email: str,
    name: str,
    birth_info: str,
    refined: str,
    chat_msgs: list,
) -> str:
    """
    Submit a PDF generation task and return its task_id.

    This is the entry point used by the FastAPI endpoint.
    Returns a task_id string that the client can poll.
    """
    task_id = str(uuid.uuid4())
    _RESULT_STORE[task_id] = {"status": "pending", "pdf_b64": None, "error": None, "ts": time.time()}
    generate_pdf.apply_async(
        args=[session_id, email, name, birth_info, refined, chat_msgs],
        task_id=task_id,
    )
    return task_id


def get_pdf_task_result(task_id: str) -> dict:
    """
    Poll the result of a PDF generation task.

    Returns
    -------
    dict with keys:
      status     : "pending" | "started" | "success" | "failure"
      pdf_bytes  : bytes | None    (only when status == "success")
      error      : str | None      (only when status == "failure")
      progress   : int             (0–100, approximate)
    """
    # Try in-memory store first (covers sync-stub case + cached Celery results)
    local = _RESULT_STORE.get(task_id)

    # Also try the Celery result backend
    try:
        async_result = celery.AsyncResult(task_id)
        celery_state  = async_result.state.lower()  # pending/started/success/failure/retry
    except Exception:
        celery_state = "unknown"
        async_result = None

    # Resolve final status
    if celery_state in ("success",):
        try:
            pdf_b64 = async_result.get(timeout=1, propagate=False)
            if pdf_b64:
                return {
                    "status":    "success",
                    "pdf_bytes": base64.b64decode(pdf_b64),
                    "error":     None,
                    "progress":  100,
                }
        except Exception:
            pass

    if local and local.get("status") == "success" and local.get("pdf_b64"):
        return {
            "status":    "success",
            "pdf_bytes": base64.b64decode(local["pdf_b64"]),
            "error":     None,
            "progress":  100,
        }

    if celery_state in ("failure",):
        err = ""
        try:
            err = str(async_result.get(timeout=1, propagate=False))
        except Exception:
            pass
        err = err or (local or {}).get("error") or "PDF generation failed"
        return {"status": "failure", "pdf_bytes": None, "error": err, "progress": 0}

    if local and local.get("status") == "failure":
        return {"status": "failure", "pdf_bytes": None, "error": local.get("error"), "progress": 0}

    # Intermediate states
    if celery_state == "started":
        return {"status": "started", "pdf_bytes": None, "error": None, "progress": 50}

    # Default: pending
    return {"status": "pending", "pdf_bytes": None, "error": None, "progress": 10}
