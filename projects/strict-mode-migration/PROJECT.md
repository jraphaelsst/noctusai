# TypeScript Strict Mode at the Seed Boundary — Project Document

> **What this project is.** Stand up TypeScript `strict: true` at the seed
> boundary (`seed/lib/frontend/` + `seed/framework/frontend/`) plus a CI
> gate that runs `tsc --noEmit` on both, so cross-product type contracts
> tighten at one place and propagate to every product via inheritance —
> *without* paying a per-product migration cost.
>
> **Re-scope of an older project.** This file replaces a 54-line
> 2026-04-27 checklist that planned strict-mode migration across all 8
> product frontends (~16-24h, low-leverage). The 2026-05-03 audit
> retired that ambition (cataloged as opt-in over time) and locked the
> narrower seed-boundary scope per user direction.
>
> **Run-by.** Designed for a fresh-session agent. §1 inlines context, §2
> quotes user direction, §5 names every file, §10 commands are
> copy-paste ready. Phase 0 audit already executed — findings are
> inlined in §6.

- **Created:** 2026-04-27 (original) · **rewritten 2026-05-03**
- **Last updated:** 2026-05-03
- **Status:** 📋 **READY FOR EXECUTION** — Phase 0 ✅ (audit complete; 3 findings inlined). Phases 1-4 ready for a separate agent / future session. Filed standalone so the current main-core-migrations-batch session can close.
- **Owner / stakeholders:** Raphael (joaoraphaelsst@gmail.com)
- **Project slug:** `strict-mode-migration` (subject=strict-mode, intent=migration; slug retained for path stability — `projects/main-core-migrations-batch/` references it)
- **Project location:** `projects/strict-mode-migration/` (cross-product / platform — the work lives at the seed boundary, not inside any one product)
- **Parent batch:** `projects/main-core-migrations-batch/` Tier 2 — Phase 2.a §7 round complete; this child is the Phase 2.b deliverable
- **Related docs:**
  - `KB § 03-SEED-ARCHITECTURE.md § Seed as Skeleton` — why seed-boundary work propagates to products
  - `KB § PATTERNS/accept-with-rationale.md` — destination for the "per-product strict is opt-in over time" entry (Phase 5 catalog deliverable)
  - `KB § PATTERNS/project-execution.md § 0` — execution workflow this child runs through

---

## 1. Context & Purpose

### What problem this project solves

Cross-product type contracts live in two seed-boundary packages: `@noctusai/lib` (`seed/lib/frontend/`) and `@noctusai/seed` (`seed/framework/frontend/`). Today both have `strict: false` (lib) or no tsconfig at all (framework). When a lib helper returns `User | undefined` but the type signature says `User`, no one catches it — the bug rides the inheritance edge into every product.

Because product frontends import seed types as **source** (workspace links, not built `.d.ts` files), the type strictness of the seed determines the type strictness of what every consumer sees. Tightening strict at the seed therefore tightens types for all 8 products without each product having to opt into strict mode itself. This is the high-leverage subset of strict-mode work.

### What "done" looks like

- `seed/lib/frontend/tsconfig.json` has `"strict": true` and `tsc --noEmit` is green
- `seed/framework/frontend/tsconfig.json` exists with `"strict": true` and `tsc --noEmit` is green
- A CI workflow runs both `tsc --noEmit` checks on every PR; the gate fires on deliberate type errors
- `KB § PATTERNS/accept-with-rationale.md` has a documented entry stating per-product strict mode is intentionally opt-in over time (not a campaign), so future agents don't reopen the question
- The original 8-frontend ambition is closed-by-rationale, not orphaned

### Why this is a project, not a one-shot script

- **The lib has never been type-checked standalone** (Phase 0 finding — see §6 Phase 0). 24 `TS2307` errors fire today from missing peer-dep types. Phase 1 is "stand up the standalone tsc check" before strict-mode gains can even be measured.
- **The framework has no tsconfig at all** — adding one is a real architectural decision (jsx mode, lib targets, types arrays) that needs to match how products consume it.
- **CI gate is the durability point.** Without it, the strict flip rots within months as new code lands without strict checking.
- **The original 8-frontend plan needs a deliberate retirement** — silently dropping it is a slip; cataloging it as accept-with-rationale is the correct landing per `feedback_triage_at_decision_time.md`.

---

## 2. Confirmed constraints

User direction during the 2026-05-03 §7 round (parent batch Phase 2.a):

- **Q: "does this strict mode project does actually add value to the project?"** → Agent surfaced honest assessment that full 8-frontend sweep is low-leverage (16-24h, mostly mechanical `!`-assertion fixes that mask the same null risk).
- **Q: User picked narrower path?** → "i liked the narrower path, let's strict the fw + lib"
- **Q: Scope decision after Phase 0 surfaced larger work than initially advertised?** → "lets go with C. file it as a separate project so i can clear this session"

Implications:
- **Scope is locked to fw + lib + CI gate.** Per-product strict is **explicitly retired** as a campaign and gets cataloged as opt-in over time in Phase 5.
- **Filed standalone for separate execution.** Parent batch `main-core-migrations-batch` does not block on Phases 1-4; this child runs to completion in a fresh session/agent.
- **Standalone tsc infrastructure is in scope.** Phase 0 audit revealed the lib has no standalone tsc today. Phase 1 fixes that — it's load-bearing for the strict-mode delivery, not a separate concern.

Carried-in constraints from CLAUDE.md / memory:
- **No `!` non-null assertion fixes** unless the value is genuinely guaranteed by upstream invariants. Default fix is a real null check or tightened upstream type. (`feedback_no_silent_errors.md`.)
- **No bypassing tsc errors** with `// @ts-ignore` or `// @ts-expect-error` outside genuinely third-party-broken cases.
- **Commit per phase, push at project close** (`feedback_no_auto_commit.md`).
- **Three-way doc sync** at close — KB / CLAUDE.md / memory move together for any new methodology this surfaces (`feedback_three_way_doc_sync.md`).

---

## 3. Design principles

### 3.1 Seed-boundary gate, not per-product flag flip

Strict mode lands at one place: the workspace packages products import from. The flip's value comes through the inheritance chain — products get strict-quality types whether or not they themselves are strict. This is why the narrow scope works.

### 3.2 Standalone tsc infrastructure first

Today the lib's tsc fails 24 times on module-resolution before strict-mode rules can fire. Phase 1 installs peer-dep types as `devDependencies` (not as `dependencies` — the runtime-peer relationship doesn't change; only the standalone-typecheck path gains them). This is a normal pattern for workspace packages whose peers are provided by consumers.

### 3.3 Lib first, framework second

Lib has 52 files (larger surface, has tsconfig already). Framework has 5 files (smaller, depends on lib). Tighten lib → framework picks up tightened types automatically when its tsconfig is added. Reverse order means re-fixing.

### 3.4 No `!`-assertion masking

A non-null assertion on a value that's actually nullable is a silent error wearing a strict-mode costume. Default fix is a real null check or tighter upstream type. Use `!` only when the invariant is genuinely upstream-guaranteed (e.g. ref captured after mount). Capture every `!` introduced in §11 with a one-line justification.

### 3.5 Retire the per-product ambition with paperwork

Per `feedback_triage_at_decision_time.md`: "accept" is a real landing — silently dropping the 8-frontend plan is a slip. Phase 5 files an accept-with-rationale entry that future agents see when they grep for "strict mode" intent.

---

## 3a. Seed-first analysis (REQUIRED)

Run of the six-question checklist (`KB § GUIDES/seed-first-design.md`):

1. **Is the contract identical for every product?** YES — every product imports types from `@noctusai/lib` and `@noctusai/seed`; tightening once tightens everywhere.
2. **Is the data source product-specific?** N/A — no data; type-checking infrastructure.
3. **Is the placement product-specific?** NO — placement is `seed/lib/frontend/` and `seed/framework/frontend/`. Per-product code count = 0.
4. **Is the visibility / permission rule the same?** N/A.
5. **Does the seam already exist in seed?** YES — the workspace packages (`@noctusai/lib`, `@noctusai/seed`) ARE the seam. Each has (or will have) its own `tsconfig.json` + `package.json` + `tsc --noEmit` script.
6. **Default-on or opt-in?** **Default-on at the seed boundary.** Products remain non-strict by default (their own tsconfig says so) — that's an opt-in concern handled separately. The seed gate is non-negotiable once landed.

**Litmus — per-product code count this design requires:**

- [x] **0 lines** — all changes land in `seed/{lib,framework}/frontend/`. No product file is touched. Products inherit tightened types via existing imports.

**Phase plan implication:** §6 phases are ordered by dependency (lib before framework) and infrastructure-before-flag (peer-dep install before strict flip). No per-product replication framing.

---

## 4. Scope

**In scope:**
- `seed/lib/frontend/tsconfig.json` → `strict: true`, with all errors fixed
- `seed/framework/frontend/tsconfig.json` → created, `strict: true` from day 1, with all errors fixed
- Peer-dep types installed as `devDependencies` in both packages (so standalone tsc resolves modules)
- `npm run check` (or equivalent) script in both `package.json` files
- CI workflow (GitHub Actions) that runs both checks on every PR + push to main
- One catalog entry in `KB § PATTERNS/accept-with-rationale.md` documenting per-product strict mode as opt-in over time

**Out of scope:**
- Strict mode in any of the 8 product frontends (`products/*/frontend/tsconfig.json` stays as-is per user direction)
- ESLint rule additions (separate concern; can layer on later if value emerges)
- Pre-commit hook (CI gate is the durability point; pre-commit is opt-in)
- Refactoring lib/framework code beyond what strict mode mechanically requires
- Adding new types or rewriting Supabase generic patterns (separate project if it surfaces)

---

## 5. Architecture / current state of the seed boundary

### 5.1 `seed/lib/frontend/` (52 .ts/.tsx files)

Source layout (`src/`):
- `api.ts`, `auth.ts`, `env.ts`, `hooks.ts`, `index.ts`, `llm.ts`, `notifications.ts`, `page-status.ts`, `query-client.ts`, `roles.ts`, `sso.ts`, `stores.ts`, `supabase.ts`, `utils.ts`
- `components/` — `AuthProvider.tsx`, `ErrorBoundary.tsx`, `SSOCallback.tsx`, `index.ts`
- `design-system/` — `useTheme.ts`, `useActivityRefresh.ts`, plus subdirectories `ai/`, `components/`, `ui/`, `tailwind.config.base.ts`

Current `tsconfig.json` (lines 1-19):
- `target: ES2020`, `lib: ["ES2020", "DOM", "DOM.Iterable"]`, `module: ESNext`, `moduleResolution: bundler`
- `jsx: react-jsx`, `noEmit: true`, `skipLibCheck: true`
- **`strict: false`** ← the flip

Current `package.json`:
- `name: @noctusai/lib`, `type: module`, `main: src/index.ts`
- Peer deps include `@supabase/supabase-js`, `@tanstack/react-query`, `clsx`, `react`, `sonner`, `tailwind-merge`, `zustand`
- **Missing from peer-deps in node_modules** (causing 24 TS2307s): `lucide-react`, `@radix-ui/react-collapsible`, `@radix-ui/react-hover-card`, `tailwindcss`, plus the workspace-link to `@noctusai/seed` (for `@noctusai/seed/infra` import)

### 5.2 `seed/framework/frontend/` (5 .ts/.tsx files)

Source layout (`src/`):
- `app.tsx` — `createProductApp` factory
- `infra.tsx` — supabase + react-query providers
- `layout.tsx` — default layout shell
- `index.ts` — re-exports
- `pages/ConsentSettingsPage.tsx` — default consent page

Current state:
- `package.json` (`name: @noctusai/seed`, `type: module`, `main: src/index.ts`) ✅
- `vite.config.factory.ts` ✅, `vitest.config.factory.ts` ✅
- **No `tsconfig.json`** ← Phase 3 creates this
- Peer deps: `@radix-ui/react-tooltip`, `@supabase/supabase-js`, `@tanstack/react-query`, `react`, `react-dom`, `react-router-dom`, `sonner`

### 5.3 Phase 0 baseline measurements

Run from `seed/lib/frontend/` using framework's tsc binary:

```
./../framework/node_modules/.bin/tsc --noEmit -p .
→ 24 errors, all TS2307 (cannot find module)

./../framework/node_modules/.bin/tsc --noEmit --strict -p .
→ 24 errors, all TS2307 (strict-mode errors masked by resolution failures)
```

Strict-mode error count is **unmeasurable** until Phase 1 lands the peer-dep installs.

### 5.4 Why source-import (no build step) makes this work

Both packages export `src/*.ts` directly via `package.json#main` and `exports`. Consumers (products) get the raw `.ts` files at type-check time, so the strict-quality of the seed's types directly affects what consumers see. This is also why a build-step wouldn't help here — it would just emit weaker `.d.ts` files.

---

## 6. Implementation phases

**Phase status icons:** no icon = pending · `⏳` = partial · `✅` = complete · `❌` = blocked.

### Phase 0 — Audit ✅ (executed 2026-05-03)

- [x] Surveyed strict state across 11 frontend tsconfigs (8 products + 2 seed packages + design-system base) — all `strict: false` or missing.
- [x] Counted lib files (52) and framework files (5).
- [x] Ran `tsc --noEmit -p .` against lib using framework's tsc binary — found 24 TS2307 module-resolution errors.
- [x] Re-ran with `--strict` flag — same 24 errors (strict-mode errors masked by resolution failures, can't be measured yet).
- [x] Verified `seed/framework/frontend/tsconfig.json` is missing entirely.
- [x] Confirmed lib + framework export source files (no build step) so strict propagates to product consumers via raw `.ts` import.

**Improvements / findings:**
- The lib has **never been tsc-checked standalone**. This is the blocker; Phase 1 is "stand it up." The work is bigger than initially advertised (~2-4h) because of this — realistic estimate is now 4-8h end-to-end.
- The framework has 5 files only — Phase 3 is small.
- The lib has lucide-react / radix imports that need installation as devDeps. These are real peer relationships; products provide them at runtime, but tsc-time needs them for module resolution.
- Original 8-frontend ambition is being retired in Phase 5 as opt-in over time; this prevents a future agent from re-opening the question.

### Phase 1 — Lib: install peer-dep types + standalone tsc green (non-strict) ✅ (executed 2026-05-10)

Goal: zero `tsc --noEmit -p .` errors in lib's current `strict: false` state.

- [x] From `seed/lib/frontend/`, install peer-dep types as devDeps:
  ```
  npm install --save-dev \
    lucide-react \
    @radix-ui/react-collapsible \
    @radix-ui/react-hover-card \
    tailwindcss
  ```
- [x] Resolve the `@noctusai/seed/infra` import — this is a workspace cross-package reference. Install via `npm install --save-dev ../framework` (workspace link) or add path-mapping in tsconfig (preferred — keeps node_modules clean). **Done via path-mapping.**
- [x] Run `tsc --noEmit -p .` — confirm zero errors.
- [x] Add `"check": "tsc --noEmit"` script to `package.json`.

**Verification:**
- `npm run check` exits 0 ✅
- `git status --short -- seed/lib/frontend/` shows `package.json`, `package-lock.json`, `tsconfig.json` modified **plus 1 source edit** (`src/design-system/tailwind.config.base.ts` — surfaced bug fix, see Improvements).

**Improvements / findings:**
- **Surfaced bug:** Installing `tailwindcss` exposed a non-strict TS2322 in `src/design-system/tailwind.config.base.ts` line 20: `darkMode: ["class"]` should be `darkMode: "class"` (tuple form requires `[mode, selector]` 2-tuple per `DarkModeStrategy`; single-string form is canonical and behaviorally equivalent to `["class", ".dark"]` default). Applied inline. The bug went unnoticed because tailwindcss types were not previously installed.
- **Phase 0 baseline drift:** Phase 0 audit ran with framework's tsc binary against a working-tree state that had peer deps available; this Phase 1 worktree starts from a cleaner state, so the initial `npm install` (existing devDeps) was a precondition before the 4 documented installs.
- **Additional in-src test deps needed:** `src/components/FakeModeBadge.test.tsx` lives under `src/` (included in tsconfig's `include`), so vitest + @testing-library/react + @testing-library/jest-dom were installed as devDeps. The Phase 0 audit list of 4 packages was incomplete for a clean install — log entry: **test-imports-from-src-counted as peer-dep types**.
- **Path mapping needs to recurse:** Mapping `@noctusai/seed/infra` to `../../framework/frontend/src/infra.tsx` works but `infra.tsx` itself imports from `@noctusai/lib/*`, requiring a SELF path mapping for the lib package. Added `@noctusai/lib` + `@noctusai/lib/*` entries pointing to `./src/*.ts` / `./src/*/index.ts` / `./src/*.tsx`. The Vite-injected `import.meta.env` typing also needed `vite/client` added to `types[]`.
- **Latest-version drift:** Initial install of `tailwindcss` resolved to v4 (current latest) which would have been a major-version mismatch against framework's `^0.462.0` Lucide and Tailwind v3 ecosystem. Re-installed with explicit `tailwindcss@^3.4.0` / `lucide-react@^0.462.0` / `vitest@^2.1.8` / `typescript@^5.8.3` etc. to match the framework. **Lesson:** for workspace-cross packages, peer-dep installs should explicitly pin to the major versions used by the other workspace packages.
- **Architectural inconsistency caught:** `seed/framework/frontend/package.json` `exports` block does not declare `./infra`, yet `seed/lib/frontend/src/design-system/ai/*` imports `@noctusai/seed/infra`. This currently works at runtime only because product Vite resolvers fall through to file paths; a stricter consumer (TypeScript without path-mapping; modern bundlers using export-conditions strictly) would break. **Recommend Phase 3 add `"./infra": "./src/infra.tsx"` to framework's exports block** so the package's public surface matches its consumers' imports.

### Phase 2 — Lib: flip strict + fix errors ✅ (executed 2026-05-10)

Goal: zero `tsc --noEmit -p .` errors with `strict: true`.

- [x] Flip `tsconfig.json`: `"strict": true` (replace `"strict": false`).
- [x] Run `tsc --noEmit -p .` — capture the actual strict-mode error count (now measurable). **Captured: 1 error (TS2322 in framework/frontend/src/infra.tsx assigning `createNotificationHooks` return to lib's `NotificationHooks` type).**
- [x] Fix errors per principle 3.4. Common categories expected:
  - **Implicit any** — none surfaced.
  - **Null/undefined** — none surfaced.
  - **Missing return types on exported functions** — none surfaced.
  - **Index signature** — none surfaced.
  - **Type contract mismatch (the actual category):** lib's `NotificationHooks.useMarcarComoLida: () => MutationResult` had `MutationResult.mutate: (arg?: unknown) => void`, which is contravariant-incompatible with react-query's `UseMutateFunction<TData, TError, TVariables>` (variables is `string`, not `unknown`). **Fix:** generic-parameterize `interface MutationResult<TVariables = void>` with `mutate: (variables: TVariables) => void`; tighten `useMarcarComoLida: () => MutationResult<string>` and `useMarcarTodasComoLidas: () => MutationResult<void>`. The defaulted type parameter keeps backward compatibility for any unknown consumer; the parameterized return tightens the seed contract to match the actual react-query hook signatures. Applied via ts-morph codemod (Engineer A pattern in `/tmp/strict-mode/`).
- [x] Verify zero errors. **`npm run check` exits 0.**

**Improvements / findings:**
- **Pre-strict-flip error count:** 0 (Phase 1 baseline, confirmed by `npm run check` before the flip).
- **Post-flip / pre-fix error count:** 1 (one TS2322 in `seed/framework/frontend/src/infra.tsx` line 81 — the `<SharedNotificationBell hooks={notificationHooks} />` site, because `notificationHooks` is built from `createNotificationHooks(...)`'s react-query mutation hooks whose `UseMutateFunction<TData, TError, TVariables>` couldn't unify with the lib's narrower `(arg?: unknown) => void`). The error fires in framework/, but its ROOT is in the lib's NotificationHooks type contract — fixing in lib closes both. (Note: framework/frontend has no tsconfig yet — Phase 3 — so this error only surfaces from the lib's tsc reach via `paths` mapping. Once Phase 3 adds framework's own tsconfig, no additional fix needed here.)
- **Post-fix error count:** 0.
- **No `!` non-null assertions introduced.** Fix was purely a generic-parameterization on an interface.
- **Why generic-parameterize rather than widen the consumer:** The alternative was `mutate: (arg?: string) => void` directly on the un-parameterized interface, but `useMarcarTodasComoLidas` mutates with no variables, so a single hard-coded signature can't fit both. Parameterizing (`MutationResult<TVariables = void>`) makes the seed contract carry the variables-type discriminator that react-query already uses — keeping the seed type generic where the underlying SDK is generic. Defaulted to `void` so an unparameterized reference behaves the same as the old narrow shape (mutate with no args).
- **Why fix in lib rather than framework:** Both consumers (framework's infra.tsx + future product wiring) build their hooks via `createNotificationHooks` returned from the lib. Tightening the lib's contract once propagates to every consumer; widening only the framework would leave the same gap open for any future direct consumer.
- **AST-first compliance:** Codemod in `/tmp/strict-mode/fix-mutation-result.ts` using ts-morph (added `TypeParameter`, updated `mutate` property type, retyped two `NotificationHooks` members). No sed/regex on TS. Pattern mirrors Engineer A's Phase 1 codemod approach.
- **Test infra gap (out of scope, surfaced for Phase 3+ or follow-up):** `npm test` fails with `Cannot find package 'jsdom'` because vitest's jsdom environment is referenced in `vitest.config.ts` but `jsdom` isn't installed as a devDep. The strict-mode work doesn't depend on this (gate is `npm run check`, which is green), but Phase 1 missed it. Suggest follow-up: add `jsdom` to devDependencies of `seed/lib/frontend` so `npm test` runs from a clean install.

### Phase 3 — Framework: add tsconfig + strict from day 1

Goal: `seed/framework/frontend/tsconfig.json` exists with `strict: true` and zero errors.

- [ ] Create `seed/framework/frontend/tsconfig.json`. Mirror lib's config except start with `strict: true`:
  ```json
  {
    "compilerOptions": {
      "target": "ES2020",
      "lib": ["ES2020", "DOM", "DOM.Iterable"],
      "module": "ESNext",
      "moduleResolution": "bundler",
      "allowImportingTsExtensions": true,
      "isolatedModules": true,
      "moduleDetection": "force",
      "noEmit": true,
      "jsx": "react-jsx",
      "strict": true,
      "skipLibCheck": true,
      "noUnusedLocals": false,
      "noUnusedParameters": false,
      "types": ["node"],
      "paths": {
        "@noctusai/lib": ["../lib/src/index.ts"],
        "@noctusai/lib/*": ["../lib/src/*"]
      }
    },
    "include": ["src"]
  }
  ```
- [ ] Install any missing peer-dep types as devDeps (the framework's 5 files import less than the lib; survey via TS2307s and install accordingly).
- [ ] Run `tsc --noEmit -p .` — fix errors.
- [ ] Add `"check": "tsc --noEmit"` script to `package.json`.

### Phase 4 — CI gate

Goal: PRs that introduce strict-mode regressions fail CI.

- [ ] Add `.github/workflows/seed-typecheck.yml`:
  - Runs on PRs touching `seed/lib/frontend/**` or `seed/framework/frontend/**` and on push to main
  - Two jobs: `lib-typecheck` (cd lib && npm ci && npm run check), `framework-typecheck` (cd framework && npm ci && npm run check)
  - Fails the workflow on any tsc error
- [ ] Verify gate fires: introduce a deliberate type error in a throwaway branch, push, observe CI failure, then revert.
- [ ] Document the gate in `KB § 03-SEED-ARCHITECTURE.md § Seed contract` so future agents see "type-checking the seed boundary is part of the contract."

### Phase 5 — Close + paperwork

- [ ] File an `accept-with-rationale.md` entry stating per-product strict mode is intentionally opt-in (not a campaign):
  - **Pattern:** Per-product TS strict mode
  - **Decision:** Opt-in over time, not a coordinated campaign
  - **Rationale:** 8 product frontends × ~2-3h each = 16-24h of mostly mechanical `!`-assertion fixes that mask the same null risk. Strict at the seed boundary captures the high-leverage subset; per-product strict is a quality-of-life improvement individual maintainers can opt into when they're touching a frontend deeply. Recurrence flips this toward "formalize" if 3+ product frontends end up wanting strict on their own.
  - **Trigger to revisit:** Any product frontend independently flipping strict, OR a real null-safety incident traced to a non-strict product file.
- [ ] Update `projects/main-core-migrations-batch/PROJECT.md` §11 with this child's outcomes.
- [ ] Three-way doc sync verification (`bash scripts/verify-kb-sync.sh`).
- [ ] Final commit + push.
- [ ] Delete this folder.

---

## 7. Open questions

All material questions resolved by user direction 2026-05-03 (see §2). Remaining minor:

1. **Path mapping vs. workspace symlink for `@noctusai/seed/infra` in lib?** *Default rec:* tsconfig `paths` with relative path to framework's `src/`. Cleaner than node_modules symlinks; no ambiguity at type-check time. Decide during Phase 1 execution.
2. **CI workflow path filtering — touch-files vs. always-run?** *Default rec:* always-run (the seed boundary is small; <30s tsc is fine to pay on every PR). Decide during Phase 4 execution.

---

## 8. Dependencies & blockers

- **Parallel-agent collision protocol.** At handoff time (2026-05-03), the current working tree has in-flight work from other agents (`scheduling-engine-seed`, `session-review-baseline`, `send-message-consolidation`, MCP `session_review` tool). The executing agent must check `git status --short` at start and stage explicitly to avoid touching files outside this project's scope. Per-phase commit only after parallel agents have finished or the staged set is verified clean.
- **`npm install` reliability.** The lib's `node_modules` was confirmed installable (2026-05-03). If it fails on next run, check Node version + npm registry access.
- **`KB § PATTERNS/accept-with-rationale.md` is currently in working-tree-modified state** by a parallel agent (2026-05-03 state). Phase 5 catalog-entry must wait for that edit to land first (or be co-edited carefully). Defer if collision risks fire.

---

## 9. Success criteria

Measurable, verifiable.

- [ ] `cd seed/lib/frontend && npm run check` exits 0 with `"strict": true` in tsconfig
- [ ] `cd seed/framework/frontend && npm run check` exits 0 with `"strict": true` in a tsconfig that exists
- [ ] CI workflow `.github/workflows/seed-typecheck.yml` exists; runs both checks on PRs; deliberate type error fails the workflow
- [ ] `KB § PATTERNS/accept-with-rationale.md` has an entry for per-product TS strict mode as opt-in
- [ ] Zero `!` non-null assertions added without a §11-logged invariant justification
- [ ] No product code touched (`git diff --stat` since branch start shows only `seed/{lib,framework}/frontend/`, `.github/workflows/`, `KB § PATTERNS/accept-with-rationale.md`, this PROJECT.md)
- [ ] Parent batch `main-core-migrations-batch/PROJECT.md` §11 updated with this child's close
- [ ] §11 closing entry written; folder deleted; final push complete

---

## 10. How to use this plan

```bash
# ── Phase 0 baseline replay (already executed; safe to re-run) ──
cd /Users/rapha/Documents/repository/NoctusAI/noctusai
cd seed/lib/frontend
./../framework/node_modules/.bin/tsc --noEmit -p .              # expect 24 TS2307 errors today
./../framework/node_modules/.bin/tsc --noEmit --strict -p .     # same 24 errors (masked)

# ── Phase 1 — install peer types ──
npm install --save-dev lucide-react @radix-ui/react-collapsible @radix-ui/react-hover-card tailwindcss
# Add tsconfig "paths" mapping for @noctusai/seed/infra → ../framework/src/
./node_modules/.bin/tsc --noEmit -p .                            # expect 0 errors
# Add "check": "tsc --noEmit" to package.json

# ── Phase 2 — flip strict ──
# Edit tsconfig.json: "strict": false → "strict": true
npm run check                                                    # capture strict-mode error count
# Fix errors; iterate; final npm run check exits 0

# ── Phase 3 — framework tsconfig + strict from day 1 ──
cd ../framework
# Create tsconfig.json per §6 Phase 3 template
# Install missing peer types if any TS2307s fire
npm run check                                                    # exits 0

# ── Phase 4 — CI gate ──
# Create .github/workflows/seed-typecheck.yml per §6 Phase 4
# Push deliberate type error on a test branch; verify CI fails; revert

# ── Phase 5 — paperwork + close ──
# Add accept-with-rationale entry
# Update parent batch §11
bash scripts/verify-kb-sync.sh
# Final commit + push; delete this folder
```

---

## 11. Change log

| Date | Change | By |
|---|---|---|
| 2026-04-27 | Original 54-line PROJECT.md drafted as TS strict-mode migration across all 8 frontends (~16-24h, never executed). | (prior session) |
| 2026-05-03 | **Re-scope to seed-boundary + Phase 0 ✅.** Parent batch `main-core-migrations-batch` Phase 2.a §7 round surfaced honest cost/leverage tradeoff; user picked narrower scope ("strict the fw + lib") then accepted Option C (full fw + lib + CI gate scope) and asked for the project to be filed standalone for separate execution. Doc rewritten to PROJECT-TEMPLATE.md format. Phase 0 audit fired and surfaced 3 findings: (1) lib has never been tsc-checked standalone (24 TS2307 errors from missing peer-dep types — strict-mode errors are masked by resolution failures and can't be measured yet); (2) framework has no tsconfig.json at all; (3) lib + framework export source `.ts` directly so strict tightens types at source-import boundary, propagating to all 8 products via inheritance without per-product migration. Honest re-estimate: 4-8 hours (vs. originally quoted 2-4h). Original 8-frontend ambition retired and slated for accept-with-rationale paperwork in Phase 5. **Status: 📋 READY FOR EXECUTION** — Phases 1-4 ready for fresh-session agent. | Claude Opus 4.7 |
| 2026-05-10 | **Phase 2 ✅.** Flipped `seed/lib/frontend/tsconfig.json` `strict: false → strict: true`. Single TS2322 error fired in `framework/frontend/src/infra.tsx:81` (contravariance: lib's `MutationResult.mutate: (arg?: unknown) => void` couldn't unify with react-query's `UseMutateFunction<TData, TError, TVariables>` where `TVariables = string` for `useMarcarComoLida`). **Fix:** generic-parameterize `interface MutationResult<TVariables = void>` in `seed/lib/frontend/src/design-system/components/NotificationBell.tsx`, retype `useMarcarComoLida: () => MutationResult<string>` + `useMarcarTodasComoLidas: () => MutationResult<void>`. **Tooling:** ts-morph codemod in `/tmp/strict-mode/fix-mutation-result.ts` (Engineer A pattern). **`!` non-null assertions added:** 0. **`any` added:** 0. **Files touched:** 2 (`tsconfig.json`, `NotificationBell.tsx`). **Verification:** `cd seed/lib/frontend && npm run check` exits 0. **Out-of-scope finding surfaced:** `npm test` fails on missing `jsdom` devDep (Phase 1 gap; doesn't block Phase 2 gate). | Engineer (strict-mode Phase 2 subagent) |
