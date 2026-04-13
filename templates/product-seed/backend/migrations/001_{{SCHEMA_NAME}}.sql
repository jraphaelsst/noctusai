-- =====================================================================
-- 001 — {{PRODUCT_NAME}} Schema
-- Creates the '{{SCHEMA_NAME}}' schema with base tables, RLS, and indexes.
-- Run this in Supabase SQL Editor or via Supabase MCP.
-- =====================================================================

-- Create schema
CREATE SCHEMA IF NOT EXISTS {{SCHEMA_NAME}};

-- Grant access
GRANT USAGE ON SCHEMA {{SCHEMA_NAME}} TO anon, authenticated, service_role;
GRANT ALL ON ALL TABLES IN SCHEMA {{SCHEMA_NAME}} TO postgres, service_role;

-- Ensure PostgREST can see this schema
-- Go to Supabase Dashboard > Project Settings > API > Exposed schemas
-- Add '{{SCHEMA_NAME}}' to the list

-- -----------------------------------------------------------------
-- HELPER FUNCTIONS (for RLS)
-- -----------------------------------------------------------------

CREATE OR REPLACE FUNCTION {{SCHEMA_NAME}}.current_user_id()
RETURNS UUID LANGUAGE sql STABLE SECURITY DEFINER
SET search_path = {{SCHEMA_NAME}}, public
AS $$ SELECT (SELECT auth.uid()); $$;

CREATE OR REPLACE FUNCTION {{SCHEMA_NAME}}.current_org_id()
RETURNS UUID LANGUAGE sql STABLE SECURITY DEFINER
SET search_path = {{SCHEMA_NAME}}, public
AS $$ SELECT ((SELECT auth.jwt()) ->> 'org_id')::uuid; $$;

-- -----------------------------------------------------------------
-- UPDATED_AT TRIGGER FUNCTION
-- -----------------------------------------------------------------

CREATE OR REPLACE FUNCTION {{SCHEMA_NAME}}.set_updated_at()
RETURNS TRIGGER LANGUAGE plpgsql
SET search_path = {{SCHEMA_NAME}}, public
AS $$ BEGIN NEW.updated_at = now(); RETURN NEW; END; $$;

-- -----------------------------------------------------------------
-- TABLES — Add your product tables here
-- -----------------------------------------------------------------

-- Example table:
-- CREATE TABLE IF NOT EXISTS {{SCHEMA_NAME}}.items (
--     id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
--     org_id UUID NOT NULL,
--     nome TEXT NOT NULL,
--     descricao TEXT,
--     status TEXT NOT NULL DEFAULT 'ativo',
--     created_at TIMESTAMPTZ DEFAULT now(),
--     updated_at TIMESTAMPTZ DEFAULT now()
-- );
--
-- CREATE INDEX IF NOT EXISTS idx_items_org ON {{SCHEMA_NAME}}.items(org_id);
--
-- CREATE TRIGGER set_updated_at_items
--     BEFORE UPDATE ON {{SCHEMA_NAME}}.items
--     FOR EACH ROW EXECUTE FUNCTION {{SCHEMA_NAME}}.set_updated_at();
--
-- ALTER TABLE {{SCHEMA_NAME}}.items ENABLE ROW LEVEL SECURITY;
--
-- CREATE POLICY "service_role_bypass" ON {{SCHEMA_NAME}}.items
--     FOR ALL TO service_role USING (true) WITH CHECK (true);
--
-- CREATE POLICY "org_isolation" ON {{SCHEMA_NAME}}.items
--     FOR ALL TO authenticated
--     USING (org_id = (SELECT {{SCHEMA_NAME}}.current_org_id()));

-- -----------------------------------------------------------------
-- SEED PRODUCT RECORD (register in Core platform)
-- -----------------------------------------------------------------

INSERT INTO public.products (nome, slug, descricao, icone, url_base, cor, logout_behavior)
VALUES (
    '{{PRODUCT_NAME}}',
    '{{PRODUCT_SLUG}}',
    'Descricao do produto',
    '📦',
    'http://localhost:{{FRONTEND_PORT}}',
    '#6366f1',
    'redirect'
) ON CONFLICT (slug) DO NOTHING;

-- -----------------------------------------------------------------
-- GRANTS
-- -----------------------------------------------------------------

GRANT ALL ON ALL TABLES IN SCHEMA {{SCHEMA_NAME}} TO postgres, service_role;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA {{SCHEMA_NAME}} TO authenticated;
GRANT USAGE ON ALL SEQUENCES IN SCHEMA {{SCHEMA_NAME}} TO anon, authenticated, service_role;
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA {{SCHEMA_NAME}} TO anon, authenticated, service_role;
