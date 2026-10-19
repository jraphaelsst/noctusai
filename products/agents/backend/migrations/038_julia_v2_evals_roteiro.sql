-- ============================================================================
-- 038_julia_v2_evals_roteiro.sql -- multi-turn evals that gate Julia's publish
-- (Julia v2 A-EVAL; contract products/agents/projects/julia-v2/CONTRACT.md
-- sections 3.5 E4 and 10.3).
--
--  1. agents.eval_cases gains suite (mecanismo|comportamento), k (runs per case,
--     pass^k), roteiro (scripted multi-turn lead messages + fixture catalogue /
--     initial state) and asserts (deterministic, code-checked). A mecanismo case
--     carries no judge criteria, so the "at least one criterion" CHECK now applies
--     to comportamento cases only.
--  2. agents.eval_mecanismo_runs / eval_mecanismo_execucoes -- the per-run
--     outcomes pass^k is computed from. SEPARATE from eval_runs/eval_results so the
--     judge-run machinery (one in-flight run per version, completa, score) is
--     untouched. Only a run driven by the LIVE model (driver='live') can open the
--     publish gate; a FakeProvider run (CI) never does.
--  3. agents.agents gains exige_mecanismo (publish requires a green mecanismo run even
--     with zero cases yet -- an empty suite must not read as green) and
--     comportamento_bloqueia (the judge suite blocks publish only when set; advisory
--     otherwise).
--  4. agents.create_eval_run only resolves comportamento cases (the judge runner
--     must never be handed a scripted-assert case).
--  5. publish_agent_version enforces the mechanism requirement IN THE DATABASE (a direct DB publish
--     cannot bypass the router gate).
--  6. Eval content is platform IP (CONTRACT 0.4): service-role only, no grant or policy to browser roles.
--
-- Eval fixtures are synthetic (Meta WhatsApp Business terms 4.7: no training on
-- WhatsApp data); the Python importer refuses phone / CPF / email.
-- Idempotent. NOT applied to any database by this slice -- the tech-lead applies it.
-- ============================================================================

SET search_path = agents, public;

-- 1 · eval_cases -------------------------------------------------------------
ALTER TABLE agents.eval_cases
    ADD COLUMN IF NOT EXISTS suite TEXT NOT NULL DEFAULT 'comportamento',
    ADD COLUMN IF NOT EXISTS k INT NOT NULL DEFAULT 3,
    ADD COLUMN IF NOT EXISTS roteiro JSONB NULL,
    ADD COLUMN IF NOT EXISTS asserts JSONB NULL;

ALTER TABLE agents.eval_cases DROP CONSTRAINT IF EXISTS eval_cases_suite_check;
ALTER TABLE agents.eval_cases ADD CONSTRAINT eval_cases_suite_check
    CHECK (suite IN ('mecanismo', 'comportamento'));

ALTER TABLE agents.eval_cases DROP CONSTRAINT IF EXISTS eval_cases_k_check;
ALTER TABLE agents.eval_cases ADD CONSTRAINT eval_cases_k_check CHECK (k BETWEEN 1 AND 10);

-- Judge criteria are required for a comportamento case only.
ALTER TABLE agents.eval_cases DROP CONSTRAINT IF EXISTS eval_cases_criterios_check;
ALTER TABLE agents.eval_cases DROP CONSTRAINT IF EXISTS eval_cases_criterios_ou_mecanismo;
ALTER TABLE agents.eval_cases ADD CONSTRAINT eval_cases_criterios_ou_mecanismo CHECK (
    suite = 'mecanismo'
    OR coalesce(jsonb_array_length(criterios -> 'deve'), 0)
       + coalesce(jsonb_array_length(criterios -> 'nao_deve'), 0) >= 1
);

-- A mecanismo case is a script plus deterministic asserts, nothing else.
ALTER TABLE agents.eval_cases DROP CONSTRAINT IF EXISTS eval_cases_mecanismo_conteudo;
ALTER TABLE agents.eval_cases ADD CONSTRAINT eval_cases_mecanismo_conteudo CHECK (
    suite <> 'mecanismo'
    -- COALESCE: a NULL roteiro/asserts makes the inner expression NULL, which a CHECK would ACCEPT.
    OR COALESCE(
        jsonb_typeof(roteiro) = 'object'
        AND jsonb_typeof(roteiro -> 'turnos') = 'array'
        AND jsonb_array_length(roteiro -> 'turnos') >= 1
        AND jsonb_typeof(asserts) = 'object'
        AND asserts <> '{}'::jsonb,
        false
    )
);

-- IP: eval content is platform-admin-only, via the API. No role other than service_role is granted
-- anything on it (the agents DB lockdown, migration 036, revokes the browser roles on every agents table).

-- 3 · agents flags -----------------------------------------------------------
ALTER TABLE agents.agents
    ADD COLUMN IF NOT EXISTS exige_mecanismo BOOLEAN NOT NULL DEFAULT false,
    ADD COLUMN IF NOT EXISTS comportamento_bloqueia BOOLEAN NOT NULL DEFAULT false;

-- 2 · per-run outcomes -------------------------------------------------------
CREATE TABLE IF NOT EXISTS agents.eval_mecanismo_runs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL,
    agent_id UUID NOT NULL REFERENCES agents.agents(id),
    version_id UUID NOT NULL REFERENCES agents.agent_versions(id) ON DELETE CASCADE,
    compiled_hash TEXT NOT NULL,
    driver TEXT NOT NULL CHECK (driver IN ('live', 'fake')),
    status TEXT NOT NULL CHECK (status IN ('executando', 'concluida', 'falhou', 'cancelada')),
    total_casos INT NOT NULL DEFAULT 0,
    casos_aprovados INT NOT NULL DEFAULT 0,
    completa BOOLEAN NOT NULL DEFAULT false,
    aprovado BOOLEAN NOT NULL DEFAULT false,
    orcamento_excedido BOOLEAN NOT NULL DEFAULT false,
    limite_usd NUMERIC(10, 2) NULL,
    custo_usd NUMERIC(10, 4) NULL,
    started_by UUID NOT NULL,
    started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at TIMESTAMPTZ NULL,
    erro TEXT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    -- "approved" is only ever true for a finished, complete, under-budget run in which
    -- EVERY case passed pass^k.
    CONSTRAINT eval_mecanismo_runs_aprovado_consistente CHECK (
        NOT aprovado
        OR (status = 'concluida' AND completa AND NOT orcamento_excedido
            AND total_casos >= 1 AND casos_aprovados = total_casos)
    )
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_eval_mecanismo_runs_um_em_execucao
    ON agents.eval_mecanismo_runs (version_id) WHERE status = 'executando';
CREATE INDEX IF NOT EXISTS idx_agents_eval_mecanismo_runs_version
    ON agents.eval_mecanismo_runs (version_id, finished_at);

CREATE TABLE IF NOT EXISTS agents.eval_mecanismo_execucoes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL,
    run_id UUID NOT NULL REFERENCES agents.eval_mecanismo_runs(id) ON DELETE CASCADE,
    case_id UUID NOT NULL REFERENCES agents.eval_cases(id),
    indice INT NOT NULL CHECK (indice >= 1),
    status TEXT NOT NULL CHECK (status IN ('aprovado', 'reprovado', 'erro', 'pulado')),
    -- [{"assert": str, "codigo": str}] -- codes only, never reply text or prompt content.
    falhas JSONB NOT NULL DEFAULT '[]'::jsonb,
    ferramentas TEXT[] NOT NULL DEFAULT '{}'::text[],
    custo_usd NUMERIC(10, 4) NULL,
    duracao_ms INT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (run_id, case_id, indice)
);
CREATE INDEX IF NOT EXISTS idx_agents_eval_mecanismo_execucoes_run
    ON agents.eval_mecanismo_execucoes (run_id);

ALTER TABLE agents.eval_mecanismo_runs ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "service_role_bypass" ON agents.eval_mecanismo_runs;
CREATE POLICY "service_role_bypass" ON agents.eval_mecanismo_runs
    FOR ALL TO service_role USING (true) WITH CHECK (true);
REVOKE ALL ON agents.eval_mecanismo_runs FROM anon, authenticated;

ALTER TABLE agents.eval_mecanismo_execucoes ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "service_role_bypass" ON agents.eval_mecanismo_execucoes;
CREATE POLICY "service_role_bypass" ON agents.eval_mecanismo_execucoes
    FOR ALL TO service_role USING (true) WITH CHECK (true);
REVOKE ALL ON agents.eval_mecanismo_execucoes FROM anon, authenticated;

DROP TRIGGER IF EXISTS set_updated_at_eval_mecanismo_runs ON agents.eval_mecanismo_runs;
CREATE TRIGGER set_updated_at_eval_mecanismo_runs
    BEFORE UPDATE ON agents.eval_mecanismo_runs
    FOR EACH ROW EXECUTE FUNCTION agents.set_updated_at();

-- 4 · the judge run only resolves comportamento cases ------------------------
CREATE OR REPLACE FUNCTION agents.create_eval_run(
    p_org_id UUID,
    p_agent_id UUID,
    p_version_id UUID,
    p_compiled_hash TEXT,
    p_limiar NUMERIC,
    p_case_ids UUID[],
    p_started_by UUID,
    p_modelo_geracao TEXT DEFAULT NULL,
    p_limite_usd NUMERIC DEFAULT NULL
) RETURNS UUID
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = agents, public
AS $$
DECLARE
    v_cases UUID[];
    v_found INT;
    v_run_id UUID;
    v_completa BOOLEAN := p_case_ids IS NULL;
BEGIN
    PERFORM 1 FROM agents.agent_versions
    WHERE id = p_version_id AND org_id = p_org_id AND agent_id = p_agent_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'version_not_found' USING ERRCODE = 'P0001';
    END IF;

    IF v_completa THEN
        SELECT COALESCE(array_agg(c.id ORDER BY c.created_at, c.id), '{}') INTO v_cases
        FROM agents.eval_cases c
        WHERE c.org_id = p_org_id AND c.agent_id = p_agent_id AND c.ativo AND c.suite = 'comportamento';
    ELSE
        SELECT COALESCE(array_agg(DISTINCT x), '{}') INTO v_cases FROM unnest(p_case_ids) AS x;
        IF cardinality(v_cases) > 200 THEN
            RAISE EXCEPTION 'too_many_cases' USING ERRCODE = 'P0001';
        END IF;
        SELECT count(*) INTO v_found FROM agents.eval_cases c
        WHERE c.id = ANY(v_cases) AND c.org_id = p_org_id AND c.agent_id = p_agent_id
          AND c.suite = 'comportamento';
        IF v_found <> cardinality(v_cases) THEN
            RAISE EXCEPTION 'eval_case_not_found' USING ERRCODE = 'P0001';
        END IF;
    END IF;
    IF cardinality(v_cases) = 0 THEN
        RAISE EXCEPTION 'no_eval_cases' USING ERRCODE = 'P0001';
    END IF;

    INSERT INTO agents.eval_runs (
        org_id, agent_id, version_id, compiled_hash, status, total, aprovados,
        limiar, completa, started_by, started_at, modelo_geracao, limite_usd
    ) VALUES (
        p_org_id, p_agent_id, p_version_id, p_compiled_hash, 'pendente', cardinality(v_cases), 0,
        p_limiar, v_completa, p_started_by, now(), p_modelo_geracao, p_limite_usd
    )
    RETURNING id INTO v_run_id;

    INSERT INTO agents.eval_results (org_id, run_id, case_id, status)
    SELECT p_org_id, v_run_id, x, 'pendente' FROM unnest(v_cases) AS x;

    RETURN v_run_id;
END;
$$;

REVOKE ALL ON FUNCTION agents.create_eval_run(UUID, UUID, UUID, TEXT, NUMERIC, UUID[], UUID, TEXT, NUMERIC) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION agents.create_eval_run(UUID, UUID, UUID, TEXT, NUMERIC, UUID[], UUID, TEXT, NUMERIC) TO service_role;

-- 5 · the DB publish path enforces the mechanism gate (012 body + the block above) -------------
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
           OR v_mec.total_casos < v_mec_cases
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
