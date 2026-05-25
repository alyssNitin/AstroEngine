# ─────────────────────────────────────────────────────────────────────────────
# notification-service — Multi-stage Dockerfile
# ─────────────────────────────────────────────────────────────────────────────

# Stage 1: Build dependencies in an isolated layer
FROM python:3.11-slim AS builder

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc g++ make libffi-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN python -m venv /opt/venv && \
    /opt/venv/bin/pip install --upgrade pip && \
    /opt/venv/bin/pip install --no-cache-dir -r requirements.txt

# Stage 2: Lean runtime image
FROM python:3.11-slim AS runtime

# Security: non-root user
RUN groupadd -r appuser && useradd -r -g appuser appuser

WORKDIR /app

# Copy venv and source
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copy service source + shared utilities
COPY src/ ./src/
COPY start.py ./start.py
# shared/ is copied from the services/ parent directory (see docker-compose build context)
# When building standalone: docker build --build-arg SHARED=../shared .
COPY shared/ ./shared/ 2>/dev/null || true

USER appuser

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import httpx; httpx.get('http://localhost:${PORT:-8002}/health').raise_for_status()"

CMD ["python", "start.py"]
