"""
backend/persistence/database.py
================================
PostgreSQL persistence layer for NarayanAstroReader.

Replaces the previous SQLite implementation. Uses psycopg2 with a
ThreadedConnectionPool for safe concurrent access from FastAPI workers.

Connection is configured via the DATABASE_URL environment variable:
  postgresql://user:password@host:5432/dbname

All JSON columns are stored as TEXT with json.dumps/loads so the
Python API surface is identical to the previous SQLite version —
no changes needed in main.py or any callers.

Wallet amounts are stored as integers (minor units):
  India:         paise  (₹1 = 100 paise)
  International: cents  ($1 = 100 cents)
"""
from __future__ import annotations

import hashlib
import json
import os
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta
from typing import Any

import psycopg2
import psycopg2.extras
import psycopg2.pool
import psycopg2.errors

# ── PII field encryption ──────────────────────────────────────────────────────
# Imported lazily-ish to avoid circular imports; safe to call at module level.
try:
    from backend.auth.field_encryption import encrypt_pii, decrypt_pii
except ImportError:
    # Fallback if cryptography library is not installed
    def encrypt_pii(v):  # type: ignore[misc]
        return v
    def decrypt_pii(v):  # type: ignore[misc]
        return v

# Columns in the users / reading_history tables that hold PII and must be
# encrypted before storage and decrypted after retrieval.
_PII_COLS: frozenset[str] = frozenset({
    "name",
    "date_of_birth",
    "time_of_birth",
    "place_of_birth",
})

# ── Config ────────────────────────────────────────────────────────────────────

DATABASE_URL: str = os.environ.get(
    "DATABASE_URL",
    "postgresql://narayan:narayan_dev_pass@localhost:5432/narayan_astro",
)

# Legacy cost constants — kept for backward-compat imports.
# Actual amounts now come from payment.wallet.get_pricing(region).
WELCOME_CREDIT_CENTS = 10_000   # ₹100 India default (paise)
REPORT_COST_CENTS    = 10_000   # ₹100 India default
CHAT_COST_CENTS      =  2_500   # ₹25  India default
FREE_CREDITS_ON_REGISTER = 0    # No free credits until email verified

# Columns whose values are JSON strings (auto-parsed on read)
_JSON_COLS = {
    "kundli_json", "predictions_json", "lagna_json",
    "birth_info_json", "children_info_json",
    "planet_knowledge_json", "wallet_transactions",
    "chat_messages_json",
}


def _welcome_credit_for_region(region: str) -> int:
    """Return the welcome credit in minor units for the given region."""
    from payment.wallet import get_pricing   # lazy import — avoids circular import
    return get_pricing(region)["welcome"]


# ── Connection pool ───────────────────────────────────────────────────────────

_pool: psycopg2.pool.ThreadedConnectionPool | None = None


def _get_pool() -> psycopg2.pool.ThreadedConnectionPool:
    """Return (and lazily create) the shared connection pool."""
    global _pool
    if _pool is None:
        _pool = psycopg2.pool.ThreadedConnectionPool(
            minconn=2,
            maxconn=10,
            dsn=DATABASE_URL,
        )
    return _pool


@contextmanager
def _get_conn():
    """Context manager: borrow a connection from the pool, return it on exit."""
    pool = _get_pool()
    conn = pool.getconn()
    try:
        yield conn
    except Exception:
        conn.rollback()
        raise
    finally:
        pool.putconn(conn)


@contextmanager
def _cursor(conn):
    """Context manager: open a RealDictCursor (returns dict-like rows)."""
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        yield cur
    finally:
        cur.close()


# ── Password hashing ──────────────────────────────────────────────────────────

def _hash_password(password: str) -> str:
    salt = os.environ.get("PASSWORD_SALT", "narayan_astro_salt_2024")
    return hashlib.sha256(f"{salt}{password}".encode()).hexdigest()


# ── Schema DDL ────────────────────────────────────────────────────────────────
# All tables use CREATE TABLE IF NOT EXISTS so this is safe to re-run.
# Schema evolution is handled by init_schema() which applies each ALTER
# inside a separate transaction so already-existing columns are skipped.

_CREATE_USERS_SQL = """
CREATE TABLE IF NOT EXISTS users (
    id                          TEXT        PRIMARY KEY,
    email                       TEXT        UNIQUE NOT NULL,
    name                        TEXT        NOT NULL DEFAULT '',
    password_hash               TEXT        NOT NULL DEFAULT '',

    -- Email verification
    email_verified              BOOLEAN     NOT NULL DEFAULT FALSE,
    verification_token          TEXT        DEFAULT NULL,
    verification_token_expires  TIMESTAMPTZ DEFAULT NULL,
    verification_resend_count   INTEGER     NOT NULL DEFAULT 0,
    verification_resend_window  TIMESTAMPTZ DEFAULT NULL,

    -- Kundli data stored as JSON text
    date_of_birth               TEXT        NOT NULL DEFAULT '',
    time_of_birth               TEXT        NOT NULL DEFAULT '',
    place_of_birth              TEXT        NOT NULL DEFAULT '',
    latitude                    DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    longitude                   DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    timezone_offset             DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    kundli_json                 TEXT        NOT NULL DEFAULT '{}',
    predictions_json            TEXT        NOT NULL DEFAULT '{}',
    overall_theme               TEXT        NOT NULL DEFAULT '',
    lagna_json                  TEXT        NOT NULL DEFAULT '{}',
    birth_info_json             TEXT        NOT NULL DEFAULT '{}',
    refined_analysis            TEXT        NOT NULL DEFAULT '',
    planet_knowledge_json       TEXT        NOT NULL DEFAULT '{}',
    children_info_json          TEXT        NOT NULL DEFAULT '{}',
    marital_status              TEXT        NOT NULL DEFAULT '',
    user_type                   TEXT        NOT NULL DEFAULT 'general',
    preferred_language          TEXT        NOT NULL DEFAULT 'English',

    -- Wallet (integer minor units — avoids floating-point errors)
    wallet_balance_cents        INTEGER     NOT NULL DEFAULT 0,
    wallet_transactions         TEXT        NOT NULL DEFAULT '[]',
    paid_balance_cents          INTEGER     NOT NULL DEFAULT 0,
    promo_balance_cents         INTEGER     NOT NULL DEFAULT 0,

    -- Region / currency
    region                      TEXT        NOT NULL DEFAULT 'India',
    currency                    TEXT        NOT NULL DEFAULT 'INR',

    -- Chat session
    session_id                  TEXT        NOT NULL DEFAULT '',
    chat_messages_json          TEXT        NOT NULL DEFAULT '[]',

    -- Audit timestamps
    created_at                  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at                  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
"""

_CREATE_HISTORY_SQL = """
CREATE TABLE IF NOT EXISTS reading_history (
    id                    TEXT        PRIMARY KEY,
    email                 TEXT        NOT NULL,
    name                  TEXT        NOT NULL DEFAULT '',
    date_of_birth         TEXT        NOT NULL DEFAULT '',
    time_of_birth         TEXT        NOT NULL DEFAULT '',
    place_of_birth        TEXT        NOT NULL DEFAULT '',
    overall_theme         TEXT        NOT NULL DEFAULT '',
    refined_analysis      TEXT        NOT NULL DEFAULT '',
    chat_messages_json    TEXT        NOT NULL DEFAULT '[]',
    planet_knowledge_json TEXT        NOT NULL DEFAULT '{}',
    session_id            TEXT        NOT NULL DEFAULT '',
    created_at            TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
"""

_CREATE_LEDGER_SQL = """
CREATE TABLE IF NOT EXISTS wallet_ledger (
    id              BIGSERIAL    PRIMARY KEY,
    email           TEXT         NOT NULL,
    txn_type        TEXT         NOT NULL,
    balance_type    TEXT         NOT NULL DEFAULT 'promo',
    amount_cents    INTEGER      NOT NULL,
    reason          TEXT         NOT NULL DEFAULT '',
    paid_after      INTEGER      NOT NULL DEFAULT 0,
    promo_after     INTEGER      NOT NULL DEFAULT 0,
    total_after     INTEGER      NOT NULL DEFAULT 0,
    reference_id    TEXT         NOT NULL DEFAULT '',
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);
"""

# Index for fast lookups by email
_CREATE_SHARED_READINGS_SQL = """
CREATE TABLE IF NOT EXISTS shared_readings (
    id               TEXT        PRIMARY KEY,
    email            TEXT        NOT NULL,
    pin_hash         TEXT        NOT NULL,
    session_id       TEXT        NOT NULL DEFAULT '',
    name             TEXT        NOT NULL DEFAULT '',
    date_of_birth    TEXT        NOT NULL DEFAULT '',
    time_of_birth    TEXT        NOT NULL DEFAULT '',
    place_of_birth   TEXT        NOT NULL DEFAULT '',
    overall_theme    TEXT        NOT NULL DEFAULT '',
    refined_analysis TEXT        NOT NULL DEFAULT '',
    lagna_info_json  TEXT        NOT NULL DEFAULT '{}',
    expires_at       TIMESTAMPTZ NOT NULL,
    view_count       INTEGER     NOT NULL DEFAULT 0,
    max_views        INTEGER     NOT NULL DEFAULT 50,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
"""


_CREATE_PROFILES_SQL = """
CREATE TABLE IF NOT EXISTS kundli_profiles (
    id                    TEXT             PRIMARY KEY,
    user_email            TEXT             NOT NULL,
    label                 TEXT             NOT NULL DEFAULT '',
    name                  TEXT             NOT NULL DEFAULT '',
    date_of_birth         TEXT             NOT NULL DEFAULT '',
    time_of_birth         TEXT             NOT NULL DEFAULT '',
    place_of_birth        TEXT             NOT NULL DEFAULT '',
    latitude              DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    longitude             DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    timezone_offset       DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    is_active             BOOLEAN          NOT NULL DEFAULT FALSE,
    kundli_json           TEXT             NOT NULL DEFAULT '{}',
    refined_analysis      TEXT             NOT NULL DEFAULT '',
    planet_knowledge_json TEXT             NOT NULL DEFAULT '{}',
    created_at            TIMESTAMPTZ      NOT NULL DEFAULT NOW(),
    updated_at            TIMESTAMPTZ      NOT NULL DEFAULT NOW()
);
"""


_CREATE_AI_REPORTS_SQL = """
CREATE TABLE IF NOT EXISTS ai_reports (
    id              TEXT        PRIMARY KEY,
    email           TEXT        NOT NULL,
    session_id      TEXT        NOT NULL DEFAULT '',
    report_type     TEXT        NOT NULL,   -- career|yearly_forecast|remedies|compatibility|dasha
    storage_key     TEXT        NOT NULL DEFAULT '',  -- S3 / local path key
    storage_backend TEXT        NOT NULL DEFAULT 'local',
    language        TEXT        NOT NULL DEFAULT 'English',
    status          TEXT        NOT NULL DEFAULT 'completed',  -- generating|completed|failed
    content_preview TEXT        NOT NULL DEFAULT '',  -- first 500 chars for quick display
    metadata_json   TEXT        NOT NULL DEFAULT '{}',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at      TIMESTAMPTZ DEFAULT NULL
);
"""

_CREATE_INDEXES_SQL = [
    "CREATE INDEX IF NOT EXISTS idx_users_email           ON users(email);",
    "CREATE INDEX IF NOT EXISTS idx_reading_history_email ON reading_history(email);",
    "CREATE INDEX IF NOT EXISTS idx_users_verification_token ON users(verification_token) WHERE verification_token IS NOT NULL;",
    "CREATE INDEX IF NOT EXISTS idx_wallet_ledger_email_ts ON wallet_ledger(email, created_at DESC);",
    "CREATE INDEX IF NOT EXISTS idx_wallet_ledger_type     ON wallet_ledger(txn_type, created_at DESC);",
    "CREATE INDEX IF NOT EXISTS idx_shared_readings_email  ON shared_readings(email, created_at DESC);",
    "CREATE INDEX IF NOT EXISTS idx_shared_readings_expires ON shared_readings(expires_at);",
    "CREATE INDEX IF NOT EXISTS idx_kundli_profiles_email ON kundli_profiles(user_email, created_at DESC);",
    "CREATE INDEX IF NOT EXISTS idx_kundli_profiles_active ON kundli_profiles(user_email, is_active) WHERE is_active = TRUE;",
    "CREATE INDEX IF NOT EXISTS idx_ai_reports_email_type  ON ai_reports(email, report_type, created_at DESC);",
    "CREATE INDEX IF NOT EXISTS idx_ai_reports_session     ON ai_reports(session_id);",
]

# ── Schema evolution — columns added after initial release ────────────────────
# Each entry: (table, column_name, column_definition)
# Applied one at a time inside its own try/except so already-existing
# columns are silently skipped (postgres raises duplicate_column = 42701).
_EVOLVE_COLS: list[tuple[str, str, str]] = [
    ("users", "paid_balance_cents",      "INTEGER NOT NULL DEFAULT 0"),
    ("users", "promo_balance_cents",     "INTEGER NOT NULL DEFAULT 0"),
    ("users", "failed_login_attempts",   "INTEGER NOT NULL DEFAULT 0"),
    ("users", "locked_until",            "TIMESTAMPTZ DEFAULT NULL"),
    ("users", "last_failed_login",       "TIMESTAMPTZ DEFAULT NULL"),
    # MFA (TOTP) — Critical gap #55
    ("users", "mfa_enabled",            "BOOLEAN NOT NULL DEFAULT FALSE"),
    ("users", "mfa_secret",             "TEXT DEFAULT NULL"),
    ("users", "mfa_backup_codes",       "TEXT DEFAULT NULL"),  # JSON list of hashed codes
    # OAuth — Critical gap #56
    ("users", "oauth_provider",         "TEXT DEFAULT NULL"),
    ("users", "google_id",              "TEXT DEFAULT NULL"),
    # Promo credit expiry tracking
    ("users", "promo_granted_at",       "TIMESTAMPTZ DEFAULT NULL"),
]


def init_schema() -> None:
    """
    Create all tables and indexes if they don't exist.
    Apply any pending schema evolution columns.
    Safe to call multiple times (idempotent).
    """
    with _get_conn() as conn:
        with _cursor(conn) as cur:
            cur.execute(_CREATE_USERS_SQL)
            cur.execute(_CREATE_HISTORY_SQL)
            cur.execute(_CREATE_LEDGER_SQL)
            cur.execute(_CREATE_SHARED_READINGS_SQL)
            cur.execute(_CREATE_PROFILES_SQL)
            cur.execute(_CREATE_AI_REPORTS_SQL)
            for idx_sql in _CREATE_INDEXES_SQL:
                cur.execute(idx_sql)
        conn.commit()

    # Apply evolution columns one-by-one
    for table, col, coldef in _EVOLVE_COLS:
        try:
            with _get_conn() as conn:
                with _cursor(conn) as cur:
                    cur.execute(
                        f"ALTER TABLE {table} ADD COLUMN {col} {coldef}"
                    )
                conn.commit()
        except psycopg2.errors.DuplicateColumn:
            pass   # Column already exists — skip silently
        except Exception:
            pass

    # Backfill promo_granted_at for existing users who have promo balance
    try:
        with _get_conn() as conn:
            with _cursor(conn) as cur:
                cur.execute("""
                    UPDATE users
                    SET promo_granted_at = COALESCE(created_at::timestamptz, NOW())
                    WHERE promo_balance_cents > 0 AND promo_granted_at IS NULL
                """)
            conn.commit()
    except Exception:
        pass  # Non-fatal: column may not exist yet on very first boot


# ── Database class ────────────────────────────────────────────────────────────

class Database:
    """
    High-level PostgreSQL persistence layer for NarayanAstroReader.

    Public API is drop-in compatible with the previous SQLite implementation.
    Uses a shared ThreadedConnectionPool — thread-safe for FastAPI.

    Example usage::

        db = Database()
        result = db.register("user@example.com", "password123")
        profile = db.get_profile("user@example.com")
    """

    def __init__(self, db_path: str = "", path: str = "") -> None:
        """
        db_path / path arguments are accepted but ignored — PostgreSQL is
        configured via the DATABASE_URL environment variable.
        """
        init_schema()   # Creates tables if they don't exist

    # ── Health check ──────────────────────────────────────────────────────────

    def health_ping(self) -> None:
        """Execute a trivial DB query. Raises on connection failure."""
        with _get_conn() as conn:
            with _cursor(conn) as cur:
                cur.execute("SELECT 1")

    # ── Internal helpers ──────────────────────────────────────────────────────

    @staticmethod
    def _now() -> str:
        return datetime.utcnow().isoformat()

    @staticmethod
    def _append_txn(existing_json: str, entry: dict) -> str:
        """Append a transaction entry to the JSON array string."""
        try:
            txns = json.loads(existing_json) if existing_json else []
        except (json.JSONDecodeError, TypeError):
            txns = []
        txns.append(entry)
        return json.dumps(txns)

    @staticmethod
    def _row_to_dict(row: dict | None) -> dict | None:
        """
        Convert a psycopg2 RealDictRow to a plain dict.
        Auto-parses JSON text columns into Python dicts/lists.
        """
        if row is None:
            return None
        d = dict(row)
        for col in _JSON_COLS:
            if col in d and isinstance(d[col], str):
                try:
                    d[col] = json.loads(d[col])
                except (json.JSONDecodeError, TypeError):
                    d[col] = {} if col != "wallet_transactions" else []
        # Normalise boolean from PostgreSQL (returns Python bool)
        if "email_verified" in d:
            d["email_verified"] = bool(d["email_verified"])
        # Decrypt PII columns
        for col in _PII_COLS:
            if col in d and isinstance(d[col], str):
                d[col] = decrypt_pii(d[col]) or d[col]
        return d

    # ── Auth ──────────────────────────────────────────────────────────────────

    def register(
        self,
        email: str,
        password: str,
        name: str = "",
        user_type: str = "general",
        region: str = "India",
        currency: str = "INR",
    ) -> dict:
        """
        Create a new user account.

        Returns::
            {"success": True,  "user_id": str, "verification_token": str, "wallet_balance_cents": 0}
            {"success": False, "error": "email_taken"}

        No credits are issued until email is verified.
        """
        user_id = str(uuid.uuid4())
        token   = str(uuid.uuid4())
        expires = datetime.utcnow() + timedelta(hours=24)
        now     = datetime.utcnow()

        try:
            with _get_conn() as conn:
                with _cursor(conn) as cur:
                    cur.execute(
                        """
                        INSERT INTO users (
                            id, email, name, password_hash,
                            email_verified, verification_token, verification_token_expires,
                            wallet_balance_cents, wallet_transactions,
                            user_type, region, currency,
                            session_id, created_at, updated_at
                        ) VALUES (
                            %s, %s, %s, %s,
                            FALSE, %s, %s,
                            0, '[]',
                            %s, %s, %s,
                            %s, %s, %s
                        )
                        """,
                        (
                            user_id,
                            email.lower().strip(),
                            encrypt_pii(name),
                            _hash_password(password),
                            token,
                            expires,
                            user_type or "general",
                            region,
                            currency,
                            str(uuid.uuid4()),
                            now,
                            now,
                        ),
                    )
                conn.commit()
            return {
                "success": True,
                "user_id": user_id,
                "verification_token": token,
                "wallet_balance_cents": 0,
            }
        except psycopg2.errors.UniqueViolation:
            return {"success": False, "error": "email_taken"}
        except psycopg2.IntegrityError:
            return {"success": False, "error": "email_taken"}

    def login(self, email: str, password: str) -> dict:
        """
        Validate credentials and return the user profile.

        Implements account lockout: 5 consecutive failures lock the account
        for 15 minutes.  The failure counter resets on a successful login.

        Returns::
            {"success": True,  "profile": dict}
            {"success": False, "error": "invalid_credentials" | "account_locked"}
        """
        from datetime import datetime, timezone as _tz

        key = email.lower().strip()
        with _get_conn() as conn:
            with _cursor(conn) as cur:
                cur.execute(
                    "SELECT * FROM users WHERE email = %s FOR UPDATE",
                    (key,),
                )
                row = cur.fetchone()

            if not row:
                # Unknown email — return generic error (no lockout tracking needed)
                return {"success": False, "error": "invalid_credentials"}

            # Check lockout
            locked_until = row.get("locked_until")
            now_utc = datetime.now(tz=_tz.utc)
            if locked_until:
                if isinstance(locked_until, str):
                    from dateutil.parser import parse as _parse
                    locked_until = _parse(locked_until)
                if locked_until.tzinfo is None:
                    locked_until = locked_until.replace(tzinfo=_tz.utc)
                if now_utc < locked_until:
                    remaining = int((locked_until - now_utc).total_seconds() // 60) + 1
                    return {"success": False, "error": "account_locked",
                            "retry_after_minutes": remaining}

            # Validate password
            if row["password_hash"] != _hash_password(password):
                # Increment failure counter; lock after 5 attempts
                attempts = (row.get("failed_login_attempts") or 0) + 1
                lock_ts  = None
                if attempts >= 5:
                    lock_ts  = now_utc + __import__("datetime").timedelta(minutes=15)
                    attempts = 0   # reset after locking
                with _cursor(conn) as cur:
                    cur.execute(
                        """UPDATE users
                           SET failed_login_attempts = %s,
                               locked_until          = %s,
                               last_failed_login     = NOW()
                           WHERE email = %s""",
                        (attempts, lock_ts, key),
                    )
                conn.commit()
                return {"success": False, "error": "invalid_credentials"}

            # Successful login — reset counters
            with _cursor(conn) as cur:
                cur.execute(
                    """UPDATE users
                       SET failed_login_attempts = 0,
                           locked_until          = NULL,
                           last_failed_login     = NULL
                       WHERE email = %s""",
                    (key,),
                )
            conn.commit()

        return {"success": True, "profile": self._row_to_dict(row)}

    # ── Email verification ────────────────────────────────────────────────────

    def verify_email(self, token: str) -> dict:
        """
        Validate the verification token, mark email as verified,
        and credit the region-aware welcome amount.

        Returns::
            {"success": True,  "email": str, "wallet_balance_cents": int, "region": str}
            {"success": False, "error": "invalid_token" | "already_verified" | "token_expired"}
        """
        with _get_conn() as conn:
            with _cursor(conn) as cur:
                cur.execute(
                    "SELECT * FROM users WHERE verification_token = %s",
                    (token,),
                )
                row = cur.fetchone()

            if not row:
                return {"success": False, "error": "invalid_token"}
            if row["email_verified"]:
                return {"success": False, "error": "already_verified"}

            expires = row["verification_token_expires"]
            if expires and expires.replace(tzinfo=None) < datetime.utcnow():
                return {"success": False, "error": "token_expired"}

            region        = row.get("region") or "India"
            credit_amount = _welcome_credit_for_region(region)
            txns          = self._append_txn(
                row["wallet_transactions"] or "[]",
                {
                    "type":         "credit",
                    "amount_cents": credit_amount,
                    "reason":       "welcome_verification",
                    "ts":           self._now(),
                },
            )
            new_balance = (row["wallet_balance_cents"] or 0) + credit_amount

            with _cursor(conn) as cur:
                cur.execute(
                    """
                    UPDATE users
                    SET    email_verified            = TRUE,
                           verification_token        = NULL,
                           verification_token_expires = NULL,
                           wallet_balance_cents       = %s,
                           wallet_transactions        = %s,
                           updated_at                 = NOW()
                    WHERE  email = %s
                    """,
                    (new_balance, txns, row["email"]),
                )
            conn.commit()

        return {
            "success":              True,
            "email":                row["email"],
            "wallet_balance_cents": new_balance,
            "region":               region,
        }

    def resend_verification(self, email: str) -> dict:
        """
        Issue a fresh verification token.
        Rate-limited: max 3 resends per rolling 1-hour window.

        Returns::
            {"success": True,  "token": str, "email": str, "name": str}
            {"success": False, "error": "not_found" | "already_verified" | "rate_limited"}
        """
        with _get_conn() as conn:
            with _cursor(conn) as cur:
                cur.execute(
                    "SELECT * FROM users WHERE email = %s",
                    (email.lower().strip(),),
                )
                row = cur.fetchone()

            if not row:
                return {"success": False, "error": "not_found"}
            if row["email_verified"]:
                return {"success": False, "error": "already_verified"}

            now   = datetime.utcnow()
            count = row["verification_resend_count"] or 0
            win   = row["verification_resend_window"]
            if win:
                win_dt = win.replace(tzinfo=None) if hasattr(win, "replace") else datetime.fromisoformat(str(win))
                if (now - win_dt).total_seconds() < 3600:
                    if count >= 3:
                        return {"success": False, "error": "rate_limited"}
                else:
                    count = 0   # Reset window

            new_token   = str(uuid.uuid4())
            new_expires = now + timedelta(hours=24)
            new_window  = win if (win and (now - (win.replace(tzinfo=None) if hasattr(win,"replace") else datetime.fromisoformat(str(win)))).total_seconds() < 3600) else now

            with _cursor(conn) as cur:
                cur.execute(
                    """
                    UPDATE users
                    SET    verification_token        = %s,
                           verification_token_expires = %s,
                           verification_resend_count  = %s,
                           verification_resend_window = %s,
                           updated_at                 = NOW()
                    WHERE  email = %s
                    """,
                    (new_token, new_expires, count + 1, new_window, row["email"]),
                )
            conn.commit()

        return {
            "success": True,
            "token":   new_token,
            "email":   row["email"],
            "name":    row["name"] or "",
        }

    # ── Wallet ────────────────────────────────────────────────────────────────

    def get_wallet_balance_cents(self, email: str) -> int:
        """Return the current wallet balance in minor units (paise or cents)."""
        with _get_conn() as conn:
            with _cursor(conn) as cur:
                cur.execute(
                    "SELECT wallet_balance_cents FROM users WHERE email = %s",
                    (email.lower().strip(),),
                )
                row = cur.fetchone()
        return int(row["wallet_balance_cents"] or 0) if row else 0

    # Alias kept for backward compatibility
    def get_wallet_balance(self, email: str) -> int:
        return self.get_wallet_balance_cents(email)

    def _write_ledger(
        self,
        cur,
        email: str,
        txn_type: str,
        balance_type: str,
        amount_cents: int,
        reason: str,
        paid_after: int,
        promo_after: int,
        reference_id: str = "",
    ) -> None:
        """Insert an immutable ledger row (call inside an open cursor/transaction)."""
        cur.execute(
            """
            INSERT INTO wallet_ledger
                (email, txn_type, balance_type, amount_cents, reason,
                 paid_after, promo_after, total_after, reference_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                email, txn_type, balance_type, amount_cents, reason,
                paid_after, promo_after, paid_after + promo_after, reference_id,
            ),
        )

    def debit_wallet_cents(
        self, email: str, amount_cents: int, reason: str = "", reference_id: str = ""
    ) -> tuple[bool, int]:
        """
        Atomically deduct amount_cents from the user's wallet.

        Debit order: promo_balance first, then paid_balance.
        Writes an immutable ledger entry.
        Uses SELECT ... FOR UPDATE to prevent concurrent over-spending.

        Returns:
            (True,  remaining_balance) on success
            (False, current_balance)   when balance is insufficient
        """
        email = email.lower().strip()
        with _get_conn() as conn:
            with _cursor(conn) as cur:
                cur.execute(
                    """
                    SELECT wallet_balance_cents, wallet_transactions,
                           paid_balance_cents, promo_balance_cents
                    FROM   users WHERE email = %s FOR UPDATE
                    """,
                    (email,),
                )
                row = cur.fetchone()
                if not row:
                    return False, 0

                current     = int(row["wallet_balance_cents"] or 0)
                paid_bal    = int(row["paid_balance_cents"]   or 0)
                promo_bal   = int(row["promo_balance_cents"]  or 0)

                if current < amount_cents:
                    return False, current

                # Spend promo first, then paid
                remaining   = amount_cents
                promo_used  = min(remaining, promo_bal)
                remaining  -= promo_used
                paid_used   = remaining   # whatever is left comes from paid

                new_promo   = promo_bal - promo_used
                new_paid    = paid_bal  - paid_used
                new_balance = current   - amount_cents

                balance_type = (
                    "promo" if paid_used == 0 else
                    "paid"  if promo_used == 0 else
                    "mixed"
                )

                txns = self._append_txn(
                    row["wallet_transactions"] or "[]",
                    {"type": "debit", "amount_cents": amount_cents,
                     "reason": reason, "ts": self._now()},
                )
                cur.execute(
                    """
                    UPDATE users
                    SET    wallet_balance_cents = %s,
                           wallet_transactions  = %s,
                           paid_balance_cents   = %s,
                           promo_balance_cents  = %s,
                           updated_at           = NOW()
                    WHERE  email = %s
                    """,
                    (new_balance, txns, new_paid, new_promo, email),
                )
                self._write_ledger(
                    cur, email, "debit", balance_type, amount_cents,
                    reason, new_paid, new_promo, reference_id,
                )
            conn.commit()
        return True, new_balance

    def credit_wallet_cents(
        self, email: str, amount_cents: int, reason: str = "",
        is_paid: bool = False, reference_id: str = ""
    ) -> int:
        """
        Add amount_cents to the user's wallet.

        Args:
            is_paid: True for real-money top-ups (goes to paid_balance),
                     False (default) for welcome/refund/promo credits.

        Returns the new total balance.
        """
        email = email.lower().strip()
        with _get_conn() as conn:
            with _cursor(conn) as cur:
                cur.execute(
                    """
                    SELECT wallet_balance_cents, wallet_transactions,
                           paid_balance_cents, promo_balance_cents
                    FROM   users WHERE email = %s FOR UPDATE
                    """,
                    (email,),
                )
                row = cur.fetchone()
                if not row:
                    return 0

                paid_bal    = int(row["paid_balance_cents"]   or 0)
                promo_bal   = int(row["promo_balance_cents"]  or 0)
                current     = int(row["wallet_balance_cents"] or 0)

                new_paid    = paid_bal  + (amount_cents if is_paid  else 0)
                new_promo   = promo_bal + (amount_cents if not is_paid else 0)
                new_balance = current   + amount_cents

                txns = self._append_txn(
                    row["wallet_transactions"] or "[]",
                    {"type": "credit", "amount_cents": amount_cents,
                     "reason": reason, "ts": self._now()},
                )
                cur.execute(
                    """
                    UPDATE users
                    SET    wallet_balance_cents = %s,
                           wallet_transactions  = %s,
                           paid_balance_cents   = %s,
                           promo_balance_cents  = %s,
                           updated_at           = NOW()
                    WHERE  email = %s
                    """,
                    (new_balance, txns, new_paid, new_promo, email),
                )
                txn_type     = "topup" if is_paid else "credit"
                balance_type = "paid"  if is_paid else "promo"
                self._write_ledger(
                    cur, email, txn_type, balance_type, amount_cents,
                    reason, new_paid, new_promo, reference_id,
                )
            conn.commit()
        return new_balance

    def credit_wallet_topup(
        self, email: str, amount_cents: int, reason: str = "topup", reference_id: str = ""
    ) -> int:
        """Convenience: credit a real-money top-up (goes to paid_balance)."""
        return self.credit_wallet_cents(email, amount_cents, reason=reason,
                                        is_paid=True, reference_id=reference_id)

    def get_wallet_transactions(
        self, email: str, limit: int = 50, offset: int = 0
    ) -> list[dict]:
        """
        Return wallet ledger entries for a user (newest first).
        Falls back to legacy JSON column if ledger is empty.
        """
        email = email.lower().strip()
        with _get_conn() as conn:
            with _cursor(conn) as cur:
                cur.execute(
                    """
                    SELECT txn_type, balance_type, amount_cents, reason,
                           paid_after, promo_after, total_after, reference_id, created_at
                    FROM   wallet_ledger
                    WHERE  email = %s
                    ORDER  BY created_at DESC
                    LIMIT  %s OFFSET %s
                    """,
                    (email, limit, offset),
                )
                rows = cur.fetchall()

        if rows:
            return [dict(r) for r in rows]

        # Fall back to legacy JSON column
        profile = self.get_profile(email)
        if not profile:
            return []
        try:
            legacy = json.loads(profile.get("wallet_transactions") or "[]")
            return list(reversed(legacy[-limit:]))
        except Exception:
            return []

    def get_wallet_balance_detail(self, email: str) -> dict:
        """Return paid, promo, and total wallet balances."""
        email = email.lower().strip()
        with _get_conn() as conn:
            with _cursor(conn) as cur:
                cur.execute(
                    "SELECT wallet_balance_cents, paid_balance_cents, promo_balance_cents "
                    "FROM users WHERE email = %s",
                    (email,),
                )
                row = cur.fetchone()
        if not row:
            return {"total": 0, "paid": 0, "promo": 0}
        return {
            "total": int(row["wallet_balance_cents"] or 0),
            "paid":  int(row["paid_balance_cents"]   or 0),
            "promo": int(row["promo_balance_cents"]  or 0),
        }

    def set_wallet_balance(self, email: str, balance: int) -> None:
        """
        Directly set the wallet balance (admin use only — no ledger entry).
        """
        with _get_conn() as conn:
            with _cursor(conn) as cur:
                cur.execute(
                    "UPDATE users SET wallet_balance_cents = %s, updated_at = NOW() WHERE email = %s",
                    (balance, email.lower().strip()),
                )
            conn.commit()

    # ── Profile CRUD ──────────────────────────────────────────────────────────

    def get_profile(self, email: str) -> dict | None:
        """Return the full user profile dict, or None if not found."""
        with _get_conn() as conn:
            with _cursor(conn) as cur:
                cur.execute(
                    "SELECT * FROM users WHERE email = %s",
                    (email.lower().strip(),),
                )
                row = cur.fetchone()
        return self._row_to_dict(row)

    # Maps data-dict keys → (column_name, serializer)
    _PROFILE_FIELDS: dict[str, tuple[str, Any]] = {
        "name":                  ("name",          lambda v: encrypt_pii(v or "") or ""),
        "date_of_birth":         ("date_of_birth", lambda v: encrypt_pii(v or "") or ""),
        "time_of_birth":         ("time_of_birth", lambda v: encrypt_pii(v or "") or ""),
        "place_of_birth":        ("place_of_birth",lambda v: encrypt_pii(v or "") or ""),
        "latitude":              ("latitude",              lambda v: float(v or 0)),
        "longitude":             ("longitude",             lambda v: float(v or 0)),
        "timezone_offset":       ("timezone_offset",       lambda v: float(v or 0)),
        "kundli_json":           ("kundli_json",           json.dumps),
        "predictions_json":      ("predictions_json",      json.dumps),
        "overall_theme":         ("overall_theme",         lambda v: v or ""),
        "lagna_json":            ("lagna_json",            json.dumps),
        "birth_info_json":       ("birth_info_json",       json.dumps),
        "refined_analysis":      ("refined_analysis",      lambda v: v or ""),
        "planet_knowledge_json": ("planet_knowledge_json", json.dumps),
        "children_info_json":    ("children_info_json",    json.dumps),
        "marital_status":        ("marital_status",        lambda v: v or ""),
        "preferred_language":    ("preferred_language",    lambda v: v or "English"),
        "session_id":            ("session_id",            lambda v: v or ""),
        "chat_messages_json":    ("chat_messages_json",    json.dumps),
        "region":                ("region",                lambda v: v or "India"),
        "currency":              ("currency",              lambda v: v or "INR"),
    }

    def save_profile(self, data: dict) -> dict:
        """
        Partial-update save: only the keys present in ``data`` are written.
        Columns not in ``data`` are left unchanged — prevents partial saves
        (e.g. the refine step) from wiping kundli_json.

        If the user doesn't exist yet, performs a full INSERT.
        """
        email = data.get("email", "").lower().strip()
        if not email:
            return {"success": False, "error": "email_required"}

        with _get_conn() as conn:
            with _cursor(conn) as cur:
                cur.execute(
                    "SELECT id FROM users WHERE email = %s", (email,)
                )
                existing = cur.fetchone()

            if existing:
                # Build UPDATE with only the fields present in data
                set_parts: list[str] = ["updated_at = NOW()"]
                values: list        = []
                for key, (col, serialize) in self._PROFILE_FIELDS.items():
                    if key in data:
                        set_parts.append(f"{col} = %s")
                        values.append(serialize(data[key]))
                values.append(email)
                with _cursor(conn) as cur:
                    cur.execute(
                        f"UPDATE users SET {', '.join(set_parts)} WHERE email = %s",
                        values,
                    )
            else:
                uid = str(uuid.uuid4())
                with _cursor(conn) as cur:
                    cur.execute(
                        """
                        INSERT INTO users (
                            id, email, name,
                            date_of_birth, time_of_birth, place_of_birth,
                            latitude, longitude, timezone_offset,
                            kundli_json, predictions_json, overall_theme,
                            lagna_json, birth_info_json, refined_analysis,
                            planet_knowledge_json, children_info_json,
                            marital_status, preferred_language,
                            wallet_balance_cents, wallet_transactions,
                            session_id, chat_messages_json,
                            region, currency,
                            created_at, updated_at
                        ) VALUES (
                            %s, %s, %s,
                            %s, %s, %s,
                            %s, %s, %s,
                            %s, %s, %s,
                            %s, %s, %s,
                            %s, %s,
                            %s, %s,
                            0, '[]',
                            %s, '[]',
                            %s, %s,
                            NOW(), NOW()
                        )
                        """,
                        (
                            uid, email,
                            encrypt_pii(data.get("name", "")),
                            encrypt_pii(data.get("date_of_birth", "")),
                            encrypt_pii(data.get("time_of_birth", "")),
                            encrypt_pii(data.get("place_of_birth", "")),
                            float(data.get("latitude") or 0),
                            float(data.get("longitude") or 0),
                            float(data.get("timezone_offset") or 0),
                            json.dumps(data.get("kundli_json", {})),
                            json.dumps(data.get("predictions_json", {})),
                            data.get("overall_theme", ""),
                            json.dumps(data.get("lagna_json", {})),
                            json.dumps(data.get("birth_info_json", {})),
                            data.get("refined_analysis", ""),
                            json.dumps(data.get("planet_knowledge_json", {})),
                            json.dumps(data.get("children_info_json", {})),
                            data.get("marital_status", ""),
                            data.get("preferred_language", "English"),
                            data.get("session_id", ""),
                            data.get("region", "India"),
                            data.get("currency", "INR"),
                        ),
                    )
            conn.commit()
        return {"success": True}

    # ── Reading History ───────────────────────────────────────────────────────

    def save_reading_to_history(self, email: str, reading: dict) -> str:
        """
        Archive a completed reading session.
        Returns the new history record id.
        """
        rid  = str(uuid.uuid4())
        chat = reading.get("chat_messages_json", [])
        with _get_conn() as conn:
            with _cursor(conn) as cur:
                cur.execute(
                    """
                    INSERT INTO reading_history (
                        id, email, name,
                        date_of_birth, time_of_birth, place_of_birth,
                        overall_theme, refined_analysis,
                        chat_messages_json, planet_knowledge_json,
                        session_id, created_at
                    ) VALUES (
                        %s, %s, %s,
                        %s, %s, %s,
                        %s, %s,
                        %s, %s,
                        %s, NOW()
                    )
                    """,
                    (
                        rid,
                        email.lower().strip(),
                        encrypt_pii(reading.get("name", "")),
                        encrypt_pii(reading.get("date_of_birth", "")),
                        encrypt_pii(reading.get("time_of_birth", "")),
                        encrypt_pii(reading.get("place_of_birth", "")),
                        reading.get("overall_theme", ""),
                        reading.get("refined_analysis", ""),
                        json.dumps(chat if isinstance(chat, list) else []),
                        json.dumps(reading.get("planet_knowledge_json", {})),
                        reading.get("session_id", ""),
                    ),
                )
            conn.commit()
        return rid

    def get_reading_history(self, email: str) -> list[dict]:
        """Return summary list of past readings (no full text)."""
        with _get_conn() as conn:
            with _cursor(conn) as cur:
                cur.execute(
                    """
                    SELECT id, name, date_of_birth, time_of_birth, place_of_birth,
                           overall_theme, created_at,
                           LEFT(refined_analysis, 300) AS preview
                    FROM   reading_history
                    WHERE  email = %s
                    ORDER  BY created_at DESC
                    """,
                    (email.lower().strip(),),
                )
                rows = cur.fetchall()
        return [dict(r) for r in rows]

    def get_reading_by_id(self, reading_id: str, email: str) -> dict | None:
        """Return full reading data by id (must belong to email)."""
        with _get_conn() as conn:
            with _cursor(conn) as cur:
                cur.execute(
                    "SELECT * FROM reading_history WHERE id = %s AND email = %s",
                    (reading_id, email.lower().strip()),
                )
                row = cur.fetchone()
        if not row:
            return None
        d = dict(row)
        for col in ("chat_messages_json", "planet_knowledge_json"):
            if col in d and isinstance(d[col], str):
                try:
                    d[col] = json.loads(d[col])
                except Exception:
                    d[col] = [] if "messages" in col else {}
        return d

    # ── User management ───────────────────────────────────────────────────────

    def delete_user(self, email: str) -> bool:
        """Delete a user account. Returns True if a row was deleted."""
        with _get_conn() as conn:
            with _cursor(conn) as cur:
                cur.execute(
                    "DELETE FROM users WHERE email = %s",
                    (email.lower().strip(),),
                )
                deleted = cur.rowcount > 0
            conn.commit()
        return deleted

    # ── MFA helpers ───────────────────────────────────────────────────────────

    def get_mfa_data(self, email: str) -> dict | None:
        """Return mfa_enabled, mfa_secret, mfa_backup_codes for a user."""
        with _get_conn() as conn:
            with _cursor(conn) as cur:
                cur.execute(
                    "SELECT mfa_enabled, mfa_secret, mfa_backup_codes "
                    "FROM users WHERE email = %s",
                    (email.lower().strip(),),
                )
                row = cur.fetchone()
        if not row:
            return None
        return {
            "mfa_enabled":     bool(row["mfa_enabled"]),
            "mfa_secret":      row.get("mfa_secret"),
            "mfa_backup_codes": json.loads(row["mfa_backup_codes"] or "[]"),
        }

    def enable_mfa(self, email: str, secret: str, hashed_backup_codes: list[str]) -> None:
        """Persist MFA secret and backup codes, mark mfa_enabled=True."""
        with _get_conn() as conn:
            with _cursor(conn) as cur:
                cur.execute(
                    "UPDATE users SET mfa_enabled=%s, mfa_secret=%s, "
                    "mfa_backup_codes=%s, updated_at=NOW() WHERE email=%s",
                    (True, secret, json.dumps(hashed_backup_codes),
                     email.lower().strip()),
                )
            conn.commit()

    def disable_mfa(self, email: str) -> None:
        """Remove MFA configuration for the user."""
        with _get_conn() as conn:
            with _cursor(conn) as cur:
                cur.execute(
                    "UPDATE users SET mfa_enabled=FALSE, mfa_secret=NULL, "
                    "mfa_backup_codes=NULL, updated_at=NOW() WHERE email=%s",
                    (email.lower().strip(),),
                )
            conn.commit()

    def consume_mfa_backup_code(self, email: str, idx: int) -> None:
        """Remove a used backup code (by index) so it cannot be reused."""
        data = self.get_mfa_data(email)
        if not data:
            return
        codes = data["mfa_backup_codes"]
        if 0 <= idx < len(codes):
            codes.pop(idx)
        with _get_conn() as conn:
            with _cursor(conn) as cur:
                cur.execute(
                    "UPDATE users SET mfa_backup_codes=%s, updated_at=NOW() WHERE email=%s",
                    (json.dumps(codes), email.lower().strip()),
                )
            conn.commit()

    def get_all_users(
        self, search: str = "", limit: int = 200, offset: int = 0
    ) -> list[dict]:
        """Return all users, optionally filtered by email/name search."""
        with _get_conn() as conn:
            with _cursor(conn) as cur:
                if search:
                    cur.execute(
                        "SELECT * FROM users WHERE email ILIKE %s OR name ILIKE %s "
                        "ORDER BY created_at DESC LIMIT %s OFFSET %s",
                        (f"%{search}%", f"%{search}%", limit, offset),
                    )
                else:
                    cur.execute(
                        "SELECT * FROM users ORDER BY created_at DESC LIMIT %s OFFSET %s",
                        (limit, offset),
                    )
                rows = cur.fetchall()
        return [self._row_to_dict(r) for r in rows]

    def get_stats(self) -> dict:
        """Return aggregated admin statistics."""
        today = datetime.utcnow().date().isoformat()
        with _get_conn() as conn:
            with _cursor(conn) as cur:
                cur.execute("SELECT COUNT(*) AS n FROM users")
                total = cur.fetchone()["n"]

                cur.execute("SELECT COUNT(*) AS n FROM users WHERE email_verified = TRUE")
                verified = cur.fetchone()["n"]

                cur.execute(
                    "SELECT COUNT(*) AS n FROM users "
                    "WHERE session_id != '' AND updated_at::date = %s::date",
                    (today,),
                )
                today_r = cur.fetchone()["n"]

                cur.execute("SELECT COALESCE(SUM(wallet_balance_cents), 0) AS s FROM users")
                credits = cur.fetchone()["s"]

        return {
            "total_users":         total,
            "verified_users":      verified,
            "unverified_users":    total - verified,
            "readings_today":      today_r,
            "total_balance_cents": credits,
        }

    def force_verify_email(self, email: str) -> bool:
        """
        Admin: force-verify a user without a token.
        Credits the region-aware welcome amount if not already verified.
        """
        with _get_conn() as conn:
            with _cursor(conn) as cur:
                cur.execute(
                    "SELECT wallet_balance_cents, wallet_transactions, "
                    "       email_verified, region "
                    "FROM users WHERE email = %s FOR UPDATE",
                    (email.lower().strip(),),
                )
                row = cur.fetchone()
            if not row:
                return False
            if row["email_verified"]:
                return True   # Already done

            region        = row.get("region") or "India"
            credit_amount = _welcome_credit_for_region(region)
            txns          = self._append_txn(
                row["wallet_transactions"] or "[]",
                {"type": "credit", "amount_cents": credit_amount,
                 "reason": "welcome_verification", "ts": self._now()},
            )
            new_balance = (row["wallet_balance_cents"] or 0) + credit_amount

            with _cursor(conn) as cur:
                cur.execute(
                    """
                    UPDATE users
                    SET    email_verified             = TRUE,
                           verification_token         = NULL,
                           verification_token_expires = NULL,
                           wallet_balance_cents        = %s,
                           wallet_transactions         = %s,
                           updated_at                  = NOW()
                    WHERE  email = %s
                    """,
                    (new_balance, txns, email.lower().strip()),
                )
            conn.commit()
        return True

    # ── Admin SQL query ───────────────────────────────────────────────────────

    def run_query(self, sql: str) -> list[dict]:
        """
        Execute a read-only SQL query and return results as a list of dicts.
        Only SELECT statements are permitted — DML and DDL are blocked.
        """
        stripped = sql.strip().upper()
        if not stripped.startswith("SELECT"):
            raise ValueError("Only SELECT queries are permitted.")
        blocked = ("INSERT", "UPDATE", "DELETE", "DROP", "ALTER",
                   "TRUNCATE", "CREATE", "GRANT", "REVOKE")
        for kw in blocked:
            if f" {kw} " in f" {stripped} ":
                raise ValueError(f"Keyword '{kw}' is not permitted.")

        with _get_conn() as conn:
            with _cursor(conn) as cur:
                cur.execute(sql)
                rows = cur.fetchall()
        return [dict(r) for r in rows]

    # ── Backward-compatibility aliases ────────────────────────────────────────

    def init(self) -> None:
        """Idempotent re-initialisation (no-op — schema created in __init__)."""
        init_schema()

    def lookup(self, email: str) -> dict | None:
        """Alias for get_profile()."""
        return self.get_profile(email)

    def list_users(self, limit: int = 500) -> list[dict]:
        """Alias for get_all_users()."""
        return self.get_all_users(limit=limit)

    def delete(self, email: str) -> bool:
        """Alias for delete_user()."""
        return self.delete_user(email)

    def has_predictions(self, email: str) -> bool:
        """Return True if the user has a stored predictions record."""
        profile = self.get_profile(email)
        if not profile:
            return False
        p = profile.get("predictions_json", {})
        return bool(p)

    def save_or_update(
        self,
        email: str,
        name: str = "",
        date_of_birth: str = "",
        time_of_birth: str = "",
        place_of_birth: str = "",
        latitude: float = 0.0,
        longitude: float = 0.0,
        timezone_offset: float = 0.0,
        kundli: dict | None = None,
        predictions: list | None = None,
        overall_theme: str = "",
        lagna: dict | None = None,
        birth_info: dict | None = None,
        marital_status: str = "",
        session_id: str = "",
        preferred_language: str = "English",
    ) -> str:
        """Legacy save method — maps to save_profile()."""
        data: dict = {
            "email": email, "name": name,
            "date_of_birth": date_of_birth, "time_of_birth": time_of_birth,
            "place_of_birth": place_of_birth,
            "latitude": latitude, "longitude": longitude,
            "timezone_offset": timezone_offset,
            "kundli_json": kundli or {},
            "predictions_json": predictions if predictions else [],
            "overall_theme": overall_theme,
            "lagna_json": lagna or {},
            "birth_info_json": birth_info or {},
            "marital_status": marital_status,
            "preferred_language": preferred_language,
            "session_id": session_id,
        }
        with _get_conn() as conn:
            with _cursor(conn) as cur:
                cur.execute(
                    "SELECT id FROM users WHERE email = %s",
                    (email.lower().strip(),),
                )
                existing = cur.fetchone()

        uid = existing["id"] if existing else str(uuid.uuid4())
        self.save_profile(data)
        return uid

    def update_refined(
        self,
        email: str,
        refined_analysis: str = "",
        planet_knowledge: dict | None = None,
        session_id: str = "",
    ) -> None:
        """Update refined analysis and planet knowledge for a user."""
        with _get_conn() as conn:
            with _cursor(conn) as cur:
                cur.execute(
                    """
                    UPDATE users
                    SET    refined_analysis      = %s,
                           planet_knowledge_json = %s,
                           session_id            = COALESCE(NULLIF(%s, ''), session_id),
                           updated_at            = NOW()
                    WHERE  email = %s
                    """,
                    (
                        refined_analysis,
                        json.dumps(planet_knowledge or {}),
                        session_id,
                        email.lower().strip(),
                    ),
                )
            conn.commit()

    # ── Password reset ────────────────────────────────────────────────────────

    def create_password_reset_token(self, email: str) -> dict:
        """
        Issue a one-time password reset token valid for 1 hour.

        Returns:
            {"success": True,  "token": str, "name": str}
            {"success": False, "error": "not_found"}
        """
        with _get_conn() as conn:
            with _cursor(conn) as cur:
                cur.execute(
                    "SELECT id, name FROM users WHERE email = %s",
                    (email.lower().strip(),),
                )
                row = cur.fetchone()
            if not row:
                return {"success": False, "error": "not_found"}

            token   = str(uuid.uuid4())
            expires = datetime.utcnow() + timedelta(hours=1)
            with _cursor(conn) as cur:
                cur.execute(
                    """UPDATE users
                       SET    verification_token         = %s,
                              verification_token_expires  = %s,
                              updated_at                  = NOW()
                       WHERE  email = %s""",
                    (f"reset:{token}", expires, email.lower().strip()),
                )
            conn.commit()
        return {"success": True, "token": token, "name": row["name"] or ""}

    def reset_password(self, token: str, new_password: str) -> dict:
        """
        Consume a password-reset token and set a new password.

        Returns:
            {"success": True,  "email": str}
            {"success": False, "error": "invalid_token" | "token_expired"}
        """
        if len(new_password) < 6:
            return {"success": False, "error": "password_too_short"}
        lookup = f"reset:{token}"
        with _get_conn() as conn:
            with _cursor(conn) as cur:
                cur.execute(
                    "SELECT email, verification_token_expires FROM users "
                    "WHERE verification_token = %s FOR UPDATE",
                    (lookup,),
                )
                row = cur.fetchone()
                if not row:
                    return {"success": False, "error": "invalid_token"}
                expires = row["verification_token_expires"]
                if expires and datetime.utcnow() > (
                    expires.replace(tzinfo=None) if hasattr(expires, "tzinfo") else expires
                ):
                    return {"success": False, "error": "token_expired"}
                cur.execute(
                    """UPDATE users
                       SET password_hash = %s,
                           verification_token = NULL,
                           verification_token_expires = NULL,
                           updated_at = NOW()
                       WHERE email = %s""",
                    (_hash_password(new_password), row["email"]),
                )
            conn.commit()
        return {"success": True, "email": row["email"]}

    # ── Shared Readings ───────────────────────────────────────────────────────

    @staticmethod
    def _hash_pin(pin: str) -> str:
        """SHA-256 hash of a 4-digit PIN."""
        return hashlib.sha256(pin.encode()).hexdigest()

    def create_shared_reading(
        self,
        email: str,
        pin: str,
        content: dict,
        session_id: str = "",
        ttl_hours: int = 72,
    ) -> dict:
        """
        Create a PIN-protected shareable reading snapshot.

        Returns:
            {"success": True, "token": str, "expires_at": str, "ttl_hours": int}
        """
        if not pin.isdigit() or len(pin) != 4:
            return {"success": False, "error": "PIN must be exactly 4 digits."}

        token      = str(uuid.uuid4()).replace("-", "")
        pin_hash   = self._hash_pin(pin)
        expires_at = datetime.utcnow() + timedelta(hours=ttl_hours)

        with _get_conn() as conn:
            with _cursor(conn) as cur:
                cur.execute(
                    """
                    INSERT INTO shared_readings
                        (id, email, pin_hash, session_id, name, date_of_birth,
                         time_of_birth, place_of_birth, overall_theme,
                         refined_analysis, lagna_info_json, expires_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        token,
                        email.lower().strip(),
                        pin_hash,
                        session_id,
                        content.get("name", ""),
                        content.get("date_of_birth", ""),
                        content.get("time_of_birth", ""),
                        content.get("place_of_birth", ""),
                        content.get("overall_theme", ""),
                        content.get("refined_analysis", ""),
                        json.dumps(content.get("lagna_info", {})),
                        expires_at,
                    ),
                )
            conn.commit()
        return {
            "success":    True,
            "token":      token,
            "expires_at": expires_at.isoformat(),
            "ttl_hours":  ttl_hours,
        }

    def get_shared_reading(self, token: str) -> dict | None:
        """Return shared reading metadata (without full content)."""
        with _get_conn() as conn:
            with _cursor(conn) as cur:
                cur.execute(
                    "SELECT * FROM shared_readings WHERE id=%s AND expires_at > NOW()",
                    (token,),
                )
                row = cur.fetchone()
        if not row:
            return None
        d = dict(row)
        # Decrypt PII
        for col in ("name", "date_of_birth", "time_of_birth", "place_of_birth"):
            if col in d and isinstance(d[col], str):
                d[col] = decrypt_pii(d[col]) or d[col]
        try:
            d["lagna_info"] = json.loads(d.get("lagna_info_json") or "{}")
        except Exception:
            d["lagna_info"] = {}
        return d

    def access_shared_reading(self, token: str, pin: str) -> dict | None:
        """
        Verify PIN and return the full reading content.
        Increments view_count on success.
        """
        with _get_conn() as conn:
            with _cursor(conn) as cur:
                cur.execute(
                    "SELECT * FROM shared_readings WHERE id=%s AND expires_at > NOW()",
                    (token,),
                )
                row = cur.fetchone()
            if not row:
                return None
            pin_hash = self._hash_pin(pin)
            if not secrets.compare_digest(pin_hash, row["pin_hash"]):
                return None
            with _cursor(conn) as cur:
                cur.execute(
                    "UPDATE shared_readings SET view_count = view_count + 1 WHERE id=%s",
                    (token,),
                )
            conn.commit()
        d = dict(row)
        for col in ("name", "date_of_birth", "time_of_birth", "place_of_birth"):
            if col in d and isinstance(d[col], str):
                d[col] = decrypt_pii(d[col]) or d[col]
        try:
            d["lagna_info"] = json.loads(d.get("lagna_info_json") or "{}")
        except Exception:
            d["lagna_info"] = {}
        return d

    def delete_shared_reading(self, token: str, email: str) -> bool:
        """Delete a shared reading. Only the owner (matching email) can delete."""
        with _get_conn() as conn:
            with _cursor(conn) as cur:
                cur.execute(
                    "DELETE FROM shared_readings WHERE id=%s AND email=%s",
                    (token, email.lower().strip()),
                )
                deleted = cur.rowcount > 0
            conn.commit()
        return deleted

    def get_admin_stats(self) -> dict:
        """Return aggregate stats for the admin dashboard."""
        with _get_conn() as conn:
            with _cursor(conn) as cur:
                cur.execute("SELECT COUNT(*) AS total_users FROM users")
                total_users = (cur.fetchone() or {}).get("total_users", 0)
                cur.execute("SELECT COUNT(*) AS total_users FROM users WHERE email_verified=TRUE")
                verified = (cur.fetchone() or {}).get("total_users", 0)
                cur.execute("SELECT COALESCE(SUM(wallet_balance_cents),0) AS total FROM users")
                total_wallet = (cur.fetchone() or {}).get("total", 0)
                cur.execute("SELECT COUNT(*) AS cnt FROM reading_history")
                readings = (cur.fetchone() or {}).get("cnt", 0)
                cur.execute(
                    "SELECT COUNT(*) AS cnt FROM users WHERE created_at > NOW() - INTERVAL '24 hours'"
                )
                new_today = (cur.fetchone() or {}).get("cnt", 0)
        return {
            "total_users":        total_users,
            "verified_users":     verified,
            "total_wallet_cents": total_wallet,
            "total_readings":     readings,
            "new_users_today":    new_today,
        }

    def list_all_users(self, limit: int = 500) -> list[dict]:
        """Return all users for admin panel display."""
        return self.get_all_users(limit=limit)

    def run_raw_query(self, query: str) -> list[dict]:
        """Execute an arbitrary SELECT query (admin only). Returns rows as dicts."""
        # Safety: only allow SELECT
        q = query.strip().upper()
        if not q.startswith("SELECT"):
            raise ValueError("Only SELECT queries are permitted via this endpoint.")
        with _get_conn() as conn:
            with _cursor(conn) as cur:
                cur.execute(query)
                rows = cur.fetchall()
        return [dict(r) for r in rows]

    def force_verify_email(self, email: str) -> bool:
        """Force-verify a user's email (admin action)."""
        with _get_conn() as conn:
            with _cursor(conn) as cur:
                cur.execute(
                    "UPDATE users SET email_verified=TRUE, updated_at=NOW() WHERE email=%s",
                    (email.lower().strip(),),
                )
                updated = cur.rowcount > 0
            conn.commit()
        return updated

    def get_analytics_metrics(self) -> dict:
        """
        Rich analytics metrics for the admin dashboard.
        Returns DAU, MAU, revenue, feature usage, and registration trends.
        """
        with _get_conn() as conn:
            with _cursor(conn) as cur:
                # Daily active users (logged in within last 24h via updated_at)
                cur.execute(
                    "SELECT COUNT(*) AS cnt FROM users "
                    "WHERE updated_at > NOW() - INTERVAL '24 hours'"
                )
                dau = (cur.fetchone() or {}).get("cnt", 0)

                # Monthly active users
                cur.execute(
                    "SELECT COUNT(*) AS cnt FROM users "
                    "WHERE updated_at > NOW() - INTERVAL '30 days'"
                )
                mau = (cur.fetchone() or {}).get("cnt", 0)

                # Total revenue (sum of paid_balance_cents debited via readings)
                cur.execute(
                    "SELECT COALESCE(SUM(amount_cents),0) AS rev FROM wallet_ledger "
                    "WHERE txn_type='debit' AND created_at > NOW() - INTERVAL '30 days'"
                )
                revenue_30d = (cur.fetchone() or {}).get("rev", 0)

                # Registrations per day for last 7 days
                cur.execute(
                    "SELECT DATE(created_at) AS day, COUNT(*) AS cnt FROM users "
                    "WHERE created_at > NOW() - INTERVAL '7 days' "
                    "GROUP BY day ORDER BY day"
                )
                reg_trend = [{"day": str(r["day"]), "count": r["cnt"]}
                             for r in cur.fetchall()]

                # Top 10 users by wallet balance
                cur.execute(
                    "SELECT email, wallet_balance_cents, region FROM users "
                    "ORDER BY wallet_balance_cents DESC LIMIT 10"
                )
                top_users = [dict(r) for r in cur.fetchall()]

                # Reading history counts per day (last 7 days)
                cur.execute(
                    "SELECT DATE(created_at) AS day, COUNT(*) AS cnt FROM reading_history "
                    "WHERE created_at > NOW() - INTERVAL '7 days' "
                    "GROUP BY day ORDER BY day"
                )
                reading_trend = [{"day": str(r["day"]), "count": r["cnt"]}
                                 for r in cur.fetchall()]

                # MFA adoption
                cur.execute(
                    "SELECT COUNT(*) AS cnt FROM users WHERE mfa_enabled=TRUE"
                )
                mfa_count = (cur.fetchone() or {}).get("cnt", 0)

        return {
            "dau":             dau,
            "mau":             mau,
            "revenue_30d_cents": revenue_30d,
            "registration_trend_7d": reg_trend,
            "reading_trend_7d":      reading_trend,
            "top_users_by_balance":  top_users,
            "mfa_enabled_count":     mfa_count,
        }

    # ── Kundli Profiles (multi-profile support) ───────────────────────────────

    def create_kundli_profile(self, email: str, data: dict) -> dict:
        """
        Create a new kundli profile for the given user.
        If this is the first profile for the user, automatically sets is_active=True.
        Returns the created profile as a dict.
        """
        import uuid as _uuid
        profile_id = str(_uuid.uuid4())
        email = email.strip().lower()
        label  = (data.get("label") or "").strip() or "Profile"
        name   = encrypt_pii(data.get("name", ""))
        dob    = encrypt_pii(data.get("date_of_birth", ""))
        tob    = encrypt_pii(data.get("time_of_birth", ""))
        pob    = encrypt_pii(data.get("place_of_birth", ""))
        lat    = float(data.get("latitude", 0.0) or 0.0)
        lon    = float(data.get("longitude", 0.0) or 0.0)
        tz     = float(data.get("timezone_offset", 0.0) or 0.0)
        gender = (data.get("gender") or "").strip() or None   # M / F / Other / None
        kundli_json = json.dumps(data.get("kundli_json") or data.get("kundli_data") or {})
        refined     = data.get("refined_analysis", "")
        pk_json     = json.dumps(data.get("planet_knowledge_json") or {})

        with _get_conn() as conn:
            with _cursor(conn) as cur:
                # Check if user already has profiles
                cur.execute(
                    "SELECT COUNT(*) AS cnt FROM kundli_profiles WHERE user_email = %s",
                    (email,)
                )
                count = (cur.fetchone() or {}).get("cnt", 0)
                is_active = (count == 0)  # first profile is auto-active

                if is_active:
                    # Deactivate all others (safety)
                    cur.execute(
                        "UPDATE kundli_profiles SET is_active = FALSE WHERE user_email = %s",
                        (email,)
                    )

                cur.execute(
                    """INSERT INTO kundli_profiles
                       (id, user_email, label, name, date_of_birth, time_of_birth,
                        place_of_birth, latitude, longitude, timezone_offset,
                        gender, is_active, kundli_json, refined_analysis, planet_knowledge_json)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                       RETURNING *""",
                    (profile_id, email, label, name, dob, tob, pob,
                     lat, lon, tz, gender, is_active, kundli_json, refined, pk_json)
                )
                row = cur.fetchone() or {}
            conn.commit()
        return self._profile_row_to_dict(row)

    def list_kundli_profiles(self, email: str) -> list:
        """Return all kundli profiles for a user, ordered by creation time."""
        email = email.strip().lower()
        with _get_conn() as conn:
            with _cursor(conn) as cur:
                cur.execute(
                    "SELECT * FROM kundli_profiles WHERE user_email = %s ORDER BY created_at ASC",
                    (email,)
                )
                rows = cur.fetchall() or []
        return [self._profile_row_to_dict(r) for r in rows]

    def get_kundli_profile(self, profile_id: str, email: str) -> dict | None:
        """Fetch a single kundli profile by id, scoped to the owning email."""
        email = email.strip().lower()
        with _get_conn() as conn:
            with _cursor(conn) as cur:
                cur.execute(
                    "SELECT * FROM kundli_profiles WHERE id = %s AND user_email = %s",
                    (profile_id, email)
                )
                row = cur.fetchone()
        return self._profile_row_to_dict(row) if row else None

    def get_active_kundli_profile(self, email: str) -> dict | None:
        """Return the currently active kundli profile for the user, or None."""
        email = email.strip().lower()
        with _get_conn() as conn:
            with _cursor(conn) as cur:
                cur.execute(
                    "SELECT * FROM kundli_profiles WHERE user_email = %s AND is_active = TRUE LIMIT 1",
                    (email,)
                )
                row = cur.fetchone()
        return self._profile_row_to_dict(row) if row else None

    def update_kundli_profile(self, profile_id: str, email: str, data: dict) -> dict | None:
        """
        Update mutable fields of a kundli profile.
        Only fields present in `data` are changed; omitted fields are left as-is.
        Returns updated profile dict or None if not found.
        """
        email = email.strip().lower()

        allowed = {
            "label", "name", "date_of_birth", "time_of_birth",
            "place_of_birth", "latitude", "longitude", "timezone_offset",
            "gender", "kundli_json", "refined_analysis", "planet_knowledge_json",
        }
        pii_cols = {"name", "date_of_birth", "time_of_birth", "place_of_birth"}
        json_cols = {"kundli_json", "planet_knowledge_json"}

        sets, vals = [], []
        for col in allowed:
            if col not in data:
                continue
            val = data[col]
            if col in pii_cols:
                val = encrypt_pii(str(val or ""))
            elif col in json_cols:
                val = json.dumps(val) if not isinstance(val, str) else val
            sets.append(f"{col} = %s")
            vals.append(val)

        if not sets:
            return self.get_kundli_profile(profile_id, email)

        sets.append("updated_at = NOW()")
        vals.extend([profile_id, email])

        with _get_conn() as conn:
            with _cursor(conn) as cur:
                cur.execute(
                    f"UPDATE kundli_profiles SET {', '.join(sets)} "
                    f"WHERE id = %s AND user_email = %s RETURNING *",
                    vals
                )
                row = cur.fetchone()
            conn.commit()
        return self._profile_row_to_dict(row) if row else None

    def set_active_kundli_profile(self, profile_id: str, email: str) -> bool:
        """
        Mark `profile_id` as active and deactivate all other profiles for the user.
        Returns True if the profile was found and updated.
        """
        email = email.strip().lower()
        with _get_conn() as conn:
            with _cursor(conn) as cur:
                # Deactivate all
                cur.execute(
                    "UPDATE kundli_profiles SET is_active = FALSE WHERE user_email = %s",
                    (email,)
                )
                # Activate target
                cur.execute(
                    "UPDATE kundli_profiles SET is_active = TRUE, updated_at = NOW() "
                    "WHERE id = %s AND user_email = %s",
                    (profile_id, email)
                )
                updated = cur.rowcount
            conn.commit()
        return updated > 0

    def delete_kundli_profile(self, profile_id: str, email: str) -> bool:
        """
        Delete a kundli profile. If it was active, activates the most-recently-updated
        remaining profile automatically.
        Returns True if a row was deleted.
        """
        email = email.strip().lower()
        with _get_conn() as conn:
            with _cursor(conn) as cur:
                # Check if it was active
                cur.execute(
                    "SELECT is_active FROM kundli_profiles WHERE id = %s AND user_email = %s",
                    (profile_id, email)
                )
                existing = cur.fetchone()
                if not existing:
                    return False
                was_active = existing.get("is_active", False)

                cur.execute(
                    "DELETE FROM kundli_profiles WHERE id = %s AND user_email = %s",
                    (profile_id, email)
                )
                deleted = cur.rowcount

                if deleted and was_active:
                    # Auto-activate the most recently updated remaining profile
                    cur.execute(
                        "UPDATE kundli_profiles SET is_active = TRUE "
                        "WHERE id = (SELECT id FROM kundli_profiles "
                        "            WHERE user_email = %s ORDER BY updated_at DESC LIMIT 1)",
                        (email,)
                    )
            conn.commit()
        return deleted > 0

    @staticmethod
    def _profile_row_to_dict(row: dict | None) -> dict:
        """Convert a kundli_profiles DB row to a clean API-facing dict."""
        if not row:
            return {}
        pii_cols = {"name", "date_of_birth", "time_of_birth", "place_of_birth"}
        json_cols = {"kundli_json", "planet_knowledge_json"}
        out = {}
        for k, v in row.items():
            if k in pii_cols:
                out[k] = decrypt_pii(v or "")
            elif k in json_cols:
                try:
                    out[k] = json.loads(v) if isinstance(v, str) else (v or {})
                except Exception:
                    out[k] = {}
            else:
                out[k] = v
        return out

    # ── AI Reports (persistence layer) ───────────────────────────────────────

    def save_ai_report(
        self,
        email:           str,
        session_id:      str,
        report_type:     str,
        storage_key:     str,
        storage_backend: str = "local",
        language:        str = "English",
        content_preview: str = "",
        metadata:        dict | None = None,
        expires_at:      str | None  = None,
    ) -> str:
        """
        Persist a metadata record for a generated AI report.

        Parameters
        ----------
        email            : owner email
        session_id       : kundli session ID
        report_type      : career|yearly_forecast|remedies|compatibility|dasha
        storage_key      : key returned by ReportStore.save()
        storage_backend  : "s3" or "local"
        language         : report language
        content_preview  : first ~500 chars of report text
        metadata         : arbitrary extra data (model, tokens, etc.)
        expires_at       : ISO datetime string or None

        Returns
        -------
        str — the new report record ID
        """
        import uuid as _uuid
        report_id = str(_uuid.uuid4())
        preview   = (content_preview or "")[:500]
        meta_json = json.dumps(metadata or {})

        with _get_conn() as conn:
            with _cursor(conn) as cur:
                cur.execute(
                    """INSERT INTO ai_reports
                       (id, email, session_id, report_type, storage_key,
                        storage_backend, language, status, content_preview,
                        metadata_json, expires_at)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,'completed',%s,%s,%s)""",
                    (
                        report_id, email.strip().lower(), session_id,
                        report_type, storage_key, storage_backend,
                        language, preview, meta_json,
                        expires_at,
                    ),
                )
            conn.commit()
        return report_id

    def list_ai_reports(
        self,
        email:       str,
        report_type: str = "",
        limit:       int = 50,
    ) -> list[dict]:
        """
        List AI report records for a user, newest first.

        Parameters
        ----------
        email       : user email
        report_type : optional filter (career|yearly_forecast|remedies|…)
        limit       : max rows to return

        Returns list of dicts without full content (use get_ai_report for that).
        """
        email = email.strip().lower()
        params: list = [email]
        extra  = ""
        if report_type:
            extra = "AND report_type = %s "
            params.append(report_type)
        params.append(limit)

        with _get_conn() as conn:
            with _cursor(conn) as cur:
                cur.execute(
                    f"""SELECT id, email, session_id, report_type,
                               storage_key, storage_backend, language,
                               status, content_preview, metadata_json,
                               created_at, expires_at
                        FROM ai_reports
                        WHERE email = %s {extra}
                        ORDER BY created_at DESC
                        LIMIT %s""",
                    params,
                )
                rows = cur.fetchall() or []

        out = []
        for row in rows:
            r = dict(row)
            try:
                r["metadata"] = json.loads(r.pop("metadata_json", "{}") or "{}")
            except Exception:
                r["metadata"] = {}
            out.append(r)
        return out

    def get_ai_report(self, report_id: str, email: str) -> dict | None:
        """Fetch a single AI report record by ID, scoped to the owning email."""
        email = email.strip().lower()
        with _get_conn() as conn:
            with _cursor(conn) as cur:
                cur.execute(
                    "SELECT * FROM ai_reports WHERE id = %s AND email = %s",
                    (report_id, email),
                )
                row = cur.fetchone()
        if not row:
            return None
        r = dict(row)
        try:
            r["metadata"] = json.loads(r.pop("metadata_json", "{}") or "{}")
        except Exception:
            r["metadata"] = {}
        return r

    def delete_ai_report(self, report_id: str, email: str) -> bool:
        """Delete an AI report record. Returns True if deleted."""
        email = email.strip().lower()
        with _get_conn() as conn:
            with _cursor(conn) as cur:
                cur.execute(
                    "DELETE FROM ai_reports WHERE id = %s AND email = %s",
                    (report_id, email),
                )
                deleted = cur.rowcount
            conn.commit()
        return deleted > 0

    def purge_expired_ai_reports(self) -> int:
        """Remove expired report records (called by a background task or cron)."""
        with _get_conn() as conn:
            with _cursor(conn) as cur:
                cur.execute(
                    "DELETE FROM ai_reports WHERE expires_at IS NOT NULL AND expires_at < NOW()"
                )
                deleted = cur.rowcount
            conn.commit()
        return deleted
