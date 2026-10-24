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

**Envelopes.** `listOps.within(env, field, fn)` applies any list op to the array an envelope keeps under `field` (`{items}`, `{itens}`, `{colecoes}` …). `pageOps` (`patch` / `replace` / `remove` / `prependNewest`) edits paginated pages (`{data, pagination.total}` / `{items, total}`) and keeps the total in step. `pageOps.add` and the `itens` envelope key cover small unpaginated envelopes. **Mixed shapes under one prefix:** `rowOps` (`patch` / `remove` / `add`) edits a bare array, an envelope or a detail entity, with target builders `patchById` / `removeById` / `addTo`; `boardOps(getCardValue, getCardId?)` (`patchCard` / `removeCard` / `addCard` / `moveCard`) edits the pipeline organ's `PipelineColumn[]` board — `createPipelineHooks.useMoveCard` uses `moveCard`. All are exported from `@noctusai/lib/cache-writes`. Wave 1 of the fan-out grew three product- or organ-local copies of these helpers (agents `cacheEnvelope`, seed `envelopeOps`, igig `rowOps`/`boardOps`, lifted as `row-ops.ts`); they were folded into the seed — a missing shape is a seed addition, never a local helper.

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
- **Insert where the server's ORDER puts it.** The cache holds the list in the API's order; the stand-in and the committed row must sit where the settle refetch will put them (`prepend` + `replace(..., 'prepend')` for a `created_at desc` list, `append` for asc). Render in that same order — never re-sort or `.reverse()` in the component. Otherwise the row jumps when the refetch lands. Live, 2026-10-21: orbity's notes API returned newest first, the panel `.reverse()`d it, and the optimistic note was appended, so it showed on top, then dropped to the bottom on the refetch. The owner also asked for newest first, so the panel now renders the API order and the hook prepends.
- **Invalidate a derived view** (funnel counts, dashboards) instead of recomputing it client-side.
- **Genuinely can't place it** (the server regroups the whole view): keep the invalidate, but mark the `useMutation(` line with `// noc-allow: invalidate-only — <why>`. That is a declared exception, not the default.

- **Settle never holds the mutation pending.** `useCacheWriteMutation` fires the settle invalidations without returning them; a returned promise from `onSettled` is awaited by TanStack, so `isPending` would stay true (and `isSuccess` false) until every refetch landed. Regression-tested with a deferred refetch.

## Write the family, not one key (2026-10-24, F88)

`setQueryData(K, …)` is **exact**; `invalidateQueries({ queryKey: K })` is a **prefix** match. A raw `useMutation` that writes `K` and never refreshes `K`'s family leaves every read whose key extends `K` with a NAMED child — `[…"negociacao"]` → `[…"negociacao","estruturada"]`, `[…"negociacao","conflitos"]` — showing the pre-write answer (social-wiring replay F88: "Valor negociado não informado" after Salvar). The family is derived from the query-key convention: a derived view of a row lives UNDER the row's key, so a prefix invalidation reaches it by construction.

- `useCacheWriteMutation` already does it — its settle invalidates every target's key (a prefix match).
- A raw `useMutation` writing `K` also invalidates `K` (or an ancestor), or each named child.
- An id-wildcard child (`[…"chats"]` → `[…"chats", <id>, "messages"]`) is a sub-resource of ONE element, not a view derived from the collection — it is not part of the family the write must refresh.
- Genuinely independent named child (e.g. an access log under the row's key): `// noc-allow: exact-write — <why>` on the `useMutation(` line.

Keeper `check_mutation_family_write` (blocking, pre-commit `--check-stale-after-write`) resolves every product's query keys to segments (`query_key_family_predicate.py`: `[...]` literals, spreads, key factories across `@/` imports, string-literal arguments) and flags a write whose family has an unrefreshed named child. A key it cannot resolve is skipped, never guessed. **Why `check_mutation_invalidate_only` missed it:** that keeper asks only "is there ANY `setQueryData`/`onMutate` in the block?" — F88's mutation had one, so it passed. (Measured on the pre-fix tree: F88's `useNegociacaoMutation` also reached the aggregate through `invalidateExtracaoDependentes`' broad `["sw","clientes"]` prefix, so its own site reads as refreshed — the family rule closes the shape, the explicit invalidate in 203b6a1b5 stays as the in-place fix.)

## Async jobs hand off to polling (2026-10-24, F87)

A write that QUEUES server-side work — the answer is a job / consulta id, a 202, "queued" — cannot put the job's result into the cache: it does not exist yet. Invalidating the polled read is not enough either: the refetch can land BEFORE the worker created or flagged the rows, `jobPolling(isActive)` sees nothing in flight, and the poll never starts (social-wiring F87: after "Solicitar emissão" the certidões grid never moved until a reload).

- The write calls **`handOffToPolling(qc, readKey, options?)`** (`@noctusai/lib`, `job-polling.ts`) instead of a bare invalidate. Every `jobPolling` read under `readKey` (prefix match) is re-read now and keeps polling until it has SEEN the job active and settled, or `graceMs` (default 90 s) passes.
- `until: 'changed'` for a read with no in-progress marker (a draft that "appears"); `until: (data, before) => …` when the landing is one field moving (a profile's `ultima_sync_em`).
- A read that shows the job's result but has no in-progress marker spreads `jobPolling(() => false, POLL_MS)` — it polls ONLY while a hand-off is pending.
- A write whose answer already IS the in-flight state (a cache-write commit into the polled entry) needs no hand-off; so does a cancel that ENDS work (`// noc-allow: no-job-handoff — <why>`), and a caller that follows the returned job id with its own `jobPolling` read (meta-ads `useSyncJob`).

Keeper `check_job_start_without_handoff` (blocking, same CLI flag) marks a mutation as a job start when its response type carries a job-shaped id (`job_id`, `consulta_id(s)`, `run_id`, `sync_id`, …), it handles a 202, or its own `noc-allow: invalidate-only` reason says the work is queued / background / asynchronous. **Why the existing keepers missed it:** F87's mutation carried an honest `noc-allow: invalidate-only — queues emissions that finish asynchronously; … the polled partes read` — the allow was the escape hatch of the only keeper that looked, and nothing checked that the polled read would actually poll.

## Drafts say they are unsaved (2026-10-24, F91)

A form that holds a local draft seeded from the server and persists it on "Salvar" shows values the server does not have. Unless the screen SAYS so, a typed or picked value reads as applied — and is gone on reload (F91: the condomínio chip looked linked, nothing was saved). There is no precise static rule for "displayed value diverges from persisted state" (it is a runtime relation, not a syntactic one), so the mechanism is the seed organ, not a keeper:

- **`useUnsavedChanges(draft, saved, { fields? })`** → `{ dirty, changed }` + a `beforeunload` guard while dirty; **`<UnsavedChangesNotice dirty />`** is the on-screen half ("Alterações não salvas — clique em Salvar."). `saved` is the persisted value in the draft's own shape (the same `toDraft`); `undefined` while loading ⇒ clean. `null` ≡ `undefined` ≡ `""`.
- **`useBeforeUnloadGuard(active)`** when "unsaved" is not a draft-vs-saved comparison (autosave writes in flight, a custom equality already computed).
- A selector whose chip LOOKS applied is not a draft at all: persist it on pick (F91's fix), keep the rest of the card on the hook.
- Inline multi-field Salvar cards adopt it (social-wiring, 2026-10-24): ImovelCartorioCard, ImovelEnderecoCard, ImovelAvaliacaoSection, ImovelCertidoesCard (CertidaoEditor), QualificacaoContratoForm, DadosPessoaisForm, NegociacaoPanel, TermosNegocioSection, MatriculaAtoDetalhesEditor (guard), edição-de-fotos Configurações, Settings › Dados da imobiliária, SimecConfigEditor (guard), CerebroEditor (guard), CerebroPerguntas (autosave guard). Dialogs/drawers are out of scope — closing them is the container's job (`SideDrawer dirty`).

## Seed ops (additive gap-closing, 2026-10-21)

- `listOps` addresses rows by `id` or a trailing `idKey`; ids are `string | number`. `listOps.update(list, id, fn)` is the nested-edit idiom (a row inside a row, with `within` for envelopes); `listOps.insertSorted(list, row, compare)` places a create where the server's sort would.
- Key-aware writes: `commit`/`optimistic` get the concrete `queryKey` as a trailing argument; a `match: 'prefix'` target accepts `predicate(queryKey)` to edit only the filtered lists the row belongs to (a create committed into every account's list is a cross-account leak).
- `infiniteOps` (`patch/replace/remove/prepend/mapPages`) edits `useInfiniteQuery` caches `{ pages, pageParams }` without touching `pageParams`.
- `pageOps.insertSorted(page, row, compare, idKey?)` — sorted insert into an envelope, `total` +1 on a new row, 0 on a replace. Pass the server's comparator; never re-sort in a component.
- `idKey` is a field name or a function `(row) => id` in `listOps` / `pageOps` / `infiniteOps` (nested ids such as `row.empresa.id`).
- `infiniteOps.remove` / `prepend` move `total` on every page that carries one (default chosen because each page repeats the WHOLE-list total, so a view reading it from the last or first page would otherwise show it off by one). Bare-array pages carry none.
- `boardOps` tolerates columns without `total` / `valorTotal`: it adjusts only the aggregates that exist, never writes NaN.
- `pageOps.prependNewest` assumes page 1 when the envelope carries no page number.

## What this does NOT fix — the other half of the latency

A cache write hides a slow write. It does not make reads fast. The same day's profile of one orbity read (`GET /api/crm/leads/{id}/activities`, 564 ms) found:
- 5–8 sequential network calls per request, most on a freshly built supabase client (a new TLS handshake each);
- a second, redundant Supabase Auth `get_user`, from `make_supabase_client` calling `set_session`;
- all of it synchronous I/O inside `async def` on a single uvicorn worker, so concurrent requests queue behind each other. Parallel calls finished as a staircase: 985, 1,524 and 2,081 ms.

That backend work is `request-path-latency.md` (seed auth dependencies, `integrations/database.py`, `noctusai_seed/database.py`). Both halves are needed: cache writes for perceived latency, a faster request path for everything else.

## Pilot and fan-out

- **Pilot #1 (2026-10-21):** orbity CRM (`products/orbity/frontend/src/hooks/useCrm.ts`).
  - Note add: optimistic + commit.
  - Lead delete: optimistic removal from the funil.
  - Lead update and move: commit into the funil + the lead detail; the move is also optimistic.
  - Lead create: commit into the first stage.
  - Regression tests in `hooks/__tests__/useCrm.test.ts` assert what is in the cache while the request is still in flight. They fail on the old hooks.
- **Fan-out (owner, 2026-10-21: "fan out to all products … structural, not local").** Pilots-first cadence (`KB § PATTERNS/architect/project-execution.md`): orbity (pilot 1) → seed organs + `createCrudHooks` (reach every consumer, incl. inactive products, through the seed) → active products in parallel slices (agents, igig, academia-de-reciclagem, core, commerce, social-wiring). Inactive products (`deploy/fleet/active-scope.txt`) are asleep and are NOT migrated by hand; the ratchet keeps them from growing and they inherit every seed-level fix. Parallel slices never hand-merge the baseline — on conflict, take either side and run the lower flag.

## Related

`server-state-family-index.md` (the family) · `lying-loading-state.md` (render rules for refetch vs first load) · `frontend.md` § Job-progress polling (`jobPolling` + `handOffToPolling`) · `inbox-chat-surface.md` (a realtime stream patching the cache: the same "write what you know" idea for pushed data) · `product-internal-wiring.md`.
