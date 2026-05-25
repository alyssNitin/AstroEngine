"""analytics-service API schemas."""
from __future__ import annotations
from pydantic import BaseModel
from typing import Optional


class DateRangeQuery(BaseModel):
    from_date: str   # ISO YYYY-MM-DD
    to_date:   str   # ISO YYYY-MM-DD


class TrafficMetrics(BaseModel):
    from_date:      str
    to_date:        str
    total_users:    int
    new_users:      int
    active_users:   int     # at least 1 event in period
    total_sessions: int
    daily_breakdown: list[dict]


class RevenueMetrics(BaseModel):
    from_date:          str
    to_date:            str
    total_revenue_cents: int
    by_pack:            dict[str, int]
    by_method:          dict[str, int]
    by_region:          dict[str, int]
    refund_amount_cents: int


class LlmCostMetrics(BaseModel):
    from_date:       str
    to_date:         str
    total_calls:     int
    total_tokens:    int
    total_cost_usd:  float
    by_report_type:  dict[str, dict]


class SystemHealthMetrics(BaseModel):
    p50_ms:      float
    p95_ms:      float
    p99_ms:      float
    error_rate:  float    # 0.0–1.0
    uptime_pct:  float    # 0.0–100.0
    checked_at:  str      # ISO datetime


class EventIngestionRequest(BaseModel):
    event_type:  str          # KUNDLI_VIEW, REPORT_GENERATED, CHAT_MSG, etc.
    user_id:     str          # UUID — never raw PII
    metadata:    dict = {}    # additional anonymised context
