#!/usr/bin/env python3
"""
start.py — NarayanAstroReader startup script
=============================================
Validates environment, then starts the FastAPI server.

Usage:
  python start.py                  # start server (default port 8000)
  python start.py --port 9000      # custom port
  python start.py --test           # run tests instead of starting server
"""
import sys, os, argparse
from pathlib import Path

_ROOT = Path(__file__).parent
sys.path.insert(0, str(_ROOT))


def check_env():
    """Validate critical configuration before starting."""
    errors = []

    # Load .env
    dotenv = _ROOT / ".env"
    if dotenv.exists():
        for line in dotenv.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

    # Anthropic key
    if not os.environ.get("ANTHROPIC_API_KEY", "").startswith("sk-ant-"):
        errors.append("❌ ANTHROPIC_API_KEY not set or invalid. Add it to your .env file.")

    # PyJHora path
    pyjhora = os.environ.get("PYJHORA_PATH", str(_ROOT.parent / "PyJHora"))
    if not Path(pyjhora).exists():
        errors.append(
            f"⚠️  PyJHora not found at: {pyjhora}\n"
            "   Set PYJHORA_PATH in .env or install PyJHora at C:\\Users\\ntalu\\PyJHora"
        )

    if errors:
        print("\n" + "\n".join(errors))
        if any("❌" in e for e in errors):
            sys.exit(1)
    else:
        print("✅ Environment OK")


def run_tests():
    """Run the test suite and open the HTML report."""
    os.chdir(_ROOT)
    rc = os.system(f'"{sys.executable}" tests/run_tests.py --verbose')
    report = _ROOT / "tests" / "test_report.html"
    if report.exists():
        import webbrowser
        webbrowser.open(report.as_uri())
    sys.exit(rc)


def init_database():
    """Initialise PostgreSQL schema (idempotent — safe to re-run on every startup)."""
    try:
        from backend.persistence.database import Database
        db = Database()
        db.init_schema()
        print("✅ Database schema OK")
    except Exception as exc:
        print(f"⚠️  Database init warning: {exc}")
        print("   Server will still start — check DATABASE_URL in .env if login fails.")


def start_server(host: str, port: int, reload: bool):
    """Launch uvicorn."""
    try:
        import uvicorn
    except ImportError:
        print("❌ uvicorn not installed. Run: pip install uvicorn")
        sys.exit(1)

    # Initialise DB schema before handing off to uvicorn
    init_database()

    print(f"\n🪐 NarayanAstroReader starting on http://{host}:{port}")
    print(f"   Open your browser to: http://localhost:{port}\n")
    uvicorn.run(
        "backend.api.main:app",
        host=host, port=port, reload=reload,
        app_dir=str(_ROOT),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="NarayanAstroReader launcher")
    parser.add_argument("--host",   default="0.0.0.0")
    parser.add_argument("--port",   type=int, default=8000)
    parser.add_argument("--reload", action="store_true", help="Hot-reload on code changes")
    parser.add_argument("--test",   action="store_true", help="Run test suite instead of server")
    parser.add_argument("--skip-checks", action="store_true")
    args = parser.parse_args()

    if not args.skip_checks:
        check_env()

    if args.test:
        run_tests()
    else:
        start_server(args.host, args.port, args.reload)
