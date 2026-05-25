"""
backend/api/shared_page.py
===========================
Generates the public HTML page for PIN-protected shareable readings.

The page is self-contained (no external JS/CSS deps) and works in two states:
  1. PIN entry form — shown on first load
  2. Reading display  — shown after the frontend POSTs the PIN and gets a 200 response

Public API
----------
    build_shared_page(token: str) -> str
        Returns the complete HTML string to serve at GET /shared/{token}
"""
from __future__ import annotations


def build_shared_page(token: str) -> str:
    """Return the PIN-entry HTML page for a shared reading."""
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Shared Vedic Reading — NarayanAstroReader</title>
<style>
  :root {{
    --bg:     #1a1a2e;
    --card:   #16213e;
    --accent: #a78bfa;
    --gold:   #f59e0b;
    --text:   #e0e0e0;
    --muted:  #888;
    --red:    #ef4444;
    --green:  #22c55e;
    --radius: 12px;
  }}
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{
    font-family: 'Segoe UI', Arial, sans-serif;
    background: var(--bg);
    color: var(--text);
    min-height: 100vh;
    display: flex;
    flex-direction: column;
    align-items: center;
    padding: 32px 16px;
  }}
  .logo {{
    font-size: 1.5rem;
    font-weight: 700;
    color: var(--accent);
    margin-bottom: 8px;
    letter-spacing: -0.5px;
  }}
  .tagline {{
    font-size: .82rem;
    color: var(--muted);
    margin-bottom: 32px;
  }}
  .card {{
    background: var(--card);
    border-radius: var(--radius);
    padding: 32px;
    width: 100%;
    max-width: 580px;
    box-shadow: 0 8px 32px rgba(0,0,0,.4);
  }}
  h2 {{ color: var(--accent); margin-bottom: 6px; font-size: 1.25rem; }}
  p  {{ color: var(--muted); font-size: .88rem; margin-bottom: 20px; line-height: 1.6; }}
  input[type=text], input[type=number] {{
    background: #0d1030;
    border: 1.5px solid #3d2b6e;
    border-radius: 8px;
    color: var(--text);
    font-size: 2rem;
    letter-spacing: 12px;
    text-align: center;
    padding: 14px;
    width: 100%;
    margin-bottom: 16px;
    outline: none;
    transition: border-color .2s;
  }}
  input:focus {{ border-color: var(--accent); }}
  button {{
    background: linear-gradient(135deg, #5b3dc8, #7c5cbf);
    color: #fff;
    border: none;
    border-radius: 8px;
    padding: 13px 28px;
    font-size: 1rem;
    font-weight: 600;
    cursor: pointer;
    width: 100%;
    transition: opacity .2s;
  }}
  button:hover {{ opacity: .9; }}
  button:disabled {{ opacity: .5; cursor: not-allowed; }}
  .err {{
    background: rgba(239,68,68,.12);
    border: 1px solid var(--red);
    border-radius: 8px;
    padding: 10px 14px;
    color: var(--red);
    font-size: .88rem;
    margin-bottom: 14px;
    display: none;
  }}
  /* Reading display */
  #readingView {{ display: none; }}
  .reading-header {{
    border-bottom: 1px solid #3d2b6e;
    padding-bottom: 16px;
    margin-bottom: 20px;
  }}
  .reading-header h1 {{ color: var(--gold); font-size: 1.4rem; }}
  .reading-meta {{ font-size: .8rem; color: var(--muted); margin-top: 6px; }}
  .section-title {{
    color: var(--accent);
    font-size: 1rem;
    font-weight: 700;
    margin: 20px 0 8px;
    text-transform: uppercase;
    letter-spacing: .5px;
  }}
  .reading-body {{
    line-height: 1.85;
    font-size: .93rem;
    white-space: pre-wrap;
    word-break: break-word;
  }}
  .badge {{
    display: inline-block;
    background: rgba(167,139,250,.15);
    color: var(--accent);
    border-radius: 20px;
    padding: 3px 12px;
    font-size: .78rem;
    margin-bottom: 16px;
  }}
  .footer {{
    text-align: center;
    color: var(--muted);
    font-size: .75rem;
    margin-top: 24px;
  }}
  .footer a {{ color: var(--accent); text-decoration: none; }}
</style>
</head>
<body>

<div class="logo">&#127775; NarayanAstroReader</div>
<div class="tagline">Vedic AI Astrology — Shared Reading</div>

<!-- PIN Entry Form -->
<div class="card" id="pinCard">
  <h2>&#128274; Enter PIN to View Reading</h2>
  <p>
    Someone shared their personalised Vedic reading with you.<br>
    Enter the 4-digit PIN they gave you to access it.
  </p>
  <div class="err" id="pinErr"></div>
  <input type="number" id="pinInput" inputmode="numeric" pattern="[0-9]{{4}}"
         placeholder="&#9679;&#9679;&#9679;&#9679;" maxlength="4"
         onkeydown="if(event.key==='Enter')submitPin()">
  <button id="pinBtn" onclick="submitPin()">&#128275; View Reading</button>
  <p style="margin-top:16px;text-align:center;font-size:.78rem">
    This link expires 72 hours after it was created.
  </p>
</div>

<!-- Reading Display (shown after successful PIN) -->
<div class="card" id="readingView">
  <div class="reading-header">
    <div class="badge">&#10024; Personalised Vedic Reading</div>
    <h1 id="rdName"></h1>
    <div class="reading-meta" id="rdMeta"></div>
  </div>

  <div id="rdThemeWrap" style="display:none">
    <div class="section-title">Overall Life Theme</div>
    <div class="reading-body" id="rdTheme"></div>
  </div>

  <div class="section-title">Deep Vedic Reading</div>
  <div class="reading-body" id="rdAnalysis"></div>

  <div class="footer">
    <p>&#169; NarayanAstroReader &mdash; <a href="/">Get your own reading</a></p>
    <p style="margin-top:6px">Views remaining on this link: <span id="rdViews"></span></p>
  </div>
</div>

<script>
const TOKEN = {repr(token)};
const API   = '';   // same origin

async function submitPin() {{
  const pin = document.getElementById('pinInput').value.trim();
  const err = document.getElementById('pinErr');
  err.style.display = 'none';

  if (pin.length !== 4 || !/^\d{{4}}$/.test(pin)) {{
    err.textContent = 'Please enter exactly 4 digits.';
    err.style.display = 'block';
    return;
  }}

  const btn = document.getElementById('pinBtn');
  btn.disabled = true;
  btn.textContent = 'Verifying…';

  try {{
    const res = await fetch(API + '/shared/' + TOKEN, {{
      method:  'POST',
      headers: {{'Content-Type': 'application/json'}},
      body:    JSON.stringify({{pin}}),
    }});

    const data = await res.json();

    if (!res.ok) {{
      err.textContent = data.detail || 'Incorrect PIN or link has expired.';
      err.style.display = 'block';
      return;
    }}

    showReading(data.reading);

  }} catch (e) {{
    err.textContent = 'Network error: ' + e.message;
    err.style.display = 'block';
  }} finally {{
    btn.disabled = false;
    btn.textContent = '\\u{1F513} View Reading';
  }}
}}

function showReading(r) {{
  document.getElementById('pinCard').style.display   = 'none';
  document.getElementById('readingView').style.display = 'block';

  document.getElementById('rdName').textContent = r.name || 'Vedic Reading';
  document.getElementById('rdMeta').textContent =
    [r.date_of_birth, r.time_of_birth, r.place_of_birth].filter(Boolean).join(' • ');

  if (r.overall_theme) {{
    document.getElementById('rdThemeWrap').style.display = 'block';
    document.getElementById('rdTheme').textContent = r.overall_theme;
  }}

  document.getElementById('rdAnalysis').textContent = r.refined_analysis || '';

  const maxViews = 50;
  const remaining = Math.max(0, maxViews - (r.view_count || 0));
  document.getElementById('rdViews').textContent = remaining;
}}

// Auto-focus PIN input
document.getElementById('pinInput').focus();
</script>
</body>
</html>"""
