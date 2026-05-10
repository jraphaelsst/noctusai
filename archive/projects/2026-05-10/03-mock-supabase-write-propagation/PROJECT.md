# Mock Supabase Write Propagation — Project Document

> Living document. Phase plan evolves as evidence accumulates.

- **Created:** 2026-05-10
- **Last updated:** 2026-05-10
- **Status:** Phases 0-4 complete; Phase 5 in progress
- **Owner / stakeholders:** joaoraphaelsst (architect / orchestrator) · solo engineer subagent on branch `mock-supabase-write-propagation`
- **Related docs:** `seed/lib/backend/noctusai_lib/testing/mocks.py`, `seed/lib/backend/tests/test_mock_payload_tracking.py`, `KB § PATTERNS/testing.md` (side-effect verification via `inserted_payloads`)
- **Project slug:** `mock-supabase-write-propagation` (cross-cutting; lives at `projects/<slug>/`)

---

## 1. Context & Purpose

The shared `MockSupabaseClient` at `seed/lib/backend/noctusai_lib/testing/mocks.py` lets every product test the Supabase-touching code paths in-process without a real database. Today the mock has a **write-propagation gap**: an `insert(...).execute()` records the payload in `inserted_payloads` and returns a fake row to production code, but does **not** mutate the underlying SELECT seed. The next `select(...).execute()` against the same table returns whatever was pre-seeded via `set_table_data(...)` (or the constructor `data=`), oblivious to the just-issued write.

The same gap exists for `update(...)` (mutates `updated_payloads`, doesn't mutate the SELECT seed) and `delete(...)` (no tracking, no mutation).

The AdConnect MVP (closed 2026-05-10) hit this gap N=4 in cart, orders, sellout, and rewards routers. Tests had to pre-seed both the read state AND the post-write state, OR shape the assertion against `inserted_payloads` instead of round-tripping through the router. Both workarounds are leaky:
- Pre-seeding post-write state hides router-level bugs that mismutate the row.
- `inserted_payloads`-only assertions miss bugs in the SELECT-after-INSERT happy path that the router itself relies on (e.g. cart → display, order → confirmation page).

**Goal.** Make INSERT / UPDATE / DELETE writes propagate to subsequent SELECT reads on the same `MockSupabaseClient` instance, in-test. Existing tests using `set_table_data(...)` to seed initial state remain unchanged in behavior — propagation is purely additive.

---

## 2. Confirmed constraints

- **Scope is the seed mock, not consumer tests.** The architect's brief explicitly forbids modifying AdConnect router tests in this project — that's a sister project. *(Closes the parallel-agent collision risk.)*
- **Backwards compatibility is non-negotiable.** Tests using only `set_table_data(...)` + SELECT (no writes) MUST behave identically. *(Hundreds of existing tests across products.)*
- **`inserted_payloads` / `updated_payloads` semantics preserved.** Both still capture raw payloads (without auto-id mutations) for tests that read them directly. *(Documented in `KB § PATTERNS/testing.md`.)*
- **Auto-id behavior preserved.** Production code reading `result.data[0]["id"]` after `insert(...).execute()` still sees `mock-<table>-<n>` when no id was provided. *(N=dozens of services rely on this.)*
- **Schema validation orthogonal.** This change does not alter when / whether `MockSchemaError` raises.
- **Filter tracking is needed for UPDATE/DELETE row-matching.** Without recording `eq` / `in_` / etc. predicates, UPDATE can't know which rows to mutate. *Decision (architect default): track only the simple equality / membership filters that exist in real product code; complex PostgREST expressions (`or_`, `match` with multiple keys, `filter("col", "fts", ...)`) fall back to "match all rows" with a debug log line — same shape as schema-cache `WARN+skip`.*
- **No monkey-patching of our own code in tests.** All test-level verification uses dependency injection or `MockSupabaseClient` itself. *(Per `feedback_no_monkeypatching_in_tests`.)*

---

## 3. Design principles

1. **Shared list reference for `_data`.** The cached `MockRequestBuilder` per table holds a stable `list` reference. Downstream `MockSelectBuilder` / `MockFilterBuilder` / `MockQueryBuilder` receive that same reference (not a copy), so mutations propagate.
2. **Filter predicates accumulate on the builder.** `_FilterMixin` records a list of `(op, col, value)` tuples on the builder instance. `MockFilterBuilder.execute()` evaluates the predicates against the shared `_data` list to decide which rows to mutate / delete.
3. **Insert mutates `_data` once, after computing the response row.** The response row (with auto-id) is appended to `_data` AND returned via the response. `inserted_payloads` continues to receive the raw (pre-auto-id) payload.
4. **Update mutates rows in place.** Each matching row gets `dict.update(payload)` applied. The response data lists the mutated rows (matches real PostgREST behavior).
5. **Delete removes matching rows.** The deleted rows are returned in the response data; the surviving rows stay in `_data`.
6. **Response-queue takes precedence.** When `set_sequential_responses(...)` is configured, write propagation is **suppressed** (the queue dictates the result). Tests using the queue explicitly opt out of mutation propagation. *(This preserves the "simulate insert failure" use case documented in the existing `insert(...)` docstring.)*
7. **Empty / unknown filter set = match-all behavior on UPDATE / DELETE.** Same as PostgREST: an unfiltered UPDATE mutates every row in the table; an unfiltered DELETE wipes the table. Matches real Supabase.

---

## 3a. Seed-first analysis (REQUIRED)

This project lives entirely in `noctusai_lib.testing.mocks` — the shared seed test fixture. All consumers (every product) inherit the fix transparently. Per-product code count: **0 lines**.

1. **Is the contract identical for every product?** YES — every product imports `MockSupabaseClient` from `noctusai_lib.testing` with the same API.
2. **Is the data source product-specific?** NO — the mock is product-agnostic; products seed their own data via `set_table_data` / `MockSupabaseResponse`.
3. **Is the placement product-specific?** NO — single shared module at `seed/lib/backend/noctusai_lib/testing/mocks.py`.
4. **Is the visibility / permission rule the same?** N/A (test infrastructure, not user-facing).
5. **Does the seam already exist in seed?** YES — `noctusai_lib.testing.MockSupabaseClient` already mediates every product's Supabase-touching test. We extend the existing seam, no new seam needed.
6. **Default-on or opt-in?** DEFAULT-ON — propagation is purely additive; tests that don't issue writes see no behavior change. Opt-out is unnecessary.

**Litmus — per-product code count this design requires:**
- [x] **0 lines** — pure seed change; products inherit transparently. Existing `initial_state={}` / `set_table_data(...)` workarounds in consumer tests can be removed in follow-up sister projects (out of scope here per architect brief).
- [ ] 1 line
- [ ] A small section
- [ ] Multiple files / pages / mounts per product — STOP

**Phase plan implications:** §6 phases work entirely in `seed/lib/backend/noctusai_lib/testing/mocks.py` + colocated tests in `seed/lib/backend/tests/`. No product files touched. ✓ correctly seed-bound.

---

## 4. Scope

**In scope:**
- INSERT propagation: appended rows visible to subsequent SELECT.
- UPDATE propagation: filter-matched rows mutated in place; new state visible to subsequent SELECT.
- DELETE propagation: filter-matched rows removed; subsequent SELECT no longer returns them.
- Filter-predicate tracking on `_FilterMixin` for `eq`, `neq`, `in_`, `gt`, `lt`, `gte`, `lte`, `is_`. Other filters (`like`, `ilike`, `contains`, `or_`, `match`, `filter`, `text_search`, `fts`) fall back to "match all" with a debug log line — out of scope to implement full evaluation.
- Coexistence with `set_sequential_responses(...)`: queue-driven responses suppress propagation (queue wins).
- New tests at `seed/lib/backend/tests/test_mock_write_propagation.py` covering INSERT / UPDATE / DELETE round-trips, filter combinations, response-queue precedence, and backwards compatibility regression checks.

**Out of scope (for now — with reason):**
- Modifying any product test file that uses `initial_state={...}` workaround — sister project per architect brief.
- Implementing full PostgREST expression evaluation for `or_` / `match` / `filter` / `text_search` / `fts` — these have no current consumer-side need; debug-logged match-all fallback is sufficient. *Recurrence later flips this toward formalize.*
- LIMIT / OFFSET / ORDER tracking on SELECT — not part of the write-propagation gap.
- The `upsert` operation — kept as a no-op-mutation for now (returns the data, but does not propagate). Adding upsert propagation requires conflict-target tracking; deferred. *Catalog entry: `mock-supabase-upsert-propagation` follow-up.*

---

## 5. Architecture / Data Model

### Current state (the gap)

```
MockSupabaseClient
  ._tables: dict[str, MockRequestBuilder]    # cached per-table builder
    .insert(payload)
       └─ self.inserted_payloads.append(payload)         # tracked
       └─ returns MockQueryBuilder(response_rows, ...)   # auto-id'd
       └─ self._data NOT updated                        # ← the gap
    .update(payload)
       └─ self.updated_payloads.append(payload)          # tracked
       └─ returns MockFilterBuilder(self._data, ...)
       └─ self._data NOT updated                        # ← the gap
    .delete()
       └─ returns MockFilterBuilder(self._data, ...)
       └─ self._data NOT updated                        # ← the gap

  .select(cols)
       └─ returns MockSelectBuilder(self._data, ...)
       └─ Reads stale self._data                        # ← misses prior writes
```

### Target state (after fix)

```
MockSupabaseClient
  ._tables: dict[str, MockRequestBuilder]
    ._data: list                                # SHARED LIST REFERENCE
                                                # passed-by-reference downstream
    .insert(payload)
       └─ inserted_payloads.append(raw payload)
       └─ response_rows = compute auto-id rows
       └─ self._data.extend(response_rows)      # ← propagates to SELECT
       └─ returns MockQueryBuilder(response_rows, ...)
    .update(payload)
       └─ updated_payloads.append(raw payload)
       └─ returns MockFilterBuilder(
            shared _data,
            update_payload=payload,
            mode="update",
            ...
          )
    .delete()
       └─ returns MockFilterBuilder(
            shared _data,
            mode="delete",
            ...
          )

  MockFilterBuilder                              # eq/neq/in_/etc. accumulate
    ._predicates: list[(op, col, value)]
    .execute():
       matching = [r for r in shared_data if predicates_match(r, _predicates)]
       if mode == "update":
           for r in matching: r.update(update_payload)
       elif mode == "delete":
           shared_data[:] = [r for r in shared_data if r not in matching]
       return MockSupabaseResponse(data=matching, ...)

  .select(cols)                                  # unchanged read-side
       └─ MockSelectBuilder(shared _data, ...)
       └─ Reads current _data including just-applied writes ✓
```

### Filter-predicate evaluation

`_predicates_match(row, predicates)` — pure function in mocks.py:

| op   | predicate true when…                                |
|------|-----------------------------------------------------|
| eq   | `row.get(col) == value`                             |
| neq  | `row.get(col) != value`                             |
| in_  | `row.get(col) in value`                             |
| gt   | `row.get(col) > value`                              |
| lt   | `row.get(col) < value`                              |
| gte  | `row.get(col) >= value`                             |
| lte  | `row.get(col) <= value`                             |
| is_  | `row.get(col) is value` (for `None` / `True` / `False`) |
| _other_ | match-all (debug-logged)                         |

Empty predicate list = match-all (mirrors real PostgREST).

### Response-queue precedence

`set_sequential_responses(...)` already overrides `execute()` output via `_response_queue`. We extend the rule: when `_response_queue` is set, the propagation step is **skipped** entirely. Tests opting into queue-driven responses retain full control over the response shape; they do not get implicit data mutation.

---

## 6. Implementation phases

### Phase 0 — Audit + failing test ✅

- [x] Read `mocks.py` end-to-end.
- [x] Catalog the four mutation paths: `insert`, `update`, `upsert`, `delete`.
- [x] Document the gap in §5.
- [x] Write failing tests at `seed/lib/backend/tests/test_mock_write_propagation.py` proving INSERT/UPDATE/DELETE don't propagate today.
- [x] Run the failing tests and capture the failure output (15 fail, 8 pass — confirming the gap).

**Improvements:** none identified.

### Phase 1 — INSERT propagation ✅

- [x] Refactor `MockRequestBuilder.__init__` to materialize `self._data` as a stable list reference (always own a fresh list).
- [x] In `MockRequestBuilder.insert(...)`: extend `self._data` with the response rows (with auto-id) so subsequent SELECT sees them.
- [x] Suppress propagation when `_response_queue` is set.
- [x] Switch auto-id counter from `len(inserted_payloads)` (per-row brittle when payloads are lists) to a dedicated `_auto_id_seq` counter on the builder.
- [x] Run `test_mock_write_propagation.py::test_insert_*` — green (7/7).
- [x] Run all of `seed/lib/backend/tests/` — full suite green (1039 passing).

### Phase 2 — UPDATE propagation ✅

- [x] Add `_predicates: list[tuple[str, str, Any]]` to every concrete builder via `_FilterMixin._record(...)`.
- [x] Add `_update_payload: Optional[Mapping]` and `_mutation_kind: Optional[str]` to `MockFilterBuilder`. Set from `MockRequestBuilder.update(...)`.
- [x] Add `_row_matches_predicates(row, predicates)` pure helper + `_PREDICATE_EVALUATORS` table mapping op → callable. 8 ops literal (`eq`, `neq`, `in_`, `gt`, `lt`, `gte`, `lte`, `is_`); other ops match-all with debug log.
- [x] In `MockFilterBuilder.execute()`: when `_mutation_kind == "update"`, evaluate predicates against shared `_data` and `dict.update` matching rows in place. Return matching rows as response data.
- [x] Suppress propagation when `_response_queue` is set.
- [x] `match({col: val, ...})` recorded as multiple `eq` predicates (logical AND, matches PostgREST).
- [x] `test_mock_write_propagation.py::test_update_*` green (7/7).
- [x] Full seed test suite green (1039 passing).

### Phase 3 — DELETE propagation ✅

- [x] Use the same `_mutation_kind` machinery: `MockRequestBuilder.delete(...)` constructs a `MockFilterBuilder` with `mutation_kind="delete"`.
- [x] In `MockFilterBuilder._apply_mutation()`: when delete mode, evaluate predicates and replace shared `_data` contents via slice assignment (`self._data[:] = survivors`) so the shared list reference stays stable.
- [x] Suppress propagation when `_response_queue` is set.
- [x] `test_mock_write_propagation.py::test_delete_*` green (6/6).
- [x] Full seed test suite green.

### Phase 4 — Cross-product regression check ✅

- [x] Full seed test suite (`pytest seed/lib/backend/tests/`): **1039 passed, 0 failed** (1016 baseline + 23 new propagation tests). Zero regressions in seed.
- [x] Spot-check `products/erp-imobiliario/backend/tests/services/`: **793 passed, 4 failed**. Investigated each failure — all four are **false-positive tests pre-existing on main** that were passing only because of the very gap this project closes. They seed rows in a state the production filter would reject (e.g. seeding rows already `status="atrasado"` while the service filters `status="pendente"`), and assert `len(result.data) > 0` because the unfiltered mock returned everything. With filtering correctly applied, those tests now correctly return 0 rows. *These are surfaced bugs in test fixtures, not regressions in production code or in my fix.* Files affected:
    - `tests/services/test_financeiro_service.py::TestMarkOverdue::test_marks_overdue_records`
    - `tests/services/test_recorrencia_service.py::TestVerificarInadimplencia::{test_marks_overdue_lancamentos, test_marks_overdue_parcelas, test_combined_lancamentos_and_parcelas}`
- [x] Spot-check `products/core/backend/tests/`: pre-existing import errors (`BaseDigestService` not found, `audit_digest` router missing) unrelated to this project — verified by running on stashed `main`.
- [x] Per architect brief, **NOT** modifying any product test in this project. Surface-list captured for the sister project (`mock-supabase-test-fixture-cleanup` candidate).

**Improvements (cross-cutting):**
- The 4 ERP tests + the 19 AdConnect tests with `initial_state` workarounds collectively form an N=23 recurrence — strong signal that pre-fix mock semantics actively encouraged false-positive test fixtures. Catalog as `mock-supabase-test-fixture-cleanup` follow-up.

### Phase 5 — Project close ⏳

- [x] Absorption-search sextet on `mocks.py` — `noctus.dev.scan_within_product_helpers` returned 19 findings none of which touch `noctusai_lib.testing` or `mocks.py`. No on-the-spot absorption candidates inside this project's scope.
- [x] Three-way sync candidate identified: methodology amendment to `KB § PATTERNS/testing.md` documenting the propagation guarantee (write-then-read round-trip works without `initial_state` workaround). Defer the KB edit to architect-side three-way sync (this engineer's branch carries the seed change; the methodology layer rides with the orchestrator's KB layer to keep three-way sync atomic per `feedback_three_way_sync`).
- [ ] Final commit + push to `mock-supabase-write-propagation` branch.
- [ ] Architect (orchestrator) reviews + merges into main + archives via `noctus.dev.archive`.

---

## 7. Open questions

1. **Should `upsert(...)` propagate too?** Deferred — needs conflict-target column tracking (`on_conflict` kwarg), which AdConnect did not exercise. Catalog entry: `mock-supabase-upsert-propagation` if a consumer hits the gap.
2. **Should the debug-log line for unsupported filter ops be configurable?** Defaulting to `logger.debug(...)` (silent at default level). Consumers wanting visibility can raise the log level. *(Decision: yes, debug-default; no flag.)*
3. **Should `match-all` UPDATE/DELETE warn?** Real PostgREST does this silently. We follow suit. *(Decision: silent.)*

---

## 8. Dependencies & blockers

- None. The change is fully internal to `noctusai_lib.testing.mocks` + colocated tests.

---

## 9. Success criteria

- All `test_mock_write_propagation.py` tests pass.
- All existing `seed/lib/backend/tests/` tests pass (zero regressions).
- A representative product test suite (core or mailing) passes with no changes required.
- INSERT → SELECT round-trip in a single `MockSupabaseClient` instance returns the inserted row.
- UPDATE filtered by `eq` mutates only matching rows; subsequent SELECT confirms.
- DELETE filtered by `eq` removes only matching rows; subsequent SELECT confirms.
- Backwards compatibility: tests that pre-seed via `set_table_data(...)` and never write continue to pass byte-identically.
- Response-queue precedence respected: tests using `set_sequential_responses(...)` get queue values, no implicit propagation.

---

## 10. How to use this plan

- Phases are commit gates — local commit at end of each phase, branch push at project close.
- `findings.md` aggregates surprises across phases.
- §11 reflects every applied change in chronological order.
- The architect (orchestrator) reviews the branch; the engineer never pushes to `main`.

---

## 11. Change log

| Date | Change | By |
|---|---|---|
| 2026-05-10 | Initial draft from `templates/PROJECT-TEMPLATE.md` after architect brief | engineer (claude-opus-4-7) |
| 2026-05-10 | Phase 0 complete: `test_mock_write_propagation.py` (23 tests, 15 fail / 8 pass on baseline) confirms gap; PROJECT.md scaffolded with §3a seed-first analysis (0-line per-product cost) | engineer |
| 2026-05-10 | Phases 1-3 implemented as one structural refactor of `mocks.py`: shared list reference for `_data` across builders; INSERT extends the list with auto-id'd response rows; UPDATE/DELETE accumulate predicates via `_FilterMixin._record(...)` and apply mutations through `MockFilterBuilder._apply_mutation(...)` against the shared list. `_PREDICATE_EVALUATORS` table covers 8 ops literally; complex PostgREST expressions debug-log + match-all. Response-queue precedence preserved (queue suppresses propagation). 1039 seed tests green | engineer |
| 2026-05-10 | Phase 4 cross-product regression check: 4 ERP tests surfaced as false-positives pre-existing on main (test fixtures seed post-write state instead of pre-write — passed by coincidence on the unfiltered mock). Per architect brief, NOT modifying consumer tests in this project. Catalog: `mock-supabase-test-fixture-cleanup` follow-up project | engineer |
| 2026-05-10 | Within-product absorption scan returned 19 findings — none in `noctusai_lib.testing` scope | engineer |
