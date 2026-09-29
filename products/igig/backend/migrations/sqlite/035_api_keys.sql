-- ============================================================================
-- IgIg — SQLite mirror of `035_igig_api_keys.sql` (035 ↔ 035).
-- Parity-tested. Same dialect differences as 006-009 (UUID→TEXT,
-- JSONB→TEXT, TIMESTAMPTZ→TEXT, RLS dropped — SQLite has no roles).
-- ============================================================================

CREATE TABLE IF NOT EXISTS credentials (
    id               TEXT PRIMARY KEY,
    org_id           TEXT NOT NULL,
    provider         TEXT NOT NULL,
    encrypted_tokens TEXT NOT NULL,
    metadata         TEXT NOT NULL DEFAULT '{}',
    created_at       TEXT NOT NULL,
    updated_at       TEXT NOT NULL,
    UNIQUE(org_id, provider)
);

CREATE INDEX IF NOT EXISTS idx_igig_credentials_org ON credentials(org_id);
CREATE INDEX IF NOT EXISTS idx_igig_credentials_provider ON credentials(provider);
