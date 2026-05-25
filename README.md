# NarayanAstroReader — Vedic AI Astrology Platform

[![Phase 1](https://img.shields.io/badge/Phase-1%20AI%20Core-blue)](.)
[![Python](https://img.shields.io/badge/Python-3.11%2B-green)](.)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.110%2B-009688)](.)
[![License](https://img.shields.io/badge/License-Proprietary-red)](.)

A production-grade Vedic astrology platform powered by Claude AI. Users enter birth details to receive a personalised Kundli chart and deep AI-generated reading, then follow up with live Q&A chat — all in English, Hindi, or Tamil with region-aware pricing.

---

## Architecture

The platform is designed as a **microservices monorepo**. Each service is independently deployable, stateless, and horizontally scalable.

```
NarayanAstroReader/
├── services/                    # Backend microservices
│   ├── auth-service/            # Registration, login, JWT, OAuth
│   ├── kundli-engine/           # Vedic chart computation (Swiss Ephemeris)
│   ├── dasha-engine/            # Dasha period calculation (pluggable)
│   ├── ai-interpretation-service/ # Claude AI reading + chat (SSE stream)
│   ├── credit-wallet-service/   # Wallet, ledger, billing
│   ├── payment-gateway-service/ # Razorpay / Stripe / UPI
│   ├── report-export-service/   # PDF / DOCX / shareable links
│   ├── analytics-service/       # Admin dashboard metrics
│   └── notification-service/    # Email / Push notifications
├── apps/
│   └── web/                     # Frontend (currently vanilla JS → React migration planned)
├── backend/                     # Monolith origin (being migrated into services/)
├── payment/                     # Payment module (being migrated → payment-gateway-service/)
├── tests/                       # Unit test suite
└── infrastructure/
    └── docker/
        └── docker-compose.yml   # Local dev environment
```

> **Note**: The `backend/` and `payment/` folders are the **current working implementation** (monolith). The `services/` folder is the **target microservices structure** that is being progressively populated. Both coexist during migration.

---

## New Team Member Setup

Follow these steps on a fresh machine to get the system running end-to-end.

### 1 — Clone both repositories (side by side)

```bash
# They must sit in the same parent folder so PYJHORA_PATH resolves correctly
git clone https://github.com/alyssNitin/AstroEngine.git
git clone https://github.com/alyssNitin/PyJHora.git
```

Your folder layout should look like:
```
C:\Users\you\
  ├── AstroEngine\
  └── PyJHora\
```

### 2 — Create your .env file

```bash
cd NarayanAstroReader
copy .env.example .env   # Windows
# cp .env.example .env   # Mac/Linux
```

Open `.env` and fill in at minimum:
- `ANTHROPIC_API_KEY` — get one at console.anthropic.com
- `PYJHORA_PATH` — absolute path to `PyJHora\src` on your machine
- `JWT_SECRET` — any random 32-char string (`python -c "import secrets; print(secrets.token_hex(32))"`)
- Leave `DATABASE_URL` blank to use SQLite (easiest for local dev)
- Leave payment keys blank — the system works in mock/dev mode automatically

### 3 — Install Python dependencies

```bash
# From NarayanAstroReader\
pip install -r requirements.txt

# Install PyJHora as an editable package
pip install -e ..\PyJHora\src
```

### 4 — Build the React frontend

Windows (double-click or run in CMD):
```
build_frontend.bat
```

Mac/Linux:
```bash
cd frontend-react
npm install
npm run build
cd ..
```

This compiles the React app into `frontend-react/dist/` which the FastAPI server then serves.

### 5 — Start the backend

```bash
python start.py
```

Then open **http://localhost:8000** in your browser.

> **First run tip:** If you see a "tables not found" error, `start.py` calls `init_schema()` automatically which creates all PostgreSQL/SQLite tables.

### 6 — Verify it works

Register a new account → verify your email (check the console if SMTP is not configured — the link is printed there) → log in → enter birth details and generate a reading.

To test the wallet top-up without real payment keys, open the wallet modal → Top Up → click any package. With no gateway keys set, the system runs in mock mode and credits your account immediately.

---

## Quick Start (Current Monolith)

### Prerequisites

- Python 3.11+
- [PyJHora](https://github.com/your-org/PyJHora) checked out at `../PyJHora`
- Anthropic API key

### Install & Run

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Configure environment
cp .env.example .env
# Edit .env: set ANTHROPIC_API_KEY, SMTP credentials

# 3. Start the server
python start.py
# or:
uvicorn backend.api.main:app --host 0.0.0.0 --port 8000 --reload

# 4. Open in browser
open http://localhost:8000
```

### Admin Panel

```
URL:      http://localhost:8000/admin
Username: (set ADMIN_USERNAME in .env, default: admin)
Password: (set ADMIN_PASSWORD in .env, default: admin123)
```

---

## Quick Start (Microservices via Docker Compose)

> ⚠️ **Note**: Not all services are fully functional yet. See Phase Status below.

```bash
# Copy and configure env
cp .env.example .env
# Set ANTHROPIC_API_KEY and other required vars

# Build and start all services
cd infrastructure/docker
docker-compose up --build

# Services available at:
#   http://localhost:8000  → auth-service
#   http://localhost:8001  → kundli-engine
#   http://localhost:8002  → dasha-engine
#   http://localhost:8003  → ai-interpretation-service
#   http://localhost:8004  → credit-wallet-service
#   http://localhost:8005  → payment-gateway-service
#   http://localhost:8006  → report-export-service
#   http://localhost:8008  → notification-service
#   http://localhost:3000  → frontend
```

---

## Environment Variables

| Variable | Required | Description |
|---|---|---|
| `ANTHROPIC_API_KEY` | ✅ | Anthropic Claude API key |
| `ANTHROPIC_MODEL` | — | Model ID (default: `claude-sonnet-4-6`) |
| `PYJHORA_PATH` | ✅ | Absolute path to PyJHora repo |
| `JWT_SECRET` | ✅ (Phase 1-B) | JWT signing secret (min 32 chars) |
| `DB_PATH` | — | SQLite DB path (default: `./narayan_astro.db`) |
| `SMTP_HOST` | — | SMTP server (email falls back to console if unset) |
| `SMTP_USER` | — | SMTP username |
| `SMTP_PASSWORD` | — | SMTP App Password |
| `FROM_EMAIL` | — | Sender email address |
| `PAYMENT_GATEWAY` | — | `razorpay` or `stripe` (default: `razorpay`) |
| `RAZORPAY_KEY_ID` | — | Razorpay key ID (Phase 1-C) |
| `RAZORPAY_KEY_SECRET` | — | Razorpay key secret (Phase 1-C) |
| `ADMIN_USERNAME` | — | Admin panel username (default: `admin`) |
| `ADMIN_PASSWORD` | — | Admin panel password (default: `admin123`) |

---

## Phase Status

| Phase | Status | Description |
|---|---|---|
| **Phase 1-A** | ✅ Complete | Core user journey: Kundli → AI Reading → Chat → Payment mock |
| **Phase 1-B** | 🚧 In Progress | JWT auth, microservice folders, wallet ledger table, auto-refund |
| **Phase 1-C** | 📋 Planned | PostgreSQL, Redis, real Razorpay, Dockerfiles, OAuth, 2FA |
| **Phase 2** | 📋 Planned | React SPA, React Native mobile, S3, FCM push, Analytics |

---

## Feature Overview

| Feature | Status |
|---|---|
| Vedic Kundli chart (via PyJHora + Swiss Ephemeris) | ✅ |
| AI deep reading — streamed via SSE | ✅ |
| Chat Q&A with billing | ✅ |
| Multi-language: English / Hindi / Tamil | ✅ |
| Region-aware pricing: India (₹) / International ($) | ✅ |
| Email verification + welcome credit | ✅ |
| Credit wallet + top-up | ✅ |
| PDF report + email delivery | ✅ |
| Admin panel (user mgmt, wallet adjust, SQL query) | ✅ |
| Guest mode (3 free chat messages) | ✅ |
| Safety filter (no death predictions) | ✅ |
| Dasha engine — Vimshottari | ✅ |
| Dasha engine — Yogini/Chara/Kalachakra | 🚧 |
| OAuth (Google / Apple) | 🚧 |
| 2FA / TOTP | 🚧 |
| Compatibility & Career reports | 🚧 |
| Real Razorpay / Stripe integration | 🚧 |
| SVG Kundli chart render | 🚧 |

---

## Running Tests

```bash
python -m pytest tests/ -v
# or run the HTML report:
python tests/run_tests.py
```

---

## Architecture Documents

- [`design_architecture.html`](design_architecture.html) — Full system architecture specification
- [`phase1_audit_report.html`](phase1_audit_report.html) — Phase-1 compliance audit (this audit)
- [`unit_test_cases.html`](unit_test_cases.html) — All unit test cases

---

## Key Design Decisions

1. **Integer minor units for money**: All wallet amounts are integers (paise for India, cents for International). No floating-point money.
2. **PII never reaches LLM**: `planet_calibrator.py` anonymises all prompts before calling Claude.
3. **SSE for AI streaming**: The deep reading streams token-by-token for perceived speed.
4. **SQLite → PostgreSQL path**: Current SQLite DB is structured to migrate cleanly; schema uses UUIDs and ISO timestamps.
5. **PyJHora dependency**: The computation engine uses PyJHora (local checkout) which wraps Swiss Ephemeris — the gold standard for Vedic calculations.

---

## Contributing

1. Each service has its own `README.md` with API docs, env vars, and run instructions
2. PRs require all tests to pass: `python -m pytest tests/ -v`
3. No hardcoded secrets — always use `.env` or Secrets Manager

---

*NarayanAstroReader — Phase 1 — Confidential*
