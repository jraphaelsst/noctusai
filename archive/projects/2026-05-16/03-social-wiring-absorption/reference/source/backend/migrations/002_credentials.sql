-- ============================================================================
-- YouTube Crawler — credentials
-- Stores per-org OAuth tokens, refresh tokens encrypted at rest with Fernet.
-- The plaintext never lives in the database; the encryption key lives in the
-- product's .env (ENCRYPTION_KEY) so DB compromise alone cannot recover the
-- refresh token.
-- ============================================================================

SET search_path = youtube_crawler, public;

CREATE TABLE youtube_crawler.credentials (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL,
    provider TEXT NOT NULL,                    -- e.g. 'youtube'
    encrypted_tokens TEXT NOT NULL,            -- Fernet-encrypted JSON {access_token, refresh_token, expires_at, ...}
    channel_id TEXT,                           -- YouTube channel ID (UCxxx...)
    channel_title TEXT,                        -- Human-readable channel name
    scopes TEXT[],                             -- Granted OAuth scopes (audit trail)
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(org_id, provider)
);

ALTER TABLE youtube_crawler.credentials ENABLE ROW LEVEL SECURITY;

-- Matches `rls_subquery_policy(youtube_crawler, "credentials",
--   "credentials_select_own_org", "SELECT",
--   using="org_id = ((SELECT auth.jwt()) ->> 'org_id')::uuid")` output.
CREATE POLICY "credentials_select_own_org" ON youtube_crawler.credentials
    FOR SELECT TO authenticated
    USING (org_id = ((SELECT auth.jwt()) ->> 'org_id')::uuid);

-- Insert/update/delete restricted to service_role — the backend writes via
-- service-role client; clients never write here directly. The encrypted_tokens
-- column should NEVER leak through PostgREST to the browser, but RLS guards
-- against accidental future authenticated writes.
CREATE POLICY "credentials_write_service_role" ON youtube_crawler.credentials
    FOR ALL TO service_role
    USING (true) WITH CHECK (true);

CREATE INDEX idx_youtube_crawler_credentials_org ON youtube_crawler.credentials(org_id);
CREATE INDEX idx_youtube_crawler_credentials_provider ON youtube_crawler.credentials(provider);

INSERT INTO youtube_crawler.status_pagina (nome_pagina, status) VALUES
    ('configuracoes', 'producao')
ON CONFLICT (nome_pagina) DO NOTHING;
