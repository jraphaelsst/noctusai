-- =====================================================================
-- 002 — Per-entity AI outputs storage (P1 indicator pattern)
--
-- Backs <AIIndicator refType refId/> for Mailing. Read by the seed
-- /api/ai/outputs standard router; written by Mailing services via
-- noctusai_lib.ai.persist_output.
--
-- Scopes by org_id matching the JWT claim (matches the rest of mailing.*).
-- =====================================================================

CREATE TABLE IF NOT EXISTS mailing.ai_outputs (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    -- Postgres forbids subqueries in DEFAULT, so we lean on the platform
    -- helper public.current_org_id() (returns the JWT's org claim).
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
    ON mailing.ai_outputs (ref_type, ref_id, created_at DESC);
CREATE INDEX IF NOT EXISTS ai_outputs_created_idx
    ON mailing.ai_outputs (created_at DESC);
CREATE INDEX IF NOT EXISTS ai_outputs_org_idx
    ON mailing.ai_outputs (org_id);

ALTER TABLE mailing.ai_outputs ENABLE ROW LEVEL SECURITY;

CREATE POLICY "ai_outputs_own_org" ON mailing.ai_outputs
    FOR ALL TO authenticated
    USING (org_id = ((SELECT auth.jwt()) ->> 'org_id')::uuid)
    WITH CHECK (org_id = ((SELECT auth.jwt()) ->> 'org_id')::uuid);

COMMENT ON TABLE mailing.ai_outputs IS
    'Per-entity AI inferences (M3 contact segmentation + future). Read by /api/ai/outputs standard router; written by mailing services via noctusai_lib.ai.persist_output.';
