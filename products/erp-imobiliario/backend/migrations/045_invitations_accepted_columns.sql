-- ============================================================================
-- Migration 045 — erp.invitations: accepted_at + accepted_by
--
-- WHY THIS EXISTS
-- ---------------
-- The seed team router's POST /api/team/accept now records WHO accepted an
-- invitation, via `accept_invitation(..., accepted_by=user_id)` — the kwarg
-- `noctusai_lib.domain.invitations.accept_invitation` has carried since
-- 2026-05-11 but which nothing passed until the accept endpoint was completed
-- on 2026-08-07.
--
-- Eight of the nine schemas mounting the seed team router already have these
-- columns (the canonical scaffold ships them via seed migration 002). `erp` was
-- the one that missed the propagation, so an accept there would fail on an
-- unknown column while the rest of the fleet succeeded — exactly the kind of
-- per-product divergence the seed exists to prevent.
--
-- The lib helper writes these columns ONLY when `accepted_by` is passed, which
-- is why the gap stayed invisible: the previous caller never passed it.
--
-- IDEMPOTENT: ADD COLUMN IF NOT EXISTS.
-- ============================================================================

ALTER TABLE erp.invitations
    ADD COLUMN IF NOT EXISTS accepted_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS accepted_by UUID REFERENCES auth.users(id);
