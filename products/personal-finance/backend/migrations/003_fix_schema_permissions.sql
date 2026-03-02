-- =====================================================================
-- Fix: Grant schema permissions for "personal-finance"
--
-- The original migration (001) created tables and RLS policies but
-- forgot to grant USAGE on the schema and table permissions to the
-- PostgREST roles (anon, authenticated, service_role).
-- Without these grants, PostgREST returns:
--   42501 — permission denied for schema personal-finance
--
-- Run this in Supabase SQL Editor.
-- =====================================================================

-- 1. Schema usage
GRANT USAGE ON SCHEMA "personal-finance" TO postgres, anon, authenticated, service_role;

-- 2. Table permissions
GRANT ALL ON ALL TABLES IN SCHEMA "personal-finance" TO postgres, service_role;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA "personal-finance" TO anon, authenticated;

-- 3. Default privileges for future tables
ALTER DEFAULT PRIVILEGES IN SCHEMA "personal-finance" GRANT ALL ON TABLES TO postgres, service_role;
ALTER DEFAULT PRIVILEGES IN SCHEMA "personal-finance" GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO anon, authenticated;

-- 4. Sequences
GRANT USAGE ON ALL SEQUENCES IN SCHEMA "personal-finance" TO anon, authenticated, service_role;
ALTER DEFAULT PRIVILEGES IN SCHEMA "personal-finance" GRANT USAGE ON SEQUENCES TO anon, authenticated, service_role;

-- 5. Functions (triggers, etc.)
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA "personal-finance" TO anon, authenticated, service_role;
ALTER DEFAULT PRIVILEGES IN SCHEMA "personal-finance" GRANT EXECUTE ON FUNCTIONS TO anon, authenticated, service_role;
