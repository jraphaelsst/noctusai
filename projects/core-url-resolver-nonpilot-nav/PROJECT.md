# core-url-resolver-nonpilot-nav — Project Document

- **Created:** 2026-05-25
- **Status:** 📋 Filed (follow-up) — pilot-first deferral from the `feat/seed-core-url-resolver` absorption (origin/dev `5021ce0c`)
- **Owner:** joaoraphaelsst · architect
- **Priority:** LOW — defense-in-depth; not a live bug once the dev `.env` `VITE_CORE_URL` is `8000` and prod bakes the real value.

---

## 1. Context & Problem

The SSO/core-URL absorption migrated the **seed** surfaces (`app.tsx`, `layout.tsx`, the `products/seed` template `Login/Landing/AcceptInvite` → `templates/product-seed` auto-synced) and the **pilots** (`erp` / `therapy` / `social-wiring`) to consume the canonical getters `env.CORE_URL` / `env.CORE_API_URL` instead of hand-rolling `import.meta.env.VITE_CORE_* || <literal>`. See [[feedback_sso_core_url_seed_resolution]] + `KB § PATTERNS/boundary-contract-tests.md` B1.

Per the **pilot-first refactor cadence** (`KB § PATTERNS/project-execution.md § 2.12`), the **non-pilot** products' nav sites are deferred to this later wave, gated on pilots-green (now satisfied — all three pilots built green 2026-05-25).

**Remaining hand-rolled sites (the nav class, stale `localhost:5173` default):**
- `products/adconnect/frontend/src/pages/{Login,Landing,AcceptInvite}.tsx`
- `products/daily-life/frontend/src/pages/{Login,Landing,AcceptInvite}.tsx`
- `products/dev-team/frontend/src/pages/{Login,Landing}.tsx`
- `products/knowledge-extractor/frontend/src/pages/{Login,Landing,AcceptInvite}.tsx`
- `products/personal-finance/frontend/src/pages/{Login,Landing,AcceptInvite}.tsx`

(Discovery: `grep -rn 'VITE_CORE_URL' products/*/frontend/src` → any line that is NOT `env.CORE_URL`.)

**Why LOW (not fixed in-flight):**
- The stale `localhost:5173` default is only hit when `VITE_CORE_URL` is **unset**. Dev now sets it (`.env` → `8000`), prod bakes the real value (`build-and-push.yml` `VITE_CORE_URL=https://core.noctusai.com`). So the default is latent, not live.
- None of these non-pilots is currently deployed/live (only core/erp/social-wiring are).

## 3a. Seed-first analysis

The formalization already shipped: the canonical getters `env.CORE_URL`/`env.CORE_API_URL` live in `seed/lib/frontend/src/env.ts`, and the seed-inherited surfaces + the new-product template already consume them. This follow-up is purely the **existing per-product copies** consuming the already-shipped seed primitive — no new seed work. Per-product page files (`Login`/`Landing`/`AcceptInvite`) are per-product by design (public pages), so they cannot be deduplicated into the seed; consuming the getter IS the correct fix.

## 4. Scope

Per file: add `import { env } from "@noctusai/lib";` and replace
`const CORE_URL = import.meta.env.VITE_CORE_URL || "http://localhost:5173";`
with `const CORE_URL = env.CORE_URL;` (+ the one-line canonical-resolver comment, matching the pilots).

## 6. Success criteria

- `grep -rn 'VITE_CORE_URL' products/{adconnect,daily-life,dev-team,knowledge-extractor,personal-finance}/frontend/src` returns **zero** hand-rolled `|| "http://localhost:..."` defaults (only `env.CORE_URL` consumption).
- `npx vite build` green for each of the five products.
- (Stretch / formalize candidate) a Stage-4 keeper `check_handrolled_core_url` that flags any `import.meta.env.VITE_CORE_*` outside `seed/lib/frontend/src/env.ts` — closes the recurrence structurally so it can never re-drift.
