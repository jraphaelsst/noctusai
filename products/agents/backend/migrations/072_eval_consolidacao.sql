-- 072_eval_consolidacao.sql -- eval-case consolidation: criticality, dependencies, per-(case, agent) state,
-- append-only transition history, per-part prompt hashes on runs, and the "skipped because consolidated" ledger.
--
-- OWNER RULE (2026-11-09): a case that passed N CONSECUTIVE times (5 normal / 10 critico) is `consolidado`
-- and is NOT re-run until a change AFFECTS it; an affected case is `revalidar` and returns to `consolidado`
-- after 3 (normal) / 6 (critico) consecutive passes; a failure while revalidating drops it back to
-- `em_validacao` (full threshold). The thresholds are ROWS (eval_consolidacao_config), never constants.
-- "Affected" = a compiled-spec PART the case depends on changed (eval_cases.depende_de vs the per-part hashes
-- stored on each run). A case with NO declared dependency is affected by ANY change (fail-safe).
--
-- Every table here is `agents.eval_*` (Platform IP tier, platform-admin API only): RLS on, service_role only,
-- no grant to anon / authenticated. Forward-only + idempotent.

SET search_path = agents, public;

-- 1 · eval_cases: criticality + declared dependencies ----------------------------------------------------
ALTER TABLE agents.eval_cases
    ADD COLUMN IF NOT EXISTS criticidade TEXT NOT NULL DEFAULT 'normal',
    ADD COLUMN IF NOT EXISTS criticidade_origem TEXT NOT NULL DEFAULT 'padrao',
    ADD COLUMN IF NOT EXISTS depende_de JSONB NULL,
    ADD COLUMN IF NOT EXISTS depende_de_origem TEXT NULL;

ALTER TABLE agents.eval_cases DROP CONSTRAINT IF EXISTS eval_cases_criticidade_check;
ALTER TABLE agents.eval_cases ADD CONSTRAINT eval_cases_criticidade_check
    CHECK (criticidade IN ('normal', 'critico'));
ALTER TABLE agents.eval_cases DROP CONSTRAINT IF EXISTS eval_cases_criticidade_origem_check;
ALTER TABLE agents.eval_cases ADD CONSTRAINT eval_cases_criticidade_origem_check
    CHECK (criticidade_origem IN ('padrao', 'sugerida', 'definida'));
-- NULL = "not declared" = affected by ANY change (fail-safe). A declared list is a JSON array of part refs
-- ('secao:<chave>', 'texto:<chave>', 'ferramenta:<nome>', 'skill:<nome>', ... a trailing '*' is a prefix wildcard).
ALTER TABLE agents.eval_cases DROP CONSTRAINT IF EXISTS eval_cases_depende_de_check;
ALTER TABLE agents.eval_cases ADD CONSTRAINT eval_cases_depende_de_check
    CHECK (depende_de IS NULL OR jsonb_typeof(depende_de) = 'array');
ALTER TABLE agents.eval_cases DROP CONSTRAINT IF EXISTS eval_cases_depende_de_origem_check;
ALTER TABLE agents.eval_cases ADD CONSTRAINT eval_cases_depende_de_origem_check
    CHECK (depende_de_origem IS NULL OR depende_de_origem IN ('declarada', 'inferida'));

-- Proposal (NOT a decision): the tags the owner named plus the obvious siblings mark a case `critico`.
-- origem='sugerida' keeps it reviewable; setting it through the API stamps 'definida'.
UPDATE agents.eval_cases
SET criticidade = 'critico', criticidade_origem = 'sugerida'
WHERE criticidade_origem = 'padrao'
  AND tags && ARRAY[
      'adversarial', 'seguranca', 'segurança', 'privacidade', 'travas', 'trava', 'firewall-clientes',
      'integridade', 'transferencia', 'transferência', 'lgpd', 'pii', 'vazamento', 'injecao', 'injeção'
  ]::text[];

-- 2 · thresholds as data ----------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS agents.eval_consolidacao_config (
    chave TEXT PRIMARY KEY CHECK (chave IN (
        'consolidar_normal', 'consolidar_critico', 'revalidar_normal', 'revalidar_critico')),
    valor INT NOT NULL CHECK (valor >= 1 AND valor <= 100),
    descricao TEXT NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
INSERT INTO agents.eval_consolidacao_config (chave, valor, descricao) VALUES
    ('consolidar_normal', 5, 'Acertos consecutivos para consolidar um caso normal (em_validacao -> consolidado).'),
    ('consolidar_critico', 10, 'Acertos consecutivos para consolidar um caso critico.'),
    ('revalidar_normal', 3, 'Acertos consecutivos para reconsolidar um caso normal afetado por mudanca (revalidar -> consolidado).'),
    ('revalidar_critico', 6, 'Acertos consecutivos para reconsolidar um caso critico afetado por mudanca.')
ON CONFLICT (chave) DO NOTHING;

-- 3 · current state per case ---------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS agents.eval_case_estado (
    case_id UUID PRIMARY KEY REFERENCES agents.eval_cases(id) ON DELETE CASCADE,
    org_id UUID NOT NULL,
    agent_id UUID NOT NULL,
    suite TEXT NOT NULL CHECK (suite IN ('mecanismo', 'comportamento')),
    estado TEXT NOT NULL DEFAULT 'em_validacao' CHECK (estado IN ('em_validacao', 'consolidado', 'revalidar')),
    sequencia INT NOT NULL DEFAULT 0 CHECK (sequencia >= 0),
    limite INT NOT NULL CHECK (limite >= 1),
    -- the per-part hashes of the last run that counted for this case (what "unchanged" is compared against)
    partes_referencia JSONB NULL,
    hash_referencia TEXT NULL,
    ultimo_run_id UUID NULL,
    ultimo_run_tipo TEXT NULL CHECK (ultimo_run_tipo IS NULL OR ultimo_run_tipo IN ('comportamento', 'mecanismo')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_agents_eval_case_estado_agent ON agents.eval_case_estado (agent_id, estado);

-- 4 · append-only transition history ------------------------------------------------------------------------
-- No FK to the case/run: a history row must never block a lifecycle delete (the agent delete removes cases; the
-- ON DELETE CASCADE on eval_case_estado / eval_casos_pulados is what clears the live tables).
CREATE TABLE IF NOT EXISTS agents.eval_case_transicoes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL,
    agent_id UUID NOT NULL,
    case_id UUID NOT NULL,
    suite TEXT NOT NULL CHECK (suite IN ('mecanismo', 'comportamento')),
    de_estado TEXT NOT NULL CHECK (de_estado IN ('em_validacao', 'consolidado', 'revalidar')),
    para_estado TEXT NOT NULL CHECK (para_estado IN ('em_validacao', 'consolidado', 'revalidar')),
    motivo TEXT NOT NULL CHECK (motivo IN (
        'acerto', 'falha', 'consolidado', 'afetado', 'afetado_reinicio', 'revalidacao_falhou',
        'reconsolidado', 'regressao', 'backfill')),
    run_id UUID NULL,
    run_tipo TEXT NULL CHECK (run_tipo IS NULL OR run_tipo IN ('comportamento', 'mecanismo')),
    criticidade TEXT NOT NULL CHECK (criticidade IN ('normal', 'critico')),
    sequencia_antes INT NOT NULL,
    sequencia_depois INT NOT NULL,
    limite INT NOT NULL,
    partes JSONB NULL,
    partes_afetadas JSONB NULL,
    compiled_hash TEXT NULL,
    origem TEXT NOT NULL DEFAULT 'run' CHECK (origem IN ('run', 'backfill', 'selecao')),
    detalhe TEXT NULL CHECK (detalhe IS NULL OR length(detalhe) <= 500),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_agents_eval_case_transicoes_case ON agents.eval_case_transicoes (case_id, created_at);
CREATE INDEX IF NOT EXISTS idx_agents_eval_case_transicoes_agent ON agents.eval_case_transicoes (agent_id, created_at);

CREATE OR REPLACE FUNCTION agents.eval_case_transicoes_sem_update() RETURNS trigger
LANGUAGE plpgsql SET search_path = agents, public AS $$
BEGIN
    RAISE EXCEPTION 'eval_case_transicoes is append-only' USING ERRCODE = 'P0001';
END;
$$;
DROP TRIGGER IF EXISTS eval_case_transicoes_sem_update ON agents.eval_case_transicoes;
CREATE TRIGGER eval_case_transicoes_sem_update
    BEFORE UPDATE ON agents.eval_case_transicoes
    FOR EACH ROW EXECUTE FUNCTION agents.eval_case_transicoes_sem_update();

-- 5 · cases a run SKIPPED (consolidated + unaffected) -----------------------------------------------------
CREATE TABLE IF NOT EXISTS agents.eval_casos_pulados (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL,
    agent_id UUID NOT NULL,
    run_id UUID NOT NULL,
    run_tipo TEXT NOT NULL CHECK (run_tipo IN ('comportamento', 'mecanismo')),
    case_id UUID NOT NULL REFERENCES agents.eval_cases(id) ON DELETE CASCADE,
    estado TEXT NOT NULL CHECK (estado IN ('em_validacao', 'consolidado', 'revalidar')),
    motivo TEXT NOT NULL CHECK (motivo IN ('consolidado_nao_afetado')),
    sequencia INT NOT NULL DEFAULT 0,
    limite INT NOT NULL DEFAULT 1,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (run_id, run_tipo, case_id)
);
CREATE INDEX IF NOT EXISTS idx_agents_eval_casos_pulados_run ON agents.eval_casos_pulados (run_id, run_tipo);

-- 6 · per-part hashes + "run everything" flag on the runs -----------------------------------------------------
ALTER TABLE agents.eval_runs
    ADD COLUMN IF NOT EXISTS partes JSONB NULL,
    ADD COLUMN IF NOT EXISTS rodar_tudo BOOLEAN NOT NULL DEFAULT false;
ALTER TABLE agents.eval_mecanismo_runs
    ADD COLUMN IF NOT EXISTS partes JSONB NULL,
    ADD COLUMN IF NOT EXISTS rodar_tudo BOOLEAN NOT NULL DEFAULT false;

-- 7 · lockdown (Platform IP: service role only) -------------------------------------------------------------
ALTER TABLE agents.eval_consolidacao_config ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "service_role_bypass" ON agents.eval_consolidacao_config;
CREATE POLICY "service_role_bypass" ON agents.eval_consolidacao_config FOR ALL TO service_role USING (true) WITH CHECK (true);
REVOKE ALL ON agents.eval_consolidacao_config FROM anon, authenticated;

ALTER TABLE agents.eval_case_estado ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "service_role_bypass" ON agents.eval_case_estado;
CREATE POLICY "service_role_bypass" ON agents.eval_case_estado FOR ALL TO service_role USING (true) WITH CHECK (true);
REVOKE ALL ON agents.eval_case_estado FROM anon, authenticated;

ALTER TABLE agents.eval_case_transicoes ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "service_role_bypass" ON agents.eval_case_transicoes;
CREATE POLICY "service_role_bypass" ON agents.eval_case_transicoes FOR ALL TO service_role USING (true) WITH CHECK (true);
REVOKE ALL ON agents.eval_case_transicoes FROM anon, authenticated;

ALTER TABLE agents.eval_casos_pulados ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "service_role_bypass" ON agents.eval_casos_pulados;
CREATE POLICY "service_role_bypass" ON agents.eval_casos_pulados FOR ALL TO service_role USING (true) WITH CHECK (true);
REVOKE ALL ON agents.eval_casos_pulados FROM anon, authenticated;

DROP TRIGGER IF EXISTS set_updated_at_eval_case_estado ON agents.eval_case_estado;
CREATE TRIGGER set_updated_at_eval_case_estado
    BEFORE UPDATE ON agents.eval_case_estado
    FOR EACH ROW EXECUTE FUNCTION agents.set_updated_at();
DROP TRIGGER IF EXISTS set_updated_at_eval_consolidacao_config ON agents.eval_consolidacao_config;
CREATE TRIGGER set_updated_at_eval_consolidacao_config
    BEFORE UPDATE ON agents.eval_consolidacao_config
    FOR EACH ROW EXECUTE FUNCTION agents.set_updated_at();
