# Frontend Patterns

React + TypeScript + Vite. All products follow the same shape.

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

## Constants & utils

- Constants: `src/lib/constants.ts` per product. No magic numbers inline.
- Utils: `src/lib/utils.ts` for tiny helpers. Larger domain utils → dedicated file.

## TanStack Query

- `enabled: !!user` — never query before auth resolves.
- `staleTime` — set appropriate (5–60s for most lists; 0 for write-heavy data).
- `invalidateQueries` — invalidate by matching keys after mutations.

### Job-progress polling — `jobPolling`, never a bare `refetchInterval`

A query that polls while a server job runs (a batch `processando`, an extraction `queued/running`, a sync `running`) spreads `jobPolling(isActive, intervalMs)` from `@noctusai/lib` instead of hand-writing `refetchInterval: (q) => active ? ms : false`:

```ts
useQuery({ queryKey, queryFn, ...jobPolling((d: Lote | undefined) => !!d && emAndamento(d.status), POLL_MS) });
```

**Why.** TanStack pauses `refetchInterval` while `document.visibilityState === 'hidden'` (`refetchIntervalInBackground` defaults to `false`), and the seed `createQueryClient` sets `refetchOnWindowFocus: false`. A user who starts a 30 s job and switches tabs comes back to the progress they left — the SW CoreStudio "Gerar headlines" modal sat at "estrutura 3 de 5" and the roteiro modal at "Preparando as perguntas…" after the server had finished (2026-10-13). A progress UI frozen over a finished job is the time-axis twin of a lying loading state (`lying-loading-state.md`).

**What it sets.** While `isActive(data)`: `refetchInterval = intervalMs`, `refetchIntervalInBackground: true`, and `refetchOnWindowFocus: 'always'` (tab visible again ⇒ immediate refetch — browsers throttle hidden-tab timers, so the last background tick can be minutes old). While idle: no polling at all, foreground or background. `refetchIntervalInBackground` is a plain boolean in v5, so it is `true` unconditionally — inert while `refetchInterval` resolves `false`; that is what keeps idle queries off the network in a background tab by construction.

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

`useMemo` is for **deriving a value**, not for running effects. React may **elide / re-run** a memo computation freely (it's a perf hint, not a guarantee), so any *side effect* tucked inside it (set default selection, refresh history, fire a callback) **may not run** ∨ may run unexpectedly. Side effects belong in `useEffect` (runs on dependency change, deterministically). Bit 2026-05-25 in social-wiring `Upload.tsx` (two `useMemo`s used purely for side-effects — recipient-default-select + history-refresh — could be skipped; fixed → `useEffect`, commit `27f24b20`). Rule: if the body has no `return <derived value>` consumed in render, it's an effect — use `useEffect`.

> Follow-up (open): `ts-morph` is NOT in the seed FE base devDeps (`seed/lib/frontend` · `seed/framework/frontend`) — add it so TypeScript AST edits (AST-first rule) work in product frontends without a per-product install. Surfaced by the same 2026-05-25 dispatch; see `project-history/worktree-salvage.ndjson` (`feat/sw-frontend-verify`).

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

---

See also:
- `../03-SEED-ARCHITECTURE.md` — `createProductApp`, `createProductLayout`, `createProductInfra`
- `../04-SHARED-LIBRARY.md` — shared hooks + components catalog
