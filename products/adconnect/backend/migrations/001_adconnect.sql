-- ============================================================================
-- AdConnect schema
-- Schema: adconnect
-- Description: Framework tables (page status + invitations) for the AdConnect
--              B2B marketplace product. Domain tables (products, orders, cart,
--              rewards, sellout, financial, distributors) land in subsequent
--              numbered migrations as the implementation project ships them.
--
-- Future migrations should use the canonical helpers from
-- `noctusai_lib.domain.sql_templates` (set_search_path, updated_at_function,
-- updated_at_trigger, rls_subquery_policy) so the conventions cannot drift.
-- ============================================================================

SET search_path = adconnect, public;

CREATE SCHEMA IF NOT EXISTS adconnect;

-- Grant usage to authenticated users (required for PostgREST)
GRANT USAGE ON SCHEMA adconnect TO anon, authenticated, service_role;
GRANT ALL ON ALL TABLES IN SCHEMA adconnect TO anon, authenticated, service_role;
GRANT ALL ON ALL SEQUENCES IN SCHEMA adconnect TO anon, authenticated, service_role;
ALTER DEFAULT PRIVILEGES IN SCHEMA adconnect GRANT ALL ON TABLES TO anon, authenticated, service_role;
ALTER DEFAULT PRIVILEGES IN SCHEMA adconnect GRANT ALL ON SEQUENCES TO anon, authenticated, service_role;


-- ============================================================================
-- Page status (feature flags)
-- ============================================================================

CREATE TABLE adconnect.status_pagina (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    nome_pagina TEXT NOT NULL UNIQUE,
    status TEXT NOT NULL DEFAULT 'producao' CHECK (status IN ('producao', 'desenvolvimento', 'desativado')),
    descricao TEXT,
    created_at TIMESTAMPTZ DEFAULT now()
);

ALTER TABLE adconnect.status_pagina ENABLE ROW LEVEL SECURITY;

-- Anonymous-readable policy (anon role too) — does not use rls_subquery_policy
-- helper which always emits `TO authenticated`.
CREATE POLICY "todos_veem_producao" ON adconnect.status_pagina
    FOR SELECT USING (status = 'producao');


-- ============================================================================
-- Invitations
-- ============================================================================

CREATE TABLE adconnect.invitations (
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

ALTER TABLE adconnect.invitations ENABLE ROW LEVEL SECURITY;

CREATE POLICY "invitations_select_own_org" ON adconnect.invitations
    FOR SELECT TO authenticated
    USING (org_id = ((SELECT auth.jwt()) ->> 'org_id')::uuid);

CREATE INDEX idx_adconnect_invitations_org ON adconnect.invitations(org_id);
CREATE INDEX idx_adconnect_invitations_token ON adconnect.invitations(token);


-- ============================================================================
-- Seed pages
-- ============================================================================

INSERT INTO adconnect.status_pagina (nome_pagina, status) VALUES
    ('dashboard', 'producao'),
    ('equipe', 'producao')
ON CONFLICT (nome_pagina) DO NOTHING;
