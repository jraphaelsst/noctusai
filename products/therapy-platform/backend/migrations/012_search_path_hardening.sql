-- Migration 012: search_path hardening on RPC functions
--
-- Project:   products/therapy-platform/projects/therapy-platform-wiring/
-- Phase:     4 — Admin Tier C scaffolding-debt sweep
-- Surfaced:  2026-05-10 Phase 4 §2 — search_path hardening audit
--
-- Background:
--   Migration 011 introduced three RPC functions consumed by the
--   scheduling-pilot OAuth flow:
--     - therapy.encrypt_gcal_token(token TEXT)     RETURNS BYTEA
--     - therapy.decrypt_gcal_token(ciphertext BYTEA) RETURNS TEXT
--     - therapy.gcal_authorization_is_fresh(authorized_at TIMESTAMPTZ) RETURNS BOOLEAN
--
--   The first two pin `SET search_path = ''` per Supabase advisor 0011
--   (Function Search Path Mutable). The third — `gcal_authorization_is_fresh`
--   — was authored as a SQL function without the SET clause. It only
--   references `now()` and INTERVAL literals (no schema-qualified objects
--   that could be shadowed), but Supabase advisor 0011 fires on every
--   function without an explicit search_path regardless of body content.
--
-- This migration:
--   1. Re-creates `gcal_authorization_is_fresh` with `SET search_path = ''`
--      to silence advisor 0011 and align with the defense-in-depth pattern
--      established by sibling functions.
--   2. Idempotent — uses CREATE OR REPLACE so re-applying is a no-op.
--
-- Per `feedback_mcp_migrations_mirror_file`: this file is committed BEFORE
-- being applied via mcp__claude_ai_Supabase__apply_migration.

-- ---------- gcal_authorization_is_fresh — pin search_path ----------
CREATE OR REPLACE FUNCTION therapy.gcal_authorization_is_fresh(authorized_at TIMESTAMPTZ)
RETURNS BOOLEAN
LANGUAGE sql
IMMUTABLE
SET search_path = ''
AS $$
  SELECT authorized_at IS NOT NULL
     AND authorized_at > now() - INTERVAL '7 days';
$$;

COMMENT ON FUNCTION therapy.gcal_authorization_is_fresh(TIMESTAMPTZ) IS
  '7-day re-auth freshness check. search_path pinned to empty (migration 012) '
  'to silence Supabase advisor 0011 and align with sibling RPCs from migration 011.';
