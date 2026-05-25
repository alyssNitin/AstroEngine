"""
backend/storage/report_store.py
================================
S3-compatible object storage for AI-generated reports,
with automatic local-filesystem fallback.

Usage
-----
    from backend.storage.report_store import ReportStore

    store = ReportStore()                          # auto-detects S3 or local
    key   = store.save("career", email, text)      # returns object key
    text  = store.load(key)                        # retrieve by key
    url   = store.presigned_url(key, expires=3600) # temporary download link
    store.delete(key)

Configuration (via .env / environment variables)
------------------------------------------------
    S3_BUCKET        — bucket name; if empty, uses local fallback
    S3_REGION        — e.g. ap-south-1
    S3_ACCESS_KEY    — AWS / compatible access key
    S3_SECRET_KEY    — AWS / compatible secret key
    S3_ENDPOINT_URL  — (optional) custom endpoint for MinIO / Backblaze / etc.
    REPORT_LOCAL_DIR — local directory for fallback storage (default: ./reports)
"""
from __future__ import annotations

import hashlib
import json
import os
import time
import uuid
from pathlib import Path
from typing import Optional

# ── Configuration ─────────────────────────────────────────────────────────────

_S3_BUCKET       = os.environ.get("S3_BUCKET", "")
_S3_REGION       = os.environ.get("S3_REGION", "ap-south-1")
_S3_ACCESS_KEY   = os.environ.get("S3_ACCESS_KEY", "")
_S3_SECRET_KEY   = os.environ.get("S3_SECRET_KEY", "")
_S3_ENDPOINT_URL = os.environ.get("S3_ENDPOINT_URL", "")   # empty = AWS
_LOCAL_DIR       = Path(os.environ.get("REPORT_LOCAL_DIR", "./reports"))

_USE_S3 = bool(_S3_BUCKET and _S3_ACCESS_KEY and _S3_SECRET_KEY)

# ── S3 client (lazy) ──────────────────────────────────────────────────────────

_s3_client = None


def _get_s3():
    global _s3_client
    if _s3_client is not None:
        return _s3_client
    try:
        import boto3
        kwargs: dict = {
            "region_name":           _S3_REGION,
            "aws_access_key_id":     _S3_ACCESS_KEY,
            "aws_secret_access_key": _S3_SECRET_KEY,
        }
        if _S3_ENDPOINT_URL:
            kwargs["endpoint_url"] = _S3_ENDPOINT_URL
        _s3_client = boto3.client("s3", **kwargs)
        return _s3_client
    except ImportError:
        raise RuntimeError(
            "boto3 is not installed. Install with: pip install boto3\n"
            "Or leave S3_BUCKET empty to use local storage fallback."
        )


# ── Key generation ─────────────────────────────────────────────────────────────

def _make_key(report_type: str, email: str) -> str:
    """
    Generate a unique object key.
    Pattern: reports/{report_type}/{email_hash}/{timestamp}_{uuid8}.json
    Email is hashed so it doesn't appear in storage paths.
    """
    email_hash = hashlib.sha256(email.lower().encode()).hexdigest()[:12]
    ts         = int(time.time())
    uid        = uuid.uuid4().hex[:8]
    return f"reports/{report_type}/{email_hash}/{ts}_{uid}.json"


# ── S3 backend ────────────────────────────────────────────────────────────────

def _s3_save(key: str, payload: str) -> None:
    client = _get_s3()
    client.put_object(
        Bucket               = _S3_BUCKET,
        Key                  = key,
        Body                 = payload.encode("utf-8"),
        ContentType          = "application/json",
        ServerSideEncryption = "AES256",
    )


def _s3_load(key: str) -> Optional[str]:
    try:
        response = _get_s3().get_object(Bucket=_S3_BUCKET, Key=key)
        return response["Body"].read().decode("utf-8")
    except Exception:
        return None


def _s3_delete(key: str) -> bool:
    try:
        _get_s3().delete_object(Bucket=_S3_BUCKET, Key=key)
        return True
    except Exception:
        return False


def _s3_presigned_url(key: str, expires: int = 3600) -> str:
    try:
        return _get_s3().generate_presigned_url(
            "get_object",
            Params    = {"Bucket": _S3_BUCKET, "Key": key},
            ExpiresIn = expires,
        )
    except Exception:
        return ""


def _s3_list(prefix: str) -> list[str]:
    try:
        resp = _get_s3().list_objects_v2(Bucket=_S3_BUCKET, Prefix=prefix)
        return [obj["Key"] for obj in resp.get("Contents", [])]
    except Exception:
        return []


# ── Local fallback backend ────────────────────────────────────────────────────

def _local_path(key: str) -> Path:
    return _LOCAL_DIR / key


def _local_save(key: str, payload: str) -> None:
    path = _local_path(key)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(payload, encoding="utf-8")


def _local_load(key: str) -> Optional[str]:
    path = _local_path(key)
    return path.read_text(encoding="utf-8") if path.exists() else None


def _local_delete(key: str) -> bool:
    path = _local_path(key)
    if path.exists():
        path.unlink()
        return True
    return False


def _local_presigned_url(key: str, expires: int = 3600) -> str:
    """Local storage has no presigned URLs; returns a relative path hint."""
    return f"/reports/download?key={key}"


def _local_list(prefix: str) -> list[str]:
    base = _LOCAL_DIR / prefix
    if not base.exists():
        return []
    return [
        str(p.relative_to(_LOCAL_DIR)).replace("\\", "/")
        for p in base.rglob("*.json")
    ]


# ── Public ReportStore interface ─────────────────────────────────────────────

class ReportStore:
    """
    Unified interface for storing and retrieving AI reports.

    Auto-selects S3 if S3_BUCKET + S3_ACCESS_KEY + S3_SECRET_KEY are set;
    otherwise falls back to local filesystem under REPORT_LOCAL_DIR.
    """

    def __init__(self) -> None:
        self._use_s3 = _USE_S3

    @property
    def backend(self) -> str:
        return "s3" if self._use_s3 else "local"

    def save(
        self,
        report_type: str,
        email: str,
        content: str,
        metadata: dict | None = None,
    ) -> str:
        """
        Persist a report and return its storage key.

        Parameters
        ----------
        report_type : e.g. "career", "yearly_forecast", "remedies", "compatibility"
        email       : owner's email (hashed in key, not stored in plaintext)
        content     : the full report text
        metadata    : optional dict merged into the stored JSON envelope

        Returns
        -------
        str — the storage key (pass to load / delete / presigned_url)
        """
        key      = _make_key(report_type, email)
        envelope = json.dumps(
            {
                "report_type": report_type,
                "content":     content,
                "created_at":  int(time.time()),
                "metadata":    metadata or {},
            },
            ensure_ascii=False,
        )
        if self._use_s3:
            _s3_save(key, envelope)
        else:
            _local_save(key, envelope)
        return key

    def load(self, key: str) -> Optional[str]:
        """Load a report by key. Returns the content string or None."""
        raw = _s3_load(key) if self._use_s3 else _local_load(key)
        if raw is None:
            return None
        try:
            return json.loads(raw).get("content", raw)
        except Exception:
            return raw

    def load_envelope(self, key: str) -> Optional[dict]:
        """Load the full JSON envelope (content + metadata + timestamps)."""
        raw = _s3_load(key) if self._use_s3 else _local_load(key)
        if raw is None:
            return None
        try:
            return json.loads(raw)
        except Exception:
            return {"content": raw}

    def delete(self, key: str) -> bool:
        """Delete a report. Returns True if found and deleted."""
        return _s3_delete(key) if self._use_s3 else _local_delete(key)

    def presigned_url(self, key: str, expires: int = 3600) -> str:
        """
        Generate a time-limited download URL.
        For S3: genuine presigned URL. For local: returns a /reports/ path.
        """
        if self._use_s3:
            return _s3_presigned_url(key, expires)
        return _local_presigned_url(key, expires)

    def list_for_email(self, email: str, report_type: str = "") -> list[str]:
        """
        List all stored report keys for an email (uses hashed prefix).
        """
        email_hash = hashlib.sha256(email.lower().encode()).hexdigest()[:12]
        if report_type:
            prefix = f"reports/{report_type}/{email_hash}/"
        else:
            prefix = "reports/"
        return _s3_list(prefix) if self._use_s3 else _local_list(prefix)


# ── Module-level singleton ────────────────────────────────────────────────────

_store: ReportStore | None = None


def get_report_store() -> ReportStore:
    """Return (or create) the module-level ReportStore singleton."""
    global _store
    if _store is None:
        _store = ReportStore()
    return _store
