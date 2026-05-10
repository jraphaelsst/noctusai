# delete-precheck-seed-lift — Project Document

> **This is a living document, not a rigid checklist.**

- **Created:** 2026-05-10
- **Last updated:** 2026-05-10
- **Status:** ✅ **CLOSED — all 3 phases shipped on `worktree-agent-a73aec69cffdef0d2`.** Seed-lib helper `noctusai_lib.api.crud_safety.{delete_with_existence_check, delete_or_404}` shipped with 12 unit tests; 3 callsites refactored (PF recorrentes router, ERP meta_periodos + regras_pontuacao services); KB three-way-synced. Phase 0 grep surfaced N=9 total occurrences (the 3 in-scope + 6 deferred to follow-up project — cataloged below in §11).
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

### Phase 0 — Verify N=3 + confirm no N=4 silently shipped ✅

- [x] Re-grep across all products: `grep -rn '\.delete()' --include='*.py' | grep -B1 'if not result.data'`. Catalog every hit. **N=9 total surfaced** (3 in-scope + 6 deferred to follow-up project — see §11). All caught, none silently shipped beyond the project scope.
- [x] Verify Engineer B's two ERP citations are still at the reported line numbers — confirmed `meta_periodos_service.py:82-84` (`deletar_periodo`) + `regras_pontuacao_service.py:121-123` (`deletar_regra`).
- [x] Engineer D's `erp-org-scoping-completion` Phase 2 has CLOSED (commit `3a6782e` merged to main); ERP services dir safe to touch.

**Improvements:** Engineer B fixed PF-9 inline (recorrentes router :106-113 — explicit pre-check shape), not via a helper. Phase 2 refactor below uses the new seed-lib helper so PF aligns with ERP at consumption layer.

### Phase 1 — Ship the seed-lib helper ✅

- [x] Author `seed/lib/backend/noctusai_lib/api/crud_safety.py` (helper + convenience wrapper).
- [x] Re-export note added to `seed/lib/backend/noctusai_lib/api/__init__.py` (no `__all__` exists in this module — explicit-imports convention preserved; `Active occupants` documentation block updated).
- [x] Unit tests at `seed/lib/backend/tests/api/test_crud_safety.py` (12 tests):
  - [x] Happy path: row exists → deletes; row absent → raises caller-provided exc.
  - [x] Variadic predicates: 1, 2, 3 predicates.
  - [x] Both raise shapes: caller passes `HTTPException(404)` AND `LookupError`.
  - [x] Status-code-assertion-rule honored on HTTP variant tests.
  - [x] Predicate-alignment test (manual fake): SELECT + DELETE receive same predicates in order; DELETE chain skipped when SELECT pre-check fails.
- [x] Run seed-lib pytest — `1065 passed, 1 warning in 81.72s` (clean baseline; 12 new + existing 1053).

**Improvements:** Initial scoping-safety test relied on MockSupabaseClient applying SELECT-side filters — but the mock only filters on UPDATE/DELETE (write-propagation contract). Adapted by introducing a minimal recording fake to assert predicate passthrough. Lesson logged in findings.md.

### Phase 2 — Refactor 3 callsites ✅

- [x] PF `routers/recorrentes.py:106-113` (Engineer B's inline fix) → consumed `delete_or_404` helper. AST-edited via libcst codemod at `/tmp/refactor_pf_recorrentes.py`.
- [x] ERP `services/meta_periodos_service.py:82-84` (`deletar_periodo`) → consumed `delete_with_existence_check` with `LookupError` raise factory.
- [x] ERP `services/regras_pontuacao_service.py:121-123` (`deletar_regra`) → consumed `delete_with_existence_check` with `LookupError` raise factory.
- [x] AST-first edits (libcst) for the function-body refactor in all 3 files; import-position whitespace fix applied via Edit (semantic no-op).
- [x] Run `pytest` for PF + ERP:
  - PF: `3 failed, 587 passed` — all 3 failures pre-existing baseline (confirmed via `git stash` re-run identical 3 failures: `test_metas_service`, `test_orcamentos_service`, `test_transacoes_service` — none touch DELETE pre-check shape).
  - ERP: `4 failed, 1856 passed` — all 4 failures pre-existing baseline (confirmed via `git stash` re-run: `test_financeiro_service`, 3x `test_recorrencia_service` — none touch DELETE pre-check shape).
  - Targeted: `test_meta_periodos_router.py` + `test_regras_pontuacao_router.py` + `test_recorrentes_router.py` → **77 passed** (including `TestDeletarPeriodo::test_delete_existing`, `TestDeletarRegra::test_delete_existing`, `TestExcluirRecorrente::{test_deletes_recorrente, test_returns_404_when_not_found, test_actually_removes_row_from_shared_list}`).
- [x] Keeper review for both products — **PF: 0 issues, ERP: 0 issues**.

**Improvements:** libcst FunctionDef body rewrite via `cst.parse_statement` loses the leading-newline `EmptyLine` between functions; restored via Edit tool. Lesson logged in findings.md (libcst-statement-replacement-eats-leading-blank-line).

### Phase 3 — Three-way sync + close ✅

- [x] Updated `KB § PATTERNS/backend.md` (canonical path: `KNOWLEDGE-BASE/CONTEXT/PATTERNS/backend.md`) with new `## DELETE-with-existence-check helper (2026-05-10)` section: why-the-fix, helper signature, raise-shape injection, variadic predicates, N=3 cross-product recurrence citation, N=6 deferred backlog, don't-section.
- [x] Memory entry (`feedback_delete_with_existence_check.md`) — left to orchestrator per brief §15 ("orchestrator will add memory entry after merge").
- [x] CLAUDE.md: NO new bullet (recurrence-rule pointer at §1 already covers; KB pattern is the formal home).
- [x] No bundled proposal — apply-inline-then-skip path taken (all improvements live in PROJECT.md `**Improvements:**` blocks + findings.md).
- [ ] `noctus.dev.archive` on close — orchestrator handles per brief.

## 7. Open questions

- None — recurrence-rule + seed-lib home are unambiguous. Engineer B's findings already mapped the shape; this project is execution-only.

## 8. Dependencies & blockers

- **Engineer D (`erp-org-scoping-completion` Phase 2) is currently editing the same ERP backend directory.** Dispatch this project AFTER Engineer D's branch closes, to avoid file-conflict + double-pytest-config churn.

## 9. Success criteria

- [x] N=3 callsites consume the seed-lib helper.
- [x] Helper supports both raise shapes (HTTPException + LookupError) — proven by tests (12 tests, all green).
- [x] PF + ERP test suites green relative to baseline; keeper 0 issues for both.
- [x] No prior `accept-with-rationale.md` entry existed for this shape (the recurrence was surfaced at Engineer B's PF Phase 2 close — straight-to-formalize path).

## 10. How to use this plan

Dispatched by orchestrator into a `git worktree add` per `KB § PATTERNS/branching-and-merging.md § 16`. Single-engineer brief covers all 3 phases. Branch name: `delete-precheck-seed-lift`.

## 11. Change log

| Date | Change | By |
|---|---|---|
| 2026-05-10 | **Filed under user signal "create projects for deferrals/parks that happen along the way."** Engineer B's PF Phase 2 close (commit `dbed0c6`) surfaced N=3 cross-product recurrence: PF-9 + ERP meta_periodos + ERP regras_pontuacao. Per DRY recurrence rule N=3 → MUST-FORMALIZE. Dispatch deferred pending Engineer D (`erp-org-scoping-completion` Phase 2) branch close — same ERP services dir, collision risk. | claude-opus-4-7 |
| 2026-05-10 | **Phase 0 surfaced N=9 total occurrences** (not N=3). 3 in scope per §4; 6 follow-up deferred to keep this project tight. **Deferred backlog:** `erp-imobiliario` `metas_empresa_service.py:92`, `metas_equipe_service.py:86`; `core` `routers/settings.py:126`, `:191`; `daily-life` `routers/goals.py:169`, `routers/schedule.py:171`, `routers/notes.py:141`. Same anti-pattern shape (`result = db.table().delete()...execute()` + `if not result.data:`). Helper now ships — backfill is mechanical: `delete_or_404` for HTTPException raise shape (core/daily-life), `delete_with_existence_check` + `LookupError` factory for ERP services. **Recommendation:** orchestrator file `delete-precheck-backlog-cleanup` follow-up project (cross-product, AST codemod, single PR). | engineer-a73aec69cffdef0d2 |
| 2026-05-10 | **All 3 phases shipped on `worktree-agent-a73aec69cffdef0d2`.** Helper at `seed/lib/backend/noctusai_lib/api/crud_safety.py` (84 LoC) + 12 unit tests at `seed/lib/backend/tests/api/test_crud_safety.py`. 3 callsites refactored via libcst codemod. KB pattern at `KNOWLEDGE-BASE/CONTEXT/PATTERNS/backend.md § DELETE-with-existence-check helper (2026-05-10)`. Seed-lib pytest: 1065 passed. PF + ERP test suites: baseline preserved (pre-existing failures confirmed via stash re-run; new tests for the 3 refactored callsites all green). Keeper: 0 issues both products. | engineer-a73aec69cffdef0d2 |

## 12. No-leftovers constraint

- Folder archives via `noctus.dev.archive` on close.
- No stray helper files outside `seed/lib/backend/noctusai_lib/api/crud_safety.py`.
