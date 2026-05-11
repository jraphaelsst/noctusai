-- ============================================================================
-- Migration 002 — Phase 9 (cancellation + reschedule) appointment audit columns
--
-- Adds the cancellation + reschedule audit trail to ``appointments``. Mirrors
-- the in-place edit in 001 so a fresh DB built from 001 alone reproduces the
-- exact same shape this patch produces against a live DB sitting at the
-- pre-Phase-9 schema state.
--
-- Convention (`KB § PATTERNS/database-rls.md § Single 001 migration`):
--   - Greenfield: re-running 001 alone re-creates the columns; this file is
--     a no-op (the ``IF NOT EXISTS`` guards make it safe to re-run).
--   - Live: this patch is the only thing that needs to land on prod databases
--     already past 001.
--
-- Columns added to ``imobi_scheduling.appointments``:
--   - ``cancellation_reason TEXT``           — free-text rationale (LLM-summarized)
--   - ``cancelled_at TIMESTAMPTZ``           — UTC timestamp when cancellation landed
--   - ``cancelled_by UUID``                  — FK to ``imobi_scheduling.users`` (nullable)
--   - ``rescheduled_at TIMESTAMPTZ``         — UTC timestamp when reschedule landed
--   - ``rescheduled_by UUID``                — FK to ``imobi_scheduling.users`` (nullable)
--   - ``previous_start_at TIMESTAMPTZ``      — captured before reschedule overwrites ``start_at``
--   - ``previous_end_at TIMESTAMPTZ``        — captured before reschedule overwrites ``end_at``
--
-- RLS: inherits the existing ``appointments_*_org`` policies — no policy change.
-- ============================================================================

SET search_path = imobi_scheduling, public;

ALTER TABLE imobi_scheduling.appointments
    ADD COLUMN IF NOT EXISTS cancellation_reason TEXT,
    ADD COLUMN IF NOT EXISTS cancelled_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS cancelled_by UUID REFERENCES imobi_scheduling.users(id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS rescheduled_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS rescheduled_by UUID REFERENCES imobi_scheduling.users(id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS previous_start_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS previous_end_at TIMESTAMPTZ;
