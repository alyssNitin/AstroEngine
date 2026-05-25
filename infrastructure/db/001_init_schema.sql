-- ─────────────────────────────────────────────────────────────────────────────
-- NarayanAstroReader — PostgreSQL Schema
-- Migration: 001_init_schema
-- Run once against a fresh database:
--   psql $DATABASE_URL -f infrastructure/db/001_init_schema.sql
-- ─────────────────────────────────────────────────────────────────────────────

-- ── Users ─────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS users (
    id                          TEXT            PRIMARY KEY,
    email                       TEXT            UNIQUE NOT NULL,
    name                        TEXT            NOT NULL DEFAULT '',
    password_hash               TEXT            NOT NULL DEFAULT '',

    -- Email verification
    email_verified              BOOLEAN         NOT NULL DEFAULT FALSE,
    verification_token          TEXT            DEFAULT NULL,
    verification_token_expires  TIMESTAMPTZ     DEFAULT NULL,
    verification_resend_count   INTEGER         NOT NULL DEFAULT 0,
    verification_resend_window  TIMESTAMPTZ     DEFAULT NULL,

    -- Kundli / birth data
    date_of_birth               TEXT            NOT NULL DEFAULT '',
    time_of_birth               TEXT            NOT NULL DEFAULT '',
    place_of_birth              TEXT            NOT NULL DEFAULT '',
    latitude                    DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    longitude                   DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    timezone_offset             DOUBLE PRECISION NOT NULL DEFAULT 0.0,

    -- Kundli JSON blobs (stored as TEXT; validated as JSON in application layer)
    kundli_json                 TEXT            NOT NULL DEFAULT '{}',
    predictions_json            TEXT            NOT NULL DEFAULT '{}',
    overall_theme               TEXT            NOT NULL DEFAULT '',
    lagna_json                  TEXT            NOT NULL DEFAULT '{}',
    birth_info_json             TEXT            NOT NULL DEFAULT '{}',
    refined_analysis            TEXT            NOT NULL DEFAULT '',
    planet_knowledge_json       TEXT            NOT NULL DEFAULT '{}',
    children_info_json          TEXT            NOT NULL DEFAULT '{}',
    marital_status              TEXT            NOT NULL DEFAULT '',

    -- Account settings
    user_type                   TEXT            NOT NULL DEFAULT 'general',
    preferred_language          TEXT            NOT NULL DEFAULT 'English',
    region                      TEXT            NOT NULL DEFAULT 'India',
    currency                    TEXT            NOT NULL DEFAULT 'INR',

    -- Wallet (integer minor units: paise for India, cents for International)
    wallet_balance_cents        INTEGER         NOT NULL DEFAULT 0,
    wallet_transactions         TEXT            NOT NULL DEFAULT '[]',

    -- Active session
    session_id                  TEXT            NOT NULL DEFAULT '',
    chat_messages_json          TEXT            NOT NULL DEFAULT '[]',

    -- Audit
    created_at                  TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    updated_at                  TIMESTAMPTZ     NOT NULL DEFAULT NOW()
);

-- ── Reading history ───────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS reading_history (
    id                    TEXT            PRIMARY KEY,
    email                 TEXT            NOT NULL,
    name                  TEXT            NOT NULL DEFAULT '',
    date_of_birth         TEXT            NOT NULL DEFAULT '',
    time_of_birth         TEXT            NOT NULL DEFAULT '',
    place_of_birth        TEXT            NOT NULL DEFAULT '',
    overall_theme         TEXT            NOT NULL DEFAULT '',
    refined_analysis      TEXT            NOT NULL DEFAULT '',
    chat_messages_json    TEXT            NOT NULL DEFAULT '[]',
    planet_knowledge_json TEXT            NOT NULL DEFAULT '{}',
    session_id            TEXT            NOT NULL DEFAULT '',
    created_at            TIMESTAMPTZ     NOT NULL DEFAULT NOW()
);

-- ── Indexes ───────────────────────────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_users_email
    ON users(email);

CREATE INDEX IF NOT EXISTS idx_users_verification_token
    ON users(verification_token)
    WHERE verification_token IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_reading_history_email
    ON reading_history(email);

CREATE INDEX IF NOT EXISTS idx_reading_history_created_at
    ON reading_history(created_at DESC);

-- ── Auto-update updated_at trigger ───────────────────────────────────────────
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS users_updated_at ON users;
CREATE TRIGGER users_updated_at
    BEFORE UPDATE ON users
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- Done
SELECT 'Schema initialised successfully.' AS status;
