-- noctus.dev.migration_replay — Supabase platform-surface stubs · STUBS_VERSION 1 (2026-10-10)
--
-- Loaded into a FRESH PGlite (PG16/WASM) before any product chain replays. Each block
-- mirrors ONE surface that Supabase provides outside our migrations; a stub exists
-- only so the chain can reference it — it is NOT a behavioural model (no JWT
-- verification, no storage IO, no cron scheduling, no HTTP). Bump STUBS_VERSION on
-- any change; the measurement behind this set: KB § PATTERNS/backend/migration-chain-replay.md.

-- [roles] Supabase's API roles (PostgREST anon/authenticated, service key bypassing RLS)
-- and the internal admin roles migrations GRANT to.
DO $$ BEGIN
  CREATE ROLE anon NOLOGIN;
  CREATE ROLE authenticated NOLOGIN;
  CREATE ROLE service_role NOLOGIN BYPASSRLS;
  CREATE ROLE authenticator NOLOGIN;
  CREATE ROLE supabase_admin NOLOGIN;
  CREATE ROLE supabase_auth_admin NOLOGIN;
  CREATE ROLE supabase_storage_admin NOLOGIN;
  CREATE ROLE dashboard_user NOLOGIN;
END $$;

-- [extensions schema] Supabase installs extensions into `extensions`.
CREATE SCHEMA extensions;
-- [pgvector] Supabase `vector` lives in `extensions`; PGlite ships the real pgvector.
CREATE EXTENSION IF NOT EXISTS vector WITH SCHEMA extensions;
-- [pgcrypto] PGlite 0.2.17 has no pgcrypto: gen_random_bytes shape only, NOT crypto-grade.
CREATE FUNCTION extensions.gen_random_bytes(n integer) RETURNS bytea LANGUAGE sql VOLATILE AS $$
  SELECT substring(decode(string_agg(replace(gen_random_uuid()::text, '-', ''), ''), 'hex') FROM 1 FOR n)
  FROM generate_series(1, (n + 15) / 16) $$;
-- [pg_trgm] deliberately NOT pre-installed: chains `CREATE EXTENSION pg_trgm` themselves
-- and use gin_trgm_ops unqualified; PGlite provides the real contrib module.

-- [auth] GoTrue's schema: the users/identities tables FKs point at, and the JWT helpers
-- RLS policies call. Claims come from the request.jwt.claim* GUCs, as on Supabase.
CREATE SCHEMA auth;
CREATE TABLE auth.users (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(), email text, phone text,
  raw_user_meta_data jsonb DEFAULT '{}', raw_app_meta_data jsonb DEFAULT '{}',
  created_at timestamptz DEFAULT now(), updated_at timestamptz DEFAULT now(),
  last_sign_in_at timestamptz, email_confirmed_at timestamptz, deleted_at timestamptz,
  is_anonymous boolean DEFAULT false, aud text, role text);
CREATE TABLE auth.identities (id uuid PRIMARY KEY DEFAULT gen_random_uuid(), user_id uuid, provider text, identity_data jsonb);
CREATE FUNCTION auth.uid() RETURNS uuid LANGUAGE sql STABLE AS $$ SELECT nullif(current_setting('request.jwt.claim.sub', true), '')::uuid $$;
CREATE FUNCTION auth.role() RETURNS text LANGUAGE sql STABLE AS $$ SELECT nullif(current_setting('request.jwt.claim.role', true), '') $$;
CREATE FUNCTION auth.email() RETURNS text LANGUAGE sql STABLE AS $$ SELECT nullif(current_setting('request.jwt.claim.email', true), '') $$;
CREATE FUNCTION auth.jwt() RETURNS jsonb LANGUAGE sql STABLE AS $$ SELECT coalesce(nullif(current_setting('request.jwt.claims', true), ''), '{}')::jsonb $$;

-- [storage] Supabase Storage's catalog tables (bucket rows + RLS'd objects) and the
-- path helpers storage policies call.
CREATE SCHEMA storage;
CREATE TABLE storage.buckets (
  id text PRIMARY KEY, name text, owner uuid, public boolean DEFAULT false,
  file_size_limit bigint, allowed_mime_types text[],
  created_at timestamptz DEFAULT now(), updated_at timestamptz DEFAULT now());
CREATE TABLE storage.objects (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(), bucket_id text REFERENCES storage.buckets(id),
  name text, owner uuid, metadata jsonb, created_at timestamptz DEFAULT now(), updated_at timestamptz DEFAULT now());
ALTER TABLE storage.objects ENABLE ROW LEVEL SECURITY;
CREATE FUNCTION storage.foldername(name text) RETURNS text[] LANGUAGE sql IMMUTABLE AS $$
  SELECT (string_to_array(name, '/'))[1:array_length(string_to_array(name, '/'), 1) - 1] $$;
CREATE FUNCTION storage.filename(name text) RETURNS text LANGUAGE sql IMMUTABLE AS $$
  SELECT (string_to_array(name, '/'))[array_length(string_to_array(name, '/'), 1)] $$;
CREATE FUNCTION storage.extension(name text) RETURNS text LANGUAGE sql IMMUTABLE AS $$
  SELECT reverse(split_part(reverse(name), '.', 1)) $$;

-- [realtime] the publication Supabase Realtime streams from.
CREATE SCHEMA realtime;
CREATE PUBLICATION supabase_realtime;

-- [pg_cron] Supabase's `cron` schema: job table + schedule/unschedule overloads (rows only,
-- nothing ever runs). `CREATE EXTENSION pg_cron` is stripped by the harness.
CREATE SCHEMA cron;
CREATE TABLE cron.job (jobid bigserial PRIMARY KEY, jobname text, schedule text, command text, active boolean DEFAULT true);
CREATE FUNCTION cron.schedule(jobname text, schedule text, command text) RETURNS bigint LANGUAGE sql AS $$
  INSERT INTO cron.job (jobname, schedule, command) VALUES ($1, $2, $3) RETURNING jobid $$;
CREATE FUNCTION cron.schedule(schedule text, command text) RETURNS bigint LANGUAGE sql AS $$
  INSERT INTO cron.job (schedule, command) VALUES ($1, $2) RETURNING jobid $$;
CREATE FUNCTION cron.unschedule(jobname text) RETURNS boolean LANGUAGE sql AS $$
  DELETE FROM cron.job WHERE jobname = $1 RETURNING true $$;
CREATE FUNCTION cron.unschedule(jobid bigint) RETURNS boolean LANGUAGE sql AS $$
  DELETE FROM cron.job WHERE jobid = $1 RETURNING true $$;

-- [pg_net] Supabase's async HTTP (`net`): signatures only, returns a fake request id.
-- `CREATE EXTENSION pg_net` is stripped by the harness.
CREATE SCHEMA net;
CREATE FUNCTION net.http_post(url text, body jsonb DEFAULT '{}', params jsonb DEFAULT '{}',
  headers jsonb DEFAULT '{}', timeout_milliseconds int DEFAULT 5000) RETURNS bigint LANGUAGE sql AS $$ SELECT 1::bigint $$;
CREATE FUNCTION net.http_get(url text, params jsonb DEFAULT '{}', headers jsonb DEFAULT '{}',
  timeout_milliseconds int DEFAULT 5000) RETURNS bigint LANGUAGE sql AS $$ SELECT 1::bigint $$;

-- [vault] Supabase Vault: plaintext stand-in for the secrets table + decrypted view.
CREATE SCHEMA vault;
CREATE TABLE vault.secrets (id uuid PRIMARY KEY DEFAULT gen_random_uuid(), name text UNIQUE, secret text, description text);
CREATE VIEW vault.decrypted_secrets AS SELECT id, name, secret AS decrypted_secret, secret, description FROM vault.secrets;
CREATE FUNCTION vault.create_secret(secret text, name text DEFAULT NULL, description text DEFAULT '') RETURNS uuid LANGUAGE sql AS $$
  INSERT INTO vault.secrets (secret, name, description) VALUES ($1, $2, $3) RETURNING id $$;
