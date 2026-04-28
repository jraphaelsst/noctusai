-- =====================================================================
-- 022 — Per-output AI feedback (X3 cross-cutting widget)
--
-- Backs <AIFeedbackButtons output_ref/> from @noctusai/lib/design-system.
-- Each product opting into the seed `ai_feedback` standard router ships
-- this same template (KB § 04-SHARED-LIBRARY § ai/).
--
-- output_ref shapes:
--   indicator: "ai_output:<uuid>"
--   digest:    "digest:<service>:<token>"
-- =====================================================================

CREATE TABLE IF NOT EXISTS erp.ai_feedback (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id          UUID NOT NULL DEFAULT public.current_org_id(),
    user_id         UUID NOT NULL,
    output_ref      TEXT NOT NULL,
    rating          INT NOT NULL CHECK (rating IN (-1, 1)),
    notes           TEXT,
    prompt_version  TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT ai_feedback_user_ref_unique UNIQUE (user_id, output_ref)
);

CREATE INDEX IF NOT EXISTS ai_feedback_output_ref_idx
    ON erp.ai_feedback (output_ref);
CREATE INDEX IF NOT EXISTS ai_feedback_org_idx
    ON erp.ai_feedback (org_id);

ALTER TABLE erp.ai_feedback ENABLE ROW LEVEL SECURITY;

CREATE POLICY "ai_feedback_select_own_org" ON erp.ai_feedback
    FOR SELECT
    USING (org_id = public.current_org_id());

CREATE POLICY "ai_feedback_insert_own_org" ON erp.ai_feedback
    FOR INSERT
    WITH CHECK (
        org_id = public.current_org_id()
        AND user_id = (SELECT auth.uid())
    );

CREATE POLICY "ai_feedback_update_own" ON erp.ai_feedback
    FOR UPDATE
    USING (user_id = (SELECT auth.uid()))
    WITH CHECK (user_id = (SELECT auth.uid()));

CREATE POLICY "ai_feedback_admin_full" ON erp.ai_feedback
    FOR ALL
    USING (public.has_role((SELECT auth.uid()), 'admin'::erp.app_role))
    WITH CHECK (public.has_role((SELECT auth.uid()), 'admin'::erp.app_role));

COMMENT ON TABLE erp.ai_feedback IS
    'Per-output AI feedback (thumbs up/down). Read+written by /api/ai/feedback standard router. UNIQUE(user_id, output_ref) makes upsert toggle-friendly.';
