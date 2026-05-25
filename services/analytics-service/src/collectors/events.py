"""
collectors/events.py
====================
Ingests anonymised platform events for analytics.

Events are written to an in-memory store (dev) or a PostgreSQL
`analytics_events` table (production, keyed by DATABASE_URL).

Schema of each event record
----------------------------
  id          UUID   PK
  event_type  TEXT         KUNDLI_VIEW / REPORT_GENERATED / CHAT_MSG / LOGIN / ...
  user_id     UUID         anonymous — never store email or name here
  metadata    JSONB        report_type, lang, region, etc.
  occurred_at TIMESTAMPTZ  server timestamp

Privacy guarantee: email, name, birth data are NEVER stored in events.
Only user_id (UUID) is stored to allow cohort analysis.
"""
from __future__ import annotations
import os, uuid, logging
from datetime import datetime, timezone
from typing import Any

log = logging.getLogger(__name__)

# ── In-memory store (dev / test mode) ────────────────────────────────────────
_EVENTS: list[dict] = []

_DB_URL = os.environ.get("DATABASE_URL", "")


class EventCollector:
    """
    Record anonymised usage events.

    Production: writes to `analytics_events` PostgreSQL table.
    Development: stores in module-level list (_EVENTS).
    """

    def record(
        self,
        event_type: str,
        user_id: str,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """
        Persist a single event. Returns the new event id.

        Args:
            event_type: String label (e.g. "REPORT_GENERATED")
            user_id:    UUID of the user (NOT email or name)
            metadata:   Optional dict of anonymised context
        """
        event = {
            "id":          str(uuid.uuid4()),
            "event_type":  event_type,
            "user_id":     user_id,
            "metadata":    metadata or {},
            "occurred_at": datetime.now(timezone.utc).isoformat(),
        }
        if _DB_URL:
            self._persist_db(event)
        else:
            _EVENTS.append(event)
            log.debug("event_recorded",
                      extra={"type": event_type, "user": user_id[:8]})
        return event["id"]

    def query(
        self,
        from_date: str,
        to_date: str,
        event_type: str | None = None,
        limit: int = 1000,
    ) -> list[dict]:
        """
        Fetch events in a date range. Returns raw event dicts.
        In dev mode reads from in-memory list.
        """
        if _DB_URL:
            return self._query_db(from_date, to_date, event_type, limit)

        results = [
            e for e in _EVENTS
            if from_date <= e["occurred_at"][:10] <= to_date
            and (event_type is None or e["event_type"] == event_type)
        ]
        return results[:limit]

    def count_by_type(self, from_date: str, to_date: str) -> dict[str, int]:
        """Return {event_type: count} for the given range."""
        events = self.query(from_date, to_date)
        counts: dict[str, int] = {}
        for e in events:
            counts[e["event_type"]] = counts.get(e["event_type"], 0) + 1
        return counts

    # ── DB helpers (stub — replace with real psycopg2 calls in production) ──

    def _persist_db(self, event: dict) -> None:
        """Insert event into analytics_events table via psycopg2."""
        try:
            import psycopg2, json
            with psycopg2.connect(_DB_URL) as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "INSERT INTO analytics_events "
                        "(id, event_type, user_id, metadata, occurred_at) "
                        "VALUES (%s, %s, %s, %s, %s)",
                        (event["id"], event["event_type"], event["user_id"],
                         json.dumps(event["metadata"]), event["occurred_at"]),
                    )
        except Exception as exc:
            log.error("event_db_write_failed", extra={"error": str(exc)})
            _EVENTS.append(event)  # fall back to memory

    def _query_db(self, from_date: str, to_date: str,
                  event_type: str | None, limit: int) -> list[dict]:
        try:
            import psycopg2, psycopg2.extras
            with psycopg2.connect(_DB_URL) as conn:
                with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                    sql = (
                        "SELECT * FROM analytics_events "
                        "WHERE occurred_at::date BETWEEN %s AND %s"
                    )
                    params: list = [from_date, to_date]
                    if event_type:
                        sql += " AND event_type = %s"
                        params.append(event_type)
                    sql += f" ORDER BY occurred_at DESC LIMIT {limit}"
                    cur.execute(sql, params)
                    return [dict(r) for r in cur.fetchall()]
        except Exception as exc:
            log.error("event_db_query_failed", extra={"error": str(exc)})
            return []
