"""
Run this once to wipe all registered users from the database.
Usage:  python clear_users.py
"""
import sqlite3, os, pathlib

db_path = pathlib.Path(__file__).parent / "narayan_astro.db"
if not db_path.exists():
    print("Database not found — nothing to clear.")
else:
    conn = sqlite3.connect(str(db_path))
    cur  = conn.cursor()
    cur.execute("DELETE FROM users")
    conn.commit()
    n = cur.rowcount
    conn.close()
    print(f"Done — {n} user(s) removed. You can now re-register with the same email.")
