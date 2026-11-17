# Frontend craft canon — the baseline a senior React engineer brings, mapped onto this house

> **What it is.** The general frontend craft (React model, state, TanStack Query, components,
> TypeScript, forms, accessibility, pt-BR formatting, performance, testing, security, UX writing)
> that every UI slice assumes — written once, mapped onto NoctusAI's seed mechanisms, with
> in-tree examples. Owned by `frontend-engineer` (`.claude/agents/frontend-engineer.md`).
>
> **Why it exists.** The frontend house rules (loading states, cache writes, silent refusals,
> status_pagina, consent routes …) each came from an incident and each has a keeper. The CRAFT
> under them had no home: zero accessibility rule, zero forms rule, no query-key convention, no
> effects lens, no TypeScript, i18n, performance or XSS guidance (audit 2026-11-05,
> `archive/projects/2026-11-05/01-agent-refinement/audits/audit-frontend-engineer.md`). This doc is that home.
>
> **How to use it.** Read §0 before any UI slice; open the section your slice touches. **The house
> mechanism wins over the general canon** — when this doc and a house pattern disagree, the house
> pattern is the contract and this doc is the bug (fix it on contact). The house patterns are
> linked, never restated: depth lives at their pointers.

**Standard term ↔ house term**

| Standard (react.dev · TanStack · WAI) | House term / mechanism | Where |
|---|---|---|
| App shell, providers, router | `createProductApp` / `createProductLayout` / `createViteConfig` | `seed/framework/frontend/src/app.tsx` |
| Error boundary + Suspense fallback | seed-owned per route (`ErrorBoundary` + `Suspense` → `PageSkeleton`) | `seed/framework/frontend/src/app.tsx:238-250` |
| Query client defaults | `createQueryClient` (5 min stale, 10 min gc, no focus refetch, transient-only retry) | `seed/lib/frontend/src/query-client.ts:38-74` |
| Optimistic update / `setQueryData` | cache write — `useCacheWriteMutation` + `listOps` | `seed/lib/frontend/src/cache-writes.ts:112`, `:184` |
| Polling while a job runs | `jobPolling` + `handOffToPolling` | `seed/lib/frontend/src/job-polling.ts:84`, `:192` |
| Query-key factory | `<entity>Keys` object in `hooks/use<Entity>.ts` | `seed/lib/frontend/src/clients/hooks.ts:57-71` |
| Design system / atoms | `@noctusai/lib/design-system` (tokens + `ui/*` primitives) | `seed/lib/frontend/src/design-system/` |
| Organism (Atomic Design) | **organ** — registered with an `.organ.yaml` | `KB § PATTERNS/architect/products-consume-canonical-organs.md` |
| Unsaved-changes guard | `useUnsavedChanges` + `<UnsavedChangesNotice>` + `useBeforeUnloadGuard` | `seed/lib/frontend/src/components/UnsavedChanges.tsx:88-124` |
| Error state with retry | `QueryErrorState` / `RetryableError` | `seed/lib/frontend/src/components/RetryableError.tsx` |
| Route-level code splitting | `lazyWithReload` (lazy + one stale-chunk reload) | `seed/lib/frontend/src/lazyWithReload.ts:59` |
| Mockup / prototype | clickable mockup on seed tokens, real data where it exists | `KB § PATTERNS/frontend/prototype-on-real-data.md` |

**Versions this doc is written against** (verify before relying on a newer API): React `^18.3.1`,
react-router-dom `^7`, `@tanstack/react-query` `^5.83` (seed `^5.102`), react-hook-form `^7.88`,
zod `^4.6`, `@hookform/resolvers` `^5.9`, Vite `^8`, vitest `4.1.x`, TypeScript `^5.5`–`^5.9`
(`products/{core,agents,nosnolimiar,social-wiring}/frontend/package.json`, `seed/lib/frontend/package.json`).
🔴 **React 18, not 19** — `use()`, `useActionState`, `useOptimistic`, form Actions and ref-as-prop
are NOT available; a react.dev page that shows them is describing a version we do not run.

---

## 0 · How to use — the decision checklist for any UI slice

Run top to bottom; each line names the section that carries the depth.

1. **Mockup validated?** No UI before the owner clicked a mockup on seed tokens (real data where it
   exists, labelled sample where it doesn't). → `KB § PATTERNS/frontend/prototype-on-real-data.md`
2. **Contract written?** Connected BE↔FE work starts from one contract → skill `noc-contract-first`.
3. **Organ exists?** Search the catalog before building a component → skill `noc-organ-consume-check` (§4).
4. **Where does each piece of state live?** server · URL · form · local UI (§2). Nothing synced by an effect (§1).
5. **Hook file + key factory** for the entity (`hooks/use<Entity>.ts`, `<entity>Keys`) (§3).
6. **Four states on screen** — loading (two signals) · error before empty · empty with a next action · success.
   → `KB § PATTERNS/frontend/lying-loading-state.md` · `KB § PATTERNS/frontend/silent-refusal.md` · §12.
7. **Writes write the cache** → `KB § PATTERNS/frontend/mutation-cache-writes.md` · skill `noc-cache-writes`.
8. **Forms** — RHF + zod mirrored from the contract, errors tied to fields (§6).
9. **Accessible by construction** — native element or seed primitive, name + focus + keyboard (§7).
10. **pt-BR formatting** — Intl via seed helpers, `null` renders "—", never 0 (§8).
11. **Fast** — route-level `lazyWithReload`, no heavy dep unchecked, transitions for non-urgent renders (§9).
12. **Tests read like a user** — role/label queries, assert the screen, mock at the network edge (§10).
13. **No raw HTML** (§11). **Copy that helps** (§12). **Review checklist** before returning (§13).

---

## 1 · The React model

### 1.1 Thinking in React — hierarchy first, then minimal state

**Principle.** Break the UI into a component hierarchy; build a static version from props; find the
*minimal* complete state; decide which component owns each piece (the closest common parent of
everything that reads it); add inverse data flow (callbacks) last. Everything that can be computed
from props or other state is **not** state. (react.dev — Thinking in React; Choosing the State Structure.)

**Here.** Pages are compositions of organs; the server state lives in the TanStack cache, not in
component state (§2), so most "state" a page holds is UI state (open/closed, selected tab) or a draft.

**Checklist.**
- [ ] Each `useState` holds something that cannot be derived from props, other state, the URL or the cache.
- [ ] No two state variables that must change together (merge them, or derive one).
- [ ] No state that mirrors a prop ("`const [x, setX] = useState(props.x)`") unless it is a deliberate
  initial value for a draft (then name it `initialX`).

### 1.2 Rules of React — purity

Components and hooks are **pure**: same props/state ⇒ same JSX, no side effects during render, props
and state treated as immutable, hooks called unconditionally at the top level, only from components or
hooks. React may render a component more than once (StrictMode does it on purpose in dev — core
mounts under `<React.StrictMode>`, `products/core/frontend/src/main.tsx:108-111`). (react.dev — Rules of React.)

### 1.3 Derive, don't sync — "You Might Not Need an Effect"

**Principle.** An Effect is an escape hatch for **synchronising with an external system** (a DOM API,
a subscription, a non-React widget, the network outside TanStack). It is NOT for:

| You want to … | Do this instead (react.dev) |
|---|---|
| compute a value from props/state | compute it during render (`useMemo` only if measurably expensive) |
| reset all state when a prop (an id) changes | give the component `key={id}` |
| adjust some state when a prop changes | compute during render; or store the previous prop and adjust during render |
| respond to a user action (submit, click, buy) | do it in the event handler |
| fetch data | a TanStack `useQuery` in the entity hook (§3) |
| notify a parent about a change | call the parent's callback in the same event handler |
| subscribe to an external store | `useSyncExternalStore` |

**Here — what good looks like.**
- `useSyncExternalStore` for the org-scoped query client: `seed/lib/frontend/src/query-client.ts:150-151`.
- A legitimate effect (reads a DOM node the server injected, after hydration):
  `products/core/frontend/src/website/lib/settings.tsx:41-44`.
- Drafts seeded from server data that respect unsaved edits: `products/agents/frontend/src/components/studio/useBuffered.ts:8-30`
  (keeps a `base`, reseeds only when not dirty, raises `conflict` when the server moved under edits).
  The seed's draft organ is `useUnsavedChanges` (`seed/lib/frontend/src/components/UnsavedChanges.tsx:101`).

**Here — the review lens (220 `useEffect(` sites in the four active product FEs, 2026-11-05).**
- `products/core/frontend/src/pages/AccountSettings.tsx:15-21` copies `user` into three `useState`s in
  an effect — a draft seeded by effect re-seeds on every `user` identity change and can clobber typing.
  Prefer a form library's `values`/`reset` (§6) or a keyed child (`<Form key={user.id} initial={user} />`).
- `products/agents/frontend/src/pages/studio/tabs/SkillsTab.tsx:95-110` — two effects reset four
  fields when `selected` changes; `key={selected}` on the editor resets all of it with no effect.

**Moved here losslessly from `KB § PATTERNS/frontend/frontend.md` (2026-11-05) — `useMemo` ≠ a side-effect channel.**
`useMemo` is for **deriving a value**, not for running effects. React may **elide / re-run** a memo
computation freely (it's a perf hint, not a guarantee), so any *side effect* tucked inside it (set
default selection, refresh history, fire a callback) **may not run** ∨ may run unexpectedly. Side
effects belong in `useEffect` (runs on dependency change, deterministically). Bit 2026-05-25 in
social-wiring `Upload.tsx` (two `useMemo`s used purely for side-effects — recipient-default-select +
history-refresh — could be skipped; fixed → `useEffect`, commit `27f24b20`). Rule: if the body has no
`return <derived value>` consumed in render, it's an effect — use `useEffect`.
**Refined 2026-11-05 against react.dev:** the fix is not automatically `useEffect` — first ask whether
the work belongs in the event that caused it (a selection default is set where the list arrives or the
user picks; a history refresh is a cache write after the mutation). `useEffect` only when the work
synchronises with something outside React.

**Anti-patterns.** effect chains (effect sets state that triggers another effect); `useEffect` +
`fetch` (no cache, no dedupe, race conditions); `useEffect(() => setFiltered(items.filter(…)), [items])`;
effect that calls `onChange` on the parent after state changes.

### 1.4 Keys and identity

A `key` is identity: same key at the same position ⇒ React preserves the component's state; new key ⇒
fresh state. Use stable ids from data, never the array index for a list that can reorder/insert/delete,
and use `key` deliberately to reset a subtree (react.dev — Preserving and Resetting State). The seed
uses this exact mechanism to drop every hook on an org swap: `OrgScopeBoundary` keys its subtree with
the client generation (`seed/lib/frontend/src/query-client.ts:181-184`).

### 1.5 Suspense and transitions

- **Suspense** shows a fallback while a child is not ready (lazy code here; we do not use
  Suspense-for-data). The seed wraps every route: `seed/framework/frontend/src/app.tsx:238-250`
  (`<Suspense fallback={<PageSkeleton />}>`). Do not add another route-level Suspense in a product.
- **`useTransition` / `startTransition`** (React 18) marks a state update as non-urgent so typing and
  clicks stay responsive while an expensive re-render happens (filtering a long list, switching a heavy
  tab). It is the first tool for a poor INP (§9). It does not apply to TanStack fetch state — keep the
  two-signal loading rule for that (`KB § PATTERNS/frontend/lying-loading-state.md`).
- `useDeferredValue` — a deferred copy of a fast-changing value for an expensive child (search box →
  results list).

### 1.6 Error boundaries — seed-owned

Every route renders inside the seed `ErrorBoundary` (`seed/framework/frontend/src/app.tsx:238`,
class at `seed/lib/frontend/src/components/ErrorBoundary.tsx:28`). Error boundaries catch **render**
errors only — not event handlers, not async code, not query failures (those are `isError` →
`QueryErrorState`). Add a **local** boundary only around an independently failing widget (a third-party
chart, an embedded editor) so one widget's crash does not take the page; never re-wrap a route. Never
hand-wire providers or boundaries (`createProductApp` IS the contract). (react.dev — Component,
catching rendering errors with an error boundary.)

### 1.7 React Compiler readiness

The React Compiler auto-memoises components and hooks; it is designed for React 19 and also supports
17/18 via a runtime package (react.dev — React Compiler; Installation). We have **not** adopted it.
Code that already obeys §1.2 (pure render, no mutation of props/state, hooks rules) is
compiler-ready; code that relies on `useMemo` for correctness (§1.3) is not. Do not add `useMemo` /
`useCallback` "for performance" without a measured reason; do add them when a referential identity is
part of a contract (a dependency array of a hook that subscribes).

---

## 2 · State architecture — server · URL · form · local UI

**Principle.** Different state has different owners; most bugs are state in the wrong home.
(TkDodo — Practical React Query; react.dev — Choosing the State Structure.)

| Kind | Owner here | Never |
|---|---|---|
| **Server state** (anything the API returns) | TanStack Query cache, via the entity hook (§3) | copied into `useState`/Zustand (it goes stale silently) |
| **URL state** (filters, tab, page, sort, selected id) | react-router `useSearchParams` / route params | held only in `useState` (lost on reload, unshareable) |
| **Form / draft state** | react-hook-form (§6) or the draft organ (`useUnsavedChanges`) | applied silently — a draft says it is unsaved (`KB § PATTERNS/common/server-state-family-index.md`) |
| **Local UI state** (open, hover, selected-in-a-dialog) | `useState` in the closest owner | lifted to global |
| **Global UI state** (sidebar collapsed, theme) | Zustand store (`store/`) | server data inside it |

**Rules.**
- [ ] A list page's filters/pagination are in the URL — `products/social-wiring/frontend/src/hooks/useLeads.ts:58-67`
  keys the list by `filters` + `params`, so the URL is the natural owner of both.
- [ ] Server-derived values are derived at read time (`select`, §3.4) rather than stored.
- [ ] The query key contains every input of the `queryFn` (§3.2) — no hidden inputs from closures.

---

## 3 · Server state — TanStack Query v5 here

### 3.1 Library defaults vs the seed overrides

TanStack's defaults (TanStack — Important Defaults): cached data is **stale immediately**
(`staleTime: 0`); stale queries refetch in the background on mount, **window refocus** and
reconnect; inactive queries are garbage-collected after **5 minutes**; failures are **retried 3 times**
with exponential backoff; results are **structurally shared**.

The seed overrides them for every product (`seed/lib/frontend/src/query-client.ts:61-72`):

| Option | TanStack default | Seed | Consequence for you |
|---|---|---|---|
| `staleTime` | 0 | **5 min** (`:63`) | data does not refetch on remount for 5 min — a write MUST put its answer in the cache (`mutation-cache-writes.md`) or the screen stays stale |
| `gcTime` | 5 min | **10 min** (`:64`) | — |
| `refetchOnWindowFocus` | true | **false** (`:65`) | returning to a tab does not refresh — job progress uses `jobPolling` (sets `'always'` while active) |
| `retry` | 3, any error | **transient only** (`:66`, `retry.ts`) — no response/timeout/408/425/429/5xx, 1 s → 3 s → 9 s; a 4xx is never retried | a 404/422 surfaces at once |
| mutations `retry` | 0 | `false` (`:70`); opt in with `autoRetryMutationOptions()` | writes are not idempotent |
| global `onError` | none | one toast after the last attempt (`:41-59`), `meta.suppressErrorToastStatuses` per query | do not add a second error toast in the hook |

`staleTime` per query: set it only with a reason (a stream owns the cache ⇒ `Infinity`,
`KB § PATTERNS/frontend/inbox-chat-surface.md`); `enabled: !!id` (or `!!user`) whenever an input may be missing.

### 3.2 Query keys come from a key factory

**Principle.** A query key is an array that uniquely identifies the data, contains **every variable
the `queryFn` depends on**, and is **hierarchical** (general → specific) so a prefix matches a family.
Centralise them in a per-entity factory (TanStack — Query Keys; TkDodo — Effective React Query Keys).

**Why it is load-bearing here.** `useCacheWriteMutation` targets with `match: 'prefix'` reach "EVERY
cached entry whose key starts with `queryKey` — e.g. `[resource]` reaches each `[resource, filters]`
list at once" (`seed/lib/frontend/src/cache-writes.ts:69-70`). A hand-typed literal that drifts from
the family (`['lead', f]` vs `['leads', 'list', f]`) silently escapes the write and the invalidation.
A factory removes that class of bug. In-tree reference: `clientsKeys`
(`seed/lib/frontend/src/clients/hooks.ts:57-71`, used at `:112-180`). In the four active product FEs,
`queryKey: [` literals appear 482× across 154 files vs ~15 factories (2026-11-05 grep).

**Shape** (worked example WE3 below):
```ts
export const leadKeys = {
  all: ['leads'] as const,
  lists: () => [...leadKeys.all, 'list'] as const,
  list: (f: LeadsFilters, p?: ListLeadsParams) => [...leadKeys.lists(), f, p] as const,
  details: () => [...leadKeys.all, 'detail'] as const,
  detail: (id: string) => [...leadKeys.details(), id] as const,
};
```

**Checklist.** [ ] one factory per entity, exported from the entity's hook file · [ ] every `useQuery`,
cache-write target and handoff uses it · [ ] no key literal outside `hooks/` (candidate keeper at N —
triage via skill `noc-triage`).

### 3.3 Hooks in dedicated files

One `hooks/use<Entity>.ts` per entity; never inline `useQuery`/`useMutation` in a page →
`KB § PATTERNS/frontend/frontend.md` § Hooks in dedicated files. The hook computes the loading
signals once (`showSkeleton`, `isRefreshing`) so no consumer re-derives them
(`KB § PATTERNS/frontend/lying-loading-state.md`).

### 3.4 `select`, structural sharing, render optimisation

`select` transforms/filters cached data per observer and re-renders the component only when the
selected result changes; structural sharing keeps unchanged references stable; tracked properties
mean a component re-renders only for the fields it read (TanStack — Render Optimizations). Use
`select` for per-view projections (counts, one field, a sorted copy) instead of storing derived data.
Keep `select` stable (module-level function or `useCallback`) when it is expensive.

### 3.5 Keeping previous data, placeholders, polling

- `placeholderData: (prev) => prev` (or `keepPreviousData`) on any user-keyed query (filters, page) —
  otherwise every key change flashes a skeleton. Exception: authorisation-scoped personal data (comment
  why). (TanStack — Placeholder Query Data; house rule in `lying-loading-state.md`.)
- Job progress: `...jobPolling(isActive, ms)`, never a bare `refetchInterval`; a write that starts a job
  calls `handOffToPolling` → `KB § PATTERNS/frontend/frontend.md` § Job-progress polling.
- Live data with no terminal state (inbox, feed) is a realtime stream, never polling →
  `KB § PATTERNS/frontend/inbox-chat-surface.md`.

### 3.6 Mutations

The cache-write contract is the house rule — `useCacheWriteMutation`, optimistic when predictable,
commit the server answer, background settle; never invalidate-only →
`KB § PATTERNS/frontend/mutation-cache-writes.md` · skill `noc-cache-writes`. TanStack documents the
same move as optimistic updates (TanStack — Optimistic Updates; Query Invalidation); our addition is
that the **server's answer** is written too, so the screen agrees with the toast before any refetch.

**Anti-patterns.** copying `data` into `useState`; `useEffect` fetches; `isLoading` as the loading
signal; a second error toast in `onError`; a key that omits a `queryFn` input; `invalidateQueries` as
the only write.

---

## 4 · Component architecture and the design system

### 4.1 Atoms → organs (Atomic Design, house vocabulary)

Atomic Design names five levels — atoms, molecules, organisms, templates, pages (Brad Frost, ch. 2).
Here: **atoms/molecules** = `@noctusai/lib/design-system` `ui/*` primitives on `tokens.css`
(`seed/lib/frontend/src/design-system/ui/`, `.../tokens.css`); **organisms** = **organs**, registered
with an `.organ.yaml` so the catalog can find them (e.g. `ui/MultiSelectPopover.organ.yaml`,
`ui/Skeleton.organ.yaml`); **templates** = `createProductLayout` + `AppShell`/`Sidebar`; **pages** = the
product's `pages/`. A missing `.organ.yaml` makes the catalog report the organ as shelfware and
manufactures forks (`KB § PATTERNS/frontend/inbox-chat-surface.md`).

### 4.2 Headless primitives + tokens

Behaviour (focus, keyboard, ARIA) comes from headless primitives — Radix in the seed
(`seed/lib/frontend/package.json:44-56`: dialog, popover, select, tabs, tooltip, checkbox, switch …);
visuals come from tokens. Radix primitives implement the WAI-ARIA authoring practices (focus trap,
roving focus, Esc, labelling) (Radix — Accessibility). Building a menu/listbox/combobox/tabs by hand
re-implements that contract and usually misses half of it.

⚠️ **Two dialogs ship in the seed — know which is which.** The bare `Dialog` export (focus in/trap/return added 2026-11-05, `Dialog.tsx:110-160`) is a minimal inline
modal with no Radix dependency (`seed/lib/frontend/src/design-system/ui/Dialog.tsx:1-27`): it has
`role="dialog"` + `aria-modal` (on the backdrop, `:117-118`), `aria-label={title}`, Esc and safe
backdrop-click, but **no focus trap, no initial focus, no focus return**. The Radix dialog is exported
as `CardHubDialog*` (`seed/lib/frontend/src/design-system/index.ts:141-150`,
`ui/radix-dialog.tsx`), which implements the full APG modal-dialog pattern. For a form modal use the
Radix one; the inline `Dialog` is acceptable for a short confirmation until its focus management is
fixed at the seed (see WE1).

### 4.3 Compound components and named seams

For an organ with several cooperating parts (`Dialog`/`DialogHeader`/`DialogBody`/`DialogFooter`,
`Dialog.tsx:33-70`), expose compound sub-components that share implicit state through context rather
than a 20-prop configuration object (KCD — Compound Components with Hooks). A product extends an organ
through a **declared named seam** (a slot, a render prop, an adapter) — never a copy
(`KB § PATTERNS/architect/products-consume-canonical-organs.md`).

### 4.4 When to promote to the seed

Another product will need it ⇒ build it in the seed from day one; a product-local helper found in a
second product ⇒ triage; N≥3 ⇒ must formalise (CLAUDE.md §1 DRY). Before writing a component: skill
`noc-organ-consume-check`. Promotion candidates seen while writing this doc:
`useBuffered` (`products/agents/frontend/src/components/studio/useBuffered.ts`) overlaps the seed
draft organ; three date-format families exist in the seed (§8.3).

---

## 5 · TypeScript — the strict ratchet

**Current state.** The seed packages are strict (`seed/lib/frontend/tsconfig.json:12`,
`seed/framework/frontend/tsconfig.json:12`). **Every product FE is not**: `"strict": false` +
`"noImplicitAny": false` in all five active products and in the scaffold the next product copies
(`products/seed/frontend/tsconfig.json:14-15`, `templates/product-seed/frontend/tsconfig.json:14-15`,
`products/core/frontend/tsconfig.json:18,21`, `products/social-wiring/frontend/tsconfig.json:14-15`,
`products/agents/frontend/tsconfig.json:14-15`, `products/nosnolimiar/frontend/tsconfig.json:14-15`). Lint
downgrades `@typescript-eslint/no-explicit-any` to `warn`, citing payload and react-hook-form `as any`
workarounds (`seed/framework/frontend/eslint.config.js:28-31`); `as any` appears 254× in the active
product FEs.

**Ratchet plan (seed-level, pilots first — described, not implemented here).**
1. Flip the scaffold (`products/seed/frontend/tsconfig.json`) to `"strict": true` so every NEW product
   is born strict — the root fix (a per-product flip is the quick-fix shape).
2. Per existing product: record a baseline of `tsc --noEmit --strict` errors; a keeper ratchets the count
   down (never up), the way `check_mutation_invalidate_only` ratchets mutations.
3. Pilots: one product per wave (core → social-wiring → agents/nosnolimiar), then fan out.
4. After `strict`: add `noUncheckedIndexedAccess` (an indexed read is `T | undefined`) — the flag that
   catches `arr[0].id` on an empty list (TSConfig reference).

**Rules while the ratchet is not in place.**
- [ ] Types come from the contract (the endpoint's schema), not from the component; never `as any` on a payload.
- [ ] Model UI states as **discriminated unions** (`{ status: 'idle' } | { status: 'error'; error: ApiError } | …`),
  not parallel booleans (TypeScript — Narrowing, discriminated unions).
- [ ] Use `satisfies` to check a literal against a type without widening it (key factories, route
  tables, config maps) (TypeScript 4.9 release notes).
- [ ] `as const` on key factories and literal tables.
- [ ] Narrow `unknown` (catch variables, `JSON.parse`) before use.

---

## 6 · Forms

**Current state.** react-hook-form + zod + `@hookform/resolvers` are declared in four of the five
active product FEs (`products/{agents,nosnolimiar,social-wiring,seed}/frontend/package.json`), but only
**one** active-product file uses them (`products/social-wiring/frontend/src/pages/Certidoes.tsx:37-38,
250-251`); the rest are hand-rolled `useState` forms (e.g.
`products/core/frontend/src/pages/admin/AdminPlans.tsx:179-250`). Declared ≠ adopted.

**Principle.** A form is state + validation + submission + error presentation. Use
`useForm({ resolver: zodResolver(schema) })` with the schema **mirrored from the endpoint contract**
(the backend's Pydantic model is the source of truth; the FE schema repeats its constraints, never
loosens or invents them). (react-hook-form — useForm; Zod.) Server-side validation errors map back to
fields with `setError` (react-hook-form — setError). Inclusive-form rules: every field has a visible
`<label>` bound to it, instructions before the field, errors identified in text and tied to the field,
suggestions for how to fix (W3C WAI — Forms Tutorial; WCAG 3.3.1 Error Identification, 3.3.3 Error
Suggestion).

**Checklist.**
- [ ] Every input has a programmatic label: `<Label htmlFor="x">` + `<Input id="x">` (or wrap). A
  `placeholder` is not a label.
- [ ] Error state: `aria-invalid={!!errors.x}` + `aria-describedby="x-erro"` on the input; the message
  element has that id. (Active FEs: 19 `aria-invalid`, 6 `aria-describedby` — 2026-11-05.)
- [ ] Messages in pt-BR, specific and actionable ("Informe um CPF com 11 dígitos", not "Inválido").
- [ ] Brazilian documents validate with the seed identificador (`cpfDvValido`/`cnpjDvValido`,
  `seed/lib/frontend/src/identificador.ts:69,88`), not a length check.
- [ ] Submit shows pending (`isSubmitting` / the mutation's `isPending`) and is not double-submittable.
- [ ] A 422 from the server lands on the field (`setError`), not only in a toast.
- [ ] Editing an existing record: pass server data via `values` / `reset(data)` — not an effect copying
  into `useState` (§1.3); unsaved edits are announced (`useUnsavedChanges`).

**Anti-pattern in tree.** `Certidoes.tsx:775-780` — `<Label>Documento</Label>` with no `htmlFor`, the
`<Input>` has no `id`, and the error `<p>` is not referenced by `aria-describedby`; the zod rule for
`documento` is `min(11)` (`:158`) rather than a CPF/CNPJ check-digit validation.

---

## 7 · Accessibility — WCAG 2.2 AA is the floor

**Why.** Accessibility is correctness for people using keyboards, screen readers, magnification and
voice control; in Brazil the Lei Brasileira de Inclusão (Lei 13.146/2015) makes accessible websites a
legal duty and eMAG is the government reference model (see §14 for verification status).

**Current state.** No product FE runs `eslint-plugin-jsx-a11y`, axe-core, or a Playwright a11y scan
(`products/*/frontend/package.json`, 2026-11-05); 25 `<div … onClick>` sites remain in the four active
product FEs.

**Rules.**
1. **Semantic HTML first.** A clickable thing is a `<button>` (action) or `<a href>` (navigation). A
   `div onClick` has no role, no focus, no Enter/Space — never use it for an interactive element.
2. **Complex widgets via seed Radix primitives** (dialog, menu, popover, select, tabs, tooltip) — they
   implement the APG patterns (WAI-ARIA APG; Radix — Accessibility). Modal = the Radix dialog (§4.2).
3. **Every control has an accessible name** (visible label, `aria-label` for icon-only buttons —
   `Certidoes.tsx:735` does it right: `aria-label={\`Excluir consulta ${consulta.nome}\`}`).
4. **Focus.** Visible focus indicator on every focusable element (tokens' `focus-visible:ring`); a dialog
   moves focus in, traps it, and returns it to the trigger on close; a route change moves focus to the
   page heading or main region; focus is never hidden behind a sticky header (WCAG 2.4.11 Focus Not
   Obscured).
5. **Target size ≥ 24×24 CSS px** for pointer targets, or enough spacing (WCAG 2.5.8 Target Size
   Minimum). Icon buttons in dense tables are the usual offender.
6. **Contrast** through tokens only (no ad-hoc hex), checked in light and dark.
7. **Status messages** (toasts, "salvo", async results, form error summaries) are announced without
   moving focus — `role="status"` / `aria-live="polite"`, `role="alert"` for errors (WCAG 4.1.3 Status
   Messages; MDN aria-live). Seed examples: `QueryErrorState` uses `role="alert"`
   (`RetryableError.tsx:24`, `:100`); `ReviewQueue.tsx:153` uses `aria-live="polite"`. sonner toasts are
   announced by the library.
8. **Motion** respects `prefers-reduced-motion` (Tailwind `motion-safe:` / `motion-reduce:`).
9. **Language**: `<html lang="pt-BR">`; content in another language is marked with `lang`.

**Tooling (adopt seed-level, not per product).** `eslint-plugin-jsx-a11y` in the seed ESLint config
(static); `axe-core` assertions in vitest render tests of organs; `@axe-core/playwright` in the E2E
smoke of each active product (Playwright — Accessibility testing). Tooling catches ≈ a third of
issues; the keyboard walk-through (Tab, Shift+Tab, Enter, Space, Esc, arrows) is the manual floor for
every new screen.

**Checklist.** [ ] keyboard-only path through the whole flow · [ ] every control named · [ ] dialog
focus in/trap/return · [ ] errors announced and tied to fields · [ ] no `div onClick` · [ ] 24 px targets ·
[ ] zoom to 200 % without loss · [ ] works at 375 px (mobile-first, `frontend.md`).

---

## 8 · pt-BR, Intl and honest values

### 8.1 Format through Intl, via the seed

Use `Intl.NumberFormat` / `Intl.DateTimeFormat` / `Intl.RelativeTimeFormat` / `Intl.PluralRules` with
locale `pt-BR` (MDN). Construct formatters once (module scope) — `new Intl.NumberFormat` per call is
measurably slow in long tables. The canonical helpers live in the seed
(`seed/lib/frontend/src/utils.ts:26` `formatCurrency`, `:46` `formatDate`; phone in `phone.ts:157`
`formatPhone`; documents in `identificador.ts:353` `formatIdentificador`). The four active product FEs
call `toLocaleString(`/`new Intl.` directly 152× vs `formatCurrency(` 8× (2026-11-05) — DRY debt;
missing seed helpers (`formatNumber`, `formatPercent`, `formatRelative`) are why.

### 8.2 `null` ≠ 0 — a missing value never renders as a real zero

A KPI with no data must read "—" (or "Sem dados"), never "R$ 0,00": a zero is a fact, a missing value is
the absence of one. This is the value-axis twin of the lying-loading-state rule and the shape the
wiring audit hunts as the "all-zeros dashboard" (skill `noc-wiring-audit`). ✅ Fixed 2026-11-05 in the seed:
`formatCurrency` / `formatCents` / `formatQty` / `formatCompactNumber` return "—" for null/undefined/NaN
(`utils.ts:28`, `organ-kit/money.ts:8`, `inventory/format.ts:8`, `charts/formatters.ts:14`; test
`format-missing.test.ts`); see WE2. `formatDate` returns `'-'` (`:47`).

### 8.3 Time zones and dates

- A DATE-only string (`YYYY-MM-DD`) is parsed as a local date, never via `new Date('YYYY-MM-DD')` (which
  is UTC midnight and shows the previous day in Brazil) — `formatDate` does this (`utils.ts:51-55`), and
  never invents a time for a date-only value (`:67-68`).
- A timestamp shown to a Brazilian user is formatted in `America/Sao_Paulo` (or the org's configured
  zone), not the browser's: `seed/lib/frontend/src/components/card-hub/format.ts:79-96`
  (`formatarDataHoraSP`) and `seed/lib/frontend/src/clients/format.ts:11-75` (`tzOf`, `zonedParts`,
  `todayIn`) do; `formatDate` uses the browser zone (`utils.ts:57-70`). Three date-format families in
  the seed = a DRY N=3 to formalise into one `@noctusai/lib/format` module (triage).

### 8.4 Brazilian identifiers and phones

CPF, CNPJ, RG, CEP: `formatIdentificador` / `lerIdentificador` / `chaveBuscaIdentificador`
(`seed/lib/frontend/src/identificador.ts:336-358`) — the punctuated form is canonical, the check digit
decides, and unparseable values stay visible (never invented). Phones: `normalizePhone` /
`isValidPhone` / `formatPhone` (`phone.ts:86-157`, default country `55`). Never hand-roll a mask.

**Checklist.** [ ] money/number/date through seed helpers · [ ] `null`/`undefined` → "—" · [ ] date-only
parsed as local · [ ] timestamps in the org/SP zone · [ ] plurals via `Intl.PluralRules` or explicit
singular/plural copy ("1 lead" / "2 leads").

---

## 9 · Performance

**Targets (75th percentile of real page loads — web.dev Web Vitals; Defining the Core Web Vitals thresholds).**
| Metric | Good | Needs improvement | What moves it here |
|---|---|---|---|
| **LCP** (largest content paint) | ≤ 2.5 s | ≤ 4.0 s | route chunk size, render-blocking fonts, first query waterfall |
| **INP** (interaction to next paint) | ≤ 200 ms | ≤ 500 ms | long renders on input — transitions, virtualisation, `select` |
| **CLS** (layout shift) | ≤ 0.1 | ≤ 0.25 | skeletons the size of the content, image `width`/`height`, no late banners |

**Rules.**
1. **Route-level splitting with `lazyWithReload`** (`seed/lib/frontend/src/lazyWithReload.ts:59`) — plain
   `React.lazy` 404s after a deploy re-hashes chunks and lands on the error screen (`:4-26`). In the
   active FEs only social-wiring uses it (`products/social-wiring/frontend/src/App.tsx:25-31`); core
   declares 38 routes with plain `lazy` (`products/core/frontend/src/main.tsx:10,19-56`). (Vite —
   dynamic import.)
2. **No heavy dependency without a bundle check** — run the product's `vite build` (through the hardware
   gate) and compare chunk sizes before/after; a new chart/editor/3D lib is lazy-loaded with the route
   that needs it.
3. **Skeletons match the final layout** (CLS) — the seed `Skeleton`/`TableSkeleton` organs.
4. **Long lists (> ~200 rows) virtualise** (TanStack Virtual) or paginate server-side.
5. **Non-urgent renders in a transition** (§1.5); avoid render cascades (effect → setState → render, §1.3).
6. **Server half**: the response budget and round-trip counting are skill `noc-fast-responses`; the
   perceived half is cache writes (§3.6).
7. **Measure, don't guess** — skill `noc-perf-probe` (browser-side capture, waterfall, duplicate
   requests, before/after). (web.dev — Optimize LCP; INP; CLS; Rendering performance.)

---

## 10 · Testing

**Principle — the testing trophy.** Static analysis (types, lint) at the base; a few unit tests for pure
logic; **most confidence from integration tests** that render a page/organ with its hooks and assert
what the user sees; a few E2E flows on top (Kent C. Dodds — The Testing Trophy). "The more your tests
resemble the way your software is used, the more confidence they can give you" (Testing Library —
Guiding Principles).

**Query priority** (Testing Library — Queries, priority): `getByRole` (with `name`) → `getByLabelText`
→ `getByPlaceholderText` → `getByText` → `getByDisplayValue` → `getByAltText`/`getByTitle` →
`getByTestId` last. Today the repo's FE tests use `*ByTestId` 5,612× vs `*ByRole` 1,367× (active
products + seed lib, 2026-11-05) — new tests invert that. A test that cannot find an element by role
is often reporting an accessibility bug (§7).

**Rules.**
- [ ] Interact with `@testing-library/user-event` (`await user.click/type/keyboard`), not `fireEvent`
  (Testing Library — user-event). It is in the seed lib and social-wiring devDeps; add it where missing.
- [ ] Assert user-visible outcomes (text, roles, `aria-*` state), not hook internals or call counts —
  except where the call count IS the contract (e.g. `markRead` reaching a real phone,
  `inbox-chat-surface.md`).
- [ ] Mock at the **network edge**. MSW (Mock Service Worker) intercepts requests so the real api
  client, hooks and cache run (MSW docs); MSW is in **0** FEs today — module-mocking the hook is the
  current norm and skips the cache contract. Adopt MSW in the seed test harness first (pilot), not per
  product.
- [ ] The **in-flight cache assertion** for writes: assert the screen shows the new value while the
  request is still pending and after it resolves with no refetch →
  `KB § PATTERNS/frontend/mutation-cache-writes.md` (skill `noc-cache-writes`).
- [ ] E2E with Playwright (core, social-wiring have `@playwright/test`): role locators
  (`page.getByRole`), web-first assertions, no fixed sleeps, an axe scan on each smoke route
  (Playwright — Best practices; Accessibility testing).
- [ ] Run the FULL vitest of every product you touched before returning (product-engineer §3), through the
  hardware gate.

**The dual-React harness gap — resolved, with one residual.** Render tests used to crash with
"Cannot read properties of null (reading 'useState')" when `react-dom/client` and the component
resolved to different React copies. Fixed 2026-05-29 by subpath aliases + `resolve.dedupe` in
`seed/lib/frontend/vitest.config.ts:12-41,63` and mirrored in the product factory
`seed/framework/frontend/vitest.config.factory.ts:26-32` (every active product's `vitest.config.ts`
calls `createProductVitestConfig`). The residual: in a symlinked worktree the lib's render tests can
still dual-React-fail — `KB § PATTERNS/common/self-branching-mode.md` (known worktree-env caveats).
A green vitest is still not "live works" → `KB § PATTERNS/devops/dev-prod-parity.md`.

---

## 11 · Security in the browser

**Principle.** React escapes text children by default; every XSS in a React app goes through one of its
**exits** (OWASP — XSS Prevention Cheat Sheet). Authorisation is server-side; FE gates are UX only
(`KB § PATTERNS/frontend/org-admin-ux-gate.md`).

| Exit | Rule |
|---|---|
| `dangerouslySetInnerHTML` | forbidden except (a) JSON-LD with `<` escaped, (b) output of a sanitiser (DOMPurify) — with a comment naming which |
| `href`/`src` from data | allow only `http(s):`/`mailto:`/`tel:` — `javascript:` URLs execute |
| Markdown | the seed `MarkdownRenderer` organ, no `rehype-raw` (`seed/lib/frontend/src/components/markdown/MarkdownRenderer.organ.yaml:31-33` records why) |
| `eval`/`new Function`/string `setTimeout` | never |
| `target="_blank"` to third parties | `rel="noopener noreferrer"` |

**JSON-LD escaping.** `JSON.stringify` does not escape `<`, so a value containing `</script>` closes the
script element; the safe form replaces `<` with `<` (HTML — restrictions for contents of script
elements). Core's server does exactly this when injecting website settings
(`products/core/backend/app/routers/website_html.py:132-138`). But the client then **parses** those
settings (`products/core/frontend/src/website/lib/settings.tsx:32`, decoding `<` back to `<`) and
the (since-deleted) core `FaqAccordion` re-serialised admin-editable FAQ items with plain `JSON.stringify` into
`dangerouslySetInnerHTML` — the
server's escaping is undone on the client. ✅ Fixed 2026-11-05: every JSON-LD site serialises through the
seed `safeJsonLd` (`@noctusai/lib/json-ld`, `seed/lib/frontend/src/json-ld.ts`; escapes `<` `>` `&` U+2028/9) —
today `products/core/frontend/src/website/components/SiteFaq.tsx:26` (core wraps the seed `Faq` organ
and emits the `FAQPage` JSON-LD), `headHtml.ts` prerender; test `website/__tests__/faqJsonLd.test.tsx`.

**CSP.** The seed sets `Content-Security-Policy-Report-Only` on HTML responses
(`seed/lib/backend/noctusai_lib/api/security_headers.py:24-33,63-64`) with `script-src 'self'
'unsafe-inline'` — report-only, so it does not block yet. Do not add inline scripts or new third-party
origins without updating that policy (OWASP — CSP Cheat Sheet).

**Secrets.** Every `VITE_*` variable is compiled into the public bundle (Vite — Env Variables and
Modes): only publishable keys (Supabase anon, public URLs) go there →
`KB § PATTERNS/devops/environment.md`. Tokens in `localStorage` (core: `products/core/frontend/src/lib/api.ts:23-25,169-184`)
are readable by any XSS — one more reason the exits above stay closed.

---

## 12 · UX writing and heuristics for the four states

**Nielsen's 10 heuristics** (NN/g), applied to what we ship most:

| Heuristic | Applied here |
|---|---|
| 1 Visibility of system status | two-signal loading; `isRefreshing` indicator; job progress that polls (§3.5) |
| 2 Match the real world | pt-BR domain words the user uses ("imóvel", "lead", "certidão"), not table names |
| 3 User control and freedom | Esc closes dialogs; undo or confirm for destructive actions (`ConfirmProvider` in the seed shell) |
| 4 Consistency and standards | organs, tokens, one toast system (sonner) |
| 5 Error prevention | validate on the client from the contract (§6); disable impossible actions with a reason |
| 6 Recognition rather than recall | show the current filters; keep context on the screen |
| 7 Flexibility and efficiency | keyboard paths; URL-shareable state (§2) |
| 8 Aesthetic and minimalist design | one primary action per view |
| 9 Help users recognise, diagnose, recover from errors | the error copy rules below |
| 10 Help and documentation | ⓘ explanations for formulas (`KB § 07-GAMIFICATION.md` rule) |

**Copy rules (pt-BR, plain, specific).**
- **Empty state** = what will be here + the next action ("Nenhum lead ainda. Importe uma planilha ou
  conecte o Facebook Ads." + the button). A first-use empty state differs from a "no results for these
  filters" state (offer "Limpar filtros") (NN/g — Designing Empty States).
- **Error** = what happened + why (if known) + how to fix, in the user's words; never only "Algo deu
  errado"/"Erro" (NN/g — Error-Message Guidelines). The seed `RetryableError` sets the bar: a title, a
  reason CLASS (never raw server text), the retry count, a real button (`RetryableError.tsx:1-25`).
  Two seed surfaces fall short and are follow-ups: the route `ErrorBoundary` fallback is
  "Algo deu errado / Ocorreu um erro inesperado" (`ErrorBoundary.tsx:86-91`), and the global query
  toast shows `error.message` raw (`query-client.ts:58`).
- **Success** confirms the specific action ("Cliente cadastrado"), green toast; events the user did not
  trigger are operational notifications → `KB § PATTERNS/frontend/notification-classes.md`.
- **Loading** never claims emptiness; long jobs say what stage they are in.
- **Sample data** in a mockup is labelled as sample (`prototype-on-real-data.md` § 0).

---

## 13 · Review checklist and anti-pattern gallery

### 13.1 One-page checklist (run before returning a UI slice)

- [ ] Mockup validated; built from canonical organs; no new component that the catalog already has.
- [ ] Seed factories; no hand-wired providers/boundaries; routes via `lazyWithReload`.
- [ ] Entity hook file + key factory; every key from the factory; `enabled` guards; no `useEffect` fetch.
- [ ] Two-signal loading; error before empty; empty has a next action; success toast specific.
- [ ] Writes via `useCacheWriteMutation`; job starts hand off to polling; drafts announce unsaved.
- [ ] No state synced by an effect; derived values computed in render; resets via `key`.
- [ ] Forms: RHF + zod from contract; labels bound; `aria-invalid` + `aria-describedby`; pending submit; 422 → field.
- [ ] Keyboard walk-through; names on every control; dialogs trap/return focus; 24 px targets; no `div onClick`.
- [ ] Money/dates via seed helpers; `null` → "—"; date-only local; timestamps in the org zone.
- [ ] No `dangerouslySetInnerHTML`/`javascript:` URL; no secret in `VITE_*`.
- [ ] Tests: role/label queries, `user-event`, user-visible assertions, in-flight cache assertion for writes.
- [ ] 375 / 768 / 1440 px; full product vitest green through the hardware gate; keepers green.

### 13.2 Anti-pattern gallery (in tree, 2026-11-05)

| Anti-pattern | Example | Section |
|---|---|---|
| Hand-rolled modal (`div` + `onClick`, no focus management, unlabelled inputs) | `products/core/frontend/src/pages/admin/AdminPlans.tsx:176-181` | §4.2 · §7 · WE1 |
| ~~Seed dialog without focus trap/return~~ fixed 2026-11-05 | `seed/lib/frontend/src/design-system/ui/Dialog.tsx:110-160` | §4.2 |
| Missing value renders as a real zero | `seed/lib/frontend/src/utils.ts:26-27` | §8.2 · WE2 |
| Key literals drifting from the family | `products/social-wiring/frontend/src/hooks/useLeadsImport.ts:91`, `useOlxLeads.ts:97`, `useImovelWebLeads.ts:200,211` vs `useLeads.ts:53-54` | §3.2 · WE3 |
| Draft seeded by an effect | `products/core/frontend/src/pages/AccountSettings.tsx:15-21` | §1.3 · §6 |
| State reset by effects instead of `key` | `products/agents/frontend/src/pages/studio/tabs/SkillsTab.tsx:95-110` | §1.3 |
| Label not bound, error not described | `products/social-wiring/frontend/src/pages/Certidoes.tsx:775-780` | §6 |
| ~~JSON-LD re-serialised unescaped~~ fixed 2026-11-05 (`safeJsonLd`) | `products/core/frontend/src/website/components/SiteFaq.tsx:26` | §11 |
| Plain `lazy` on 38 routes | `products/core/frontend/src/main.tsx:19-56` | §9 |
| Generic error copy at the boundary | `seed/lib/frontend/src/components/ErrorBoundary.tsx:86-91` | §12 |
| Product tsconfig not strict (scaffold) | `products/seed/frontend/tsconfig.json:14-15` | §5 |

---

## Worked examples

### WE1 — Hand-rolled modal → seed Radix dialog (organs + a11y + testing)

**Before.** `products/core/frontend/src/pages/admin/AdminPlans.tsx:175-181`:
```tsx
{showModal && (
  <div className="fixed inset-0 bg-black/50 z-50 …" onClick={() => setShowModal(false)}>
    <div className="bg-card …" onClick={e => e.stopPropagation()}>
      <h2 …>{editingId ? 'Editar Plano' : 'Novo Plano'}</h2>
      <form onSubmit={handleSubmit} …>
        <label className="…">Nome</label>
        <input type="text" value={formData.nome} … />
```
Missing: `role="dialog"`/`aria-modal`/an accessible name; focus does not move into the dialog, is not
trapped, does not return to "Novo plano"; Esc does nothing; the backdrop closes on a drag that started
inside the panel (the bug the seed `Dialog` fixed, `Dialog.tsx:18-21`); every `<label>` is unbound
(`:181`, `:193`, `:205`, `:216`, `:227`, `:240`), so the inputs have no accessible name.

**After (shape).** Consume the Radix dialog (`CardHubDialog*`, `seed/lib/frontend/src/design-system/index.ts:141-150`)
— it implements the APG modal-dialog pattern (WAI-ARIA APG — Dialog (Modal); Radix — Dialog):
```tsx
<CardHubDialogRoot open={open} onOpenChange={setOpen}>
  <CardHubDialogTrigger asChild><Button>Novo plano</Button></CardHubDialogTrigger>
  <CardHubDialogContent>
    <CardHubDialogHeader><CardHubDialogTitle>{editingId ? 'Editar plano' : 'Novo plano'}</CardHubDialogTitle></CardHubDialogHeader>
    <form onSubmit={handleSubmit(onSave)}>
      <Label htmlFor="plano-nome">Nome</Label>
      <Input id="plano-nome" aria-invalid={!!errors.nome} aria-describedby={errors.nome ? 'plano-nome-erro' : undefined} {...register('nome')} />
      {errors.nome && <p id="plano-nome-erro" role="alert">{errors.nome.message}</p>}
      …
```
**Test (reads like a user).**
```tsx
const user = userEvent.setup();
await user.click(screen.getByRole('button', { name: /novo plano/i }));
expect(screen.getByRole('dialog', { name: /novo plano/i })).toBeInTheDocument();
expect(screen.getByLabelText(/nome/i)).toHaveFocus();          // or the first field Radix focuses
await user.keyboard('{Escape}');
expect(screen.getByRole('button', { name: /novo plano/i })).toHaveFocus();
```
**Seed follow-up (DONE 2026-11-05 — bare `Dialog` now has focus-in/trap/return).** It was to gain focus-in/trap/return (or become a thin wrapper
over the Radix one) so "consume the seed dialog" is accessible by construction — pilots first.

### WE2 — `formatCurrency(null)` lies with a zero (honest values)

**Before (fixed 2026-11-05: `formatCurrency` & siblings now return "—"; the `opts.empty` / `formatNumber` extras below remain future work).** `seed/lib/frontend/src/utils.ts:22-31`:
```ts
/** Returns "R$ 0,00" when value is null/undefined. */
export function formatCurrency(value: number | null | undefined): string {
  if (value == null) return 'R$ 0,00';
  return new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' }).format(value);
}
```
A revenue tile whose query returned `null` (no data yet, a field the endpoint does not fill) shows
"R$ 0,00" — indistinguishable from a real zero. Same family as the lying loading state: the screen
asserts something the server never said.

**After (shape, seed-level, pilots first).**
```ts
const BRL = new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' }); // built once
export const EMPTY_VALUE = '—';
export function formatCurrency(value: number | null | undefined, opts: { empty?: string } = {}): string {
  if (value == null || Number.isNaN(value)) return opts.empty ?? EMPTY_VALUE;
  return BRL.format(value);                        // 0 → "R$ 0,00": a real zero stays a zero
}
```
Plus `formatNumber`, `formatPercent`, `formatRelative` (Intl.RelativeTimeFormat) with the same
`null → "—"` contract, then a recurrence sweep of the 152 ad-hoc `toLocaleString(`/`new Intl.` sites in
the active FEs. Changing a seed default is a fleet change: grep every `formatCurrency(` consumer for a
caller that relied on the zero, prove it on three pilots, then fan out
(`KB § PATTERNS/architect/seed-canonical-defaults.md`). (MDN — Intl.NumberFormat.)

### WE3 — A key factory makes cache writes correct by construction

**Before.** social-wiring's leads hook defines two private prefixes —
`FAMILY_KEY = ["leads","list"]`, `DETAIL_KEY = ["leads","detail"]`
(`products/social-wiring/frontend/src/hooks/useLeads.ts:53-54`) — and uses them for its own queries and
cache-write targets (`:67`, `:79`, `:122`, `:128`, `:140`). Five sibling hooks cannot import them, so they
hand-type `["leads"]` (`useLeadsImport.ts:91`, `useOlxLeads.ts:97`, `useImovelWebLeads.ts:200,211`;
`useLeads.ts:92` itself). It works today only because `["leads"]` happens to be the common prefix; a
future list keyed `['lead-list', …]` or a typo would silently escape every one of those writes.

**After.** Export one factory from `useLeads.ts` (shape in §3.2) and use it everywhere:
```ts
useQuery({ queryKey: leadKeys.list(filters, params), … });
useCacheWriteMutation({ targets: [{ queryKey: leadKeys.lists(), match: 'prefix' }, …] });
qc.invalidateQueries({ queryKey: leadKeys.all });   // settle step of a cache write, never the only write
```
The seed already does this for clients (`seed/lib/frontend/src/clients/hooks.ts:57-71`). Ties to
`KB § PATTERNS/frontend/mutation-cache-writes.md` (§ Write the family — the family is derived from the
key convention, which a factory makes explicit).

---

## 14 · Sources

All URLs returned HTTP 200 on 2026-11-05 (the audit's verified list, plus the rows marked ★ fetched for
this doc). Primary sources first.

| Title | URL | Supports |
|---|---|---|
| Thinking in React | https://react.dev/learn/thinking-in-react | §1.1 |
| Choosing the State Structure ★ | https://react.dev/learn/choosing-the-state-structure | §1.1 · §2 |
| Rules of React | https://react.dev/reference/rules | §1.2 |
| You Might Not Need an Effect | https://react.dev/learn/you-might-not-need-an-effect | §1.3 |
| Preserving and Resetting State ★ | https://react.dev/learn/preserving-and-resetting-state | §1.4 |
| `<Suspense>` | https://react.dev/reference/react/Suspense | §1.5 |
| useTransition | https://react.dev/reference/react/useTransition | §1.5 · §9 |
| Component — error boundaries | https://react.dev/reference/react/Component#catching-rendering-errors-with-an-error-boundary | §1.6 |
| React Compiler (+ Installation: "supports React 17 and 18") | https://react.dev/learn/react-compiler | §1.7 |
| TanStack Query — Important Defaults | https://tanstack.com/query/latest/docs/framework/react/guides/important-defaults | §3.1 |
| TanStack Query — Query Keys | https://tanstack.com/query/latest/docs/framework/react/guides/query-keys | §3.2 |
| TanStack Query — Render Optimizations | https://tanstack.com/query/latest/docs/framework/react/guides/render-optimizations | §3.4 |
| TanStack Query — Placeholder Query Data ★ | https://tanstack.com/query/latest/docs/framework/react/guides/placeholder-query-data | §3.5 |
| TanStack Query — Optimistic Updates | https://tanstack.com/query/latest/docs/framework/react/guides/optimistic-updates | §3.6 |
| TanStack Query — Query Invalidation ★ | https://tanstack.com/query/latest/docs/framework/react/guides/query-invalidation | §3.6 |
| Effective React Query Keys (TkDodo) | https://tkdodo.eu/blog/effective-react-query-keys | §3.2 |
| Practical React Query (TkDodo) | https://tkdodo.eu/blog/practical-react-query | §2 |
| TanStack Virtual ★ | https://tanstack.com/virtual/latest | §9 |
| React Router — useSearchParams ★ | https://reactrouter.com/api/hooks/useSearchParams | §2 |
| Atomic Design, ch. 2 (Brad Frost) | https://atomicdesign.bradfrost.com/chapter-2/ | §4.1 |
| Compound components with hooks (KCD) | https://kentcdodds.com/blog/compound-components-with-react-hooks | §4.3 |
| Radix Primitives — Accessibility | https://www.radix-ui.com/primitives/docs/overview/accessibility | §4.2 · §7 |
| Radix Primitives — Dialog ★ | https://www.radix-ui.com/primitives/docs/components/dialog | WE1 |
| TSConfig `strict` | https://www.typescriptlang.org/tsconfig/#strict | §5 |
| TSConfig `noUncheckedIndexedAccess` | https://www.typescriptlang.org/tsconfig/#noUncheckedIndexedAccess | §5 |
| TypeScript — Narrowing, discriminated unions ★ | https://www.typescriptlang.org/docs/handbook/2/narrowing.html#discriminated-unions | §5 |
| TypeScript 4.9 release notes (`satisfies`) ★ | https://www.typescriptlang.org/docs/handbook/release-notes/typescript-4-9.html | §5 |
| React Hook Form — useForm | https://react-hook-form.com/docs/useform | §6 |
| React Hook Form — setError ★ | https://react-hook-form.com/docs/useform/seterror | §6 |
| Zod | https://zod.dev/ | §6 |
| W3C WAI — Forms Tutorial | https://www.w3.org/WAI/tutorials/forms/ | §6 |
| WCAG 2.2 | https://www.w3.org/TR/WCAG22/ | §7 |
| Understanding 3.3.1 Error Identification ★ | https://www.w3.org/WAI/WCAG22/Understanding/error-identification.html | §6 |
| Understanding 2.5.8 Target Size (Minimum) — "24 by 24 CSS pixels" | https://www.w3.org/WAI/WCAG22/Understanding/target-size-minimum.html | §7 |
| Understanding 2.4.11 Focus Not Obscured (Minimum) ★ | https://www.w3.org/WAI/WCAG22/Understanding/focus-not-obscured-minimum.html | §7 |
| Understanding 4.1.3 Status Messages ★ | https://www.w3.org/WAI/WCAG22/Understanding/status-messages.html | §7 |
| WAI-ARIA Authoring Practices Guide | https://www.w3.org/WAI/ARIA/apg/ | §7 |
| APG — Dialog (Modal) pattern | https://www.w3.org/WAI/ARIA/apg/patterns/dialog-modal/ | WE1 |
| MDN — aria-live ★ | https://developer.mozilla.org/en-US/docs/Web/Accessibility/ARIA/Reference/Attributes/aria-live | §7 |
| eslint-plugin-jsx-a11y | https://github.com/jsx-eslint/eslint-plugin-jsx-a11y | §7 |
| axe-core | https://github.com/dequelabs/axe-core | §7 |
| Playwright — Accessibility testing | https://playwright.dev/docs/accessibility-testing | §7 · §10 |
| eMAG (Modelo de Acessibilidade em Governo Eletrônico) | https://emag.governoeletronico.gov.br/ | §7 |
| gov.br — Modelo de Acessibilidade (eMAG) ★ | https://www.gov.br/governodigital/pt-br/acessibilidade-e-usuario/acessibilidade-digital/modelo-de-acessibilidade | §7 |
| MDN — Intl.NumberFormat | https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Intl/NumberFormat | §8 · WE2 |
| MDN — Intl.DateTimeFormat | https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Intl/DateTimeFormat | §8 |
| MDN — Intl.RelativeTimeFormat ★ | https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Intl/RelativeTimeFormat | §8 |
| MDN — Intl.PluralRules ★ | https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Intl/PluralRules | §8 |
| Web Vitals | https://web.dev/articles/vitals | §9 |
| Defining the Core Web Vitals thresholds ★ | https://web.dev/articles/defining-core-web-vitals-thresholds | §9 |
| Interaction to Next Paint — "200 milliseconds" good | https://web.dev/articles/inp | §9 |
| Optimize LCP | https://web.dev/articles/optimize-lcp | §9 |
| Cumulative Layout Shift | https://web.dev/articles/cls | §9 |
| Rendering performance | https://web.dev/articles/rendering-performance | §9 |
| Vite — dynamic import | https://vite.dev/guide/features.html#dynamic-import | §9 |
| Vite — Env Variables and Modes ★ | https://vite.dev/guide/env-and-mode | §11 |
| Testing Library — Guiding Principles | https://testing-library.com/docs/guiding-principles | §10 |
| Testing Library — Query priority | https://testing-library.com/docs/queries/about/#priority | §10 |
| Testing Library — user-event ★ | https://testing-library.com/docs/user-event/intro | §10 |
| The Testing Trophy (Kent C. Dodds) | https://kentcdodds.com/blog/the-testing-trophy-and-testing-classifications | §10 |
| MSW docs | https://mswjs.io/docs/ | §10 |
| Playwright — Best practices | https://playwright.dev/docs/best-practices | §10 |
| OWASP — XSS Prevention Cheat Sheet | https://cheatsheetseries.owasp.org/cheatsheets/Cross_Site_Scripting_Prevention_Cheat_Sheet.html | §11 |
| OWASP — Content Security Policy Cheat Sheet | https://cheatsheetseries.owasp.org/cheatsheets/Content_Security_Policy_Cheat_Sheet.html | §11 |
| HTML Standard — restrictions for contents of script elements ★ | https://html.spec.whatwg.org/multipage/scripting.html#restrictions-for-contents-of-script-elements | §11 |
| NN/g — 10 Usability Heuristics | https://www.nngroup.com/articles/ten-usability-heuristics/ | §12 |
| NN/g — Error-Message Guidelines | https://www.nngroup.com/articles/error-message-guidelines/ | §12 |
| NN/g — Designing Empty States ★ | https://www.nngroup.com/articles/empty-state-interface-design/ | §12 |

**Not verified — do not cite as authority until re-checked:** Lei 13.146/2015 (LBI) on planalto.gov.br
(`https://www.planalto.gov.br/ccivil_03/_ato2015-2018/2015/lei/l13146.htm` — connection timed out
2026-11-05, as in the audit); the specific article on accessible websites (art. 63) is cited from the
audit, unverified.

---

## Composes with

`KB § PATTERNS/frontend/frontend.md` (layer structure, toasts, jobPolling, Sidebar) ·
`KB § PATTERNS/frontend/lying-loading-state.md` · `KB § PATTERNS/frontend/mutation-cache-writes.md` ·
`KB § PATTERNS/frontend/silent-refusal.md` · `KB § PATTERNS/frontend/prototype-on-real-data.md` ·
`KB § PATTERNS/common/server-state-family-index.md` · `KB § PATTERNS/architect/products-consume-canonical-organs.md` ·
`KB § PATTERNS/devops/dev-prod-parity.md` · skills `noc-organ-consume-check` · `noc-cache-writes` ·
`noc-perf-probe` · `noc-fast-responses` · `noc-wiring-audit` · `noc-contract-first`.
