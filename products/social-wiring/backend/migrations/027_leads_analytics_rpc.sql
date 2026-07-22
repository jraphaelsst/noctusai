-- 027_leads_analytics_rpc.sql — move Leads analytics aggregation from
-- Python (fetch-every-row, count/group in the app) into Postgres.
--
-- THE PROBLEM THIS FIXES
-- ───────────────────────
-- `app/modules/leads/services/query.py::fetch_filtered` pages through
-- PostgREST's 1000-row cap and returns EVERY matching row; every
-- analytics endpoint (summary/timeseries/by-dimension/heatmap) and
-- `facets` called it, then counted/grouped in Python. With 12,177 real
-- leads (org_id 6dd73140-74a4-41c6-aeff-bc94b5312b53) that is ~13 HTTP
-- round-trips PER endpoint. A single Leads page load fires summary +
-- timeseries + by-dimension×2 + heatmap + facets concurrently → 50-100
-- PostgREST requests per page view, and real transient 500s were
-- observed on /api/leads/sources and /api/leads/corretores under that
-- burst (PostgREST returned a non-JSON body under load ->
-- json.decoder.JSONDecodeError -> 500).
--
-- WHAT THIS ADDS
-- ───────────────
-- Six functions, all read-only, all STABLE:
--   `_leads_matching`             — shared filtered-rows primitive (private)
--   `leads_analytics_summary`     — §5.3 LeadsSummary
--   `leads_analytics_timeseries`  — §5.3 TimeseriesOut
--   `leads_analytics_by_dimension`— §5.3 ByDimensionOut
--   `leads_analytics_heatmap`     — §5.3 HeatmapOut
--   `leads_facets`                — §5.3 (facets endpoint's inline shape)
-- Each response shape is IDENTICAL to what the Python implementation in
-- `app/modules/leads/services/analytics_service.py` (kept there, renamed
-- `_reference_*`, as the equivalence oracle) already produced — this is
-- an internal optimization, §5.3 does not change. Every function takes
-- the exact §5.1 canonical filter set, marshalled from Python via
-- `query.py::to_rpc_params` — ONE shared parameter contract for all six.
--
-- SECURITY INVOKER, not DEFINER — and why
-- ─────────────────────────────────────────
-- These functions are called ONLY by the backend's admin (service-role)
-- client (`app/modules/leads/deps.py::get_leads_client`), which already
-- bypasses RLS via the `..._service_role` "FOR ALL ... USING (true)"
-- policies on every `leads`/`lead_sources`/`lead_corretores` table AND
-- via `service_role`'s BYPASSRLS role attribute — so for THIS caller,
-- DEFINER vs INVOKER makes no difference; there's no reason to elevate
-- to the function owner's privileges when the invoking role already has
-- full access. What INVOKER buys, that DEFINER would silently throw
-- away: every function takes `p_org_id` as an EXPLICIT parameter (never
-- `public.current_org_id()`) because the caller isn't a per-request
-- authenticated session — so if EXECUTE were ever mistakenly granted to
-- `authenticated` (misconfiguration, not the intended path), an INVOKER
-- function still runs the underlying `SELECT ... FROM social_wiring.leads`
-- AS that calling role, and RLS's `leads_select_own_org` policy
-- (`org_id = public.current_org_id()`) still applies — so a caller could
-- only ever get rows for THEIR OWN org back, regardless of what `p_org_id`
-- they passed. A SECURITY DEFINER function would execute with the
-- function owner's privileges and bypass that RLS check entirely,
-- silently removing this second, independent safety net. Defense in
-- depth: EXECUTE is ALSO explicitly restricted to `service_role` below
-- (the primary control — these functions should never be reachable by
-- `authenticated`/`anon` in the first place); RLS is the secondary,
-- structural backstop that INVOKER preserves for free.
--
-- Every WHERE clause below is STATIC SQL (`(p_x IS NULL OR col = ANY(p_x))`)
-- — no dynamic SQL / string-building anywhere in this file, so there is
-- no injection surface to reason about.
--
-- PREREQUISITE: 025_leads.sql (the tables), 011_rls_current_org_id.sql.
-- Forward-only + idempotent (CREATE OR REPLACE FUNCTION).
--
-- 🔴 MIGRATION FILE ONLY — not applied to any DB by this change. Apply
-- via noctus.dev.migrate_product with explicit tech-lead consent. This
-- file has NOT been executed against a real Postgres (no such
-- environment is available to this engineer — see the PR's return note
-- for what WAS verified: manual line-by-line cross-check against the
-- retained `_reference_*` Python implementation, plus structural test
-- coverage of the RPC parameter contract). Recommend a dry apply +
-- spot-check against real data before treating this as fully verified.
--
-- KEEP fetch_filtered / apply_db_filters / LeadFilters / the pager —
-- untouched by this migration. The list endpoint's default sort still
-- pushes count+page to SQL directly (not via these functions — see
-- `leads_service.py`'s module docstring); its origem/corretor-sort
-- fallback and the importer still call `fetch_filtered` exactly as
-- before.

SET search_path = social_wiring, public;

-- ── shared filtered-rows primitive (private — not part of the API) ─────
-- Plain SQL (not plpgsql): Postgres can inline a single-SELECT SQL
-- function into the caller's query plan, so calling this 2-5x inside one
-- analytics function (current window + previous window, plus per-bucket
-- aggregation) still resolves to index scans on `leads`, not repeated
-- materializations of the whole table.
CREATE OR REPLACE FUNCTION social_wiring._leads_matching(
    p_org_id uuid,
    p_de date,
    p_ate date,
    p_ano int[],
    p_mes int[],
    p_origem_id uuid[],
    p_corretor_id uuid[],
    p_tipo text[],
    p_tier text[],
    p_empreendimento text[],
    p_regiao text[],
    p_needs_review boolean,
    p_q text
) RETURNS SETOF social_wiring.leads
LANGUAGE sql STABLE SECURITY INVOKER
SET search_path TO 'social_wiring', 'public'
AS $$
    SELECT l.*
    FROM social_wiring.leads l
    WHERE l.org_id = p_org_id
      AND (p_de IS NULL OR l.data_entrada >= p_de)
      AND (p_ate IS NULL OR l.data_entrada <= p_ate)
      AND (p_ano IS NULL OR l.ano = ANY(p_ano))
      AND (p_mes IS NULL OR l.mes = ANY(p_mes))
      AND (p_origem_id IS NULL OR l.origem_id = ANY(p_origem_id))
      AND (p_corretor_id IS NULL OR l.corretor_id = ANY(p_corretor_id))
      AND (p_tipo IS NULL OR l.tipo_lead = ANY(p_tipo))
      AND (p_tier IS NULL OR l.anuncio_tier = ANY(p_tier))
      AND (p_empreendimento IS NULL OR l.empreendimento = ANY(p_empreendimento))
      AND (p_regiao IS NULL OR l.regiao = ANY(p_regiao))
      AND (p_needs_review IS NULL OR l.needs_review = p_needs_review)
      AND (
            p_q IS NULL OR p_q = '' OR
            l.cliente_nome ILIKE '%' || p_q || '%' OR
            l.contato      ILIKE '%' || p_q || '%' OR
            l.codigo_raw   ILIKE '%' || p_q || '%' OR
            l.observacoes  ILIKE '%' || p_q || '%'
      );
$$;

REVOKE ALL ON FUNCTION social_wiring._leads_matching FROM PUBLIC;
GRANT EXECUTE ON FUNCTION social_wiring._leads_matching TO service_role;

-- ── leads_analytics_summary — §5.3 LeadsSummary ─────────────────────────
-- Mirrors `analytics_service._reference_summary` line for line: total /
-- novos / retornos / origens_ativas / corretores_ativos / empreendimentos
-- / needs_review are straight counts (COUNT DISTINCT already excludes
-- NULL, matching the Python set-comprehension's `if r.get(...)` guard);
-- media_diaria uses the (de,ate)-span when both are set, else the count
-- of DISTINCT data_entrada values in the current window (else 1);
-- top_origem/top_corretor pick the highest-count group and join the
-- dimension table for the label; comparativo is only computed when BOTH
-- de/ate are set, over the immediately-preceding window of equal length
-- (same non-date filters, shifted dates) — same formula as
-- `analytics_service._previous_window_rows`.
CREATE OR REPLACE FUNCTION social_wiring.leads_analytics_summary(
    p_org_id uuid,
    p_de date DEFAULT NULL,
    p_ate date DEFAULT NULL,
    p_ano int[] DEFAULT NULL,
    p_mes int[] DEFAULT NULL,
    p_origem_id uuid[] DEFAULT NULL,
    p_corretor_id uuid[] DEFAULT NULL,
    p_tipo text[] DEFAULT NULL,
    p_tier text[] DEFAULT NULL,
    p_empreendimento text[] DEFAULT NULL,
    p_regiao text[] DEFAULT NULL,
    p_needs_review boolean DEFAULT NULL,
    p_q text DEFAULT NULL
) RETURNS jsonb
LANGUAGE plpgsql STABLE SECURITY INVOKER
SET search_path TO 'social_wiring', 'public'
AS $$
DECLARE
    v_total integer;
    v_novos integer;
    v_retornos integer;
    v_origens_ativas integer;
    v_corretores_ativos integer;
    v_empreendimentos integer;
    v_needs_review integer;
    v_span_days integer;
    v_media_diaria numeric;
    v_top_origem jsonb;
    v_top_corretor jsonb;
    v_comparativo jsonb;
    v_total_anterior integer;
    v_prev_de date;
    v_prev_ate date;
BEGIN
    SELECT
        count(*),
        count(*) FILTER (WHERE tipo_lead = 'novo'),
        count(*) FILTER (WHERE tipo_lead = 'retorno'),
        count(DISTINCT origem_id),
        count(DISTINCT corretor_id),
        count(DISTINCT empreendimento),
        count(*) FILTER (WHERE needs_review)
    INTO v_total, v_novos, v_retornos, v_origens_ativas, v_corretores_ativos,
         v_empreendimentos, v_needs_review
    FROM social_wiring._leads_matching(
        p_org_id, p_de, p_ate, p_ano, p_mes, p_origem_id, p_corretor_id,
        p_tipo, p_tier, p_empreendimento, p_regiao, p_needs_review, p_q
    );

    IF p_de IS NOT NULL AND p_ate IS NOT NULL THEN
        v_span_days := (p_ate - p_de) + 1;
    ELSE
        SELECT count(DISTINCT data_entrada)
        INTO v_span_days
        FROM social_wiring._leads_matching(
            p_org_id, p_de, p_ate, p_ano, p_mes, p_origem_id, p_corretor_id,
            p_tipo, p_tier, p_empreendimento, p_regiao, p_needs_review, p_q
        );
        IF v_span_days IS NULL OR v_span_days = 0 THEN
            v_span_days := 1;
        END IF;
    END IF;
    v_media_diaria := round((v_total::numeric / v_span_days), 2);

    SELECT jsonb_build_object(
        'id', s.origem_id, 'label', src.label, 'total', s.cnt,
        'share_pct', CASE WHEN v_total > 0
            THEN round((s.cnt::numeric / v_total * 100), 1) ELSE 0 END
    )
    INTO v_top_origem
    FROM (
        SELECT origem_id, count(*) AS cnt
        FROM social_wiring._leads_matching(
            p_org_id, p_de, p_ate, p_ano, p_mes, p_origem_id, p_corretor_id,
            p_tipo, p_tier, p_empreendimento, p_regiao, p_needs_review, p_q
        )
        WHERE origem_id IS NOT NULL
        GROUP BY origem_id
        ORDER BY count(*) DESC
        LIMIT 1
    ) s
    JOIN social_wiring.lead_sources src ON src.id = s.origem_id;

    SELECT jsonb_build_object('id', c.corretor_id, 'nome', cor.nome, 'total', c.cnt)
    INTO v_top_corretor
    FROM (
        SELECT corretor_id, count(*) AS cnt
        FROM social_wiring._leads_matching(
            p_org_id, p_de, p_ate, p_ano, p_mes, p_origem_id, p_corretor_id,
            p_tipo, p_tier, p_empreendimento, p_regiao, p_needs_review, p_q
        )
        WHERE corretor_id IS NOT NULL
        GROUP BY corretor_id
        ORDER BY count(*) DESC
        LIMIT 1
    ) c
    JOIN social_wiring.lead_corretores cor ON cor.id = c.corretor_id;

    IF p_de IS NOT NULL AND p_ate IS NOT NULL THEN
        v_prev_ate := p_de - 1;
        v_prev_de := v_prev_ate - (v_span_days - 1);
        SELECT count(*) INTO v_total_anterior
        FROM social_wiring._leads_matching(
            p_org_id, v_prev_de, v_prev_ate, p_ano, p_mes, p_origem_id, p_corretor_id,
            p_tipo, p_tier, p_empreendimento, p_regiao, p_needs_review, p_q
        );
        v_comparativo := jsonb_build_object(
            'total_anterior', v_total_anterior,
            'variacao_pct', CASE WHEN v_total_anterior > 0
                THEN round(((v_total - v_total_anterior)::numeric / v_total_anterior * 100), 1)
                ELSE NULL END
        );
    ELSE
        v_comparativo := NULL;
    END IF;

    RETURN jsonb_build_object(
        'total', v_total,
        'novos', v_novos,
        'retornos', v_retornos,
        'origens_ativas', v_origens_ativas,
        'corretores_ativos', v_corretores_ativos,
        'empreendimentos', v_empreendimentos,
        'needs_review', v_needs_review,
        'periodo', jsonb_build_object('de', p_de, 'ate', p_ate),
        'comparativo', v_comparativo,
        'media_diaria', v_media_diaria,
        'top_origem', v_top_origem,
        'top_corretor', v_top_corretor
    );
END;
$$;

REVOKE ALL ON FUNCTION social_wiring.leads_analytics_summary FROM PUBLIC;
GRANT EXECUTE ON FUNCTION social_wiring.leads_analytics_summary TO service_role;

-- ── leads_analytics_timeseries — §5.3 TimeseriesOut ─────────────────────
-- Mirrors `analytics_service._reference_timeseries`: bucket = data_entrada
-- (dia) / "YYYY-MM" (mes, default) / "YYYY" (ano); label is the pt-BR
-- "Mmm/YY" for mes, "DD/MM" for dia, the bucket itself for ano (same as
-- `_label_for`). `p_split` ∈ origem|corretor|tipo|tier resolves a
-- per-row key/label/cor (NULL split key => row still counts toward the
-- bucket total, just not toward any series — same as
-- `_split_key_label_cor` returning None); `series_meta` order is the
-- FIXED canonical order for tipo/tier, (ordem,label) for origem, nome
-- for corretor — same as the Python `_TIPO_ORDER`/`_TIER_ORDER` /
-- sorted-refs branches. `series` key is OMITTED (not null) on each point
-- when no split is requested, matching the TS `series?` optional field.
CREATE OR REPLACE FUNCTION social_wiring.leads_analytics_timeseries(
    p_org_id uuid,
    p_de date DEFAULT NULL,
    p_ate date DEFAULT NULL,
    p_ano int[] DEFAULT NULL,
    p_mes int[] DEFAULT NULL,
    p_origem_id uuid[] DEFAULT NULL,
    p_corretor_id uuid[] DEFAULT NULL,
    p_tipo text[] DEFAULT NULL,
    p_tier text[] DEFAULT NULL,
    p_empreendimento text[] DEFAULT NULL,
    p_regiao text[] DEFAULT NULL,
    p_needs_review boolean DEFAULT NULL,
    p_q text DEFAULT NULL,
    p_grain text DEFAULT 'mes',
    p_split text DEFAULT NULL
) RETURNS jsonb
LANGUAGE plpgsql STABLE SECURITY INVOKER
SET search_path TO 'social_wiring', 'public'
AS $$
DECLARE
    v_grain text := CASE WHEN p_grain IN ('dia', 'mes', 'ano') THEN p_grain ELSE 'mes' END;
    v_points jsonb;
    v_series_meta jsonb;
BEGIN
    WITH base AS (
        SELECT
            l.tipo_lead, l.anuncio_tier, l.origem_id, l.corretor_id,
            CASE v_grain
                WHEN 'dia' THEN l.data_entrada::text
                WHEN 'ano' THEN lpad(l.ano::text, 4, '0')
                ELSE lpad(l.ano::text, 4, '0') || '-' || lpad(l.mes::text, 2, '0')
            END AS bucket
        FROM social_wiring._leads_matching(
            p_org_id, p_de, p_ate, p_ano, p_mes, p_origem_id, p_corretor_id,
            p_tipo, p_tier, p_empreendimento, p_regiao, p_needs_review, p_q
        ) l
    ),
    keyed AS (
        SELECT
            b.bucket,
            CASE p_split
                WHEN 'origem' THEN src.slug
                WHEN 'corretor' THEN b.corretor_id::text
                WHEN 'tipo' THEN b.tipo_lead
                WHEN 'tier' THEN b.anuncio_tier
                ELSE NULL
            END AS skey
        FROM base b
        LEFT JOIN social_wiring.lead_sources src
            ON p_split = 'origem' AND src.id = b.origem_id
    ),
    bucket_totals AS (
        SELECT bucket, count(*) AS total FROM keyed GROUP BY bucket
    ),
    bucket_series AS (
        SELECT bucket, jsonb_object_agg(skey, cnt) AS series
        FROM (
            SELECT bucket, skey, count(*) AS cnt
            FROM keyed
            WHERE p_split IS NOT NULL AND skey IS NOT NULL
            GROUP BY bucket, skey
        ) s
        GROUP BY bucket
    )
    SELECT jsonb_agg(
        (
            jsonb_build_object(
                'bucket', t.bucket,
                'label', CASE v_grain
                    WHEN 'dia' THEN to_char(t.bucket::date, 'DD/MM')
                    WHEN 'ano' THEN t.bucket
                    ELSE
                        (ARRAY['Jan','Fev','Mar','Abr','Mai','Jun','Jul','Ago','Set','Out','Nov','Dez'])
                            [split_part(t.bucket, '-', 2)::int]
                        || '/' || right(split_part(t.bucket, '-', 1), 2)
                END,
                'total', t.total
            )
            || CASE WHEN p_split IS NOT NULL
                    THEN jsonb_build_object('series', COALESCE(bs.series, '{}'::jsonb))
                    ELSE '{}'::jsonb
               END
        ) ORDER BY t.bucket
    )
    INTO v_points
    FROM bucket_totals t
    LEFT JOIN bucket_series bs ON bs.bucket = t.bucket;

    IF p_split = 'tipo' THEN
        SELECT jsonb_agg(
            jsonb_build_object(
                'key', k,
                'label', CASE k WHEN 'novo' THEN 'Novo' WHEN 'retorno' THEN 'Retorno' ELSE 'Desconhecido' END,
                'cor', NULL
            ) ORDER BY ord
        )
        INTO v_series_meta
        FROM (VALUES ('novo', 1), ('retorno', 2), ('desconhecido', 3)) AS canon(k, ord)
        WHERE k IN (
            SELECT DISTINCT tipo_lead FROM social_wiring._leads_matching(
                p_org_id, p_de, p_ate, p_ano, p_mes, p_origem_id, p_corretor_id,
                p_tipo, p_tier, p_empreendimento, p_regiao, p_needs_review, p_q
            )
        );
    ELSIF p_split = 'tier' THEN
        SELECT jsonb_agg(
            jsonb_build_object(
                'key', k,
                'label', CASE k WHEN 'simples' THEN 'Simples' WHEN 'destaque' THEN 'Destaque' WHEN 'super_destaque' THEN 'Super Destaque' END,
                'cor', NULL
            ) ORDER BY ord
        )
        INTO v_series_meta
        FROM (VALUES ('simples', 1), ('destaque', 2), ('super_destaque', 3)) AS canon(k, ord)
        WHERE k IN (
            SELECT DISTINCT anuncio_tier FROM social_wiring._leads_matching(
                p_org_id, p_de, p_ate, p_ano, p_mes, p_origem_id, p_corretor_id,
                p_tipo, p_tier, p_empreendimento, p_regiao, p_needs_review, p_q
            ) WHERE anuncio_tier IS NOT NULL
        );
    ELSIF p_split = 'origem' THEN
        SELECT jsonb_agg(
            jsonb_build_object('key', src.slug, 'label', src.label, 'cor', src.cor)
            ORDER BY src.ordem, src.label
        )
        INTO v_series_meta
        FROM social_wiring.lead_sources src
        WHERE src.org_id = p_org_id
          AND src.id IN (
              SELECT DISTINCT origem_id FROM social_wiring._leads_matching(
                  p_org_id, p_de, p_ate, p_ano, p_mes, p_origem_id, p_corretor_id,
                  p_tipo, p_tier, p_empreendimento, p_regiao, p_needs_review, p_q
              ) WHERE origem_id IS NOT NULL
          );
    ELSIF p_split = 'corretor' THEN
        SELECT jsonb_agg(
            jsonb_build_object('key', cor.id::text, 'label', cor.nome, 'cor', cor.cor)
            ORDER BY cor.nome
        )
        INTO v_series_meta
        FROM social_wiring.lead_corretores cor
        WHERE cor.org_id = p_org_id
          AND cor.id IN (
              SELECT DISTINCT corretor_id FROM social_wiring._leads_matching(
                  p_org_id, p_de, p_ate, p_ano, p_mes, p_origem_id, p_corretor_id,
                  p_tipo, p_tier, p_empreendimento, p_regiao, p_needs_review, p_q
              ) WHERE corretor_id IS NOT NULL
          );
    ELSE
        v_series_meta := '[]'::jsonb;
    END IF;

    RETURN jsonb_build_object(
        'grain', v_grain,
        'split', p_split,
        'series_meta', COALESCE(v_series_meta, '[]'::jsonb),
        'points', COALESCE(v_points, '[]'::jsonb)
    );
END;
$$;

REVOKE ALL ON FUNCTION social_wiring.leads_analytics_timeseries FROM PUBLIC;
GRANT EXECUTE ON FUNCTION social_wiring.leads_analytics_timeseries TO service_role;

-- ── leads_analytics_by_dimension — §5.3 ByDimensionOut ──────────────────
-- Mirrors `analytics_service._reference_by_dimension`: group the current
-- window by `p_dim`'s key (joined label for origem/corretor, fixed label
-- map for tipo/tier, raw value for empreendimento/regiao); rank
-- descending by total; the top `p_limit` become buckets with
-- share_pct/novos/retornos/variacao_pct (variacao_pct compares the SAME
-- key's total in the immediately-preceding window, same formula as
-- summary's comparativo); anything past the limit folds into ONE
-- "Outros" bucket (only emitted when there IS a remainder — same as the
-- Python `if rest_keys:` guard).
CREATE OR REPLACE FUNCTION social_wiring.leads_analytics_by_dimension(
    p_org_id uuid,
    p_de date DEFAULT NULL,
    p_ate date DEFAULT NULL,
    p_ano int[] DEFAULT NULL,
    p_mes int[] DEFAULT NULL,
    p_origem_id uuid[] DEFAULT NULL,
    p_corretor_id uuid[] DEFAULT NULL,
    p_tipo text[] DEFAULT NULL,
    p_tier text[] DEFAULT NULL,
    p_empreendimento text[] DEFAULT NULL,
    p_regiao text[] DEFAULT NULL,
    p_needs_review boolean DEFAULT NULL,
    p_q text DEFAULT NULL,
    p_dim text DEFAULT 'origem',
    p_limit int DEFAULT 15
) RETURNS jsonb
LANGUAGE plpgsql STABLE SECURITY INVOKER
SET search_path TO 'social_wiring', 'public'
AS $$
DECLARE
    v_has_prev boolean := (p_de IS NOT NULL AND p_ate IS NOT NULL);
    v_prev_de date;
    v_prev_ate date;
    v_total_all integer;
    v_buckets jsonb;
BEGIN
    IF v_has_prev THEN
        v_prev_ate := p_de - 1;
        v_prev_de := v_prev_ate - (p_ate - p_de);
    END IF;

    WITH cur AS (
        SELECT
            CASE p_dim
                WHEN 'origem' THEN src.slug
                WHEN 'corretor' THEN l.corretor_id::text
                WHEN 'tipo' THEN l.tipo_lead
                WHEN 'tier' THEN l.anuncio_tier
                WHEN 'empreendimento' THEN l.empreendimento
                WHEN 'regiao' THEN l.regiao
                ELSE NULL
            END AS key,
            CASE p_dim
                WHEN 'origem' THEN src.label
                WHEN 'corretor' THEN cor.nome
                WHEN 'tipo' THEN CASE l.tipo_lead WHEN 'novo' THEN 'Novo' WHEN 'retorno' THEN 'Retorno' ELSE 'Desconhecido' END
                WHEN 'tier' THEN CASE l.anuncio_tier WHEN 'simples' THEN 'Simples' WHEN 'destaque' THEN 'Destaque' WHEN 'super_destaque' THEN 'Super Destaque' ELSE NULL END
                WHEN 'empreendimento' THEN l.empreendimento
                WHEN 'regiao' THEN l.regiao
                ELSE NULL
            END AS label,
            CASE p_dim WHEN 'origem' THEN src.cor WHEN 'corretor' THEN cor.cor ELSE NULL END AS cor,
            l.tipo_lead
        FROM social_wiring._leads_matching(
            p_org_id, p_de, p_ate, p_ano, p_mes, p_origem_id, p_corretor_id,
            p_tipo, p_tier, p_empreendimento, p_regiao, p_needs_review, p_q
        ) l
        LEFT JOIN social_wiring.lead_sources src ON p_dim = 'origem' AND src.id = l.origem_id
        LEFT JOIN social_wiring.lead_corretores cor ON p_dim = 'corretor' AND cor.id = l.corretor_id
    ),
    cur_agg AS (
        SELECT key, max(label) AS label, max(cor) AS cor,
               count(*) AS total,
               count(*) FILTER (WHERE tipo_lead = 'novo') AS novos,
               count(*) FILTER (WHERE tipo_lead = 'retorno') AS retornos
        FROM cur
        WHERE key IS NOT NULL
        GROUP BY key
    ),
    prev_raw AS (
        SELECT
            CASE p_dim
                WHEN 'origem' THEN src.slug
                WHEN 'corretor' THEN l.corretor_id::text
                WHEN 'tipo' THEN l.tipo_lead
                WHEN 'tier' THEN l.anuncio_tier
                WHEN 'empreendimento' THEN l.empreendimento
                WHEN 'regiao' THEN l.regiao
                ELSE NULL
            END AS key
        FROM social_wiring._leads_matching(
            p_org_id, v_prev_de, v_prev_ate, p_ano, p_mes, p_origem_id, p_corretor_id,
            p_tipo, p_tier, p_empreendimento, p_regiao, p_needs_review, p_q
        ) l
        LEFT JOIN social_wiring.lead_sources src ON p_dim = 'origem' AND src.id = l.origem_id
        WHERE v_has_prev
    ),
    prev_agg AS (
        SELECT key, count(*) AS total FROM prev_raw WHERE key IS NOT NULL GROUP BY key
    ),
    ranked AS (
        SELECT c.key, c.label, c.cor, c.total, c.novos, c.retornos,
               COALESCE(p.total, 0) AS prev_total,
               row_number() OVER (ORDER BY c.total DESC, c.key) AS rn
        FROM cur_agg c
        LEFT JOIN prev_agg p ON p.key = c.key
    ),
    totals AS (
        SELECT COALESCE(sum(total), 0)::int AS total_all FROM cur_agg
    ),
    top_json AS (
        SELECT jsonb_agg(
            jsonb_build_object(
                'key', r.key, 'label', r.label, 'cor', r.cor, 'total', r.total,
                'share_pct', CASE WHEN t.total_all > 0
                    THEN round((r.total::numeric / t.total_all * 100), 1) ELSE 0 END,
                'novos', r.novos, 'retornos', r.retornos,
                'variacao_pct', CASE WHEN r.prev_total > 0
                    THEN round(((r.total - r.prev_total)::numeric / r.prev_total * 100), 1)
                    ELSE NULL END
            ) ORDER BY r.rn
        ) AS buckets
        FROM ranked r CROSS JOIN totals t
        WHERE r.rn <= GREATEST(p_limit, 0)
    ),
    rest_agg AS (
        SELECT
            COALESCE(sum(r.total), 0)::int AS total,
            COALESCE(sum(r.novos), 0)::int AS novos,
            COALESCE(sum(r.retornos), 0)::int AS retornos,
            COALESCE(sum(r.prev_total), 0)::int AS prev_total,
            count(*) AS n
        FROM ranked r
        WHERE r.rn > GREATEST(p_limit, 0)
    )
    SELECT
        t.total_all,
        CASE WHEN ra.n > 0 THEN
            COALESCE(tj.buckets, '[]'::jsonb) || jsonb_build_array(
                jsonb_build_object(
                    'key', 'outros', 'label', 'Outros', 'cor', NULL,
                    'total', ra.total,
                    'share_pct', CASE WHEN t.total_all > 0
                        THEN round((ra.total::numeric / t.total_all * 100), 1) ELSE 0 END,
                    'novos', ra.novos, 'retornos', ra.retornos,
                    'variacao_pct', CASE WHEN ra.prev_total > 0
                        THEN round(((ra.total - ra.prev_total)::numeric / ra.prev_total * 100), 1)
                        ELSE NULL END
                )
            )
        ELSE COALESCE(tj.buckets, '[]'::jsonb) END
    INTO v_total_all, v_buckets
    FROM totals t
    LEFT JOIN top_json tj ON true
    LEFT JOIN rest_agg ra ON true;

    RETURN jsonb_build_object(
        'dim', p_dim,
        'total', COALESCE(v_total_all, 0),
        'buckets', COALESCE(v_buckets, '[]'::jsonb)
    );
END;
$$;

REVOKE ALL ON FUNCTION social_wiring.leads_analytics_by_dimension FROM PUBLIC;
GRANT EXECUTE ON FUNCTION social_wiring.leads_analytics_by_dimension TO service_role;

-- ── leads_analytics_heatmap — §5.3 HeatmapOut ───────────────────────────
-- Mirrors `analytics_service._reference_heatmap`: count per (ano, mes),
-- one row per year with all 12 months present — NULL where the month has
-- no data at all (blank, not zero — the contract's explicit requirement).
CREATE OR REPLACE FUNCTION social_wiring.leads_analytics_heatmap(
    p_org_id uuid,
    p_de date DEFAULT NULL,
    p_ate date DEFAULT NULL,
    p_ano int[] DEFAULT NULL,
    p_mes int[] DEFAULT NULL,
    p_origem_id uuid[] DEFAULT NULL,
    p_corretor_id uuid[] DEFAULT NULL,
    p_tipo text[] DEFAULT NULL,
    p_tier text[] DEFAULT NULL,
    p_empreendimento text[] DEFAULT NULL,
    p_regiao text[] DEFAULT NULL,
    p_needs_review boolean DEFAULT NULL,
    p_q text DEFAULT NULL
) RETURNS jsonb
LANGUAGE sql STABLE SECURITY INVOKER
SET search_path TO 'social_wiring', 'public'
AS $$
    WITH counts AS (
        SELECT ano, mes, count(*) AS cnt
        FROM social_wiring._leads_matching(
            p_org_id, p_de, p_ate, p_ano, p_mes, p_origem_id, p_corretor_id,
            p_tipo, p_tier, p_empreendimento, p_regiao, p_needs_review, p_q
        )
        WHERE ano IS NOT NULL AND mes IS NOT NULL
        GROUP BY ano, mes
    ),
    anos AS (
        SELECT DISTINCT ano FROM counts
    ),
    cells AS (
        SELECT a.ano, jsonb_agg(c.cnt ORDER BY m.mes) AS row_arr
        FROM anos a
        CROSS JOIN generate_series(1, 12) AS m(mes)
        LEFT JOIN counts c ON c.ano = a.ano AND c.mes = m.mes
        GROUP BY a.ano
    )
    SELECT jsonb_build_object(
        'anos', COALESCE((SELECT jsonb_agg(ano ORDER BY ano) FROM anos), '[]'::jsonb),
        'cells', COALESCE((SELECT jsonb_object_agg(ano::text, row_arr) FROM cells), '{}'::jsonb),
        'max', COALESCE((SELECT max(cnt) FROM counts), 0)
    );
$$;

REVOKE ALL ON FUNCTION social_wiring.leads_analytics_heatmap FROM PUBLIC;
GRANT EXECUTE ON FUNCTION social_wiring.leads_analytics_heatmap TO service_role;

-- ── leads_facets — §5.2 GET /api/leads/facets ───────────────────────────
-- Mirrors `leads_service._reference_facets`: distinct empreendimentos /
-- regioes (with counts, sorted -count then value) + distinct anos, all
-- over the current filtered window.
CREATE OR REPLACE FUNCTION social_wiring.leads_facets(
    p_org_id uuid,
    p_de date DEFAULT NULL,
    p_ate date DEFAULT NULL,
    p_ano int[] DEFAULT NULL,
    p_mes int[] DEFAULT NULL,
    p_origem_id uuid[] DEFAULT NULL,
    p_corretor_id uuid[] DEFAULT NULL,
    p_tipo text[] DEFAULT NULL,
    p_tier text[] DEFAULT NULL,
    p_empreendimento text[] DEFAULT NULL,
    p_regiao text[] DEFAULT NULL,
    p_needs_review boolean DEFAULT NULL,
    p_q text DEFAULT NULL
) RETURNS jsonb
LANGUAGE sql STABLE SECURITY INVOKER
SET search_path TO 'social_wiring', 'public'
AS $$
    WITH matched AS (
        SELECT * FROM social_wiring._leads_matching(
            p_org_id, p_de, p_ate, p_ano, p_mes, p_origem_id, p_corretor_id,
            p_tipo, p_tier, p_empreendimento, p_regiao, p_needs_review, p_q
        )
    ),
    emp AS (
        SELECT empreendimento AS value, count(*) AS cnt
        FROM matched WHERE empreendimento IS NOT NULL
        GROUP BY empreendimento
    ),
    reg AS (
        SELECT regiao AS value, count(*) AS cnt
        FROM matched WHERE regiao IS NOT NULL
        GROUP BY regiao
    ),
    anos AS (
        SELECT DISTINCT ano FROM matched WHERE ano IS NOT NULL
    )
    SELECT jsonb_build_object(
        'empreendimentos', COALESCE(
            (SELECT jsonb_agg(jsonb_build_object('value', value, 'count', cnt) ORDER BY cnt DESC, value)
             FROM emp), '[]'::jsonb),
        'regioes', COALESCE(
            (SELECT jsonb_agg(jsonb_build_object('value', value, 'count', cnt) ORDER BY cnt DESC, value)
             FROM reg), '[]'::jsonb),
        'anos', COALESCE((SELECT jsonb_agg(ano ORDER BY ano) FROM anos), '[]'::jsonb)
    );
$$;

REVOKE ALL ON FUNCTION social_wiring.leads_facets FROM PUBLIC;
GRANT EXECUTE ON FUNCTION social_wiring.leads_facets TO service_role;
