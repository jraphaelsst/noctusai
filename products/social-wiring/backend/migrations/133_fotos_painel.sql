-- 133_fotos_painel.sql -- social_wiring: dashboard aggregation RPC (W9)
--
-- Contract §8 `GET /painel`: "pipeline throughput · queue & health ·
-- activity · learning loop · costs. Scope follows `capacidades.dashboard`."
-- One JSONB payload, one round-trip -- the SAME SQL-aggregation move as
-- `027_leads_analytics_rpc.sql` (the aggregation happens in Postgres, not
-- via N paged PostgREST reads collapsed in Python).
--
-- SECURITY INVOKER, not DEFINER -- same rationale as
-- `027_leads_analytics_rpc.sql`: the ONLY caller is the backend's
-- service-role admin client (`app/modules/edicao_fotos/deps.py::
-- get_painel_client`), which already bypasses RLS via each table's
-- `service_role_bypass` policy. INVOKER means EXECUTE granted to
-- `authenticated` by mistake still can't cross an org boundary -- the
-- underlying SELECTs stay subject to each table's own RLS policy
-- (`fotos_lote_visivel`, `fotos_avaliacoes_select_admins`, etc). Defense
-- in depth: EXECUTE is ALSO explicitly restricted to `service_role`
-- below, same as every other analytics RPC in this product.
--
-- p_org_id NULL = platform-wide (every org); non-null = one org's rows.
-- The route layer (`routers/painel.py`) enforces WHO may pass NULL
-- (platform admin only -- contract §1 "Platform dashboard" row); this
-- function trusts its caller completely, same trust boundary every RPC
-- in this product uses.
--
-- Queue & health (`jobs`) is ALWAYS platform-wide (`fila.escopo =
-- 'plataforma'`), REGARDLESS of p_org_id -- `social_wiring.jobs` carries
-- no `org_id` column (it's the product's ONE shared queue, not a
-- fotos-only table), so there is no honest way to scope it per org.
-- Filtering `type LIKE 'fotos.%'` narrows it to this pipeline's own job
-- types (plan §6) without fabricating an org boundary the table doesn't
-- have.
--
-- Revenue is billing-sourced (Core `billing_payments` etc., project plan
-- Wave 2 §C3/§C4) -- NOT shipped as of this migration (verified: no
-- `subscriptions`/`billing_payments`/`plan_prices` table anywhere under
-- `products/core/backend/migrations/`, latest is `046_permissions_fx_
-- cost_ledger.sql`). `custos.receita.disponivel` is therefore always
-- `false`, `total_brl` always `0`, with an explicit `nota` -- CLAUDE.md
-- §1 "no silent errors" / dispatch brief: "show zero ... with a note
-- rather than inventing". `margem_brl` follows honestly from that
-- explicit zero (`0 - custo_total_brl`), never a guessed number.
--
-- Cost rows are scoped to this pipeline via `cost_ledger.step LIKE
-- 'fotos.%'` -- `public.cost_ledger` (Core 046) is a platform-wide sink;
-- other products/features can also write rows there.
--
-- PREREQUISITE: 121_jobs.sql, 123_fotos_core.sql, 125_fotos_aprendizado.sql,
-- Core 046_permissions_fx_cost_ledger.sql (`public.cost_ledger`).
-- Forward-only + idempotent (CREATE OR REPLACE FUNCTION).
--
-- 🔴 MIGRATION FILE ONLY -- not applied to any database by this change.
-- Applying needs owner consent (`projects/edicao-fotos/PROJECT.md`
-- "Owner-consent gates").

SET search_path = social_wiring, public;

CREATE OR REPLACE FUNCTION social_wiring.fotos_painel(
    p_org_id UUID DEFAULT NULL,
    p_desde  DATE DEFAULT NULL,
    p_ate    DATE DEFAULT NULL
) RETURNS jsonb
LANGUAGE plpgsql STABLE SECURITY INVOKER
SET search_path = social_wiring, public
AS $$
DECLARE
    -- Half-open interval [v_desde, v_ate) -- default window: the last 30
    -- days up to and including today.
    v_desde     TIMESTAMPTZ := COALESCE(p_desde, CURRENT_DATE - INTERVAL '30 days')::timestamptz;
    v_ate       TIMESTAMPTZ := COALESCE(p_ate, CURRENT_DATE)::timestamptz + INTERVAL '1 day';
    -- Zero-filled domains -- every status map below is EXHAUSTIVE (every
    -- known value present, defaulting to 0), not sparse. A sparse map
    -- (only present-count keys) would make the FE contract ambiguous --
    -- "key absent" vs "count is 0" become indistinguishable without a
    -- default-fill on every consumer. `category` (`custos.por_categoria`)
    -- is the one exception -- `cost_ledger.category` has no CHECK
    -- constraint (Core 046: "'openai_edit' | 'openai_vision' | ... "),
    -- so it stays a sparse list of whatever categories actually occurred.
    c_job_status  CONSTANT TEXT[] := ARRAY['pending', 'running', 'completed', 'failed', 'dead_letter'];
    c_foto_status CONSTANT TEXT[] := ARRAY[
        'recebida', 'normalizando', 'pronta', 'editando', 'em_lote_openai',
        'editada', 'avaliando', 'aguardando_decisao', 'aprovada', 'rejeitada', 'falhou'
    ];
    c_decisao     CONSTANT TEXT[] := ARRAY['aprovar', 'rejeitar'];
    v_pipeline    jsonb;
    v_fila        jsonb;
    v_atividade   jsonb;
    v_aprendizado jsonb;
    v_custos      jsonb;
BEGIN
    -- 1. pipeline throughput -- photos per state over time (fotos_eventos
    --    is the append-only state-transition log, contract §3). Every row
    --    with `estado_para IS NOT NULL` is a real state change written by
    --    `transition_photo` -- NOT just `tipo = 'transicao_estado'` rows:
    --    the review decision path (`dataset.record_decision`) transitions
    --    a photo to `aprovada`/`rejeitada` with `event_tipo='decisao'`,
    --    and a retry/failure path uses `'retry_manual'`/`'falha'` -- all
    --    four populate `estado_de`/`estado_para` identically
    --    (`repository.py::transition_photo`), so filtering on the LABEL
    --    would silently drop the funnel's own terminal states. Rows with
    --    no photo state change (e.g. `tipo='lote_submetido'`,
    --    `foto_id`/`estado_para` both NULL) are excluded by construction. --
    SELECT COALESCE(jsonb_agg(jsonb_build_object(
               'data', dia, 'estado', estado_para, 'total', total
           ) ORDER BY dia, estado_para), '[]'::jsonb)
      INTO v_pipeline
      FROM (
          SELECT date_trunc('day', e.created_at)::date AS dia,
                 e.estado_para,
                 COUNT(*) AS total
            FROM social_wiring.fotos_eventos e
           WHERE e.estado_para IS NOT NULL
             AND e.created_at >= v_desde AND e.created_at < v_ate
             AND (p_org_id IS NULL OR e.org_id = p_org_id)
           GROUP BY 1, 2
      ) t;

    -- 2. queue & health (platform-wide -- see header) --------------------
    SELECT jsonb_build_object(
               'escopo', 'plataforma',
               'jobs', (
                   SELECT jsonb_object_agg(s, COALESCE(c.total, 0))
                     FROM unnest(c_job_status) AS s
                     LEFT JOIN (
                         SELECT status, COUNT(*) AS total
                           FROM social_wiring.jobs
                          WHERE type LIKE 'fotos.%'
                          GROUP BY status
                     ) c ON c.status = s
               ),
               'travados', (
                   SELECT COUNT(*) FROM social_wiring.jobs
                    WHERE type LIKE 'fotos.%' AND status = 'running'
                      AND lease_expires_at IS NOT NULL AND lease_expires_at < now()
               ),
               'fotos_por_estado', (
                   SELECT jsonb_object_agg(s, COALESCE(c.total, 0))
                     FROM unnest(c_foto_status) AS s
                     LEFT JOIN (
                         SELECT status, COUNT(*) AS total
                           FROM social_wiring.fotos_fotos
                          WHERE created_at >= v_desde AND created_at < v_ate
                            AND (p_org_id IS NULL OR org_id = p_org_id)
                          GROUP BY status
                     ) c ON c.status = s
               )
           )
      INTO v_fila;

    -- 3. activity ---------------------------------------------------------
    SELECT jsonb_build_object(
               'lotes_criados', (
                   SELECT COUNT(*) FROM social_wiring.fotos_lotes l
                    WHERE l.created_at >= v_desde AND l.created_at < v_ate
                      AND (p_org_id IS NULL OR l.org_id = p_org_id)
               ),
               'fotos_enviadas', (
                   SELECT COUNT(*) FROM social_wiring.fotos_fotos f
                    WHERE f.created_at >= v_desde AND f.created_at < v_ate
                      AND (p_org_id IS NULL OR f.org_id = p_org_id)
               ),
               'decisoes', (
                   SELECT jsonb_object_agg(s, COALESCE(c.total, 0))
                     FROM unnest(c_decisao) AS s
                     LEFT JOIN (
                         SELECT d.decisao, COUNT(*) AS total
                           FROM social_wiring.fotos_decisoes d
                          WHERE d.created_at >= v_desde AND d.created_at < v_ate
                            AND (p_org_id IS NULL OR d.org_id = p_org_id)
                          GROUP BY d.decisao
                     ) c ON c.decisao = s
               ),
               'usuarios_ativos', (
                   SELECT COUNT(DISTINCT d.decidido_por) FROM social_wiring.fotos_decisoes d
                    WHERE d.created_at >= v_desde AND d.created_at < v_ate
                      AND (p_org_id IS NULL OR d.org_id = p_org_id)
               ),
               'serie_diaria', COALESCE((
                   SELECT jsonb_agg(jsonb_build_object(
                              'data', dia, 'lotes', lotes, 'fotos', fotos, 'decisoes', decisoes
                          ) ORDER BY dia)
                     FROM (
                         SELECT dia,
                                SUM(lotes) AS lotes, SUM(fotos) AS fotos, SUM(decisoes) AS decisoes
                           FROM (
                               SELECT date_trunc('day', l.created_at)::date AS dia,
                                      1 AS lotes, 0 AS fotos, 0 AS decisoes
                                 FROM social_wiring.fotos_lotes l
                                WHERE l.created_at >= v_desde AND l.created_at < v_ate
                                  AND (p_org_id IS NULL OR l.org_id = p_org_id)
                               UNION ALL
                               SELECT date_trunc('day', f.created_at)::date, 0, 1, 0
                                 FROM social_wiring.fotos_fotos f
                                WHERE f.created_at >= v_desde AND f.created_at < v_ate
                                  AND (p_org_id IS NULL OR f.org_id = p_org_id)
                               UNION ALL
                               SELECT date_trunc('day', d.created_at)::date, 0, 0, 1
                                 FROM social_wiring.fotos_decisoes d
                                WHERE d.created_at >= v_desde AND d.created_at < v_ate
                                  AND (p_org_id IS NULL OR d.org_id = p_org_id)
                           ) u
                          GROUP BY dia
                     ) g
               ), '[]'::jsonb)
           )
      INTO v_atividade;

    -- 4. learning loop -- approval rate + AI verdicts + AI/human
    --    agreement (contract §1 "See AI verdict": this route is
    --    admin-tier only, so the verdict aggregate is safe to expose) --
    WITH ultima_decisao AS (
        SELECT DISTINCT ON (d.foto_id) d.foto_id, d.decisao
          FROM social_wiring.fotos_decisoes d
         WHERE d.created_at >= v_desde AND d.created_at < v_ate
           AND (p_org_id IS NULL OR d.org_id = p_org_id)
         ORDER BY d.foto_id, d.created_at DESC
    ),
    ultima_avaliacao AS (
        SELECT DISTINCT ON (a.foto_id) a.foto_id, a.recomendacao
          FROM social_wiring.fotos_avaliacoes a
         WHERE a.created_at >= v_desde AND a.created_at < v_ate
           AND (p_org_id IS NULL OR a.org_id = p_org_id)
         ORDER BY a.foto_id, a.created_at DESC
    )
    SELECT jsonb_build_object(
               'taxa_aprovacao', COALESCE(
                   (SELECT AVG(CASE WHEN decisao = 'aprovar' THEN 1.0 ELSE 0.0 END) FROM ultima_decisao), 0
               ),
               'veredito_ia', (
                   SELECT jsonb_object_agg(s, COALESCE(v.total, 0))
                     FROM unnest(c_decisao) AS s
                     LEFT JOIN (
                         SELECT recomendacao, COUNT(*) AS total FROM ultima_avaliacao GROUP BY recomendacao
                     ) v ON v.recomendacao = s
               ),
               'acerto_ia_pct', (
                   SELECT AVG(CASE WHEN ud.decisao = ua.recomendacao THEN 1.0 ELSE 0.0 END) * 100
                     FROM ultima_avaliacao ua
                     JOIN ultima_decisao ud ON ud.foto_id = ua.foto_id
               ),
               'regras', jsonb_build_object(
                   'aprovadas', (
                       SELECT COUNT(*) FROM social_wiring.fotos_regras_org r
                        WHERE r.status = 'aprovada' AND (p_org_id IS NULL OR r.org_id = p_org_id)
                   ),
                   'pendentes', (
                       SELECT COUNT(*) FROM social_wiring.fotos_regras_org r
                        WHERE r.status = 'proposta' AND (p_org_id IS NULL OR r.org_id = p_org_id)
                   )
               )
           )
      INTO v_aprendizado;

    -- 5. costs -- OpenAI edits + vision, Supabase storage, payment fees;
    --    revenue vs cost margin (billing absent -- see header) ----------
    WITH custos AS (
        SELECT c.category, c.amount_brl, c.fx_pending
          FROM public.cost_ledger c
         WHERE c.created_at >= v_desde AND c.created_at < v_ate
           AND (p_org_id IS NULL OR c.org_id = p_org_id)
           AND c.step LIKE 'fotos.%'
    )
    SELECT jsonb_build_object(
               'moeda_base', 'BRL',
               'por_categoria', COALESCE((
                   SELECT jsonb_agg(jsonb_build_object(
                              'categoria', category, 'total_brl', total_brl
                          ) ORDER BY category)
                     FROM (
                         SELECT category, ROUND(COALESCE(SUM(amount_brl), 0), 2) AS total_brl
                           FROM custos
                          GROUP BY category
                     ) g
               ), '[]'::jsonb),
               'total_brl', ROUND(COALESCE((SELECT SUM(amount_brl) FROM custos), 0), 2),
               'fx_pendentes', (SELECT COUNT(*) FROM custos WHERE fx_pending),
               'receita', jsonb_build_object(
                   'disponivel', false,
                   'total_brl', 0,
                   'nota', 'sem dados de faturamento'
               ),
               'margem_brl', 0 - ROUND(COALESCE((SELECT SUM(amount_brl) FROM custos), 0), 2)
           )
      INTO v_custos;

    RETURN jsonb_build_object(
        'periodo', jsonb_build_object(
            'desde', v_desde::date,
            'ate', (v_ate - INTERVAL '1 day')::date
        ),
        'escopo', CASE WHEN p_org_id IS NULL THEN 'plataforma' ELSE 'organizacao' END,
        'pipeline', jsonb_build_object('pontos', v_pipeline),
        'fila', v_fila,
        'atividade', v_atividade,
        'aprendizado', v_aprendizado,
        'custos', v_custos
    );
END;
$$;

REVOKE ALL ON FUNCTION social_wiring.fotos_painel(UUID, DATE, DATE) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION social_wiring.fotos_painel(UUID, DATE, DATE) TO service_role;

COMMENT ON FUNCTION social_wiring.fotos_painel(UUID, DATE, DATE) IS
    'Contract §8 GET /painel: pipeline/fila/atividade/aprendizado/custos, one JSONB payload. Called only via the service-role admin client (app/modules/edicao_fotos/deps.py::get_painel_client).';
