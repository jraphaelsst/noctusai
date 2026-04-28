-- =====================================================================
-- 021 — Per-entity AI outputs storage (P1 indicator pattern)
--
-- Backs <AIIndicator refType refId/> for ERP. Every product opting into
-- the P1 pattern ships this same template (KB § 04-SHARED-LIBRARY.md
-- § ai/). Indicators are the read-side of the seed `/api/ai/outputs`
-- standard router; writes happen from product AI services via
-- noctusai_lib.ai.persist_output().
--
-- Org scoping: org_id auto-fills from public.current_org_id() so service
-- code passing the seed AIOutput dataclass shape (which has no org_id
-- field) still produces an RLS-scoped row.
-- =====================================================================

CREATE TABLE IF NOT EXISTS erp.ai_outputs (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id          UUID NOT NULL DEFAULT public.current_org_id(),
    ref_type        TEXT NOT NULL,
    ref_id          UUID NOT NULL,
    kind            TEXT NOT NULL,
    label           TEXT NOT NULL,
    score           NUMERIC,
    chip            TEXT,
    explanation     TEXT,
    confidence      NUMERIC,
    model_version   TEXT,
    prompt_version  TEXT,
    metadata        JSONB NOT NULL DEFAULT '{}',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT ai_outputs_kind_check CHECK (
        kind IN ('classification', 'score', 'flag', 'extraction', 'narrative')
    ),
    CONSTRAINT ai_outputs_confidence_range CHECK (
        confidence IS NULL OR (confidence >= 0 AND confidence <= 1)
    )
);

CREATE INDEX IF NOT EXISTS ai_outputs_ref_idx
    ON erp.ai_outputs (ref_type, ref_id, created_at DESC);
CREATE INDEX IF NOT EXISTS ai_outputs_created_idx
    ON erp.ai_outputs (created_at DESC);
CREATE INDEX IF NOT EXISTS ai_outputs_org_idx
    ON erp.ai_outputs (org_id);

ALTER TABLE erp.ai_outputs ENABLE ROW LEVEL SECURITY;

-- SELECT: org members read their org's outputs (RLS via current_org_id()).
CREATE POLICY "ai_outputs_select_own_org" ON erp.ai_outputs
    FOR SELECT
    USING (org_id = public.current_org_id());

-- INSERT: only into the caller's org. The DEFAULT auto-fills org_id;
-- WITH CHECK guards against a client that explicitly passes a different
-- org_id.
CREATE POLICY "ai_outputs_insert_own_org" ON erp.ai_outputs
    FOR INSERT
    WITH CHECK (org_id = public.current_org_id());

-- UPDATE/DELETE: admins only (rare — typically rows are insert-only and
-- the newest one wins per ref_id ordering).
CREATE POLICY "ai_outputs_admin_full" ON erp.ai_outputs
    FOR ALL
    USING (public.has_role((SELECT auth.uid()), 'admin'::erp.app_role))
    WITH CHECK (public.has_role((SELECT auth.uid()), 'admin'::erp.app_role));

COMMENT ON TABLE erp.ai_outputs IS
    'Per-entity AI inferences (classifications/scores/flags/extractions/narratives). Read by /api/ai/outputs standard router; written by erp services via noctusai_lib.ai.persist_output.';
