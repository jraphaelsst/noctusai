-- =====================================================================
-- 007 — Per-output AI feedback (X3 cross-cutting widget)
-- See KB § 04-SHARED-LIBRARY § ai/ for the cross-product template.
-- =====================================================================

CREATE TABLE IF NOT EXISTS "personal-finance".ai_feedback (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id          UUID NOT NULL DEFAULT public.current_org_id() REFERENCES public.organizations(id),
    user_id         UUID NOT NULL,
    output_ref      TEXT NOT NULL,
    rating          INT NOT NULL CHECK (rating IN (-1, 1)),
    notes           TEXT,
    prompt_version  TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT ai_feedback_user_ref_unique UNIQUE (user_id, output_ref)
);

CREATE INDEX IF NOT EXISTS ai_feedback_output_ref_idx
    ON "personal-finance".ai_feedback (output_ref);
CREATE INDEX IF NOT EXISTS ai_feedback_org_idx
    ON "personal-finance".ai_feedback (org_id);

ALTER TABLE "personal-finance".ai_feedback ENABLE ROW LEVEL SECURITY;

CREATE POLICY "ai_feedback_org_scoped" ON "personal-finance".ai_feedback
    FOR ALL TO authenticated
    USING (org_id = public.current_org_id())
    WITH CHECK (
        org_id = public.current_org_id()
        AND user_id = (SELECT auth.uid())
    );

COMMENT ON TABLE "personal-finance".ai_feedback IS
    'Per-output AI feedback. Read+written by /api/ai/feedback standard router.';
