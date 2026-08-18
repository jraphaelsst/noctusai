# PostgREST row cap — the mock, not the seven fixes, was the bug

> Formalized 2026-08-17 from a single session that shipped SEVEN instances of
> the same bug class to production (2026-08-13/14): `portal_roi_service`,
> `clientes_service` (x2), and the `imoveis_service.filter_options` /
> negociações-repoint / portal-roi-vendas siblings it names. Self-contained.

## The class

**PostgREST silently caps every unbounded select at a fixed row count — the
Supabase default is 1 000. No error, no warning. `response.data` just has
fewer rows than the table, and the request still answers `200`.**

```python
# Looks correct. Returns AT MOST 1 000 rows, always, silently.
rows = db.table("leads").select("*").eq("org_id", str(org_id)).execute().data
```

Real instances that shipped:

- `portal_roi_service._count_leads_by_origem` — `/portal-roi/resumo` reported
  **1 000 leads** when the true count was **13 255**. A plausible-looking
  number is exactly why it survived review.
- `clientes_service._repoint_negociacoes` — a production backfill silently
  skipped **365 of 1 365** rows and reported `negociacoes_orphaned: []`, i.e.
  "clean."
- `clientes_service.list_review_groups` — an unpaginated select over
  `identidade_incerta` clientes dropped 177 of 1 177 rows from the review
  queue.

## The second, related failure — `.in_()` and the URL

PostgREST serializes `.in_(col, values)` **into the URL query string**, not
the request body. A collection large enough is an over-long request line, and
the server answers a bare `400` with no hint about length:

```
postgrest.exceptions.APIError: {'message': 'JSON could not be generated',
                                'code': 400, 'details': "b'Bad Request'"}
```

This is what actually took `/clientes/revisao` down in production
(2026-08-14): `list_review_groups` fed `.in_("cliente_id", ids)` a ~1 000-UUID
list — a ~40 KB request line, comfortably over the ~8 KB request-line limit
most servers/proxies enforce.

## The root enabler — why all seven had passing tests

`MockSupabaseClient.range()` used to be a **no-op with no row ceiling**.
Every one of the seven call sites had a green unit test, because the mock
returned whatever the fixture held — all of it, regardless of what the code
under test asked for. The row cap, the ONE behavior that mattered, was
**untestable by construction**. Fixing the seven call sites without fixing
the mock guarantees an eighth.

The general lesson (same shape as `§ postgrest-schema-targeting.md`'s
fixture-vs-real false-green): **when the mock is more permissive than
production on the exact axis the bug lives on, the test asserts nothing about
that axis.**

## The fix — three layers, same as every gate in this codebase

| Layer | Mechanism | Where |
|---|---|---|
| The mock, made honest | `MockSelectBuilder` models PostgREST's real window/cap semantics + `.in_()` raises the real `postgrest.exceptions.APIError` shape over budget | `seed/lib/backend/noctusai_lib/testing/mocks.py` |
| Call-site fix | `_paginate` / `_select_all` / `_select_all_where` / `_paginate_query` helpers + `_batched` | `portal_roi_service.py`, `clientes_service.py` (reference implementations) |
| Static backstop | Keeper `check_postgrest_unbounded_query` (heuristic, observe-first) | `mcp/noctusai/tools/noctus/dev/compliance.py` |

### Layer 1 — the mock

`MockSelectBuilder` now tracks `.range(start, end)` / `.limit(n)` /
`.offset(n)` and applies them the way the real `postgrest-py` SDK does
(`.range()` == `offset=start, limit=end-start+1`), THEN applies
`_POSTGREST_MAX_ROWS = 1000` as a hard ceiling regardless of what was
requested — exactly like a real Supabase deployment's `db-max-rows`. An
unbounded select is just the `limit=None` case of the same rule, starting at
offset 0. `.single()` / `.maybe_single()` bypass the window (PostgREST
returns 0/1 rows for those either way).

`.in_(col, value)` computes the approximate query-string bytes the value
would add (`sum(len(str(v)) + 1 for v in value)`) and raises the real
`postgrest.exceptions.APIError({"message": "JSON could not be generated",
"code": "400", "details": "b'Bad Request'"})` once that exceeds
`_IN_FILTER_URL_BUDGET_BYTES = 8000` — the same class production hit, not an
invented mock-only error. `postgrest` is already a transitive dependency
(via `supabase`), so raising the real SDK's exception type means the
existing `postgrest_exception_handler` (`noctusai_lib.primitives.exceptions`)
handles it identically to a real deployment.

🔴 **Do NOT weaken this.** No bypass flag defaulting to the old behavior, no
monkeypatching `_POSTGREST_MAX_ROWS`/`_IN_FILTER_URL_BUDGET_BYTES` in a
product's tests (`§ PATTERNS/compliance/testing.md`'s "no workarounds"
applies here specifically because this constant's whole job is to be the one
thing tests cannot route around). If a fixture legitimately needs >1 000
rows, either paginate the test's own read the same way production would, or
seed the fixture at/under the cap and assert the cap's edge explicitly.

### Layer 2 — the canonical pager, not a recipe to copy

**Do not hand-roll the loop. Compose
`noctusai_lib.integrations.persistence.iter_paged_rows`.**

```python
from noctusai_lib.integrations.persistence import iter_paged_rows

def fetch_page(start, end):                      # INCLUSIVE, PostgREST's own convention
    return (client.table("olx_leads").select("*").eq("org_id", str(org_id))
            .order("id").range(start, end).execute().data)

for row in iter_paged_rows(fetch_page, page_size=500, label=f"olx backfill {org_id}"):
    ...

_IN_FILTER_BATCH = 200  # ~200 UUIDs ≈ 7.6 KB, under the ~8 KB request-line budget

def _batched(items, size):
    for i in range(0, len(items), size):
        yield items[i : i + size]
```

The caller keeps query construction (filters differ at every call site) and
**must** `.order(id_key)` — without a deterministic sort PostgREST may return
overlapping or missing rows across ranges, which no guard can repair.

Every `.select(...).execute()` whose result set is not **provably** bounded
below 1 000 goes through the pager. Every `.in_(col, ids)` whose `ids` is not a
small, statically-bounded collection goes through `_batched` first, with each
batch itself paginated (a batch can still exceed 1 000 matching rows on the
OTHER side of the filter).

#### Why a helper and not the four-line recipe (added 2026-08-17)

The recipe used to be inlined here, and four services copied it. Two things
made that untenable within days, both surfaced by the Grupo OLX backfill —
which **hung on its first test run**:

**The loop has a second failure mode the recipe does not address.** `while
True: … range(offset, offset + n - 1)` terminates *only if the backend honours
`range()`*. One that ignores it returns the same page forever. That is not
hypothetical — it is exactly what `MockSupabaseClient.range()` did before
Layer 1 landed, and a client or proxy that dropped the `Range` header would do
it in production, on the path that touches the most rows, with no test
watching. Fixing the truncation without noticing the hang is the real trap:
the two `query.py` pagers carried a `_MAX_PAGES` ceiling and were fine, while
the backfills written later from the same shape were not.

**Four copies is four places to fix it.** At N=5 (`portal_roi_service`,
`clientes_service`, the `leads` query pager, the Meta backfill, the OLX
backfill) the recurrence rule applies: the loop becomes one seed function.

What `iter_paged_rows` guarantees beyond the recipe:

| Property | Behaviour |
|---|---|
| Termination | Dedupes on `id_key` and advances on unseen rows, so it never depends on the backend cooperating |
| Non-advancing pager, **over-long** page | Real PostgREST never over-delivers ⇒ the range was disregarded and page 1 already carried everything: warn, stop, nothing lost |
| Non-advancing pager, **full repeated** page | Equally consistent with "this is everything" and "this is a capped prefix" — indistinguishable, so it **raises** rather than answer a guess |
| Page ceiling | `page_size * max_pages` (500 000 rows default) raises; callers pass `overflow_error=` to keep their own public exception name (social-wiring's `LeadsResultTooLargeError` subclasses `PagerOverflowError`) |
| Missing `id_key` | Raises. Degrading the guard to a no-op when the column was not selected would bring the hang straight back |

That last one has a call-site consequence worth copying: `iter_leads_rows`
forces `id` into the projection, because the columns its callers ask for
(`origem_raw`, `corretor_raw`, `source_sheet`) are non-unique and deduping on
one of those would collapse rows they are counting.

**Migrated:** `modules/leads/services/query.py` (`fetch_filtered`,
`iter_leads_rows`), `modules/leads/services/meta_ingest_service.py`,
`modules/portal_leads/services/olx_ingest_service.py`.
**Not yet migrated** — still correct against real PostgREST, but each carries
its own loop: `app/services/portal_roi_service.py` (`_paginate`,
`_select_all`), `app/services/clientes_service.py` (`_select_all`,
`_select_all_where`, `_paginate_query`), `app/services/imoveis_service.py`,
`app/modules/email_marketing/services/contact_service.py`. Worth a sweep;
`_batched` stays where it is, it solves the other half.

### Layer 3 — the keeper

`check_postgrest_unbounded_query` (AST-based, `libcst`-adjacent use of the
stdlib `ast` module — never regex, `§ PATTERNS/common/ast.md`) scans
`seed/**` + `products/*/backend/**` for two shapes, **at two DIFFERENT
severities**:

1. A `.select(...)` chain reaching `.execute()` with none of `.range(`,
   `.single(`, `.maybe_single(`, an in-cap literal `.limit(N ≤ 1000)`, or a
   primary-key `.eq("id", …)` on the chain. **Severity `info`.**
2. An `.in_(col, value)` call where `value` is not a small literal collection
   (`≤ 200` elements) and does not sit inside a `for … in <batch-helper>(...)`
   loop (matched by the iterated call's name containing "batch").
   **Severity `warning`.**

Both shapes accept a `postgrest-unbounded-ok: <why>` rationale comment
(same-line or up to 3 preceding lines) as an escape hatch — the regex
requires an actual explanation after the keyword, not just the keyword
(`§ PATTERNS/backend/postgrest-schema-targeting.md`'s hatch accepts a bare
keyword; this one deliberately does not, because the false-positive rate
here is high enough that a rubber-stampable hatch would get rubber-stamped).

**Severity is split by shape, not uniform — this is the load-bearing design
decision, not a cosmetic one.** A full-tree run on this codebase (2026-08-17)
found **~700 select-shape candidates** and **~90 `.in_()`-shape candidates**.
At one badge, the ~90 that are structurally risky REGARDLESS of table
cardinality (an unbatched `.in_()` on a dynamically-sized collection WILL 400
once it crosses the URL budget, independent of what the column means — the
exact shape that took `/clientes/revisao` down) were indistinguishable from
the ~700 whose risk is entirely a function of a row count pure AST cannot
see:

- Pure AST analysis has no table-cardinality knowledge. It cannot tell "this
  table has 30 rows in every org, ever" (a lookup/catalog table) from "this
  table has 13 255 rows for one real org" (`leads`) — both compile to the
  identical `.select(...).eq("org_id", …).execute()` shape. That ambiguity is
  irreducible for the select-shape without either a hand-maintained
  high-cardinality-table allowlist (the exact drift class `§ PATTERNS/devops/
  product-lockfile-and-slug-drift.md` forbids) or wiring the migration-derived
  schema cache to reason about row-count-bearing constraints — both out of
  scope for the keeper's first cut. So the select-shape stays `info`:
  reported, discoverable when someone audits a specific service, but not
  claiming to be a defect list. `info` is not invented for this keeper —
  `tools/noctus/seed/scan_optimizations.py` already uses it for the same
  register (a real, non-actionable-at-a-glance finding).
- The `.in_()`-shape has no such ambiguity — it is a **structural** property
  of the call, not a guess about the table behind it. It stays `warning`.
- Per `§ PATTERNS/common/methodology-execution-discipline.md`: a keeper that
  puts ~700 low-actionability findings at the SAME badge as ~90 high-signal
  ones is noise the moment it ships, and a noisy keeper gets ignored (or
  `--no-verify`'d, which is worse) — the split is what keeps the `warning`
  tier meaning something.

**Both tiers stay non-blocking** — wired into the CLI
(`--check-postgrest-unbounded-query`) and pre-commit (advisory, staged
backend `.py` only, never blocks), matching `check_lying_loading_state`'s
observe-first cadence for a brand-new heuristic detector. Promote the
`.in_()`-shape (`warning`) to blocking once triage shows its false-positive
rate is low enough; the select-shape (`info`) has no such promotion path
without the table-cardinality knowledge above.

CLI: `python mcp/noctusai/cli.py --check-postgrest-unbounded-query`.

## The general lesson

A mock that is MORE PERMISSIVE than production on the exact axis a bug lives
on makes that axis untestable — not "less tested," literally untestable,
because a passing test proves nothing about it. Before adding a new call-site
fix for a class that already recurred once, ask whether the test
infrastructure itself is the reason it recurred. Here it was: the seventh
fix (`clientes_service.list_review_groups`) named this explicitly in its own
commit message before the mock fix landed.
