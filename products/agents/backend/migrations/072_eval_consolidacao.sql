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
    -- optimistic-concurrency token: parallel runs of one version finish together; a state write is compare-and-swap on it
    versao INT NOT NULL DEFAULT 1 CHECK (versao >= 1),
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

-- 8 · consolidated coverage in the DB publish gate ----------------------------------------------------------------
-- A skipped case is COVERED only while it is `consolidado` with its streak at the threshold, BOTH as recorded when the run
-- skipped it and NOW. `revalidar` / `em_validacao` / a critical case below its 10 are never covered; the state is re-read at
-- publish so a regression after the run revokes the coverage.
CREATE OR REPLACE FUNCTION agents.eval_run_cobre_casos(
    p_org_id UUID, p_agent_id UUID, p_run_id UUID, p_run_tipo TEXT, p_suite TEXT
) RETURNS BOOLEAN
LANGUAGE sql STABLE
SET search_path = agents, public
AS $$
    SELECT NOT EXISTS (
        SELECT 1 FROM agents.eval_cases c
        WHERE c.org_id = p_org_id AND c.agent_id = p_agent_id AND c.ativo AND c.suite = p_suite
          AND NOT (
              (p_run_tipo = 'comportamento'
               AND EXISTS (SELECT 1 FROM agents.eval_results r WHERE r.run_id = p_run_id AND r.case_id = c.id))
              OR (p_run_tipo = 'mecanismo'
                  AND EXISTS (SELECT 1 FROM agents.eval_mecanismo_execucoes x WHERE x.run_id = p_run_id AND x.case_id = c.id))
              OR EXISTS (
                  SELECT 1 FROM agents.eval_casos_pulados p
                  JOIN agents.eval_case_estado s ON s.case_id = p.case_id
                  WHERE p.run_id = p_run_id AND p.run_tipo = p_run_tipo AND p.case_id = c.id
                    AND p.estado = 'consolidado' AND p.sequencia >= p.limite
                    AND s.estado = 'consolidado' AND s.sequencia >= s.limite
              )
          )
    );
$$;
REVOKE ALL ON FUNCTION agents.eval_run_cobre_casos(UUID, UUID, UUID, TEXT, TEXT) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION agents.eval_run_cobre_casos(UUID, UUID, UUID, TEXT, TEXT) TO service_role;

-- publish_agent_version = 038's body + consolidated coverage (judge run and mechanism run).
CREATE OR REPLACE FUNCTION agents.publish_agent_version(
    p_org_id UUID,
    p_version_id UUID,
    p_published_by UUID,
    p_eval_run_id UUID,
    p_override_reason TEXT,
    p_expected_hash TEXT,
    p_texto TEXT,
    p_manifest JSONB
) RETURNS VOID
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = agents, public
AS $$
DECLARE
    v_row agents.agent_versions;
    v_prev agents.agent_versions;
    v_limiar NUMERIC(4,3);
    v_score NUMERIC(4,3);
    v_reason TEXT := NULLIF(btrim(p_override_reason, E' \t\r\n'), '');
    v_mec agents.eval_mecanismo_runs;
    v_mec_cases INT;
    v_mec_exige BOOLEAN;
BEGIN
    SELECT * INTO v_row FROM agents.agent_versions
    WHERE id = p_version_id AND org_id = p_org_id
    FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'version_not_found' USING ERRCODE = 'P0001';
    END IF;
    IF v_row.status <> 'rascunho' THEN
        RAISE EXCEPTION 'version_immutable' USING ERRCODE = 'P0001';
    END IF;
    IF p_expected_hash IS NULL OR v_row.compiled_hash IS DISTINCT FROM p_expected_hash THEN
        RAISE EXCEPTION 'draft_changed' USING ERRCODE = 'P0001';
    END IF;

    -- Julia v2 A-EVAL: the mechanism suite is a hard gate with no override, enforced here so a direct
    -- DB publish cannot bypass the router. Required when the agent says so or has an active mecanismo
    -- case; satisfied only by the newest LIVE-driver run of THIS version for THIS hash that finished,
    -- was complete, stayed under budget and passed every case (an empty required suite is never green).
    SELECT a.exige_mecanismo INTO v_mec_exige FROM agents.agents a
    WHERE a.id = v_row.agent_id AND a.org_id = p_org_id;
    SELECT count(*) INTO v_mec_cases FROM agents.eval_cases c
    WHERE c.org_id = p_org_id AND c.agent_id = v_row.agent_id AND c.ativo AND c.suite = 'mecanismo';
    IF COALESCE(v_mec_exige, false) OR v_mec_cases > 0 THEN
        SELECT * INTO v_mec FROM agents.eval_mecanismo_runs r
        WHERE r.org_id = p_org_id AND r.version_id = p_version_id AND r.driver = 'live' AND r.status = 'concluida'
        ORDER BY r.finished_at DESC NULLS LAST, r.created_at DESC
        LIMIT 1;
        IF NOT FOUND
           OR v_mec.compiled_hash IS DISTINCT FROM p_expected_hash
           OR NOT v_mec.aprovado OR NOT v_mec.completa OR v_mec.orcamento_excedido
           OR (v_mec.total_casos < v_mec_cases
               AND NOT agents.eval_run_cobre_casos(p_org_id, v_row.agent_id, v_mec.id, 'mecanismo', 'mecanismo'))
           OR (EXISTS (SELECT 1 FROM agents.eval_casos_pulados p WHERE p.run_id = v_mec.id AND p.run_tipo = 'mecanismo')
               AND NOT agents.eval_run_cobre_casos(p_org_id, v_row.agent_id, v_mec.id, 'mecanismo', 'mecanismo'))
           OR v_mec.casos_aprovados <> v_mec.total_casos THEN
            RAISE EXCEPTION 'mecanismo_required' USING ERRCODE = 'P0001';
        END IF;
    END IF;

    -- FOR SHARE: a concurrent threshold change waits for this publish, so
    -- the snapshot is the threshold the gate was actually held to.
    SELECT publicacao_limiar INTO v_limiar FROM agents.agents
    WHERE id = v_row.agent_id AND org_id = p_org_id
    FOR SHARE;

    IF p_eval_run_id IS NOT NULL THEN
        SELECT r.score INTO v_score FROM agents.eval_runs r
        WHERE r.id = p_eval_run_id
          AND r.org_id = p_org_id
          AND r.version_id = p_version_id
          AND r.status = 'concluida'
          AND r.completa
          AND r.total >= 1
          AND r.compiled_hash = p_expected_hash
          AND r.score IS NOT NULL
          AND r.score >= v_limiar;
        IF NOT FOUND THEN
            RAISE EXCEPTION 'eval_required' USING ERRCODE = 'P0001';
        END IF;
        -- Consolidated coverage (owner decision 2026-11-09): a run that skipped consolidated cases only counts when EVERY
        -- active case is executed in it or still validly consolidated (state re-read NOW, threshold met).
        IF EXISTS (SELECT 1 FROM agents.eval_casos_pulados p WHERE p.run_id = p_eval_run_id AND p.run_tipo = 'comportamento')
           AND NOT agents.eval_run_cobre_casos(p_org_id, v_row.agent_id, p_eval_run_id, 'comportamento', 'comportamento') THEN
            RAISE EXCEPTION 'eval_required' USING ERRCODE = 'P0001';
        END IF;
        PERFORM 1 FROM agents.eval_cases c
        WHERE c.org_id = p_org_id AND c.agent_id = v_row.agent_id AND c.ativo;
        IF NOT FOUND THEN
            RAISE EXCEPTION 'eval_required' USING ERRCODE = 'P0001';
        END IF;
        v_reason := NULL;
    ELSIF v_reason IS NULL OR length(regexp_replace(v_reason, '\s', '', 'g')) < 20 THEN
        RAISE EXCEPTION 'eval_required' USING ERRCODE = 'P0001';
    END IF;

    IF p_texto IS NULL OR p_manifest IS NULL THEN
        RAISE EXCEPTION 'invalid_payload' USING ERRCODE = 'P0001';
    END IF;
    INSERT INTO agents.compiled_prompts (org_id, hash, version_id, client_id, texto, manifest)
    VALUES (p_org_id, p_expected_hash, p_version_id, NULL, p_texto, p_manifest)
    ON CONFLICT (org_id, hash) DO NOTHING;

    SELECT * INTO v_prev FROM agents.agent_versions
    WHERE org_id = p_org_id AND agent_id = v_row.agent_id AND status = 'ativa'
    FOR UPDATE;

    UPDATE agents.agent_versions
    SET status = 'substituida'
    WHERE org_id = p_org_id AND agent_id = v_row.agent_id AND status = 'ativa';

    UPDATE agents.agent_versions
    SET status = 'ativa',
        published_by = p_published_by,
        published_at = now(),
        eval_run_id = p_eval_run_id,
        publish_override_reason = v_reason,
        limiar_aplicado = v_limiar,
        eval_score = v_score
    WHERE id = p_version_id AND org_id = p_org_id;

    INSERT INTO agents.agent_audit_log (org_id, agent_id, actor, acao, antes, depois)
    VALUES (
        p_org_id, v_row.agent_id, p_published_by,
        CASE WHEN p_eval_run_id IS NULL THEN 'publicado_override' ELSE 'publicado' END,
        CASE WHEN v_prev.id IS NULL THEN NULL
             ELSE jsonb_build_object('version_id', v_prev.id, 'versao', v_prev.versao) END,
        jsonb_build_object(
            'version_id', v_row.id, 'versao', v_row.versao, 'compiled_hash', v_row.compiled_hash,
            'eval_run_id', p_eval_run_id, 'eval_score', v_score, 'limiar_aplicado', v_limiar,
            'override_reason', v_reason
        )
    );
END;
$$;

REVOKE ALL ON FUNCTION agents.publish_agent_version(UUID, UUID, UUID, UUID, TEXT, TEXT, TEXT, JSONB) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION agents.publish_agent_version(UUID, UUID, UUID, UUID, TEXT, TEXT, TEXT, JSONB) TO service_role;
