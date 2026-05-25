"""
config.py — Central configuration for NarayanAstroReader
All settings are read from environment variables or a .env file.
"""
from __future__ import annotations
import os
import sys
from pathlib import Path

# ── Load .env if present ────────────────────────────────────────────────────
_DOTENV = Path(__file__).parent.parent / ".env"
if _DOTENV.exists():
    for line in _DOTENV.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

# ── PyJHora path ─────────────────────────────────────────────────────────────
# Default: sibling folder ../PyJHora  (C:\Users\ntalu\PyJHora)
_HERE = Path(__file__).parent.parent        # NarayanAstroReader/
PYJHORA_PATH: str = os.environ.get(
    "PYJHORA_PATH",
    str(_HERE.parent / "PyJHora")           # ../PyJHora
)

def inject_pyjhora_path() -> None:
    """Ensure PyJHora and its src/ are on sys.path before any import."""
    pj = Path(PYJHORA_PATH)
    src = pj / "src"
    ephe = pj / "src" / "jhora" / "data" / "ephe"

    for p in [str(pj), str(src)]:
        if p not in sys.path:
            sys.path.insert(0, p)

    ephe_str = str(ephe) + os.sep
    os.environ["SE_EPHE_PATH"] = ephe_str

    try:
        import swisseph as swe
        swe.set_ephe_path(ephe_str)
    except ImportError:
        pass  # Handled at import time in engine.py

    return ephe_str

# ── Anthropic ────────────────────────────────────────────────────────────────
ANTHROPIC_API_KEY: str = os.environ.get("ANTHROPIC_API_KEY", "")
ANTHROPIC_MODEL:   str = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-6")
AI_MAX_TOKENS:     int = int(os.environ.get("AI_MAX_TOKENS", "8192"))
MAX_CHAT_HISTORY:  int = int(os.environ.get("MAX_CHAT_HISTORY", "10"))

# ── Database — PostgreSQL ─────────────────────────────────────────────────────
# Set DATABASE_URL in .env:  postgresql://user:password@host:5432/dbname
DATABASE_URL: str = os.environ.get(
    "DATABASE_URL",
    "postgresql://narayan:narayan_dev_pass@localhost:5432/narayan_astro",
)

# DB_PATH kept as a no-op alias so any lingering references don't crash
DB_PATH: str = DATABASE_URL

# ── Server ───────────────────────────────────────────────────────────────────
API_HOST: str = os.environ.get("API_HOST", "0.0.0.0")
API_PORT: int = int(os.environ.get("API_PORT", "8000"))
DEBUG:    bool = os.environ.get("DEBUG", "false").lower() == "true"

# ── Environment / deployment mode ────────────────────────────────────────────
# Set ENVIRONMENT=production in your cloud/server environment.
# Defaults to "development" so local dev works without extra config.
ENVIRONMENT: str = os.environ.get("ENVIRONMENT", "development").lower()
IS_PRODUCTION: bool = ENVIRONMENT == "production"

# ── Security secrets (set these in .env or secrets manager) ──────────────────
# These are read here for documentation purposes; the actual values are
# consumed by backend/auth/jwt_utils.py and backend/api/security.py.
#   JWT_SECRET    — min 32 chars, random hex; signs JWT access + refresh tokens
#   ADMIN_SECRET  — min 32 chars, random hex; authenticates admin panel access
#   FIELD_ENCRYPTION_KEY — base64-encoded 32-byte Fernet key for PII columns

# ── Safety rules ─────────────────────────────────────────────────────────────
# Minimum child age (years) before we answer age-related child questions
MIN_CHILD_AGE_FOR_QUESTIONS: int = int(os.environ.get("MIN_CHILD_AGE_FOR_QUESTIONS", "5"))

# ── Email ─────────────────────────────────────────────────────────────────────
SMTP_HOST:     str = os.environ.get("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT:     int = int(os.environ.get("SMTP_PORT", "587"))
SMTP_USER:     str = os.environ.get("SMTP_USER", "")
SMTP_PASSWORD: str = os.environ.get("SMTP_PASSWORD", "")
SMTP_FROM:     str = os.environ.get("SMTP_FROM", SMTP_USER)

# ── Redis ─────────────────────────────────────────────────────────────────────
REDIS_URL: str = os.environ.get("REDIS_URL", "redis://localhost:6379/0")

# ── Storage (S3-compatible or local fallback) ─────────────────────────────────
S3_BUCKET:     str = os.environ.get("S3_BUCKET", "")
S3_REGION:     str = os.environ.get("S3_REGION", "ap-south-1")
S3_ACCESS_KEY: str = os.environ.get("S3_ACCESS_KEY", "")
S3_SECRET_KEY: str = os.environ.get("S3_SECRET_KEY", "")
