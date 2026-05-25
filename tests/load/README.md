# Load Tests — NarayanAstroReader

## Setup

```bash
pip install locust
```

## Quick smoke test (100 users, 30s)

```bash
locust -f tests/load/locustfile.py \
    --headless -u 100 -r 20 --run-time 30s \
    --host http://localhost:8000
```

## Full SLO test (1000 concurrent users, 5 min)

```bash
locust -f tests/load/locustfile.py \
    --headless -u 1000 -r 50 \
    --run-time 5m \
    --host http://localhost:8000 \
    --html tests/load/report.html
```

## Interactive UI

```bash
locust -f tests/load/locustfile.py --host http://localhost:8000
# Open http://localhost:8089
```

## SLO targets (SRS §6.1)

| Endpoint            | p95 target | Error rate |
|---------------------|-----------|-----------|
| `/health`           | 200ms     | < 0.5%    |
| `/auth/login`       | 500ms     | < 0.5%    |
| `/auth/register`    | 500ms     | < 0.5%    |
| `/wallet/balance`   | 2000ms    | < 0.5%    |
| `/kundli/calculate` | 5000ms    | < 0.5%    |
| `/user/profile`     | 500ms     | < 0.5%    |

## Environment variables

| Variable            | Default                          | Description              |
|---------------------|----------------------------------|--------------------------|
| `LOAD_TEST_EMAIL`   | `loadtest@narayan-astro.dev`     | Test account email       |
| `LOAD_TEST_PASSWORD`| `LoadTest#2024`                  | Test account password    |
| `LOAD_TEST_JWT`     | _(empty)_                        | Pre-issued JWT (optional)|
