-- ============================================================
-- Migration 004: Security Hardening
-- ============================================================
-- Adds account lockout tracking columns to the users table.
-- failed_login_attempts : rolling count of consecutive failures
-- locked_until          : NULL = unlocked; future timestamp = locked
-- last_failed_login     : timestamp of most recent failure (for decay)
-- ============================================================

ALTER TABLE users
    ADD COLUMN IF NOT EXISTS failed_login_attempts INTEGER     NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS locked_until          TIMESTAMPTZ          DEFAULT NULL,
    ADD COLUMN IF NOT EXISTS last_failed_login     TIMESTAMPTZ          DEFAULT NULL;

CREATE INDEX IF NOT EXISTS idx_users_locked_until
    ON users (locked_until)
    WHERE locked_until IS NOT NULL;
