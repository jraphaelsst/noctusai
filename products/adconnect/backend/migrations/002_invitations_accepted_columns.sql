-- AdConnect: add accepted_at + accepted_by to invitations
-- Lockstep with noctusai_lib.domain.invitations.accept_invitation kwarg
-- (Phase 2 of seed-team-router-accept-real-adapter, 2026-05-11).
--
-- The seed router currently invokes accept_invitation without accepted_by
-- (no authenticated-user context on POST /api/team/accept), so the
-- domain helper writes only `status="accepted"`. These columns are
-- forward-compatible — populated once the user-context elevation
-- follow-up (`seed-team-router-user-creation-seam`) lands.

ALTER TABLE adconnect.invitations
    ADD COLUMN IF NOT EXISTS accepted_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS accepted_by UUID REFERENCES auth.users(id);
