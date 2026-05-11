-- Mailing: add accepted_at + accepted_by to invitations
-- Lockstep with noctusai_lib.domain.invitations.accept_invitation kwarg
-- (Phase 2 of seed-team-router-accept-real-adapter, 2026-05-11).

ALTER TABLE mailing.invitations
    ADD COLUMN IF NOT EXISTS accepted_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS accepted_by UUID REFERENCES auth.users(id);
