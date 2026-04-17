-- ============================================================================
-- AdConnect schema
-- Schema: seed
-- Description: Minimal product schema that proves the entire shared stack works.
-- ============================================================================

CREATE SCHEMA IF NOT EXISTS seed;

-- Grant usage to authenticated users (required for PostgREST)
GRANT USAGE ON SCHEMA seed TO anon, authenticated, service_role;
GRANT ALL ON ALL TABLES IN SCHEMA seed TO anon, authenticated, service_role;
GRANT ALL ON ALL SEQUENCES IN SCHEMA seed TO anon, authenticated, service_role;
ALTER DEFAULT PRIVILEGES IN SCHEMA seed GRANT ALL ON TABLES TO anon, authenticated, service_role;
ALTER DEFAULT PRIVILEGES IN SCHEMA seed GRANT ALL ON SEQUENCES TO anon, authenticated, service_role;


-- ============================================================================
-- Page status (feature flags)
-- ============================================================================

CREATE TABLE seed.status_pagina (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    nome_pagina TEXT NOT NULL UNIQUE,
    status TEXT NOT NULL DEFAULT 'producao' CHECK (status IN ('producao', 'desenvolvimento', 'desativado')),
    descricao TEXT,
    created_at TIMESTAMPTZ DEFAULT now()
);

ALTER TABLE seed.status_pagina ENABLE ROW LEVEL SECURITY;

CREATE POLICY "todos_veem_producao" ON seed.status_pagina
    FOR SELECT USING (status = 'producao');


-- ============================================================================
-- Invitations
-- ============================================================================

CREATE TABLE seed.invitations (
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

ALTER TABLE seed.invitations ENABLE ROW LEVEL SECURITY;

CREATE POLICY "invitations_select_own_org" ON seed.invitations
    FOR SELECT TO authenticated
    USING (org_id = ((SELECT auth.jwt()) ->> 'org_id')::uuid);

CREATE INDEX idx_seed_invitations_org ON seed.invitations(org_id);
CREATE INDEX idx_seed_invitations_token ON seed.invitations(token);


-- ============================================================================
-- Seed pages
-- ============================================================================

INSERT INTO seed.status_pagina (nome_pagina, status) VALUES
    ('dashboard', 'producao'),
    ('equipe', 'producao')
ON CONFLICT (nome_pagina) DO NOTHING;
