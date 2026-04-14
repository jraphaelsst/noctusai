-- Therapy Platform: Invitations table (extended with invite_type)
-- Run in Supabase SQL Editor

CREATE TABLE IF NOT EXISTS therapy.invitations (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id UUID,                     -- NULL for platform-level invites
  clinic_id UUID,                  -- set for clinic-scoped invites
  email TEXT NOT NULL,
  role TEXT NOT NULL DEFAULT 'patient',
  invite_type TEXT NOT NULL DEFAULT 'platform_to_user'
    CHECK (invite_type IN (
      'platform_to_clinic',        -- admin invites a clinic
      'platform_to_user',          -- admin invites any user
      'clinic_to_therapist',       -- clinic admin invites therapist
      'clinic_to_patient',         -- clinic admin invites patient
      'therapist_to_patient',      -- therapist invites patient (bound)
      'therapist_to_therapist'     -- therapist invites colleague (no binding)
    )),
  invited_by UUID NOT NULL,
  bound_to UUID,                   -- therapist ID for therapist_to_patient binding
  token TEXT UNIQUE NOT NULL,
  status TEXT NOT NULL DEFAULT 'pending'
    CHECK (status IN ('pending', 'accepted', 'expired', 'canceled')),
  expires_at TIMESTAMPTZ NOT NULL DEFAULT (now() + interval '7 days'),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE therapy.invitations ENABLE ROW LEVEL SECURITY;

-- Platform admin sees all
CREATE POLICY "invitations_admin_all" ON therapy.invitations FOR SELECT TO authenticated
  USING (therapy.current_user_role() = 'platform_admin');

-- Clinic admin sees own clinic's invitations
CREATE POLICY "invitations_clinic_own" ON therapy.invitations FOR SELECT TO authenticated
  USING (
    therapy.current_user_role() = 'clinic_admin'
    AND clinic_id = therapy.current_clinic_id()
  );

-- Therapist sees invitations they sent
CREATE POLICY "invitations_therapist_own" ON therapy.invitations FOR SELECT TO authenticated
  USING (
    therapy.current_user_role() = 'therapist'
    AND invited_by = (SELECT auth.uid())
  );

CREATE INDEX idx_therapy_invitations_token ON therapy.invitations(token);
CREATE INDEX idx_therapy_invitations_clinic ON therapy.invitations(clinic_id);
CREATE INDEX idx_therapy_invitations_invited_by ON therapy.invitations(invited_by);
