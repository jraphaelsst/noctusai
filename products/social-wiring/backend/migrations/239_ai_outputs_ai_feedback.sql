-- ============================================================================
-- Migration 239 — social_wiring.ai_outputs + social_wiring.ai_feedback.
--
-- WHY: social-wiring mounts the seed `ai_outputs` / `ai_feedback` standard
-- routers (app/main.py) but never had either table, so both endpoints failed;
-- and email_marketing's contact segmentation still persisted into the legacy
-- `mailing.ai_outputs`, which the owner retired on 2026-10-10 (harvest into
-- email_marketing, then drop `mailing`). This gives social-wiring its own.
--
-- The bodies below are noctusai_lib.domain.sql_templates.ai_outputs_table_sql /
-- ai_feedback_table_sql('social_wiring') pasted VERBATIM (a test pins parity).
-- Idempotent. Nothing to copy from mailing: 0 rows there.
-- ============================================================================

CREATE TABLE IF NOT EXISTS social_wiring.ai_outputs (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id         UUID NOT NULL DEFAULT public.current_org_id_for('social_wiring'),
    ref_type       TEXT NOT NULL,
    ref_id         UUID NOT NULL,
    kind           TEXT NOT NULL,
    label          TEXT NOT NULL,
    score          NUMERIC,
    chip           TEXT,
    explanation    TEXT,
    confidence     NUMERIC,
    model_version  TEXT,
    prompt_version TEXT,
    metadata       JSONB NOT NULL DEFAULT '{}',
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT ai_outputs_kind_check CHECK (
        kind IN ('classification', 'score', 'flag', 'extraction', 'narrative')),
    CONSTRAINT ai_outputs_confidence_range CHECK (
        confidence IS NULL OR (confidence >= 0 AND confidence <= 1))
);
CREATE INDEX IF NOT EXISTS ai_outputs_ref_idx ON social_wiring.ai_outputs (ref_type, ref_id, created_at DESC);
CREATE INDEX IF NOT EXISTS ai_outputs_org_idx ON social_wiring.ai_outputs (org_id);
ALTER TABLE social_wiring.ai_outputs ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS ai_outputs_own_org ON social_wiring.ai_outputs;
CREATE POLICY ai_outputs_own_org ON social_wiring.ai_outputs FOR ALL TO authenticated
    USING (org_id = (SELECT public.current_org_id_for('social_wiring'))) WITH CHECK (org_id = (SELECT public.current_org_id_for('social_wiring')));
DROP POLICY IF EXISTS service_role_bypass ON social_wiring.ai_outputs;
CREATE POLICY service_role_bypass ON social_wiring.ai_outputs FOR ALL TO service_role
    USING (true) WITH CHECK (true);
REVOKE ALL ON social_wiring.ai_outputs FROM anon;
GRANT SELECT, INSERT, UPDATE, DELETE ON social_wiring.ai_outputs TO authenticated;
GRANT ALL ON social_wiring.ai_outputs TO service_role;

CREATE TABLE IF NOT EXISTS social_wiring.ai_feedback (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id         UUID NOT NULL DEFAULT public.current_org_id_for('social_wiring'),
    user_id        UUID NOT NULL,
    output_ref     TEXT NOT NULL,
    rating         INTEGER NOT NULL,
    notes          TEXT,
    prompt_version TEXT,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT ai_feedback_user_ref_unique UNIQUE (user_id, output_ref),
    CONSTRAINT ai_feedback_rating_check CHECK (rating IN (-1, 1))
);
CREATE INDEX IF NOT EXISTS ai_feedback_org_idx ON social_wiring.ai_feedback (org_id);
ALTER TABLE social_wiring.ai_feedback ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS ai_feedback_own_org ON social_wiring.ai_feedback;
CREATE POLICY ai_feedback_own_org ON social_wiring.ai_feedback FOR ALL TO authenticated
    USING (org_id = (SELECT public.current_org_id_for('social_wiring')))
    WITH CHECK (org_id = (SELECT public.current_org_id_for('social_wiring')) AND user_id = (SELECT auth.uid()));
DROP POLICY IF EXISTS service_role_bypass ON social_wiring.ai_feedback;
CREATE POLICY service_role_bypass ON social_wiring.ai_feedback FOR ALL TO service_role
    USING (true) WITH CHECK (true);
REVOKE ALL ON social_wiring.ai_feedback FROM anon;
GRANT SELECT, INSERT, UPDATE, DELETE ON social_wiring.ai_feedback TO authenticated;
GRANT ALL ON social_wiring.ai_feedback TO service_role;
