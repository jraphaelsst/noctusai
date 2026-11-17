-- 088_eval_erro_e_loop_driver.sql -- the eval pipeline stops lying and the loop gets a driver (owner 2026-11-17).
--
-- 1. A run whose cases ERRORED is no longer `concluida`: `erro` (no case produced a verdict) | `parcial_com_erros` (some did),
--    carrying `erro_codigo` (the first error's code, e.g. qualificacao_indisponivel) next to the existing `erro` text. Errored
--    cases are excluded from the score denominator; a run with none measured has score NULL, never 0.
-- 2. A loop round can close as `erro` | `parcial_com_erros`; a loop can stop with motivo `erro` (+ detalhe_parada).
-- 3. A loop runs its rounds BY ITSELF (`modo` automatico) until a stop condition, or waits for the owner (`manual`).
--    `aviso` = why an automatic loop is idle (e.g. hash_inalterado: waiting for a draft edit), shown by the UI.
-- 4. Measurement by design: every lifecycle change of a loop / round / run is an append-only row in `eval_loop_eventos`.
-- Tier: Platform IP (service role only). Forward-only + idempotent: the previous image reads none of the new columns.

SET search_path = agents, public;

-- 1 . widen the status checks (found by definition, not by name) ------------------------------------------------------
DO $$
DECLARE c record;
BEGIN
    FOR c IN SELECT conrelid::regclass AS tbl, conname FROM pg_constraint
              WHERE contype = 'c'
                AND conrelid IN ('agents.eval_runs'::regclass, 'agents.eval_loop_rodadas'::regclass)
                AND pg_get_constraintdef(oid) LIKE '%''executando''%' AND pg_get_constraintdef(oid) LIKE '%status%'
    LOOP
        EXECUTE format('ALTER TABLE %s DROP CONSTRAINT %I', c.tbl, c.conname);
    END LOOP;
END $$;
ALTER TABLE agents.eval_runs DROP CONSTRAINT IF EXISTS eval_runs_status_check;
ALTER TABLE agents.eval_runs ADD CONSTRAINT eval_runs_status_check
    CHECK (status IN ('pendente', 'executando', 'concluida', 'falhou', 'cancelada', 'erro', 'parcial_com_erros'));
ALTER TABLE agents.eval_loop_rodadas DROP CONSTRAINT IF EXISTS eval_loop_rodadas_status_check;
ALTER TABLE agents.eval_loop_rodadas ADD CONSTRAINT eval_loop_rodadas_status_check
    CHECK (status IN ('executando', 'concluida', 'falhou', 'cancelada', 'erro', 'parcial_com_erros'));

ALTER TABLE agents.eval_runs ADD COLUMN IF NOT EXISTS erro_codigo TEXT NULL;
ALTER TABLE agents.eval_runs ADD COLUMN IF NOT EXISTS casos_com_erro INT NOT NULL DEFAULT 0 CHECK (casos_com_erro >= 0);
ALTER TABLE agents.eval_loop_rodadas ADD COLUMN IF NOT EXISTS erro_codigo TEXT NULL;
ALTER TABLE agents.eval_loop_rodadas ADD COLUMN IF NOT EXISTS erro_mensagem TEXT NULL;

-- 2 . the loop: stop reason `erro`, the driver mode and its idle notice ------------------------------------------------
DO $$
DECLARE c record;
BEGIN
    FOR c IN SELECT conname FROM pg_constraint
              WHERE contype = 'c' AND conrelid = 'agents.eval_loops'::regclass
                AND pg_get_constraintdef(oid) LIKE '%alvo_atingido%'
    LOOP
        EXECUTE format('ALTER TABLE agents.eval_loops DROP CONSTRAINT %I', c.conname);
    END LOOP;
END $$;
ALTER TABLE agents.eval_loops DROP CONSTRAINT IF EXISTS eval_loops_motivo_parada_check;
ALTER TABLE agents.eval_loops ADD CONSTRAINT eval_loops_motivo_parada_check CHECK (motivo_parada IS NULL OR motivo_parada IN (
    'alvo_atingido', 'sem_melhora', 'orcamento_atingido', 'rodadas_esgotadas', 'parado_manualmente', 'erro'));
ALTER TABLE agents.eval_loops ADD COLUMN IF NOT EXISTS modo TEXT NOT NULL DEFAULT 'manual'
    CHECK (modo IN ('automatico', 'manual'));
ALTER TABLE agents.eval_loops ADD COLUMN IF NOT EXISTS aviso JSONB NULL;

-- transition-log-ok: eval_loop_eventos one polymorphic lifecycle log for three entities (loop, round, run) written by the app driver, not a single state row + events pair
-- 3 . the lifecycle events (append-only) ------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS agents.eval_loop_eventos (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL,
    loop_id UUID NOT NULL REFERENCES agents.eval_loops(id) ON DELETE CASCADE,
    run_id UUID NULL,
    rodada_seq INT NULL,
    evento TEXT NOT NULL CHECK (evento IN (
        'loop_iniciado', 'rodada_aberta', 'rodada_fechada', 'rodada_com_erro', 'run_com_erro', 'preflight_recusado',
        'driver_aguardando', 'driver_retomado', 'loop_parado', 'modo_alterado')),
    detalhe JSONB NOT NULL DEFAULT '{}'::jsonb,
    ator UUID NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_agents_eval_loop_eventos_loop ON agents.eval_loop_eventos (loop_id, created_at);
COMMENT ON TABLE agents.eval_loop_eventos IS 'tier:platform';
ALTER TABLE agents.eval_loop_eventos ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "service_role_bypass" ON agents.eval_loop_eventos;
CREATE POLICY "service_role_bypass" ON agents.eval_loop_eventos FOR ALL TO service_role USING (true) WITH CHECK (true);
REVOKE ALL ON agents.eval_loop_eventos FROM anon, authenticated;

CREATE OR REPLACE FUNCTION agents.eval_loop_eventos_append_only() RETURNS trigger
LANGUAGE plpgsql SET search_path = agents, public
AS $$
BEGIN
    RAISE EXCEPTION 'eval_loop_eventos is append-only';
END;
$$;
REVOKE ALL ON FUNCTION agents.eval_loop_eventos_append_only() FROM PUBLIC, anon, authenticated;
DROP TRIGGER IF EXISTS eval_loop_eventos_no_update ON agents.eval_loop_eventos;
CREATE TRIGGER eval_loop_eventos_no_update BEFORE UPDATE OR DELETE ON agents.eval_loop_eventos
    FOR EACH ROW EXECUTE FUNCTION agents.eval_loop_eventos_append_only();
