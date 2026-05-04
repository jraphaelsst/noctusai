# findings.md — seed-shadow-purge-helper-lift

> Per `KB § 01-PHILOSOPHY.md § Knowledge tracking`: append-as-you-go for surprises;
> synthesize at close. Five categories. `none` is a valid entry.

## Errors

- _(none yet — append if any encountered during build)_

## Mistakes / slips

- **Recurrence rule slip in Batch 1B → 1C**: the seed-side helper shipped with a known incorrect lookup
  (`getattr(finder, "MAPPING", ...)` against the class) but the bug was masked because product conftests
  hadn't yet been wired. When ERP + Daily-Life mirrored the seed-side helper verbatim in Batch 1C,
  they inherited the bug. PF Engineer A spotted + fixed it product-side (without backporting to seed).
  **Lesson:** when copying a helper across products, the absorption-search trio must run before AND
  after — and a bug fix in *any* mirror should propagate up to the seed before the next product copy.

## Lessons

- **Verify-the-seed-ships-it has a sub-shape:** "the seed has Helper X" is true on paper, but if the helper
  has a bug, every consumer who mirrors it inherits the bug. The verify rule needs to read the *correctness*
  of the seed implementation, not just its existence.
- **pip PEP-660 finder shape:** the `_EditableFinder` *class* has no `MAPPING` attribute; `MAPPING` is a
  module-level dict in the generated `__editable___<pkg>_<version>_finder.py`. The class is what gets
  appended to `sys.meta_path`. So a finder-attr inspection MUST also resolve `finder.__module__` →
  `sys.modules[<mod>]` → `mod.MAPPING`. PF Engineer A surfaced this; lifted helper handles both shapes
  defensively.

## Interesting findings

- **Divergence audit (4 implementations):**
  - `seed/lib/backend/tests/conftest.py` — class-MAPPING only (BUG: misses pip PEP-660 finders entirely).
  - `products/personal-finance/.../conftest.py` — class-MAPPING + module-MAPPING fallback (CORRECT).
  - `products/erp-imobiliario/.../conftest.py` — class-MAPPING only (BUG: same as seed).
  - `products/daily-life/.../conftest.py` — class-MAPPING only (BUG: same as seed).
  - Three of four are buggy; PF is the lone correct implementation.
- **Why the bug went unnoticed for so long:** in single-worktree workflows there is no shadowing finder
  to drop, so the helper is a no-op. The bug only surfaces under parallel-worktree usage where one
  worktree runs `pip install -e seed/lib/backend` and a sibling tries to import. Then the seed's
  buggy helper silently does nothing and the wrong source tree wins.
- **`sys.meta_path` shape:** pip's editable installer appends the *class* (`sys.meta_path.append(_EditableFinder)`).
  So `finder` in iteration is a class object whose `__module__` is the editable finder module name.
  `sys.modules[finder.__module__]` returns the module where `MAPPING` lives. That's the resolution path.

## Knowledge pieces (durable)

- **Lifted helper:** `noctusai_lib.testing.purge_shadowing_editable_finders(local_lib_root)` — accepts the
  worktree's `seed/lib/backend` Path; handles class-level + module-level MAPPING; returns `None`
  (mutates `sys.meta_path` and `sys.modules` as side effect by design — meant for conftest top-level use).
- **Wiring recipe (4 sites):**
  ```python
  from pathlib import Path
  import sys
  _LIB = Path(__file__).resolve().parents[N] / "seed" / "lib" / "backend"  # N varies
  if str(_LIB) not in sys.path:
      sys.path.insert(0, str(_LIB))
  from noctusai_lib.testing import purge_shadowing_editable_finders
  purge_shadowing_editable_finders(_LIB)
  ```
- **N=4 → MUST formalize.** This project IS the formalization (per the recurrence rule in
  `KB § PATTERNS/project-execution.md § 2.7`).
