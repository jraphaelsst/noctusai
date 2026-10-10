-- ============================================================================
-- Migration 243 — automation_enrollments.pause_reason + paused_at.
--
-- WHY: the email-marketing step executor (P1b(b)) pauses an enrollment on a
-- webhook step, a malformed config, or a template/list that is gone — and the
-- only explanation lived in the job's dead letter, which no operator sees: a
-- silent-error shape. The executor now writes the reason here, the Automações
-- enrollments view shows it, and re-enrolling clears both columns.
-- Additive + idempotent.
-- ============================================================================

ALTER TABLE social_wiring.automation_enrollments
    ADD COLUMN IF NOT EXISTS pause_reason TEXT,
    ADD COLUMN IF NOT EXISTS paused_at    TIMESTAMPTZ;

COMMENT ON COLUMN social_wiring.automation_enrollments.pause_reason IS
    'Why the step executor paused this enrollment (NULL unless status = paused).';
