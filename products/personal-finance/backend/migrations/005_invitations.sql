-- Personal Finance: Team invitations table
-- Run in Supabase SQL Editor

CREATE TABLE IF NOT EXISTS "personal-finance".invitations (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id UUID NOT NULL,
  email TEXT NOT NULL,
  role TEXT NOT NULL DEFAULT 'member',
  invited_by UUID NOT NULL,
  token TEXT UNIQUE NOT NULL,
  status TEXT NOT NULL DEFAULT 'pending'
    CHECK (status IN ('pending', 'accepted', 'expired', 'canceled')),
  expires_at TIMESTAMPTZ NOT NULL DEFAULT (now() + interval '7 days'),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE "personal-finance".invitations ENABLE ROW LEVEL SECURITY;

-- Org-scoped via user_org_id() helper
CREATE POLICY "invitations_select_own_org" ON "personal-finance".invitations FOR SELECT TO authenticated
  USING (org_id = "personal-finance".user_org_id());

CREATE INDEX idx_pf_invitations_org ON "personal-finance".invitations(org_id);
CREATE INDEX idx_pf_invitations_token ON "personal-finance".invitations(token);
