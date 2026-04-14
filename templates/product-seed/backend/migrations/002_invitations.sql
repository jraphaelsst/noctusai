-- {{PRODUCT_NAME}}: Team invitations table
-- Run in Supabase SQL Editor

CREATE TABLE IF NOT EXISTS {{SCHEMA_NAME}}.invitations (
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

ALTER TABLE {{SCHEMA_NAME}}.invitations ENABLE ROW LEVEL SECURITY;

-- Org-scoped: users see only their org's invitations
CREATE POLICY "invitations_select_own_org" ON {{SCHEMA_NAME}}.invitations FOR SELECT TO authenticated
  USING (org_id = ((SELECT auth.jwt()) ->> 'org_id')::uuid);

CREATE INDEX idx_{{SCHEMA_NAME}}_invitations_org ON {{SCHEMA_NAME}}.invitations(org_id);
CREATE INDEX idx_{{SCHEMA_NAME}}_invitations_token ON {{SCHEMA_NAME}}.invitations(token);
