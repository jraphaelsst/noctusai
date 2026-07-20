-- ============================================================================
-- Migration 014 — Backfill orbity.lead_stages for orgs already licensed
--
-- WHY (verified live in prod, 2026-07-20):
--   orbity.seed_default_lead_stages(org_id), defined in 005_crm_core.sql,
--   has ZERO call sites anywhere in the repo — the definition is the only
--   hit. The backend has no RPC mechanism at all (no `.rpc(` call site
--   exists anywhere in products/orbity/backend/app), so nothing could ever
--   reach it, directly or indirectly. Every org's Funil kanban has
--   therefore rendered permanently empty since launch — not "unwired",
--   genuinely unreachable.
--
-- THIS MIGRATION covers the EXISTING-ORG leg only:
--   Backfills the 7 canonical default stages for every org that already
--   holds an orbity license, via the existing SECURITY DEFINER function
--   (direct in-database SQL invocation — no PostgREST/RPC exposure
--   involved, so none of the RPC-mechanism gap above applies here).
--   Idempotent: the function's own `ON CONFLICT (org_id, position) DO
--   NOTHING` makes re-running this migration a no-op.
--
--   SCOPE: `public.licenses ⋈ public.products WHERE slug = 'orbity'`
--   rather than "every org in public.noctus_users" — orgs that never
--   installed orbity should not get 7 unused rows seeded into a schema
--   they'll never touch.
--
-- THE NEW-ORG / FORWARD leg is intentionally NOT a lazy-seed-on-read here.
--   Considered and rejected: auto-seeding inside CRMService.list_stages()
--   (a GET handler silently writing on first read is a surprising side
--   effect, and — per the empty-state fix in Funil.tsx — a self-serve
--   "Criar etapas padrão" button was already required for the UI, so a
--   second, implicit mechanism would just be a redundant seam for the
--   exact same job). Instead: CRMService.seed_default_stages() +
--   POST /api/crm/stages/seed-defaults (crm_router.py) — an explicit,
--   user-triggered, idempotent endpoint every org (old or new) can call.
--   Concurrency: protected by lead_stages_org_position_ux (declared in
--   005_crm_core.sql) — a racing second INSERT hits the UNIQUE
--   (org_id, position) index and is resolved app-side as "already
--   seeded" (see CRMService._is_duplicate_stage_error).
--
-- IDEMPOTENT: re-running this file is a no-op (function-level ON CONFLICT).
-- SEARCH PATH: session-pinned to orbity, public (consistent with 001).
-- ============================================================================

SET search_path = orbity, public;

DO $$
DECLARE
  r RECORD;
BEGIN
  FOR r IN
    SELECT DISTINCT lic.org_id
    FROM public.licenses lic
    JOIN public.products p ON p.id = lic.product_id
    WHERE p.slug = 'orbity'
  LOOP
    PERFORM orbity.seed_default_lead_stages(r.org_id);
  END LOOP;
END;
$$;
