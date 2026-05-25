# analytics-service

**Microservice for platform analytics, metrics aggregation, and the Super Admin dashboard.**

Aggregates anonymised usage metrics, revenue data, and system health indicators. Powers the admin dashboard with both real-time and historical views. Runs scheduled Celery tasks for periodic reports.

---

## Responsibilities

| Responsibility | Detail |
|---|---|
| Traffic metrics | DAU, MAU, registrations, report generations |
| Revenue metrics | Payments by gateway, pack, region, date range |
| System health | API latency p50/p95/p99, error rates, uptime |
| LLM cost tracking | Token usage and cost per report type |
| CSV/Excel export | Admin can export any metric table |
| Weekly digest | Automated email report every Monday morning |
| Admin dashboard | Read-only aggregated views (no raw PII) |

---

## API Endpoints (Admin-only)

| Method | Path | Auth | Description |
|---|---|---|---|
| `GET` | `/admin/analytics/traffic` | Admin | User traffic with date range filter |
| `GET` | `/admin/analytics/revenue` | Admin | Revenue breakdown by pack/gateway/region |
| `GET` | `/admin/analytics/llm-costs` | Admin | LLM token usage and cost breakdown |
| `GET` | `/admin/analytics/system-health` | Admin | Latency, error rates, uptime |
| `GET` | `/admin/analytics/export` | Admin | CSV/Excel export of any metric |
| `GET` | `/admin/stats` | Admin | Quick summary stats (existing implementation) |

---

## Implementation Status

| Feature | Status |
|---|---|
| Basic stats (user count, revenue total) | ✅ Implemented in admin panel |
| LLM API call logging | ✅ Implemented |
| Celery async tasks | 🚧 Phase 2 |
| OpenSearch storage | 🚧 Phase 2 |
| Traffic charts | 🚧 Phase 2 |
| Weekly digest email | 🚧 Phase 2 |

---

## Module Structure

```
services/analytics-service/
├── src/
│   ├── collectors/
│   │   ├── events.py          # Event ingestion from other services
│   │   └── llm_costs.py       # Token + cost log aggregation
│   ├── aggregators/
│   │   ├── traffic.py         # User activity aggregations
│   │   ├── revenue.py         # Payment aggregations
│   │   └── health.py          # System health metrics
│   └── api/
│       ├── main.py
│       └── schemas.py
├── requirements.txt
├── Dockerfile
└── README.md
```
