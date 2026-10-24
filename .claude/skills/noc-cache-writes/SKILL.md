---
name: noc-cache-writes
description: Use when writing or migrating a TanStack mutation in any product or the seed — triggers "add a mutation", "create/update/delete hook", "useMutation", "invalidateQueries", "the list updates late", "shows up after a second", "optimistic update", "migrate hooks to cache writes", "fan out useCacheWriteMutation", "stays stale after Salvar", "never updates after starting a job", or check_mutation_invalidate_only / check_mutation_family_write / check_job_start_without_handoff blocking a commit. Every write puts what it knows into every entry it touches; a queued job hands off to polling; never invalidate-only.
version: 1.6.0
---

# noc-cache-writes — a write puts what it knows into the cache

An invalidate-only `useMutation` throws the server's answer away and refetches, so the screen disagrees with the toast for write + refetch (orbity lead note ~2 s, 2026-10-21). The rule, primitive and keeper are the structural answer. → `KB § PATTERNS/frontend/mutation-cache-writes.md`

## Writing a NEW mutation

1. **Plain CRUD resource?** Use `createCrudHooks` (`@noctusai/lib/hooks`) — it already writes the cache. Done.
2. **Otherwise** `useCacheWriteMutation` (`@noctusai/lib/cache-writes`). Reference shape: the scaffold's `products/seed/frontend/src/hooks/useExample.ts`.
3. **Per target, pick** (the KB "Choosing per write" section):
   - result predictable from input (note, toggle, rename, delete, drag) → `optimistic` + `commit`;
   - server decides (generated number, assigned stage, computed total) → `commit` only;
   - derived views (counts, dashboards, funnels) → `invalidate: [...]`, never recompute client-side;
   - lists keyed by filters → one `{ queryKey: [prefix], match: 'prefix' }` target reaches all of them; `listOps` leave non-arrays (details, `{items}` envelopes) alone.
   - envelopes: `listOps.within(old, 'items', (l) => listOps.…)` for `{items|itens|…: []}`; `pageOps` (paginated `{data,pagination}` / `{items,total}` — keeps the total honest). `rowOps` (patch/remove/add on a bare array, an envelope or a detail entity under ONE prefix target), `boardOps(getCardValue)` (pipeline `PipelineColumn[]`: patchCard/removeCard/addCard/moveCard) and the target builders `patchById` / `removeById` / `addTo`. All from `@noctusai/lib/cache-writes`. **Never write a product-local cache-ops helper** — a missing shape is a seed addition.
4. **Insert where the server's sort puts it** (`created_at desc` → `prepend` + `replace(old, tempId, saved, 'prepend')`), and render the cache in that order — no `.reverse()`/re-sort in the component, or the row jumps when the settle refetch lands.
5. **New row stand-in** → `{ id: tempId, ... }` from the ctx; commit with `listOps.replace(old, tempId, saved)` (never duplicates).
6. **Keep the caller's UX** — toasts, `form.reset`, `navigate` stay in `onSuccess`/`onError`; they run after the cache work.
7. **Raw `useMutation` with `setQueryData(K)`?** That write is EXACT — also `invalidateQueries({ queryKey: K })` (prefix) so the reads under `K` (`[...K, "estruturada"]`) refresh, or use `useCacheWriteMutation` (its settle does). Keeper `check_mutation_family_write`.
8. **The write QUEUES server work** (answer = job/consulta id, 202, "queued")? It cannot place the result — `handOffToPolling(qc, readKey)` (`@noctusai/lib`) instead of a bare invalidate, so the polled read keeps polling until the job ran. A result read with no in-progress marker spreads `jobPolling(() => false, POLL_MS)`. Keeper `check_job_start_without_handoff`.
9. **Genuinely can't place it** (server regroups the whole view, a mutation with no cached read, a fire-and-forget action like "send email") → keep `useMutation`, put `// noc-allow: invalidate-only — <why>` on the `useMutation(` line. A reason is mandatory; "too hard" is not one.

## MIGRATING an existing file (the fan-out procedure)

1. `python mcp/noctusai/cli.py --check-mutation-invalidate-only` / the baseline JSON lists the files + counts. Work file by file.
2. For each mutation, read the QUERY it should update first (its key factory + response shape: array? `{items}`? detail?). The mutation's target is that key, not a guess.
3. Rewrite per the "new mutation" rules. Preserve every side effect the old `onSuccess` had (toasts, extra invalidations → `invalidate`, callbacks).
4. Tests: for each file you touch, at least one test asserting the cache WHILE the request is in flight (deferred promise) — see `products/orbity/frontend/src/hooks/__tests__/useCrm.test.ts` "cache writes". Existing tests that asserted `invalidateQueries` calls may need updating to the new contract, never deleting coverage.
5. `python mcp/noctusai/cli.py --lower-mutation-invalidate-only-baseline` — re-derives the ratchet downward. On a rebase CONFLICT in `mcp/noctusai/tests/mutation_invalidate_only_baseline.json`: take either side, re-run this flag, stage. Never hand-merge it.
6. Gates: product `tsc --noEmit`, `vitest run`, `vite build`; `--check-mutation-invalidate-only` + `--check-stale-after-write` clean.

- **Settle is background, never awaited.** `onSettled` fires the invalidations (`void`), it never returns them: TanStack awaits a returned promise, which would keep `isPending` true (buttons stuck on "Adicionando…") until the refetches finish. Don't write a plain `useMutation` whose `onSettled` returns `invalidateQueries`.

## Op reference (seed `@noctusai/lib/cache-writes`) — v1.4.0
- `listOps` — `append/prepend/replace/patch/remove/update/insertSorted/merge/within`. Rows by `id` or the trailing `idKey` arg (`'hostname'`, `'slug'`); ids may be `string | number`. `insertSorted(list, row, compare)` lands a create where the server's sort puts it (never append-then-re-sort).
- **Nested edit** (a row inside a row): `listOps.update(list, parentId, (p) => ({ ...p, children: listOps.prepend(p.children, c) }))`; in an envelope wrap with `listOps.within(old, 'items', (l) => listOps.update(l, ...))`. Decision: a one-line `update` beats nested map lambdas; no dedicated "nested" op.
- **Key-aware writes**: `commit`/`optimistic` receive the concrete `queryKey` as a trailing argument (optional in the type); a `match: 'prefix'` target takes `predicate: (queryKey) => boolean` to touch only the matching filtered lists (account/scope/archived) — never commit a create into lists it does not belong in.
- `infiniteOps` — `{ pages, pageParams }` caches: `patch/replace/remove` by id across pages, `prepend` into page 1 (replaces if already present), `mapPages`. Pages may be bare arrays or `pageOps` envelopes; `pageParams` untouched.
- `pageOps.insertSorted(page, row, compare, idKey?)` places a row at its server-sorted spot on an envelope and moves `total` (+1 new, 0 replace). `idKey` is a field name OR a function `(row) => id` (nested ids) in `listOps`/`pageOps`/`infiniteOps`. `infiniteOps.remove/prepend` move `total` on EVERY page that carries one (each page repeats the whole-list total; a list reading it from its last page must not lag). `boardOps` only adjusts `total`/`valorTotal` columns that have them (no NaN).
- `pageOps.prependNewest` treats an envelope with no `page`/`pagination.page` as page 1.

## Guardrails
- Inactive products (catalog `ativo=false`, not in `deploy/fleet/active-scope.txt`) are asleep — don't migrate them; the ratchet keeps them from growing.
- A seed organ's hook factory (`seed/lib/frontend/src/**/hooks.ts`, `create*Hooks`) is migrated in the SEED, never wrapped per product.
- Unit-green ≠ live: after deploy, live-check one migrated write on the product (the change shows on click, survives a reload).

## Depth
`KB § PATTERNS/frontend/mutation-cache-writes.md` · `KB § PATTERNS/frontend/lying-loading-state.md`.
