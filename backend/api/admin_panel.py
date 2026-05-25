"""
backend/api/admin_panel.py
===========================
Generates the Super Admin HTML panel.

Extracted from main.py so that the giant HTML string does not cause
Edit-tool truncation of the main application file.

Public API
----------
    build_admin_html(stats, users) -> str
        Returns the complete HTML page as a string.
"""
from __future__ import annotations


def build_admin_html(stats: dict, users: list[dict]) -> str:
    """Render the super-admin dashboard HTML page."""

    # ── User table rows ──────────────────────────────────────────────────────
    def _fmt_bal(cents: int, region: str = "India") -> str:
        sym = "₹" if region == "India" else "$"
        return f"{sym}{cents / 100:,.2f}"

    user_rows = ""
    for u in users:
        bal_cents = u.get("wallet_balance_cents", 0)
        region    = u.get("region", "India")
        verified  = "&#10003;" if u.get("email_verified") else "&#10007;"
        v_color   = "#1e8c5a" if u.get("email_verified") else "#c0392b"
        user_rows += (
            "<tr>"
            f"<td>{u.get('email', '')}</td>"
            f"<td>{u.get('name', '')}</td>"
            f"<td style='color:{v_color}'>{verified}</td>"
            f"<td>{_fmt_bal(bal_cents, region)}</td>"
            f"<td>{u.get('region', 'India')}</td>"
            f"<td>{str(u.get('created_at', ''))[:10]}</td>"
            "</tr>"
        )

    # ── Stats cards ──────────────────────────────────────────────────────────
    total_users      = stats.get("total_users", 0)
    verified_users   = stats.get("verified_users", 0)
    total_readings   = stats.get("total_readings", 0)
    total_balance    = stats.get("total_balance_cents", 0)

    html = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Admin &#8212; NarayanAstroReader</title>
<style>
  *{{box-sizing:border-box;margin:0;padding:0}}
  body{{font-family:Arial,sans-serif;background:#1a1a2e;color:#e0e0e0;padding:24px}}
  h1{{color:#7c5cbf;margin-bottom:4px;font-size:1.6rem}}
  h2{{color:#a78bfa;font-size:1rem;margin:20px 0 10px}}
  h3{{color:#c4b5fd;font-size:0.95rem;margin-bottom:8px}}
  .stats{{display:flex;gap:16px;flex-wrap:wrap;margin:20px 0}}
  .stat{{background:#16213e;border-radius:8px;padding:16px 24px;min-width:150px}}
  .stat .val{{font-size:1.8rem;font-weight:bold;color:#a78bfa}}
  .stat .lbl{{font-size:11px;color:#888;margin-top:4px}}
  .section{{background:#16213e;border-radius:8px;padding:16px;margin-bottom:16px}}
  input,select,textarea{{background:#0d1030;color:#e0e0e0;border:1px solid #3d2b6e;
    border-radius:4px;padding:7px 10px;font-size:13px;width:100%;margin-bottom:8px}}
  button{{background:#5b3dc8;color:#fff;border:none;border-radius:4px;
    padding:8px 16px;cursor:pointer;font-size:13px;margin-right:6px}}
  button:hover{{background:#7c5cbf}}
  pre{{background:#0d1030;border-radius:4px;padding:10px;font-size:12px;
    white-space:pre-wrap;word-break:break-word;max-height:200px;overflow-y:auto;
    display:none;margin-top:8px}}
  table{{width:100%;border-collapse:collapse;margin-top:12px;font-size:13px}}
  th{{background:#2d1f5e;color:#c4b5fd;padding:8px 10px;text-align:left;font-size:11px}}
  td{{padding:7px 10px;border-bottom:1px solid #2a2050}}
  tr:hover td{{background:#1e1545}}
  .badge{{display:inline-block;padding:2px 8px;border-radius:10px;font-size:11px}}
</style>
</head>
<body>
<h1>&#127775; NarayanAstroReader — Super Admin</h1>
<p style="color:#888;font-size:12px">Restricted access. All actions are logged.</p>

<div class="stats">
  <div class="stat"><div class="val">""" + str(total_users) + """</div><div class="lbl">Total Users</div></div>
  <div class="stat"><div class="val">""" + str(verified_users) + """</div><div class="lbl">Verified Users</div></div>
  <div class="stat"><div class="val">""" + str(total_readings) + """</div><div class="lbl">Total Readings</div></div>
  <div class="stat"><div class="val">&#8377;""" + f"{total_balance / 100:,.0f}" + """</div><div class="lbl">Total Wallet Balance</div></div>
</div>

<!-- Wallet Adjust -->
<div class="section">
  <h3>&#128176; Adjust Wallet Balance</h3>
  <input id="wadj_email" placeholder="user@example.com" type="email">
  <input id="wadj_delta" placeholder="Amount in paise/cents (negative to debit)" type="number">
  <input id="wadj_reason" placeholder="Reason (e.g. manual_credit, support_refund)" type="text">
  <button onclick="adjustWallet()">Apply Adjustment</button>
  <pre id="wadj_result"></pre>
</div>

<!-- SQL Query -->
<div class="section">
  <h3>&#128202; Read-only SQL Query</h3>
  <textarea id="adm_sql" rows="3" placeholder="SELECT email, wallet_balance_cents FROM users LIMIT 10;"></textarea>
  <button onclick="runQuery()">Run Query</button>
  <pre id="adm_result"></pre>
</div>

<!-- Force Verify -->
<div class="section">
  <h3>&#9989; Force Verify Email</h3>
  <input id="fv_email" placeholder="user@example.com" type="email">
  <button onclick="forceVerify()">Force Verify + Grant Welcome Credit</button>
  <pre id="fv_result"></pre>
</div>

<!-- Delete User -->
<div class="section" style="border:1px solid #8b1a1a">
  <h3 style="color:#e74c3c">&#128465; Delete User</h3>
  <p style="font-size:12px;color:#aaa;margin:0 0 10px">
    &#9888; Permanently deletes the account and all associated data. Cannot be undone.
  </p>
  <input id="du_email" placeholder="user@example.com" type="email">
  <button onclick="confirmDelete()" style="background:#c0392b">&#128465; Delete User</button>
  <pre id="du_result"></pre>
</div>

<!-- User Table -->
<div class="section">
  <h3>&#128101; All Users</h3>
  <table>
    <thead>
      <tr>
        <th>Email</th><th>Name</th><th>Verified</th>
        <th>Balance</th><th>Region</th><th>Joined</th>
      </tr>
    </thead>
    <tbody>
""" + user_rows + """
    </tbody>
  </table>
</div>

<script>
const H = {'Content-Type': 'application/json'};

async function adjustWallet() {
  const email       = document.getElementById('wadj_email').value;
  const delta_cents = parseInt(document.getElementById('wadj_delta').value) || 0;
  const reason      = document.getElementById('wadj_reason').value;
  const r           = document.getElementById('wadj_result');
  r.style.display = 'block'; r.textContent = 'Adjusting...';
  try {
    const res = await fetch('/admin/wallet/adjust', {
      method: 'POST', headers: H,
      body: JSON.stringify({email, delta_cents, reason})
    });
    r.textContent = JSON.stringify(await res.json(), null, 2);
  } catch(e) { r.textContent = 'Error: ' + e; }
}

async function runQuery() {
  const sql = document.getElementById('adm_sql').value;
  const r   = document.getElementById('adm_result');
  r.style.display = 'block'; r.textContent = 'Running...';
  try {
    const res = await fetch('/admin/query', {
      method: 'POST', headers: H, body: JSON.stringify({sql})
    });
    r.textContent = JSON.stringify(await res.json(), null, 2);
  } catch(e) { r.textContent = 'Error: ' + e; }
}

async function forceVerify() {
  const email = document.getElementById('fv_email').value;
  const r     = document.getElementById('fv_result');
  r.style.display = 'block'; r.textContent = 'Verifying...';
  try {
    const res = await fetch('/admin/force-verify', {
      method: 'POST', headers: H, body: JSON.stringify({email})
    });
    r.textContent = JSON.stringify(await res.json(), null, 2);
  } catch(e) { r.textContent = 'Error: ' + e; }
}

async function confirmDelete() {
  const email = document.getElementById('du_email').value;
  if (!email) { alert('Enter an email address first.'); return; }
  if (!confirm('Permanently delete user ' + email + '? This cannot be undone.')) return;
  const r = document.getElementById('du_result');
  r.style.display = 'block'; r.textContent = 'Deleting...';
  try {
    const res = await fetch('/admin/delete-user', {
      method: 'POST', headers: H, body: JSON.stringify({email})
    });
    r.textContent = JSON.stringify(await res.json(), null, 2);
  } catch(e) { r.textContent = 'Error: ' + e; }
}
</script>
</body>
</html>"""

    return html
