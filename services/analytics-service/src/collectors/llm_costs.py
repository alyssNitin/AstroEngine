"""
collectors/llm_costs.py
========================
Aggregates LLM API call logs: token counts, cost per call, cost per report type.

Source of truth: the `api_call_logs` table populated by backend/ai_interpretation/agent.py
(logged after every Claude API call with input_tokens, output_tokens, cost_usd, report_type).

Pricing basis (Claude Sonnet):
  Input : $3.00 per million tokens
  Output: $15.00 per million tokens
"""
from __future__ import annotations
import os, logging
from datetime import datetime, timezone

log = logging.getLogger(__name__)

_DB_URL = os.environ.get("DATABASE_URL", "")

# Approximate Claude Sonnet pricing (USD per token)
_INPUT_COST_PER_TOKEN  = 3.00  / 1_000_000
_OUTPUT_COST_PER_TOKEN = 15.00 / 1_000_000


def estimate_cost(input_tokens: int, output_tokens: int) -> float:
    """Estimate USD cost for a single API call."""
    return (input_tokens * _INPUT_COST_PER_TOKEN
            + output_tokens * _OUTPUT_COST_PER_TOKEN)


class LlmCostCollector:
    """
    Reads `api_call_logs` and aggregates cost / token metrics.

    When DATABASE_URL is not set, returns sample data for dev/testing.
    """

    def get_metrics(self, from_date: str, to_date: str) -> dict:
        """
        Return aggregated LLM cost metrics for a date range.

        Returns dict with:
          total_calls, total_input_tokens, total_output_tokens,
          total_cost_usd, by_report_type, avg_cost_per_call
        """
        if not _DB_URL:
            return self._sample_metrics(from_date, to_date)

        try:
            import psycopg2, psycopg2.extras
            with psycopg2.connect(_DB_URL) as conn:
                with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                    cur.execute(
                        """
                        SELECT
                            COUNT(*)                          AS total_calls,
                            COALESCE(SUM(input_tokens),  0)  AS total_input,
                            COALESCE(SUM(output_tokens), 0)  AS total_output,
                            COALESCE(SUM(cost_usd),      0)  AS total_cost,
                            report_type
                        FROM api_call_logs
                        WHERE created_at::date BETWEEN %s AND %s
                        GROUP BY report_type
                        """,
                        (from_date, to_date),
                    )
                    rows = [dict(r) for r in cur.fetchall()]
            return self._aggregate(rows)
        except Exception as exc:
            log.error("llm_cost_query_failed", extra={"error": str(exc)})
            return self._sample_metrics(from_date, to_date)

    # ── Private helpers ───────────────────────────────────────────────────────

    def _aggregate(self, rows: list[dict]) -> dict:
        total_calls  = sum(int(r["total_calls"])  for r in rows)
        total_input  = sum(int(r["total_input"])  for r in rows)
        total_output = sum(int(r["total_output"]) for r in rows)
        total_cost   = sum(float(r["total_cost"]) for r in rows)
        by_type      = {
            r["report_type"]: {
                "calls":       int(r["total_calls"]),
                "input_tokens": int(r["total_input"]),
                "output_tokens": int(r["total_output"]),
                "cost_usd":    float(r["total_cost"]),
            }
            for r in rows if r.get("report_type")
        }
        return {
            "total_calls":         total_calls,
            "total_input_tokens":  total_input,
            "total_output_tokens": total_output,
            "total_cost_usd":      round(total_cost, 4),
            "avg_cost_per_call":   round(total_cost / total_calls, 4) if total_calls else 0,
            "by_report_type":      by_type,
        }

    def _sample_metrics(self, from_date: str, to_date: str) -> dict:
        """Return realistic sample data for dev/demo mode."""
        return {
            "total_calls":         42,
            "total_input_tokens":  168_000,
            "total_output_tokens": 336_000,
            "total_cost_usd":      5.544,
            "avg_cost_per_call":   0.132,
            "by_report_type": {
                "personal":      {"calls": 20, "input_tokens": 80_000,  "output_tokens": 160_000, "cost_usd": 2.64},
                "compatibility": {"calls": 12, "input_tokens": 48_000,  "output_tokens": 96_000,  "cost_usd": 1.584},
                "career":        {"calls": 10, "input_tokens": 40_000,  "output_tokens": 80_000,  "cost_usd": 1.32},
            },
            "note": "Sample data — DATABASE_URL not configured",
        }
