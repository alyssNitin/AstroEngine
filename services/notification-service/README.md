# notification-service

**Microservice for all outbound communications: email, push notifications, and in-app alerts.**

All notifications are dispatched asynchronously via a message queue (SQS / RabbitMQ). Templates are i18n-aware (English / Hindi / Tamil). The service is the single egress point for all user-facing communications — other services never send emails or push notifications directly.

---

## Responsibilities

| Responsibility | Detail |
|---|---|
| Email delivery | SMTP (dev) / AWS SES (production) with console fallback |
| Email templates | Verification, welcome, receipt, low-balance, password reset |
| Push notifications | 🚧 Firebase FCM for iOS + Android |
| In-app alerts | 🚧 Stored notification objects fetched by frontend |
| i18n templates | All templates available in English / Hindi / Tamil |
| Async consumption | Consumes messages from SQS queue |

---

## API Endpoints (Internal only — not exposed via API Gateway)

| Method | Path | Description |
|---|---|---|
| `POST` | `/notify/email` | Send templated email to a user |
| `POST` | `/notify/push` | 🚧 Send FCM push notification |
| `GET`  | `/notify/alerts/{user_id}` | 🚧 Fetch unread in-app alerts |

---

## Email Templates

| Template Key | Trigger | Languages |
|---|---|---|
| `email_verification` | Registration | en, hi, ta |
| `welcome` | First verification | en, hi, ta |
| `payment_receipt` | Successful top-up | en, hi, ta |
| `low_balance` | Balance ≤ threshold | en, hi, ta |
| `password_reset` | Forgot-password request | en, hi, ta |
| `reading_ready` | AI report completed | en, hi, ta |
| `weekly_digest` | Admin weekly report | en |

---

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `EMAIL_PROVIDER` | `smtp` | `smtp` or `ses` |
| `EMAIL_HOST` | — | SMTP server hostname |
| `EMAIL_PORT` | `587` | SMTP port (TLS) |
| `EMAIL_USER` | — | SMTP username |
| `EMAIL_PASSWORD` | — | App Password (Gmail) or SMTP credential |
| `FROM_EMAIL` | — | Sender email address |
| `AWS_SES_REGION` | `ap-south-1` | SES region (production) |
| `FCM_SERVER_KEY` | — | 🚧 Firebase Cloud Messaging key |
| `SQS_QUEUE_URL` | — | 🚧 SQS queue to consume |
| `API_PORT` | `8008` | Listen port |

---

## Implementation Status

| Feature | Status |
|---|---|
| SMTP email (verification, receipt, low-balance) | ✅ Implemented |
| Console fallback when SMTP not configured | ✅ Implemented |
| Gmail App Password support | ✅ Implemented |
| i18n email templates | 🚧 Phase 1-B |
| Firebase FCM push | 🚧 Phase 2 |
| SQS consumer | 🚧 Phase 2 |
| In-app alerts | 🚧 Phase 2 |

---

## Module Structure

```
services/notification-service/
├── src/
│   ├── email/
│   │   ├── email_service.py   # EmailService class (existing implementation)
│   │   ├── smtp_client.py     # SMTP connection pool
│   │   └── ses_client.py      # 🚧 AWS SES client
│   ├── push/
│   │   └── fcm_client.py      # 🚧 Firebase FCM sender
│   └── templates/
│       ├── en/                # English email templates (HTML + text)
│       ├── hi/                # Hindi email templates
│       └── ta/                # Tamil email templates
├── requirements.txt
├── Dockerfile
└── README.md
```
