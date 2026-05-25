# dasha-engine

**Microservice for Vedic Dasha (planetary period) calculation and transit correlation.**

Dasha systems are the core predictive tool in Vedic astrology. This service takes a birth chart (produced by `kundli-engine`) and returns structured timeline data for any supported Dasha system. Each Dasha system is an isolated pluggable module — adding a new system requires no changes to core code.

---

## Responsibilities

| Responsibility | Detail |
|---|---|
| Vimshottari Dasha | Standard 120-year planetary period system |
| Yogini Dasha | 36-year system based on Moon's nakshatra |
| Chara Dasha | Sign-based system by Jaimini |
| Kalachakra Dasha | Nakshatra-pada based system |
| Narayana Dasha | Sign-based predictive system |
| Moola Dasha | Root dasha system |
| Mahadasha → Sookshma | Full 5-level nesting (Maha → Antar → Pratyantar → Sookshma → Prana) |
| Gochara (Transit) | Current planetary transits over natal chart positions |

---

## API Endpoints

| Method | Path | Auth | Description |
|---|---|---|---|
| `POST` | `/dasha/calculate` | JWT | Calculate dasha timeline for given profile + system |
| `GET`  | `/dasha/current/{profile_id}` | JWT | Active Mahadasha + Antardasha right now |
| `GET`  | `/dasha/systems` | Public | List all available dasha systems |
| `GET`  | `/dasha/transit/{profile_id}` | JWT | Current planetary transits over natal positions |

### Request — POST /dasha/calculate

```json
{
  "profile_id": "uuid-here",
  "birth_chart": { ... },
  "system": "vimshottari",
  "from_date": "2024-01-01",
  "to_date": "2030-12-31",
  "depth": 2
}
```

`depth` controls nesting: `1` = Mahadasha only, `2` = +Antardasha, `3` = +Pratyantar, etc.

### Response

```json
{
  "system": "vimshottari",
  "timeline": [
    {
      "level": 1,
      "planet": "Jupiter",
      "start": "2020-03-14",
      "end": "2036-03-14",
      "antardasha": [
        { "level": 2, "planet": "Jupiter", "start": "2020-03-14", "end": "2022-07-07" },
        { "level": 2, "planet": "Saturn",  "start": "2022-07-07", "end": "2025-01-13" }
      ]
    }
  ],
  "current": {
    "mahadasha": "Jupiter",
    "antardasha": "Saturn",
    "started": "2022-07-07",
    "ends": "2025-01-13"
  }
}
```

---

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `PYJHORA_PATH` | `../../PyJHora` | PyJHora path (for Vimshottari base data) |
| `API_HOST` | `0.0.0.0` | Listen host |
| `API_PORT` | `8002` | Listen port |
| `LOG_LEVEL` | `INFO` | Logging verbosity |

---

## How to Run (Local Dev)

```bash
pip install -r requirements.txt
uvicorn src.api.main:app --host 0.0.0.0 --port 8002 --reload
```

---

## Module Structure

```
services/dasha-engine/
├── src/
│   ├── systems/               # Pluggable dasha system modules
│   │   ├── __init__.py        # System registry — auto-discovers modules
│   │   ├── base.py            # AbstractDashaSystem interface
│   │   ├── vimshottari.py     # ✅ Implemented (via PyJHora)
│   │   ├── yogini.py          # 🚧 Stub
│   │   ├── chara.py           # 🚧 Stub
│   │   ├── kalachakra.py      # 🚧 Stub
│   │   ├── narayana.py        # 🚧 Stub
│   │   └── moola.py           # 🚧 Stub
│   ├── timeline/
│   │   ├── builder.py         # Builds nested Maha→Sookshma timeline JSON
│   │   └── formatter.py       # Human-readable timeline formatter
│   ├── transit/
│   │   └── gochara.py         # Current transit positions vs natal chart
│   ├── api/
│   │   ├── main.py            # FastAPI app
│   │   └── schemas.py         # Pydantic models
│   └── tests/
│       └── test_vimshottari.py
├── requirements.txt
├── Dockerfile
└── README.md
```

---

## Pluggable System Interface

Every dasha system must implement `AbstractDashaSystem`:

```python
from abc import ABC, abstractmethod

class AbstractDashaSystem(ABC):
    name: str          # e.g. "vimshottari"
    total_years: int   # e.g. 120

    @abstractmethod
    def calculate(self, birth_chart: dict, from_date: str, to_date: str, depth: int) -> dict:
        """Return structured timeline dict."""
        ...

    @abstractmethod
    def get_current(self, birth_chart: dict) -> dict:
        """Return active period at today's date."""
        ...
```

To add a new system: create `src/systems/new_system.py`, subclass `AbstractDashaSystem`, and register in `src/systems/__init__.py`. No other changes needed.

---

## Testing

```bash
python -m pytest src/tests/ -v
```

---

## Implementation Status

| System | Status |
|---|---|
| Vimshottari | ✅ Via PyJHora |
| Yogini | 🚧 Stub only |
| Chara | 🚧 Stub only |
| Kalachakra | 🚧 Stub only |
| Narayana | 🚧 Stub only |
| Moola | 🚧 Stub only |
| Gochara (Transit) | 🚧 Stub only |
