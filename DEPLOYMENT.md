# NarayanAstroReader — Deployment Guide

## Architecture Overview

NarayanAstroReader is a **monolith-first** application:
all backend logic lives in a single FastAPI process backed by PostgreSQL,
Redis, and optionally an S3-compatible object store.
The monolith is structured in clean modules (`backend/auth/`, `backend/api/`,
`backend/kundli_engine/`, `backend/persistence/`, `backend/ai_interpretation/`)
so individual modules can be extracted to microservices later without rewrites.

```
┌─────────────────────────────────────────────────────────┐
│  Reverse Proxy  (Nginx / Caddy / AWS ALB)               │
│  TLS termination · Static asset serving · Rate limit    │
└───────────────────────────┬─────────────────────────────┘
                            │ HTTP/2
┌───────────────────────────▼─────────────────────────────┐
│  FastAPI Application  (Uvicorn workers)                  │
│  backend/api/main.py  — all REST + SSE endpoints         │
│  Gunicorn supervisor recommended for production          │
└──────┬──────────────────────────────────────────┬────────┘
       │                                          │
┌──────▼──────┐    ┌────────────┐    ┌────────────▼───────┐
│ PostgreSQL  │    │   Redis    │    │  Anthropic API     │
│ (primary    │    │  Sessions  │    │  (Claude)          │
│  + replica) │    │  + JWT BL  │    └────────────────────┘
└─────────────┘    └────────────┘
       │
┌──────▼──────┐
│ S3 / Local  │
│ Report store│
└─────────────┘
```

---

## Prerequisites

| Component     | Minimum version | Notes                            |
|---------------|-----------------|----------------------------------|
| Python        | 3.11            | 3.12 works; 3.10 breaks `X \| Y` type hints |
| PostgreSQL    | 14              | 15/16 preferred                  |
| Redis         | 6.2             | 7.x recommended                  |
| pyswisseph    | 2.10+           | Installed by pip                 |
| PyJHora       | latest main     | Sibling directory `../PyJHora`   |

---

## Environment Variables (`.env`)

Copy `.env.example` to `.env` and fill in all values.
**Never commit `.env` to version control.**

```bash
# Required — must be strong random values in production
JWT_SECRET=<hex string, min 64 chars>
ADMIN_SECRET=<hex string, min 64 chars>
FIELD_ENCRYPTION_KEY=<base64 Fernet key — generate with scripts/gen_keys.py>

# Database
DATABASE_URL=postgresql://narayan:STRONGPASSWORD@localhost:5432/narayan_astro

# AI
ANTHROPIC_API_KEY=sk-ant-...
ANTHROPIC_MODEL=claude-sonnet-4-6

# Redis
REDIS_URL=redis://localhost:6379/0

# Email (SMTP)
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your@gmail.com
SMTP_PASSWORD=<app password>

# Google OAuth (optional)
GOOGLE_CLIENT_ID=...apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=...

# Object Storage (optional — falls back to local ./reports/)
S3_BUCKET=narayan-reports
S3_REGION=ap-south-1
S3_ACCESS_KEY=...
S3_SECRET_KEY=...

# Deployment mode
ENVIRONMENT=production
```

### Generating secrets

```bash
python3 scripts/gen_keys.py
# Outputs ready-to-paste lines for JWT_SECRET, ADMIN_SECRET, FIELD_ENCRYPTION_KEY
```

---

## Local Development

```bash
# 1. Clone repos side-by-side
git clone https://github.com/yourorg/NarayanAstroReader
git clone https://github.com/yourorg/PyJHora

# 2. Create virtualenv
cd NarayanAstroReader
python3 -m venv .venv && source .venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt --break-system-packages

# 4. Start PostgreSQL + Redis (Docker Compose)
docker compose up -d db redis

# 5. Copy and configure .env
cp .env.example .env   # edit with your values

# 6. Start the API
uvicorn backend.api.main:app --reload --port 8000

# 7. Open frontend
open frontend/index.html
# or serve:
python3 -m http.server 3000 --directory frontend
```

---

## Docker Deployment (Single Server)

```bash
# Build
docker build -t narayan-astro:latest .

# Run with environment file
docker run -d \
  --name narayan-astro \
  --env-file .env \
  -p 8000:8000 \
  -v $(pwd)/reports:/app/reports \
  narayan-astro:latest
```

### Docker Compose (full stack)

```yaml
# docker-compose.prod.yml
version: "3.9"
services:
  app:
    image: narayan-astro:latest
    env_file: .env
    ports:
      - "8000:8000"
    depends_on:
      db:
        condition: service_healthy
      redis:
        condition: service_started
    volumes:
      - reports:/app/reports
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 10s
      retries: 3

  db:
    image: postgres:16-alpine
    environment:
      POSTGRES_DB: narayan_astro
      POSTGRES_USER: narayan
      POSTGRES_PASSWORD: ${DB_PASSWORD}
    volumes:
      - pgdata:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD", "pg_isready", "-U", "narayan"]
      interval: 10s

  redis:
    image: redis:7-alpine
    command: redis-server --appendonly yes
    volumes:
      - redisdata:/data

volumes:
  pgdata:
  redisdata:
  reports:
```

```bash
docker compose -f docker-compose.prod.yml up -d
```

---

## Cloud Deployment

### Option A — AWS (recommended for India traffic)

| Component | AWS Service | Notes |
|-----------|------------|-------|
| App       | ECS Fargate (2 tasks min) | ALB in front |
| Database  | RDS PostgreSQL 16 (db.t4g.medium) | Multi-AZ for HA |
| Redis     | ElastiCache Redis 7 (cache.t4g.small) | |
| Object Store | S3 (`ap-south-1`) | Reports + backups |
| Secrets   | AWS Secrets Manager | Inject at container start |
| TLS       | ACM + ALB | Free certificates |
| CDN       | CloudFront | Serve `frontend/` as SPA |

Estimated monthly cost (India region, low traffic): **~₹4,000–8,000/month**

```bash
# ECR push
aws ecr create-repository --repository-name narayan-astro
docker tag narayan-astro:latest <account>.dkr.ecr.ap-south-1.amazonaws.com/narayan-astro:latest
docker push <account>.dkr.ecr.ap-south-1.amazonaws.com/narayan-astro:latest
```

### Option B — VPS / Bare Metal (Budget option)

Suitable for development or low-traffic production.

```bash
# On Ubuntu 22.04 VPS (4GB RAM minimum)

# Install dependencies
sudo apt update && sudo apt install -y python3.11 python3.11-venv python3-pip \
     postgresql redis-server nginx libpq-dev build-essential

# Clone and setup
git clone https://github.com/yourorg/NarayanAstroReader /opt/narayan
cd /opt/narayan
python3.11 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Configure PostgreSQL
sudo -u postgres createuser narayan
sudo -u postgres createdb narayan_astro -O narayan
sudo -u postgres psql -c "ALTER USER narayan PASSWORD 'STRONGPASSWORD';"

# Systemd service
sudo tee /etc/systemd/system/narayan.service << 'SVC'
[Unit]
Description=NarayanAstroReader API
After=postgresql.service redis.service

[Service]
User=narayan
WorkingDirectory=/opt/narayan
EnvironmentFile=/opt/narayan/.env
ExecStart=/opt/narayan/.venv/bin/gunicorn backend.api.main:app \
    -w 2 -k uvicorn.workers.UvicornWorker \
    --bind 127.0.0.1:8000 \
    --timeout 120 --graceful-timeout 30
Restart=on-failure
RestartSec=5s

[Install]
WantedBy=multi-user.target
SVC

sudo systemctl enable --now narayan

# Nginx reverse proxy
sudo tee /etc/nginx/sites-available/narayan << 'NGINX'
server {
    listen 80;
    server_name yourdomain.com;
    return 301 https://$host$request_uri;
}
server {
    listen 443 ssl http2;
    server_name yourdomain.com;

    ssl_certificate     /etc/letsencrypt/live/yourdomain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/yourdomain.com/privkey.pem;

    # Serve frontend SPA
    root /opt/narayan/frontend;
    index index.html;
    try_files $uri $uri/ /index.html;

    # Proxy API
    location /api/ {
        proxy_pass         http://127.0.0.1:8000/;
        proxy_set_header   Host $host;
        proxy_set_header   X-Real-IP $remote_addr;
        proxy_set_header   X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header   X-Forwarded-Proto $scheme;
        # SSE support
        proxy_buffering    off;
        proxy_cache        off;
        proxy_read_timeout 300s;
    }
}
NGINX

sudo ln -s /etc/nginx/sites-available/narayan /etc/nginx/sites-enabled/
sudo certbot --nginx -d yourdomain.com
sudo nginx -t && sudo systemctl reload nginx
```

---

## Database Migrations

Schema is managed by `init_schema()` in `database.py`.
It is **idempotent** — safe to run on every startup.
New columns are added via `_EVOLVE_COLS` without data loss.

```bash
# Run manually if needed
python3 -c "from backend.persistence.database import init_schema; init_schema(); print('done')"
```

For major schema changes, use Alembic:
```bash
pip install alembic
alembic init alembic
# Edit alembic.ini: sqlalchemy.url = ${DATABASE_URL}
alembic revision --autogenerate -m "description"
alembic upgrade head
```

---

## Health & Monitoring

| Endpoint    | Purpose                        |
|-------------|-------------------------------|
| `GET /health` | Liveness probe (returns `{"status":"ok"}`) |
| `GET /admin/analytics` | Real-time DAU/MAU/revenue metrics |

```bash
# Health check
curl https://yourdomain.com/api/health

# Structured logs (JSON)
export LOG_FORMAT=json   # set in .env for log aggregators (Datadog, CloudWatch)
```

---

## CI/CD

GitHub Actions workflow is at `.github/workflows/ci.yml`:

- **lint**: flake8 (E/W errors, max-line 100)
- **test**: pytest with PostgreSQL + Redis services
- **security**: pip-audit (CVE scan) + bandit (SAST)
- **docker**: build + push to registry on `main` branch merge

Deployments are triggered on merge to `main`.
For zero-downtime deploys, use rolling updates (ECS) or a blue/green nginx swap.

---

## Backup Strategy

```bash
# PostgreSQL — daily dump (add to cron)
pg_dump $DATABASE_URL | gzip > backup_$(date +%Y%m%d).sql.gz

# Upload to S3
aws s3 cp backup_$(date +%Y%m%d).sql.gz s3://narayan-backups/db/

# Redis — RDB snapshot is automatic with appendonly=yes
# Copy /data/dump.rdb periodically
```

---

## Security Checklist (pre-launch)

- [ ] `ENVIRONMENT=production` set in server environment
- [ ] Strong `JWT_SECRET` (64+ hex chars) configured
- [ ] Strong `ADMIN_SECRET` (64+ hex chars) configured
- [ ] `FIELD_ENCRYPTION_KEY` set (Fernet key from `gen_keys.py`)
- [ ] TLS certificate installed and HTTP → HTTPS redirect active
- [ ] PostgreSQL not exposed to internet (firewall rule)
- [ ] Redis password set and not exposed to internet
- [ ] Admin panel accessible only from known IPs (optional Nginx `allow`)
- [ ] MFA enabled on admin account
- [ ] `DEBUG=false` in production
- [ ] Rate limiting active (built-in + Nginx `limit_req`)
- [ ] CVE scan green (`pip-audit` in CI)
