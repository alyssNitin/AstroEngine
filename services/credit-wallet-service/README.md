# credit-wallet-service

**Microservice for credit wallet management, atomic balance operations, and immutable ledger.**

Every credit transaction on the platform flows through this service. Atomicity is guaranteed via database transactions — partial writes are impossible. The ledger table is write-once (append-only) to provide a full immutable audit trail.

---

## Responsibilities

| Responsibility | Detail |
|---|---|
| Balance inquiry | Returns paid_balance + promo_balance + total per user |
| Credit deduction | Atomic deduction for report/chat; promo credits consumed first |
| Credit addition | After payment confirmation via SQS message |
| Welcome credit | Awarded on first email verification; region-aware amount |
| Promo credits | Separate promo_balance column; consumed before paid balance |
| Refund | Auto-reverse on AI failure (within 60 seconds) |
| Ledger | Immutable append-only `wallet_ledger` table with `balance_after` snapshot |
| Low-balance alert | Triggers notification-service when balance ≤ threshold |
| Transaction history | Paginated ledger with type, amount, description, timestamp |

---

## API Endpoints

| Method | Path | Auth | Description |
|---|---|---|---|
| `GET`  | `/wallet/balance` | JWT | Paid + promo + total balance |
| `POST` | `/wallet/deduct` | Internal | Atomic credit deduction |
| `POST` | `/wallet/credit` | Internal | Credit wallet (from payment webhook) |
| `POST` | `/wallet/refund` | Internal | Reverse a deduction by transaction ID |
| `GET`  | `/wallet/transactions` | JWT | Paginated ledger history |
| `GET`  | `/wallet/transactions/{id}` | JWT | Single transaction detail |

> **Internal endpoints** are not exposed via the API Gateway — only callable by other services over the internal service mesh.

---

## Database Schema

### credit_wallets
| Column | Type | Notes |
|---|---|---|
| `id` | UUID | Primary key |
| `user_id` | UUID | FK → users.id; unique (one wallet per user) |
| `paid_balance` | INTEGER | Minor units (paise / cents) — purchased credits |
| `promo_balance` | INTEGER | Promotional / welcome credits |
| `updated_at` | TIMESTAMPTZ | Optimistic locking check |

### wallet_ledger *(immutable — append only)*
| Column | Type | Notes |
|---|---|---|
| `id` | UUID | Primary key |
| `wallet_id` | UUID | FK → credit_wallets |
| `type` | ENUM | `purchase`, `consumed`, `refund`, `promo`, `welcome` |
| `credits_delta` | INTEGER | Signed value: +addition, -deduction (minor units) |
| `reason` | VARCHAR | Human-readable label |
| `balance_after` | INTEGER | Running balance snapshot at time of write |
| `created_at` | TIMESTAMPTZ | Write-once; set by DB default |

> **Note**: Current implementation stores transactions as a JSON array in the `users.wallet_transactions` column. Migration to this normalised schema is a Phase 1-B priority.

---

## Region-Aware Pricing

All amounts are stored as **integer minor units** to avoid floating-point rounding:

| Region | Unit | Welcome | Report | Chat |
|---|---|---|---|---|
| India | Paise (1₹ = 100p) | 10,000 (₹100) | 10,000 (₹100) | 2,500 (₹25) |
| International | Cents (1$ = 100¢) | 100 ($1.00) | 100 ($1.00) | 100 ($1.00) |

Top-up tiers with bonus:

| Region | Paid | Credited | Bonus |
|---|---|---|---|
| India Tier 1 | ₹99 | ₹110 | ~11% |
| India Tier 2 | ₹249 | ₹300 | ~20% |
| Intl Tier 1 | $10 | $11 | 10% |
| Intl Tier 2 | $25 | $30 | 20% |

---

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `DB_URL` | **required** | PostgreSQL connection string |
| `REDIS_URL` | — | Redis for rate limiting |
| `NOTIFICATION_SERVICE_URL` | `http://notification-service:8008` | For low-balance alerts |
| `LOW_BALANCE_THRESHOLD_PAISE` | `3000` | Alert trigger (₹30) |
| `LOW_BALANCE_THRESHOLD_CENTS` | `300` | Alert trigger ($3.00) |
| `API_HOST` | `0.0.0.0` | |
| `API_PORT` | `8004` | |

---

## How to Run

```bash
pip install -r requirements.txt
uvicorn src.api.main:app --host 0.0.0.0 --port 8004 --reload
```

---

## Module Structure

```
services/credit-wallet-service/
├── src/
│   ├── wallet/
│   │   ├── wallet.py          # WalletService — balance, deduct, credit, refund
│   │   └── pricing.py         # get_pricing(region) — constants + formatting
│   ├── ledger/
│   │   ├── database.py        # DB access (SQLite now → PostgreSQL target)
│   │   └── ledger.py          # Append-only ledger writer
│   ├── alerts/
│   │   └── low_balance.py     # Checks threshold after each deduction; triggers notify
│   └── api/
│       ├── main.py
│       └── schemas.py
├── requirements.txt
├── Dockerfile
└── README.md
```
