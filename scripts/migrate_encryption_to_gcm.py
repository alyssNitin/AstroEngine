#!/usr/bin/env python3
"""
scripts/migrate_encryption_to_gcm.py
======================================
One-off migration: re-encrypt all Fernet (AES-128) PII columns → AES-256-GCM.

Run AFTER updating FIELD_ENCRYPTION_KEY or AWS_KMS_KEY_ID in .env:
    python3 scripts/migrate_encryption_to_gcm.py [--dry-run]

Columns migrated:
    users          : email, mfa_secret
    kundli_profiles: name, place_of_birth
"""
from __future__ import annotations

import argparse
import sys
import os

# Allow running from project root
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import psycopg2
import psycopg2.extras

from backend.auth.field_encryption import decrypt_pii, encrypt_pii, is_pii_encrypted, _GCM_PREFIX

DATABASE_URL = os.environ.get("DATABASE_URL", "")

COLUMNS: list[tuple[str, str, str]] = [
    # (table, pk_column, value_column)
    ("users",           "email",  "email"),
    ("users",           "email",  "mfa_secret"),
    ("kundli_profiles", "id",     "name"),
    ("kundli_profiles", "id",     "place_of_birth"),
]


def migrate(dry_run: bool = False) -> None:
    if not DATABASE_URL:
        print("ERROR: DATABASE_URL not set", file=sys.stderr)
        sys.exit(1)

    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = False
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)

    total_migrated = 0
    total_skipped  = 0

    for table, pk_col, val_col in COLUMNS:
        cur.execute(f"SELECT {pk_col}, {val_col} FROM {table} WHERE {val_col} IS NOT NULL")
        rows = cur.fetchall()

        migrated_in_table = 0
        for row in rows:
            pk    = row[pk_col]
            stored = row[val_col]

            if not stored:
                continue
            if stored.startswith(_GCM_PREFIX):
                total_skipped += 1
                continue   # Already GCM

            # Decrypt (handles enc:, plain:, bare)
            plaintext = decrypt_pii(stored)
            if plaintext is None:
                continue

            new_val = encrypt_pii(plaintext)
            if new_val is None:
                continue

            if not dry_run:
                cur.execute(
                    f"UPDATE {table} SET {val_col} = %s WHERE {pk_col} = %s",
                    (new_val, pk),
                )
            migrated_in_table += 1

        print(
            f"  {table}.{val_col}: {migrated_in_table} rows "
            + ("(dry-run, not saved)" if dry_run else "migrated")
        )
        total_migrated += migrated_in_table

    if not dry_run:
        conn.commit()
        print(f"\n✅ Migration complete: {total_migrated} values upgraded to AES-256-GCM")
    else:
        print(f"\n(Dry-run) Would migrate {total_migrated} values | {total_skipped} already GCM")

    cur.close()
    conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Migrate PII encryption: Fernet → AES-256-GCM")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be migrated without writing")
    args = parser.parse_args()
    migrate(dry_run=args.dry_run)
