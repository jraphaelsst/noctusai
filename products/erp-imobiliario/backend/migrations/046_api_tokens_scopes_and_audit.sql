-- 046_api_tokens_scopes_and_audit.sql — Migration: api_tokens scopes + audit
-- Generated for SEED-1 (project-history/roadmaps/julia-agents-academia-2026-09.md)
-- Schema: erp
--
-- Same shape as social-wiring's 105_api_tokens_scopes_and_audit.sql
-- (contract §F: "erp-imobiliario | same shape as social-wiring"). ERP's
-- `get_auth_context` composition still wires `FakeApiTokenResolver()`
-- (never resolves a `pk_*` bearer) — this migration adds the columns +
-- audit table for parity/future-readiness ONLY; it does NOT switch ERP's
-- wiring to the seed's `SupabaseApiTokenResolver` (that would newly enable
-- product-token auth on a live product — explicitly out of SEED-1's scope,
-- see the dispatch brief).

SET search_path = erp, public;

-- ── api_tokens: new columns ─────────────────────────────────────────────
ALTER TABLE erp.api_tokens
    ADD COLUMN IF NOT EXISTS expires_at        TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS principal_agent_id UUID,
    ADD COLUMN IF NOT EXISTS issuer             TEXT,
    ADD COLUMN IF NOT EXISTS human_personal     BOOLEAN NOT NULL DEFAULT false,
    ADD COLUMN IF NOT EXISTS minted_by          UUID;

UPDATE erp.api_tokens
   SET expires_at = now() + interval '365 days'
 WHERE expires_at IS NULL;

-- ── api_token_audit ──────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS erp.api_token_audit (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    api_token_id  UUID NOT NULL REFERENCES erp.api_tokens(id),
    org_id        UUID NOT NULL,
    method        TEXT NOT NULL,
    path          TEXT NOT NULL,
    status        INTEGER NOT NULL,
    at            TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE erp.api_token_audit ENABLE ROW LEVEL SECURITY;

CREATE POLICY "api_token_audit_select_own_org" ON erp.api_token_audit
    FOR SELECT TO authenticated
    USING (org_id = current_org_id());

-- service_role_bypass — keeper-audited canonical literal policy name
-- (check_admin_endpoint_service_role_bypass).
CREATE POLICY "service_role_bypass" ON erp.api_token_audit
    FOR ALL TO service_role USING (true) WITH CHECK (true);

INSERT INTO erp.api_token_audit (api_token_id, org_id, method, path, status, at)
SELECT id, org_id, 'MIGRATION', '046_api_tokens_scopes_and_audit', 0, now()
  FROM erp.api_tokens;

CREATE INDEX IF NOT EXISTS idx_erp_api_token_audit_org
    ON erp.api_token_audit(org_id);
CREATE INDEX IF NOT EXISTS idx_erp_api_token_audit_token
    ON erp.api_token_audit(api_token_id);
