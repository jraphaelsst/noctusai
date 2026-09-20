-- ============================================================================
-- {{PRODUCT_NAME}} schema
-- Schema: seed
-- Description: Minimal product schema that proves the entire shared stack works.
--
-- Future migrations should use the canonical helpers from
-- `noctusai_lib.domain.sql_templates` (set_search_path, updated_at_function,
-- updated_at_trigger, rls_subquery_policy) so the conventions cannot drift.
-- ============================================================================

SET search_path = {{SCHEMA_NAME}}, public;

CREATE SCHEMA IF NOT EXISTS {{SCHEMA_NAME}};

-- ============================================================================
-- Grants — `anon` gets schema USAGE only, NEVER a blanket table grant
--
-- 🔴 2026-09-20 incident: this exact migration used to read
-- `GRANT ALL ON ALL TABLES IN SCHEMA seed TO anon, authenticated, service_role`
-- + the matching `ALTER DEFAULT PRIVILEGES ... GRANT ALL ... TO anon, ...`.
-- Propagated verbatim (via templates/product-seed/) into 9 product schemas,
-- it let the unauthenticated `anon` PostgREST role read AND write every
-- table in every one of those schemas by default. In the live
-- `social_wiring` schema that default let `anon` read+write 4 out-of-band
-- backup tables (`_leads_backup_20260902` + 3 siblings — 21,567 rows of
-- names/emails/birthdates) that were never routed through any RLS policy at
-- all. RLS is the ROW-level gate; the GRANT is the TABLE-level gate that
-- must exist BEFORE RLS is even consulted — a table with no RLS policy yet
-- (or created out-of-band, like the backups) is fully exposed to any role
-- the schema-wide grant names.
--
-- The fix: `anon` gets USAGE on the schema (routing only, required by
-- PostgREST) and NOTHING at the table level by default. `service_role` gets
-- ALL — it's the trusted server-side role and already bypasses RLS.
-- `authenticated` gets SELECT/INSERT/UPDATE/DELETE — real signed-in users,
-- gated per table by RLS. A table that genuinely needs anonymous access
-- (see `status_pagina` below) re-grants it EXPLICITLY, per table, with a
-- comment saying why — never by widening this schema-wide default again.
-- Enforced going forward by the `check_schema_wide_anon_grant` keeper.
GRANT USAGE ON SCHEMA {{SCHEMA_NAME}} TO anon, authenticated, service_role;

GRANT ALL ON ALL TABLES IN SCHEMA {{SCHEMA_NAME}} TO service_role;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA {{SCHEMA_NAME}} TO authenticated;
ALTER DEFAULT PRIVILEGES IN SCHEMA {{SCHEMA_NAME}} GRANT ALL ON TABLES TO service_role;
ALTER DEFAULT PRIVILEGES IN SCHEMA {{SCHEMA_NAME}} GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO authenticated;

-- Sequences are out of scope for this lockdown (no data, just nextval/
-- currval) — left as the pre-existing broader grant.
GRANT ALL ON ALL SEQUENCES IN SCHEMA {{SCHEMA_NAME}} TO anon, authenticated, service_role;
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

-- `anon` has no blanket table grant any more (see the schema-wide grants
-- above) — the policy above only decides which ROWS a role may see; a role
-- still needs a TABLE-level grant before RLS is even consulted. Page
-- visibility flags (name + status) are not sensitive, so this is a safe,
-- explicit, per-table exception.
GRANT SELECT ON {{SCHEMA_NAME}}.status_pagina TO anon;


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
