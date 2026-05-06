# Proposal: erp-metas-seed-wiring end-of-project bundle

**Agent:** claude-opus-4-7 (engineer; dispatched by architect — parallel-batch 1C of N=3 sister wiring projects: pf-metas-seed-wiring + erp-metas-seed-wiring + daily-life-goals-seed-wiring)
**Origin:** project:erp-metas-seed-wiring:phase-1-2
**Generated:** 2026-05-04
**Severity:** medium
**Effort:** small (refactor done; follow-ups are independently executable)
**Affected products:** erp-imobiliario (directly); personal-finance + daily-life (cross-product follow-up §2.2)
**Status:** pending

---

## 1. Context

`projects/erp-metas-seed-wiring/` shipped the ERP-side wiring of
`noctusai_lib.domain.metas` (commit `09fa759`). Two ERP service files
were refactored:

- `products/erp-imobiliario/backend/app/services/metas_service.py` — 7
  local helpers (`_period_end_date`, `_count_weekdays`,
  `_dias_uteis_totais_mes`, `_dias_uteis_restantes_semana`,
  `_dias_uteis_restantes_mes`, `_dias_uteis_totais_ano`,
  `_dias_uteis_restantes_ano`, `_calcular_meta_proporcional`) collapsed
  to thin shims over the seed surface (`period_bounds`,
  `count_business_days`, `working_days_*`, `proportional_target`).
  ERP `tipo` ↔ `PeriodKind` mapping (`_TIPO_TO_PERIOD_KIND`) at
  the boundary; legacy "unknown tipo" fallback preserved.
- `products/erp-imobiliario/backend/app/services/meta_periodos_service.py` —
  3 bound helpers (`quinzena_bounds`, `mes_bounds`, `trimestre_bounds`)
  collapsed to thin delegations over seed `period_bounds`. The
  `gerar_trimestre` parent-child cascade + `_get_or_create_periodo` +
  `_months_in_trimestre` + `_month_name_pt` stay ERP-side (N=1).

Test contract preserved: every existing public function name +
signature + return shape unchanged. **53 focused tests pass; 1819 full
ERP backend tests (excl. realdb) pass; 660 seed/lib tests pass.** No
regression.

Five bundled improvements below — each independently executable, none
blocking another.

---

## 2. Bundled improvements

### 2.1 Lift `purge_shadowing_finders` into `noctusai_lib.testing`

**Linkage.** Mid-execution, ERP backend tests resolved
`noctusai_lib.domain.metas` to a sibling worktree's stale checkout (the
shared host venv has an editable-install of `noctusai_lib` pinned to
ONE worktree's `seed/lib/backend` path; sibling worktrees' tests get
shadowed). The `seed/lib/backend/tests/conftest.py` already had a
defensive shadow-purge from Batch 1B (`ai-plumbing-seed-absorption`),
but the **product-side conftests were not protected**. This project
shipped a duplicate of the same logic in
`products/erp-imobiliario/backend/tests/conftest.py`. The shape is now
N=2 (seed conftest + ERP conftest); the recurrence rule fires —
formalize.

**Application steps.** Add a public helper to
`noctusai_lib.testing`:

```python
# seed/lib/backend/noctusai_lib/testing/_shadow_purge.py
from __future__ import annotations
import sys
from pathlib import Path

def purge_shadowing_finders(local_lib_root: str | Path) -> None:
    """Remove sys.meta_path finders that map `noctusai_lib` to a path
    outside `local_lib_root`. Drop already-imported `noctusai_lib*`
    modules so they re-resolve through the local source tree.

    Idempotent + side-effect-scoped. Call from a conftest BEFORE any
    `from noctusai_lib...` import.
    """
    local_target = str(Path(local_lib_root).resolve())
    if local_target not in sys.path:
        sys.path.insert(0, local_target)
    keep: list = []
    for finder in sys.meta_path:
        mapping = getattr(finder, "MAPPING", None)
        if isinstance(mapping, dict) and "noctusai_lib" in mapping:
            target = str(Path(mapping["noctusai_lib"]).resolve())
            if not target.startswith(local_target):
                continue
        keep.append(finder)
    sys.meta_path[:] = keep
    for name in list(sys.modules):
        if name == "noctusai_lib" or name.startswith("noctusai_lib."):
            del sys.modules[name]
```

Then update each product conftest to:

```python
from pathlib import Path
from noctusai_lib.testing import purge_shadowing_finders

# Find local seed/lib/backend (climb to worktree root, then descend).
_LOCAL_LIB = Path(__file__).resolve().parents[4] / "seed" / "lib" / "backend"
purge_shadowing_finders(_LOCAL_LIB)
```

**Risks.** Bootstrapping order — the helper itself must be importable
BEFORE the shadow-purge runs. Either (a) inline a copy in each
conftest as today (the proposed lift drops this), or (b) the conftest
imports from the local `seed/lib/backend` directly via `sys.path`
manipulation. Option (b) is what the seed conftest already does, so
it's pre-validated.

**Triage.** **N=2 → triage time.** Recommend formalize: the helper is
small (15 LOC), the use case keeps recurring as new products land or
new parallel-worktree workflows mature, and the seed-lib already
exposes `noctusai_lib.testing` for this kind of shared test plumbing.

### 2.2 Mirror the shadow-purge in PF + daily-life conftests

**Linkage.** Sister engineers in this batch (PF + daily-life) face the
exact same shadowing issue; their wiring of
`noctusai_lib.domain.metas` will fail with `ModuleNotFoundError` until
their conftests have a shadow-purge. The architect should anticipate
this when merging the sister branches — either land the seed helper
(§2.1) first and have all three product conftests consume it, or
land all three product conftest copies in the same retrospective.

**Application steps.** Either:
- (preferred, post-§2.1) update PF + daily-life conftests to consume
  the seed helper.
- (fallback, immediate) inline copy the same `_purge_shadowing_editable_finders`
  from this branch's `products/erp-imobiliario/backend/tests/conftest.py`
  into the equivalent product conftests.

**Risks.** None — the fix is observation-only (drops shadowing finders;
local lib resolution wins). Idempotent.

**Triage.** **Refactor.** Both sister branches need it; orchestrator
applies during merge if not already shipped by the sister engineers.

### 2.3 ERP `tipo` vocabulary unification — defer

**Linkage.** ERP has TWO tipo vocabularies across its metas surface:
`metas_service.py` uses `diaria/semanal/mensal/anual`; `meta_periodos_service.py`
uses `quinzenal/mensal/trimestral/anual`. Both map to `PeriodKind` via
small in-file mappings. A future cleanup project could unify them
(via the `PeriodKind` enum at the API/router boundary), but that's a
schema-touching change (the `metas` table's `tipo` column +
`meta_periodos.tipo` column would need to settle on one vocabulary).

**Application steps.** None now. When ERP next opens a metas-domain
project, evaluate whether to migrate one of the vocabularies (preserving
DB compatibility via a view or column rename migration).

**Risks.** Schema migration; out of scope here.

**Triage.** Accept-with-rationale. This is a documented divergence the
seed-wiring intentionally preserves (test contract preservation). If
N=3 product cycles surface the same friction, escalate to formalize.

### 2.4 Cosmetic — `metas_service.py` module docstring stale wording

**Linkage.** The docstring says "All date math is computed in Python
to avoid N+1 RPC round-trips to the database." Post-refactor, the math
lives in `noctusai_lib.domain.metas` (still pure Python; the N+1
avoidance still holds because the seed math is in-process), but the
wording reads as if the math is local to the file.

**Application steps.** Rewrite the docstring to:
"All date math delegates to `noctusai_lib.domain.metas` (kept pure-Python
to avoid N+1 RPC round-trips against the database)."

**Risks.** None.

**Triage.** Accept (low value, defer to next ERP-metas touch) OR apply
inline in this commit (cheap). **Recommendation:** apply inline since
the file is already being touched.

### 2.5 `quinzena_bounds`/`mes_bounds`/`trimestre_bounds` callers could go direct

**Linkage.** Inside `meta_periodos_service.py`, 5 callers use the local
`mes_bounds(ref)` / `quinzena_bounds(ref)` / `trimestre_bounds(year, q)`
shims. Each call could become `period_bounds(PeriodKind.X, ref)` directly,
eliminating the shims entirely. The cost is updating the test file
(`tests/routers/test_meta_periodos_router.py` imports the shim names
to assert math equivalence).

**Application steps.** Future cleanup project: replace shim-call sites
with seed-call sites; redirect the corresponding tests to the seed's
existing `tests/domain/metas/test_periods.py`. Drop the shims entirely.

**Risks.** Low — pure-function math swap. Test file movement is the
main cost.

**Triage.** Accept-with-rationale. The shims are 5 LOC and serve a
docstring purpose (translate `(year, quarter)` → date inside quarter
for `trimestre_bounds`). Wait until N=2 callers across products use
the shim shape before formalizing — for now, the shim shape is
ERP-only.

---

## 3. Acceptance Criteria

- [ ] §2.1 (`purge_shadowing_finders` lift) — file as
  `seed-shadow-purge-helper-lift` follow-up project; small (15 LOC +
  tests + 3 conftest consumer updates).
- [ ] §2.2 (mirror in PF + daily-life) — handled by architect during
  Batch 1C merge OR by sister engineers in their branches.
- [ ] §2.3 (tipo vocabulary unification) — deferred; reopen at N=2.
- [ ] §2.4 (docstring) — apply inline if cheap, otherwise next ERP touch.
- [ ] §2.5 (drop shims) — deferred; reopen at N=2.

---

## 4. Standalone vs scheduled

All five improvements are **independently executable**.

- §2.1 + §2.2 together close the shadow-purge gap (formalize + mirror).
- §2.3, §2.4, §2.5 are independent cleanups.

---

## 5. Related files

- `products/erp-imobiliario/backend/app/services/metas_service.py` — refactored.
- `products/erp-imobiliario/backend/app/services/meta_periodos_service.py` — refactored.
- `products/erp-imobiliario/backend/tests/conftest.py` — defensive shadow-purge added.
- `seed/lib/backend/tests/conftest.py` — seed-side shadow-purge (reference / N=1 prior).
- `seed/lib/backend/noctusai_lib/testing/` — proposed §2.1 destination.
- `KB § PATTERNS/metas-seed.md` — wiring recipe (consumer-side reference).
- `projects/metas-domain-seed-absorption/proposals/claude-opus-4-7-20260503-end-of-project-bundle.md` — the parent absorption project's bundle that this wiring closes.

---

## 6. Phase learnings (synthesized)

1. **Verify the venv path before the test run.** The host venv editable
   install pinned `noctusai_lib` to one worktree; this trips up every
   sibling worktree until conftests are protected. **Lesson durable in
   memory:** when running tests in a parallel-worktree, run
   `python -c "import noctusai_lib; print(noctusai_lib.__file__)"`
   first — if the path doesn't match `<this-worktree>/seed/lib/backend/noctusai_lib`,
   the conftest needs the shadow-purge before any `noctusai_lib` import.
2. **Naming-collision audits cost a phase.** "9 metas-related service
   files" included `meta_api_service.py` (Facebook/Meta API), unrelated.
   30-second purpose-skim of each file BEFORE the audit narrows scope
   accurately.
3. **Phase 1+2 collapse held.** Engineer 3 §2.5 calibration validated:
   for a wiring cycle (no new design surface), Phase 1 (refactor) and
   Phase 2 (close + bundled proposal) collapse into a single working
   pass. PROJECT.md sub-task list under one phase header is the cleanest
   shape.
4. **Test contract preservation > code minimalism.** Keeping the
   ERP-side helper names as 1-line shims (rather than deleting them
   and migrating all callers / tests) shipped the refactor in 2 files
   touched instead of 5+. The shim shape is the right boundary today;
   when N=2 callers want direct seed access, formalize via §2.5.
5. **AST-first held end-to-end.** Both refactors used libcst
   transformers; only Edit was used afterwards for PEP 8 whitespace
   touch-ups (an indication the libcst node-replacement could output
   trailing-newline adjustments more carefully — minor; not worth
   refactoring the transformer).
