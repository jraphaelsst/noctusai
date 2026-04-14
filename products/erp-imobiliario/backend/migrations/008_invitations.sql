-- ERP Imobiliario: Team invitations table
-- Run in Supabase SQL Editor

CREATE TABLE IF NOT EXISTS erp.invitations (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id UUID NOT NULL,
  email TEXT NOT NULL,
  role TEXT NOT NULL DEFAULT 'corretor',
  invited_by UUID NOT NULL,
  token TEXT UNIQUE NOT NULL,
  status TEXT NOT NULL DEFAULT 'pending'
    CHECK (status IN ('pending', 'accepted', 'expired', 'canceled')),
  expires_at TIMESTAMPTZ NOT NULL DEFAULT (now() + interval '7 days'),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE erp.invitations ENABLE ROW LEVEL SECURITY;

-- Org-scoped: users see only their org's invitations
CREATE POLICY "invitations_select_own_org" ON erp.invitations FOR SELECT TO authenticated
  USING (org_id = ((SELECT auth.jwt()) ->> 'org_id')::uuid);

-- Admin-only management (insert/update/delete via service role)

CREATE INDEX idx_erp_invitations_org ON erp.invitations(org_id);
CREATE INDEX idx_erp_invitations_token ON erp.invitations(token);
CREATE INDEX idx_erp_invitations_email_status ON erp.invitations(email, status);
