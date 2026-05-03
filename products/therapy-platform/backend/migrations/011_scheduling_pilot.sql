-- Migration 011: scheduling-pilot wiring
--
-- Project:   products/therapy-platform/projects/therapy-scheduling-pilot/
-- Phase:     1
-- Decisions: §2 — multi-clinic + solo (Q1), global per-clinic 15-min buffer (Q2),
--            internal + Google Calendar two-way (Q3), pgcrypto+Vault encryption
--            with 7-day re-auth policy (§7 Q1, answered 2026-05-03).
--
-- Adds:
--   1. therapy.clinic_settings.transition_buffer_minutes (cleaning buffer; default 15)
--   2. therapy.therapist_profiles GCal OAuth columns (encrypted refresh token,
--      calendar id, authorization timestamp for 7-day re-auth check)
--   3. Vault-keyed pgcrypto helper functions for encrypt/decrypt + freshness check
--
-- Per `feedback_mcp_migrations_mirror_file`: this file is committed BEFORE
-- being applied via mcp__claude_ai_Supabase__apply_migration.
--
-- Migration 010 is reserved by the parallel `therapy-platform-wiring` agent
-- for `010_rejection_audit.sql` — pilot takes 011 to avoid number collision.

-- ---------- 0. Required extensions ----------
-- Supabase: pgcrypto (extensions schema) + supabase_vault (vault schema)
-- both ship pre-installed. We assert without forcing CREATE EXTENSION
-- to avoid permission issues on managed Supabase.
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'pgcrypto') THEN
    RAISE EXCEPTION 'pgcrypto extension required (expected in schema extensions)';
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'supabase_vault') THEN
    RAISE EXCEPTION 'supabase_vault extension required';
  END IF;
END $$;

-- ---------- 1. Clinic-level cleaning buffer ----------
ALTER TABLE therapy.clinic_settings
  ADD COLUMN IF NOT EXISTS transition_buffer_minutes INT NOT NULL DEFAULT 15;

-- ---------- 2. Per-therapist Google Calendar OAuth credentials ----------
-- Refresh token stored as pgcrypto-encrypted BYTEA, keyed by a Supabase
-- Vault secret. 7-day re-auth policy: app refuses to use credentials older
-- than 7 days (computed against gcal_authorized_at; therapist must re-consent
-- through the OAuth UI). Defense-in-depth on top of column encryption +
-- the existing therapy.therapist_profiles RLS (owning therapist + platform_admin).
ALTER TABLE therapy.therapist_profiles
  ADD COLUMN IF NOT EXISTS gcal_refresh_token_encrypted BYTEA,
  ADD COLUMN IF NOT EXISTS gcal_calendar_id TEXT,
  ADD COLUMN IF NOT EXISTS gcal_authorized_at TIMESTAMPTZ;

-- ---------- 3. Vault secret bootstrap (idempotent) ----------
-- Creates the symmetric key only if absent. Rotate later via
-- vault.update_secret(<id>, <new-base64-key>) — existing rows must be
-- re-encrypted by a follow-up migration (no rolling rotation here).
DO $$
DECLARE
  existing_id UUID;
BEGIN
  SELECT id INTO existing_id FROM vault.secrets WHERE name = 'gcal_token_key' LIMIT 1;
  IF existing_id IS NULL THEN
    PERFORM vault.create_secret(
      encode(gen_random_bytes(32), 'base64'),
      'gcal_token_key',
      'Symmetric key for therapy GCal refresh-token encryption (pgcrypto). '
      'Owned by: products/therapy-platform/projects/therapy-scheduling-pilot/.'
    );
  END IF;
END $$;

-- ---------- 4. Encrypt / decrypt helpers ----------
-- SECURITY DEFINER so the helpers can read vault.decrypted_secrets even when
-- called by a non-privileged role; search_path locked to '' to defeat
-- function-shadowing attacks.

CREATE OR REPLACE FUNCTION therapy.encrypt_gcal_token(token TEXT)
RETURNS BYTEA
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $$
DECLARE
  vault_key TEXT;
BEGIN
  SELECT decrypted_secret INTO vault_key
  FROM vault.decrypted_secrets
  WHERE name = 'gcal_token_key'
  LIMIT 1;

  IF vault_key IS NULL THEN
    RAISE EXCEPTION 'Vault secret gcal_token_key missing';
  END IF;

  RETURN extensions.pgp_sym_encrypt(token, vault_key);
END;
$$;

CREATE OR REPLACE FUNCTION therapy.decrypt_gcal_token(ciphertext BYTEA)
RETURNS TEXT
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $$
DECLARE
  vault_key TEXT;
BEGIN
  IF ciphertext IS NULL THEN
    RETURN NULL;
  END IF;

  SELECT decrypted_secret INTO vault_key
  FROM vault.decrypted_secrets
  WHERE name = 'gcal_token_key'
  LIMIT 1;

  IF vault_key IS NULL THEN
    RAISE EXCEPTION 'Vault secret gcal_token_key missing';
  END IF;

  RETURN extensions.pgp_sym_decrypt(ciphertext, vault_key);
END;
$$;

-- ---------- 5. 7-day re-auth freshness check ----------
-- Returns TRUE when the stored authorization is still within the 7-day
-- re-auth window. App-side gate uses this to refuse-and-redirect to the
-- OAuth flow when stale.
CREATE OR REPLACE FUNCTION therapy.gcal_authorization_is_fresh(authorized_at TIMESTAMPTZ)
RETURNS BOOLEAN
LANGUAGE sql
IMMUTABLE
AS $$
  SELECT authorized_at IS NOT NULL
     AND authorized_at > now() - INTERVAL '7 days';
$$;

-- ---------- 6. LGPD audit trail ----------
-- Per `feedback_lgpd_first`: OAuth refresh tokens are credentials-grade
-- secrets per LGPD Art. 46. Encryption-at-rest + 7-day re-auth + RLS
-- combine as the safeguard set. Compromise scenario requires DB read
-- access AND Vault key access AND a fresh re-auth window — three
-- independent factors.
