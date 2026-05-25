# payment-gateway-service

**PCI-DSS-scoped microservice for payment processing. Handles Razorpay (India / UPI) and Stripe (International) integrations.**

Card data **never touches this service's servers** — the gateway provider hosts the card entry form via an embeddable iframe/checkout.js. This service only handles order creation, HMAC-verified webhook receipt, and instructing `credit-wallet-service` to credit the user's wallet.

---

## Responsibilities

| Responsibility | Detail |
|---|---|
| Geo-based pricing | Returns correct INR/USD pack prices based on user's region |
| Order creation | Creates Razorpay order / Stripe PaymentIntent; returns to frontend |
| Webhook receipt | Verifies HMAC signature; idempotent (duplicate webhooks safe) |
| Credit instruction | Publishes to SQS / calls credit-wallet-service after confirmed payment |
| Payment history | Records each order with status (pending/success/failed) |
| Receipt generation | Triggers email receipt via notification-service |
| UPI flow | UPI VPA validation, QR code generation, deep-link intent |

---

## API Endpoints

| Method | Path | Auth | Description |
|---|---|---|---|
| `GET`  | `/payment/packs` | JWT | Geo-priced credit pack list for user's region |
| `POST` | `/payment/order` | JWT | Create payment order → gateway order_id |
| `POST` | `/payment/webhook` | HMAC-Sig | Razorpay / Stripe payment confirmation webhook |
| `GET`  | `/payment/history` | JWT | User's purchase history |
| `GET`  | `/payment/receipt/{order_id}` | JWT | Download PDF receipt |

---

## Payment Flows

### Card (Razorpay Checkout.js / Stripe.js)

```
User clicks "Buy Credits"
    → POST /payment/order  →  gateway creates order, returns order_id + key
    → Frontend loads gateway's hosted checkout (card data stays with gateway)
    → User completes 3DS
    → Gateway sends webhook to POST /payment/webhook
    → Service verifies HMAC signature
    → Publishes credit grant to SQS → credit-wallet-service adds credits
    → Notification-service sends email receipt
```

### UPI (India only)

```
User clicks "Pay via UPI"
    → POST /payment/order  →  returns UPI VPA, QR code, deep-link
    → User scans QR or opens UPI app
    → UPI gateway confirms payment → webhook → same webhook handler
```

---

## Credit Packs

| Pack | Region | Price | Credits | Bonus |
|---|---|---|---|---|
| Starter | India | ₹99 | ₹110 | ~11% |
| Standard | India | ₹249 | ₹300 | ~20% |
| Starter | Intl | $10 | $11 | 10% |
| Standard | Intl | $25 | $30 | 20% |

---

## Webhook Security

All incoming webhooks are verified before processing:

```python
# Razorpay
expected = hmac.new(key_secret, f"{order_id}|{payment_id}", sha256).hexdigest()
assert expected == razorpay_signature  # Reject if mismatch

# Stripe
event = stripe.Webhook.construct_event(payload, sig_header, webhook_secret)
```

Idempotency: each `gateway_order_id` is stored in `payment_orders` table. Duplicate webhook → return 200 (already processed).

---

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `PAYMENT_GATEWAY` | `razorpay` | Active gateway: `razorpay` or `stripe` |
| `RAZORPAY_KEY_ID` | — | Razorpay API key ID |
| `RAZORPAY_KEY_SECRET` | — | Razorpay secret (HMAC signing) |
| `STRIPE_SECRET_KEY` | — | Stripe secret key |
| `STRIPE_WEBHOOK_SECRET` | — | Stripe webhook signing secret |
| `WALLET_SERVICE_URL` | `http://credit-wallet-service:8004` | Internal credit grant URL |
| `SQS_QUEUE_URL` | — | Optional SQS queue for async credit grants |
| `DB_URL` | **required** | PostgreSQL connection |
| `API_PORT` | `8005` | Listen port |

---

## Implementation Status

| Feature | Status |
|---|---|
| Geo-pricing API | ✅ Implemented |
| Mock payment UI (UPI/Card/NetBanking) | ✅ In frontend |
| Razorpay order creation (real SDK) | 🚧 Stub — Phase 1-C |
| Stripe PaymentIntent (real SDK) | 🚧 Stub — Phase 1-C |
| HMAC webhook verification | 🚧 Stub — Phase 1-C |
| Idempotent webhook handler | 🚧 Phase 1-C |
| UPI QR + deep-link | 🚧 Phase 1-C |
| SQS async credit grant | 🚧 Phase 2 |
| PDF receipt | 🚧 Phase 2 |

---

## Module Structure

```
services/payment-gateway-service/
├── src/
│   ├── adapters/
│   │   ├── base_adapter.py        # AbstractPaymentAdapter interface
│   │   ├── gateway.py             # Dispatcher — selects Razorpay or Stripe
│   │   ├── razorpay_adapter.py    # 🚧 Razorpay SDK integration
│   │   └── stripe_adapter.py      # 🚧 Stripe SDK integration
│   ├── upi/
│   │   ├── vpa_validator.py       # UPI VPA format validation
│   │   └── qr_generator.py        # UPI QR code generation
│   ├── webhooks/
│   │   ├── handler.py             # Idempotent webhook processor
│   │   └── verifier.py            # HMAC signature verification
│   ├── geo_pricing/
│   │   └── pricing.py             # get_packs(region) — pack definitions
│   └── api/
│       ├── main.py
│       └── schemas.py
├── requirements.txt
├── Dockerfile
└── README.md
```

---

## PCI-DSS Compliance Notes

- Card numbers, CVV, expiry **never** pass through this service
- Gateway-hosted checkout/iframe is used exclusively
- This service only receives a `payment_id` token after completion
- No card data stored — `payment_orders` table stores only gateway reference IDs
