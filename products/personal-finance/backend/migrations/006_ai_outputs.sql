-- =====================================================================
-- 006 — Per-entity AI outputs storage (P1 indicator pattern)
--
-- Backs <AIIndicator refType refId/> for Personal Finance. Read by the
-- seed `/api/ai/outputs` standard router; written by product AI services
-- via noctusai_lib.ai.persist_output.
--
-- Org scoping: org_id auto-fills from public.current_org_id() so
-- service code passing the seed AIOutput dataclass shape (which has no
-- org_id field) still produces an RLS-scoped row.
-- =====================================================================

CREATE TABLE IF NOT EXISTS "personal-finance".ai_outputs (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id          UUID NOT NULL DEFAULT public.current_org_id() REFERENCES public.organizations(id),
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
    ON "personal-finance".ai_outputs (ref_type, ref_id, created_at DESC);
CREATE INDEX IF NOT EXISTS ai_outputs_created_idx
    ON "personal-finance".ai_outputs (created_at DESC);
CREATE INDEX IF NOT EXISTS ai_outputs_org_idx
    ON "personal-finance".ai_outputs (org_id);

ALTER TABLE "personal-finance".ai_outputs ENABLE ROW LEVEL SECURITY;

CREATE POLICY "ai_outputs_org_scoped" ON "personal-finance".ai_outputs
    FOR ALL TO authenticated
    USING (org_id = public.current_org_id())
    WITH CHECK (org_id = public.current_org_id());

COMMENT ON TABLE "personal-finance".ai_outputs IS
    'Per-entity AI inferences (classifications/scores/flags/extractions/narratives). Read by /api/ai/outputs standard router; written by personal-finance services via noctusai_lib.ai.persist_output.';
