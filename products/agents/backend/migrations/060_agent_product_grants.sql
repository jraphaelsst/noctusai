-- ============================================================================
-- 060: agents.agent_product_grants -- the platform grant ledger (Julia-line CONTRACT D1).
--
-- A platform admin wires one agent instance of one org to one product ("grant"): agents mints the channel
-- token (agents.api_tokens), the product's tools token (<product schema>.api_tokens) and delivers the credential
-- to the product. This table records which tokens belong to which grant; the tokens themselves reuse
-- api_tokens unchanged (only a SHA-256 of a secret is ever stored there, and nothing here holds a secret).
--
--   status  pendente -> ativo | falhou ; ativo -> revogado.   `pendente` exists only while a mint+deliver runs.
--   expires_at NULL = the grant never expires (owner decision 2026-11-04); revocation and last_used_at still apply.
--   product_token_id lives in ANOTHER schema (the product's api_tokens), hence no FK.
--   agent_id is the org's instance (agents.agents.id); no FK so agent lifecycle deletes are never blocked by a
--   ledger row (048 refuses to delete an agent with a live channel token already).
--
-- ONE live grant per (org, agent, product): partial UNIQUE over pendente+ativo (a failed or revoked grant may be
-- re-created; two concurrent creates cannot both run).
--
-- SERVICE-ROLE ONLY (platform-admin control plane, same posture as plataforma_controles): RLS on, the single
-- service_role_bypass policy, no grant to authenticated / anon.
-- ============================================================================

SET search_path = agents, public;

CREATE TABLE IF NOT EXISTS agents.agent_product_grants (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id              UUID NOT NULL,
    agent_id            UUID NOT NULL,
    agent_key           TEXT NOT NULL CHECK (agent_key ~ '^[a-z0-9]+([-_][a-z0-9]+)*$' AND length(agent_key) <= 64),
    product             TEXT NOT NULL CHECK (product ~ '^[a-z0-9]+(-[a-z0-9]+)*$' AND length(product) <= 64),
    status              TEXT NOT NULL DEFAULT 'pendente' CHECK (status IN ('pendente', 'ativo', 'revogado', 'falhou')),
    channel_token_id    UUID NULL REFERENCES agents.api_tokens(id),
    product_token_id    UUID NULL,
    expires_at          TIMESTAMPTZ NULL,
    created_by          UUID NULL,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    revoked_by          UUID NULL,
    revoked_at          TIMESTAMPTZ NULL,
    last_delivered_at   TIMESTAMPTZ NULL,
    last_error          TEXT NULL CHECK (last_error IS NULL OR length(last_error) <= 500)
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_agent_product_grants_one_live
    ON agents.agent_product_grants (org_id, agent_id, product)
    WHERE status IN ('pendente', 'ativo');

CREATE INDEX IF NOT EXISTS idx_agent_product_grants_org ON agents.agent_product_grants (org_id, created_at DESC);

ALTER TABLE agents.agent_product_grants ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "service_role_bypass" ON agents.agent_product_grants;
CREATE POLICY "service_role_bypass" ON agents.agent_product_grants
    FOR ALL TO service_role USING (true) WITH CHECK (true);
REVOKE ALL ON agents.agent_product_grants FROM anon, authenticated;
