"""
backend/scheduler/promo_expiry.py
==================================
Promotional credit expiry cron job.

Architecture §5.2 / TC-WALLET-007:
  Promotional credits must expire after 30 days.
  A nightly scheduler zeroes out expired promo balances and writes an
  immutable ledger entry so the audit trail is complete.

Usage
-----
This module is imported by start.py / main.py which start the APScheduler
BackgroundScheduler.  The job runs nightly at 02:00 UTC.

Schema migration
----------------
The promo_granted_at column is managed by init_schema() in database.py.
No migration logic is needed here.

Can also be run standalone for testing:
    python -m backend.scheduler.promo_expiry
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone

logger = logging.getLogger(__name__)

# How many days before promo credits expire.
PROMO_TTL_DAYS: int = int(os.environ.get("PROMO_TTL_DAYS", "30"))


def _db_conn_cursor():
    """
    Return the module-level _get_conn / _cursor helpers from the database
    module.  Imported lazily so this module can be imported without a live DB.
    """
    from backend.persistence.database import _get_conn, _cursor  # noqa: PLC0415
    return _get_conn, _cursor


def expire_promo_credits(db=None) -> dict:
    """
    Zero out promo_balance_cents for all users whose promo credits have expired.

    Parameters
    ----------
    db : unused — kept for backwards-compatible call signature.
         Connection is obtained via the module-level pool in database.py.

    Returns
    -------
    dict with keys:
      - users_expired: int   — number of users whose promo balance was zeroed
      - credits_expired: int — total paise/cents zeroed across all users
      - errors: list[str]    — any per-user errors encountered
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=PROMO_TTL_DAYS)
    users_expired = 0
    credits_expired = 0
    errors: list[str] = []

    try:
        _get_conn, _cursor = _db_conn_cursor()
    except Exception as e:
        logger.error("promo_expiry: could not import DB helpers: %s", e)
        return {"users_expired": 0, "credits_expired": 0, "errors": [str(e)]}

    try:
        with _get_conn() as conn:
            with _cursor(conn) as cur:
                # Find users with expired promo credits.
                # promo_granted_at column is guaranteed by init_schema().
                try:
                    cur.execute(
                        """
                        SELECT email, promo_balance_cents, promo_granted_at
                        FROM   users
                        WHERE  promo_balance_cents > 0
                          AND  promo_granted_at IS NOT NULL
                          AND  promo_granted_at < %s
                        """,
                        (cutoff.isoformat(),),
                    )
                    rows = cur.fetchall()
                except Exception as e:
                    logger.warning(
                        "promo_expiry: could not query users: %s", e
                    )
                    return {
                        "users_expired": 0,
                        "credits_expired": 0,
                        "errors": [str(e)],
                    }

                for row in rows:
                    email     = row["email"]
                    promo_bal = int(row["promo_balance_cents"] or 0)
                    now_iso   = datetime.now(timezone.utc).isoformat()

                    try:
                        cur.execute(
                            "UPDATE users SET promo_balance_cents = 0 WHERE email = %s",
                            (email,),
                        )
                        cur.execute(
                            """
                            INSERT INTO wallet_transactions
                                (email, type, amount_cents, balance_before_cents,
                                 balance_after_cents, description, created_at)
                            VALUES (%s, 'promo_expiry', %s, %s, %s,
                                    'Promotional credits expired after 30 days',
                                    %s)
                            """,
                            (email, -promo_bal, promo_bal, 0, now_iso),
                        )
                        users_expired += 1
                        credits_expired += promo_bal
                        logger.info(
                            "promo_expiry: zeroed %d promo cents for %s", promo_bal, email
                        )
                    except Exception as e:
                        errors.append(f"{email}: {e}")
                        logger.error("promo_expiry: failed for %s: %s", email, e)

                conn.commit()

    except Exception as e:
        logger.error("promo_expiry: job failed: %s", e)
        errors.append(str(e))

    result = {
        "users_expired":   users_expired,
        "credits_expired": credits_expired,
        "errors":          errors,
        "ran_at":          datetime.now(timezone.utc).isoformat(),
    }
    logger.info("promo_expiry: complete — %s", result)
    return result


def migrate_promo_schema(db=None) -> None:
    """
    No-op — schema is now managed by init_schema() in database.py.
    Kept for backwards-compatible call signatures in main.py / start.py.
    """
    logger.debug(
        "promo_expiry: migrate_promo_schema() is a no-op — "
        "promo_granted_at is managed by init_schema() in database.py"
    )


def setup_scheduler(db=None) -> object:
    """
    Create and start an APScheduler BackgroundScheduler that runs
    expire_promo_credits() nightly at 02:00 UTC.

    Parameters
    ----------
    db : unused — kept for backwards-compatible call signature.

    Returns
    -------
    scheduler : APScheduler BackgroundScheduler (already started), or None.
    """
    try:
        from apscheduler.schedulers.background import BackgroundScheduler  # noqa: PLC0415
        from apscheduler.triggers.cron import CronTrigger                  # noqa: PLC0415
    except ImportError:
        logger.warning(
            "APScheduler not installed — promo expiry cron disabled. "
            "Install with: pip install apscheduler"
        )
        return None

    scheduler = BackgroundScheduler(timezone="UTC")
    scheduler.add_job(
        func=expire_promo_credits,
        trigger=CronTrigger(hour=2, minute=0),   # 02:00 UTC nightly
        id="promo_expiry",
        name="Expire promotional credits",
        replace_existing=True,
        misfire_grace_time=3600,   # allow up to 1h late if server was down
    )
    scheduler.start()
    logger.info("promo_expiry: scheduler started — runs nightly at 02:00 UTC")
    return scheduler


if __name__ == "__main__":
    # Standalone test run
    import sys
    sys.path.insert(0, ".")
    result = expire_promo_credits()
    print("Expiry result:", result)
