-- 076_eval_loops.sql -- the eval-loop gate (owner spec 2026-11-09, rules G1-G7).
--
-- A LOOP is a refinement session of ONE suite (comportamento | mecanismo) of ONE agent: it declares its planned rounds,
-- a target (100%), a floor (the agent's publicacao_limiar) and a budget. Each run started with a loop_id is a ROUND of
-- that loop. The gate stops the loop (and notifies the owner in-app) at 100% (G3), at 2 consecutive rounds without a score
-- improvement (G4), or when the loop budget is spent (G7); it flags every round that did not raise the score (G5) and refuses
-- a round on an unchanged content hash that the consolidation passes do not justify (G6, evaluated in the API).
--
-- Spend is NOT tracked twice: a round's cost is the run's own recorded custo_usd (eval_runs / eval_mecanismo_runs), copied
-- onto the round when it closes; the shared daily ceiling (public.ai_usage, seed spend_ceiling) keeps bounding token runs.
--
-- Tier: Platform IP (`agents.eval_*`): RLS on, service_role only, no grant to anon / authenticated; the API in front is
-- platform-admin / evals-token only. Forward-only + idempotent. 073 / 074 belong to queued branches.

SET search_path = agents, public;

-- 1 · the loop -----------------------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS agents.eval_loops (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL,
    agent_id UUID NOT NULL REFERENCES agents.agents(id) ON DELETE CASCADE,
    agente_chave TEXT NOT NULL,
    suite TEXT NOT NULL CHECK (suite IN ('comportamento', 'mecanismo')),
    rodadas_planejadas INT NOT NULL CHECK (rodadas_planejadas >= 1 AND rodadas_planejadas <= 100),
    alvo NUMERIC(5, 4) NOT NULL DEFAULT 1.0 CHECK (alvo > 0 AND alvo <= 1),
    piso NUMERIC(5, 4) NOT NULL CHECK (piso >= 0 AND piso <= 1),
    orcamento_usd NUMERIC(10, 2) NOT NULL CHECK (orcamento_usd > 0),
    gasto_usd NUMERIC(10, 4) NOT NULL DEFAULT 0 CHECK (gasto_usd >= 0),
    status TEXT NOT NULL DEFAULT 'ativo' CHECK (status IN ('ativo', 'parado', 'concluido')),
    motivo_parada TEXT NULL CHECK (motivo_parada IS NULL OR motivo_parada IN (
        'alvo_atingido', 'sem_melhora', 'orcamento_atingido', 'rodadas_esgotadas', 'parado_manualmente')),
    detalhe_parada JSONB NULL,
    started_by UUID NOT NULL,
    started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    stopped_at TIMESTAMPTZ NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    -- a loop that is no longer active says why and when; an active one carries neither
    CONSTRAINT eval_loops_parada_consistente CHECK (
        (status = 'ativo' AND motivo_parada IS NULL AND stopped_at IS NULL)
        OR (status <> 'ativo' AND motivo_parada IS NOT NULL AND stopped_at IS NOT NULL))
);
-- one ACTIVE loop per (agent, suite): two loops racing the same suite would each read the other's rounds as noise
CREATE UNIQUE INDEX IF NOT EXISTS uq_agents_eval_loops_ativo_por_suite
    ON agents.eval_loops (agent_id, suite) WHERE status = 'ativo';
CREATE INDEX IF NOT EXISTS idx_agents_eval_loops_agent ON agents.eval_loops (agent_id, started_at DESC);

-- 2 · the rounds ---------------------------------------------------------------------------------------------
-- One row per run started with a loop_id; opened when the run is booked (status 'executando'), closed when it ends. Series,
-- overcalls and checkpoints are derived from these rows. run_id has no FK (two run tables); loop_id is mirrored on the runs.
CREATE TABLE IF NOT EXISTS agents.eval_loop_rodadas (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL,
    loop_id UUID NOT NULL REFERENCES agents.eval_loops(id) ON DELETE CASCADE,
    seq INT NOT NULL CHECK (seq >= 1),
    run_id UUID NOT NULL,
    run_tipo TEXT NOT NULL CHECK (run_tipo IN ('comportamento', 'mecanismo')),
    compiled_hash TEXT NOT NULL,
    partes JSONB NULL,
    status TEXT NOT NULL DEFAULT 'executando' CHECK (status IN ('executando', 'concluida', 'falhou', 'cancelada')),
    score NUMERIC(6, 5) NULL CHECK (score IS NULL OR (score >= 0 AND score <= 1)),
    custo_usd NUMERIC(10, 4) NOT NULL DEFAULT 0 CHECK (custo_usd >= 0),
    falhas JSONB NOT NULL DEFAULT '[]'::jsonb CHECK (jsonb_typeof(falhas) = 'array'),
    melhorou BOOLEAN NULL,
    overcall BOOLEAN NOT NULL DEFAULT false,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at TIMESTAMPTZ NULL,
    UNIQUE (loop_id, seq),
    UNIQUE (run_id, run_tipo)
);
CREATE INDEX IF NOT EXISTS idx_agents_eval_loop_rodadas_loop ON agents.eval_loop_rodadas (loop_id, seq);

-- 3 · loop_id on the run tables (nullable: runs started without a loop are unchanged) ---------------------------
ALTER TABLE agents.eval_runs
    ADD COLUMN IF NOT EXISTS loop_id UUID NULL REFERENCES agents.eval_loops(id) ON DELETE SET NULL;
ALTER TABLE agents.eval_mecanismo_runs
    ADD COLUMN IF NOT EXISTS loop_id UUID NULL REFERENCES agents.eval_loops(id) ON DELETE SET NULL;
CREATE INDEX IF NOT EXISTS idx_agents_eval_runs_loop ON agents.eval_runs (loop_id) WHERE loop_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_agents_eval_mecanismo_runs_loop ON agents.eval_mecanismo_runs (loop_id) WHERE loop_id IS NOT NULL;

-- 4 · tier + lockdown (Platform IP: service role only) --------------------------------------------------------
COMMENT ON TABLE agents.eval_loops IS 'tier:platform';
COMMENT ON TABLE agents.eval_loop_rodadas IS 'tier:platform';

ALTER TABLE agents.eval_loops ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "service_role_bypass" ON agents.eval_loops;
CREATE POLICY "service_role_bypass" ON agents.eval_loops FOR ALL TO service_role USING (true) WITH CHECK (true);
REVOKE ALL ON agents.eval_loops FROM anon, authenticated;

ALTER TABLE agents.eval_loop_rodadas ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "service_role_bypass" ON agents.eval_loop_rodadas;
CREATE POLICY "service_role_bypass" ON agents.eval_loop_rodadas FOR ALL TO service_role USING (true) WITH CHECK (true);
REVOKE ALL ON agents.eval_loop_rodadas FROM anon, authenticated;

DROP TRIGGER IF EXISTS set_updated_at_eval_loops ON agents.eval_loops;
CREATE TRIGGER set_updated_at_eval_loops
    BEFORE UPDATE ON agents.eval_loops
    FOR EACH ROW EXECUTE FUNCTION agents.set_updated_at();
