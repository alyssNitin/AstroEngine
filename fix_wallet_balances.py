"""
fix_wallet_balances.py
======================
One-time migration: bring all verified users' wallets up to the correct
welcome credit amount for their region.

Run AFTER stopping the server:
    python fix_wallet_balances.py
"""
import sqlite3, json, os
from datetime import datetime
from pathlib import Path

DB_PATH = os.environ.get("DB_PATH", str(Path(__file__).parent / "narayan_astro.db"))

INDIA_WELCOME  = 10_000   # ₹100 in paise
INTL_WELCOME   =    100   # $1.00 in cents

print(f"Opening: {DB_PATH}")
conn = sqlite3.connect(DB_PATH)
conn.row_factory = sqlite3.Row

rows = conn.execute(
    "SELECT email, wallet_balance_cents, wallet_transactions, region, email_verified FROM users"
).fetchall()

fixed = 0
for row in rows:
    email    = row["email"]
    bal      = row["wallet_balance_cents"] or 0
    verified = row["email_verified"]
    region   = row["region"] or "India"
    expected = INDIA_WELCOME if region == "India" else INTL_WELCOME

    if not verified:
        print(f"  SKIP  {email} — not yet verified")
        continue

    if bal >= expected:
        print(f"  OK    {email} — balance {bal} paise already at target ({expected})")
        continue

    diff = expected - bal
    try:
        txns = json.loads(row["wallet_transactions"] or "[]")
    except Exception:
        txns = []
    txns.append({
        "type": "credit",
        "amount_cents": diff,
        "reason": "welcome_credit_correction",
        "ts": datetime.utcnow().isoformat(),
    })
    conn.execute(
        "UPDATE users SET wallet_balance_cents=?, wallet_transactions=?, updated_at=? WHERE email=?",
        (expected, json.dumps(txns), datetime.utcnow().isoformat(), email),
    )
    amt_str = f"₹{expected//100}" if region == "India" else f"${expected/100:.2f}"
    print(f"  FIXED {email} ({region}): {bal} → {expected} paise | credited +{diff} | new balance {amt_str}")
    fixed += 1

conn.commit()
conn.close()
print(f"\nDone — {fixed} account(s) corrected.")
