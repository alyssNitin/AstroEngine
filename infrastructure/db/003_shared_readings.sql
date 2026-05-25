-- ============================================================
-- Migration 003: PIN-Protected Shareable Reading Links
-- ============================================================
-- Adds the shared_readings table for generating secure,
-- time-limited, PIN-protected reading share links.
-- ============================================================

CREATE TABLE IF NOT EXISTS shared_readings (
    id              TEXT        PRIMARY KEY,          -- UUID share token (used in URL)
    email           TEXT        NOT NULL,             -- owner's email
    pin_hash        TEXT        NOT NULL,             -- SHA-256(pin) — 4-digit PIN
    session_id      TEXT        NOT NULL DEFAULT '',  -- originating session ID (informational)

    -- Content snapshot (captured at share time so it's immutable)
    name            TEXT        NOT NULL DEFAULT '',
    date_of_birth   TEXT        NOT NULL DEFAULT '',
    time_of_birth   TEXT        NOT NULL DEFAULT '',
    place_of_birth  TEXT        NOT NULL DEFAULT '',
    overall_theme   TEXT        NOT NULL DEFAULT '',
    refined_analysis TEXT       NOT NULL DEFAULT '',
    lagna_info_json  TEXT       NOT NULL DEFAULT '{}',

    -- Access control
    expires_at      TIMESTAMPTZ NOT NULL,             -- 72 hours from creation
    view_count      INTEGER     NOT NULL DEFAULT 0,
    max_views       INTEGER     NOT NULL DEFAULT 50,  -- anti-abuse cap

    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_shared_readings_email
    ON shared_readings (email, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_shared_readings_expires
    ON shared_readings (expires_at);
