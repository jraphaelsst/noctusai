-- ============================================================================
-- 002 — Google OAuth credentials (Phase 1 of youtube-crawler-domain-implementation)
-- Schema: youtube_crawler
-- Description: One row per (org_id, user_id); stores Fernet-encrypted Google
--   refresh tokens + access tokens. The encryption key is loaded out-of-band
--   from `YOUTUBE_CRAWLER_VAULT_KEY` env var (see app/services/credential_vault.py).
--
-- LGPD: `email`, `refresh_token_encrypted`, `access_token_encrypted` are
--   PII / sensitive credentials. Encryption-at-rest defends against backup
--   exfiltration. Flagged via `noctus.dev.lgpd_flag` at every write site.
--
-- Per the single-001-migration convention (KB § feedback_single_001_migration)
-- this would normally be folded into 001 — but 001 is the original scaffold
-- carryover (`status_pagina` + `invitations`). Treating this as the canonical
-- "phase-1 schema add" file under the same lock-step rule: future phases edit
-- 002+ in lock-step, not 001.
-- ============================================================================

SET search_path = youtube_crawler, public;

-- ─── Updated-at trigger function (idempotent) ────────────────────────────────
-- Output mirrors `noctusai_lib.domain.sql_templates.updated_at_function()`.
CREATE OR REPLACE FUNCTION youtube_crawler.set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;


-- ─── google_credentials ──────────────────────────────────────────────────────
CREATE TABLE youtube_crawler.google_credentials (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL,
    user_id UUID NOT NULL,                              -- operator user
    email TEXT NOT NULL,                                -- LGPD (Google account email)
    refresh_token_encrypted TEXT NOT NULL,              -- Fernet ciphertext (urlsafe-base64)
    access_token_encrypted TEXT,                        -- Fernet ciphertext; nullable until first refresh
    access_token_expires_at TIMESTAMPTZ,                -- absolute UTC; refresh when within ~5min
    scopes TEXT[] NOT NULL DEFAULT '{}',                -- granted scopes (subset of requested)
    state_nonce TEXT,                                   -- CSRF nonce; persisted between authorize + callback
    state_expires_at TIMESTAMPTZ,                       -- nonce TTL (typ. ~10min)
    connected_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    revoked_at TIMESTAMPTZ,                             -- non-NULL once disconnect was called
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(org_id, user_id)                             -- one Google connection per (org, operator)
);

ALTER TABLE youtube_crawler.google_credentials ENABLE ROW LEVEL SECURITY;

-- RLS: org-scoped; matches the canonical `rls_subquery_policy` whitespace shape.
CREATE POLICY "google_credentials_select_own_org" ON youtube_crawler.google_credentials
    FOR SELECT TO authenticated
    USING (org_id = ((SELECT auth.jwt()) ->> 'org_id')::uuid);

CREATE POLICY "google_credentials_insert_own_org" ON youtube_crawler.google_credentials
    FOR INSERT TO authenticated
    WITH CHECK (org_id = ((SELECT auth.jwt()) ->> 'org_id')::uuid);

CREATE POLICY "google_credentials_update_own_org" ON youtube_crawler.google_credentials
    FOR UPDATE TO authenticated
    USING (org_id = ((SELECT auth.jwt()) ->> 'org_id')::uuid);

CREATE POLICY "google_credentials_delete_own_org" ON youtube_crawler.google_credentials
    FOR DELETE TO authenticated
    USING (org_id = ((SELECT auth.jwt()) ->> 'org_id')::uuid);

-- updated_at maintenance
CREATE TRIGGER trg_google_credentials_updated_at
    BEFORE UPDATE ON youtube_crawler.google_credentials
    FOR EACH ROW EXECUTE FUNCTION youtube_crawler.set_updated_at();

CREATE INDEX idx_google_credentials_org_user
    ON youtube_crawler.google_credentials(org_id, user_id);

CREATE INDEX idx_google_credentials_state_nonce
    ON youtube_crawler.google_credentials(state_nonce)
    WHERE state_nonce IS NOT NULL;
