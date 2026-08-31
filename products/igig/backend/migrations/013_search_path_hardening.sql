-- Migration 013: search_path hardening on igig functions
--
-- Surfaced:  2026-08-31 drift-found (feat/igig-cofre-declare-and-ui,
--            noctus.dev.review) — Supabase advisor 0011 (Function Search
--            Path Mutable) on `igig.set_updated_at()` (006_igig_dominio.sql:209).
--
-- Background:
--   A function without a pinned `search_path` resolves unqualified names
--   against whatever `search_path` the CALLING session happens to have —
--   for a SECURITY DEFINER function that is a privilege-escalation vector
--   (a caller who can create objects in an earlier-resolving schema can
--   shadow a name the function body references and have it execute with
--   the definer's rights); Supabase advisor 0011 flags it regardless of
--   SECURITY DEFINER because the risk class is the mutable resolution
--   itself, not only who runs under it.
--
--   Full sweep of `CREATE [OR REPLACE] FUNCTION` across every igig
--   migration (001-012) + noctus.dev.scan_migration_patterns' search_path
--   probe found exactly ONE function missing the pin:
--     - igig.set_updated_at()               — 006_igig_dominio.sql:209
--   The other two functions the sweep surfaced already pin it and are
--   NOT igig-schema functions (shared seed-canonical resolvers declared
--   once and re-declared idempotently by every product's own migration
--   chain, unrelated to this schema's own gap):
--     - public.current_org_id()             — 001_igig.sql:34   (already pinned)
--     - public.current_org_role()           — 005_status_pagina_dev_visibility.sql:35 (already pinned)
--
--   This is the platform's THIRD instance of the same solved problem —
--   see `therapy_012_search_path_hardening` and `erp_028_search_path_hardening`
--   (both already applied). This migration follows their shape rather
--   than inventing a new one.
--
-- This migration:
--   1. CREATE OR REPLACE `igig.set_updated_at()` with the canonical
--      `SECURITY DEFINER SET search_path = igig, public` shape — the
--      exact form `noctusai_lib.domain.sql_templates.updated_at_function`
--      emits, and the one therapy/daily-life/personal-finance/mailing's
--      `set_updated_at()` already use. Body unchanged from 006
--      (`NEW.updated_at = now(); RETURN NEW;`) — only the function
--      header changes.
--   2. Idempotent — CREATE OR REPLACE; every existing trigger created
--      by 006-012 (`trg_*_updated_at`) continues to reference the
--      function by name and picks up the new header transparently, no
--      trigger re-creation needed.
--
-- NOT APPLIED. Committed only — applying to prod is the tech-lead's call.
-- Per `feedback_mcp_migrations_mirror_file`: this file is committed BEFORE
-- being applied via mcp__claude_ai_Supabase__apply_migration.

CREATE OR REPLACE FUNCTION igig.set_updated_at()
RETURNS TRIGGER
LANGUAGE plpgsql SECURITY DEFINER SET search_path = igig, public
AS $$ BEGIN NEW.updated_at = now(); RETURN NEW; END; $$;

COMMENT ON FUNCTION igig.set_updated_at() IS
  'Generic created_at/updated_at trigger function; search_path pinned in '
  'migration 013 per Supabase advisor 0011. Body unchanged from migration 006.';
