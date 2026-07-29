-- 015_status_pagina_dev_visibility.sql — make 'desenvolvimento' pages
-- visible to dev / owner / admin, closing a gate that hid them from EVERYONE.
--
-- THE DEFECT (fan-out from the social-wiring pilot, feat/status-pagina-
-- dev-visibility, migration 026/032): orbity.status_pagina had exactly ONE
-- policy — todos_veem_producao, USING (status = 'producao'). The FE reads
-- this table through the product's *authenticated* Supabase client (RLS
-- applies), so a 'desenvolvimento' row was NEVER returned to anyone — not
-- even owner/dev. seed/lib/frontend/src/page-status.ts's isPageVisible()
-- desenvolvimento branch (isDevOrOwner) was therefore dead code for orbity.
--
-- THE FIX: a SECOND, additive SELECT policy (Postgres OR's permissive
-- policies) that returns 'desenvolvimento' rows to owner/dev/admin.
-- todos_veem_producao is untouched — this can only WIDEN visibility.
--
-- SAFE ROLE SOURCE (the load-bearing security decision):
--   role comes from public.noctus_users.org_role keyed on auth.uid() — a
--   core-managed, server-owned table. This is the SAME trust root as
--   public.current_org_id() (already defined for orbity in 001_orbity.sql).
--   It is 🔴 NOT user_metadata — that JWT claim is user-spoofable and must
--   never key RLS (KB § PATTERNS/security,
--   memory feedback_rls_never_key_on_user_metadata).
--
-- current_org_role() is declared in the shared `public` schema (same as
-- current_org_id()) — CREATE OR REPLACE is idempotent across every product
-- migration chain that (re)declares it; one definition serves the fleet.
--
-- Forward-only + idempotent. Apply to the noctusai Supabase (orbity schema).

SET search_path = orbity, public;

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
DROP POLICY IF EXISTS "dev_veem_desenvolvimento" ON orbity.status_pagina;
CREATE POLICY "dev_veem_desenvolvimento" ON orbity.status_pagina
    FOR SELECT TO authenticated
    USING (
        status = 'desenvolvimento'
        AND public.current_org_role() = ANY (ARRAY['owner', 'dev', 'admin'])
    );

-- 🔴 PARITY CONTRACT: the role array above MUST stay identical to the FE
-- DEV_ROLES const (seed/lib/frontend/src/roles.ts). There is no shared
-- source between this SQL literal and that TS const today; keeping them in
-- lockstep is a manual contract until a keeper enforces it.
