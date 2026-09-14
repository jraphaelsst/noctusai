-- ============================================================================
-- Migration 008 — api_tokens + api_token_audit (contract §B.0).
--
-- Academia is a NEW consumer of the seed's product-token auth surface (the
-- seed `create_auth_router`'s `/api/settings/api-tokens` mint route + the
-- `SupabaseApiTokenResolver` / `SupabaseApiTokenAuditWriter` adapters). It
-- never had a pre-SEED-1 `api_tokens` table, so — unlike social-wiring's
-- `105_api_tokens_scopes_and_audit.sql` (an ALTER on an existing table) —
-- this migration CREATEs the table with every SEED-1 column baked in from
-- the start: `expires_at`, `principal_agent_id`, `issuer`,
-- `human_personal`, `minted_by`. Same shape as social-wiring `001` (base
-- columns) + `105` (SEED-1 columns) combined into one CREATE.
--
-- NOT APPLIED by this slice (A1b) — the tech-lead applies it per the
-- roadmap's deploy-order rule (contract §F: the migration lands BEFORE
-- any image reading these columns is deployed).
-- ============================================================================

SET search_path = academia_de_reciclagem, public;

-- ── api_tokens ──────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS academia_de_reciclagem.api_tokens (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id              UUID NOT NULL,
    label               TEXT NOT NULL,
    token_hash          TEXT NOT NULL UNIQUE,
    token_prefix        TEXT NOT NULL,
    scopes              TEXT[] NOT NULL DEFAULT '{}',
    created_by          UUID,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_used_at        TIMESTAMPTZ,
    revoked_at          TIMESTAMPTZ,
    -- SEED-1 (contract §B.0) — baked in from the start; no backfill
    -- needed since this table has no pre-SEED-1 rows.
    expires_at          TIMESTAMPTZ NOT NULL,
    principal_agent_id  UUID,
    issuer              TEXT,
    human_personal      BOOLEAN NOT NULL DEFAULT false,
    minted_by           UUID
);

ALTER TABLE academia_de_reciclagem.api_tokens ENABLE ROW LEVEL SECURITY;

CREATE POLICY "api_tokens_select_own_org" ON academia_de_reciclagem.api_tokens
    FOR SELECT TO authenticated
    USING (org_id = current_org_id());

-- INSERT + UPDATE limited to owner/admin org_role (matches the platform's
-- convention for sensitive config; org_role lives in noctus_users).
CREATE POLICY "api_tokens_insert_own_org_admin" ON academia_de_reciclagem.api_tokens
    FOR INSERT TO authenticated
    WITH CHECK (
        org_id = current_org_id()
        AND EXISTS (
            SELECT 1 FROM public.noctus_users nu
            WHERE nu.id = (SELECT auth.uid())
              AND nu.org_id = academia_de_reciclagem.api_tokens.org_id
              AND nu.org_role IN ('owner', 'admin')
        )
    );

CREATE POLICY "api_tokens_update_own_org_admin" ON academia_de_reciclagem.api_tokens
    FOR UPDATE TO authenticated
    USING (
        org_id = current_org_id()
        AND EXISTS (
            SELECT 1 FROM public.noctus_users nu
            WHERE nu.id = (SELECT auth.uid())
              AND nu.org_id = academia_de_reciclagem.api_tokens.org_id
              AND nu.org_role IN ('owner', 'admin')
        )
    );

-- service_role_bypass — keeper-audited canonical literal policy name
-- (check_admin_endpoint_service_role_bypass): the resolver + mint route
-- both run on the admin client.
CREATE POLICY "service_role_bypass" ON academia_de_reciclagem.api_tokens
    FOR ALL TO service_role USING (true) WITH CHECK (true);

CREATE INDEX IF NOT EXISTS idx_academia_api_tokens_org
    ON academia_de_reciclagem.api_tokens(org_id) WHERE revoked_at IS NULL;
CREATE UNIQUE INDEX IF NOT EXISTS idx_academia_api_tokens_hash_active
    ON academia_de_reciclagem.api_tokens(token_hash) WHERE revoked_at IS NULL;

-- ── api_token_audit ─────────────────────────────────────────────────────
-- Contract §B.0: "every resolved product-token call writes
-- api_token_audit(api_token_id, org_id, method, path, status, at),
-- best-effort and logged loudly on failure" — written by
-- `noctusai_lib.api.auth.session.audit_middleware` (this slice, A1b).

CREATE TABLE IF NOT EXISTS academia_de_reciclagem.api_token_audit (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    api_token_id  UUID NOT NULL REFERENCES academia_de_reciclagem.api_tokens(id),
    org_id        UUID NOT NULL,
    method        TEXT NOT NULL,
    path          TEXT NOT NULL,
    status        INTEGER NOT NULL,
    at            TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE academia_de_reciclagem.api_token_audit ENABLE ROW LEVEL SECURITY;

CREATE POLICY "api_token_audit_select_own_org" ON academia_de_reciclagem.api_token_audit
    FOR SELECT TO authenticated
    USING (org_id = current_org_id());

CREATE POLICY "service_role_bypass" ON academia_de_reciclagem.api_token_audit
    FOR ALL TO service_role USING (true) WITH CHECK (true);

CREATE INDEX IF NOT EXISTS idx_academia_api_token_audit_org
    ON academia_de_reciclagem.api_token_audit(org_id);
CREATE INDEX IF NOT EXISTS idx_academia_api_token_audit_token
    ON academia_de_reciclagem.api_token_audit(api_token_id);
