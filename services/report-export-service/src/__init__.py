"""
report-export-service
=====================
Generates, stores, and distributes Vedic astrology reading reports.

Formats:
  PDF   — fpdf2-based; fully implemented
  DOCX  — python-docx; Phase 1-C
  HTML  — print-optimised; Phase 2

Storage:
  Local disk (dev) → S3 presigned URLs (production, Phase 1-C)

Modules:
  generators/pdf_generator.py  — fpdf2 PDF builder
  generators/docx_generator.py — python-docx builder (Phase 1-C)
  storage/local_storage.py     — Dev filesystem storage
  storage/s3_client.py         — AWS S3 (Phase 1-C)
  api/main.py                  — FastAPI routes
"""
