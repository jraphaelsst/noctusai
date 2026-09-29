-- ============================================================================
-- 035_igig_api_keys.sql — IGIG (igig)
--
-- Org-scoped, Fernet-encrypted managed API keys. Owner decision
-- 2026-09-28: IgIg gets its OWN per-org Anthropic key (same mechanism
-- `social-wiring` and `community` consume — N=2→N=3 recurrence, this
-- product is the seed router's second consumer) so an agency can set/
-- change it from Integrações → Chaves de API instead of depending on the
-- platform-wide default.
--
-- `credentials` is the VERBATIM output of
-- `noctusai_lib.security.api_keys.credentials_table_ddl("igig")`
-- (authoring-time helper, not a live-apply tool — copied here so this
-- migration is the single source of truth, same as `community`'s own
-- migration 011 for the identical table shape). Backs
-- `noctusai_seed.api_keys_router` mounted at
-- `app/routers/api_keys_router.py` — `GET/PUT/DELETE
-- /api/settings/api-keys*`.
--
-- Encrypted at rest with `IGIG_COFRE_KEY` (Fernet) — the SAME key that
-- already gates the Cofre de Acessos (008) and the canal/e-mail secrets
-- (010), not a new env var. See
-- `noctusai_lib.security.api_keys.require_fernet`.
--
-- Assumes `public.current_org_id()` already exists on this Supabase
-- project (004_rls_current_org_id.sql codified it for igig's own RLS
-- policies). `ALTER DEFAULT PRIVILEGES IN SCHEMA igig GRANT ALL ON
-- TABLES TO authenticated, service_role` (001) already covers this new
-- table — no explicit GRANT needed here.
--
-- SQLite mirror: migrations/sqlite/035_api_keys.sql (parity-tested).
-- ============================================================================
SET search_path = igig, public;

CREATE TABLE igig.credentials (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL,
    provider TEXT NOT NULL,
    encrypted_tokens TEXT NOT NULL,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(org_id, provider)
);

ALTER TABLE igig.credentials ENABLE ROW LEVEL SECURITY;

CREATE POLICY "credentials_select_own_org" ON igig.credentials FOR SELECT TO authenticated
  USING (org_id = current_org_id());

CREATE POLICY "credentials_service_role_bypass" ON igig.credentials FOR ALL TO service_role USING (true) WITH CHECK (true);

CREATE INDEX idx_igig_credentials_org ON igig.credentials(org_id);
CREATE INDEX idx_igig_credentials_provider ON igig.credentials(provider);
