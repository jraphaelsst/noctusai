-- 126_fotos_modelos.sql -- social_wiring: model notes history + live
-- metrics RPC
--
-- Plan §1: "Catalog shows name, version, performance/cheap tag,
-- batch-capable tag, and recommendations: live metrics instantly + notes
-- rewritten daily 00:05 America/Sao_Paulo by AI from our own results."
--
-- The catalog itself (name/version/tags) is CODE, not data --
-- `noctusai_lib.integrations.llm.models.MODELS` (S2, this project's Wave
-- 1). This migration ships the two pieces that ARE data: the append-only
-- history of AI-written daily notes per model, and a metrics RPC computed
-- live from fotos_decisoes / fotos_avaliacoes / fotos_edicoes / llm_usage
-- -- never stored/cached, per "live metrics instantly".
--
-- FORWARD-ONLY. MIGRATION FILE ONLY -- not applied to any database by this
-- change. Applying needs owner consent.

SET search_path = social_wiring, public;

-- ----------------------------------------------------------------------------
-- 1. fotos_modelos_notas -- append-only AI-written note history per model
-- ----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS social_wiring.fotos_modelos_notas (
    id          BIGSERIAL PRIMARY KEY,
    -- `noctusai_lib.integrations.llm.models.ModelEntry.id` -- free text,
    -- no FK (the catalog is code, not a table).
    modelo_id   TEXT NOT NULL,
    texto       TEXT NOT NULL,
    -- The metrics snapshot the note was generated from -- lets a human
    -- audit "why did the daily writer say this" without re-deriving it.
    dados_base  JSONB NOT NULL DEFAULT '{}'::jsonb,
    gerado_em   TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Latest-note-per-model read path (the /modelos endpoint's common query).
CREATE INDEX IF NOT EXISTS ix_fotos_modelos_notas_modelo_gerado
    ON social_wiring.fotos_modelos_notas (modelo_id, gerado_em DESC);

ALTER TABLE social_wiring.fotos_modelos_notas ENABLE ROW LEVEL SECURITY;

-- Model selection is org-admin/platform-admin surface (contract §8),
-- not org-scoped data -- role-gated only.
CREATE POLICY "fotos_modelos_notas_select_admins" ON social_wiring.fotos_modelos_notas
    FOR SELECT TO authenticated
    USING (public.current_org_role() = ANY (ARRAY['owner', 'admin', 'manager']) OR public.is_platform_admin());

CREATE POLICY "service_role_bypass" ON social_wiring.fotos_modelos_notas
    FOR ALL TO service_role USING (true) WITH CHECK (true);

-- ----------------------------------------------------------------------------
-- 2. fotos_modelo_metricas() -- live metrics RPC (approval rate, average
--    AI score, cost per approved photo), computed on every call
-- ----------------------------------------------------------------------------
--
-- SECURITY DEFINER + STABLE -- reads across fotos_avaliacoes (which most
-- callers' own RLS would otherwise deny for a corretor caller); this RPC
-- is deliberately reachable only through the /modelos endpoint's own
-- admin-tier gate, not exposed as a raw PostgREST table read.
--
-- Cost is computed only for photos whose LATEST decision is 'aprovar' --
-- "cost per APPROVED photo" per plan §1. A photo edited with `modelo_id`
-- but whose fotos_edicoes.llm_usage_id was never linked (e.g. a very
-- early dev call before the sink was wired) contributes 0 to the cost sum
-- for that photo, same silent-zero-for-unknown-cost convention
-- `ModelEntry.cost_per_1m_*_tokens = None` already uses elsewhere in this
-- codebase, never a fabricated number.

CREATE OR REPLACE FUNCTION social_wiring.fotos_modelo_metricas(p_modelo_id TEXT)
RETURNS TABLE (
    total_fotos                   BIGINT,
    taxa_aprovacao                 NUMERIC,
    score_medio                    NUMERIC,
    custo_por_foto_aprovada_usd    NUMERIC
)
LANGUAGE sql STABLE SECURITY DEFINER
SET search_path = social_wiring, public
AS $$
    WITH ultima_decisao AS (
        SELECT DISTINCT ON (d.foto_id) d.foto_id, d.decisao
        FROM social_wiring.fotos_decisoes d
        JOIN social_wiring.fotos_edicoes e
            ON e.foto_id = d.foto_id AND e.modelo_id = p_modelo_id
        ORDER BY d.foto_id, d.created_at DESC
    ),
    custos AS (
        SELECT e.foto_id, u.cost_estimate_usd
        FROM social_wiring.fotos_edicoes e
        LEFT JOIN social_wiring.llm_usage u ON u.id = e.llm_usage_id
        WHERE e.modelo_id = p_modelo_id
    ),
    scores AS (
        SELECT a.foto_id, a.score
        FROM social_wiring.fotos_avaliacoes a
        JOIN social_wiring.fotos_edicoes e ON e.id = a.edicao_id
        WHERE e.modelo_id = p_modelo_id
    )
    SELECT
        (SELECT COUNT(*) FROM ultima_decisao),
        COALESCE((SELECT AVG(CASE WHEN decisao = 'aprovar' THEN 1.0 ELSE 0.0 END) FROM ultima_decisao), 0),
        COALESCE((SELECT AVG(score) FROM scores), 0),
        COALESCE(
            (
                SELECT SUM(COALESCE(c.cost_estimate_usd, 0))
                FROM custos c
                JOIN ultima_decisao ud ON ud.foto_id = c.foto_id AND ud.decisao = 'aprovar'
            )
            / NULLIF((SELECT COUNT(*) FROM ultima_decisao WHERE decisao = 'aprovar'), 0),
            0
        );
$$;
