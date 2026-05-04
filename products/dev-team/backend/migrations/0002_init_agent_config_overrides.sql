-- ============================================================================
-- 0002 — dev-team agent config overrides (per-org)
--
-- Per-tenant override storage. The engine's YAML configs ship platform
-- defaults (`dev_team/src/dev_team/configs/default.yaml`); this table lets
-- an org swap one agent's model / provider without rewriting the YAML.
--
-- Effective config = YAML defaults (merged) ← overrides (this table) for
-- the org. Resolved by `app/services/dev_team_proxy.py` when an override
-- table is wired in (post-MVP — for v1 the PATCH /api/configs/{name}
-- endpoint writes directly to YAML via the engine, which is single-source
-- and matches the CLI / MCP behavior).
--
-- Mark this migration "future-state" — it ships the storage so the
-- multi-tenant override path is unblocked, but the API does not yet read
-- from this table. Tracked in the cross-product-absorption-catalog.
-- ============================================================================

CREATE TABLE IF NOT EXISTS dev_team.dev_team_agent_config_overrides (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id        UUID NOT NULL DEFAULT public.current_org_id(),
    config_name   TEXT NOT NULL,        -- e.g. "default"
    agent_name    TEXT NOT NULL,        -- one of the 11 canonical role names
    model         TEXT,                 -- override; NULL means inherit YAML
    provider      TEXT,                 -- override; NULL means inherit YAML
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT dev_team_overrides_uniq
        UNIQUE (org_id, config_name, agent_name)
);

CREATE INDEX IF NOT EXISTS idx_dev_team_overrides_org_config
    ON dev_team.dev_team_agent_config_overrides (org_id, config_name);

ALTER TABLE dev_team.dev_team_agent_config_overrides ENABLE ROW LEVEL SECURITY;

CREATE POLICY "agent_config_overrides_own_org"
    ON dev_team.dev_team_agent_config_overrides
    FOR ALL TO authenticated
    USING (org_id = ((SELECT auth.jwt()) ->> 'org_id')::uuid)
    WITH CHECK (org_id = ((SELECT auth.jwt()) ->> 'org_id')::uuid);

COMMENT ON TABLE dev_team.dev_team_agent_config_overrides IS
    'Per-org overrides for the engine YAML configs. NULL field = inherit from YAML. Reserved for the multi-tenant override path; v1 PATCH /api/configs writes through to the engine YAML directly (matches CLI / MCP).';
