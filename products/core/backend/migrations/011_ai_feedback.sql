-- =====================================================================
-- 011 — Per-output AI feedback (X3 cross-cutting widget)
--
-- Public schema since Core's `ai_feedback` aggregates feedback for the
-- platform-level audit digest narrative. See KB § 04-SHARED-LIBRARY § ai/.
-- =====================================================================

CREATE TABLE IF NOT EXISTS public.ai_feedback (
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
    ON public.ai_feedback (output_ref);
CREATE INDEX IF NOT EXISTS ai_feedback_org_idx
    ON public.ai_feedback (org_id);

ALTER TABLE public.ai_feedback ENABLE ROW LEVEL SECURITY;

CREATE POLICY "ai_feedback_select_own_org" ON public.ai_feedback
    FOR SELECT
    USING (org_id = public.current_org_id());

CREATE POLICY "ai_feedback_insert_own" ON public.ai_feedback
    FOR INSERT
    WITH CHECK (
        org_id = public.current_org_id()
        AND user_id = (SELECT auth.uid())
    );

CREATE POLICY "ai_feedback_update_own" ON public.ai_feedback
    FOR UPDATE
    USING (user_id = (SELECT auth.uid()))
    WITH CHECK (user_id = (SELECT auth.uid()));

CREATE POLICY "ai_feedback_admin_full" ON public.ai_feedback
    FOR ALL
    USING ((SELECT auth.uid()) IN (SELECT id FROM public.noctus_users WHERE role = 'admin'))
    WITH CHECK ((SELECT auth.uid()) IN (SELECT id FROM public.noctus_users WHERE role = 'admin'));

COMMENT ON TABLE public.ai_feedback IS
    'Per-output AI feedback (Core/public schema). Read+written by /api/ai/feedback standard router.';
