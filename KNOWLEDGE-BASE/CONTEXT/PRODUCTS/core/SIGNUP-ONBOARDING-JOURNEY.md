# Core — Signup → Onboarding → Org → JWT Claim Journey

> **Root-fix context:** a test user had no `org_id` in its JWT; RLS then stripped all their data.
> This doc codifies the guaranteed chain so any agent modifying auth/onboarding knows the invariants.

---

## 1. Chain overview

```
User signs up / OAuth login
    └─> organizations row created  (org_type, number_of_users, prefixed slug)
    └─> noctus_users row created   (org_id FK, org_role='owner')
    └─> user_metadata.org_id stamped  ← THIS is what the JWT carries
            └─> auth.jwt()->>'org_id' in Supabase RLS
                    └─> every product's RLS policy evaluates to the right org
```

**Invariant:** no account-creation path may exit without completing all three legs above.
`test_signup_org_guarantee.py` + `test_oauth_router.py` enforce this.

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

## 5. JWT claim chain

Supabase embeds `user_metadata` top-level in the JWT access token.

```sql
-- RLS helper function (migration 001):
CREATE OR REPLACE FUNCTION get_current_org_id() RETURNS uuid AS
$$ SELECT (SELECT (auth.jwt() ->> 'org_id'))::uuid; $$;
```

`auth.jwt() ->> 'org_id'` reads `user_metadata.org_id`.

**Stamp timing:**
- Email signup: stamped immediately after org insert via `update_user_by_id`
- OAuth signup: same, in the callback handler
- SSO session: re-stamped on each `/api/sso/session` call (picks up org changes)

**Legacy users (7 without org_id in metadata):** the stamp was missing on creation.
Fix: call `update_user_by_id` with `{"user_metadata": {"org_id": <noctus_users.org_id>}}` for each.
The `/api/sso/session` endpoint will also re-stamp on next SSO login.

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
