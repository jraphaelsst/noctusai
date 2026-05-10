# mock-supabase-write-propagation — Orchestration Findings

> Transcribed by the orchestrator post-merge per `KB § PATTERNS/branching-and-merging.md § 17.6.1` (return-as-text protocol). Engineer A returned the 5-category content as text in their report after the harness blocked their `findings.md` Write call.

## Errors encountered

None during execution.

## Mistakes / slips

- Engineer authored a test that referenced a non-existent `response.status_code` attribute on `MockSupabaseResponse` (only `data`, `error`, `count` exist). 22/23 tests passed on first run; this one slipped through. Fixed in the same Phase 1-3 commit. **Lesson:** when designing assertion shape, read the response class first instead of pattern-matching from FastAPI's response shape.
- Authorized `findings.md` write was blocked by harness despite the explicit Write-authorization paragraph in the dispatch brief. The brief authorization paragraph isn't being honored by the harness — the harness has a hard rule that supersedes brief-level authorization. Engineer-side workaround: returned the curated findings content in the report, which the orchestrator then transcribed here. **This finding contributed to the §17.6.1 N=5 recurrence formalize.**

## Lessons learned (durable rules)

- **The mock's filter-blindness was masking real test fixture bugs.** Pre-fix, `update(...).eq("status", "pendente").execute()` returned every seeded row regardless of status — so tests asserting `len(result.data) == N` could pass with fixtures that didn't actually match the production filter. 4 ERP tests fell into this trap. Post-fix correctly returns 0 when fixtures don't match. **The fix is a detector for fixture-vs-production mismatches, beyond just enabling write→read round-trips.**
- **Auto-id counter design**: the existing `len(inserted_payloads)` for auto-id generation breaks for list payloads — if you `insert([row1, row2])` then `insert([row3])`, the per-row id assignment was based on `len(inserted_payloads)` after each list-extend, so successive list inserts would re-use ids `mock-tbl-2`, `mock-tbl-2`, `mock-tbl-3`... Switched to a dedicated `_auto_id_seq` counter that increments per row. This is a quiet correctness improvement that landed for free with the propagation work.
- **Predicate accumulation architecture**: putting `_predicates` on `_FilterMixin` (consumed by both `MockSelectBuilder` and `MockFilterBuilder`) means SELECT could also evaluate predicates in the future. Out of scope for this project but a clean extension point. Currently SELECT ignores predicates and returns all `_data`; that matches existing behavior so no test breaks.

## Interesting findings (surprises, discoveries)

- `MockRequestBuilder` already records `inserted_payloads` AND `updated_payloads`, but the SELECT seed (`self._data`) is independent. The two halves of the contract were built piecemeal — payload-tracking landed before propagation. Consumer-side tests filled the gap by reading `inserted_payloads` directly, which works for unit-level write assertions but masks SELECT-after-INSERT bugs in the router.
- `set_sequential_responses(...)` already overrode `execute()` output. The propagation fix needed to respect this so tests simulating insert-failure (`MockSupabaseResponse(data=[])`) don't get implicit "but the data still appears in the next SELECT" surprises. Codified as: response-queue presence suppresses propagation.
- Filter validation (`_check_col`) already routed through `_FilterMixin` but the filter **values** were discarded — only column names flowed through. UPDATE/DELETE propagation needs the values too. Cleanest extension reuses the existing `_check_col` indirection (added `_record(op, col, value)` alongside).

## Knowledge pieces (durable patterns)

- Real PostgREST: empty filter list on UPDATE/DELETE = match-all. The mock now mirrors this exactly.
- `MockSupabaseResponse` has only `.data`, `.error`, `.count` — no `status_code`.
- `MockSupabaseClient.set_table_data(name, data)` re-creates the per-table builder via `_builder_for(...)`, so it wipes any propagated mutations on that table. That's the documented "explicit reset" behavior; no change needed.
- The list-update form (`update([dict, dict])`) is rare. Engineer merged the dicts (last-key-wins) for propagation purposes and continued to capture the raw list in `updated_payloads` for tests that read it directly.
- **Recommended NEW follow-up**: `mock-supabase-test-fixture-cleanup` — N=23 fixture workarounds to retire (4 ERP + 19 AdConnect tests using `initial_state={...}` workarounds). With propagation working, these tests can drop the workaround AND the 4 ERP tests reveal real fixture bugs (seeding post-write state).
