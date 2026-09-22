-- ============================================================================
-- 014_agent_studio_cost.sql — Agent Studio: cost visibility + cheap-iteration
-- controls (Agent Studio contract §L "Controle de custo").
--
-- WHY: on 2026-09-21 five eval runs (160 cases: an Opus-5 generator via the
-- Claude Agent SDK + a Sonnet-5 judge via `noctusai_lib`) cost ~$20 of
-- Anthropic credit while NOTHING in this product recorded what a turn or a
-- case cost. This migration adds the columns three call sites need to make
-- cost visible, bounded, and cheap to iterate on:
--
--   * `agents.eval_results` — per-case cost (generator + judge combined) and
--     the generator's token counts (from the Claude Agent SDK's
--     `ResultMessage.usage`).
--   * `agents.eval_runs` — the cheaper-iteration model override
--     (`modelo_geracao`), the run's budget cap (`limite_usd`) and its
--     accumulated cost (`custo_usd`).
--   * `agents.messages` — the same cost/token columns for a studio agent's
--     real chat turns (assistant messages), captured from the same SDK
--     `ResultMessage`.
--
-- `eval_results.status` gains `'pulado'` — the terminal status a case gets
-- when a run's `limite_usd` is reached before that case started (contract
-- §L "pulado ... nota 'limite de custo atingido'"); distinct from `'erro'`
-- (which means the turn or the judge actually failed).
--
-- `agents.create_eval_run` (013) gains two trailing, DEFAULT-NULL parameters
-- (`p_modelo_geracao`, `p_limite_usd`) so it stamps them on the run row in
-- the SAME one-transaction insert (L6) 013 already does. Postgres treats a
-- changed parameter list as a distinct function identity, so the old
-- 7-parameter overload is dropped first — leaving exactly one
-- `create_eval_run` function, never two overloads silently diverging.
--
-- IDEMPOTENCY: `ADD COLUMN IF NOT EXISTS` / `DROP CONSTRAINT IF EXISTS` +
-- `ADD CONSTRAINT` / `DROP FUNCTION IF EXISTS` + `CREATE OR REPLACE
-- FUNCTION` / `CREATE INDEX IF NOT EXISTS`, matching 009's documented
-- convention. NOT applied to any database by this slice — the tech-lead
-- applies it once, with user consent (shared prod DB).
-- ============================================================================

SET search_path = agents, public;

-- ────────────────────────────────────────────────────────────────────────
-- eval_results — per-case cost + generator token counts, and the new
-- 'pulado' terminal status (budget cap reached before the case started).
-- ────────────────────────────────────────────────────────────────────────

ALTER TABLE agents.eval_results
    ADD COLUMN IF NOT EXISTS custo_usd NUMERIC(10, 4) NULL,
    ADD COLUMN IF NOT EXISTS tokens_entrada INT NULL,
    ADD COLUMN IF NOT EXISTS tokens_saida INT NULL,
    ADD COLUMN IF NOT EXISTS tokens_cache_leitura INT NULL;

ALTER TABLE agents.eval_results
    DROP CONSTRAINT IF EXISTS eval_results_status_check;

ALTER TABLE agents.eval_results
    ADD CONSTRAINT eval_results_status_check
        CHECK (status IN ('pendente', 'aprovado', 'reprovado', 'erro', 'pulado'));


-- ────────────────────────────────────────────────────────────────────────
-- eval_runs — cheaper-iteration model override, per-run budget cap, and
-- the run's accumulated cost (generator + judge summed over every result).
-- ────────────────────────────────────────────────────────────────────────

ALTER TABLE agents.eval_runs
    ADD COLUMN IF NOT EXISTS modelo_geracao TEXT NULL,
    ADD COLUMN IF NOT EXISTS limite_usd NUMERIC(10, 2) NULL,
    ADD COLUMN IF NOT EXISTS custo_usd NUMERIC(10, 4) NULL;

ALTER TABLE agents.eval_runs
    DROP CONSTRAINT IF EXISTS eval_runs_modelo_geracao_check;

-- Contract §L: the cheap-iteration allowlist is intentionally NARROWER than
-- `agent_versions.model` (012's `claude-opus-5`/`claude-sonnet-5`) — it
-- exists to let an iteration run cost less than the version's own model,
-- never to let it cost more. `NULL` = "use the version's own model" (the
-- publish-gate-eligible shape).
ALTER TABLE agents.eval_runs
    ADD CONSTRAINT eval_runs_modelo_geracao_check
        CHECK (modelo_geracao IS NULL OR modelo_geracao IN ('claude-sonnet-5', 'claude-haiku-4-5'));

ALTER TABLE agents.eval_runs
    DROP CONSTRAINT IF EXISTS eval_runs_limite_usd_check;

ALTER TABLE agents.eval_runs
    ADD CONSTRAINT eval_runs_limite_usd_check
        CHECK (limite_usd IS NULL OR (limite_usd > 0 AND limite_usd <= 50));


-- ────────────────────────────────────────────────────────────────────────
-- messages — the same cost/token columns for a studio agent's real chat
-- turns (assistant messages only; the columns stay NULL for `user`/`system`
-- rows and for every Julia message, contract §E.1's existing shape).
-- ────────────────────────────────────────────────────────────────────────

ALTER TABLE agents.messages
    ADD COLUMN IF NOT EXISTS custo_usd NUMERIC(10, 4) NULL,
    ADD COLUMN IF NOT EXISTS tokens_entrada INT NULL,
    ADD COLUMN IF NOT EXISTS tokens_saida INT NULL;


-- ────────────────────────────────────────────────────────────────────────
-- agents.create_eval_run — 013's one-transaction run+results insert (L6),
-- now also stamping `modelo_geracao` / `limite_usd` on the run row. Same
-- body otherwise; see 013 for the case-resolution + `completa` logic this
-- mirrors verbatim.
-- ────────────────────────────────────────────────────────────────────────

DROP FUNCTION IF EXISTS agents.create_eval_run(UUID, UUID, UUID, TEXT, NUMERIC, UUID[], UUID);

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
        WHERE c.org_id = p_org_id AND c.agent_id = p_agent_id AND c.ativo;
    ELSE
        SELECT COALESCE(array_agg(DISTINCT x), '{}') INTO v_cases FROM unnest(p_case_ids) AS x;
        IF cardinality(v_cases) > 200 THEN
            RAISE EXCEPTION 'too_many_cases' USING ERRCODE = 'P0001';
        END IF;
        SELECT count(*) INTO v_found FROM agents.eval_cases c
        WHERE c.id = ANY(v_cases) AND c.org_id = p_org_id AND c.agent_id = p_agent_id;
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


-- ────────────────────────────────────────────────────────────────────────
-- agents.publicacao_limiar / the publish gate (app/routers/
-- studio_agents_router.py) already reads `eval_runs.completa` +
-- `eval_runs.compiled_hash` off the row `SupabaseEvalGate` selects; the
-- gate additionally now filters `modelo_geracao IS NULL` at the query
-- (contract §L "a run with modelo_geracao set can never satisfy the
-- publish gate") — no schema change needed for that half, it is a WHERE
-- clause in `app/stores/studio_evals.py::SupabaseEvalGate`.
-- ────────────────────────────────────────────────────────────────────────
