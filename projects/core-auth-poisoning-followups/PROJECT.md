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

## 2 · Follow-ups

> NOTE: this folder is **ephemeral** (projects/ archives away). The DURABLE
> outputs are already codified — keepers in `compliance.py`, lessons in KB +
> memory. The two product-fix items below are durably tracked by the
> **keepers-at-warning** (they re-surface every `noctus.dev.review`/`hound` run),
> so they survive this doc's deletion. This doc is just the active checklist.

### ✅ F2 — Keeper `check_rls_policy_self_reference` — DONE
Built (`compliance.py`, migration-supersession aware), registered, 5 colocated
tests + meta-keeper green. Severity `warning` (1 pre-existing: therapy) → promote
to `error` when F6 lands. Found a 3rd instance (therapy) on first run.

### ✅ F3 — Keeper `check_auth_session_mutation_on_shared_client` — DONE
Built (`compliance.py`, AST-based), registered, 5 colocated tests + meta-keeper
green. Severity `warning` (1 pre-existing: social-wiring) → `error` when F5 lands.
Found a 2nd instance (social-wiring) on first run — so N=2, not N=1.

### ✅ F4 — Codify the 2 lessons — DONE (durable)
`KB § PATTERNS/database-rls.md` § RLS self-reference recursion +
`KB § PATTERNS/backend.md` § Admin-client poisoning; memory
`feedback_rls_policy_self_reference` + `feedback_admin_client_poisoning` (+ MEMORY.md).

### ⏳ F1 — Deploy the sso.py fix to prod (PERMANENCE) — prod-critical, GATED
Prod core runs the **OLD sso.py** (restart restored login). Until the new sso.py
deploys, a future magic-link `verify_otp` can re-poison (035 downgrades it to a
mis-scoped read, not a 500). 035 is **already applied to live** (do NOT re-apply).
Path: `main` pushed → CI builds core GHCR image → gated promote `main→prod` →
`deploy_image core`. Gated prod action — **deploy only when everything's tied up.**

### ✅ F5 — Fix social-wiring login poisoning — DONE (code)
`products/social-wiring/backend/app/routers/auth.py` `login()` now uses a throwaway
`create_client(settings.supabase_url, settings.supabase_anon_key)` (mirrors core
`auth.py:113`). Dispatched to Engineer SW-AUTH (isolated worktree), reconciled by
architect. Verified: social-wiring auth tests 82 passed; keeper `[]`. F3 promoted to
`error`. **Gated remainder:** deploy social-wiring to prod so the fix takes effect
(prod still runs the old code) — same gated class as F1.

### ✅ F6 — Fix therapy RLS self-reference — DONE (migration in git)
`products/therapy-platform/backend/migrations/015_fix_conversation_participants_rls_recursion.sql`
adds a SECURITY DEFINER `therapy.is_conversation_member()` helper + DROP/recreates
`conversation_participants_access` to call it (mirrors 035/026, intent preserved).
Dispatched to Engineer TH-RLS (isolated worktree), reconciled by architect. Verified:
therapy suite 1381 passed / 14 skipped; keeper `[]` (supersession). F2 promoted to
`error`. **Gated remainder:** **live-apply 015 to the therapy Supabase** (git-only
so far → git↔live drift until applied; latent 42P17 persists in live until then).

## 3a · Seed-first analysis
F2/F3 are platform keepers (single `compliance.py` file, 0 per-product code). F4 is
durable KB. F1 is a one-time prod deploy. All correctly platform-level.

## 11 · Change log
- 2026-05-23 — filed at the shared-checkout auth-fix resolution (`21294376` on main). Fix shipped to git; F1 (deploy) prod-critical; F2 N=2 / F3 N=1 keepers + F4 lessons left for the compliance.py owner. Recorded durably per [[feedback_checkpoint_shorthand_evaporates]].
