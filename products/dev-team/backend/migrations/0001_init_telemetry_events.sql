-- ============================================================================
-- 0001 — dev-team telemetry events
--
-- Postgres mirror of the engine's SQLite schema (dev_team/src/dev_team/
-- memory/store/telemetry.sqlite). The local SQLite stays for single-tenant
-- CLI / MCP usage; this Postgres table backs the multi-tenant product API.
--
-- Schema reference: projects/agno-dev-team-rollout/PROJECT.md §5.4
--
-- RLS pattern follows the canonical org_id-from-JWT shape used across the
-- platform (the original reference was the retired `mailing` product,
-- consolidated into `social-wiring` 2026-05-16). Each event is tagged
-- with the writer's org_id; reads
-- scoped by `org_id = (jwt -> 'org_id')::uuid`.
-- ============================================================================

CREATE SCHEMA IF NOT EXISTS dev_team;

GRANT USAGE ON SCHEMA dev_team TO anon, authenticated, service_role;
GRANT ALL ON ALL TABLES IN SCHEMA dev_team TO anon, authenticated, service_role;
GRANT ALL ON ALL SEQUENCES IN SCHEMA dev_team TO anon, authenticated, service_role;
ALTER DEFAULT PRIVILEGES IN SCHEMA dev_team
    GRANT ALL ON TABLES TO anon, authenticated, service_role;
ALTER DEFAULT PRIVILEGES IN SCHEMA dev_team
    GRANT ALL ON SEQUENCES TO anon, authenticated, service_role;


-- ============================================================================
-- 1. Standard platform table — page status (feature flags)
-- ============================================================================

CREATE TABLE IF NOT EXISTS dev_team.status_pagina (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    nome_pagina  TEXT NOT NULL UNIQUE,
    status       TEXT NOT NULL DEFAULT 'producao'
                   CHECK (status IN ('producao', 'desenvolvimento', 'desativado')),
    descricao    TEXT,
    created_at   TIMESTAMPTZ DEFAULT now()
);

ALTER TABLE dev_team.status_pagina ENABLE ROW LEVEL SECURITY;

CREATE POLICY "todos_veem_producao" ON dev_team.status_pagina
    FOR SELECT USING (status = 'producao');


-- ============================================================================
-- 2. Standard platform table — invitations
-- ============================================================================

CREATE TABLE IF NOT EXISTS dev_team.invitations (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id      UUID NOT NULL,
    email       TEXT NOT NULL,
    role        TEXT NOT NULL DEFAULT 'member',
    invited_by  UUID NOT NULL,
    token       TEXT UNIQUE NOT NULL,
    status      TEXT NOT NULL DEFAULT 'pending'
                  CHECK (status IN ('pending', 'accepted', 'expired', 'canceled')),
    expires_at  TIMESTAMPTZ NOT NULL DEFAULT (now() + interval '7 days'),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE dev_team.invitations ENABLE ROW LEVEL SECURITY;

CREATE POLICY "invitations_select_own_org" ON dev_team.invitations
    FOR SELECT TO authenticated
    USING (org_id = ((SELECT auth.jwt()) ->> 'org_id')::uuid);

CREATE INDEX IF NOT EXISTS idx_dev_team_invitations_org
    ON dev_team.invitations (org_id);
CREATE INDEX IF NOT EXISTS idx_dev_team_invitations_token
    ON dev_team.invitations (token);


-- ============================================================================
-- 3. Telemetry events — every agent turn captured for measurability
--
-- Mirrors `dev_team/src/dev_team/memory/store/telemetry.sqlite`'s `events`
-- table. The product writes one row per agno turn; reads serve the metrics
-- API (/api/metrics, /api/agents/{name}/metrics) and the future dashboard.
-- ============================================================================

CREATE TABLE IF NOT EXISTS dev_team.dev_team_telemetry_events (
    id              BIGSERIAL PRIMARY KEY,
    org_id          UUID NOT NULL DEFAULT public.current_org_id(),
    timestamp       TIMESTAMPTZ NOT NULL DEFAULT now(),
    project         TEXT,                 -- project slug, nullable
    config_name     TEXT NOT NULL,        -- which YAML config was active
    agent_name      TEXT NOT NULL,        -- e.g. "backend_engineer"
    sub_team        TEXT,                 -- "design_review_team" / null
    turn_index      INTEGER NOT NULL,     -- per-task turn counter
    input_tokens    INTEGER NOT NULL,
    output_tokens   INTEGER NOT NULL,
    total_cost_usd  NUMERIC(10, 6) NOT NULL,
    latency_ms      INTEGER NOT NULL,
    tool_calls      JSONB,                -- list of {name, args, latency_ms}
    outcome         TEXT NOT NULL CHECK (outcome IN ('ok', 'error', 'timeout')),
    output_chars    INTEGER NOT NULL,
    task_hash       TEXT                  -- sha1 of the task string for grouping
);

CREATE INDEX IF NOT EXISTS idx_dev_team_telemetry_org_agent
    ON dev_team.dev_team_telemetry_events (org_id, agent_name);
CREATE INDEX IF NOT EXISTS idx_dev_team_telemetry_org_project
    ON dev_team.dev_team_telemetry_events (org_id, project);
CREATE INDEX IF NOT EXISTS idx_dev_team_telemetry_timestamp
    ON dev_team.dev_team_telemetry_events (timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_dev_team_telemetry_task_hash
    ON dev_team.dev_team_telemetry_events (task_hash);

ALTER TABLE dev_team.dev_team_telemetry_events ENABLE ROW LEVEL SECURITY;

CREATE POLICY "telemetry_events_own_org" ON dev_team.dev_team_telemetry_events
    FOR ALL TO authenticated
    USING (org_id = ((SELECT auth.jwt()) ->> 'org_id')::uuid)
    WITH CHECK (org_id = ((SELECT auth.jwt()) ->> 'org_id')::uuid);

COMMENT ON TABLE dev_team.dev_team_telemetry_events IS
    'Per-tenant mirror of the engine SQLite events table. One row per agno turn. Read by /api/metrics + /api/agents/{name}/metrics; written by the product when /api/run dispatches the team.';
