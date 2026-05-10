# Feature — seed-absorption-batch-1 (rounds A–D)

> **What this is.** First wave of seed absorption driven by the new `noctus.seed.*` MCP tools. Removed 22 duplicate file groups across 11 products (15% reduction in total scan-detected duplication; 100% reduction of near-identical drift). Cross-validated with `scan_repetition` before and after every round; 3 product builds (ERP / Therapy / Core) verified green at the end.

- **Created:** 2026-05-10
- **Owner:** rapha
- **Trigger:** User directive — *"please evaluate the similar candidates of absorption. If they are, indeed, absorbable, please do."* + *"please dispatch our branching feature for quality and time optimizations, costing tokens for effectivity."*

## Snapshot delta

|                  | Before (2026-05-05, 9 products) | After (2026-05-10, 11 products) | Delta |
|------------------|---------------------------------|---------------------------------|-------|
| total dup groups | 145                             | 123                             | **−22** |
| byte_identical   | 34                              | 16                              | **−18** |
| near_identical   | 4                               | 0                               | **−4 (eliminated)** |
| divergent        | 107                             | 107                             | 0 |

(Worth noting: 2 new products were scaffolded in the interim — `youtube-crawler` joined the SSOCallback + tailwind groups before absorption — yet duplication went DOWN despite +2 products. Net signal stronger than the raw numbers.)

## Round A — SSOCallback (9 products)

**Finding:** All 9 product `SSOCallback.tsx` wrappers were unrouted dead code (zero consumers — same shape as the earlier `exceptions.py` shim). The seed's `createProductApp` already auto-mounts `/sso` at line 253 of `seed/framework/frontend/src/app.tsx`.

**Action:**
1. Pushed env-var reading (`VITE_CORE_API_URL`, `VITE_CORE_URL`) into the seed's `/sso` route mount, so deployments override without per-product wiring.
2. Deleted all 9 wrappers (adconnect, daily-life, erp-imobiliario, mailing, media-scheduling, personal-finance, seed, therapy-platform, youtube-crawler).

**Result:** SSOCallback group disappeared from the duplicates list.

## Round B — tailwind.config.ts factory (11 products)

**Finding:** 11 products had near-identical 11-line tailwind configs (only `"./index.html"` content-glob varied; core was the lone outlier without it).

**Action:**
1. Built `seed/framework/frontend/tailwind.config.factory.ts` exposing `createTailwindConfig({ extraContent, extraPlugins })` with `./index.html` in defaults (harmless on products without it — Tailwind silently ignores missing globs).
2. Rewrote 11 product `tailwind.config.ts` files to a 2-line factory call.
3. Added `tailwindcss-animate` to seed's `package.json` dependencies + ran `npm install` so the factory's `require()` resolves from the seed's node_modules (fixed initial build failure).

**Result:** Near-identical group eliminated. Remaining `tailwind.config.ts` 11x byte-identical = the 2-line wrapper itself; structural absorption is achieved.

## Round C — nginx.conf via envsubst template (3 products)

**Finding:** 3 products (core, erp-imobiliario, dev-team) had near-identical 19-line `nginx.conf` files differing only by `listen <port>`.

**Action:**
1. Created `seed/framework/frontend/nginx.conf.template` with `listen ${PORT};`.
2. Updated 3 Dockerfiles to `COPY` the template into `/etc/nginx/templates/default.conf.template` + `ENV PORT=<port>`. The official `nginx:alpine` image auto-substitutes `${PORT}` at startup — no extra entrypoint script needed.
3. Deleted the 3 per-product `nginx.conf` files.

**Result:** nginx.conf group disappeared.

## Round D — 19 shadcn UI components (erp + therapy)

**Finding:** 19 shadcn UI components were byte-identical between `products/erp-imobiliario/frontend/src/components/ui/` and `products/therapy-platform/frontend/src/components/ui/`. Other 9 products had no `ui/` folder.

**Action (parallel agent did most of the work; I verified + fixed build):**
1. 19 components moved into `seed/framework/frontend/src/components/ui/`.
2. `seed/framework/frontend/package.json` `exports` field added: `"./components/ui/*": "./src/components/ui/*.tsx"`.
3. ERP and Therapy import paths rewritten from `@/components/ui/X` → `@noctusai/seed/components/ui/X`.
4. Untouched: 31 ERP-only + 2 Therapy-only UI components (intentionally not absorbed since they're not duplicated).

**Components moved:** alert-dialog, avatar, badge, button, card, collapsible, dialog, dropdown-menu, input, label, popover, progress, scroll-area, select, separator, skeleton, switch, tabs, tooltip.

**Result:** UI duplicate groups dropped from 19 to 2 (`page-skeleton.tsx` and `textarea.tsx` remain divergent — different content per product, so not absorption candidates yet).

## Round dropping out — `app/exceptions.py` (4 products)

Bonus from the prior session — 4 vestigial `app/exceptions.py` re-export shims with zero consumers. Deleted.

## Self-absorption — noctus.seed.* skip lists

`scan_repetition.py` and `audit_drift.py` had N=2 duplication of file-walk skip lists. Extracted into `mcp/noctusai/tools/noctus/seed/_filewalk.py` (`SKIP_DIR_NAMES`, `SKIP_FILE_SUFFIXES`, `SKIP_FILENAMES`, `walk_files()`) before the future `absorb_file` tool would have made it N=3.

## Build verification

After all rounds:
- `products/erp-imobiliario/frontend` — `vite build` ✓ (25.27s)
- `products/therapy-platform/frontend` — `vite build` ✓ (7.53s)
- `products/core/frontend` — `vite build` ✓ (10.63s)

## Out of scope (intentionally deferred)

- **Trivial byte-identicals**: `frontend/postcss.config.js` (11x, 5 lines) + `frontend/src/index.css` (10x, 4 lines) + `frontend/eslint.config.js` (9x, 30 lines). Absorption complexity > marginal gain when files are this small. Could revisit if a per-product variation surfaces.
- **31 ERP-only + 2 Therapy-only UI components**: not duplicated, no absorption signal yet. They become candidates the moment a 3rd product needs the same component.
- **`page-skeleton.tsx` and `textarea.tsx`**: divergent content between ERP and Therapy. Either intentional or drift gone too far for trivial absorption — needs domain inspection.
- **107 divergent groups**: most are intentional (different products genuinely have different files at the same path). `noctus.seed.audit_drift` would surface the small-drift subset for re-sync candidates.

## Sub-tasks

- [x] Round A (SSOCallback) — env vars pushed into seed; 9 wrappers deleted.
- [x] Round B (tailwind factory) — factory + 11 product configs + tailwindcss-animate installed in seed.
- [x] Round C (nginx envsubst) — seed template + 3 Dockerfile updates + 3 file deletions.
- [x] Round D (UI components) — 19 components in seed; ERP + Therapy imports rewritten; 2 stragglers documented.
- [x] Self-absorption — `_filewalk.py` shared helper.
- [x] All builds green (ERP + Therapy + Core).
- [x] Scan delta documented (-22 groups, -18 byte-identical, -4 near-identical → 0).

## Methodology notes

- **Parallel-agent collision protocol activated and held.** I did not touch AdConnect work (handled by parallel agent). The Round D UI absorption was partially landed by another agent before I got to it; I verified, fixed the build, and documented — did not fight or duplicate.
- **The `noctus.seed.*` MCP tools paid for themselves immediately.** Each round was scoped + verified by `scan_repetition` deltas; the diagnostic loop (scan → absorb → re-scan) made each absorption explicit and checkable.
- **Branching-first dispatch attempt** — the engineers I dispatched landed minimal usable work (one's worktree was auto-cleaned, the other duplicated my Round B rather than executing Round D). Lesson: for tightly-scoped, well-understood sequential work, direct execution by the architect can be faster than dispatch overhead. Branching shines on truly independent multi-hour chunks.
