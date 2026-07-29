-- 005_status_pagina_dev_visibility.sql — make 'desenvolvimento' pages
-- visible to dev / owner / admin, closing a gate that hid them from EVERYONE.
--
-- SEED/TEMPLATE LEG of the status_pagina dev-visibility fan-out (pilot:
-- social-wiring migration 026/032, feat/status-pagina-dev-visibility).
-- Every product scaffolded FROM this seed copies 001_seed.sql (which ships
-- only "todos_veem_producao", USING status='producao') — so without this
-- migration every NEW product inherits the same defect: a 'desenvolvimento'
-- row is never returned to anyone (not even dev/owner) through the FE's
-- authenticated product-client read (seed/lib/frontend/src/page-status.ts
-- usePageStatus). This migration makes the seed canonical shape correct
-- day-1 for future products.
--
-- THE FIX: a SECOND, additive SELECT policy (Postgres OR's permissive
-- policies) that returns 'desenvolvimento' rows to owner/dev/admin.
-- todos_veem_producao is untouched — this can only WIDEN visibility.
--
-- SAFE ROLE SOURCE: role comes from public.noctus_users.org_role keyed on
-- auth.uid() — the same trust root as public.current_org_id() (001_seed.sql).
-- 🔴 NOT user_metadata — spoofable, must never key RLS
-- (memory feedback_rls_never_key_on_user_metadata).
--
-- current_org_role() is declared in the shared `public` schema (same as
-- current_org_id()) — CREATE OR REPLACE is idempotent across every product
-- migration chain that (re)declares it; one definition serves the fleet.
--
-- Forward-only + idempotent. products/seed/ and templates/product-seed/
-- MUST stay in sync (pre-commit hook mirrors products/seed → templates on
-- staged change) — this file has a byte-identical sibling in
-- templates/product-seed/backend/migrations/ with {{SCHEMA_NAME}} in place
-- of the literal `seed` schema.

SET search_path = seed, public;

CREATE OR REPLACE FUNCTION public.current_org_role()
  RETURNS text
  LANGUAGE sql
  STABLE SECURITY DEFINER
  SET search_path TO 'public'
AS $f$
  SELECT org_role FROM public.noctus_users WHERE id = (SELECT auth.uid());
$f$;

-- Additive: 'desenvolvimento' rows become readable by dev/owner/admin.
-- TO authenticated is mandatory — anon has no auth.uid(), so
-- current_org_role() is NULL and `NULL = ANY(...)` is false ⇒ zero rows.
-- Scoped to 'desenvolvimento' ONLY — 'desativado' stays hidden from all.
DROP POLICY IF EXISTS "dev_veem_desenvolvimento" ON seed.status_pagina;
CREATE POLICY "dev_veem_desenvolvimento" ON seed.status_pagina
    FOR SELECT TO authenticated
    USING (
        status = 'desenvolvimento'
        AND public.current_org_role() = ANY (ARRAY['owner', 'dev', 'admin'])
    );

-- 🔴 PARITY CONTRACT: the role array above MUST stay identical to the FE
-- DEV_ROLES const (seed/lib/frontend/src/roles.ts). There is no shared
-- source between this SQL literal and that TS const today; keeping them in
-- lockstep is a manual contract until a keeper enforces it.
