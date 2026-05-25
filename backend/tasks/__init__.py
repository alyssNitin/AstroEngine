"""backend/tasks — Celery async task queue for NarayanAstroReader.

B8: PDF generation runs as a Celery background task so the HTTP request
returns immediately (202 Accepted + task_id) rather than blocking for
potentially 10–30 seconds while fpdf2 renders the report.

Architecture §8 / SRS §4.2:
  - POST /export/{session_id}/pdf/async  → 202 {"task_id": "<uuid>"}
  - GET  /export/status/{task_id}        → {"status": "pending|started|success|failure",
                                             "result_url": "/export/download/<task_id>"}
  - GET  /export/download/{task_id}      → PDF binary (when complete)
"""
