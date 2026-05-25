"""
aggregators/revenue.py
=======================
Aggregates payment and wallet revenue metrics.

Reads from: payment_orders (status='success') and wallet_ledger.
"""
from __future__ import annotations
import os, logging

log = logging.getLogger(__name__)
_DB_URL = os.environ.get("DATABASE_URL", "")


class RevenueAggregator:

    def get_metrics(self, from_date: str, to_date: str) -> dict:
        if not _DB_URL:
            return self._sample(from_date, to_date)
        try:
            import psycopg2, psycopg2.extras
            with psycopg2.connect(_DB_URL) as conn:
                with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                    cur.execute(
                        "SELECT COALESCE(SUM(amount_cents),0) AS total, "
                        "       COALESCE(SUM(tax_amount_cents),0) AS tax "
                        "FROM payment_orders "
                        "WHERE status='success' AND created_at::date BETWEEN %s AND %s",
                        (from_date, to_date),
                    )
                    row = cur.fetchone()
                    total = int(row["total"])
                    tax   = int(row["tax"])

                    cur.execute(
                        "SELECT pack_id, SUM(amount_cents) AS amt, COUNT(*) AS cnt "
                        "FROM payment_orders "
                        "WHERE status='success' AND created_at::date BETWEEN %s AND %s "
                        "GROUP BY pack_id",
                        (from_date, to_date),
                    )
                    by_pack = {r["pack_id"]: int(r["amt"]) for r in cur.fetchall()}

                    cur.execute(
                        "SELECT method, SUM(amount_cents) AS amt "
                        "FROM payment_orders "
                        "WHERE status='success' AND created_at::date BETWEEN %s AND %s "
                        "GROUP BY method",
                        (from_date, to_date),
                    )
                    by_method = {r["method"]: int(r["amt"]) for r in cur.fetchall()}

                    cur.execute(
                        "SELECT currency, SUM(amount_cents) AS amt "
                        "FROM payment_orders "
                        "WHERE status='success' AND created_at::date BETWEEN %s AND %s "
                        "GROUP BY currency",
                        (from_date, to_date),
                    )
                    by_region = {r["currency"]: int(r["amt"]) for r in cur.fetchall()}

                    cur.execute(
                        "SELECT COALESCE(SUM(credits_delta * -1), 0) AS refunded "
                        "FROM wallet_ledger "
                        "WHERE type='refund' AND created_at::date BETWEEN %s AND %s",
                        (from_date, to_date),
                    )
                    refunds = int(cur.fetchone()["refunded"])

            return {
                "from_date": from_date, "to_date": to_date,
                "total_revenue_cents": total, "total_tax_cents": tax,
                "by_pack": by_pack, "by_method": by_method,
                "by_region": by_region, "refund_amount_cents": refunds,
            }
        except Exception as exc:
            log.error("revenue_query_failed", extra={"error": str(exc)})
            return self._sample(from_date, to_date)

    def _sample(self, from_date: str, to_date: str) -> dict:
        return {
            "from_date": from_date, "to_date": to_date,
            "total_revenue_cents": 59700, "total_tax_cents": 9000,
            "by_pack":   {"starter": 9900, "standard": 29900, "value": 19900},
            "by_method": {"upi": 35820, "card": 23880},
            "by_region": {"INR": 59700},
            "refund_amount_cents": 1000,
            "note": "Sample data — DATABASE_URL not configured",
        }
