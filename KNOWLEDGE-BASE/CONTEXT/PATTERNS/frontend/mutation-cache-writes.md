# Mutation cache writes — a write puts what it knows into the cache

> **Rule.** A mutation never only invalidates. It **draws** the change on the click when it can (optimistic), **commits** the server's answer into the cache the moment it arrives, and only then **settles** with a background invalidate. Use the seed primitive:
>
> ```ts
> import { listOps, useCacheWriteMutation } from "@noctusai/lib/cache-writes";
>
> return useCacheWriteMutation<Activity, { leadId: string; payload: ActivityCreate }>({
>   mutationFn: ({ leadId, payload }) => api.post(`/api/crm/leads/${leadId}/activities`, payload),
>   targets: ({ leadId }) => [{
>     queryKey: crmKeys.activities(leadId),
>     optimistic: (old, { payload }, { tempId }) => listOps.append(old, { id: tempId, ...draft(payload) }),
>     commit: (old, saved, _vars, { tempId }) => listOps.replace(old, tempId, saved),
>   }],
>   invalidate: [crmKeys.funil()],             // derived views refresh in the background
>   onSuccess: () => toast.success("Atividade registrada"),
> });
> ```
>
> Keeper `check_mutation_invalidate_only` (ratchet, high, pre-commit blocking): a raw `useMutation({...})` with neither `onMutate` nor `setQueryData` may not be added; the per-file count in `mcp/noctusai/tests/mutation_invalidate_only_baseline.json` only goes down.

## Why — the incident

On 2026-10-21, while live-testing orbity's new lead delete, the owner saw a saved lead note appear **about two seconds late**:
- the toast said "Atividade registrada";
- the list right under it still said "Nenhuma atividade registrada".

The hook was the fleet's default shape:

```ts
onSuccess: () => qc.invalidateQueries({ queryKey: crmKeys.activities(leadId) })
```

The POST had already returned the created row, and the hook threw it away and fetched the whole list again. So the user waited for **two** sequential round trips before the screen agreed with the toast. At orbity's measured API latency (p50 453 ms, p90 1.6 s, same day), that is 1–3 s of the UI contradicting itself.

The owner's read was that this is not a cosmetic bug but **architectural drift**, and the numbers agreed. A sweep of every `useMutation({...})` in the fleet that day found:

| | count |
|---|---:|
| mutations | 1,049 |
| optimistic (`onMutate`) | 18 |
| write the server result (`setQueryData`) | 49 |
| **invalidate-only** | **982 (94%)** |

The few optimistic ones (the seed pipeline and card-hub organs, orbity's kanban drag) were each hand-rolled. There was no shared primitive, no pattern and no gate, so the cheap shape won by default.

## The contract (what `useCacheWriteMutation` does)

| Step | When | What |
|---|---|---|
| optimistic | `onMutate`, per target that defines it | cancel in-flight fetches of that key (a late refetch would erase the drawing), snapshot, draw the change. New rows get a stand-in id from `optimisticId()` (`optimistic:` prefix; `isOptimistic(row)` tells them apart) |
| commit | `onSuccess`, per target that defines it | write the **server's** answer, replacing the stand-in. Correct after ONE round trip even without optimism |
| rollback | `onError` | restore every snapshot |
| settle | `onSettled` | background-invalidate every target + `invalidate` keys, so server-computed fields converge. Data is already on screen, so this is a refresh (`isFetching && !!data`), never a skeleton — see `lying-loading-state.md` |

The caller's `onSuccess` and `onError` still run after the cache work, so toasts and form resets stay where they were.

`listOps` holds the pure edits: `append`, `prepend`, `replace` (stand-in → server row, never duplicating when a refetch already brought it), `patch`, `remove`, and `merge` (one detail object). An uncached entry passes through untouched (nothing to draw on; the next read fetches it), and so does anything that is not an array — a detail object or a paginated `{ items }` envelope — so a list edit can never mangle it.

**Lists keyed by filters.** A target with `match: 'prefix'` reaches EVERY cached entry whose key starts with `queryKey`: `{ queryKey: ['clientes'], match: 'prefix', optimistic: (old, id) => listOps.remove(old, id) }` removes the row from `['clientes', undefined]`, `['clientes', {status:'open'}]` and any other cached list in one target, snapshots each, and rolls each back on failure. Details sharing the prefix are skipped by the non-array rule.

## Where the contract lives (structural, not per product)

| Layer | What carries the contract |
|---|---|
| seed primitive | `useCacheWriteMutation` + `listOps` (`@noctusai/lib/cache-writes`) |
| seed CRUD factory | `createCrudHooks` (`@noctusai/lib/hooks`) — `useCreate` commits the server row into the unfiltered list, `useUpdate` draws the edit in every list (prefix) and the detail then commits the server row, `useDelete` removes on click. Every consumer (incl. the `ResourceManager` organ) inherits it |
| seed organ hook factories | `seed/lib/frontend/src/**/hooks.ts`, `create*Hooks` — migrated in the seed, so every product consuming the organ inherits it |
| new-product scaffold | `products/seed/frontend/src/hooks/useExample.ts` (→ `templates/product-seed`) is the reference shape: TanStack reads with the two-signal render rule + cache-write create/update/delete |
| procedure | skill `noc-cache-writes` (writing a new mutation · migrating a file · resolving a baseline conflict) |
| gate | keeper `check_mutation_invalidate_only` — ratchet, pre-commit blocking; `--lower-mutation-invalidate-only-baseline` re-derives the baseline downward (never raises) |
| always-on rule | CLAUDE.md §1 "Frontend server state" family → `KB § PATTERNS/common/server-state-family-index.md` |

## Choosing per write

- **Draw optimistically** when the result is predictable from the input: a note, a toggle, a rename, a removal, a drag.
- **Commit only** when the server decides something the client can't predict, such as an assigned stage, a computed total or a generated number. orbity's `useCreateLead` does this, because the server places a lead with no stage in the org's first stage.
- **Invalidate a derived view** (funnel counts, dashboards) instead of recomputing it client-side.
- **Genuinely can't place it** (the server regroups the whole view): keep the invalidate, but mark the `useMutation(` line with `// noc-allow: invalidate-only — <why>`. That is a declared exception, not the default.

## What this does NOT fix — the other half of the latency

A cache write hides a slow write. It does not make reads fast. The same day's profile of one orbity read (`GET /api/crm/leads/{id}/activities`, 564 ms) found:
- 5–8 sequential network calls per request, most on a freshly built supabase client (a new TLS handshake each);
- a second, redundant Supabase Auth `get_user`, from `make_supabase_client` calling `set_session`;
- all of it synchronous I/O inside `async def` on a single uvicorn worker, so concurrent requests queue behind each other. Parallel calls finished as a staircase: 985, 1,524 and 2,081 ms.

That backend work is tracked separately in the seed request path (auth dependencies, `integrations/database.py`, `noctusai_seed/database.py`). Both halves are needed: cache writes for perceived latency, a faster request path for everything else.

## Pilot and fan-out

- **Pilot #1 (2026-10-21):** orbity CRM (`products/orbity/frontend/src/hooks/useCrm.ts`).
  - Note add: optimistic + commit.
  - Lead delete: optimistic removal from the funil.
  - Lead update and move: commit into the funil + the lead detail; the move is also optimistic.
  - Lead create: commit into the first stage.
  - Regression tests in `hooks/__tests__/useCrm.test.ts` assert what is in the cache while the request is still in flight. They fail on the old hooks.
- **Fan-out (owner, 2026-10-21: "fan out to all products … structural, not local").** Pilots-first cadence (`KB § PATTERNS/architect/project-execution.md`): orbity (pilot 1) → seed organs + `createCrudHooks` (reach every consumer, incl. inactive products, through the seed) → active products in parallel slices (agents, igig, academia-de-reciclagem, core, commerce, social-wiring). Inactive products (`deploy/fleet/active-scope.txt`) are asleep and are NOT migrated by hand; the ratchet keeps them from growing and they inherit every seed-level fix. Parallel slices never hand-merge the baseline — on conflict, take either side and run the lower flag.

## Related

`lying-loading-state.md` (render rules for refetch vs first load) · `inbox-chat-surface.md` (a realtime stream patching the cache: the same "write what you know" idea for pushed data) · `product-internal-wiring.md`.
