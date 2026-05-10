# delete-precheck-seed-lift — Project Document

> **This is a living document, not a rigid checklist.**

- **Created:** 2026-05-10
- **Last updated:** 2026-05-10
- **Status:** 📋 **READY FOR EXECUTION (deferred dispatch — Engineer D file-overlap risk).** Filed under user signal *"create projects for deferrals/parks that happen along the way."* Engineer B's PF Phase 2 close (commit `dbed0c6`) surfaced N=3 cross-product recurrence; per DRY recurrence rule N=3 MUST-FORMALIZE. Dispatchable as soon as `erp-org-scoping-completion` Phase 2 closes (Engineer D touches same ERP services dir).
- **Owner / stakeholders:** rapha (joaoraphaelsst@gmail.com)
- **Project slug:** `delete-precheck-seed-lift` (root `projects/` — cross-product / seed-lib formalize)
- **Related docs:**
  - `KB § PATTERNS/project-execution.md § 2.7 recurrence rule` — the rule that fires here
  - `feedback_recurrence_rule.md` — N=3 must-formalize memory rule
  - `seed/lib/backend/noctusai_lib/api/auth.py` — sibling pattern (HTTP-layer raise-on-violation helper home)
  - `archive/projects/2026-05-10/personal-finance-wiring/PROJECT.md` (when archived) — surfacing context

---

## 1. Context & Purpose

Engineer B's `personal-finance-wiring` Phase 2 (closed 2026-05-10, commit `dbed0c6`) fixed three DELETE endpoints that used `result.data` as a 404-proxy after `.delete().execute()`. While fixing PF-9 (`routers/recorrentes.py:106-108`), the engineer identified two more occurrences of the **same anti-pattern shape** in ERP:

- `products/erp-imobiliario/backend/app/services/meta_periodos_service.py:82-84` — `deletar_periodo`
- `products/erp-imobiliario/backend/app/services/regras_pontuacao_service.py:121-123` — `deletar_regra`

ERP variants raise `LookupError` instead of `HTTPException` but the false-404-on-RLS-collapse risk shape is identical. **N=3 cross-product recurrence triggers MUST-FORMALIZE per `KB § PATTERNS/project-execution.md § 2.7`.**

The shape:
```python
# ANTI-PATTERN — `result.data` from .delete() is unreliable for 404 detection
result = self.db.table("X").delete().eq("id", x_id).execute()
if not result.data:
    raise NotFound("X")  # or LookupError, or HTTPException(404)
```

The fix shape (already canonical in 4 PF services after Phase 2):
```python
# Explicit pre-check → 404 → delete
check = self.db.table("X").select("id").eq("id", x_id).eq("org_id", self.org_id).execute()
if not check.data:
    raise HTTPException(status_code=404, detail="X nao encontrado")
self.db.table("X").delete().eq("id", x_id).eq("org_id", self.org_id).execute()
```

## 2. Confirmed constraints

- **N=3 is the formalize-or-refactor trigger.** Silently shipping a 4th instance is forbidden.
- **ERP convention divergence**: ERP variants raise `LookupError`, not `HTTPException`. The seed-lib helper must support both raise shapes via injection.
- **RLS-via-parent variant**: `orcamento_itens`-style tables don't need `.eq("org_id", ...)` — the helper must accept variadic predicates.
- **No Supabase mock change required** — PF Phase 2 confirmed `MockSelectBuilder.execute()` returns seeded data; helper is a pure shape.

## 3. Design principles

1. **Helper lives in seed-lib, callsites adopt it** — formalize the pattern, then refactor the 3 known sites.
2. **Raise-shape injectable** — caller passes the exception type + message; helper doesn't hardcode `HTTPException(404)`.
3. **Variadic predicates** — `delete_with_existence_check(db, table, *predicates, not_found_exc)` — caller chains `.eq(...)` predicates via a list.
4. **Test the helper with both raise shapes** — ensures convention divergence doesn't drift.

## 3a. Seed-first analysis (REQUIRED)

- **Is this a cross-product concern?** YES — N=3 confirmed across PF + ERP×2.
- **Does the seed already ship a similar shape?** PARTIAL — `noctusai_lib.api.auth.make_require_role` is the canonical sibling (HTTP-layer raise-on-violation). The new helper belongs alongside it (or in a new `noctusai_lib.api.crud_safety` module if N=2+ DB-shape helpers surface).
- **Per-product code count for cross-cutting concern?** Zero. The 3 callsites become `from noctusai_lib.api.crud_safety import delete_with_existence_check`.

## 4. Scope

- **In scope:**
  - New seed-lib helper `delete_with_existence_check`.
  - Refactor of 3 known callsites: PF recorrentes router, ERP meta_periodos_service, ERP regras_pontuacao_service.
  - Tests: helper unit tests (both raise shapes); regression tests on the 3 callsites confirm no behavior change.
- **Out of scope:**
  - The other PF/ERP `if not result.data:` hits Engineer B surfaced (they're correct existence checks on READ paths, not the DELETE anti-pattern).
  - MockSupabaseClient UPDATE/SELECT propagation gap (separate seed-lib follow-up — Engineer B flagged it).

## 5. Architecture / Data Model

New helper at `seed/lib/backend/noctusai_lib/api/crud_safety.py`:

```python
def delete_with_existence_check(
    db,
    table: str,
    *predicates: tuple[str, Any],  # e.g. ("id", x_id), ("org_id", self.org_id)
    not_found_exc: Callable[[], Exception],  # caller-provided raise
) -> None:
    """Pre-check existence via select; raise if absent; delete on success.

    Replaces the `.delete().execute()` + `if not result.data: raise` shape
    that's an unreliable 404 detector when RLS collapses the row to invisible.
    """
    check = db.table(table).select("id")
    for col, val in predicates:
        check = check.eq(col, val)
    if not check.execute().data:
        raise not_found_exc()
    builder = db.table(table).delete()
    for col, val in predicates:
        builder = builder.eq(col, val)
    builder.execute()
```

Plus a thin HTTPException-flavored convenience wrapper:

```python
def delete_or_404(db, table: str, *predicates, message: str = "Not found") -> None:
    delete_with_existence_check(
        db, table, *predicates,
        not_found_exc=lambda: HTTPException(status_code=404, detail=message),
    )
```

## 6. Implementation phases

### Phase 0 — Verify N=3 + confirm no N=4 silently shipped

- [ ] Re-grep across all products: `grep -rn '\.delete()' --include='*.py' | grep -B1 'if not result.data'`. Catalog every hit. If N≥4, **STOP** and surface — silently shipping the Nth instance is forbidden.
- [ ] Verify Engineer B's two ERP citations are still at the reported line numbers.
- [ ] Confirm no in-flight engineer is editing these files (Engineer D is on `erp-org-scoping-completion` Phase 2 — coordinate).

### Phase 1 — Ship the seed-lib helper

- [ ] Author `seed/lib/backend/noctusai_lib/api/crud_safety.py` (helper + convenience wrapper).
- [ ] Re-export from `noctusai_lib.api.__init__.__all__`.
- [ ] Unit tests at `seed/lib/backend/tests/api/test_crud_safety.py`:
  - Happy path: row exists → deletes; row absent → raises caller-provided exc.
  - Variadic predicates: 1, 2, 3 predicates.
  - Both raise shapes: caller passes `HTTPException(404)` AND `LookupError`.
  - Status-code-assertion-rule honored on HTTP variant test.
- [ ] Run seed-lib pytest — all green.

### Phase 2 — Refactor 3 callsites

- [ ] PF `routers/recorrentes.py:106-108` → consume helper.
- [ ] ERP `services/meta_periodos_service.py:82-84` → consume helper with `LookupError` raise.
- [ ] ERP `services/regras_pontuacao_service.py:121-123` → consume helper with `LookupError` raise.
- [ ] AST-first edits (libcst). NEVER sed/regex.
- [ ] Run `pytest` for PF + ERP — all green; pre-existing baseline failures still pre-existing.
- [ ] Keeper review for both products — 0 issues.

### Phase 3 — Three-way sync + close

- [ ] Update `KB § PATTERNS/backend.md` (or sibling pattern doc) with the canonical helper.
- [ ] Memory entry `feedback_delete_with_existence_check.md` + MEMORY.md index row.
- [ ] CLAUDE.md: NO new bullet (covered by existing recurrence-rule bullet pointing to KB).
- [ ] Bundled proposal at `projects/delete-precheck-seed-lift/proposals/` if improvements accumulated; otherwise apply-inline-then-skip.
- [ ] `noctus.dev.archive` on close.

## 7. Open questions

- None — recurrence-rule + seed-lib home are unambiguous. Engineer B's findings already mapped the shape; this project is execution-only.

## 8. Dependencies & blockers

- **Engineer D (`erp-org-scoping-completion` Phase 2) is currently editing the same ERP backend directory.** Dispatch this project AFTER Engineer D's branch closes, to avoid file-conflict + double-pytest-config churn.

## 9. Success criteria

- [ ] N=3 callsites consume the seed-lib helper.
- [ ] Helper supports both raise shapes (HTTPException + LookupError) — proven by tests.
- [ ] PF + ERP test suites green; keeper 0 issues.
- [ ] `accept-with-rationale.md` entry (if one existed for this shape) flipped to FORMALIZED.

## 10. How to use this plan

Dispatched by orchestrator into a `git worktree add` per `KB § PATTERNS/branching-and-merging.md § 16`. Single-engineer brief covers all 3 phases. Branch name: `delete-precheck-seed-lift`.

## 11. Change log

| Date | Change | By |
|---|---|---|
| 2026-05-10 | **Filed under user signal "create projects for deferrals/parks that happen along the way."** Engineer B's PF Phase 2 close (commit `dbed0c6`) surfaced N=3 cross-product recurrence: PF-9 + ERP meta_periodos + ERP regras_pontuacao. Per DRY recurrence rule N=3 → MUST-FORMALIZE. Dispatch deferred pending Engineer D (`erp-org-scoping-completion` Phase 2) branch close — same ERP services dir, collision risk. | claude-opus-4-7 |

## 12. No-leftovers constraint

- Folder archives via `noctus.dev.archive` on close.
- No stray helper files outside `seed/lib/backend/noctusai_lib/api/crud_safety.py`.
