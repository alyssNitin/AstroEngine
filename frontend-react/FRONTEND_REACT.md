# NarayanAstroReader — React SPA Frontend

A React 18 + Vite single-page application that replaces the original vanilla HTML/JS frontend.
Follows SOLID principles throughout: every module has a single responsibility, components are
open for extension via props/context, and UI code never calls `fetch` directly (Dependency Inversion).

---

## Quick Start (Windows PowerShell)

```powershell
# From the project root:
.\scripts\build_frontend.ps1          # install deps + production build
.\scripts\build_frontend.ps1 -Dev     # install deps + Vite hot-reload dev server
```

Then in a **separate terminal**, start FastAPI as usual:
```powershell
python start.py
```

| Mode | URL | Notes |
|------|-----|-------|
| Dev  | http://localhost:5173 | Hot-reload; API proxied to :8000 |
| Prod | http://localhost:8000 | FastAPI serves the compiled `dist/` |

---

## Manual Steps

```powershell
cd frontend-react
npm install          # first time only
npm run dev          # development (Vite)
npm run build        # production build → dist/
npm run preview      # preview the production build locally
```

---

## Architecture

```
frontend-react/
├── index.html                  # Vite entry HTML (mounts #root)
├── vite.config.js              # Vite config: dev proxy, aliases, build output
├── package.json
├── .env.example                # copy to .env.local for local overrides
│
└── src/
    ├── main.jsx                # React entry point — mounts <App />
    ├── App.jsx                 # BrowserRouter + context providers + routes
    │
    ├── api/                    # ── Service Layer (Dependency Inversion) ──
    │   ├── client.js           # Base fetch wrapper: auth headers, token refresh, ApiError
    │   ├── authApi.js          # /auth/* endpoints
    │   ├── kundliApi.js        # /kundli/* endpoints
    │   └── walletApi.js        # /wallet/*, /payment/* endpoints
    │
    ├── context/                # ── Global State (React Context) ──
    │   ├── AuthContext.jsx     # user, login(), logout(), refreshUser()
    │   ├── WalletContext.jsx   # balanceCents, refresh(), deduct()
    │   └── SessionContext.jsx  # reading session state, step machine, STEPS enum
    │
    ├── components/
    │   ├── ui/                 # ── Atomic Design System ──
    │   │   ├── Button.jsx      # primary|secondary|ghost|danger|gold variants
    │   │   ├── Input.jsx       # labelled input + Select wrapper
    │   │   ├── Card.jsx        # dark glass-morphism surface
    │   │   ├── Modal.jsx       # accessible dialog (focus trap, Escape key)
    │   │   ├── Spinner.jsx     # full-screen or inline loading indicator
    │   │   └── ErrorMessage.jsx# error|success|info|warning alert banner
    │   │
    │   ├── auth/               # ── Auth Forms ──
    │   │   ├── LoginForm.jsx
    │   │   ├── RegisterForm.jsx
    │   │   └── ForgotPasswordForm.jsx
    │   │
    │   ├── kundli/             # ── Reading Flow Steps ──
    │   │   ├── BirthDetailsStep.jsx   # Form → POST /kundli/start
    │   │   ├── PredictionsStep.jsx    # Confirm/correct → POST /kundli/refine/
    │   │   ├── RefiningStep.jsx       # Loading screen with animated messages
    │   │   └── ReadingResultStep.jsx  # Reading text + Q&A chat + report actions
    │   │
    │   ├── wallet/
    │   │   └── WalletModal.jsx        # Top-up modal with package selection
    │   │
    │   └── layout/
    │       └── AppHeader.jsx          # Sticky header: logo, step progress, wallet, logout
    │
    ├── pages/                  # ── Route-level page components ──
    │   ├── AuthPage.jsx        # Login / Register / ForgotPassword tabs
    │   ├── ReadingPage.jsx     # Step machine: BIRTH → CHART → REFINING → READING
    │   └── ResetPasswordPage.jsx
    │
    ├── utils/
    │   └── formatters.js       # formatCents(), formatDate(), escHtml(), truncate()
    │
    └── styles/
        └── index.css           # CSS custom properties (design tokens) + global reset
```

---

## SOLID Principles Applied

| Principle | Where |
|-----------|-------|
| **SRP** — Single Responsibility | Each file owns one thing: `client.js` = HTTP only, `AuthContext` = auth state only, `BirthDetailsStep` = birth form only |
| **OCP** — Open/Closed | Button variants via `variant` prop; new API endpoints added to `*Api.js` files without touching callers |
| **LSP** — Liskov Substitution | `WalletLocalFallback` and `WalletServiceClient` share the same interface — the backend swap is transparent |
| **ISP** — Interface Segregation | Three separate API files (`authApi`, `kundliApi`, `walletApi`) — components import only what they need |
| **DIP** — Dependency Inversion | Components consume `useAuth()` / `useWallet()` hooks and `*Api.js` functions — never raw `fetch()` |

---

## Routes

| Path | Component | Guard |
|------|-----------|-------|
| `/` | `AuthPage` | Public — redirects to `/reading` if logged in |
| `/reading` | `ReadingPage` | **Protected** — redirects to `/` if not logged in |
| `/reset-password?token=…` | `ResetPasswordPage` | Public |
| `*` | → redirect `/` | — |

---

## Reading Flow (Step Machine)

```
AUTH → BIRTH → CHART → REFINING → READING
                 ↑         ↓ (on error)
                 └─────────┘
```

Steps are defined in `SessionContext.STEPS` and driven by `goToStep()`.
`ReadingPage.jsx` is a pure switch that renders the correct step component.

---

## Environment Variables

Copy `.env.example` → `.env.local`:

```bash
VITE_API_BASE_URL=        # leave empty — Vite proxy handles it in dev
VITE_GOOGLE_CLIENT_ID=    # optional: enables "Sign in with Google"
```

---

## Dev Proxy (vite.config.js)

In dev mode, Vite proxies these paths to `http://localhost:8000`:
`/auth`, `/kundli`, `/wallet`, `/payment`, `/admin`, `/health`, `/share`

No CORS configuration needed during development.

---

## Production Build

`npm run build` outputs to `frontend-react/dist/`.
FastAPI auto-detects this directory (via `_ACTIVE_FRONT` in `backend/api/main.py`) and
serves it in preference to the legacy `frontend/` directory.

Hashed asset filenames (`dist/assets/index-abc123.js`) enable long-term browser caching.
