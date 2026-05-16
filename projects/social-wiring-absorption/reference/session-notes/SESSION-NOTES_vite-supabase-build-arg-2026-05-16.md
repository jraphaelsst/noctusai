# SESSION-NOTES — Vite Supabase build-arg defect (seed-level fix needed)

**Date:** 2026-05-16
**From:** youtube-crawler WhatsApp-flow-management work (Slice 1)
**Severity:** High — blanks the *entire* SPA for any product scaffolded
from the seed whose frontend Docker build doesn't pass Vite env.
**Status:** Fixed in youtube-crawler; **seed-level fix outstanding.**

---

## The defect

Every route of the youtube-crawler frontend rendered a blank white
page. Root cause:

- The seed frontend's `createProductSupabase` (`seed/lib/frontend/src/
  supabase.ts`) throws `Missing VITE_SUPABASE_URL or
  VITE_SUPABASE_PUBLISHABLE_KEY` at module-eval time when those vars
  are empty.
- Vite **inlines `import.meta.env.VITE_*` at `vite build` time** — they
  are a *build* concern, not runtime.
- The product `Dockerfile.frontend` ran `RUN npx vite build` with **no
  env**: root `.env` is not in the frontend build context, and Vite
  only auto-loads `.env` from the frontend project dir (which has only
  `.env.example`). So the two vars were empty in the bundle → boot
  throw → React never mounts → blank page on *every* route.

The values were present and correct in the workspace `.env` the whole
time. The build simply never consumed them. A normal browser reload
also kept serving the cached crashing bundle (hard-reload needed once
after the fix).

## Fix applied in youtube-crawler (reference implementation)

`Dockerfile.frontend` — before `RUN npx vite build`:

```dockerfile
ARG VITE_SUPABASE_URL
ARG VITE_SUPABASE_PUBLISHABLE_KEY
ENV VITE_SUPABASE_URL=${VITE_SUPABASE_URL}
ENV VITE_SUPABASE_PUBLISHABLE_KEY=${VITE_SUPABASE_PUBLISHABLE_KEY}
RUN npx vite build
```

`docker-compose.yml` — frontend service:

```yaml
build:
  args:
    VITE_SUPABASE_URL: ${VITE_SUPABASE_URL:-}
    VITE_SUPABASE_PUBLISHABLE_KEY: ${VITE_SUPABASE_PUBLISHABLE_KEY:-}
```

Only the two boot-critical vars are baked. `VITE_BACKEND_API_URL` is
deliberately NOT baked — `apiBase.ts` is runtime-detecting by design
(one artifact serves direct/proxy/tunnel); baking it would pin the
backend URL and break proxy/tunnel mode.

## Why this is a seed-level concern

This is **not** a youtube-crawler-specific bug. Any product scaffolded
through the seed system inherits the same broken shape, because:

1. The seed owns `createProductSupabase` and the hard throw.
2. The new-product methodology already states that on product creation
   the frontend is updated to the product's context — but that step
   does **not** currently wire the Vite build args, so every new
   product ships a frontend that blanks unless someone manually adds
   the ARG/ENV + compose args.

## Recommended seed-level fix (for the noc maintainer)

1. **Ship the build-arg wiring in the seed's frontend Docker template**
   (`templates/seed-workspace-docker/` or wherever the canonical
   `Dockerfile.frontend` + `docker-compose.yml` frontend service
   template lives) so scaffolded products inherit it by default.
2. **Add a step to the new-product methodology** (`KB § GUIDES/
   new-product.md` frontend section): "wire Vite build args for the
   product's required `VITE_*` (minimum: `VITE_SUPABASE_URL`,
   `VITE_SUPABASE_PUBLISHABLE_KEY`)" — explicitly the two the seed's
   `createProductSupabase` requires.
3. **Consider a build-time guard**: have the seed frontend fail the
   `vite build` (not just runtime boot) when required `VITE_*` are
   empty, so the breakage surfaces at image-build time with a clear
   message instead of as a silent blank page in the browser.
4. Optionally: a small codification candidate — a check that any
   product `Dockerfile.frontend` containing `vite build` also declares
   the required `VITE_SUPABASE_*` ARGs.

The runtime-vs-build distinction (only Supabase baked; backend URL
runtime-detected) should be captured in the methodology so future
products don't over-bake and break proxy/tunnel access.
