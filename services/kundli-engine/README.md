# kundli-engine

**Microservice for Vedic astrology chart (Kundli) computation.**

Delegates all planetary calculations to the battle-tested **PyJHora** library which wraps the Swiss Ephemeris (`pyswisseph`). This service is the numerical backbone of the platform — it produces all position data consumed downstream by `dasha-engine` and `ai-interpretation-service`.

---

## Responsibilities

| Responsibility | Detail |
|---|---|
| Birth chart (D1 Rasi) | Planetary positions, houses, Lagna — Nirayan system |
| Divisional charts | D1–D16 (Navamsa, Drekkana, Dashamsa …) |
| Dasha data (raw) | Vimshottari Mahadasha/Antardasha start/end dates |
| Ayanamsa | Lahiri (default), Raman, KP — configurable per request |
| Chart styles | North Indian, South Indian |
| Yoga detection | Raj yoga, Dhana yoga, Kemadruma, etc. |
| Shadbala | Six-fold planetary strength scores |
| Ashtakavarga | Eight-source benefic point tables |

---

## API Endpoints

| Method | Path | Auth | Description |
|---|---|---|---|
| `POST` | `/kundli/calculate` | JWT | Full chart computation |
| `GET`  | `/kundli/profiles` | JWT | List user's saved profiles |
| `POST` | `/kundli/profiles` | JWT | Save a new Kundli profile |
| `GET`  | `/kundli/chart/{profile_id}/svg` | JWT | North/South Indian SVG chart |

### Request — POST /kundli/calculate

```json
{
  "name": "Ramesh Kumar",
  "date_of_birth": "1990-05-15",
  "time_of_birth": "14:30:00",
  "place_of_birth": "Mumbai, India",
  "latitude": 19.0760,
  "longitude": 72.8777,
  "timezone_offset": 5.5,
  "ayanamsa": "lahiri"
}
```

### Response (abbreviated)

```json
{
  "birth_info": { "name": "...", "ayanamsa_value": "23.15°", ... },
  "lagna": { "rasi": "Scorpio", "degree": 14.32, "nakshatra": "Anuradha" },
  "rasi_chart": { "Sun": { "rasi": "Taurus", "house": 7, "retrograde": false }, ... },
  "divisional_charts": { "D9": { ... }, "D10": { ... } },
  "yogas": ["Gaja Kesari", "Budhaditya"],
  "shadbala": { "Sun": 1.43, "Moon": 0.87, ... },
  "dashas": { "vimshottari": { "current_mahadasha": "Jupiter", ... } }
}
```

---

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `PYJHORA_PATH` | `../../PyJHora` | Path to local PyJHora installation |
| `SE_EPHE_PATH` | auto-set | Swiss Ephemeris data files path |
| `API_HOST` | `0.0.0.0` | Listen host |
| `API_PORT` | `8001` | Listen port |
| `LOG_LEVEL` | `INFO` | Logging verbosity |

---

## How to Run (Local Dev)

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Ensure PyJHora is available
export PYJHORA_PATH=/path/to/PyJHora

# 3. Start service
uvicorn src.api.main:app --host 0.0.0.0 --port 8001 --reload
```

---

## How to Run (Docker)

```bash
docker build -t narayan/kundli-engine:latest .
docker run -p 8001:8001 \
  -e PYJHORA_PATH=/app/pyjhora \
  -v /path/to/PyJHora:/app/pyjhora \
  narayan/kundli-engine:latest
```

---

## Module Structure

```
services/kundli-engine/
├── src/
│   ├── calculator/
│   │   ├── engine.py          # PyJHora facade — main computation class
│   │   ├── formatter.py       # Formats raw dict for AI/API consumption
│   │   ├── ephemeris.py       # (TODO) Swiss Ephemeris direct wrapper
│   │   ├── ayanamsa.py        # (TODO) Multi-ayanamsa support
│   │   ├── divisional.py      # (TODO) D1-D16 structured parser
│   │   ├── shadbala.py        # (TODO) Shadbala scorer
│   │   └── yogas.py           # (TODO) Yoga detection rules engine
│   ├── api/
│   │   ├── main.py            # FastAPI app + routes
│   │   └── schemas.py         # Pydantic request/response models
│   └── tests/
│       └── test_engine.py     # Unit tests (≥80% coverage target)
├── requirements.txt
├── Dockerfile
└── README.md  ← you are here
```

---

## Testing

```bash
python -m pytest src/tests/ -v --cov=src --cov-report=term-missing
```

Target: **≥80% coverage** on `calculator/` module (per architecture NFR).

---

## Dependencies

| Package | Purpose |
|---|---|
| `fastapi` | REST API framework |
| `uvicorn` | ASGI server |
| `pyswisseph` | Swiss Ephemeris Python binding |
| `numpy` | Numerical operations |
| `geopy` | Place-name → lat/lon geocoding |
| `timezonefinder` | Lat/lon → IANA timezone |
| `pytz` | Timezone-aware datetime conversion |

---

## Architecture Notes

- This service is **stateless** — no DB. Birth data passed in per request; profiles persisted by `auth-service`.
- Chart calculations are CPU-bound. Use **Redis cache** (keyed on birth data + ayanamsa hash) to avoid recomputation for repeat requests.
- All output is pure JSON — no HTML. The frontend or `ai-interpretation-service` consumes the output.
- PyJHora is a **local library dependency** — it is not installed via pip. The `PYJHORA_PATH` env var must point to a checkout of the PyJHora repository.
