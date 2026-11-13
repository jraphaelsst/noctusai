-- 087_eval_um_por_usuario.sql -- ONE eval run / eval loop per USER at a time (owner 2026-11-12): "1 run per user at a time. So if
-- marina is running a loop or an eval, cindy can still run her rounds/evals, but marina cant open a second one while a still
-- running eval is on."
--
-- Scope = the run's `started_by` (the human's user id; a platform `studio:evals-run` token is recorded by its token row id, so the
-- rule applies per token). Across ALL agents, BOTH suites (agents.eval_runs = behaviour judge, agents.eval_mecanismo_runs =
-- mechanism), single runs AND loop rounds.
--
-- WHY A TRIGGER (not a partial unique index): the two suites live in two tables, so no single unique index can say "one in-flight
-- row per user". A BEFORE INSERT trigger on each run table (and on eval_loops) takes a per-user transaction advisory lock, THEN
-- reads both tables: two simultaneous starts by one user serialize on the lock, the second sees the first's committed row and is
-- refused. It guards every writer (the create_eval_run RPC, the mechanism insert, any future path) -- the API pre-check only adds
-- the friendly message naming what is running; this is the backstop that makes double-booking impossible.
--   in flight = eval_runs.status IN ('pendente','executando')  |  eval_mecanismo_runs.status = 'executando'
--   execucao_em_andamento  the user already has a run in flight (any agent / suite)
--   loop_ativo_do_usuario  the user already has an ACTIVE loop (checked here when OPENING a loop; the API checks it for single
--                          runs and for rounds of another loop, since the run row does not carry its loop_id at insert time)
-- A run that ended (concluida/falhou/cancelada, incl. the startup orphan sweep and POST .../cancel) frees the slot by definition.
-- Each refusal is also recorded as an append-only event (agents.eval_recusas_eventos) by the API. Tier: platform. Forward-only,
-- idempotent; the triggers add no columns, so the previous image keeps working (it only sees the new refusals).

SET search_path = agents, public;

-- 1 . partial indexes: the lookups the trigger runs ------------------------------------------------------------------
CREATE INDEX IF NOT EXISTS idx_agents_eval_runs_usuario_em_voo
    ON agents.eval_runs (started_by) WHERE status IN ('pendente', 'executando');
CREATE INDEX IF NOT EXISTS idx_agents_eval_mecanismo_runs_usuario_em_voo
    ON agents.eval_mecanismo_runs (started_by) WHERE status = 'executando';
CREATE INDEX IF NOT EXISTS idx_agents_eval_loops_usuario_ativo
    ON agents.eval_loops (started_by) WHERE status = 'ativo';

-- 2 . the guard -------------------------------------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION agents.guard_eval_um_por_usuario() RETURNS trigger
LANGUAGE plpgsql SET search_path = agents, public
AS $$
BEGIN
    IF NEW.started_by IS NULL THEN
        RETURN NEW;
    END IF;
    -- serialize this user's starts for the rest of the transaction (released at commit/rollback)
    PERFORM pg_advisory_xact_lock(hashtextextended('agents.eval_um_por_usuario:' || NEW.started_by::text, 0));
    IF EXISTS (SELECT 1 FROM agents.eval_runs
                WHERE started_by = NEW.started_by AND status IN ('pendente', 'executando'))
       OR EXISTS (SELECT 1 FROM agents.eval_mecanismo_runs
                   WHERE started_by = NEW.started_by AND status = 'executando') THEN
        RAISE EXCEPTION 'execucao_em_andamento';
    END IF;
    IF TG_TABLE_NAME = 'eval_loops'
       AND EXISTS (SELECT 1 FROM agents.eval_loops WHERE started_by = NEW.started_by AND status = 'ativo') THEN
        RAISE EXCEPTION 'loop_ativo_do_usuario';
    END IF;
    RETURN NEW;
END;
$$;
REVOKE ALL ON FUNCTION agents.guard_eval_um_por_usuario() FROM PUBLIC, anon, authenticated;

DROP TRIGGER IF EXISTS guard_eval_um_por_usuario ON agents.eval_runs;
CREATE TRIGGER guard_eval_um_por_usuario BEFORE INSERT ON agents.eval_runs
    FOR EACH ROW EXECUTE FUNCTION agents.guard_eval_um_por_usuario();
DROP TRIGGER IF EXISTS guard_eval_um_por_usuario ON agents.eval_mecanismo_runs;
CREATE TRIGGER guard_eval_um_por_usuario BEFORE INSERT ON agents.eval_mecanismo_runs
    FOR EACH ROW EXECUTE FUNCTION agents.guard_eval_um_por_usuario();
DROP TRIGGER IF EXISTS guard_eval_um_por_usuario ON agents.eval_loops;
CREATE TRIGGER guard_eval_um_por_usuario BEFORE INSERT ON agents.eval_loops
    FOR EACH ROW EXECUTE FUNCTION agents.guard_eval_um_por_usuario();

-- 3 . the refusals, as events (append-only; written by the API, which has the context the trigger lacks) ---------------
CREATE TABLE IF NOT EXISTS agents.eval_recusas_eventos (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL,
    started_by UUID NOT NULL,
    codigo TEXT NOT NULL CHECK (codigo IN ('execucao_em_andamento', 'loop_ativo_do_usuario')),
    agent_id UUID NULL,                -- the agent the refused start targeted
    suite TEXT NULL CHECK (suite IS NULL OR suite IN ('comportamento', 'mecanismo')),
    loop_id UUID NULL,                 -- the loop the refused start targeted (a round), if any
    em_andamento_run_id UUID NULL,     -- what was blocking: the in-flight run ...
    em_andamento_run_tipo TEXT NULL CHECK (em_andamento_run_tipo IS NULL OR em_andamento_run_tipo IN ('comportamento', 'mecanismo')),
    em_andamento_loop_id UUID NULL,    -- ... or the user's open loop
    occurred_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_agents_eval_recusas_eventos_usuario ON agents.eval_recusas_eventos (started_by, occurred_at DESC);

CREATE OR REPLACE FUNCTION agents.guard_eval_recusas_eventos_append_only() RETURNS trigger
LANGUAGE plpgsql SET search_path = agents, public
AS $$ BEGIN RAISE EXCEPTION 'eval_recusas_eventos is append-only'; END; $$;
REVOKE ALL ON FUNCTION agents.guard_eval_recusas_eventos_append_only() FROM PUBLIC, anon, authenticated;

DROP TRIGGER IF EXISTS guard_eval_recusas_eventos_append_only ON agents.eval_recusas_eventos;
CREATE TRIGGER guard_eval_recusas_eventos_append_only
    BEFORE UPDATE OR DELETE ON agents.eval_recusas_eventos
    FOR EACH ROW EXECUTE FUNCTION agents.guard_eval_recusas_eventos_append_only();

COMMENT ON TABLE agents.eval_recusas_eventos IS 'tier:platform';
ALTER TABLE agents.eval_recusas_eventos ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "service_role_bypass" ON agents.eval_recusas_eventos;
CREATE POLICY "service_role_bypass" ON agents.eval_recusas_eventos FOR ALL TO service_role USING (true) WITH CHECK (true);
REVOKE ALL ON agents.eval_recusas_eventos FROM anon, authenticated;
