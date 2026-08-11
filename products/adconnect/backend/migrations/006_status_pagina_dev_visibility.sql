-- 006_status_pagina_dev_visibility.sql — make 'desenvolvimento' pages
-- visible to dev / owner / admin, closing a gate that hid them from EVERYONE.
--
-- THE DEFECT: adconnect.status_pagina had exactly ONE policy —
-- todos_veem_producao, USING (status = 'producao'). The FE reads this table
-- through the product's *authenticated* Supabase client (RLS applies), so a
-- 'desenvolvimento' row was NEVER returned to anyone — not even owner/dev.
-- seed/lib/frontend/src/page-status.ts's isPageVisible() desenvolvimento
-- branch (isDevOrOwner) was therefore dead code for adconnect.
--
-- WHY THIS LANDS NOW, FOR AN INATIVO PRODUCT: adconnect is STATUS:INATIVO, so
-- nothing here is deployed today. It is included because the keeper that
-- catches this defect (`check_status_pagina_dev_reachability`, the
-- reachability half of `check_status_pagina_role_parity`) is DERIVED from the
-- migrations rather than driven by a hand-maintained roster of active
-- products — an allowlist would drift the moment the catalog changed. Fixing
-- the two products it found is cheaper and more honest than teaching the gate
-- to look away, and it means a future reactivation starts correct.
--
-- THE FIX: a SECOND, additive SELECT policy (Postgres OR's permissive
-- policies) that returns 'desenvolvimento' rows to owner/dev/admin.
-- todos_veem_producao is untouched — this can only WIDEN visibility.
--
-- SAFE ROLE SOURCE (the load-bearing security decision):
--   role comes from public.noctus_users.org_role keyed on auth.uid() — a
--   core-managed, server-owned table. It is 🔴 NOT user_metadata — that JWT
--   claim is user-spoofable and must never key RLS (KB § PATTERNS/security,
--   memory feedback_rls_never_key_on_user_metadata).
--
-- Forward-only + idempotent. Apply to the noctusai Supabase (adconnect schema).

SET search_path = adconnect, public;

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
DROP POLICY IF EXISTS "dev_veem_desenvolvimento" ON adconnect.status_pagina;
CREATE POLICY "dev_veem_desenvolvimento" ON adconnect.status_pagina
    FOR SELECT TO authenticated
    USING (
        status = 'desenvolvimento'
        AND public.current_org_role() = ANY (ARRAY['owner', 'dev', 'admin'])
    );

-- 🔴 PARITY CONTRACT: the role array above MUST stay identical to the FE
-- DEV_ROLES const (seed/lib/frontend/src/roles.ts). Enforced by
-- `check_status_pagina_role_parity`.
