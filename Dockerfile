# ── NarayanAstroReader — Production Dockerfile ────────────────────────────────
FROM python:3.11-slim

# System dependencies (psycopg2 needs libpq)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev gcc && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies first (layer-cacheable)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create a non-root user for security
RUN useradd -m -u 1001 narayan && chown -R narayan:narayan /app
USER narayan

# Environment defaults (override in production via .env or secrets manager)
ENV ENVIRONMENT=production \
    API_HOST=0.0.0.0 \
    API_PORT=8000 \
    PYTHONUNBUFFERED=1

EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"

CMD ["python", "-m", "uvicorn", "backend.api.main:app", \
     "--host", "0.0.0.0", "--port", "8000", \
     "--workers", "2", "--log-level", "info"]
