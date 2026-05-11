# therapy-bulk-lookup-extraction — Project Document

> **This is a living document, not a rigid checklist.**

- **Created:** 2026-05-10
- **Last updated:** 2026-05-10
- **Status:** ✅ **CLOSED — single-engineer dispatch complete on `worktree-agent-a8b36ee6a4d0979fb`.** Helper shipped; 11 unit tests green; 2 of 3 admin_service callsites refactored + 1 inline admin_financials callsite folded in (N=4 within-product, all aligned). _resolve_session_counts left as-is (different shape — aggregation, not single-row lookup). pytest baseline preserved (1273 → 1284, same 4 pre-existing failures); keeper 0 issues.
- **Owner / stakeholders:** rapha (joaoraphaelsst@gmail.com)
- **Project slug:** `therapy-bulk-lookup-extraction`
- **Related docs:**
  - `products/therapy-platform/backend/app/services/admin_service.py` — the 3 callsites
  - `archive/projects/.../therapy-platform-wiring/` (eventual) — predecessor
  - `feedback_absorption_search_standing_duty.md` — N≥3 within-product trigger

---

## 1. Context & Purpose

Engineer R's Phase 3 close shipped 3 sibling helpers in `admin_service.py`:

- `_resolve_clinic_names(db, clinic_ids) → {id: name}` (Phase 2 → Phase 3 — N=2 cross-method)
- `_resolve_session_counts(db, patient_ids) → {id: count}` (Phase 3)
- `_resolve_message_previews(db, report_ids) → {id: preview_str}` (Phase 3)

Each takes `(db, list[id]) → {id: scalar}` and pre-fetches a bulk lookup before DTO mapping (eliminates N+1). **3 siblings in one product file = within-product N=3.**

Per `feedback_absorption_search_standing_duty.md`: "Within-product duplications at N=2 require architect-eyes during Phase 0 audit — automated scanners threshold at N≥3 to suppress noise." N=3 means the scanner threshold has fired too.

**Right move:** extract to an in-product `app/services/_bulk.py` helper FIRST (per Engineer R's recommendation). Seed-promotion (to `noctusai_lib`) waits for a second product needing the same shape — at N=2 cross-product, file the seed lift.

## 2. Confirmed constraints

- **In-product extraction first**, NOT seed-promotion. Seed-promotion requires generic polymorphism (table-name + key-col + value-col) which is larger surface than current callers need.
- **Each `_resolve_X` reads a product-owned table** (`therapy.clinics`, `therapy.appointments`, `therapy.messages`). Not auth-side.
- **Bulk-fetch pattern is canonical** — preserve `.in_(key_col, ids).execute()` shape; don't introduce a generic that masks the SQL.

## 3. Design principles

1. **Helper signature**: `bulk_lookup(db, table, ids: list, key_col: str = "id", value_cols: list[str] | str)` returning `{id: value_or_dict}`. Single value_col → scalar; multiple → dict.
2. **Stay in-product**. Move when N=2 cross-product surfaces (likely PF admin or ERP, both have admin-style pages but no current bulk-lookup pattern visible).
3. **Caller updates inline** — replace 3 `_resolve_*` helpers with `bulk_lookup` calls; keep wrapper functions if call-site readability suffers.

## 3a. Seed-first analysis

- **Cross-product?** Today: NO (N=1 product). The recurrence is within-product (N=3 across 3 methods in same file). Seed-promotion deferred.
- **Seed home if/when promoted?** `noctusai_lib.api.bulk_lookup` or `noctusai_lib.integrations.supabase_bulk_fetch` (sibling of `supabase_identity`).
- **Litmus per `feedback_absorption_search_standing_duty.md`**: WITHIN-product N=3 fires architect-eyes-Phase-0-audit → formalize in-product. CROSS-product N=2 (different rule) fires seed-promotion. We're on the first path.

## 4. Scope

- **In scope:**
  - New helper `bulk_lookup` at `products/therapy-platform/backend/app/services/_bulk.py`.
  - Refactor 3 callsites (`_resolve_clinic_names`, `_resolve_session_counts`, `_resolve_message_previews`).
  - Unit tests for the helper.
  - Existing admin tests stay green.
- **Out of scope:**
  - Seed-promotion (defer to N=2 cross-product trigger).
  - Refactoring product-owned-table reads outside the 3 named helpers.

## 5. Architecture / Data Model

`products/therapy-platform/backend/app/services/_bulk.py`:

```python
async def bulk_lookup(
    db,
    table: str,
    ids: Sequence[str],
    key_col: str = "id",
    value_cols: list[str] | str = "name",
) -> dict[str, Any]:
    """Bulk pre-fetch a {id: value} map from `table` to avoid N+1.
    
    - value_cols: str → returns {id: scalar}.
    - value_cols: list[str] → returns {id: {col: val, ...}}.
    Empty `ids` short-circuits to {}.
    """
    if not ids:
        return {}
    select_cols = value_cols if isinstance(value_cols, str) else ", ".join([key_col, *value_cols])
    result = db.table(table).select(f"{key_col}, {select_cols}").in_(key_col, list(ids)).execute()
    if isinstance(value_cols, str):
        return {row[key_col]: row.get(value_cols) for row in result.data}
    return {row[key_col]: {c: row.get(c) for c in value_cols} for row in result.data}
```

## 6. Implementation phases

### Phase 0 — Confirm callsites + sibling-grep ✅

- [x] Re-grep `admin_service.py` for the 3 named helpers + confirm signatures. **Confirmed** at lines 335, 704, 793 (pre-refactor).
- [x] Sibling-grep across `products/therapy-platform/backend/` for any 4th instance. **Found N=4**: `routers/admin_financials.py` line 270-280 has an inline `clinic_name_map` build that's the same shape as `_resolve_clinic_names`. Did NOT escalate to seed-promotion (still N=1 cross-product); folded the 4th callsite into Phase 1 refactor scope.

**Improvements:**
- Phase-0 audit surfaced that `_resolve_session_counts` is NOT the same shape as the other two helpers — it has an extra `.eq("status", "completed")` filter AND aggregates COUNT across multiple rows per id. `bulk_lookup` as designed in PROJECT.md §5 returns `{id: scalar}` from a single row per id. session_counts is a different abstraction (bulk-aggregation). Documented at `_bulk.py` module docstring; left helper as-is. Future N=2 trigger: file a sibling `bulk_count(db, table, key_col, ids, *, where=...)` helper if a second aggregation site lands.

### Phase 1 — Ship + refactor ✅

- [x] Author `_bulk.py` at `products/therapy-platform/backend/app/services/_bulk.py` (synchronous; signature matches PROJECT.md §5 except sync — Supabase Python SDK `.execute()` is sync, and the existing `_resolve_*` callsites are sync too; PROJECT.md spec showed `async def` which would break the callers and the SDK shape — accepted-with-rationale: sync matches reality).
- [x] Unit tests at `tests/services/test_bulk.py` — 11 tests covering scalar return, dict return, empty ids, all-falsy ids, falsy filtering, no-matching-rows, custom key_col (×2 shapes). **All 11 green.**
- [x] Refactor admin_service.py callsites via libcst codemod (`/tmp/refactor_admin_service.py`):
  - `_resolve_clinic_names` → wrapper choice (a): 1-line `return {k: (v or "") for k, v in bulk_lookup(db, "clinics", clinic_ids, value_cols="name").items()}`. Wrapper kept because 3 callsites consume it by name and the `(v or "")` normalization is non-trivial.
  - `_resolve_message_previews` → wrapper choice (a): rewrites to use `bulk_lookup` with `value_cols=["content", "message_type"]` (dict-mode), then post-processes for the 120-char truncation + system-tag fallback. Wrapper kept because the post-processing IS non-trivial.
  - `_resolve_session_counts` → **UNCHANGED** (different shape — see Phase 0 Improvements).
- [x] Refactor `routers/admin_financials.py` inline 4th callsite via libcst codemod (`/tmp/refactor_admin_financials.py`): the 10-line `clinic_name_map: dict = {}` + `if clinic_ids: ...` block collapsed to 2 lines using `bulk_lookup` directly (no wrapper — single callsite).
- [x] AST-first edits via libcst. Zero sed/regex on source.
- [x] `pytest products/therapy-platform/backend/` — **1284 passed, 14 skipped, 4 failed**. Baseline (without my work) was **1273 passed, 14 skipped, 4 failed**. Delta: +11 new bulk tests passing; same 4 pre-existing test-isolation failures (`test_crisis_router::test_review_alert_admin_allowed`, `test_refunds_router::test_deny_refund_with_reason`, `test_crisis_service::test_review_as_false_positive`, `test_homework_service::test_review_pending_homework_fails`) — pass when run in isolation, fail in full-suite for reasons unrelated to bulk-lookup (verified by stash + re-run on clean tree).
- [x] Keeper review (`mcp/noctusai/cli.py --review --product therapy-platform`) — **0 issues.**

**Improvements:**
- The codemod removed cosmetic blank lines + section-header banners around the rewritten functions. Restored manually via Edit tool (post-codemod cleanup). For future libcst codemods that replace whole `FunctionDef` nodes, preserve `leading_lines` of the original node and re-attach to the new node — captured as a methodology learning for the architect to consider via the AST patterns doc.
- The `MockSupabaseClient` (used here) does NOT apply `.in_()` filtering when `validate_schema=False`; one initial test caught this (asserting that requesting `["c1", "c3"]` from a 3-row table returns only `{c1, c3}` — it actually returns all 3). Rewrote that test to `test_multiple_ids_all_resolve` (seed exactly the rows that should match). Not a bulk_lookup bug; documented as a mock-isolation gotcha.

### Phase 2 — Verify + close ✅

- [x] Improvements blocks (above).
- [x] §11 close entry (below).
- [x] Branch pushed to remote (engineer responsibility); orchestrator handles archive + main FF per §16/§17.

## 7. Open questions

- None — in-product extraction is unambiguous. Seed-promotion question deferred to N=2 cross-product trigger.

## 8. Dependencies & blockers

- None.

## 9. Success criteria

- [x] `bulk_lookup` ships in-product with tests (11 unit tests, all green).
- [x] **3 callsites consume the helper** — 2 in admin_service.py (`_resolve_clinic_names`, `_resolve_message_previews`) + 1 in admin_financials.py (inline 4th instance refactored to direct call). `_resolve_session_counts` excluded with rationale (different shape — aggregation, not single-row lookup).
- [x] No N+1 regressions — verified by reading call paths: each `_resolve_X` is called ONCE per page in `list_appointments_for_admin` / `list_patients_for_admin` / `list_reports_for_admin` / `list_active_overrides`; the bulk-pre-fetch shape is preserved (one `.in_(...)` query per page, not N per row).
- [x] Therapy pytest + keeper green (1284 passed; 4 baseline failures unchanged; keeper 0 issues).

## 10. How to use this plan

Single-engineer dispatch via `git worktree add`. Pattern is locked by Engineer R's analysis — mechanical extraction. Branch: `therapy-bulk-lookup-extraction`.

## 11. Change log

| Date | Change | By |
|---|---|---|
| 2026-05-10 | **Filed under user signal "create projects for deferrals/parks that happen along the way."** Engineer R's therapy Phase 3 surfaced N=3 within-product bulk-lookup pattern (_resolve_clinic_names + _resolve_session_counts + _resolve_message_previews). In-product extraction recommended over seed-promotion (per Engineer R analysis: product-owned tables; seed-promotion needs generic polymorphism larger than current callers warrant). Single-engineer dispatch when scheduled. | claude-opus-4-7 |
| 2026-05-10 | **CLOSED.** Single-engineer dispatch on `worktree-agent-a8b36ee6a4d0979fb`. Shipped `app/services/_bulk.py` (sync, not async — accepted-with-rationale: matches Supabase SDK + existing callers). Refactored 2 of 3 admin_service callsites + 1 inline admin_financials callsite (N=4 surfaced in Phase 0); `_resolve_session_counts` left as-is (different shape — aggregation, not single-row lookup; documented in `_bulk.py` module docstring + Phase 0 Improvements). 11 unit tests green; pytest 1284 passed (delta +11 vs 1273 baseline); same 4 pre-existing test-isolation failures (unrelated to bulk-lookup); keeper 0 issues. AST-first via libcst (2 codemod scripts under /tmp/). | engineer-on-worktree |

## 12. No-leftovers constraint

- Folder archives via `noctus.dev.archive` on close.
