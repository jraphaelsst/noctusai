# Core — Signup → Onboarding → Org → JWT Claim Journey

> **Root-fix context:** a test user had no `org_id` in its JWT; RLS then stripped all their data.
> This doc codifies the guaranteed chain so any agent modifying auth/onboarding knows the invariants.

---

## 1. Chain overview

```
User signs up / OAuth login
    └─> organizations row created  (org_type, number_of_users, prefixed slug)
    └─> noctus_users row created   (org_id FK, org_role='owner')  ← THE RLS SOURCE OF TRUTH
            └─> public.current_org_id()  (SECURITY DEFINER) reads
                noctus_users WHERE id = auth.uid()
                    └─> every product's RLS policy evaluates to the right org
    └─> user_metadata.org_id stamped  (app-convenience signal ONLY — see §5;
        user_metadata is client-editable ⇒ NEVER trusted for RLS)
```

**Invariant:** no account-creation path may exit without completing all three legs above.
`test_signup_org_guarantee.py` + `test_oauth_router.py` enforce this. The
`noctus_users` row is the leg RLS actually depends on (`current_org_id()` reads
it via `auth.uid()`); the `user_metadata` stamp is belt-and-suspenders, not the
authorization path.

---

## 2. Where each leg lives

| Leg | File | Key call |
|-----|------|----------|
| Email signup | `products/core/backend/app/routers/auth.py` · `POST /api/auth/signup` | `db.table("organizations").insert(...)` + `db.table("noctus_users").insert(...)` + `db.auth.admin.update_user_by_id(uid, {"user_metadata": {"org_id": ...}})` |
| OAuth signup | `products/core/backend/app/routers/oauth.py` · `POST /api/auth/oauth/callback` | Same three legs; OAuth defaults to `org_type='individual'` |
| JWT claim sync | Both paths above (at creation); also `POST /api/sso/session` (at each SSO login, enriches user_metadata with org_id + role + plan) | `supabase_admin.auth.admin.update_user_by_id(uid, {"user_metadata": {...}})` |
| Onboarding update | `products/core/backend/app/routers/onboarding.py` · `PATCH /api/onboarding/complete` with `step='company_details'` | Can update org_type + number_of_users post-signup |

---

## 3. Org model

### 3a. `public.organizations` columns (auth-journey-relevant)

| Column | Type | Constraint | Notes |
|--------|------|-----------|-------|
| `id` | UUID PK | — | Never prefixed — UUID is the FK anchor + RLS pivot |
| `slug` | TEXT UNIQUE | — | Prefixed: `indv_<base>` or `comp_<base>` (visible, queryable) |
| `org_type` | TEXT | `NOT NULL DEFAULT 'individual' CHECK (org_type IN ('individual','company'))` | Added migration 039 |
| `number_of_users` | INT | `NOT NULL DEFAULT 1 CHECK (number_of_users >= 1)` | Required ≥1; company-required in FE |
| `owner_id` | UUID FK → auth.users | — | Set to creating user's id |
| `onboarding_completed` | BOOL | DEFAULT false | Flipped when all 4 steps done |

### 3b. Slug prefix model

- `indv_<base>` — individual org (default for both signup paths)
- `comp_<base>` — company org (when `org_type='company'` at signup or updated in onboarding)
- Base = slugified org name (lowercase, spaces→hyphens, max 44 chars)
- Total slug max: 49 chars (`comp_` + 44)
- UUID id is NOT prefixed — prefixing a PK with FK refs would require cascading renames
- Easy querying: `WHERE org_type = 'company'`; slug prefix is the human-visible signal

Helper: `_make_org_slug(base_name, org_type)` in `auth.py` and `oauth.py`

---

## 4. `public.noctus_users` guarantees

| Column | Invariant |
|--------|-----------|
| `id` | = Supabase `auth.users.id` |
| `org_id` | NOT NULL (FK → organizations.id). A row without org_id = impossible by schema + enforced by signup code |
| `org_role` | `'owner'` for the creating user |

---

## 5. How RLS resolves the org (the trusted path)

> ⚠️ **Superseded model (do NOT reintroduce):** earlier RLS read the org claim
> straight off the JWT — `auth.jwt() ->> 'org_id'`. That was broken **and**
> insecure: (a) Supabase nests app-set claims under `user_metadata`, so the
> top-level claim is NULL → RLS stripped every row; (b) `user_metadata` is
> **client-editable** (`supabase.auth.updateUser({ data: { org_id } })`), so
> keying RLS on it is a privilege-escalation hole (Supabase advisor flags
> `rls_references_user_metadata`). See `memory/feedback_rls_never_key_on_user_metadata`.

**Current model — derive the org from a trusted, server-controlled table:**

```sql
-- The single org-resolution function every RLS policy calls (fleet-wide).
CREATE OR REPLACE FUNCTION public.current_org_id() RETURNS uuid
  LANGUAGE sql STABLE SECURITY DEFINER SET search_path TO 'public'
  AS $$ SELECT org_id FROM public.noctus_users WHERE id = (SELECT auth.uid()); $$;
-- policies: USING (org_id = public.current_org_id())
```

`auth.uid()` is the cryptographically-signed subject — the user cannot forge it —
so the resolved org is always the caller's real `noctus_users.org_id`. This is
exactly why the **`noctus_users` leg of the signup chain is non-negotiable**: it
is what authorization reads. A forged `user_metadata.org_id` is ignored.

**`user_metadata.org_id` stamp — app-convenience only (NOT authorization):**
- Email signup: stamped immediately after org insert via `update_user_by_id`
- OAuth signup: same, in the callback handler
- SSO session: re-stamped on each `/api/sso/session` call (picks up org changes)
- It is read by the FE/app for display/routing; it is **never** the RLS source.

**Legacy users without a `noctus_users` row:** the org guarantee here backfills
both legs. The authorization fix for any orgless user is to ensure the
`noctus_users` row exists with the right `org_id` (what `current_org_id()` reads),
not to re-stamp `user_metadata`.

---

## 6. Onboarding UI (company_details step)

File: `products/core/frontend/src/pages/Onboarding.tsx`

Step 1 (`company_details`) now includes:

- **Tipo de conta** — two-button picker: "Individual" | "Empresa"
- **Numero de funcionarios** — number input, hidden (`max-h-0 opacity-0`) when `individual`,
  fades in (`max-h-24 opacity-100`, CSS transition) when `Empresa` selected, resets to 1 on
  switch back to `individual`
- On submit: sends `org_type` + `number_of_users` in `data` dict to `PATCH /api/onboarding/complete`

FE test: `products/core/frontend/src/pages/Onboarding.test.tsx` — 6 tests cover picker + fade behavior.

---

## 7. Migration

Migration `039_org_type_number_of_users.sql`:
- Adds `org_type TEXT NOT NULL DEFAULT 'individual'` + CHECK
- Adds `number_of_users INT NOT NULL DEFAULT 1` + CHECK
- Backfills existing rows conservatively (all → `individual`, `1`)
- Adds `idx_organizations_org_type` index
- Does NOT rename existing slugs (preserves FK + bookmark integrity)

**Tech-lead: apply this migration to prod before deploying the new auth code.**

---

## 8. Test coverage

| File | Coverage |
|------|----------|
| `tests/routers/test_signup_org_guarantee.py` | Email signup creates org + stamps metadata; org_type validation; slug prefix logic; OAuth new-user guarantee |
| `tests/routers/test_auth_router.py` | Existing signup/login/me/logout tests (26 → still passing) |
| `tests/routers/test_oauth_router.py` | Existing OAuth tests (still passing) |
| `products/core/frontend/src/pages/Onboarding.test.tsx` | Org-type picker UX + conditional field behavior |
