-- 105_api_tokens_scopes_and_audit.sql — Migration: api_tokens scopes + audit
-- Generated for SEED-1 (project-history/roadmaps/julia-agents-academia-2026-09.md)
-- Schema: social_wiring
--
-- Contract §B.0 (projects/julia-agents-academia-CONTRACT.md): every product
-- token gets an expiry, an optional bound automation principal, a
-- human-personal flag, and a minted-by attribution — plus a best-effort
-- audit trail table the seed's `SupabaseApiTokenAuditWriter`
-- (`noctusai_lib.api.auth.session.audit`) writes to.
--
-- ORDERING (contract §B.0): this migration MUST be applied BEFORE the
-- resolver that reads `expires_at` is deployed — the reverse order treats
-- every live token as having no expiry check yet, which is safe, but
-- deploying the resolver first would 500 on the missing column instead.

-- ============================================================
-- Schema lock — pin name resolution to social_wiring, public
-- IDEMPOTENT: session-level setting; no DDL emitted.
-- ============================================================
SET search_path = social_wiring, public;

-- ── api_tokens: new columns ─────────────────────────────────────────────
ALTER TABLE social_wiring.api_tokens
    ADD COLUMN IF NOT EXISTS expires_at        TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS principal_agent_id UUID,
    ADD COLUMN IF NOT EXISTS issuer             TEXT,
    ADD COLUMN IF NOT EXISTS human_personal     BOOLEAN NOT NULL DEFAULT false,
    ADD COLUMN IF NOT EXISTS minted_by          UUID;

-- Backfill every pre-existing live token with a 365-day expiry from now
-- (contract §B.0's three-condition backfill — condition 2, an audit row
-- per backfilled token, is emitted below; condition 3, the 30-day expiry
-- alert, is a monitoring/cron concern out of this migration's scope).
UPDATE social_wiring.api_tokens
   SET expires_at = now() + interval '365 days'
 WHERE expires_at IS NULL;

-- ── api_token_audit ──────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS social_wiring.api_token_audit (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    api_token_id  UUID NOT NULL REFERENCES social_wiring.api_tokens(id),
    org_id        UUID NOT NULL,
    method        TEXT NOT NULL,
    path          TEXT NOT NULL,
    status        INTEGER NOT NULL,
    at            TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE social_wiring.api_token_audit ENABLE ROW LEVEL SECURITY;

CREATE POLICY "api_token_audit_select_own_org" ON social_wiring.api_token_audit
    FOR SELECT TO authenticated
    USING (org_id = current_org_id());

-- service_role_bypass — keeper-audited canonical literal policy name
-- (check_admin_endpoint_service_role_bypass): the audit writer runs on
-- the admin client (RLS would otherwise block every write — the audit
-- trail exists precisely because the caller already bypassed
-- authenticated-user RLS to resolve the token in the first place).
CREATE POLICY "service_role_bypass" ON social_wiring.api_token_audit
    FOR ALL TO service_role USING (true) WITH CHECK (true);

-- Backfill one audit row per pre-existing token, recording the
-- expires_at backfill itself (contract §B.0 condition 2).
INSERT INTO social_wiring.api_token_audit (api_token_id, org_id, method, path, status, at)
SELECT id, org_id, 'MIGRATION', '105_api_tokens_scopes_and_audit', 0, now()
  FROM social_wiring.api_tokens;

CREATE INDEX IF NOT EXISTS idx_sw_api_token_audit_org
    ON social_wiring.api_token_audit(org_id);
CREATE INDEX IF NOT EXISTS idx_sw_api_token_audit_token
    ON social_wiring.api_token_audit(api_token_id);
