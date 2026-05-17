# 📩 Feedback from `noctusai-youtube-crawler` — seed needs dev auth + sqlite pre-wired

> **Date filed:** 2026-05-12
> **From workspace:** `noctusai-youtube-crawler` (sibling seed-workspace)
> **To:** noc architect / next agent working in this repo
> **Signal:** Read this before touching the seed-workspace template or any
> product scaffold. It identifies a recurring friction the next consumer
> will also hit if we don't fix it at the seed level.

---

## TL;DR

Every product born from the seed today ships with:

- ✅ A complete backend skeleton + OpenAPI surface
- ✅ A complete frontend skeleton + React Router + sidebar/topbar layout
- ✅ Docker + compose + Cloudflare quick-tunnel scaffold
- ❌ **NO ready-to-use auth path in dev mode**
- ❌ **NO pre-seeded test user the frontend can log in as**
- ❌ **NO SQLite local-dev DB pre-populated with that user**

The result: the moment an engineer (or the user) opens the frontend at
`/dashboard` or `/upload` or `/configuracoes`, the seed's auth gate
(`createProductApp`'s protected `routes` array) bounces them to
`/landing` or `/login`. The login form expects a real Supabase user
with a real org assignment. Without that, the page stays blank or
shows the landing CTA. **Every workspace will hit this wall.**

We hit this today, twice — first when the user tried
`localhost:8150/chat` (404 from the frontend nginx, separate bug), then
again when the unauthenticated tunnel visit to `/chat` rendered a dark
empty page because the seed auth gate ate the route silently. The fix
this time was to move `/chat` into `publicRoutes`. That's a workaround
— the structural answer lives in the seed.

---

## What happened (the trace)

1. Workspace built the platform chat agent at `/chat`, backend
   intentionally unauthenticated for v1 demo.
2. Frontend mounted `/chat` like every other route — under the seed's
   protected-route umbrella.
3. Unauthenticated tunnel hit → seed's auth gate suppressed the route
   → browser shows the global dark background + nothing else, no
   error in the console, no redirect spinner visible to the user.
4. Two debugging cycles later we discovered the gate ate the route
   and moved it into `publicRoutes`.

The whole drill could have been zero-cycle if the seed had shipped a
working dev auth path that recognized a pre-seeded test user.

---

## Why a productized seed should fix this (not each product)

The seed promises a "scaffolded product runs end-to-end on day one."
Today that promise is half-true:

- ✅ Backend boots and responds to `/api/health`.
- ✅ Frontend builds and serves `/landing`.
- ❌ Anything past `/landing` requires a working Supabase + an existing
  user + an org binding — none of which the seed provisions.

Every consumer either:
- spins up their own Supabase project + manually creates a user
  (high friction, weeks of "why doesn't login work" for new devs), or
- bypasses auth ad-hoc per product (what we just did — works, but
  resets the audit/RBAC posture and creates drift between products), or
- never accesses the protected UI in dev (which means UI bugs hide
  until staging).

This is a recurrence at N≥3 already (PF, ERP-imobiliario, this
workspace; therapy-platform's bootstrap has the same gap mid-flight
per its findings.md). **Per the noc recurrence rule, N=3 is "MUST
formalize."**

---

## Recommended implementation (concrete)

### 1. Pre-seeded SQLite dev DB

`apply_sqlite_migrations.py` is already scaffolded for products that
opt into `DATABASE_BACKEND=sqlite`. Extend it so:

- The first migration always creates an `auth_users` mirror table
  matching Supabase's auth shape (id, email, encrypted_password,
  raw_app_meta_data, raw_user_meta_data, created_at).
- A bootstrap row is inserted on every `apply_sqlite_migrations.py`
  run:
  ```
  id:    settings.local_dev_user_id    (already present in config)
  email: dev@noctusai.local
  org_id:settings.local_dev_org_id     (already present in config)
  role:  owner
  password_hash: bcrypt("noctus-dev")  # well-known dev password
  ```
- The same row populates the product's RLS-relevant tables (an
  `orgs` row, a `user_org_membership` row) so RLS doesn't 403
  the dev user out.

### 2. SQLite-aware auth path in the seed

`noctusai_seed.make_get_current_user` currently expects a real
Supabase JWT. Add a sibling factory `make_dev_auth_get_current_user`
that:

- Activates only when `DATABASE_BACKEND=sqlite` (so it can NEVER fire
  in production by mistake).
- Resolves to the pre-seeded dev user. No JWT verification.
- Returns the same `(user, token, org_id)` triple the prod path
  returns, so downstream code is identical.

Wire `make_get_current_user_org` to pick the dev variant automatically
when `DATABASE_BACKEND=sqlite`. Zero per-product code.

### 3. Auto-login on the frontend for SQLite mode

The seed's `createProductApp` reads `VITE_BACKEND_API_URL` etc. Add
a `VITE_DEV_AUTOLOGIN=true` flag that:

- On mount, fakes the supabase `auth.getSession()` to return a hard-
  coded dev session for `dev@noctusai.local` with the known dev org
  binding.
- Skips the Landing/Login redirect entirely — the dev user lands on
  the protected routes immediately.
- A loud `[DEV AUTOLOGIN]` console banner so no one ships this to
  prod without seeing it.

Like the backend variant, this MUST be off by default in production
builds. The flag goes on the `seed-workspace-docker` template
`.env.example` set to `true`, and on the prod compose set to `false`.

### 4. SSO-ready production posture preserved

The factory split keeps production code clean. Real Supabase Auth +
Google SSO + invite flow keep working untouched. The dev path is a
parallel implementation, never a code modification of the prod path.
This matches the "no monkey-patching, in production OR tests" rule
in CLAUDE.md.

### 5. Document in `KB § GUIDES/new-product.md`

The new-product guide should explicitly say: "Your scaffolded product
already has a working dev login — `dev@noctusai.local` / `noctus-dev`
— on the SQLite backend. Switch to Supabase when you wire real auth
in Phase 1."

---

## Why this also matters for the test surface

Existing tests bypass auth via `MockSupabaseClient` + `AuthClient`
fixtures. That works for unit tests but doesn't help an engineer
manually verify the UI. A pre-seeded dev login is the missing link
between "tests are green" and "I can click through the product."

---

## Worked example — what we did in `noctusai-youtube-crawler`

To unblock today's demo, we:

1. Added `DATABASE_BACKEND=sqlite` to the workspace `.env` and ran
   `apply_sqlite_migrations.py` (the seed already supports this
   path — kudos).
2. Patched `make_get_current_user_org` per-product so SQLite mode
   returns a stubbed local user. Lives in
   `products/youtube-crawler/backend/app/dependencies.py`. **This is
   the per-product duplication the seed should absorb.**
3. Marked `/chat` as `publicRoutes: [...]` to bypass the frontend
   auth gate entirely. **A scaffold-time auto-login would have made
   this unnecessary — the bypass would be reserved for genuinely
   public surfaces.**

When the seed implements §1-§3 above, those per-product hacks can be
removed in a deletion-shaped PR per consumer.

---

## Sign-off

The user explicitly requested this note land in noc's root so it
isn't missed. Filing it as a top-level markdown to maximize
notice probability (matches the convention of `NEXT-STEPS.md`,
`GOOGLE_OAUTH_NEXT_STEPS.md`, `LGPD-WARNINGS.md`).

When the seed-side work lands, this file can be deleted; until then,
it stays as a standing reminder.

— filed by Claude (Opus 4.7) working in `noctusai-youtube-crawler`,
  2026-05-12
