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
--   This is the platform's THIRD instance of the same CLASS of problem —
--   see `therapy_012_search_path_hardening` and `erp_028_search_path_hardening`
--   (both already applied). Their functions genuinely ARE SECURITY
--   DEFINER (org-resolvers like `current_org_id()` that must read a
--   trusted table regardless of caller privilege), so their fix pins
--   `search_path` ON TOP OF an already-necessary DEFINER context.
--   `igig.set_updated_at()` is NOT SECURITY DEFINER in 006 and has no
--   reason to become one — it only stamps `NEW.updated_at = now()` on a
--   row the calling statement is already authorized (via RLS) to write,
--   so it runs correctly and safely under the INVOKER's own rights. An
--   earlier draft of this migration copied the precedents' shape
--   (`SECURITY DEFINER SET search_path = ...`) rather than their reason,
--   which would have silently escalated an invoker-rights function to
--   definer-rights while "fixing" search_path — the opposite of an
--   advisor-0011 fix, caught before being applied. Corrected: this
--   migration pins `search_path` only; the security context (INVOKER,
--   unchanged from 006) is untouched.
--
--   PROD ALREADY COMPLIANT, VERIFIED 2026-08-31 (out-of-band, not via
--   this migration ledger): `proname=set_updated_at
--   security_definer=false proconfig={search_path=igig, public}`. The
--   live function already carries exactly the shape below — this
--   migration was never applied to reach that state; something else
--   was. (Same drift class logged separately for p_studio 007/008 and
--   social-wiring 060 — applied-but-unrecorded — which is why prod was
--   checked directly instead of trusting the ledger.) This file's
--   remaining value is as the durable RECORD that a fresh or replayed
--   database reaches the same state prod is already in — do not delete
--   it as a "no-op" once you notice `CREATE OR REPLACE` doesn't change
--   anything live; that is the expected, verified outcome here, not a
--   sign this migration is stale or wrong.
--
-- This migration:
--   1. CREATE OR REPLACE `igig.set_updated_at()` pinning
--      `SET search_path = igig, public` — NO `SECURITY DEFINER` (see
--      above; 006 never had it, and it must not gain it here). Body
--      unchanged from 006 (`NEW.updated_at = now(); RETURN NEW;`) —
--      only the function header changes.
--   2. Idempotent and safe to run against a database where it is
--      already true (prod, per the verification above) — CREATE OR
--      REPLACE converges to the same definition either way. Every
--      existing trigger created by 006-012 (`trg_*_updated_at`)
--      continues to reference the function by name and picks up the
--      (identical, on prod) header transparently, no trigger
--      re-creation needed.
--
-- NOT APPLIED BY THIS WORKTREE. Committed only — applying (even though
-- it should be a verified no-op against prod) is the tech-lead's call.
-- Per `feedback_mcp_migrations_mirror_file`: this file is committed BEFORE
-- being applied via mcp__claude_ai_Supabase__apply_migration.

CREATE OR REPLACE FUNCTION igig.set_updated_at()
RETURNS TRIGGER
LANGUAGE plpgsql SET search_path = igig, public
AS $$ BEGIN NEW.updated_at = now(); RETURN NEW; END; $$;

COMMENT ON FUNCTION igig.set_updated_at() IS
  'Generic created_at/updated_at trigger function; search_path pinned in '
  'migration 013 per Supabase advisor 0011. Body AND security context '
  '(INVOKER rights — no SECURITY DEFINER) unchanged from migration 006; '
  'only the search_path clause was added. Verified already applied to '
  'prod out-of-band as of 2026-08-31 — this file is the durable record, '
  'not the origin of that state.';
