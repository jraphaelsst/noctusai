---
name: noc-cache-writes
description: Use when writing or migrating a TanStack mutation in any product or the seed — triggers "add a mutation", "create/update/delete hook", "useMutation", "invalidateQueries", "the list updates late", "shows up after a second", "optimistic update", "migrate hooks to cache writes", "fan out useCacheWriteMutation", or check_mutation_invalidate_only blocking a commit. Every write puts what it knows into the cache; never invalidate-only.
version: 1.0.0
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
4. **New row stand-in** → `{ id: tempId, ... }` from the ctx; commit with `listOps.replace(old, tempId, saved)` (never duplicates).
5. **Keep the caller's UX** — toasts, `form.reset`, `navigate` stay in `onSuccess`/`onError`; they run after the cache work.
6. **Genuinely can't place it** (server regroups the whole view, a mutation with no cached read, a fire-and-forget action like "send email") → keep `useMutation`, put `// noc-allow: invalidate-only — <why>` on the `useMutation(` line. A reason is mandatory; "too hard" is not one.

## MIGRATING an existing file (the fan-out procedure)

1. `python mcp/noctusai/cli.py --check-mutation-invalidate-only` / the baseline JSON lists the files + counts. Work file by file.
2. For each mutation, read the QUERY it should update first (its key factory + response shape: array? `{items}`? detail?). The mutation's target is that key, not a guess.
3. Rewrite per the "new mutation" rules. Preserve every side effect the old `onSuccess` had (toasts, extra invalidations → `invalidate`, callbacks).
4. Tests: for each file you touch, at least one test asserting the cache WHILE the request is in flight (deferred promise) — see `products/orbity/frontend/src/hooks/__tests__/useCrm.test.ts` "cache writes". Existing tests that asserted `invalidateQueries` calls may need updating to the new contract, never deleting coverage.
5. `python mcp/noctusai/cli.py --lower-mutation-invalidate-only-baseline` — re-derives the ratchet downward. On a rebase CONFLICT in `mcp/noctusai/tests/mutation_invalidate_only_baseline.json`: take either side, re-run this flag, stage. Never hand-merge it.
6. Gates: product `tsc --noEmit`, `vitest run`, `vite build`; `--check-mutation-invalidate-only` clean.

## Guardrails
- Inactive products (catalog `ativo=false`, not in `deploy/fleet/active-scope.txt`) are asleep — don't migrate them; the ratchet keeps them from growing.
- A seed organ's hook factory (`seed/lib/frontend/src/**/hooks.ts`, `create*Hooks`) is migrated in the SEED, never wrapped per product.
- Unit-green ≠ live: after deploy, live-check one migrated write on the product (the change shows on click, survives a reload).

## Depth
`KB § PATTERNS/frontend/mutation-cache-writes.md` · `KB § PATTERNS/frontend/lying-loading-state.md`.
