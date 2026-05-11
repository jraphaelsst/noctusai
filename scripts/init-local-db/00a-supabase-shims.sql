-- ============================================================================
-- 00a-supabase-shims.sql — minimal Supabase-emulating primitives.
--
-- Why this exists. Every product's `001_<slug>.sql` migration was authored
-- against a Supabase project, which ships these primitives out of the box:
--   - roles: `anon`, `authenticated`, `service_role`
--   - schema: `auth` with helper functions `auth.jwt()`, `auth.uid()`,
--             `auth.role()`
--   - schema: `extensions` (some Supabase projects install vector / pg_cron
--             / pg_net here)
--   - schema: `storage` (referenced indirectly by RLS policies)
--
-- Plain `postgres:16-alpine` has none of these — applying a product
-- migration straight away fails with `role "authenticated" does not exist`
-- or `schema "auth" does not exist`.
--
-- This file installs the **minimal stubs** required so migrations apply
-- cleanly. The stubs are NO-OP: `auth.jwt()` returns NULL, so any RLS
-- policy that compares `auth.jwt()->>'org_id'` evaluates to FALSE. That's
-- the right default for offline-dev — local Postgres has no JWT issuer.
-- For end-to-end testing with multi-tenant data, set `request.jwt.claims`
-- explicitly via `SET LOCAL request.jwt.claims = '{...}'` per session, or
-- bypass RLS by connecting as `noctus` (the POSTGRES_USER — superuser).
--
-- This file is run FIRST after 00-extensions.sql by virtue of the `00a`
-- alphabetical prefix.
-- ============================================================================

-- ─── Supabase roles (NOLOGIN — used only for GRANT/RLS targeting) ───────────
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
    CREATE ROLE anon NOLOGIN;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
    CREATE ROLE authenticated NOLOGIN;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'service_role') THEN
    CREATE ROLE service_role NOLOGIN BYPASSRLS;
  END IF;
END
$$;

-- ─── auth schema + helper functions ─────────────────────────────────────────
CREATE SCHEMA IF NOT EXISTS auth;

-- auth.jwt() — Supabase returns the current request's JWT payload as jsonb.
-- For local Postgres, return the `request.jwt.claims` GUC if set, else NULL.
-- RLS policies comparing `auth.jwt()->>'org_id'` to a column thus evaluate
-- to NULL = NULL = FALSE under default settings. Tests can SET LOCAL the
-- GUC to simulate a logged-in user.
CREATE OR REPLACE FUNCTION auth.jwt() RETURNS jsonb
LANGUAGE sql STABLE AS $$
  SELECT NULLIF(current_setting('request.jwt.claims', true), '')::jsonb;
$$;

-- auth.uid() — Supabase returns the `sub` claim of the JWT as uuid.
CREATE OR REPLACE FUNCTION auth.uid() RETURNS uuid
LANGUAGE sql STABLE AS $$
  SELECT NULLIF(current_setting('request.jwt.claim.sub', true), '')::uuid;
$$;

-- auth.role() — Supabase returns the current role (`anon` / `authenticated`).
CREATE OR REPLACE FUNCTION auth.role() RETURNS text
LANGUAGE sql STABLE AS $$
  SELECT COALESCE(NULLIF(current_setting('request.jwt.claim.role', true), ''), 'anon');
$$;

-- auth.email() — Supabase convenience; rarely used in our migrations but
-- harmless to expose.
CREATE OR REPLACE FUNCTION auth.email() RETURNS text
LANGUAGE sql STABLE AS $$
  SELECT NULLIF(current_setting('request.jwt.claim.email', true), '');
$$;

GRANT USAGE ON SCHEMA auth TO anon, authenticated, service_role;
GRANT EXECUTE ON FUNCTION auth.jwt() TO anon, authenticated, service_role;
GRANT EXECUTE ON FUNCTION auth.uid() TO anon, authenticated, service_role;
GRANT EXECUTE ON FUNCTION auth.role() TO anon, authenticated, service_role;
GRANT EXECUTE ON FUNCTION auth.email() TO anon, authenticated, service_role;

-- ─── extensions schema (Supabase installs some contrib extensions here) ─────
-- Some product migrations do `CREATE EXTENSION ... WITH SCHEMA extensions`.
-- The schema needs to exist; the extensions themselves we install when they
-- actually exist for postgres:16-alpine (pg_cron / pg_net / vector are NOT
-- in the alpine image; product migrations referencing them will fail and
-- that's OK — those are best-effort offline. Most products don't reference
-- them.)
CREATE SCHEMA IF NOT EXISTS extensions;
GRANT USAGE ON SCHEMA extensions TO anon, authenticated, service_role;

-- ─── storage schema (placeholder — RLS policies sometimes reference it) ─────
CREATE SCHEMA IF NOT EXISTS storage;
GRANT USAGE ON SCHEMA storage TO anon, authenticated, service_role;

-- ─── cron schema + no-op schedule() (pg_cron not in alpine image) ───────────
-- Some product migrations call `cron.schedule('job', '...', 'SQL')` to
-- register periodic jobs (Supabase ships pg_cron). The alpine image
-- doesn't bundle pg_cron, so we expose a no-op stub that records the
-- intent in a local table — visible to inspection but never actually
-- fired. Real cron scheduling is out of scope for offline-dev; production
-- still uses Supabase pg_cron.
CREATE SCHEMA IF NOT EXISTS cron;
GRANT USAGE ON SCHEMA cron TO anon, authenticated, service_role;

CREATE TABLE IF NOT EXISTS cron._stub_scheduled_jobs (
    jobname TEXT PRIMARY KEY,
    schedule TEXT NOT NULL,
    command TEXT NOT NULL,
    registered_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE OR REPLACE FUNCTION cron.schedule(p_jobname TEXT, p_schedule TEXT, p_command TEXT)
RETURNS BIGINT
LANGUAGE plpgsql AS $$
BEGIN
  INSERT INTO cron._stub_scheduled_jobs(jobname, schedule, command)
  VALUES (p_jobname, p_schedule, p_command)
  ON CONFLICT (jobname) DO UPDATE
    SET schedule = EXCLUDED.schedule, command = EXCLUDED.command;
  -- Return value mirrors pg_cron's INTEGER job id; here we return a stable
  -- hash of jobname so the caller's expectation (numeric job id) is met.
  RETURN abs(hashtext(p_jobname))::BIGINT;
END;
$$;

CREATE OR REPLACE FUNCTION cron.unschedule(p_jobname TEXT)
RETURNS BOOLEAN
LANGUAGE plpgsql AS $$
BEGIN
  DELETE FROM cron._stub_scheduled_jobs WHERE jobname = p_jobname;
  RETURN FOUND;
END;
$$;

GRANT EXECUTE ON FUNCTION cron.schedule(TEXT, TEXT, TEXT) TO anon, authenticated, service_role;
GRANT EXECUTE ON FUNCTION cron.unschedule(TEXT) TO anon, authenticated, service_role;

-- ─── postgres role (some migrations GRANT to it) ────────────────────────────
-- Supabase's `postgres` superuser role. Local image uses `noctus` as the
-- POSTGRES_USER; provide a NOLOGIN role of the same name so `GRANT ... TO
-- postgres` statements succeed.
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'postgres') THEN
    CREATE ROLE postgres NOLOGIN;
  END IF;
END
$$;

-- ─── auth.users table shim ──────────────────────────────────────────────────
-- Some migrations declare FK constraints against `auth.users(id)`. Create a
-- minimal table so the references resolve. Empty by default; tests can
-- INSERT directly when they need to simulate a logged-in user.
CREATE TABLE IF NOT EXISTS auth.users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
GRANT SELECT ON auth.users TO anon, authenticated, service_role;
