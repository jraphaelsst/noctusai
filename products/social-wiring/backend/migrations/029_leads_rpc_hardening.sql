-- 029_leads_rpc_hardening.sql — two correctness fixes to the migration
-- 027 analytics RPC functions. 027 is ALREADY APPLIED to the live DB —
-- these are `CREATE OR REPLACE FUNCTION` redefinitions, not edits to
-- that file (never edit an applied migration in place).
--
-- FIX 1 — `q` free-text search treated `%`/`_` as ILIKE wildcards
-- ──────────────────────────────────────────────────────────────
-- `_leads_matching`'s free-text clause builds `'%' || p_q || '%'` and
-- feeds it straight to ILIKE — so a search for a literal `%` or `_`
-- (typed by a user searching e.g. a phone/percentage-looking string)
-- silently becomes a WILDCARD there. Observed divergence: searching
-- "50%" returns the 3 actually-matching leads via the Python path
-- (`query.py::matches_free_text` — already literal, was always
-- correct) but SQL's `leads_analytics_summary` returns the FULL org
-- total (12,177), because `%50%%` matches everything. Same filter, two
-- different answers on the same page.
--
-- Fix: escape `%`/`_`/`\` in `p_q` (via `_escape_ilike_pattern`) before
-- interpolating — the same string now matches the SAME literal
-- substring, in Python AND SQL. `ESCAPE '\'` is Postgres's ILIKE
-- default anyway; stated explicitly for clarity.
--
-- FIX 2 — `media_diaria`'s divisor changes definition depending on the
-- date filter, and can divide by future days
-- ──────────────────────────────────────────────────────────────────
-- No `de`/`ate` filter -> divisor was `count(DISTINCT data_entrada)`
-- ("days WITH data"). `de`+`ate` set -> divisor was `(ate - de) + 1`
-- ("every calendar day in the window, including ones that haven't
-- happened yet"). Toggling a date filter changed what the number MEANS,
-- and picking e.g. "este ano" mid-year divided ~7 months of real leads
-- by 365 calendar days, showing roughly half the true daily rate.
--
-- Decision (ratified by the user, not this migration's author): ONE
-- definition everywhere — leads per CALENDAR DAY, clamped to the days
-- that could plausibly have data:
--   * upper bound: `LEAST(effective_ate, CURRENT_DATE)` — never divide
--     by days that haven't happened yet.
--   * lower bound: `GREATEST(effective_de, min(data_entrada) over the
--     filtered set)` — never divide by days before the data existed.
--   * unfiltered case: `effective_de`/`effective_ate` default to the
--     filtered set's own `min`/`max(data_entrada)` — i.e. leads-per-day
--     across the org's OBSERVED span, not since some arbitrary epoch.
--   * `v_total = 0` short-circuits to `media_diaria = 0` (never divides
--     by a NULL min/max, and floors a fully-future filter range to 0
--     instead of a divide-by-zero/negative-span error).
-- Ported line-for-line into `analytics_service._reference_summary` (the
-- Python equivalence oracle) in the same change — see that function's
-- docstring.
--
-- 🔴 MIGRATION FILE ONLY — not applied to any DB by this change. Apply
-- via noctus.dev.migrate_product with explicit tech-lead consent.
-- Forward-only + idempotent (CREATE OR REPLACE FUNCTION).

SET search_path = social_wiring, public;

-- ── shared ILIKE-pattern escaper (private) ──────────────────────────────
CREATE OR REPLACE FUNCTION social_wiring._escape_ilike_pattern(p_text text)
RETURNS text
LANGUAGE sql IMMUTABLE SECURITY INVOKER
AS $$
    -- Backslash first (it's the escape character itself), then the two
    -- ILIKE metacharacters.
    SELECT replace(replace(replace(p_text, '\', '\\'), '%', '\%'), '_', '\_');
$$;

REVOKE ALL ON FUNCTION social_wiring._escape_ilike_pattern FROM PUBLIC;
GRANT EXECUTE ON FUNCTION social_wiring._escape_ilike_pattern TO service_role;

-- ── _leads_matching — FIX 1 (q escaping) ────────────────────────────────
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
            l.cliente_nome ILIKE '%' || social_wiring._escape_ilike_pattern(p_q) || '%' ESCAPE '\' OR
            l.contato      ILIKE '%' || social_wiring._escape_ilike_pattern(p_q) || '%' ESCAPE '\' OR
            l.codigo_raw   ILIKE '%' || social_wiring._escape_ilike_pattern(p_q) || '%' ESCAPE '\' OR
            l.observacoes  ILIKE '%' || social_wiring._escape_ilike_pattern(p_q) || '%' ESCAPE '\'
      );
$$;

REVOKE ALL ON FUNCTION social_wiring._leads_matching FROM PUBLIC;
GRANT EXECUTE ON FUNCTION social_wiring._leads_matching TO service_role;

-- ── leads_analytics_summary — FIX 2 (media_diaria) ──────────────────────
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
    v_min_de date;
    v_max_de date;
    v_eff_de date;
    v_eff_ate date;
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

    -- media_diaria: leads per CALENDAR DAY, clamped to the days that
    -- could plausibly have data (never future, never before the
    -- earliest lead in this filtered set). See the header comment for
    -- the full rationale + the Python oracle
    -- (`analytics_service._reference_summary`) this must match exactly.
    IF v_total = 0 THEN
        v_media_diaria := 0;
    ELSE
        SELECT min(data_entrada), max(data_entrada)
        INTO v_min_de, v_max_de
        FROM social_wiring._leads_matching(
            p_org_id, p_de, p_ate, p_ano, p_mes, p_origem_id, p_corretor_id,
            p_tipo, p_tier, p_empreendimento, p_regiao, p_needs_review, p_q
        );
        v_eff_de := COALESCE(p_de, v_min_de);
        v_eff_ate := COALESCE(p_ate, v_max_de);
        v_eff_de := GREATEST(v_eff_de, v_min_de);
        v_eff_ate := LEAST(v_eff_ate, CURRENT_DATE);
        v_span_days := GREATEST((v_eff_ate - v_eff_de) + 1, 1);
        v_media_diaria := round((v_total::numeric / v_span_days), 2);
    END IF;

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
        v_prev_de := v_prev_ate - ((p_ate - p_de));
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
