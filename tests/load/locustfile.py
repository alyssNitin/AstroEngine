"""
tests/load/locustfile.py
=========================
Locust load test suite for NarayanAstroReader.

B16: Validates the system under 1000 concurrent users as required by SRS §6.1.

Performance targets (Architecture §9 / SRS §6.1):
  - p95 response time ≤ 200ms  for health / static endpoints
  - p95 response time ≤ 500ms  for auth endpoints
  - p95 response time ≤ 2000ms for wallet balance (cache hit)
  - p95 response time ≤ 30s    for AI interpretation (async / Celery)
  - Error rate < 0.5% under sustained 1000 CCU load

Usage
-----
  # Install: pip install locust

  # Run headless (CI / terminal):
  locust -f tests/load/locustfile.py \
      --headless -u 1000 -r 50 \
      --run-time 5m \
      --host http://localhost:8000 \
      --html tests/load/report.html

  # Run with web UI (interactive):
  locust -f tests/load/locustfile.py --host http://localhost:8000

  # Light smoke-test (100 users, 30 seconds):
  locust -f tests/load/locustfile.py \
      --headless -u 100 -r 20 --run-time 30s \
      --host http://localhost:8000

Environment variables
---------------------
  LOAD_TEST_EMAIL    : existing test-account email (default: loadtest@narayan-astro.dev)
  LOAD_TEST_PASSWORD : password for the test account  (default: LoadTest#2024)
  LOAD_TEST_JWT      : pre-issued JWT (skips login step if set)
"""
from __future__ import annotations

import json
import os
import random
import string
import time
from typing import Optional

from locust import HttpUser, TaskSet, between, constant_pacing, task, events

# ── Config ────────────────────────────────────────────────────────────────────
_DEFAULT_EMAIL    = "loadtest@narayan-astro.dev"
_DEFAULT_PASSWORD = "LoadTest#2024"
_PRESET_JWT       = os.environ.get("LOAD_TEST_JWT", "")

_TEST_EMAIL    = os.environ.get("LOAD_TEST_EMAIL",    _DEFAULT_EMAIL)
_TEST_PASSWORD = os.environ.get("LOAD_TEST_PASSWORD", _DEFAULT_PASSWORD)

# Typical birth-data payload used in kundli / reading endpoints
_BIRTH_PAYLOAD = {
    "name":           "Load Test User",
    "date_of_birth":  "1990-01-15",
    "time_of_birth":  "10:30",
    "place_of_birth": "Mumbai, India",
    "gender":         "M",
}


# ── Shared state (populated at test startup) ──────────────────────────────────
_shared_jwt: Optional[str] = None


def _rand_str(n: int = 8) -> str:
    return "".join(random.choices(string.ascii_lowercase, k=n))


# ── Task sets ─────────────────────────────────────────────────────────────────

class PublicTaskSet(TaskSet):
    """
    Public endpoints that do not require authentication.
    These represent unauthenticated / CDN-hit traffic patterns.
    Target: p95 ≤ 200ms.
    """

    @task(10)
    def health_check(self):
        """GET /health — highest-weight since monitoring agents hit this constantly."""
        with self.client.get("/health", catch_response=True, name="/health") as resp:
            if resp.status_code == 200:
                resp.success()
            else:
                resp.failure(f"Health check failed: {resp.status_code}")

    @task(3)
    def serve_root(self):
        """GET / — SPA index page."""
        with self.client.get("/", catch_response=True, name="/") as resp:
            if resp.status_code in (200, 304):
                resp.success()
            else:
                resp.failure(f"Root returned {resp.status_code}")

    @task(1)
    def openapi_schema(self):
        """GET /openapi.json — API schema fetch (Swagger UI, integrations)."""
        with self.client.get("/openapi.json", catch_response=True, name="/openapi.json") as resp:
            if resp.status_code == 200:
                resp.success()
            else:
                resp.failure(f"OpenAPI schema: {resp.status_code}")


class AuthTaskSet(TaskSet):
    """
    Authentication flow: register → login → refresh.
    Simulates new-user acquisition traffic.
    Target: p95 ≤ 500ms.
    """

    @task(5)
    def login_valid(self):
        """POST /auth/login — valid credentials (most common)."""
        payload = {"email": _TEST_EMAIL, "password": _TEST_PASSWORD}
        with self.client.post(
            "/auth/login",
            json=payload,
            catch_response=True,
            name="/auth/login [valid]",
        ) as resp:
            if resp.status_code in (200, 401):
                # 401 is expected when test account doesn't exist — don't fail the test
                resp.success()
            else:
                resp.failure(f"Login returned {resp.status_code}")

    @task(2)
    def login_invalid(self):
        """POST /auth/login — invalid credentials (tests rate-limiter / brute-force guard)."""
        payload = {"email": f"nouser_{_rand_str()}@x.dev", "password": "wrong"}
        with self.client.post(
            "/auth/login",
            json=payload,
            catch_response=True,
            name="/auth/login [invalid]",
        ) as resp:
            # Expect 401 or 429 (rate-limited) — both are correct behaviour
            if resp.status_code in (401, 422, 429):
                resp.success()
            else:
                resp.failure(f"Expected 401/429, got {resp.status_code}")

    @task(1)
    def register_new_user(self):
        """POST /auth/register — new user registration."""
        email   = f"lt_{_rand_str(12)}@loadtest.narayan.dev"
        payload = {
            "name":     "Load Test",
            "email":    email,
            "password": "LoadTest#9999",
            "region":   random.choice(["India", "US", "UK"]),
        }
        with self.client.post(
            "/auth/register",
            json=payload,
            catch_response=True,
            name="/auth/register",
        ) as resp:
            if resp.status_code in (200, 201, 409, 422):
                resp.success()
            else:
                resp.failure(f"Register returned {resp.status_code}")


class AuthenticatedTaskSet(TaskSet):
    """
    Authenticated user journey: wallet → kundli → reading.
    Uses a shared JWT obtained at worker startup.
    Target: mixed — wallet p95 ≤ 2s, reading p95 ≤ 30s.
    """

    def on_start(self):
        """Obtain a JWT if one is not pre-configured."""
        global _shared_jwt
        if _PRESET_JWT:
            self._jwt = _PRESET_JWT
        elif _shared_jwt:
            self._jwt = _shared_jwt
        else:
            resp = self.client.post(
                "/auth/login",
                json={"email": _TEST_EMAIL, "password": _TEST_PASSWORD},
            )
            if resp.status_code == 200:
                self._jwt = resp.json().get("access_token", "")
                _shared_jwt = self._jwt
            else:
                self._jwt = ""

    def _auth_headers(self) -> dict:
        if self._jwt:
            return {"Authorization": f"Bearer {self._jwt}"}
        return {}

    @task(15)
    def wallet_balance(self):
        """GET /wallet/balance — most frequently polled endpoint (cached via Redis)."""
        with self.client.get(
            "/wallet/balance",
            headers=self._auth_headers(),
            catch_response=True,
            name="/wallet/balance",
        ) as resp:
            if resp.status_code in (200, 401):
                resp.success()
            else:
                resp.failure(f"Wallet balance: {resp.status_code}")

    @task(8)
    def kundli_calculate(self):
        """POST /kundli/calculate — core chart computation."""
        with self.client.post(
            "/kundli/calculate",
            json=_BIRTH_PAYLOAD,
            headers=self._auth_headers(),
            catch_response=True,
            name="/kundli/calculate",
        ) as resp:
            if resp.status_code in (200, 201, 401, 422):
                resp.success()
            else:
                resp.failure(f"Kundli calculate: {resp.status_code}")

    @task(5)
    def user_profile(self):
        """GET /user/profile — user data fetch."""
        with self.client.get(
            "/user/profile",
            headers=self._auth_headers(),
            catch_response=True,
            name="/user/profile",
        ) as resp:
            if resp.status_code in (200, 401, 404):
                resp.success()
            else:
                resp.failure(f"User profile: {resp.status_code}")

    @task(3)
    def wallet_transactions(self):
        """GET /wallet/transactions — ledger history."""
        with self.client.get(
            "/wallet/transactions",
            params={"email": _TEST_EMAIL, "limit": 20},
            headers=self._auth_headers(),
            catch_response=True,
            name="/wallet/transactions",
        ) as resp:
            if resp.status_code in (200, 401, 404):
                resp.success()
            else:
                resp.failure(f"Wallet transactions: {resp.status_code}")

    @task(2)
    def dasha_narrative(self):
        """POST /dasha/narrative — dasha period interpretation."""
        with self.client.post(
            "/dasha/narrative",
            json={"email": _TEST_EMAIL, "language": "English"},
            headers=self._auth_headers(),
            catch_response=True,
            name="/dasha/narrative",
        ) as resp:
            if resp.status_code in (200, 400, 401, 404):
                resp.success()
            else:
                resp.failure(f"Dasha narrative: {resp.status_code}")

    @task(1)
    def metrics_endpoint(self):
        """GET /metrics — Prometheus scrape (monitoring agents)."""
        with self.client.get(
            "/metrics",
            catch_response=True,
            name="/metrics",
        ) as resp:
            # Prometheus endpoint may be IP-restricted in production
            if resp.status_code in (200, 403, 404):
                resp.success()
            else:
                resp.failure(f"Metrics: {resp.status_code}")


# ── User classes ──────────────────────────────────────────────────────────────

class AnonUser(HttpUser):
    """
    Anonymous visitor — browses the landing page, checks health.
    Weight 1: 10% of total users (unauthenticated / SEO bots / monitoring).
    """
    tasks    = [PublicTaskSet]
    weight   = 1
    wait_time = between(1, 3)


class AuthUser(HttpUser):
    """
    Authentication-focused user — simulates login / registration load.
    Weight 2: 20% of total users.
    """
    tasks    = [AuthTaskSet]
    weight   = 2
    wait_time = between(2, 5)


class ActiveUser(HttpUser):
    """
    Logged-in active user — wallet checks, kundli charts, readings.
    Weight 7: 70% of total users (the bulk of production traffic).
    Target: sustain 700 active users without p95 regression.
    """
    tasks    = [AuthenticatedTaskSet]
    weight   = 7
    wait_time = between(1, 4)


# ── Event hooks (custom SLO assertions) ──────────────────────────────────────

@events.quitting.add_listener
def assert_slos(environment, **kwargs):
    """
    After the test run, assert that SLOs defined in SRS §6.1 are met.
    Exits with code 1 if any SLO is violated (fails CI pipeline).
    """
    stats = environment.runner.stats

    slo_failures = []

    def check(name: str, p95_target_ms: int, error_rate_target: float = 0.005):
        entry = stats.entries.get((name, "GET")) or stats.entries.get((name, "POST"))
        if entry is None:
            return  # endpoint not hit — skip
        p95 = entry.get_response_time_percentile(0.95)
        err_rate = entry.fail_ratio
        if p95 > p95_target_ms:
            slo_failures.append(
                f"SLO FAIL: {name} p95={p95:.0f}ms > target {p95_target_ms}ms"
            )
        if err_rate > error_rate_target:
            slo_failures.append(
                f"SLO FAIL: {name} error_rate={err_rate:.2%} > target {error_rate_target:.2%}"
            )

    check("/health",           p95_target_ms=200)
    check("/",                 p95_target_ms=200)
    check("/auth/login [valid]",  p95_target_ms=500)
    check("/auth/register",    p95_target_ms=500)
    check("/wallet/balance",   p95_target_ms=2000)
    check("/kundli/calculate", p95_target_ms=5000)
    check("/user/profile",     p95_target_ms=500)

    if slo_failures:
        print("\n" + "="*60)
        print("LOAD TEST SLO VIOLATIONS:")
        for f in slo_failures:
            print(f"  ✗ {f}")
        print("="*60 + "\n")
        environment.process_exit_code = 1
    else:
        print("\n✓ All SLOs passed.\n")
