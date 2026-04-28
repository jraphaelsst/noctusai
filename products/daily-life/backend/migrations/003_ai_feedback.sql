-- =====================================================================
-- 003 — Per-output AI feedback (X3 cross-cutting widget)
--
-- User-scoped (matches the rest of daily_life.* — RLS via auth.uid()).
-- See KB § 04-SHARED-LIBRARY § ai/.
-- =====================================================================

CREATE TABLE IF NOT EXISTS daily_life.ai_feedback (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id          UUID,
    user_id         UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    output_ref      TEXT NOT NULL,
    rating          INT NOT NULL CHECK (rating IN (-1, 1)),
    notes           TEXT,
    prompt_version  TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT ai_feedback_user_ref_unique UNIQUE (user_id, output_ref)
);

CREATE INDEX IF NOT EXISTS ai_feedback_output_ref_idx
    ON daily_life.ai_feedback (output_ref);
CREATE INDEX IF NOT EXISTS ai_feedback_user_idx
    ON daily_life.ai_feedback (user_id);

ALTER TABLE daily_life.ai_feedback ENABLE ROW LEVEL SECURITY;

CREATE POLICY "ai_feedback_select_own" ON daily_life.ai_feedback
    FOR SELECT TO authenticated
    USING (user_id = (SELECT auth.uid()));

CREATE POLICY "ai_feedback_insert_own" ON daily_life.ai_feedback
    FOR INSERT TO authenticated
    WITH CHECK (user_id = (SELECT auth.uid()));

CREATE POLICY "ai_feedback_update_own" ON daily_life.ai_feedback
    FOR UPDATE TO authenticated
    USING (user_id = (SELECT auth.uid()))
    WITH CHECK (user_id = (SELECT auth.uid()));

CREATE POLICY "ai_feedback_delete_own" ON daily_life.ai_feedback
    FOR DELETE TO authenticated
    USING (user_id = (SELECT auth.uid()));

COMMENT ON TABLE daily_life.ai_feedback IS
    'Per-output AI feedback (user-scoped). Read+written by /api/ai/feedback standard router.';
