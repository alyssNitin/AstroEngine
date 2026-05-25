# report-export-service

**Microservice for generating, storing, and sharing Vedic astrology reading reports.**

Produces PDF and DOCX exports of completed AI readings. Stores generated files in object storage (S3/GCS) and returns presigned URLs. Supports shareable expirable links for free access without login.

---

## Responsibilities

| Responsibility | Detail |
|---|---|
| PDF generation | Formatted report with branding, sections, and kundli summary |
| DOCX generation | 🚧 Word document export for Pro users |
| Object storage | Uploads to S3; returns presigned URL (24h default) |
| Email delivery | Triggers notification-service to email the PDF |
| Share link | Generates signed token URL with configurable expiry |
| Print layout | Print-optimised CSS for browser-based printing |

---

## API Endpoints

| Method | Path | Auth | Description |
|---|---|---|---|
| `POST` | `/export/{report_id}/pdf` | JWT | Generate PDF; returns presigned S3 URL |
| `POST` | `/export/{report_id}/docx` | JWT | 🚧 Generate DOCX |
| `POST` | `/export/{report_id}/email` | JWT | Generate PDF and email to user |
| `POST` | `/export/{report_id}/share` | JWT | Create shareable expiring link |
| `GET`  | `/export/shared/{share_token}` | Public | Serve shared report (token validated) |

---

## PDF Report Sections

1. Cover page — Name, date, platform branding
2. Birth Details — DOB, TOB, Place, Ayanamsa
3. Lagna (Ascendant) — Sign, nakshatra, pada
4. Planet Positions — D1 Rasi chart table
5. Key Dashas — Current Mahadasha + Antardasha
6. AI Deep Reading — Full multi-section narrative
7. Appendix — Divisional chart summary

---

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `S3_BUCKET` | — | S3 bucket name for report storage |
| `S3_REGION` | `ap-south-1` | AWS region |
| `AWS_ACCESS_KEY_ID` | — | AWS credentials |
| `AWS_SECRET_ACCESS_KEY` | — | AWS credentials |
| `PRESIGNED_URL_TTL_SEC` | `86400` | Presigned URL expiry (24h) |
| `SHARE_LINK_TTL_HOURS` | `72` | Share link token expiry |
| `NOTIFICATION_SERVICE_URL` | `http://notification-service:8008` | For email delivery |
| `API_PORT` | `8006` | Listen port |

---

## Implementation Status

| Feature | Status |
|---|---|
| PDF generation (fpdf2) | ✅ Implemented |
| Email PDF to user | ✅ Implemented |
| DOCX generation | 🚧 Phase 1-C |
| S3 storage | 🚧 Phase 1-C |
| Shareable expirable links | 🚧 Phase 1-C |
| Print-optimised HTML layout | 🚧 Phase 2 |

---

## Module Structure

```
services/report-export-service/
├── src/
│   ├── generators/
│   │   ├── pdf_generator.py   # fpdf2-based PDF builder
│   │   └── docx_generator.py  # 🚧 python-docx builder
│   ├── storage/
│   │   ├── s3_client.py       # 🚧 boto3 upload + presign
│   │   └── local_storage.py   # Fallback for dev (saves to disk)
│   └── api/
│       ├── main.py
│       └── schemas.py
├── requirements.txt
├── Dockerfile
└── README.md
```
