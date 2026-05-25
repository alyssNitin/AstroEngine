"""
test_wallet_flow.py
===================
Quick diagnostic for Bug-1 (topup) and Bug-2 (history direction).

Run from the project root while the backend is running:
    python test_wallet_flow.py

What it checks:
  1.  POST /auth/login            — get a valid JWT token
  2.  GET  /wallet/balance        — check current balance
  3.  POST /wallet/topup/order    — create a mock order (no gateway keys needed)
  4.  POST /wallet/topup/verify   — apply the mock payment → wallet should go UP
  5.  GET  /wallet/balance        — confirm balance increased
  6.  GET  /payment/history       — confirm entries carry txn_type field
"""

import sys, json
import urllib.request, urllib.error

BASE   = "http://127.0.0.1:8000"
GREEN  = "\033[92m"
RED    = "\033[91m"
YELLOW = "\033[93m"
RESET  = "\033[0m"

# ── Config: fill in a real registered user ────────────────────────────────────
EMAIL    = "test@example.com"   # ← change to a real account
PASSWORD = "testpass123"        # ← change to that account's password
# ─────────────────────────────────────────────────────────────────────────────


def _req(method, path, body=None, token=None):
    url     = BASE + path
    data    = json.dumps(body).encode() if body is not None else None
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as e:
        try:
            detail = json.loads(e.read())
        except Exception:
            detail = {"raw": str(e)}
        return e.code, detail


def ok(msg):   print(f"{GREEN}  ✓  {msg}{RESET}")
def fail(msg): print(f"{RED}  ✗  {msg}{RESET}")
def info(msg): print(f"{YELLOW}  ℹ  {msg}{RESET}")


def run():
    print(f"\n{'='*60}")
    print("  NarayanAstroReader — Wallet Diagnostic")
    print(f"{'='*60}\n")

    # ── 1. Login ──────────────────────────────────────────────────────────────
    print("[1] POST /auth/login")
    code, resp = _req("POST", "/auth/login", {"email": EMAIL, "password": PASSWORD})
    if code != 200:
        fail(f"Login failed ({code}): {resp}")
        sys.exit(1)
    token = resp.get("access_token") or (resp.get("user") or {}).get("access_token")
    if not token:
        fail(f"No access_token in response: {list(resp.keys())}")
        sys.exit(1)
    ok(f"Logged in as {EMAIL}  (token: {token[:20]}…)")

    # ── 2. Balance before ─────────────────────────────────────────────────────
    print("\n[2] GET /wallet/balance")
    code, resp = _req("GET", "/wallet/balance", token=token)
    if code != 200:
        fail(f"Balance check failed ({code}): {resp}")
    else:
        bal_before = resp.get("balance_cents", 0)
        ok(f"Balance before topup: {resp.get('balance', bal_before)}")

    # ── 3. Topup order ────────────────────────────────────────────────────────
    print("\n[3] POST /wallet/topup/order  (tier=1)")
    code, resp = _req("POST", "/wallet/topup/order", {"email": EMAIL, "tier": 1})
    if code != 200:
        fail(f"Topup order failed ({code}): {resp}")
        sys.exit(1)
    is_mock = resp.get("mock", False)
    ok(f"Order created — mock={is_mock}  order_id={resp.get('order_id')}  "
       f"credits={resp.get('credits')}  total={resp.get('total_display')}")
    if not is_mock:
        info("Gateway keys are set — real payment required. "
             "For dev testing set PAYMENT_GATEWAY=razorpay and leave "
             "RAZORPAY_KEY_ID / RAZORPAY_KEY_SECRET empty.")

    # ── 4. Topup verify ───────────────────────────────────────────────────────
    print("\n[4] POST /wallet/topup/verify  (mock payment)")
    code, resp = _req("POST", "/wallet/topup/verify",
                      {"email": EMAIL, "tier": 1, "payment_data": {"mock": True}})
    if code != 200:
        fail(f"Topup verify failed ({code}): {resp}")
    elif not resp.get("success"):
        fail(f"Backend returned success=false: {resp}")
    else:
        ok(f"Wallet credited!  new_balance={resp.get('new_balance_display')}  "
           f"({resp.get('new_balance_cents')} minor-units)")

    # ── 5. Balance after ──────────────────────────────────────────────────────
    print("\n[5] GET /wallet/balance  (should be higher)")
    code, resp = _req("GET", "/wallet/balance", token=token)
    if code != 200:
        fail(f"Balance check failed ({code}): {resp}")
    else:
        bal_after = resp.get("balance_cents", 0)
        diff = bal_after - bal_before
        if diff > 0:
            ok(f"Balance after topup: {resp.get('balance', bal_after)}  "
               f"(+{diff} minor-units ✓)")
        else:
            fail(f"Balance did NOT increase! before={bal_before} after={bal_after}")

    # ── 6. Transaction history ────────────────────────────────────────────────
    print("\n[6] GET /payment/history")
    code, resp = _req("GET", "/payment/history?page=1&per_page=10", token=token)
    if code != 200:
        fail(f"History failed ({code}): {resp}")
    else:
        entries = resp.get("entries", [])
        ok(f"Got {len(entries)} entries (region={resp.get('region')})")
        for i, e in enumerate(entries[:5]):
            txn_type = e.get("txn_type") or e.get("type") or "?"
            amount   = e.get("amount_cents", e.get("amount", 0))
            reason   = e.get("reason", "")
            sign     = "−" if txn_type == "debit" else "+"
            flag     = "" if txn_type in ("debit", "credit", "topup", "refund_ai_error") else " ⚠ unknown txn_type"
            print(f"     [{i+1}] {sign}{abs(amount):,} minor-units  "
                  f"txn_type={txn_type!r}  reason={reason!r}{flag}")

    print(f"\n{'='*60}")
    print("  Diagnostic complete.")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--email",    default=EMAIL)
    p.add_argument("--password", default=PASSWORD)
    p.add_argument("--base",     default=BASE)
    args = p.parse_args()

    EMAIL    = args.email
    PASSWORD = args.password
    BASE     = args.base

    run()
