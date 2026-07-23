-- 032_status_pagina_dev_visibility.sql — make 'desenvolvimento' pages
-- visible to dev / owner / admin, closing a gate that hid them from EVERYONE.
--
-- THE DEFECT (verified against live prod 2026-07-17):
--   status_pagina had exactly ONE policy — todos_veem_producao,
--   USING (status = 'producao'). The FE reads this table through the
--   product's *authenticated* Supabase client (RLS applies), so a
--   'desenvolvimento' row was NEVER returned to anyone — not even owner.
--   The FE's isPageVisible() then does find()→undefined→hidden, making
--   its own `if (status==='desenvolvimento') return isDevOrOwner(...)`
--   branch dead code. Net effect: 'desenvolvimento' == invisible to all,
--   and instagram_insights + meta (seeded 'desenvolvimento') were silently
--   missing from the sidebar in production.
--
-- THE FIX: a SECOND, additive SELECT policy (Postgres OR's permissive
--   policies) that returns 'desenvolvimento' rows to dev/owner/admin.
--   todos_veem_producao is untouched — this can only WIDEN visibility.
--
-- SAFE ROLE SOURCE (the load-bearing security decision):
--   role comes from public.noctus_users.org_role keyed on auth.uid() —
--   a core-managed, server-owned table. This is the SAME trust root as
--   current_org_id() (011). It is 🔴 NOT user_metadata — that JWT claim
--   is user-spoofable and must never key RLS
--   (KB § PATTERNS/security, memory feedback_rls_never_key_on_user_metadata).
--
-- Scope: this migration fixes the LIVE social_wiring defect. New products
--   inheriting the policy (seed/template 001) and the fleet fan-out to the
--   other ~10 schemas are a deliberate pilot-gated FOLLOW-ON, not folded
--   here (products/seed/backend/migrations/ is a live peer worktree).
--
-- Forward-only + idempotent. Apply to the noctusai Supabase (social_wiring).

SET search_path = social_wiring, public;

-- Symmetric helper to current_org_id() (011) — one public definition
-- serves every product schema; search_path locked so noctus_users
-- resolves regardless of the caller's session search_path. SECURITY
-- DEFINER so it does not depend on noctus_users' own RLS being permissive
-- to the invoker.
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
-- DROP+CREATE (not IF NOT EXISTS, unsupported for CREATE POLICY) for
-- idempotency across re-application.
DROP POLICY IF EXISTS "dev_veem_desenvolvimento" ON social_wiring.status_pagina;
CREATE POLICY "dev_veem_desenvolvimento" ON social_wiring.status_pagina
    FOR SELECT TO authenticated
    USING (
        status = 'desenvolvimento'
        AND public.current_org_role() = ANY (ARRAY['owner', 'dev', 'admin'])
    );

-- 🔴 PARITY CONTRACT: the role array above MUST stay identical to the FE
-- DEV_ROLES const (seed/lib/frontend/src/roles.ts). If they diverge you
-- get split-brain — RLS returns the row but the FE hides it, or vice
-- versa. There is no shared source between this SQL literal and that TS
-- const today; keeping them in lockstep is a manual contract until a
-- keeper enforces it.
