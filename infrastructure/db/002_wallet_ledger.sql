-- ============================================================
-- Migration 002: Wallet Ledger + Paid/Promo Balance Split
-- ============================================================
-- Run after 001_init_schema.sql
-- Adds:
--   1. paid_balance_cents  — balance from real payments
--   2. promo_balance_cents — balance from welcome credits / refunds / gifts
--   3. wallet_ledger table — immutable append-only transaction log
-- ============================================================

-- ── 1. Add balance columns to users ─────────────────────────
ALTER TABLE users
    ADD COLUMN IF NOT EXISTS paid_balance_cents  INTEGER NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS promo_balance_cents INTEGER NOT NULL DEFAULT 0;

-- Back-fill: treat existing wallet_balance_cents as promo (safest default)
UPDATE users
   SET promo_balance_cents = wallet_balance_cents
 WHERE promo_balance_cents = 0
   AND wallet_balance_cents > 0;

-- ── 2. Immutable wallet ledger table ─────────────────────────
CREATE TABLE IF NOT EXISTS wallet_ledger (
    id              BIGSERIAL    PRIMARY KEY,
    email           TEXT         NOT NULL,
    txn_type        TEXT         NOT NULL,   -- 'debit' | 'credit' | 'refund' | 'topup' | 'welcome'
    balance_type    TEXT         NOT NULL,   -- 'paid' | 'promo' | 'mixed'
    amount_cents    INTEGER      NOT NULL,
    reason          TEXT         NOT NULL DEFAULT '',
    -- running totals at the time of the transaction
    paid_after      INTEGER      NOT NULL DEFAULT 0,
    promo_after     INTEGER      NOT NULL DEFAULT 0,
    total_after     INTEGER      NOT NULL DEFAULT 0,
    reference_id    TEXT         NOT NULL DEFAULT '',  -- session_id, order_id, etc.
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

-- Index for fast per-user lookups (newest first)
CREATE INDEX IF NOT EXISTS idx_wallet_ledger_email_ts
    ON wallet_ledger (email, created_at DESC);

-- Index for reporting
CREATE INDEX IF NOT EXISTS idx_wallet_ledger_type
    ON wallet_ledger (txn_type, created_at DESC);
