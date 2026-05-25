#!/usr/bin/env python3
"""
orchestrator.py — NarayanAstroReader service orchestrator
===========================================================
Starts every microservice and the API gateway with a single command.
Fans their stdout/stderr into one terminal with colour-coded prefixes so
you can watch all services in one window.

Usage
-----
  python orchestrator.py                   # start everything
  python orchestrator.py --no-dasha        # skip dasha-engine
  python orchestrator.py --no-notify       # skip notification-service
  python orchestrator.py --no-analytics    # skip analytics-service
  python orchestrator.py --gateway-only    # start only the FastAPI gateway
  python orchestrator.py --reload          # hot-reload the gateway

Press Ctrl+C to stop all services cleanly.

Services started
----------------
  api-gateway        :8000   backend/api/main.py   (FastAPI — serves React SPA + all API routes)
  dasha-engine       :8001   services/dasha-engine/start.py
  notification-svc   :8002   services/notification-service/start.py
  analytics-svc      :8003   services/analytics-service/start.py

SOLID Notes
-----------
SRP : Each ServiceDef knows only its own startup parameters.
OCP : Add a new service by appending one ServiceDef — zero other changes.
DIP : The fan-log loop depends on the abstract "process with a pipe" — not
      on any specific service implementation.
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

# ── Project root (directory containing this file) ─────────────────────────────
ROOT = Path(__file__).parent

# ── ANSI colour codes (work on Windows 10+ with ENABLE_VIRTUAL_TERMINAL) ─────
RESET  = "\033[0m"
BOLD   = "\033[1m"
COLOURS = {
    "api-gateway":       "\033[94m",   # bright blue
    "dasha-engine":      "\033[95m",   # bright magenta
    "notification-svc":  "\033[96m",   # bright cyan
    "analytics-svc":     "\033[93m",   # bright yellow
    "orchestrator":      "\033[92m",   # bright green
}

def _colour(name: str, text: str) -> str:
    c = COLOURS.get(name, "")
    label = f"{name:<18}"              # fixed-width label
    return f"{c}{BOLD}[{label}]{RESET} {text}"


# ── Service definition ─────────────────────────────────────────────────────────

@dataclass
class ServiceDef:
    """Describes how to start one microservice.

    Attributes
    ----------
    name        : Human-readable label shown in log prefix.
    script      : Path to the service's start.py (relative to ROOT).
    port        : Port the service listens on.
    extra_args  : Additional CLI arguments forwarded to the script.
    env_overrides: Extra env vars merged into the subprocess environment.
    restart     : Auto-restart on unexpected exit (default False).
    """
    name:           str
    script:         Path
    port:           int
    extra_args:     list[str]         = field(default_factory=list)
    env_overrides:  dict[str, str]    = field(default_factory=dict)
    restart:        bool              = False

    def build_cmd(self) -> list[str]:
        """Return the full command list to launch this service."""
        return [sys.executable, str(ROOT / self.script), "--port", str(self.port)] + self.extra_args


# ── Service registry ───────────────────────────────────────────────────────────

def _build_registry(args: argparse.Namespace) -> list[ServiceDef]:
    """Construct the list of services to start based on CLI flags."""
    gateway_extra = ["--reload"] if args.reload else []

    all_services: list[ServiceDef] = [
        ServiceDef(
            name    = "api-gateway",
            script  = Path("start.py"),
            port    = args.gateway_port,
            extra_args = gateway_extra,
            restart = False,  # gateway restart breaks browser sessions
        ),
        ServiceDef(
            name    = "dasha-engine",
            script  = Path("services/dasha-engine/start.py"),
            port    = 8001,
            restart = True,
        ),
        ServiceDef(
            name    = "notification-svc",
            script  = Path("services/notification-service/start.py"),
            port    = 8002,
            restart = True,
        ),
        ServiceDef(
            name    = "analytics-svc",
            script  = Path("services/analytics-service/start.py"),
            port    = 8003,
            restart = True,
        ),
    ]

    if args.gateway_only:
        return [s for s in all_services if s.name == "api-gateway"]

    skip = set()
    if args.no_dasha:      skip.add("dasha-engine")
    if args.no_notify:     skip.add("notification-svc")
    if args.no_analytics:  skip.add("analytics-svc")

    return [s for s in all_services if s.name not in skip]


# ── Process manager ────────────────────────────────────────────────────────────

class ManagedProcess:
    """Wraps a subprocess and fans its output to the orchestrator terminal.

    Runs a background thread that reads lines from the child's stdout and
    prints them with the service's colour-coded prefix.
    """

    def __init__(self, svc: ServiceDef) -> None:
        self.svc        = svc
        self.proc: Optional[subprocess.Popen] = None
        self._thread: Optional[threading.Thread] = None
        self._stop      = threading.Event()

    # ── Start ─────────────────────────────────────────────────────────────────
    def start(self) -> None:
        env = {
            **os.environ,
            # Force UTF-8 I/O on all Python child processes so emoji in log
            # messages don't crash on Windows cp1252 consoles.
            "PYTHONIOENCODING": "utf-8",
            "PYTHONUTF8":       "1",
            **self.svc.env_overrides,
        }
        cmd = self.svc.build_cmd()

        _log("orchestrator", f"Starting  {self.svc.name}  on :{self.svc.port}")
        _log("orchestrator", f"  cmd: {' '.join(cmd)}")

        self.proc = subprocess.Popen(
            cmd,
            stdout     = subprocess.PIPE,
            stderr     = subprocess.STDOUT,   # merge stderr → stdout
            env        = env,
            cwd        = str(ROOT),
            bufsize    = 1,                   # line-buffered
            text       = True,
            encoding   = "utf-8",
            errors     = "replace",
        )
        self._stop.clear()
        self._thread = threading.Thread(
            target = self._fan_logs,
            name   = f"fan-{self.svc.name}",
            daemon = True,
        )
        self._thread.start()

    # ── Log fan ───────────────────────────────────────────────────────────────
    def _fan_logs(self) -> None:
        """Read lines from the child process and print with prefix."""
        assert self.proc and self.proc.stdout
        for line in self.proc.stdout:
            if self._stop.is_set():
                break
            print(_colour(self.svc.name, line.rstrip()), flush=True)

    # ── Stop ──────────────────────────────────────────────────────────────────
    def stop(self) -> None:
        """Ask the process to terminate gracefully, then force-kill."""
        self._stop.set()
        if self.proc and self.proc.poll() is None:
            _log("orchestrator", f"Stopping {self.svc.name}…")
            self.proc.terminate()
            try:
                self.proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                _log("orchestrator", f"Force-killing {self.svc.name}")
                self.proc.kill()

    # ── Status ────────────────────────────────────────────────────────────────
    @property
    def is_running(self) -> bool:
        return self.proc is not None and self.proc.poll() is None

    @property
    def returncode(self) -> Optional[int]:
        return self.proc.returncode if self.proc else None


# ── Helpers ────────────────────────────────────────────────────────────────────

def _log(name: str, msg: str) -> None:
    print(_colour(name, msg), flush=True)


def _enable_windows_ansi() -> None:
    """Enable ANSI escape codes on Windows 10+ consoles."""
    if sys.platform != "win32":
        return
    try:
        import ctypes
        kernel32 = ctypes.windll.kernel32          # type: ignore[attr-defined]
        # ENABLE_VIRTUAL_TERMINAL_PROCESSING = 0x0004
        kernel32.SetConsoleMode(kernel32.GetStdHandle(-11), 7)
    except Exception:
        pass  # non-fatal — colours just won't render


# ── Main ───────────────────────────────────────────────────────────────────────

def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="NarayanAstroReader — start all services",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    p.add_argument("--gateway-port",  type=int, default=8000,  help="Port for the API gateway (default: 8000)")
    p.add_argument("--reload",        action="store_true",     help="Enable hot-reload on the API gateway")
    p.add_argument("--gateway-only",  action="store_true",     help="Start only the FastAPI gateway (no microservices)")
    p.add_argument("--no-dasha",      action="store_true",     help="Skip dasha-engine")
    p.add_argument("--no-notify",     action="store_true",     help="Skip notification-service")
    p.add_argument("--no-analytics",  action="store_true",     help="Skip analytics-service")
    p.add_argument("--restart-delay", type=float, default=3.0, help="Seconds to wait before restarting a crashed service (default: 3)")
    return p.parse_args()


def main() -> None:
    _enable_windows_ansi()
    args   = _parse_args()
    registry = _build_registry(args)

    print()
    _log("orchestrator", "=" * 60)
    _log("orchestrator", "  NarayanAstroReader — Service Orchestrator")
    _log("orchestrator", "=" * 60)
    _log("orchestrator", f"  Starting {len(registry)} service(s):")
    for svc in registry:
        _log("orchestrator", f"    • {svc.name:<20} :{svc.port}")
    _log("orchestrator", "  Press Ctrl+C to stop all services.")
    _log("orchestrator", "=" * 60)
    print()

    # ── Spawn all services ────────────────────────────────────────────────────
    managed: list[ManagedProcess] = [ManagedProcess(svc) for svc in registry]
    for mp in managed:
        mp.start()
        time.sleep(0.3)   # small stagger so ports don't collide on startup

    # ── Monitor loop — auto-restart services that exit unexpectedly ───────────
    try:
        while True:
            time.sleep(1)
            for mp in managed:
                if not mp.is_running and not mp._stop.is_set():
                    rc = mp.returncode
                    if mp.svc.restart:
                        _log("orchestrator",
                             f"⚠️  {mp.svc.name} exited (rc={rc}). "
                             f"Restarting in {args.restart_delay}s…")
                        time.sleep(args.restart_delay)
                        mp.start()
                    else:
                        _log("orchestrator",
                             f"⚠️  {mp.svc.name} exited (rc={rc}). Not restarting.")

    except KeyboardInterrupt:
        print()
        _log("orchestrator", "Ctrl+C received — shutting down all services…")

    # ── Graceful shutdown ─────────────────────────────────────────────────────
    for mp in reversed(managed):   # stop gateway last so it can drain requests
        mp.stop()

    _log("orchestrator", "All services stopped. Goodbye! 🪐")
    print()


if __name__ == "__main__":
    main()
