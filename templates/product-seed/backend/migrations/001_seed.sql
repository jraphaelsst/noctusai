-- ============================================================================
-- {{PRODUCT_NAME}} schema
-- Schema: {{SCHEMA_NAME}}
-- Description: Minimal product schema that proves the entire shared stack works.
--
-- Future migrations should use the canonical helpers from
-- `noctusai_lib.domain.sql_templates` (set_search_path, updated_at_function,
-- updated_at_trigger, rls_subquery_policy) so the conventions cannot drift.
-- ============================================================================

SET search_path = {{SCHEMA_NAME}}, public;

CREATE SCHEMA IF NOT EXISTS {{SCHEMA_NAME}};

-- Grant usage to authenticated users (required for PostgREST)
GRANT USAGE ON SCHEMA {{SCHEMA_NAME}} TO anon, authenticated, service_role;
GRANT ALL ON ALL TABLES IN SCHEMA {{SCHEMA_NAME}} TO anon, authenticated, service_role;
GRANT ALL ON ALL SEQUENCES IN SCHEMA {{SCHEMA_NAME}} TO anon, authenticated, service_role;
ALTER DEFAULT PRIVILEGES IN SCHEMA {{SCHEMA_NAME}} GRANT ALL ON TABLES TO anon, authenticated, service_role;
ALTER DEFAULT PRIVILEGES IN SCHEMA {{SCHEMA_NAME}} GRANT ALL ON SEQUENCES TO anon, authenticated, service_role;


-- ============================================================================
-- current_org_id() — SECURITY DEFINER org resolver (prerequisite for RLS)
--
-- Must be declared before any RLS policy that calls it. Using
-- auth.jwt() ->> 'org_id' (top-level) is always NULL in Supabase because
-- org_id lives under user_metadata. Using user_metadata directly is a
-- privilege-escalation hole (user-editable, Supabase advisor ERROR).
-- This SECURITY DEFINER function reads from the trusted noctus_users table.
-- Codified by 011_rls_current_org_id.sql on 2026-06-02.
-- ============================================================================
CREATE OR REPLACE FUNCTION public.current_org_id()
  RETURNS uuid
  LANGUAGE sql
  STABLE SECURITY DEFINER
  SET search_path TO 'public'
AS $f$
  SELECT org_id FROM public.noctus_users WHERE id = (SELECT auth.uid());
$f$;


-- ============================================================================
-- Page status (feature flags)
-- ============================================================================

CREATE TABLE {{SCHEMA_NAME}}.status_pagina (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    nome_pagina TEXT NOT NULL UNIQUE,
    status TEXT NOT NULL DEFAULT 'producao' CHECK (status IN ('producao', 'desenvolvimento', 'desativado')),
    descricao TEXT,
    created_at TIMESTAMPTZ DEFAULT now()
);

ALTER TABLE {{SCHEMA_NAME}}.status_pagina ENABLE ROW LEVEL SECURITY;

-- Note: this policy intentionally does NOT use `rls_subquery_policy` — that
-- helper always emits `TO authenticated`, but `todos_veem_producao` is an
-- anonymous-readable policy (anon role too).
CREATE POLICY "todos_veem_producao" ON {{SCHEMA_NAME}}.status_pagina
    FOR SELECT USING (status = 'producao');


-- ============================================================================
-- Invitations
-- ============================================================================

CREATE TABLE {{SCHEMA_NAME}}.invitations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL,
    email TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'member',
    invited_by UUID NOT NULL,
    token TEXT UNIQUE NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'accepted', 'expired', 'canceled')),
    expires_at TIMESTAMPTZ NOT NULL DEFAULT (now() + interval '7 days'),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE {{SCHEMA_NAME}}.invitations ENABLE ROW LEVEL SECURITY;

-- Uses public.current_org_id() — the SECURITY DEFINER trusted-table resolver.
-- NOTE: the scaffold regression test in test_scaffold.py was updated in the
-- same commit (011_rls_current_org_id) to assert current_org_id() instead
-- of the old jwt()-based form.
CREATE POLICY "invitations_select_own_org" ON {{SCHEMA_NAME}}.invitations
    FOR SELECT TO authenticated
    USING (org_id = current_org_id());

CREATE INDEX idx_{{SCHEMA_NAME}}_invitations_org ON {{SCHEMA_NAME}}.invitations(org_id);
CREATE INDEX idx_{{SCHEMA_NAME}}_invitations_token ON {{SCHEMA_NAME}}.invitations(token);


-- ============================================================================
-- Seed pages
-- ============================================================================

INSERT INTO {{SCHEMA_NAME}}.status_pagina (nome_pagina, status) VALUES
    ('dashboard', 'producao'),
    ('equipe', 'producao')
ON CONFLICT (nome_pagina) DO NOTHING;
