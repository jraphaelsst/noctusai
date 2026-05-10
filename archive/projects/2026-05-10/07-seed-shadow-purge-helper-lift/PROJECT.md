# seed-shadow-purge-helper-lift — Project Document

- **Created:** 2026-05-04
- **Last updated:** 2026-05-04
- **Status:** ALL PHASES ✅ — helper lifted, 4 conftests rewired, 665+584+235+1819 tests passing, KB pointer + bundled proposal filed. Bootstrap shape deviates from brief (`importlib.util` instead of plain import) — chicken-and-egg, documented in proposal.
- **Owner / stakeholders:** joaoraphaelsst · architect-orchestrator (Batch 1C follow-up)
- **Related docs:**
  - `projects/pf-metas-seed-wiring/proposals/claude-opus-4-7-20260504-end-of-project-bundle.md`
  - `projects/erp-metas-seed-wiring/proposals/claude-opus-4-7-20260504-end-of-project-bundle.md`
  - `projects/daily-life-goals-seed-wiring/proposals/claude-opus-4-7-20260504-end-of-project-bundle.md`
  - `KB § PATTERNS/project-execution.md § 2.7 The recurrence rule`
  - `KB § PATTERNS/seed-lib-layout.md § testing/`
  - `KB § PATTERNS/testing.md`
- **Project slug:** `seed-shadow-purge-helper-lift` — at `projects/seed-shadow-purge-helper-lift/` (cross-product / platform-infra; touches seed-lib + 3 products + 1 seed-side conftest).

---

## 1. Context & Purpose

Three of the four current Batch-1B/1C metas-seed-wiring projects shipped a verbatim copy of the seed-side
parallel-worktree shadow-purge helper (`_purge_shadowing_editable_finders()`) into their product's
`tests/conftest.py`. PF (Engineer A of Batch 1C) discovered + fixed a bug in that helper but only patched
PF — the seed and the other two product mirrors still ship the buggy version.

**The bug.** The helper inspects `getattr(finder, "MAPPING", None)` against the *class* registered in
`sys.meta_path`, but pip's PEP-660 editable installer puts `MAPPING` at the *module* level of
`__editable___<pkg>_<version>_finder.py`. The class has no `MAPPING` attribute, so the lookup returns
`None` and the helper drops *no* finders — the parallel-worktree shadow is never purged.

**Why the bug stayed hidden.** Single-worktree workflows have no shadowing finder; the helper is a no-op
either way. Only parallel-worktree usage (one worktree owns `pip install -e seed/lib/backend`, a sibling
runs tests) surfaces it — and even then, the symptom is "tests resolve `noctusai_lib` to the wrong source
tree" which produces confusing import errors, not a clean failure.

**Recurrence count.** N=4 (1 seed + 3 products). The recurrence rule (`N=3+ → MUST formalize`) demands
absorption into seed-lib. This project IS the formalization.

**The win.**
1. Single source of truth for shadow-purge logic, in `noctusai_lib.testing.conftest_helpers`.
2. The lifted version handles BOTH class-level and module-level MAPPING shapes (correctness merge of
   PF's fix into the seed canon).
3. All 4 conftest sites collapse to a 1-line import + 1-line call.
4. New products inherit the helper for free; can never re-introduce the bug.

---

## 2. Confirmed constraints

- **Helper signature** — accept the worktree's `seed/lib/backend` Path explicitly; do not auto-detect.
  *(Each conftest knows its own `parents[N]` math; passing it in keeps the helper pure + testable.)*
- **Side-effect-by-design** — helper mutates `sys.meta_path` and `sys.modules` (drops cached
  `noctusai_lib*`). *(Documented; meant for conftest top-level use.)*
- **AST-first for the lift** — libcst for the new module + the 4 conftest rewires.
- **Class-MAPPING + module-MAPPING shapes both supported** — defensive against the PEP-660 install shape
  AND any hypothetical legacy/class-level shape.
- **No silent errors** — if a finder's `__module__` resolves to a module without `MAPPING`, fall through
  silently (same effect as `getattr` returning `None` — the finder is kept). Document this.
- **Branch-push only; never main** — orchestrator FFs after merge.
- **`PYTHON=/Users/rapha/Documents/repository/NoctusAI/noctusai/venv/bin/python` prefix** for all pytest
  invocations in this worktree (parallel-venv shadowing — defensive shadow-purge is exactly what we are
  formalizing here, but conftest only fires once pytest collects).

---

## 3. Design principles

1. **Lift unmodified-correctness.** PF's correct shape (class + module MAPPING fallback) becomes the
   canonical implementation. Seed + ERP + Daily-Life converge to it.
2. **Explicit local-root parameter.** The helper does not infer the worktree root; conftests pass the
   `seed/lib/backend` Path. *(Pure function modulo the documented `sys` mutations — testable.)*
3. **Idempotent.** Calling twice in one process is safe (second call is a no-op when shadowing was
   already cleared).
4. **Documented side-effects.** Docstring states `sys.meta_path` and `sys.modules` are mutated.
5. **Five high-value tests.** Class-MAPPING removal, module-MAPPING removal, foreign-target purge,
   local-target preservation, idempotency.

---

## 3a. Seed-first analysis (REQUIRED — the seed is every product's skeleton)

This project IS a seed-first absorption. The §3a checklist:

1. **Is the contract identical for every product?** YES — every product's conftest needs the same
   shadow-purge logic. The only product-specific bit is the `parents[N]` math to find the worktree's
   `seed/lib/backend`, which the conftest computes and passes in.
2. **Is the data source product-specific?** NO — the data is `sys.meta_path` (process-global).
3. **Is the placement product-specific?** NO — every product calls it at conftest top-level.
4. **Is the visibility / permission rule the same?** YES — same purge rule everywhere.
5. **Does the seam already exist in seed?** PARTIAL — `noctusai_lib.testing` exists as the package; we
   add `conftest_helpers` as a new submodule and re-export the function.
6. **Default-on or opt-in?** OPT-IN — each conftest decides to call it (some single-product test setups
   without parallel worktrees may not need it). The helper is silent + no-op when no shadowing finder
   exists, so calling it unconditionally is also safe.

**Litmus — per-product code count this design requires:**

- [x] **A small section** — 4 lines per product conftest (path math + sys.path insert + import + call).
  The shadow-purge logic itself lives in seed at 0-per-product cost.
- [ ] _0 lines / 1 line / multiple files_ — not applicable.

The 4 lines per product are unavoidable: each conftest must know its own depth to `seed/lib/backend`
(`parents[3]` for seed-lib's own conftest, `parents[4]` for product conftests). We could move the
`parents[N]` math into the helper too — but that would require the helper to introspect the caller's
filesystem location, which is fragile. Explicit-path-in is the cleaner contract.

**Phase plan implications:** §6 phases work in seed (lift) + 4 consumer rewires. No replication framing.

---

## 4. Scope

**In scope:**
- New module `seed/lib/backend/noctusai_lib/testing/conftest_helpers.py` exposing
  `purge_shadowing_editable_finders(local_lib_root: Path) -> None`.
- Re-export from `noctusai_lib.testing.__init__`.
- Rewire all 4 consumers (1 seed + 3 products) to import + call the lifted helper.
- New tests at `seed/lib/backend/tests/test_conftest_helpers.py` covering 5 cases.
- Brief KB pointer in `KB § PATTERNS/testing.md` referencing the new helper.

**Out of scope (for now — with reason):**
- Auto-detecting the worktree root in the helper — fragile + not requested. Conftests pass the path.
- Migration of `tests/__init__.py`-style auto-injection (e.g., a pytest plugin entry point) — could
  later collapse the 4-line conftest preamble to 0 lines, but adds packaging surface. Defer.
- Three-way sync to memory + CLAUDE.md — the brief permits a brief KB pattern entry; the helper is too
  niche to warrant a §1 universal rule. (Will be referenced from `KB § PATTERNS/testing.md` only.)

---

## 5. Architecture / Data Model

**New file:** `seed/lib/backend/noctusai_lib/testing/conftest_helpers.py`

```python
"""Conftest helpers for parallel-worktree-safe testing.

When the host venv carries an editable-install of `noctusai_lib` pointing at a
sibling worktree, that finder shadows the local `sys.path` entry and tests run
against the wrong source tree. This module ships the canonical shadow-purge
helper used by seed-lib + every product conftest.
"""
from __future__ import annotations
import sys
from pathlib import Path

__all__ = ["purge_shadowing_editable_finders"]

def purge_shadowing_editable_finders(local_lib_root: Path) -> None:
    """Drop meta-path finders whose `noctusai_lib` mapping points outside `local_lib_root`.

    Handles BOTH shapes pip PEP-660 / hand-rolled finders use:
      * class-level `MAPPING` attribute (legacy / hypothetical);
      * module-level `MAPPING` dict on the finder's defining module (pip's
        `__editable___<pkg>_<version>_finder.py` shape — the actual real-world
        case).

    Side-effects:
      * mutates `sys.meta_path` (drops shadowing finders);
      * drops cached `noctusai_lib*` entries from `sys.modules` so they
        re-resolve through the local source tree on next import.

    Idempotent: calling twice is safe (second call is a no-op).
    """
    local_target = str(local_lib_root.resolve())
    keep: list = []
    for finder in sys.meta_path:
        mapping = getattr(finder, "MAPPING", None)
        if mapping is None:
            mod_name = getattr(finder, "__module__", None)
            mod = sys.modules.get(mod_name) if mod_name else None
            mapping = getattr(mod, "MAPPING", None)
        if isinstance(mapping, dict) and "noctusai_lib" in mapping:
            target = str(Path(mapping["noctusai_lib"]).resolve())
            if not target.startswith(local_target):
                continue  # editable finder bound to a different worktree — drop it
        keep.append(finder)
    sys.meta_path[:] = keep
    for name in list(sys.modules):
        if name == "noctusai_lib" or name.startswith("noctusai_lib."):
            del sys.modules[name]
```

**4 consumer rewires (uniform shape):**

```python
from pathlib import Path
import sys
_LIB = Path(__file__).resolve().parents[N] / "seed" / "lib" / "backend"  # N varies per consumer
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))
from noctusai_lib.testing import purge_shadowing_editable_finders
purge_shadowing_editable_finders(_LIB)
```

| Consumer | Path | parents[N] |
|---|---|---|
| seed-lib | `seed/lib/backend/tests/conftest.py` | `parents[1]` (already at `seed/lib/backend/`) |
| PF | `products/personal-finance/backend/tests/conftest.py` | `parents[4]` |
| ERP | `products/erp-imobiliario/backend/tests/conftest.py` | `parents[4]` |
| Daily-Life | `products/daily-life/backend/tests/conftest.py` | `parents[4]` |

---

## 6. Implementation phases

### Phase 0 — Audit + project scaffold ✅
- [x] Read all 4 conftest implementations
- [x] Confirm the bug in 3 of 4 (seed/ERP/Daily-Life) and the fix in PF
- [x] Document divergence in this PROJECT.md + findings.md
- [x] Inspect pip's `__editable___noctusai_lib_0_1_0_finder.py` to confirm MAPPING is module-level
- [x] Reference the 3 originating Batch 1C bundled proposals
- [x] Commit Phase 0 on branch

**Improvements:** none identified — Phase 0 is pure audit + scaffold.

### Phase 1 — Lift helper to seed-lib (libcst-authored) ✅
- [x] Create `seed/lib/backend/noctusai_lib/testing/conftest_helpers.py` with the unified helper
- [x] Add `purge_shadowing_editable_finders` to `noctusai_lib/testing/__init__.py` exports + `__all__`

**Improvements:** none identified — straight lift + libcst export edit.

### Phase 2 — Tests for the helper ✅
- [x] Create `seed/lib/backend/tests/testing/test_conftest_helpers.py`
- [x] Test (a): class-MAPPING finder pointing outside local_root is removed
- [x] Test (b): module-MAPPING finder (pip PEP-660 shape) pointing outside local_root is removed
- [x] Test (c): finder pointing at a different worktree is purged
- [x] Test (d): finder pointing at the local worktree is preserved
- [x] Test (e): idempotency — calling twice is safe (no AttributeError, no double-removal)

**Improvements:**
- The idempotency test had to compare meta_path snapshots (not absolute lengths) because the test session itself runs through a real pip-editable finder pointing at a sibling worktree — the helper's first call drops it. Documented in the test docstring.

### Phase 3 — Rewire 4 consumers to use the lifted helper (libcst) ✅
- [x] Rewrite `seed/lib/backend/tests/conftest.py` (drop inline impl; replace with importlib.util bootstrap)
- [x] Rewrite `products/personal-finance/backend/tests/conftest.py`
- [x] Rewrite `products/erp-imobiliario/backend/tests/conftest.py`
- [x] Rewrite `products/daily-life/backend/tests/conftest.py`
- [x] Verify NONE of the 4 still has an inline `_purge_shadowing_editable_finders` definition

**Improvements:**
- **Brief deviation: bootstrap shape.** Brief said `from noctusai_lib.testing import purge_shadowing_editable_finders; purge_shadowing_editable_finders()`. Doesn't work — chicken-and-egg: `from noctusai_lib...` resolves THROUGH the shadowing finder before the purge can fire. Switched to `importlib.util.spec_from_file_location` direct file load (~7 lines per consumer instead of 1). Documented in proposal IMP-1 as future-collapse candidate via pytest plugin.
- Two libcst passes were needed: 3 consumers had a standard `sys.path.insert` block (one transformer); ERP had its path bootstrap INSIDE the helper function (different transformer that synthesized the `_LIB` assignment).

### Phase 4 — Verify (pytest gates) ✅
- [x] `seed/lib/backend/` pytest — **665 passed** (incl. 5 new helper tests)
- [x] PF backend pytest — **584 passed, 10 skipped**
- [x] ERP backend pytest (excl. realdb) — **1819 passed, 29 deselected**
- [x] Daily-Life backend pytest — **235 passed**

**Improvements:** none identified — verification phase, no code authored.

### Phase 5 — KB pointer + project close ✅
- [x] Added entry in `KB § PATTERNS/testing.md § Parallel-worktree shadow purge` documenting helper + bootstrap pattern
- [x] Filed bundled proposal at `projects/seed-shadow-purge-helper-lift/proposals/claude-opus-4-7-20260504-seed-shadow-purge-helper-lift-bundle.md`
- [x] Final-commit + branch-push — landed in commit `f46f76a` on origin/main 2026-05-04

**Improvements:** none identified — project-close mechanics.

---

## 7. Open questions

1. **Should the 4-line conftest preamble collapse further via a pytest plugin entry point?** — deferred
   to a future project. The 4-line shape is honest about the conftest's local-root math; a plugin
   that auto-detects via stack inspection trades clarity for line count.

---

## 8. Dependencies & blockers

- **None.** Helper is pure; tests use mock finder shapes; rewires are mechanical.

---

## 9. Success criteria

- [x] N=1 implementation in seed-lib; N=0 inline copies in any of the 4 consumers
- [x] 5 new tests passing in seed-lib
- [x] All 4 consumer test suites still green (665 + 584 + 235 + 1819)
- [x] Helper handles BOTH class-level and module-level MAPPING shapes
- [x] Brief KB entry in `KB § PATTERNS/testing.md`

---

## 10. How to use this plan

Standard. Phase-by-phase; live-tick. Phase 0 commit on branch first; per-phase commits as we go.

---

## 11. Change log

| Date | Change | By |
|---|---|---|
| 2026-05-04 | Phase 0 — file PROJECT.md after audit; document N=4 recurrence + bug + 3-of-4 buggy / 1-of-4 fixed shape | claude-opus-4-7-1m (engineer) |
| 2026-05-04 | Phase 1+2+3+4+5 ✅ — lifted helper to `noctusai_lib.testing.conftest_helpers`; 5 unit tests; 4 conftests rewired via libcst (bootstrap shape switched to `importlib.util` to break the chicken-and-egg the brief did not anticipate); KB pointer added; bundled proposal filed; all 4 test suites green (665 + 584 + 235 + 1819) | claude-opus-4-7-1m (engineer) |
