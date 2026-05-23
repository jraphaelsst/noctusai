# core-auth-poisoning-followups — Project Document

> Filed 2026-05-23 to give durable form to the deploy + codify follow-ups handed
> off after the shared-checkout auth fix (commit `21294376`, on `main`). The fix
> itself (sso.py un-poisoning + migration 035 RLS-recursion cure) is SHIPPED to
> git; these are the remaining permanence + codification steps.
> Symbol-first per `KB § PATTERNS/doc-symbology.md`.

- **Created:** 2026-05-23
- **Status:** ⏳ OPEN
- **Owner:** joaoraphaelsst@gmail.com · architect
- **Origin commit:** `21294376 fix(core-sso): stop admin-client poisoning on magic-link verify_otp + cure noctus_users RLS recursion (035)`

## 1 · Context (the bug that shipped the fix)

Prod login broke 2026-05-23: `GET /api/auth/me` 500'd with PostgREST `42P17`
"infinite recursion detected in policy for relation noctus_users". Two coupled
defects:
1. **Admin-client poisoning** — `sso.py` ran `verify_otp` (which *establishes a
   session*) on the shared service-role singleton `supabase_admin`; supabase-py
   propagated the user token onto it → every later `get_admin_client()` was
   silently downgraded `service_role → authenticated` **process-wide** → RLS
   tripped on unrelated requests. **Fixed** (throwaway anon client).
2. **RLS self-recursion** — `noctus_users.users_read_own` SELECT policy
   self-queried `noctus_users` in its own USING clause → 42P17. **Fixed**
   (migration 035: SECURITY DEFINER `current_user_org_id()` helper). Same shape
   as `026` for `erp.equipe_membros`.

## 2 · Follow-ups (none silently dropped)

### F1 — Deploy the sso.py fix to prod (PERMANENCE) ⏳ prod-critical
Prod core was restarted (fresh un-poisoned singleton → login works now) but runs
the **OLD sso.py**. Until the new sso.py deploys, a future magic-link `verify_otp`
can **re-poison** the singleton — now downgraded by 035 from a hard 500 to a
mis-scoped (authenticated-not-service_role) read, but still wrong. Migration 035
is **already applied to live** (do NOT re-apply). Deploy path: `main` is pushed →
CI builds the core GHCR image → gated promote `main→prod` → `deploy_image core`
(VPS). Gated prod action — operator/user runs it.

### F2 — Keeper `check_rls_policy_self_reference` ⏳ (N=2 → triage→formalize)
Flag any RLS policy whose `USING` / `WITH CHECK` clause subqueries the **same
table** the policy is ON (the 42P17 shape). N=2: `erp.equipe_membros` (026) +
`public.noctus_users` (035). Remediation = a SECURITY DEFINER bypass helper.
Touches `compliance.py` (the keeper-owner's lane). Migrations are SQL (prose-class
predicate). Colocated test + 3-way-sync.

### F3 — Keeper `check_auth_session_mutation_on_shared_client` ⏳ (N=1, proactive)
Flag a session-establishing supabase-py auth call (`verify_otp`, `sign_in*`,
`set_session`, `refresh_session`) invoked on a **shared/singleton** client
(`supabase_admin` / `get_admin_client()` result) rather than a throwaway
`create_client(...)`. N=1 (this bug) — proactive keeper, mark as such. Touches
`compliance.py`. Colocated test + 3-way-sync.

### F4 — Codify the 2 lessons (KB + memory) ⏳
- **admin-client poisoning** — never run session-establishing auth on a shared
  service-role singleton; supabase-py mutates the calling client's PostgREST auth
  layer process-wide. Use a throwaway client.
- **RLS policy self-reference** — a policy that reads its own table recurses
  (42P17); resolve org/tenant scope via a SECURITY DEFINER (BYPASSRLS) helper.
  Likely homes: `KB § PATTERNS/database-rls.md` + `KB § PATTERNS/backend.md`.

## 3a · Seed-first analysis
F2/F3 are platform keepers (single `compliance.py` file, 0 per-product code). F4 is
durable KB. F1 is a one-time prod deploy. All correctly platform-level.

## 11 · Change log
- 2026-05-23 — filed at the shared-checkout auth-fix resolution (`21294376` on main). Fix shipped to git; F1 (deploy) prod-critical; F2 N=2 / F3 N=1 keepers + F4 lessons left for the compliance.py owner. Recorded durably per [[feedback_checkpoint_shorthand_evaporates]].
