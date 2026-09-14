-- ============================================================================
-- 007_api_tokens.sql — agents.api_tokens + agents.api_token_audit
-- (contract §B.0 / §F, project-history/roadmaps/julia-agents-academia-2026-09.md)
--
-- Fresh product (no pre-existing api_tokens row to backfill), so this is a
-- single CREATE carrying every SEED-1 column from the start — the shape is
-- the SAME as social-wiring's 001 (base table) + 105 (scopes/audit columns)
-- combined, not a two-step ALTER. A `pk_` bearer CAN resolve against this
-- table (`SupabaseApiTokenResolver(schema="agents")`), but every route in
-- this product is user-only (contract §E intro), so a resolved product
-- caller always gets refused with 403 `user_required` — never an ambiguous
-- 401 that looks like "token not found".
-- ============================================================================

SET search_path = agents, public;

CREATE TABLE agents.api_tokens (
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
    expires_at          TIMESTAMPTZ,
    principal_agent_id  UUID,
    issuer              TEXT,
    human_personal      BOOLEAN NOT NULL DEFAULT false,
    minted_by           UUID
);

ALTER TABLE agents.api_tokens ENABLE ROW LEVEL SECURITY;

CREATE POLICY "api_tokens_select_own_org" ON agents.api_tokens
    FOR SELECT TO authenticated
    USING (org_id = current_org_id());

-- INSERT + UPDATE limited to owner/admin org_role (matches the platform's
-- convention for sensitive config; org_role lives in noctus_users).
CREATE POLICY "api_tokens_insert_own_org_admin" ON agents.api_tokens
    FOR INSERT TO authenticated
    WITH CHECK (
        org_id = current_org_id()
        AND EXISTS (
            SELECT 1 FROM public.noctus_users nu
            WHERE nu.id = (SELECT auth.uid())
              AND nu.org_id = agents.api_tokens.org_id
              AND nu.org_role IN ('owner', 'admin')
        )
    );

CREATE POLICY "api_tokens_update_own_org_admin" ON agents.api_tokens
    FOR UPDATE TO authenticated
    USING (
        org_id = current_org_id()
        AND EXISTS (
            SELECT 1 FROM public.noctus_users nu
            WHERE nu.id = (SELECT auth.uid())
              AND nu.org_id = agents.api_tokens.org_id
              AND nu.org_role IN ('owner', 'admin')
        )
    );

CREATE POLICY "service_role_bypass" ON agents.api_tokens
    FOR ALL TO service_role USING (true) WITH CHECK (true);

CREATE INDEX idx_agents_api_tokens_org ON agents.api_tokens(org_id) WHERE revoked_at IS NULL;
CREATE UNIQUE INDEX idx_agents_api_tokens_hash_active ON agents.api_tokens(token_hash) WHERE revoked_at IS NULL;

-- ── api_token_audit ──────────────────────────────────────────────────────
CREATE TABLE agents.api_token_audit (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    api_token_id  UUID NOT NULL REFERENCES agents.api_tokens(id),
    org_id        UUID NOT NULL,
    method        TEXT NOT NULL,
    path          TEXT NOT NULL,
    status        INTEGER NOT NULL,
    at            TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE agents.api_token_audit ENABLE ROW LEVEL SECURITY;

CREATE POLICY "api_token_audit_select_own_org" ON agents.api_token_audit
    FOR SELECT TO authenticated
    USING (org_id = current_org_id());

-- service_role_bypass — keeper-audited canonical literal policy name
-- (check_admin_endpoint_service_role_bypass): the audit writer runs on the
-- admin client (RLS would otherwise block every write — the audit trail
-- exists precisely because the caller already bypassed authenticated-user
-- RLS to resolve the token in the first place).
CREATE POLICY "service_role_bypass" ON agents.api_token_audit
    FOR ALL TO service_role USING (true) WITH CHECK (true);

CREATE INDEX idx_agents_api_token_audit_org ON agents.api_token_audit(org_id);
CREATE INDEX idx_agents_api_token_audit_token ON agents.api_token_audit(api_token_id);
