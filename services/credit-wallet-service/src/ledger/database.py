"""
backend/persistence/database.py
=================================
SQLite persistence layer.
Auto-migrates old schemas to add new columns.
"""
from __future__ import annotations
import hashlib
import json
import os
import sqlite3
import uuid
from datetime import datetime, timedelta
from pathlib import Path

# ── Config ────────────────────────────────────────────────────────────────────
DB_PATH = os.environ.get("DB_PATH", str(Path(__file__).parent.parent.parent / "narayan_astro.db"))

# Legacy cost constants kept for backward-compat imports.
# Actual deductions now go through payment.wallet.get_pricing(region).
WELCOME_CREDIT_CENTS = 10_000   # ₹100 India default (paise); overridden per region at runtime
REPORT_COST_CENTS    = 10_000   # ₹100 India default
CHAT_COST_CENTS      =  2_500   # ₹25  India default

# Legacy compat alias used in payment/wallet.py
FREE_CREDITS_ON_REGISTER = 0   # No free credits until email verified


def _welcome_credit_for_region(region: str) -> int:
    """Return the correct welcome credit in minor units for the given region."""
    from payment.wallet import get_pricing
    return get_pricing(region)["welcome"]

_JSON_COLS = {
    "kundli_json", "predictions_json", "lagna_json",
    "birth_info_json", "children_info_json",
    "planet_knowledge_json", "wallet_transactions",
    "chat_messages_json",
}

_conn: sqlite3.Connection | None = None


# ── Connection ────────────────────────────────────────────────────────────────

def _get_conn(db_path: str = DB_PATH) -> sqlite3.Connection:
    global _conn
    if _conn is None or _conn.execute("PRAGMA database_list").fetchone() is None:
        _conn = sqlite3.connect(db_path, check_same_thread=False)
        _conn.row_factory = sqlite3.Row
    return _conn


# ── Schema ────────────────────────────────────────────────────────────────────

_CREATE_USERS_SQL = """
CREATE TABLE IF NOT EXISTS users (
    id                          TEXT PRIMARY KEY,
    email                       TEXT UNIQUE NOT NULL,
    name                        TEXT DEFAULT '',
    password_hash               TEXT DEFAULT '',

    -- Email verification
    email_verified              INTEGER DEFAULT 0,
    verification_token          TEXT DEFAULT NULL,
    verification_token_expires  TEXT DEFAULT NULL,
    verification_resend_count   INTEGER DEFAULT 0,
    verification_resend_window  TEXT DEFAULT NULL,

    -- Kundli data (JSON columns)
    date_of_birth               TEXT DEFAULT '',
    time_of_birth               TEXT DEFAULT '',
    place_of_birth              TEXT DEFAULT '',
    latitude                    REAL DEFAULT 0.0,
    longitude                   REAL DEFAULT 0.0,
    timezone_offset             REAL DEFAULT 0.0,
    kundli_json                 TEXT DEFAULT '{}',
    predictions_json            TEXT DEFAULT '{}',
    overall_theme               TEXT DEFAULT '',
    lagna_json                  TEXT DEFAULT '{}',
    birth_info_json             TEXT DEFAULT '{}',
    refined_analysis            TEXT DEFAULT '',
    planet_knowledge_json       TEXT DEFAULT '{}',
    children_info_json          TEXT DEFAULT '{}',
    marital_status              TEXT DEFAULT '',
    user_type                   TEXT DEFAULT 'general',
    preferred_language          TEXT DEFAULT 'English',

    -- Wallet (integer cents — avoids floating-point errors)
    wallet_balance_cents        INTEGER DEFAULT 0,
    wallet_transactions         TEXT DEFAULT '[]',

    -- Session
    session_id                  TEXT DEFAULT '',
    created_at                  TEXT DEFAULT '',
    updated_at                  TEXT DEFAULT ''
);
"""

_CREATE_HISTORY_SQL = """CREATE TABLE IF NOT EXISTS reading_history (
    id                  TEXT PRIMARY KEY,
    email               TEXT NOT NULL,
    name                TEXT DEFAULT '',
    date_of_birth       TEXT DEFAULT '',
    time_of_birth       TEXT DEFAULT '',
    place_of_birth      TEXT DEFAULT '',
    overall_theme       TEXT DEFAULT '',
    refined_analysis    TEXT DEFAULT '',
    chat_messages_json  TEXT DEFAULT '[]',
    planet_knowledge_json TEXT DEFAULT '{}',
    session_id          TEXT DEFAULT '',
    created_at          TEXT DEFAULT ''
);
"""

_MIGRATE_COLS = [
    ("password_hash",               "TEXT DEFAULT ''"),
    ("preferred_language",          "TEXT DEFAULT 'English'"),
    ("email_verified",              "INTEGER DEFAULT 0"),
    ("verification_token",          "TEXT DEFAULT NULL"),
    ("verification_token_expires",  "TEXT DEFAULT NULL"),
    ("verification_resend_count",   "INTEGER DEFAULT 0"),
    ("verification_resend_window",  "TEXT DEFAULT NULL"),
    # Wallet migration: new cents column
    ("user_type",                   "TEXT DEFAULT 'general'"),
    ("wallet_balance_cents",        "INTEGER DEFAULT 0"),
    ("wallet_transactions",         "TEXT DEFAULT '[]'"),
    ("chat_messages_json",          "TEXT DEFAULT '[]'"),
    ("region",                      "TEXT DEFAULT 'India'"),
    ("currency",                    "TEXT DEFAULT 'INR'"),
]


def _migrate(conn: sqlite3.Connection) -> None:
    """Add any missing columns to existing databases."""
    existing = {row[1] for row in conn.execute("PRAGMA table_info(users)")}
    for col, typedef in _MIGRATE_COLS:
        if col not in existing:
            conn.execute(f"ALTER TABLE users ADD COLUMN {col} {typedef}")
    conn.commit()


# ── Password hashing ──────────────────────────────────────────────────────────

def _hash_password(password: str) -> str:
    salt = os.environ.get("PASSWORD_SALT", "narayan_astro_salt_2024")
    return hashlib.sha256(f"{salt}{password}".encode()).hexdigest()


# ── Database class ────────────────────────────────────────────────────────────

class Database:
    """High-level persistence layer.  Each instance uses its own SQLite connection."""

    def __init__(self, db_path: str = DB_PATH, path: str = "") -> None:
        if path and not db_path or db_path == DB_PATH:
            db_path = path or db_path
        self._path = db_path
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute(_CREATE_USERS_SQL)
        self._conn.execute(_CREATE_HISTORY_SQL)
        self._conn.commit()
        _migrate(self._conn)

    # ── Auth ──────────────────────────────────────────────────────────────────

    def register(self, email: str, password: str, name: str = "", user_type: str = "general") -> dict:
        """
        Create a new account.
        Returns {"success": True, "user_id": ..., "wallet_balance_cents": 0}
        or      {"success": False, "error": "email_taken"}.
        No credits until email is verified.
        """
        try:
            user_id = str(uuid.uuid4())
            token   = str(uuid.uuid4())
            expires = (datetime.utcnow() + timedelta(hours=24)).isoformat()
            now     = datetime.utcnow().isoformat()
            self._conn.execute(
                """INSERT INTO users
                   (id, email, name, password_hash,
                    email_verified, verification_token, verification_token_expires,
                    wallet_balance_cents, wallet_transactions,
                    user_type, session_id, created_at, updated_at)
                   VALUES (?,?,?,?,0,?,?,0,'[]',?,?,?,?)""",
                (user_id, email.lower().strip(), name,
                 _hash_password(password),
                 token, expires,
                 user_type or "general",
                 str(uuid.uuid4()), now, now),
            )
            self._conn.commit()
            return {"success": True, "user_id": user_id,
                    "verification_token": token,
                    "wallet_balance_cents": 0}
        except sqlite3.IntegrityError:
            return {"success": False, "error": "email_taken"}

    def login(self, email: str, password: str) -> dict:
        row = self._conn.execute(
            "SELECT * FROM users WHERE email=?", (email.lower().strip(),)
        ).fetchone()
        if not row or row["password_hash"] != _hash_password(password):
            return {"success": False, "error": "invalid_credentials"}
        return {"success": True, "profile": self._row_to_dict(row)}

    # ── Email verification ────────────────────────────────────────────────────

    def verify_email(self, token: str) -> dict:
        """
        Validate token, mark email verified, credit region-aware welcome amount.
        Returns {"success": True, "email": ...} or {"success": False, "error": ...}.
        """
        row = self._conn.execute(
            "SELECT * FROM users WHERE verification_token=?", (token,)
        ).fetchone()
        if not row:
            return {"success": False, "error": "invalid_token"}
        if row["email_verified"]:
            return {"success": False, "error": "already_verified"}
        expires = row["verification_token_expires"]
        if expires and datetime.fromisoformat(expires) < datetime.utcnow():
            return {"success": False, "error": "token_expired"}

        # Determine region-aware welcome credit amount
        region = row["region"] if "region" in row.keys() else "India"
        credit_amount = _welcome_credit_for_region(region or "India")

        # Credit welcome amount and mark verified
        txns = self._append_txn(
            row["wallet_transactions"] or "[]",
            {"type": "credit", "amount_cents": credit_amount,
             "reason": "welcome_verification", "ts": datetime.utcnow().isoformat()}
        )
        self._conn.execute(
            """UPDATE users SET
               email_verified=1, verification_token=NULL,
               verification_token_expires=NULL,
               wallet_balance_cents = wallet_balance_cents + ?,
               wallet_transactions=?,
               updated_at=?
               WHERE email=?""",
            (credit_amount, txns,
             datetime.utcnow().isoformat(), row["email"])
        )
        self._conn.commit()
        return {"success": True, "email": row["email"],
                "wallet_balance_cents": (row["wallet_balance_cents"] or 0) + credit_amount,
                "region": region}

    def resend_verification(self, email: str) -> dict:
        """
        Issue a new token. Rate-limited: max 3 resends per hour.
        Returns {"success": True, "token": ...} or {"success": False, "error": ...}.
        """
        row = self._conn.execute(
            "SELECT * FROM users WHERE email=?", (email.lower().strip(),)
        ).fetchone()
        if not row:
            return {"success": False, "error": "not_found"}
        if row["email_verified"]:
            return {"success": False, "error": "already_verified"}

        # Rate limit
        window_str = row["verification_resend_window"]
        count      = row["verification_resend_count"] or 0
        now        = datetime.utcnow()
        if window_str:
            window_start = datetime.fromisoformat(window_str)
            if (now - window_start).total_seconds() < 3600:
                if count >= 3:
                    return {"success": False, "error": "rate_limited"}
            else:
                count = 0  # Reset window
        new_token   = str(uuid.uuid4())
        new_expires = (now + timedelta(hours=24)).isoformat()
        self._conn.execute(
            """UPDATE users SET
               verification_token=?, verification_token_expires=?,
               verification_resend_count=?,
               verification_resend_window=?,
               updated_at=?
               WHERE email=?""",
            (new_token, new_expires, count + 1,
             window_str if (window_str and (now - datetime.fromisoformat(window_str)).total_seconds() < 3600)
             else now.isoformat(),
             now.isoformat(), row["email"])
        )
        self._conn.commit()
        return {"success": True, "token": new_token, "email": row["email"],
                "name": row["name"] or ""}

    # ── Wallet ────────────────────────────────────────────────────────────────

    def get_wallet_balance_cents(self, email: str) -> int:
        """Return balance in cents (integer)."""
        row = self._conn.execute(
            "SELECT wallet_balance_cents FROM users WHERE email=?",
            (email.lower().strip(),)
        ).fetchone()
        return int(row["wallet_balance_cents"] or 0) if row else 0

    # Legacy alias (integer credits — kept for payment/wallet.py compat)
    def get_wallet_balance(self, email: str) -> int:
        return self.get_wallet_balance_cents(email)

    def debit_wallet_cents(self, email: str, amount_cents: int, reason: str = "") -> tuple[bool, int]:
        """
        Deduct amount_cents atomically.
        Returns (success, remaining_balance_cents).
        """
        email = email.lower().strip()
        row   = self._conn.execute(
            "SELECT wallet_balance_cents, wallet_transactions FROM users WHERE email=?", (email,)
        ).fetchone()
        if not row:
            return False, 0
        current = int(row["wallet_balance_cents"] or 0)
        if current < amount_cents:
            return False, current
        txns = self._append_txn(
            row["wallet_transactions"] or "[]",
            {"type": "debit", "amount_cents": amount_cents,
             "reason": reason, "ts": datetime.utcnow().isoformat()}
        )
        new_balance = current - amount_cents
        self._conn.execute(
            "UPDATE users SET wallet_balance_cents=?, wallet_transactions=?, updated_at=? WHERE email=?",
            (new_balance, txns, datetime.utcnow().isoformat(), email)
        )
        self._conn.commit()
        return True, new_balance

    def credit_wallet_cents(self, email: str, amount_cents: int, reason: str = "") -> int:
        """Add amount_cents. Returns new balance."""
        email = email.lower().strip()
        row   = self._conn.execute(
            "SELECT wallet_balance_cents, wallet_transactions FROM users WHERE email=?", (email,)
        ).fetchone()
        if not row:
            return 0
        txns = self._append_txn(
            row["wallet_transactions"] or "[]",
            {"type": "credit", "amount_cents": amount_cents,
             "reason": reason, "ts": datetime.utcnow().isoformat()}
        )
        new_balance = int(row["wallet_balance_cents"] or 0) + amount_cents
        self._conn.execute(
            "UPDATE users SET wallet_balance_cents=?, wallet_transactions=?, updated_at=? WHERE email=?",
            (new_balance, txns, datetime.utcnow().isoformat(), email)
        )
        self._conn.commit()
        return new_balance

    def set_wallet_balance(self, email: str, balance: int) -> None:
        """Legacy compat — sets balance directly (no transaction log)."""
        self._conn.execute(
            "UPDATE users SET wallet_balance_cents=?, updated_at=? WHERE email=?",
            (balance, datetime.utcnow().isoformat(), email.lower().strip())
        )
        self._conn.commit()

    # ── Profile CRUD ──────────────────────────────────────────────────────────

    def get_profile(self, email: str) -> dict | None:
        row = self._conn.execute(
            "SELECT * FROM users WHERE email=?", (email.lower().strip(),)
        ).fetchone()
        return self._row_to_dict(row) if row else None

    # Maps data-dict keys → (column_name, serializer)
    _PROFILE_FIELDS = {
        "name":                 ("name",                 lambda v: v or ""),
        "date_of_birth":        ("date_of_birth",        lambda v: v or ""),
        "time_of_birth":        ("time_of_birth",        lambda v: v or ""),
        "place_of_birth":       ("place_of_birth",       lambda v: v or ""),
        "latitude":             ("latitude",             lambda v: float(v or 0)),
        "longitude":            ("longitude",            lambda v: float(v or 0)),
        "timezone_offset":      ("timezone_offset",      lambda v: float(v or 0)),
        "kundli_json":          ("kundli_json",          json.dumps),
        "predictions_json":     ("predictions_json",     json.dumps),
        "overall_theme":        ("overall_theme",        lambda v: v or ""),
        "lagna_json":           ("lagna_json",           json.dumps),
        "birth_info_json":      ("birth_info_json",      json.dumps),
        "refined_analysis":     ("refined_analysis",     lambda v: v or ""),
        "planet_knowledge_json":("planet_knowledge_json",json.dumps),
        "children_info_json":   ("children_info_json",   json.dumps),
        "marital_status":       ("marital_status",       lambda v: v or ""),
        "preferred_language":   ("preferred_language",   lambda v: v or "English"),
        "session_id":           ("session_id",           lambda v: v or ""),
        "chat_messages_json":   ("chat_messages_json",   json.dumps),
        "region":               ("region",               lambda v: v or "India"),
        "currency":             ("currency",             lambda v: v or "INR"),
    }

    def save_profile(self, data: dict) -> dict:
        """
        Partial-update save: only the keys present in `data` are written.
        Existing columns NOT in `data` are left unchanged.
        This prevents partial saves (e.g. refine-step) from wiping kundli_json.
        """
        email = data.get("email", "").lower().strip()
        if not email:
            return {"success": False, "error": "email_required"}
        existing = self._conn.execute(
            "SELECT id FROM users WHERE email=?", (email,)
        ).fetchone()
        now = datetime.utcnow().isoformat()

        if existing:
            # Build UPDATE with only the explicitly-provided fields
            set_clauses: list[str] = ["updated_at = ?"]
            values: list = [now]
            for key, (col, serialize) in self._PROFILE_FIELDS.items():
                if key in data:
                    set_clauses.append(f"{col} = ?")
                    values.append(serialize(data[key]))
            values.append(email)
            self._conn.execute(
                f"UPDATE users SET {', '.join(set_clauses)} WHERE email = ?",
                values,
            )
        else:
            # Full INSERT with sensible defaults for omitted fields
            uid = str(uuid.uuid4())
            self._conn.execute(
                """INSERT INTO users
                   (id, email, name, date_of_birth, time_of_birth, place_of_birth,
                    latitude, longitude, timezone_offset,
                    kundli_json, predictions_json, overall_theme,
                    lagna_json, birth_info_json, refined_analysis,
                    planet_knowledge_json, children_info_json,
                    marital_status, preferred_language,
                    wallet_balance_cents, wallet_transactions,
                    session_id, region, currency, created_at, updated_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,0,'[]',?,?,?,?,?)""",
                (uid, email,
                 data.get("name",""), data.get("date_of_birth",""),
                 data.get("time_of_birth",""), data.get("place_of_birth",""),
                 float(data.get("latitude") or 0), float(data.get("longitude") or 0),
                 float(data.get("timezone_offset") or 0),
                 json.dumps(data.get("kundli_json",{})),
                 json.dumps(data.get("predictions_json",{})),
                 data.get("overall_theme",""),
                 json.dumps(data.get("lagna_json",{})),
                 json.dumps(data.get("birth_info_json",{})),
                 data.get("refined_analysis",""),
                 json.dumps(data.get("planet_knowledge_json",{})),
                 json.dumps(data.get("children_info_json",{})),
                 data.get("marital_status",""),
                 data.get("preferred_language","English"),
                 data.get("session_id",""),
                 data.get("region","India"), data.get("currency","INR"),
                 now, now)
            )
        self._conn.commit()
        return {"success": True}

    # ── Reading History ───────────────────────────────────────────────────────

    def save_reading_to_history(self, email: str, reading: dict) -> str:
        """Archive a completed reading. Returns the new history record id."""
        rid = str(uuid.uuid4())
        now = datetime.utcnow().isoformat()
        chat = reading.get("chat_messages_json", [])
        self._conn.execute(
            """INSERT INTO reading_history
               (id, email, name, date_of_birth, time_of_birth, place_of_birth,
                overall_theme, refined_analysis, chat_messages_json,
                planet_knowledge_json, session_id, created_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (rid, email.lower().strip(),
             reading.get("name",""), reading.get("date_of_birth",""),
             reading.get("time_of_birth",""), reading.get("place_of_birth",""),
             reading.get("overall_theme",""), reading.get("refined_analysis",""),
             json.dumps(chat if isinstance(chat, list) else []),
             json.dumps(reading.get("planet_knowledge_json", {})),
             reading.get("session_id",""), now)
        )
        self._conn.commit()
        return rid

    def get_reading_history(self, email: str) -> list[dict]:
        """Return summary list of past readings (no full text)."""
        rows = self._conn.execute(
            """SELECT id, name, date_of_birth, time_of_birth, place_of_birth,
                      overall_theme, created_at,
                      substr(refined_analysis, 1, 300) as preview
               FROM reading_history WHERE email=?
               ORDER BY created_at DESC""",
            (email.lower().strip(),)
        ).fetchall()
        return [dict(r) for r in rows]

    def get_reading_by_id(self, reading_id: str, email: str) -> dict | None:
        """Return full reading data by id (must belong to email)."""
        row = self._conn.execute(
            """SELECT * FROM reading_history
               WHERE id=? AND email=?""",
            (reading_id, email.lower().strip())
        ).fetchone()
        if not row:
            return None
        d = dict(row)
        for col in ("chat_messages_json", "planet_knowledge_json"):
            if col in d and isinstance(d[col], str):
                try: d[col] = json.loads(d[col])
                except Exception: d[col] = [] if "messages" in col else {}
        return d

    def delete_user(self, email: str) -> bool:
        cur = self._conn.execute(
            "DELETE FROM users WHERE email=?", (email.lower().strip(),)
        )
        self._conn.commit()
        return cur.rowcount > 0

    def get_all_users(self, search: str = "", limit: int = 200, offset: int = 0) -> list[dict]:
        if search:
            rows = self._conn.execute(
                "SELECT * FROM users WHERE email LIKE ? OR name LIKE ? LIMIT ? OFFSET ?",
                (f"%{search}%", f"%{search}%", limit, offset)
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM users LIMIT ? OFFSET ?", (limit, offset)
            ).fetchall()
        return [self._row_to_dict(r) for r in rows]

    def get_stats(self) -> dict:
        total   = self._conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        verified= self._conn.execute("SELECT COUNT(*) FROM users WHERE email_verified=1").fetchone()[0]
        # Sessions created today
        today   = datetime.utcnow().date().isoformat()
        today_r = self._conn.execute(
            "SELECT COUNT(*) FROM users WHERE session_id != '' AND updated_at LIKE ?",
            (f"{today}%",)
        ).fetchone()[0]
        # Sum of all credits issued
        credits = self._conn.execute(
            "SELECT COALESCE(SUM(wallet_balance_cents),0) FROM users"
        ).fetchone()[0]
        return {
            "total_users":         total,
            "verified_users":      verified,
            "unverified_users":    total - verified,
            "readings_today":      today_r,
            "total_balance_cents": credits,
        }

    def force_verify_email(self, email: str) -> bool:
        """Admin: force-verify without token check. Credits region-aware welcome amount."""
        row = self._conn.execute(
            "SELECT wallet_balance_cents, wallet_transactions, email_verified, region FROM users WHERE email=?",
            (email.lower().strip(),)
        ).fetchone()
        if not row:
            return False
        if row["email_verified"]:
            return True  # Already done

        region = row["region"] if "region" in row.keys() else "India"
        credit_amount = _welcome_credit_for_region(region or "India")

        txns = self._append_txn(
            row["wallet_transactions"] or "[]",
            {"type": "credit", "amount_cents": credit_amount,
             "reason": "welcome_verification", "ts": datetime.utcnow().isoformat()}
        )
        self._conn.execute(
            """UPDATE users SET
               email_verified=1, verification_token=NULL,
               verification_token_expires=NULL,
               wallet_balance_cents = wallet_balance_cents + ?,
               wallet_transactions=?,
               updated_at=?
               WHERE email=?""",
            (credit_amount, txns,
             datetime.utcnow().isoformat(), email.lower().strip())
        )
        self._conn.commit()
        return True

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _append_txn(existing_json: str, entry: dict) -> str:
        try:
            txns = json.loads(existing_json) if existing_json else []
        except (json.JSONDecodeError, TypeError):
            txns = []
        txns.append(entry)
        return json.dumps(txns)

    def _row_to_dict(self, row) -> dict:
        d = dict(row)
        for col in _JSON_COLS:
            if col in d and isinstance(d[col], str):
                try:
                    d[col] = json.loads(d[col])
                except (json.JSONDecodeError, TypeError):
                    d[col] = {}
        return d


    # ── Backward-compatibility aliases ────────────────────────────────────────

    def init(self) -> None:
        """Idempotent re-initialisation (no-op if schema already exists)."""
        self._conn.execute(_CREATE_USERS_SQL)
        self._conn.execute(_CREATE_HISTORY_SQL)
        self._conn.commit()
        _migrate(self._conn)

    def lookup(self, email: str) -> dict | None:
        """Alias for get_profile()."""
        return self.get_profile(email)

    def save_or_update(
        self, email: str, name: str = "",
        date_of_birth: str = "", time_of_birth: str = "",
        place_of_birth: str = "",
        latitude: float = 0.0, longitude: float = 0.0,
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
        uid = str(uuid.uuid4())
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
        existing = self._conn.execute(
            "SELECT id FROM users WHERE email=?", (email.lower().strip(),)
        ).fetchone()
        if existing:
            uid = existing["id"]
            data["id"] = uid
        self.save_profile(data)
        if not existing:
            row = self._conn.execute(
                "SELECT id FROM users WHERE email=?", (email.lower().strip(),)
            ).fetchone()
            uid = row["id"] if row else uid
        return uid

    def update_refined(
        self, email: str,
        refined_analysis: str = "",
        planet_knowledge: dict | None = None,
        session_id: str = "",
    ) -> None:
        """Legacy method to update refined analysis and planet knowledge."""
        now = datetime.utcnow().isoformat()
        self._conn.execute(
            """UPDATE users SET
               refined_analysis=?,
               planet_knowledge_json=?,
               session_id=COALESCE(NULLIF(?, \'\'), session_id),
               updated_at=?
               WHERE email=?""".replace("\\'", "'"),
            (refined_analysis,
             json.dumps(planet_knowledge or {}),
             session_id,
             now,
             email.lower().strip())
        )
        self._conn.commit()

    def has_predictions(self, email: str) -> bool:
        """Return True if the user has a stored predictions record."""
        row = self._conn.execute(
            "SELECT predictions_json FROM users WHERE email=?",
            (email.lower().strip(),)
        ).fetchone()
        if not row:
            return False
        try:
            p = json.loads(row["predictions_json"] or "{}")
            return bool(p)
        except Exception:
            return False

    def delete(self, email: str) -> bool:
        """Alias for delete_user()."""
        return self.delete_user(email)

    def list_users(self, limit: int = 500) -> list[dict]:
        """Alias for get_all_users()."""
        return self.get_all_users(limit=limit)

    def run_query(self, sql: str) -> list[dict]:
        """Execute a SELECT query and return rows as dicts. Non-SELECT raises ValueError."""
        stripped = sql.strip().upper()
        blocked  = ("INSERT", "UPDATE", "DELETE", "DROP", "ALTER", "ATTACH", "PRAGMA", "CREATE")
        if not stripped.startswith("SELECT"):
            raise ValueError("Only SELECT queries are permitted.")
        for kw in blocked:
            if kw in stripped:
                raise ValueError(f"Keyword '{kw}' is not allowed.")
        cur  = self._conn.execute(sql)
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, r)) for r in cur.fetchall()]
