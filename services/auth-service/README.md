# auth-service

**Microservice for user authentication, identity management, and session lifecycle.**

Handles registration, login, OAuth (Google/Apple), email verification, password management, 2FA/MFA, and JWT issuance. All other services validate tokens issued by this service.

---

## Responsibilities

| Responsibility | Detail |
|---|---|
| Registration | Email/password with bcrypt hashing |
| Email verification | Token-based email link; re-verify soft-response |
| Login | Validates credentials; issues JWT access + refresh tokens |
| Guest mode | Anonymous session with limited free chat turns |
| OAuth | Google + Apple (🚧 planned Phase 1-C) |
| 2FA / MFA | TOTP via pyotp (🚧 planned Phase 1-C; mandatory for admins) |
| JWT lifecycle | Access: 15 min TTL; Refresh: 7 days; rotated on use |
| Password reset | Forgot-password email flow (🚧 planned) |
| Region detection | IP-based geolocation at registration for pricing |

---

## API Endpoints

| Method | Path | Auth | Description |
|---|---|---|---|
| `POST` | `/auth/register` | Public | Register with email + password |
| `POST` | `/auth/login` | Public | Login; returns access + refresh tokens |
| `POST` | `/auth/guest` | Public | Create anonymous guest session |
| `GET`  | `/auth/verify-email` | Public | Verify email via token link |
| `POST` | `/auth/resend-verification` | Public | Resend verification email |
| `POST` | `/auth/refresh` | Refresh token | Rotate access token |
| `POST` | `/auth/logout` | JWT | Invalidate session |
| `POST` | `/auth/forgot-password` | Public | 🚧 Send password reset email |
| `POST` | `/auth/reset-password` | Public | 🚧 Consume reset token |
| `POST` | `/auth/oauth/{provider}` | Public | 🚧 OAuth callback (google/apple) |
| `POST` | `/auth/mfa/setup` | JWT | 🚧 Enable TOTP 2FA |
| `POST` | `/auth/mfa/verify` | JWT | 🚧 Verify TOTP code |

---

## JWT Token Lifecycle

```
Register/Login
     │
     ▼
auth-service issues:
  access_token  (JWT, 15 min, HS256)
  refresh_token (opaque, 7 days, stored in Redis)
     │
     ▼
Client sends: Authorization: Bearer <access_token>
     │
     ▼
Any service validates token locally (shared JWT_SECRET)
     │
     ▼
On expiry: POST /auth/refresh with refresh_token
  → New access_token issued
  → Refresh token rotated (old invalidated)
```

---

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `JWT_SECRET` | **required** | HMAC-SHA256 signing secret (min 32 chars) |
| `JWT_ACCESS_TTL_MIN` | `15` | Access token TTL in minutes |
| `JWT_REFRESH_TTL_DAYS` | `7` | Refresh token TTL in days |
| `DB_URL` | **required** | PostgreSQL connection string |
| `REDIS_URL` | **required** | Redis URL for refresh token storage |
| `SMTP_HOST` | — | SMTP server for verification emails |
| `SMTP_USER` | — | SMTP username |
| `SMTP_PASSWORD` | — | SMTP password (App Password for Gmail) |
| `VERIFICATION_BASE_URL` | — | Base URL for email verification link |
| `API_HOST` | `0.0.0.0` | Listen host |
| `API_PORT` | `8000` | Listen port |

---

## Current Implementation vs Target

| Feature | Current State | Target |
|---|---|---|
| Email/password registration | ✅ Working | ✅ |
| Email verification | ✅ Working | ✅ |
| Welcome credit on verify | ✅ Working | ✅ |
| Guest mode | ✅ Working | ✅ |
| JWT tokens | ❌ Uses email+session_id | 🚧 Phase 1-B |
| OAuth Google/Apple | ❌ Not built | 🚧 Phase 1-C |
| 2FA / TOTP | ❌ Not built | 🚧 Phase 1-C |
| Password reset | ❌ Not built | 🚧 Phase 1-B |
| Redis session store | ❌ Not connected | 🚧 Phase 1-C |
| PostgreSQL | ❌ Uses SQLite | 🚧 Phase 1-C |

---

## How to Run (Local Dev)

```bash
pip install -r requirements.txt
export JWT_SECRET=your-super-secret-key-here
export DB_URL=postgresql://user:pass@localhost/narayan
uvicorn src.api.main:app --host 0.0.0.0 --port 8000 --reload
```

---

## Module Structure

```
services/auth-service/
├── src/
│   ├── controllers/
│   │   ├── auth.py            # Registration, login, logout handlers
│   │   ├── verification.py    # Email verify + resend handlers
│   │   └── mfa.py             # 🚧 2FA setup/verify handlers
│   ├── middleware/
│   │   ├── jwt_validator.py   # FastAPI dependency — validates Bearer token
│   │   └── rate_limiter.py    # 🚧 Rate limiting (5 req/min on login)
│   ├── models/
│   │   ├── user.py            # User ORM model (SQLAlchemy)
│   │   └── schemas.py         # Pydantic request/response schemas
│   └── utils/
│       ├── email_service.py   # SMTP email with console fallback
│       ├── jwt_utils.py       # 🚧 JWT sign/verify helpers
│       └── password.py        # bcrypt hash + verify
├── requirements.txt
├── Dockerfile
└── README.md
```

---

## Security Notes

- Passwords hashed with **bcrypt** (cost factor 12)
- Refresh tokens stored in **Redis** (not DB) — instantly revocable
- All auth endpoints are **rate-limited** to prevent brute force
- Email verification tokens expire after **24 hours**
- Password reset tokens expire after **1 hour**
- Admin accounts will require **2FA** (Phase 1-C)
