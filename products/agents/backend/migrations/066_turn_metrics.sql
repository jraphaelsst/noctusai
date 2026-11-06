-- ============================================================================
-- 066: agents.turn_metrics -- ONE row per agent turn (inbound message -> reply): cost, speed, size.
--
-- Written ONCE at the end of the turn by the app (fire-and-forget safe: a failed write is logged with the exception and
-- never fails the turn). Cost/tokens are the SUM of the turn's already-priced central-ledger UsageEvents
-- (`noctusai_lib.integrations.llm.coletar_uso`, D25) -- never re-priced here, so this is a per-turn VIEW of the same
-- money `public.ai_usage` holds, not a second ledger. Surfaced ONLY in the agents app, platform admins only.
--
--   origem   'canal' (a real channel turn) | 'eval' (the mechanism / eval driver): the page filters or excludes evals.
--   status   'ok' | 'erro' (the turn raised; erro_classe = the exception class name, never its message).
--   tokens_entrada = prompt + cache_read + cache_write (the provider's uncached count is `tokens_entrada - cache_*`).
--   *_bytes  UTF-8 payload bytes the app measured, NOT on-disk Postgres size. media_bytes NULL = not measured (the
--            agents app does not persist media; it lives in the channel / social-wiring side).
--   thread_id / agent_id / version_id carry NO foreign key: an eval turn has an ephemeral thread, and a metrics row must
--            never block an agent / thread lifecycle delete.
--
-- SERVICE-ROLE ONLY (platform-admin control plane, same posture as agent_product_grants): RLS on, the single
-- service_role_bypass policy, no grant to authenticated / anon. The read is the `require_platform_admin` studio API.
-- ============================================================================

SET search_path = agents, public;

CREATE TABLE IF NOT EXISTS agents.turn_metrics (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    org_id              UUID NOT NULL,
    agent_id            UUID NOT NULL,
    agent_key           TEXT NOT NULL CHECK (length(agent_key) <= 64),
    version_id          UUID NULL,
    compiled_hash       TEXT NULL,
    thread_id           UUID NULL,
    inbound_message_id  UUID NULL,
    reply_message_id    UUID NULL,
    origem              TEXT NOT NULL DEFAULT 'canal' CHECK (origem IN ('canal', 'eval')),
    gatilho             TEXT NULL,
    status              TEXT NOT NULL CHECK (status IN ('ok', 'erro')),
    erro_classe         TEXT NULL CHECK (erro_classe IS NULL OR length(erro_classe) <= 120),
    turno_status        TEXT NULL,
    handoff             BOOLEAN NOT NULL DEFAULT false,
    tools               TEXT[] NOT NULL DEFAULT '{}',
    -- LLM (sum of the turn's priced UsageEvents)
    llm_calls           INTEGER NOT NULL DEFAULT 0 CHECK (llm_calls >= 0),
    tokens_entrada      INTEGER NOT NULL DEFAULT 0 CHECK (tokens_entrada >= 0),
    tokens_saida        INTEGER NOT NULL DEFAULT 0 CHECK (tokens_saida >= 0),
    tokens_cache_leitura  INTEGER NOT NULL DEFAULT 0 CHECK (tokens_cache_leitura >= 0),
    tokens_cache_escrita  INTEGER NOT NULL DEFAULT 0 CHECK (tokens_cache_escrita >= 0),
    custo_usd           NUMERIC(14, 6) NOT NULL DEFAULT 0 CHECK (custo_usd >= 0),
    modelos             TEXT[] NOT NULL DEFAULT '{}',
    price_versions      TEXT[] NOT NULL DEFAULT '{}',
    -- speed (ms)
    turno_ms            INTEGER NOT NULL DEFAULT 0 CHECK (turno_ms >= 0),
    llm_ms              INTEGER NOT NULL DEFAULT 0 CHECK (llm_ms >= 0),
    tool_ms             INTEGER NOT NULL DEFAULT 0 CHECK (tool_ms >= 0),
    tools_ms            JSONB NOT NULL DEFAULT '{}'::jsonb,
    intake_ms           INTEGER NULL CHECK (intake_ms IS NULL OR intake_ms >= 0),
    -- size (UTF-8 payload bytes)
    inbound_bytes       INTEGER NOT NULL DEFAULT 0 CHECK (inbound_bytes >= 0),
    reply_bytes         INTEGER NOT NULL DEFAULT 0 CHECK (reply_bytes >= 0),
    prompt_bytes        INTEGER NOT NULL DEFAULT 0 CHECK (prompt_bytes >= 0),
    db_bytes            INTEGER NOT NULL DEFAULT 0 CHECK (db_bytes >= 0),
    media_bytes         INTEGER NULL CHECK (media_bytes IS NULL OR media_bytes >= 0)
);

CREATE INDEX IF NOT EXISTS idx_turn_metrics_agent ON agents.turn_metrics (agent_key, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_turn_metrics_org ON agents.turn_metrics (org_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_turn_metrics_thread ON agents.turn_metrics (thread_id, created_at) WHERE thread_id IS NOT NULL;

ALTER TABLE agents.turn_metrics ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "service_role_bypass" ON agents.turn_metrics;
CREATE POLICY "service_role_bypass" ON agents.turn_metrics
    FOR ALL TO service_role USING (true) WITH CHECK (true);
REVOKE ALL ON agents.turn_metrics FROM anon, authenticated;
