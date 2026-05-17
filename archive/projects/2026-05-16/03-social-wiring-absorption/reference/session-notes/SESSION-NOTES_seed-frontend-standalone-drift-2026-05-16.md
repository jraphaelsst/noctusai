# SESSION-NOTES — Seed frontend drift in standalone product deploys

**Date:** 2026-05-16
**From:** youtube-crawler WhatsApp-flow work (post Slice-2, live test)
**Severity:** Medium — error toasts on every page load in any standalone
(no-Core-platform) product deploy. Cosmetic-but-alarming; erodes trust
in an otherwise-working stack.
**Status:** Diagnosed; **seed-level fix outstanding** (no product-side
workaround applied — surfacing to noc as requested).

---

## Symptom

Fresh login to a standalone product (youtube-crawler, SQLite dev
backend, no Core platform running) shows three red "Servidor
indisponível — verifique se o backend está rodando" toasts:

- `/api/notificacoes`
- `/api/notificacoes/contagem`
- `/api/me/consents`

The backend is running fine. Two different root causes.

## Root cause 1 — pre-auth query race (`/api/notificacoes*`)

- With a valid JWT these endpoints return **200** (verified:
  `{"data":[],"total":0}` and `{"nao_lidas":0}`).
- Without a token they return **401**.
- The seed frontend's notification hooks fire on initial mount
  **before** `useSupabaseAuthInit` has restored/attached the session,
  so the first call goes out unauthenticated → 401 → the generic
  "servidor indisponível" toast. It self-heals on the next refetch
  once the token is present, but the toast already alarmed the user.

**Seed-fix direction:** gate auth-dependent queries on auth-ready
(e.g. `enabled: !!session` in the shared hooks, or a global
`AuthGate` that defers data hooks until `useSupabaseAuthInit`
resolves). The seed owns these hooks, so every product inherits the
race today.

## Root cause 2 — Core-only endpoint, no standalone fallback (`/api/me/consents`)

- `seed/lib/frontend/src/design-system/ai/useConsents.ts` hard-calls
  `GET /api/me/consents` (and `useUpdateConsent.ts` →
  `PUT /api/me/consents/{key}`), documented in-code as a **"Core
  platform endpoint"**.
- A standalone product backend does NOT expose it (verified: 404;
  product OpenAPI has no consents path). There is no Core platform in
  a single-product dev/standalone deploy.
- The hook has no standalone degradation → unconditional 404 → toast
  on every load, and the Consent settings page is dead in standalone.

**Seed-fix direction (pick one, seed-owned):**
1. Make the consent hooks **topology-aware** — no-op / hidden when no
   Core base URL is configured (mirror how `apiBase.ts` already
   reasons about deployment topology). Cleanest: the consent UI only
   renders when the platform is Core-attached.
2. Ship a **seed standard router** `consents` (like `whatsapp_admin`,
   `notificacoes`) so a standalone product can serve a local consent
   catalog from its own schema instead of depending on Core.
3. At minimum, **swallow 404 as "no consent catalog"** in
   `useConsents` so standalone deploys degrade silently instead of
   toasting a backend-down error.

Option 1 or 2 is the real fix; option 3 is the floor.

## Why this is seed-level (not product)

Both hooks live in `seed/lib/frontend/src` and are inherited verbatim
by every product via `@noctusai/lib`. No product can fix this without
forking the seed. Same class as the `VITE_SUPABASE_*` build-arg drift
noted in `SESSION-NOTES_vite-supabase-build-arg-2026-05-16.md`: the
seed assumes a topology (Core-attached, auth-already-ready) that a
standalone product deploy doesn't satisfy, with no graceful
degradation. The new-product methodology should document the
standalone-vs-Core-attached topology contract and which seed surfaces
require which.

No product-side patch was applied (per user instruction — surface to
noc, don't mask at the product layer).
