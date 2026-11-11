# Frontend Patterns

React + TypeScript + Vite. All products follow the same shape.

> House shape here; the general craft under it (React model, state, query keys, forms, accessibility, pt-BR formatting, performance, testing, security, UX copy) → `KB § PATTERNS/frontend/frontend-craft-canon.md`.

## Layer structure

```
pages/ → components/ → hooks/ → store/ → lib/
```

State split:
- **Zustand** — global UI state (sidebar collapsed, theme, etc.).
- **TanStack Query** — server state (all API data).
- Never put server state in Zustand. Never put transient UI state in TanStack Query.

## Mobile-first 3-tier responsive

- Base: mobile (320–639px).
- `sm:` / `md:` — tablet (640–1023px).
- `lg:` / `xl:` — desktop (1024px+).

**Test at 375 / 768 / 1440 px** before marking any UI work complete.

## Toasts

- Use `sonner` only. Never `react-hot-toast`, never custom toast systems.
- Error toasts: concrete message. No "Something went wrong." Say what went wrong.
- Success toasts: confirm the action ("Cliente cadastrado").
- Toasts are FEEDBACK only (green/red, X close). Events the user did not trigger (new lead, sync) are operational notifications - bell + neutral pop-up: `KB § PATTERNS/backend/notifications.md`.

## Constants & utils

- Constants: `src/lib/constants.ts` per product. No magic numbers inline.
- Utils: `src/lib/utils.ts` for tiny helpers. Larger domain utils → dedicated file.

## TanStack Query

- `enabled: !!user` — never query before auth resolves.
- `staleTime` — the seed `createQueryClient` default is 5 min (`seed/lib/frontend/src/query-client.ts:63`); override per query only with a reason (a realtime stream owns the cache ⇒ `Infinity`). Seed defaults vs TanStack's → `KB § PATTERNS/frontend/frontend-craft-canon.md` §3.1.
- **Writes write the cache — never invalidate-only.** A mutation puts what it knows into every entry it touches via `useCacheWriteMutation` (`@noctusai/lib/cache-writes`); `invalidateQueries` is only the background settle step after that write, never the write itself → `KB § PATTERNS/frontend/mutation-cache-writes.md`. Keys come from the entity's key factory so prefix writes reach every list → `KB § PATTERNS/frontend/frontend-craft-canon.md` §3.2.

> **Fixed 2026-11-05 (always-doc-the-trim).** The two bullets above replaced "`staleTime` — set appropriate (5–60s for most lists; 0 for write-heavy data)" and "`invalidateQueries` — invalidate by matching keys after mutations": the first contradicted the seed's 5-min default, the second the never-invalidate-only rule (`mutation-cache-writes.md`, keeper `check_mutation_invalidate_only`).

### Job-progress polling — `jobPolling`, never a bare `refetchInterval`

A query that polls while a server job runs (a batch `processando`, an extraction `queued/running`, a sync `running`) spreads `jobPolling(isActive, intervalMs)` from `@noctusai/lib` instead of hand-writing `refetchInterval: (q) => active ? ms : false`:

```ts
useQuery({ queryKey, queryFn, ...jobPolling((d: Lote | undefined) => !!d && emAndamento(d.status), POLL_MS) });
```

**Why.** TanStack pauses `refetchInterval` while `document.visibilityState === 'hidden'` (`refetchIntervalInBackground` defaults to `false`), and the seed `createQueryClient` sets `refetchOnWindowFocus: false`. A user who starts a 30 s job and switches tabs comes back to the progress they left — the SW CoreStudio "Gerar headlines" modal sat at "estrutura 3 de 5" and the roteiro modal at "Preparando as perguntas…" after the server had finished (2026-10-13). A progress UI frozen over a finished job is the time-axis twin of a lying loading state (`lying-loading-state.md`).

**What it sets.** While `isActive(data)`: `refetchInterval = intervalMs` (15 s after 2 min), `refetchIntervalInBackground: false` (a hidden tab pauses — nobody is watching; request budget 2026-11-10), and `refetchOnWindowFocus: 'always'` (tab visible again ⇒ immediate refetch, which is what fixes the original freeze). After 30 min of VISIBLE polling it stops and `useJobPollingStalled()` turns true; the layout-mounted `JobPollingPausedNotice` shows "Atualização automática pausada" with an Atualizar button (`resumeJobPolling`) — never a silently stale screen. While idle: no polling at all.

**Starting the job: hand off.** `isActive(data)` only sees what the last read returned. A write that queues the job and then invalidates races the worker — the refetch can land before the job's rows exist and the poll never starts (social-wiring F87, 2026-10-24). The write calls `handOffToPolling(qc, readKey)` instead: the `jobPolling` reads under `readKey` keep polling until they have seen the job run and settle (or `graceMs`). Keeper `check_job_start_without_handoff`; depth in `mutation-cache-writes.md` § Async jobs hand off to polling.

**Not for** live data with no terminal state (inbox, feed, presence) — that is a realtime stream (`inbox-chat-surface.md`), and a fixed-cadence dashboard refresh (`refetchInterval: 30_000`) stays a plain interval that rightly pauses in a hidden tab. Variable-cadence job pollers (a fast-then-slow window, a max-poll budget) do not fit the fixed-interval helper yet — extend `jobPolling` before hand-rolling a fourth.

## Hooks in dedicated files, always

Every domain entity gets its own hook file:
```
hooks/useContacts.ts
hooks/useCampaigns.ts
hooks/useTemplates.ts
```

Never inline hooks in page components, even for simple products. Products grow — extracted hooks are ready when a second page needs the same data. No refactoring needed.

## `useMemo` ≠ a side-effect channel

> **Moved 2026-11-05 (always-doc-the-trim, lossless).** The full section (rule, the 2026-05-25 social-wiring `Upload.tsx` incident, commit `27f24b20`) now lives in `KB § PATTERNS/frontend/frontend-craft-canon.md` §1.3 "Derive, don't sync", aligned with react.dev: derive in render, act in the event handler, `useEffect` only to synchronise with an external system — the old "side effects belong in `useEffect`" fix is refined there, not dropped.

> Follow-up (open; re-checked 2026-11-05 — still absent from both `package.json`s): `ts-morph` is NOT in the seed FE base devDeps (`seed/lib/frontend` · `seed/framework/frontend`) — add it so TypeScript AST edits (AST-first rule) work in product frontends without a per-product install. Surfaced by the same 2026-05-25 dispatch; see `project-history/worktree-salvage.ndjson` (`feat/sw-frontend-verify`).

## Sidebar nav groups — collapsed by construction

The canonical `Sidebar` organ (`@noctusai/lib/design-system` → `seed/lib/frontend/src/design-system/components/Sidebar.tsx`) starts **every** `NavGroup` closed. This is not a per-product convention to remember — it's baked into the organ: `NavGroup.defaultOpen` is `@deprecated` and **ignored** at render time, so a new group appended to a product's `navGroups` array is collapsed with zero extra code, and setting `defaultOpen: true` on it does nothing.

Two things keep the user oriented despite starting closed:
- The group containing the **currently active route** auto-expands (computed from `location.pathname` vs. each item's `href`).
- A user's manual expand/collapse choice **persists to `localStorage`** (best-effort, try/catch-wrapped — degrades to "nothing persists" if storage is disabled, never a crash) and survives a reload.

Don't hand-roll a `useState(true)` / `open` prop on a new nav-group-shaped component — consume `Sidebar`'s `NavGroup[]` via `navGroups` (products consume canonical organs). See `Sidebar.tsx`'s module docblock ("Collapsed-by-construction nav groups") for the full rationale, and its colocated `AppShell.test.tsx` for the behavioral tests (starts closed / active-route auto-open / toggle / persistence / localStorage-unavailable degrade).

### Nested groups and current-page marks (2026-10-05)

`NavGroup` may carry `groups: NavGroup[]` next to `items`, up to **4 levels** (L1 group > L2 group > L3 group > L4 leaf); flat configs are unchanged. Open state is an **accordion per level** (one open child per parent; clicking the open header closes it), and navigation auto-opens every group on the path to the current page. Only the **most specific matching href** is the current leaf (`aria-current="page"`, so `/admin` no longer lights up with `/admin/vendas`); the L1 group on the path gets an active style and intermediate groups an emphasized label. `filterNavByPageStatus` recurses through every level and drops groups left empty at any level. Open state persists per product (`noctus.sidebar.openGroups.<storageKey>`; `createProductLayout` passes a slug of `brandTitle`). Tests: `Sidebar.nesting.test.tsx`, `page-status.nested.test.ts`.

## Token refresh

Two complementary mechanisms:
- **Proactive**: `useActivityRefresh` — refresh when user interacts near expiry.
- **Reactive**: `onTokenExpired` in api-client — retry on 401 after refresh.

Both live in the seed's shared lib. Products don't implement refresh logic.

## API client

Use `api` from `@noctusai/seed/infra`:
```ts
import { api } from '@noctusai/seed/infra';
const res = await api.get('/api/contacts');
```

Never `fetch()` or `axios` directly. The seed api-client handles auth, correlation IDs, error shapes.

## Styling — Tailwind 4 with the v3 look pinned (2026-11-09)

One entry stylesheet styles the fleet: `seed/framework/frontend/src/index.css` (`@import "tailwindcss"`, the pinned v3 palette `tailwind-v3-palette.css`, then `tokens.css`, then a small v3-compat block). Each product's `src/index.css` imports it and adds `@config "../tailwind.config.ts"` — the seed factory (`createTailwindConfig`) stays the single theme/content/plugin source. PostCSS is `@tailwindcss/postcss` (no autoprefixer).

- **Two names changed what they draw:** write `shadow-xs` (v3's `shadow-sm`) and `outline-hidden` (v3's `outline-none`). v4's `shadow-sm`/`outline-none` compile but look different.
- **Brand glyphs** (`Facebook`, `Instagram`, `Youtube`) left lucide-react 1.x — import them from `@noctusai/lib/brand-icons` (same `LucideIcon` type).
- **Colours:** the default palette is v3's (pinned); deleting `tailwind-v3-palette.css` adopts v4's OKLCH palette — a visual decision, not a technical one.
- **Browser floor:** Safari 16.4+, Chrome 111+, Firefox 128+.
- **Use `tailwind-merge` ^3** (v2 does not know the v4 names).

Gate: keeper `check_tailwind_v4_class_names` (warn-first; escape `noc-allow: tailwind-v3-class — why`).

---

See also:
- `../03-SEED-ARCHITECTURE.md` — `createProductApp`, `createProductLayout`, `createProductInfra`
- `../04-SHARED-LIBRARY.md` — shared hooks + components catalog
