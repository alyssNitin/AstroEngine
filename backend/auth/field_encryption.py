"""
backend/auth/field_encryption.py
==================================
Column-level AES-256-GCM encryption for PII fields.

Upgrade path
------------
  Previous: Fernet (AES-128-CBC + HMAC-SHA256)  -- stored as "enc:<token>"
  Current:  AES-256-GCM                          -- stored as "gcm:<nonce>:<tag>:<ct>"
  Both formats are transparently readable; new writes always use AES-256-GCM.

Key management
--------------
  Mode 1 -- AWS KMS (production):
      Set AWS_KMS_KEY_ID. KMS GenerateDataKey is called once per process,
      the 32-byte plaintext data-key is cached in memory.

  Mode 2 -- Environment variable (dev / staging):
      Set FIELD_ENCRYPTION_KEY to a URL-safe base64-encoded 32-byte key.
      Generate:
          python3 -c "import os,base64; print(base64.urlsafe_b64encode(os.urandom(32)).decode())"

  Mode 3 -- Dev mode (no key):
      Values stored as "plain:<value>" -- app still runs, WARNING logged.

Storage prefixes:
  "gcm:<nonce_b64>:<tag_b64>:<ct_b64>"  -- AES-256-GCM (current)
  "enc:<fernet_token>"                  -- legacy Fernet (read-only)
  "plain:<value>"                       -- dev mode (no key)
  "<bare value>"                        -- pre-encryption legacy rows
"""
from __future__ import annotations

import base64
import os
import sys
from typing import Optional

# -- Configuration -------------------------------------------------------------

_KEY_ENV     = "FIELD_ENCRYPTION_KEY"
_KMS_KEY_ENV = "AWS_KMS_KEY_ID"

_ENC_PREFIX   = "enc:"     # legacy Fernet (read-only)
_GCM_PREFIX   = "gcm:"     # AES-256-GCM (current)
_PLAIN_PREFIX = "plain:"   # dev mode

_raw_env_key: str = os.environ.get(_KEY_ENV, "")
_kms_key_id:  str = os.environ.get(_KMS_KEY_ENV, "")

# -- Module-level key state ----------------------------------------------------

_aes_key:    Optional[bytes] = None   # 32-byte AES-256 key
_fernet:     object          = None   # Fernet instance (legacy read-only)
_kms_client: object          = None   # boto3 KMS client (lazy init)


def _init() -> None:
    """Initialise encryption key from environment on import."""
    global _aes_key, _fernet

    if _kms_key_id:
        # KMS mode -- data-key fetched lazily on first encrypt/decrypt call
        return

    if _raw_env_key:
        raw = _raw_env_key.strip()
        try:
            decoded = base64.urlsafe_b64decode(raw + "==")
        except Exception:
            try:
                decoded = base64.b64decode(raw + "==")
            except Exception:
                decoded = b""

        if len(decoded) >= 32:
            _aes_key = decoded[:32]
            # Also init legacy Fernet for reading old rows
            try:
                from cryptography.fernet import Fernet
                fernet_key = base64.urlsafe_b64encode(_aes_key)
                _fernet = Fernet(fernet_key)
            except Exception:
                pass
            return

        # Might be a native 44-char Fernet key -- try directly
        try:
            from cryptography.fernet import Fernet
            _fernet = Fernet(_raw_env_key.encode())
            _aes_key = base64.urlsafe_b64decode(_raw_env_key.encode() + b"==")[:32]
            return
        except Exception as exc:
            print(
                f"[field_encryption] ERROR: FIELD_ENCRYPTION_KEY invalid: {exc}\n"
                'Generate a key: python3 -c "import os,base64; '
                'print(base64.urlsafe_b64encode(os.urandom(32)).decode())"',
                file=sys.stderr,
            )
            return

    print(
        "[field_encryption] WARNING: Neither AWS_KMS_KEY_ID nor FIELD_ENCRYPTION_KEY "
        "is set -- PII will NOT be encrypted at rest. NOT safe for production.",
        file=sys.stderr,
    )


_init()


# -- KMS helpers ---------------------------------------------------------------

_kms_plaintext_key: Optional[bytes] = None


def _get_kms_key() -> bytes:
    """Return the 32-byte plaintext data-key from KMS (cached after first call)."""
    global _kms_plaintext_key, _kms_client

    if _kms_plaintext_key is not None:
        return _kms_plaintext_key

    try:
        import boto3
    except ImportError:
        raise RuntimeError(
            "boto3 not installed (pip install boto3) -- required for KMS mode.\n"
            "Alternatively, set FIELD_ENCRYPTION_KEY for env-var mode."
        )

    if _kms_client is None:
        _kms_client = boto3.client("kms")

    resp = _kms_client.generate_data_key(KeyId=_kms_key_id, KeySpec="AES_256")
    _kms_plaintext_key = resp["Plaintext"]   # 32 bytes
    return _kms_plaintext_key


# -- AES-256-GCM core ----------------------------------------------------------

def _gcm_encrypt(plaintext: str, key: bytes) -> str:
    """Encrypt with AES-256-GCM. Returns gcm:<nonce_b64>:<tag_b64>:<ct_b64>"""
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    nonce = os.urandom(12)
    aesgcm = AESGCM(key)
    ct_and_tag = aesgcm.encrypt(nonce, plaintext.encode("utf-8"), None)
    # AESGCM appends 16-byte tag to ciphertext
    ct  = ct_and_tag[:-16]
    tag = ct_and_tag[-16:]
    b64 = base64.urlsafe_b64encode
    return (
        _GCM_PREFIX
        + b64(nonce).decode().rstrip("=")
        + ":" + b64(tag).decode().rstrip("=")
        + ":" + b64(ct).decode().rstrip("=")
    )


def _gcm_decrypt(stored: str, key: bytes) -> str:
    """Decrypt gcm:<nonce_b64>:<tag_b64>:<ct_b64>"""
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    def _pad(s: str) -> str:
        return s + "=" * (-len(s) % 4)

    body = stored[len(_GCM_PREFIX):]
    parts = body.split(":")
    if len(parts) != 3:
        raise ValueError(f"Malformed GCM token: expected 3 parts, got {len(parts)}")
    nonce_b64, tag_b64, ct_b64 = parts
    nonce = base64.urlsafe_b64decode(_pad(nonce_b64))
    tag   = base64.urlsafe_b64decode(_pad(tag_b64))
    ct    = base64.urlsafe_b64decode(_pad(ct_b64))
    aesgcm = AESGCM(key)
    return aesgcm.decrypt(nonce, ct + tag, None).decode("utf-8")


# -- Public API ----------------------------------------------------------------

def is_encryption_enabled() -> bool:
    """Return True if encryption is active (env key or KMS key configured)."""
    return bool(_aes_key or _kms_key_id)


def encrypt_pii(value: Optional[str]) -> Optional[str]:
    """
    Encrypt a PII string using AES-256-GCM.

    Returns:
        "gcm:<nonce>:<tag>:<ct>"  -- encrypted
        "plain:<value>"           -- dev mode (no key set)
        None / ""                 -- passthrough for None/empty
    """
    if value is None:
        return None
    if value == "":
        return ""

    try:
        if _kms_key_id:
            key = _get_kms_key()
        elif _aes_key:
            key = _aes_key
        else:
            return _PLAIN_PREFIX + value

        return _gcm_encrypt(value, key)

    except Exception as exc:
        print(f"[field_encryption] encrypt error: {exc}", file=sys.stderr)
        return _PLAIN_PREFIX + value   # fallback: plaintext > crash


def decrypt_pii(stored: Optional[str]) -> Optional[str]:
    """
    Decrypt a PII string from storage.

    Handles all storage formats:
        "gcm:..."   -> AES-256-GCM  (current)
        "enc:..."   -> legacy Fernet (backward-compat read)
        "plain:..." -> dev-mode plaintext
        "<bare>"    -> pre-encryption legacy rows
        None / ""   -> returned as-is
    """
    if stored is None:
        return None
    if stored == "":
        return ""

    # AES-256-GCM (current)
    if stored.startswith(_GCM_PREFIX):
        try:
            key = _get_kms_key() if _kms_key_id else _aes_key
            if not key:
                print(
                    "[field_encryption] WARNING: GCM token found but no key configured.",
                    file=sys.stderr,
                )
                return "[encrypted -- key not loaded]"
            return _gcm_decrypt(stored, key)
        except Exception as exc:
            print(f"[field_encryption] GCM decrypt error: {exc}", file=sys.stderr)
            return "[decrypt error]"

    # Legacy Fernet (read-only backward compat)
    if stored.startswith(_ENC_PREFIX):
        if _fernet is None:
            print(
                "[field_encryption] WARNING: legacy Fernet token found but Fernet not initialised.",
                file=sys.stderr,
            )
            return "[encrypted -- legacy key needed]"
        try:
            token = stored[len(_ENC_PREFIX):].encode("ascii")
            return _fernet.decrypt(token).decode("utf-8")  # type: ignore[attr-defined]
        except Exception as exc:
            print(f"[field_encryption] Fernet decrypt error: {exc}", file=sys.stderr)
            return "[decrypt error]"

    # Dev-mode plaintext
    if stored.startswith(_PLAIN_PREFIX):
        return stored[len(_PLAIN_PREFIX):]

    # Bare legacy value (pre-encryption rows)
    return stored


def is_pii_encrypted(stored: Optional[str]) -> bool:
    """Return True if the stored value is encrypted (GCM or legacy Fernet)."""
    if not stored:
        return False
    return stored.startswith(_GCM_PREFIX) or stored.startswith(_ENC_PREFIX)


def rotate_to_gcm(stored: Optional[str]) -> Optional[str]:
    """
    Re-encrypt a single field value from Fernet/plain -> AES-256-GCM.
    Use in a one-off migration script to upgrade existing rows.
    """
    if stored is None:
        return None
    plaintext = decrypt_pii(stored)
    if plaintext is None:
        return None
    return encrypt_pii(plaintext)


def validate_encryption_key() -> list[str]:
    """
    Validate the encryption configuration.
    Returns a list of error strings; empty = OK.
    """
    if _kms_key_id:
        return []   # KMS configured -- validated lazily
    errors: list[str] = []
    if not _raw_env_key:
        errors.append(
            "Neither AWS_KMS_KEY_ID nor FIELD_ENCRYPTION_KEY is set -- "
            "PII fields will not be encrypted. Required for production."
        )
    elif _aes_key is None:
        errors.append(
            "FIELD_ENCRYPTION_KEY is set but could not be decoded to a 32-byte key. "
            'Generate: python3 -c "import os,base64; print(base64.urlsafe_b64encode(os.urandom(32)).decode())"'
        )
    return errors
