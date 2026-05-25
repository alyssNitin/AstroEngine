-- ============================================================
-- Migration 005: Gender field + GDPR account deletion support
-- ============================================================
-- 1. Adds gender column to kundli_profiles
-- 2. Adds is_deleted + deleted_at columns to users for soft-delete (GDPR)
-- 3. Adds data_export_requested_at for GDPR audit trail
-- ============================================================

-- ── kundli_profiles: add gender ──────────────────────────────────────────────
ALTER TABLE kundli_profiles
    ADD COLUMN IF NOT EXISTS gender VARCHAR(20) DEFAULT NULL;

COMMENT ON COLUMN kundli_profiles.gender IS
    'Optional gender for chart analysis (M/F/Other). Not PII-sensitive.';

-- ── users: GDPR soft-delete support ──────────────────────────────────────────
ALTER TABLE users
    ADD COLUMN IF NOT EXISTS is_deleted                BOOLEAN     NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS deleted_at                TIMESTAMPTZ          DEFAULT NULL,
    ADD COLUMN IF NOT EXISTS anonymised_at             TIMESTAMPTZ          DEFAULT NULL,
    ADD COLUMN IF NOT EXISTS data_export_requested_at  TIMESTAMPTZ          DEFAULT NULL;

COMMENT ON COLUMN users.is_deleted IS
    'Soft-delete flag. TRUE = account deleted by user (GDPR). PII anonymised in-place.';
COMMENT ON COLUMN users.deleted_at IS
    'Timestamp when the user requested account deletion.';
COMMENT ON COLUMN users.anonymised_at IS
    'Timestamp when PII fields were anonymised (email → anon-uuid@deleted.invalid).';

-- Partial index: only index non-deleted users for auth queries (performance)
CREATE INDEX IF NOT EXISTS idx_users_active_email
    ON users (email)
    WHERE is_deleted = FALSE;
