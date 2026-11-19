-- ============================================================================
-- Migration 363 · social_wiring: CoreStudio criação pipeline, M-B -- cs_criacao_jobs, the measured step ledger
-- ============================================================================
-- WHY
-- ---
-- Spec: criacao-pipeline-contract.md section 2 (M-B) + script-to-media-production.md section 5. A post's media is
-- produced by a graph of steps (tts -> render_motion -> mux, layout -> render_slides, ...). ONE row per step per round
-- IS the measured ledger: wall time, cpu time, vendor / model, request id, vendor units (characters, audio seconds,
-- credits), cost in USD and BRL (+ fx status), render speed, measurements (LUFS, true peak, safe zone) and the result.
-- Unmeasured is NULL plus the field's name in `nao_medido` -- never an estimate, never a silent zero (a concluded step
-- must either carry cost_usd / cpu_s or declare it unmeasured).
--
--   * cs_criacao_jobs               -- one row per (post, rodada, passo). A re-run of a rejected step is a NEW rodada
--                                      (the old rows stay: time and cost already spent are facts). NO foreign key on
--                                      post_id/org_id: the ledger outlives its post (same as cs_post_eventos) and the
--                                      append-only guard would refuse an ON DELETE CASCADE anyway.
--   * cs_criacao_passo_registrar    -- the ONLY writer. SECURITY DEFINER; it validates the post belongs to the org,
--                                      row-locks the step, moves the status FORWARD only (pendente < em_andamento <
--                                      terminal; terminal rows are immutable; replaying the same status is a no-op),
--                                      stamps iniciado_em / terminado_em / duracao_s itself, and writes the step's
--                                      cs_post_eventos row (passo_iniciado / passo_concluido / passo_falhou, plus
--                                      cota_excedida when erro_codigo = 'cota') in the SAME transaction (EOA).
--   * guard trigger                 -- seed guc_carveout_guard_sql: INSERT/UPDATE only while the RPC's transaction-local
--                                      GUC is on, DELETE never. service_role holds SELECT only (defence in depth).
--
-- Records -> metrics (measurement-by-design): wall time and cost per format and step, render speed, rejection / failure
-- rate per step (status falhou by passo / erro_codigo), vendor credit burn per org per month (M-E's view), steps whose
-- cost went unmeasured (nao_medido).
--
-- ORDER: the RPC writes the event names that M-C (364, `cs_post_eventos` CHECK) admits -- apply 364 with or before the
-- first call. Backward compatible with the previous image: a NEW table + NEW functions, nothing existing touched.
-- Tier: org (reads go through the backend; the browser holds no grant). FORWARD-ONLY, IDEMPOTENT. Requires 342.
-- ============================================================================

SET search_path = social_wiring, public;

DO $guard$
BEGIN
  IF to_regclass('social_wiring.cs_post_eventos') IS NULL OR to_regclass('social_wiring.cs_posts') IS NULL THEN
    RAISE EXCEPTION 'Migration 363 requires cs_posts (241) and cs_post_eventos (342) -- apply them first';
  END IF;
END
$guard$;

-- ----------------------------------------------------------------------------
-- 1. the ledger
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS social_wiring.cs_criacao_jobs (
    id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id                UUID NOT NULL,
    post_id               UUID NOT NULL,
    rodada                INTEGER NOT NULL DEFAULT 1,
    passo                 TEXT NOT NULL,
    depende_de            UUID[] NOT NULL DEFAULT '{}'::uuid[],
    status                TEXT NOT NULL DEFAULT 'pendente',
    job_id                UUID,
    iniciado_em           TIMESTAMPTZ,
    terminado_em          TIMESTAMPTZ,
    duracao_s             NUMERIC(12, 3),
    cpu_s                 NUMERIC(12, 3),
    vendor                TEXT,
    modelo                TEXT,
    request_id            TEXT,
    unidades              JSONB NOT NULL DEFAULT '{}'::jsonb,
    custo_usd             NUMERIC(14, 6),
    custo_brl             NUMERIC(14, 6),
    fx_status             TEXT,
    velocidade_render_x   NUMERIC(10, 3),
    medicoes              JSONB NOT NULL DEFAULT '{}'::jsonb,
    resultado             JSONB NOT NULL DEFAULT '{}'::jsonb,
    erro_codigo           TEXT,
    nao_medido            TEXT[] NOT NULL DEFAULT '{}'::text[],
    created_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT cs_criacao_jobs_passo_uq UNIQUE (post_id, rodada, passo),
    CONSTRAINT cs_criacao_jobs_rodada_check CHECK (rodada >= 1),
    CONSTRAINT cs_criacao_jobs_passo_check CHECK (passo ~ '^[a-z][a-z0-9_]{0,39}$'),
    CONSTRAINT cs_criacao_jobs_status_check
        CHECK (status IN ('pendente', 'em_andamento', 'concluido', 'falhou', 'cancelado', 'pulado')),
    CONSTRAINT cs_criacao_jobs_depende_de_max CHECK (cardinality(depende_de) <= 10),
    -- terminal <=> terminado_em; a started step carries iniciado_em
    CONSTRAINT cs_criacao_jobs_terminado_check
        CHECK ((status IN ('concluido', 'falhou', 'cancelado', 'pulado')) = (terminado_em IS NOT NULL)),
    CONSTRAINT cs_criacao_jobs_iniciado_check
        CHECK (status <> 'em_andamento' OR iniciado_em IS NOT NULL),
    CONSTRAINT cs_criacao_jobs_erro_check
        CHECK ((status = 'falhou') = (erro_codigo IS NOT NULL)
               AND (erro_codigo IS NULL OR erro_codigo ~ '^[a-z0-9_]{1,60}$')),
    CONSTRAINT cs_criacao_jobs_custos_check
        CHECK ((custo_usd IS NULL OR custo_usd >= 0) AND (custo_brl IS NULL OR custo_brl >= 0)
               AND (cpu_s IS NULL OR cpu_s >= 0) AND (velocidade_render_x IS NULL OR velocidade_render_x >= 0)),
    CONSTRAINT cs_criacao_jobs_fx_check
        CHECK ((fx_status IS NULL OR fx_status IN ('ok', 'indisponivel', 'nao_aplicavel'))
               AND (custo_brl IS NULL OR fx_status = 'ok')),
    CONSTRAINT cs_criacao_jobs_json_check
        CHECK (jsonb_typeof(unidades) = 'object' AND jsonb_typeof(medicoes) = 'object'
               AND jsonb_typeof(resultado) = 'object'),
    -- unmeasured = NULL + named in nao_medido; a measured value is never also declared unmeasured
    CONSTRAINT cs_criacao_jobs_nao_medido_check
        CHECK (nao_medido <@ ARRAY['custo_usd', 'custo_brl', 'cpu_s', 'duracao_s', 'velocidade_render_x',
                                   'unidades', 'medicoes']::text[]
               AND (NOT 'custo_usd' = ANY (nao_medido) OR custo_usd IS NULL)
               AND (NOT 'cpu_s' = ANY (nao_medido) OR cpu_s IS NULL)),
    CONSTRAINT cs_criacao_jobs_concluido_medido_check
        CHECK (status <> 'concluido'
               OR ((custo_usd IS NOT NULL OR 'custo_usd' = ANY (nao_medido))
                   AND (cpu_s IS NOT NULL OR 'cpu_s' = ANY (nao_medido))))
);
CREATE INDEX IF NOT EXISTS cs_criacao_jobs_post_idx ON social_wiring.cs_criacao_jobs (org_id, post_id, rodada, created_at);
-- the quota / spend scan (M-E) and the per-step failure metrics
CREATE INDEX IF NOT EXISTS cs_criacao_jobs_org_tempo_idx ON social_wiring.cs_criacao_jobs (org_id, terminado_em)
    WHERE terminado_em IS NOT NULL;
CREATE INDEX IF NOT EXISTS cs_criacao_jobs_ativos_idx ON social_wiring.cs_criacao_jobs (org_id, status)
    WHERE status IN ('pendente', 'em_andamento');

-- ----------------------------------------------------------------------------
-- 2. guard: written only through cs_criacao_passo_registrar, never deleted
-- ----------------------------------------------------------------------------
-- guc-carveout-guard: rendered by noctusai_lib.domain.sql_templates.guc_carveout_guard_sql
CREATE OR REPLACE FUNCTION social_wiring.guard_cs_criacao_jobs_append_only()
RETURNS TRIGGER
LANGUAGE plpgsql SECURITY DEFINER SET search_path = social_wiring, public
AS $$
BEGIN
    IF TG_OP = 'INSERT' AND current_setting('social_wiring.cs_criacao_jobs_registrar', true) = 'on' THEN
        RETURN NEW;
    ELSIF TG_OP = 'UPDATE' AND current_setting('social_wiring.cs_criacao_jobs_registrar', true) = 'on' THEN
        RETURN NEW;
    END IF;
    RAISE EXCEPTION 'guard_cs_criacao_jobs_append_only: cs_criacao_jobs is written only through cs_criacao_passo_registrar' USING ERRCODE = 'P0001';
END;
$$;

REVOKE ALL ON FUNCTION social_wiring.guard_cs_criacao_jobs_append_only() FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION social_wiring.guard_cs_criacao_jobs_append_only() TO service_role;

DROP TRIGGER IF EXISTS guard_cs_criacao_jobs_append_only ON social_wiring.cs_criacao_jobs;
CREATE TRIGGER guard_cs_criacao_jobs_append_only
    BEFORE INSERT OR UPDATE OR DELETE ON social_wiring.cs_criacao_jobs
    FOR EACH ROW EXECUTE FUNCTION social_wiring.guard_cs_criacao_jobs_append_only();

-- ----------------------------------------------------------------------------
-- 3. the only status writer
-- ----------------------------------------------------------------------------
-- p_dados keys (all optional): depende_de (uuid[]), job_id, vendor, modelo, request_id, unidades (object), cpu_s,
-- custo_usd, custo_brl, fx_status, velocidade_render_x, medicoes (object), resultado (object), erro_codigo,
-- nao_medido (text[]). A key that is absent keeps the stored value.
CREATE OR REPLACE FUNCTION social_wiring.cs_criacao_passo_registrar(
    p_org UUID, p_post UUID, p_rodada INTEGER, p_passo TEXT, p_status TEXT, p_dados JSONB)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = social_wiring, pg_catalog, pg_temp
AS $fn$
DECLARE
    v_dados JSONB := COALESCE(p_dados, '{}'::jsonb);
    v_old social_wiring.cs_criacao_jobs%ROWTYPE;
    v_new social_wiring.cs_criacao_jobs%ROWTYPE;
    v_existe BOOLEAN;
    v_rank_old INTEGER;
    v_rank_new INTEGER;
    v_agora TIMESTAMPTZ := now();
    v_tipo TEXT;
    v_evento_dados JSONB;
BEGIN
    IF p_status IS NULL OR p_status NOT IN ('pendente', 'em_andamento', 'concluido', 'falhou', 'cancelado', 'pulado') THEN
        RAISE EXCEPTION 'status_invalido';
    END IF;
    IF p_rodada IS NULL OR p_rodada < 1 THEN
        RAISE EXCEPTION 'rodada_invalida';
    END IF;
    IF p_passo IS NULL OR p_passo !~ '^[a-z][a-z0-9_]{0,39}$' THEN
        RAISE EXCEPTION 'passo_invalido';
    END IF;
    IF jsonb_typeof(v_dados) <> 'object' THEN
        RAISE EXCEPTION 'dados_invalidos';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM social_wiring.cs_posts WHERE id = p_post AND org_id = p_org) THEN
        RAISE EXCEPTION 'post_nao_encontrado';
    END IF;

    -- serialise concurrent registrations of the same step (create race included)
    PERFORM pg_advisory_xact_lock(hashtextextended(p_post::text || ':' || p_rodada::text || ':' || p_passo, 0));
    SELECT * INTO v_old FROM social_wiring.cs_criacao_jobs
     WHERE post_id = p_post AND rodada = p_rodada AND passo = p_passo FOR UPDATE;
    v_existe := FOUND;

    IF v_existe THEN
        IF v_old.org_id <> p_org THEN
            RAISE EXCEPTION 'post_nao_encontrado';
        END IF;
        IF v_old.status = p_status THEN
            RETURN jsonb_build_object('id', v_old.id, 'status', v_old.status, 'mudou', false);
        END IF;
        v_rank_old := CASE v_old.status WHEN 'pendente' THEN 0 WHEN 'em_andamento' THEN 1 ELSE 2 END;
        v_rank_new := CASE p_status WHEN 'pendente' THEN 0 WHEN 'em_andamento' THEN 1 ELSE 2 END;
        IF v_rank_new <= v_rank_old THEN
            RAISE EXCEPTION 'transicao_invalida: % -> %', v_old.status, p_status;
        END IF;
    ELSE
        v_old.id := gen_random_uuid();
        v_old.org_id := p_org;
        v_old.post_id := p_post;
        v_old.rodada := p_rodada;
        v_old.passo := p_passo;
        v_old.depende_de := '{}'::uuid[];
        v_old.unidades := '{}'::jsonb;
        v_old.medicoes := '{}'::jsonb;
        v_old.resultado := '{}'::jsonb;
        v_old.nao_medido := '{}'::text[];
        v_old.created_at := v_agora;
    END IF;

    v_new := v_old;
    v_new.status := p_status;
    v_new.updated_at := v_agora;
    IF jsonb_typeof(v_dados -> 'depende_de') = 'array' THEN
        v_new.depende_de := ARRAY(SELECT jsonb_array_elements_text(v_dados -> 'depende_de')::uuid);
    END IF;
    v_new.job_id := COALESCE((v_dados ->> 'job_id')::uuid, v_old.job_id);
    v_new.vendor := COALESCE(v_dados ->> 'vendor', v_old.vendor);
    v_new.modelo := COALESCE(v_dados ->> 'modelo', v_old.modelo);
    v_new.request_id := COALESCE(v_dados ->> 'request_id', v_old.request_id);
    v_new.cpu_s := COALESCE((v_dados ->> 'cpu_s')::numeric, v_old.cpu_s);
    v_new.custo_usd := COALESCE((v_dados ->> 'custo_usd')::numeric, v_old.custo_usd);
    v_new.custo_brl := COALESCE((v_dados ->> 'custo_brl')::numeric, v_old.custo_brl);
    v_new.fx_status := COALESCE(v_dados ->> 'fx_status', v_old.fx_status);
    v_new.velocidade_render_x := COALESCE((v_dados ->> 'velocidade_render_x')::numeric, v_old.velocidade_render_x);
    IF jsonb_typeof(v_dados -> 'unidades') = 'object' THEN v_new.unidades := v_dados -> 'unidades'; END IF;
    IF jsonb_typeof(v_dados -> 'medicoes') = 'object' THEN v_new.medicoes := v_dados -> 'medicoes'; END IF;
    IF jsonb_typeof(v_dados -> 'resultado') = 'object' THEN v_new.resultado := v_dados -> 'resultado'; END IF;
    IF jsonb_typeof(v_dados -> 'nao_medido') = 'array' THEN
        v_new.nao_medido := ARRAY(SELECT jsonb_array_elements_text(v_dados -> 'nao_medido'));
    END IF;
    v_new.erro_codigo := CASE WHEN p_status = 'falhou' THEN COALESCE(v_dados ->> 'erro_codigo', v_old.erro_codigo) END;

    IF p_status = 'em_andamento' THEN
        v_new.iniciado_em := COALESCE(v_old.iniciado_em, v_agora);
    END IF;
    IF p_status IN ('concluido', 'falhou', 'cancelado', 'pulado') THEN
        v_new.terminado_em := v_agora;
        IF v_new.iniciado_em IS NOT NULL THEN
            v_new.duracao_s := round(extract(epoch FROM (v_agora - v_new.iniciado_em))::numeric, 3);
        END IF;
    END IF;

    IF p_status = 'falhou' AND v_new.erro_codigo IS NULL THEN
        RAISE EXCEPTION 'erro_obrigatorio';
    END IF;
    IF p_status = 'concluido' AND ((v_new.custo_usd IS NULL AND NOT 'custo_usd' = ANY (v_new.nao_medido))
                                   OR (v_new.cpu_s IS NULL AND NOT 'cpu_s' = ANY (v_new.nao_medido))) THEN
        RAISE EXCEPTION 'medicao_ausente';  -- measured or declared nao_medido, never an estimate
    END IF;

    PERFORM set_config('social_wiring.cs_criacao_jobs_registrar', 'on', true);
    IF v_existe THEN
        UPDATE social_wiring.cs_criacao_jobs SET
            depende_de = v_new.depende_de, status = v_new.status, job_id = v_new.job_id,
            iniciado_em = v_new.iniciado_em, terminado_em = v_new.terminado_em, duracao_s = v_new.duracao_s,
            cpu_s = v_new.cpu_s, vendor = v_new.vendor, modelo = v_new.modelo, request_id = v_new.request_id,
            unidades = v_new.unidades, custo_usd = v_new.custo_usd, custo_brl = v_new.custo_brl,
            fx_status = v_new.fx_status, velocidade_render_x = v_new.velocidade_render_x,
            medicoes = v_new.medicoes, resultado = v_new.resultado, erro_codigo = v_new.erro_codigo,
            nao_medido = v_new.nao_medido, updated_at = v_new.updated_at
         WHERE id = v_old.id;
    ELSE
        INSERT INTO social_wiring.cs_criacao_jobs (
            id, org_id, post_id, rodada, passo, depende_de, status, job_id, iniciado_em, terminado_em, duracao_s,
            cpu_s, vendor, modelo, request_id, unidades, custo_usd, custo_brl, fx_status, velocidade_render_x,
            medicoes, resultado, erro_codigo, nao_medido, created_at, updated_at)
        VALUES (
            v_old.id, p_org, p_post, p_rodada, p_passo, v_new.depende_de, v_new.status, v_new.job_id,
            v_new.iniciado_em, v_new.terminado_em, v_new.duracao_s, v_new.cpu_s, v_new.vendor, v_new.modelo,
            v_new.request_id, v_new.unidades, v_new.custo_usd, v_new.custo_brl, v_new.fx_status,
            v_new.velocidade_render_x, v_new.medicoes, v_new.resultado, v_new.erro_codigo, v_new.nao_medido,
            v_old.created_at, v_new.updated_at);
    END IF;
    PERFORM set_config('social_wiring.cs_criacao_jobs_registrar', 'off', true);

    -- the step's event, same transaction (cs_post_eventos is append-only; names admitted by 364)
    v_tipo := CASE p_status WHEN 'em_andamento' THEN 'passo_iniciado' WHEN 'concluido' THEN 'passo_concluido'
                            WHEN 'falhou' THEN 'passo_falhou' END;
    IF v_tipo IS NOT NULL THEN
        v_evento_dados := jsonb_build_object(
            'passo', p_passo, 'rodada', p_rodada, 'passo_id', v_old.id, 'job_id', v_new.job_id,
            'vendor', v_new.vendor, 'modelo', v_new.modelo, 'duracao_s', v_new.duracao_s,
            'custo_usd', v_new.custo_usd, 'erro_codigo', v_new.erro_codigo);
        INSERT INTO social_wiring.cs_post_eventos (org_id, post_id, tipo, de, para, dados, ator_id)
        VALUES (p_org, p_post, v_tipo, CASE WHEN v_existe THEN v_old.status END, p_status, v_evento_dados, NULL);
        IF p_status = 'falhou' AND v_new.erro_codigo = 'cota' THEN
            INSERT INTO social_wiring.cs_post_eventos (org_id, post_id, tipo, para, dados, ator_id)
            VALUES (p_org, p_post, 'cota_excedida', p_status, v_evento_dados, NULL);
        END IF;
    END IF;

    RETURN jsonb_build_object('id', v_old.id, 'status', p_status, 'mudou', true,
                              'duracao_s', v_new.duracao_s, 'criado', NOT v_existe);
END;
$fn$;

REVOKE ALL ON FUNCTION social_wiring.cs_criacao_passo_registrar(UUID, UUID, INTEGER, TEXT, TEXT, JSONB)
    FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION social_wiring.cs_criacao_passo_registrar(UUID, UUID, INTEGER, TEXT, TEXT, JSONB)
    TO service_role;

COMMENT ON FUNCTION social_wiring.cs_criacao_passo_registrar(UUID, UUID, INTEGER, TEXT, TEXT, JSONB) IS
    'The only writer of cs_criacao_jobs: forward-only status + its cs_post_eventos row, one transaction (criacao-pipeline-contract 2).';

-- ----------------------------------------------------------------------------
-- 4. RLS + grants (service-only), tier
-- ----------------------------------------------------------------------------
ALTER TABLE social_wiring.cs_criacao_jobs ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "cs_criacao_jobs_service_role" ON social_wiring.cs_criacao_jobs;
CREATE POLICY "cs_criacao_jobs_service_role" ON social_wiring.cs_criacao_jobs FOR ALL TO service_role USING (true) WITH CHECK (true);
REVOKE ALL ON TABLE social_wiring.cs_criacao_jobs FROM PUBLIC, anon, authenticated, service_role;
GRANT SELECT ON TABLE social_wiring.cs_criacao_jobs TO service_role;

COMMENT ON TABLE social_wiring.cs_criacao_jobs IS 'tier:org';
COMMENT ON COLUMN social_wiring.cs_criacao_jobs.nao_medido IS
    'Field names that could not be measured for this step (their column is NULL). Never an estimate. Migration 363.';
