# therapy-bulk-lookup-extraction — Project Document

> **This is a living document, not a rigid checklist.**

- **Created:** 2026-05-10
- **Last updated:** 2026-05-10
- **Status:** 📋 **READY FOR EXECUTION (dispatchable).** Filed under user signal "create projects for deferrals/parks that happen along the way." Engineer R's `therapy-platform-wiring` Phase 3 close (commit `f5ca4c2`) surfaced N=3 within-product bulk-lookup pattern. Per `feedback_absorption_search_standing_duty.md` (N≥3 within one product = architect-eyes-during-Phase-0-audit / MUST-formalize).
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

### Phase 0 — Confirm callsites + sibling-grep

- [ ] Re-grep `admin_service.py` for the 3 named helpers + confirm signatures.
- [ ] Sibling-grep across `products/therapy-platform/backend/` for any 4th instance of the same shape (recurrence rule fires harder if N=4+ — escalate to seed-promotion immediately).

### Phase 1 — Ship + refactor

- [ ] Author `_bulk.py` + unit tests at `tests/services/test_bulk.py`.
- [ ] Refactor 3 callsites — each `_resolve_X` either:
  - (a) becomes a 1-line wrapper `return await bulk_lookup(db, ...)`, OR
  - (b) is inlined at the consumer (delete the wrapper).
  Pick (a) if call-site readability suffers from inlining; pick (b) if the wrapper carries no extra logic.
- [ ] AST-first edits (libcst). NEVER sed/regex.
- [ ] `pytest products/therapy-platform/backend/` — green; baseline failures unchanged.
- [ ] Keeper 0 issues.

### Phase 2 — Close

- [ ] Improvements block + §11 close entry.
- [ ] Archive.

## 7. Open questions

- None — in-product extraction is unambiguous. Seed-promotion question deferred to N=2 cross-product trigger.

## 8. Dependencies & blockers

- None.

## 9. Success criteria

- [ ] `bulk_lookup` ships in-product with tests.
- [ ] 3 callsites consume the helper.
- [ ] No N+1 regressions (the helper preserves the bulk-pre-fetch pattern).
- [ ] Therapy pytest + keeper green.

## 10. How to use this plan

Single-engineer dispatch via `git worktree add`. Pattern is locked by Engineer R's analysis — mechanical extraction. Branch: `therapy-bulk-lookup-extraction`.

## 11. Change log

| Date | Change | By |
|---|---|---|
| 2026-05-10 | **Filed under user signal "create projects for deferrals/parks that happen along the way."** Engineer R's therapy Phase 3 surfaced N=3 within-product bulk-lookup pattern (_resolve_clinic_names + _resolve_session_counts + _resolve_message_previews). In-product extraction recommended over seed-promotion (per Engineer R analysis: product-owned tables; seed-promotion needs generic polymorphism larger than current callers warrant). Single-engineer dispatch when scheduled. | claude-opus-4-7 |

## 12. No-leftovers constraint

- Folder archives via `noctus.dev.archive` on close.
