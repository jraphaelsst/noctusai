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

### ⏳ F5 — Fix social-wiring login poisoning (clears the F3 warning)
`products/social-wiring/backend/app/routers/auth.py:~150` `login()`: `sb =
get_admin_client(); sb.auth.sign_in_with_password(...)` poisons the singleton.
Recipe: swap `sb` to a throwaway `create_client(settings.supabase_url,
settings.supabase_anon_key)` (exactly core `auth.py:113`). Verify with social-wiring
tests before shipping. Then promote `check_auth_session_mutation_on_shared_client`
to `error`.

### ⏳ F6 — Fix therapy RLS self-reference (clears the F2 warning)
`products/therapy-platform/backend/migrations/001_therapy_platform.sql:1311`
`conversation_participants_access` self-queries `therapy.conversation_participants`
(latent 42P17). Recipe: a new therapy migration adding a SECURITY DEFINER helper
(mirror `035` / `026`) + rewrite the policy to call it. Validate therapy
conversation access before shipping. Then promote `check_rls_policy_self_reference`
to `error`.

## 3a · Seed-first analysis
F2/F3 are platform keepers (single `compliance.py` file, 0 per-product code). F4 is
durable KB. F1 is a one-time prod deploy. All correctly platform-level.

## 11 · Change log
- 2026-05-23 — filed at the shared-checkout auth-fix resolution (`21294376` on main). Fix shipped to git; F1 (deploy) prod-critical; F2 N=2 / F3 N=1 keepers + F4 lessons left for the compliance.py owner. Recorded durably per [[feedback_checkpoint_shorthand_evaporates]].
