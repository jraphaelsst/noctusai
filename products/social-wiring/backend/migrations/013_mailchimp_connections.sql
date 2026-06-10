-- 013_mailchimp_connections.sql — per-org Mailchimp connection (single row per org).
--
-- Stores an encrypted Mailchimp API key + resolved server_prefix + audience_id
-- per-org. The key is Fernet-encrypted at rest (TEXT, not bytea — avoids the
-- PostgREST \x-hex read trap by construction; mirrors 004_whatsapp_connections.sql).
--
-- RLS: authenticated user reads via public.current_org_id() (defined in
-- migration 011); service_role ALL (backend writes through admin client).
-- PREREQUISITE: public.current_org_id() defined in 011_rls_current_org_id.sql.
--
-- status_pagina inserts: the nav gates items by status; these rows make the
-- Mailchimp pages visible. ON CONFLICT DO NOTHING for idempotency.

SET search_path = social_wiring, public;

CREATE TABLE IF NOT EXISTS social_wiring.mailchimp_connections (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id            UUID NOT NULL UNIQUE,            -- one connection per org
    encrypted_api_key TEXT NOT NULL,                   -- Fernet(api_key) — TEXT not bytea
    server_prefix     TEXT NOT NULL,                   -- e.g. "us6" parsed from key suffix
    audience_id       TEXT,                            -- selected default audience
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE social_wiring.mailchimp_connections ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "mailchimp_connections_select_own_org" ON social_wiring.mailchimp_connections;
CREATE POLICY "mailchimp_connections_select_own_org" ON social_wiring.mailchimp_connections
    FOR SELECT TO authenticated
    USING (org_id = public.current_org_id());

DROP POLICY IF EXISTS "mailchimp_connections_service_role" ON social_wiring.mailchimp_connections;
CREATE POLICY "mailchimp_connections_service_role" ON social_wiring.mailchimp_connections
    FOR ALL TO service_role USING (true) WITH CHECK (true);

CREATE INDEX IF NOT EXISTS idx_sw_mailchimp_connections_org_id
    ON social_wiring.mailchimp_connections(org_id);

-- ── Nav: register the Mailchimp pages so they appear in the sidebar ──────────
-- The nav gates items by status_pagina (unlisted route ⇒ hidden).
INSERT INTO social_wiring.status_pagina (nome_pagina, status) VALUES
    ('contatos',           'producao'),
    ('email_listas',       'producao'),
    ('email_templates',    'producao'),
    ('email_campanhas',    'producao'),
    ('email_config',       'producao')
ON CONFLICT (nome_pagina) DO NOTHING;
