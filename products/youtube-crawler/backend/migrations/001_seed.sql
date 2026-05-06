-- ============================================================================
-- YouTube Crawler schema
-- Schema: youtube_crawler
-- Description: Minimal product schema that proves the entire shared stack works.
--
-- Future migrations should use the canonical helpers from
-- `noctusai_lib.domain.sql_templates` (set_search_path, updated_at_function,
-- updated_at_trigger, rls_subquery_policy) so the conventions cannot drift.
-- ============================================================================

SET search_path = youtube_crawler, public;

CREATE SCHEMA IF NOT EXISTS youtube_crawler;

-- Grant usage to authenticated users (required for PostgREST)
GRANT USAGE ON SCHEMA youtube_crawler TO anon, authenticated, service_role;
GRANT ALL ON ALL TABLES IN SCHEMA youtube_crawler TO anon, authenticated, service_role;
GRANT ALL ON ALL SEQUENCES IN SCHEMA youtube_crawler TO anon, authenticated, service_role;
ALTER DEFAULT PRIVILEGES IN SCHEMA youtube_crawler GRANT ALL ON TABLES TO anon, authenticated, service_role;
ALTER DEFAULT PRIVILEGES IN SCHEMA youtube_crawler GRANT ALL ON SEQUENCES TO anon, authenticated, service_role;


-- ============================================================================
-- Page status (feature flags)
-- ============================================================================

CREATE TABLE youtube_crawler.status_pagina (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    nome_pagina TEXT NOT NULL UNIQUE,
    status TEXT NOT NULL DEFAULT 'producao' CHECK (status IN ('producao', 'desenvolvimento', 'desativado')),
    descricao TEXT,
    created_at TIMESTAMPTZ DEFAULT now()
);

ALTER TABLE youtube_crawler.status_pagina ENABLE ROW LEVEL SECURITY;

-- Note: this policy intentionally does NOT use `rls_subquery_policy` — that
-- helper always emits `TO authenticated`, but `todos_veem_producao` is an
-- anonymous-readable policy (anon role too).
CREATE POLICY "todos_veem_producao" ON youtube_crawler.status_pagina
    FOR SELECT USING (status = 'producao');


-- ============================================================================
-- Invitations
-- ============================================================================

CREATE TABLE youtube_crawler.invitations (
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

ALTER TABLE youtube_crawler.invitations ENABLE ROW LEVEL SECURITY;

-- Matches `rls_subquery_policy(youtube_crawler, "invitations", "invitations_select_own_org",
--   "SELECT", using="org_id = ((SELECT auth.jwt()) ->> 'org_id')::uuid")`
-- output (whitespace-normalized). The scaffold's regression test enforces this.
CREATE POLICY "invitations_select_own_org" ON youtube_crawler.invitations
    FOR SELECT TO authenticated
    USING (org_id = ((SELECT auth.jwt()) ->> 'org_id')::uuid);

CREATE INDEX idx_youtube_crawler_invitations_org ON youtube_crawler.invitations(org_id);
CREATE INDEX idx_youtube_crawler_invitations_token ON youtube_crawler.invitations(token);


-- ============================================================================
-- Seed pages
-- ============================================================================

INSERT INTO youtube_crawler.status_pagina (nome_pagina, status) VALUES
    ('dashboard', 'producao'),
    ('equipe', 'producao')
ON CONFLICT (nome_pagina) DO NOTHING;
