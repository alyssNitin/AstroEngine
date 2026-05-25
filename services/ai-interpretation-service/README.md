# ai-interpretation-service

**Microservice for AI-powered Vedic astrology interpretation using Claude (Anthropic).**

Receives structured chart + dasha JSON from the upstream engines, constructs anonymised locale-aware prompts, calls the LLM, validates the response, and streams the result back to the client via Server-Sent Events (SSE).

---

## Responsibilities

| Responsibility | Detail |
|---|---|
| Prompt construction | Locale-aware (en/hi/ta), anonymised, no PII to LLM |
| LLM invocation | Claude Sonnet (Anthropic SDK); provider-agnostic adapter |
| Safety filtering | Blocks death-prediction, harmful advice, minor-related queries |
| Planet calibration | Sanitises planet-name mentions; removes birth PII from prompt |
| SSE streaming | Streams token-by-token response to frontend |
| Report types | Personal (✅), Compatibility (🚧 stub), Career (🚧 stub) |
| Chat Q&A | Conversational follow-up with session history |
| API call logging | Logs input/output tokens and estimated USD cost per call |
| Credit gate check | Calls `credit-wallet-service` to verify balance before generation |
| Auto-refund | On AI failure, instructs `credit-wallet-service` to reverse deduction |

---

## API Endpoints

| Method | Path | Auth | Description |
|---|---|---|---|
| `POST` | `/ai/report/generate` | JWT | Generate a new AI report (SSE stream) |
| `GET`  | `/ai/report/{report_id}` | JWT | Fetch a completed report |
| `POST` | `/ai/report/{report_id}/ask` | JWT | Chat follow-up on a report |
| `GET`  | `/ai/report/{report_id}/status` | JWT | Check generation status |

### Request — POST /ai/report/generate

```json
{
  "profile_id": "uuid",
  "birth_chart": { ... },
  "dasha_timeline": { ... },
  "report_type": "personal",
  "language": "hi",
  "user_preferences": { "focus": "career" }
}
```

### SSE Response Stream

```
data: {"type": "chunk", "text": "आपके जन्म कुंडली में "}
data: {"type": "chunk", "text": "गुरु लग्न में स्थित हैं..."}
data: {"type": "done", "report_id": "uuid", "tokens_used": 2847}
data: {"type": "error", "message": "...", "refund_issued": true}
```

---

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `ANTHROPIC_API_KEY` | **required** | Your Anthropic API key |
| `ANTHROPIC_MODEL` | `claude-sonnet-4-6` | Model to use |
| `AI_MAX_TOKENS` | `8192` | Maximum output tokens |
| `MAX_CHAT_HISTORY` | `10` | Messages retained in session |
| `WALLET_SERVICE_URL` | `http://credit-wallet-service:8004` | Internal URL for credit checks |
| `API_HOST` | `0.0.0.0` | Listen host |
| `API_PORT` | `8003` | Listen port |

---

## How to Run (Local Dev)

```bash
pip install -r requirements.txt
export ANTHROPIC_API_KEY=sk-ant-...
uvicorn src.api.main:app --host 0.0.0.0 --port 8003 --reload
```

---

## Module Structure

```
services/ai-interpretation-service/
├── src/
│   ├── prompt_builder/
│   │   ├── prompts.py             # System + user prompt templates per language
│   │   └── locale_adapter.py      # i18n-aware prompt construction
│   ├── validators/
│   │   ├── safety_filter.py       # Death/harmful/child question blocker
│   │   └── planet_calibrator.py   # PII scrubber for chart data
│   ├── llm_client/
│   │   ├── agent.py               # AstroAgent class — main LLM orchestrator
│   │   ├── anthropic_client.py    # Anthropic SDK adapter
│   │   └── base_client.py         # AbstractLLMClient interface
│   ├── report_types/
│   │   ├── personal.py            # Personal reading prompts + validation
│   │   ├── compatibility.py       # 🚧 Stub — partner compatibility reading
│   │   └── career.py              # 🚧 Stub — career + finance reading
│   ├── api/
│   │   ├── main.py                # FastAPI app
│   │   └── schemas.py             # Pydantic models
│   └── tests/
│       ├── test_agent.py
│       ├── test_safety_filter.py
│       └── test_planet_calibrator.py
├── requirements.txt
├── Dockerfile
└── README.md
```

---

## Safety Policy

All user questions pass through `safety_filter.py` before the LLM is invoked:

1. **Death timing** — Never predict when anyone will die
2. **Children under 5** — Refuse detailed questions about very young children's futures
3. **Medical/legal advice** — Redirect to professionals
4. **Past death context** — Allowed with respectful framing

The safety filter is a **pure function** — no I/O, fully unit-testable.

---

## PII Handling

`planet_calibrator.py` ensures no personally identifiable information reaches the LLM:

- Birth place name is **generalised** to a region (e.g. "Mumbai" → "Western India")
- Full name is **replaced** with a placeholder ("the native")
- Exact birth time is **rounded** to the nearest 15 minutes in the prompt

---

## Testing

```bash
python -m pytest src/tests/ -v
```

---

## Dependencies

| Package | Purpose |
|---|---|
| `fastapi` | REST + SSE API framework |
| `anthropic` | Claude API client |
| `pydantic` | Request/response validation |
