-- ============================================================
-- Schema lock — pin name resolution to social_wiring, public
-- WHY:
--   * RLS isolation: every product's tables live in its own
--     schema; un-locked search_path leaks resolution to
--     whatever the caller's session set.
--   * Cross-product safety: prevents accidental shadowing
--     when two products define identically-named helpers
--     (e.g. `current_org_id()`) in different schemas.
-- IDEMPOTENT: session-level setting; no DDL emitted.
-- ============================================================
SET search_path = social_wiring, public;

CREATE SCHEMA IF NOT EXISTS social_wiring;

-- Grant usage to authenticated users (required for PostgREST)
GRANT USAGE ON SCHEMA social_wiring TO anon, authenticated, service_role;
GRANT ALL ON ALL TABLES IN SCHEMA social_wiring TO anon, authenticated, service_role;
GRANT ALL ON ALL SEQUENCES IN SCHEMA social_wiring TO anon, authenticated, service_role;
ALTER DEFAULT PRIVILEGES IN SCHEMA social_wiring GRANT ALL ON TABLES TO anon, authenticated, service_role;
ALTER DEFAULT PRIVILEGES IN SCHEMA social_wiring GRANT ALL ON SEQUENCES TO anon, authenticated, service_role;


-- ============================================================================
-- Page status (feature flags)
-- ============================================================================

CREATE TABLE social_wiring.status_pagina (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    nome_pagina TEXT NOT NULL UNIQUE,
    status TEXT NOT NULL DEFAULT 'producao' CHECK (status IN ('producao', 'desenvolvimento', 'desativado')),
    descricao TEXT,
    created_at TIMESTAMPTZ DEFAULT now()
);

ALTER TABLE social_wiring.status_pagina ENABLE ROW LEVEL SECURITY;

-- Note: this policy intentionally does NOT use `rls_subquery_policy` — that
-- helper always emits `TO authenticated`, but `todos_veem_producao` is an
-- anonymous-readable policy (anon role too).
CREATE POLICY "todos_veem_producao" ON social_wiring.status_pagina
    FOR SELECT USING (status = 'producao');


-- ============================================================================
-- Invitations
-- ============================================================================

CREATE TABLE social_wiring.invitations (
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

ALTER TABLE social_wiring.invitations ENABLE ROW LEVEL SECURITY;

-- Matches `rls_subquery_policy(social_wiring, "invitations", "invitations_select_own_org",
--   "SELECT", using="org_id = ((SELECT auth.jwt()) ->> 'org_id')::uuid")`
-- output (whitespace-normalized). The scaffold's regression test enforces this.
CREATE POLICY "invitations_select_own_org" ON social_wiring.invitations
    FOR SELECT TO authenticated
    USING (org_id = ((SELECT auth.jwt()) ->> 'org_id')::uuid);

CREATE INDEX idx_social_wiring_invitations_org ON social_wiring.invitations(org_id);
CREATE INDEX idx_social_wiring_invitations_token ON social_wiring.invitations(token);


-- ============================================================================
-- Seed pages
-- ============================================================================

INSERT INTO social_wiring.status_pagina (nome_pagina, status) VALUES
    ('dashboard', 'producao'),
    ('equipe', 'producao')
ON CONFLICT (nome_pagina) DO NOTHING;
