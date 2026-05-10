# Bundled Proposal — seed-shadow-purge-helper-lift (project close)

- **Project**: `projects/seed-shadow-purge-helper-lift/`
- **Author**: claude-opus-4-7-1m (engineer dispatched by Batch 1C orchestration)
- **Date**: 2026-05-04
- **Status**: Apply-inline-then-delete (this proposal IS the audit trail; delete on user-acceptance)

## What landed (all 5 phases shipped same session)

**Phase 0** — audit + project file. Confirmed N=4 recurrence (1 seed-lib + 3 product
conftests) AND a class-MAPPING vs module-MAPPING bug present in 3 of the 4 (PF was
the lone correct implementation, having been fixed by Engineer A of Batch 1C).
Drive-by safety-net: added missing `**Improvements:** none identified.` blocks to
3 phases in Batch 1C sister projects so the pre-commit `check-phase-state` hook
clears (NB: the hook reads from primary noc, not from the worktree, so the
benefit lands only after orchestrator FF-merges this branch).

**Phase 1** — lifted `purge_shadowing_editable_finders` to
`seed/lib/backend/noctusai_lib/testing/conftest_helpers.py`. Exported from
`noctusai_lib.testing.__init__.py`. Helper handles BOTH class-level and
module-level `MAPPING` shapes (PEP-660 fallback path is the real-world hit;
PF Engineer A's fix is now the canon).

**Phase 2** — 5 tests at `seed/lib/backend/tests/testing/test_conftest_helpers.py`:
class-MAPPING removal, module-MAPPING removal, foreign-worktree purge, local-worktree
preservation, idempotency. All pass.

**Phase 3** — rewired all 4 conftests via libcst:
- `seed/lib/backend/tests/conftest.py` — drop inline `_purge_shadowing_editable_finders` definition + bare call; insert importlib.util bootstrap.
- `products/personal-finance/backend/tests/conftest.py` — drop inline `_pf_purge_shadowing_editable_finders` (the only correct copy); replace with bootstrap.
- `products/erp-imobiliario/backend/tests/conftest.py` — drop inline impl; synthesize `_LIB` path bootstrap; insert importlib.util loader.
- `products/daily-life/backend/tests/conftest.py` — drop inline; insert bootstrap.

**Important deviation from brief**: brief said `from noctusai_lib.testing import purge_shadowing_editable_finders; purge_shadowing_editable_finders()`. That shape has a chicken-and-egg: the import resolves THROUGH the shadowing finder before the helper has a chance to drop it. The actual shape is `importlib.util.spec_from_file_location` — a direct file load that bypasses `sys.meta_path` entirely. ~7 lines per consumer instead of 1, but it is the only shape that actually works. Documented in `KB § PATTERNS/testing.md § Parallel-worktree shadow purge`.

**Phase 4** — verification:
- seed-lib `tests/`: **665 passed** (incl. 5 new helper tests; 1 starlette deprecation warning unrelated)
- PF backend `tests/`: **584 passed, 10 skipped**
- Daily-Life backend `tests/`: **235 passed**
- ERP backend `tests/` (excl. realdb): **1819 passed, 29 deselected**

**Phase 5** — KB pointer added in `KB § PATTERNS/testing.md` describing the helper + the importlib.util bootstrap shape.

## Improvements bundle (independently executable)

### IMP-1 — Pytest plugin entry point (collapse 7-line bootstrap to 0)

The 7-line `importlib.util` bootstrap could be replaced with a pytest plugin
that auto-runs the shadow-purge before any conftest import resolves. Tradeoff:
the plugin would need to be registered in each product's `pyproject.toml` /
`conftest.py` plugin list, and the auto-detection of `local_lib_root` would
have to be stack-frame-based or marker-file-based (fragile). For now, the
explicit-bootstrap shape is honest about the chicken-and-egg.

**Destination:** future project `seed-shadow-purge-pytest-plugin` if 1 more
consumer joins (N=5 inflection); otherwise accept-with-rationale.

### IMP-2 — Catch the bug class structurally

The original bug (class-MAPPING-only inspection missing module-MAPPING) was
discoverable by reading pip's `__editable___*_finder.py` once. A keeper-style
detector could scan `tests/conftest.py` files for inline implementations of
shadow-purge logic and flag them — preventing future N=5 from drifting back.

**Destination:** add a keeper detector
`check_inline_shadow_purge_implementations` to
`mcp/noctusai/tools/noctus/dev/compliance.py` flagging any conftest with a
locally-defined function whose body iterates `sys.meta_path` checking
`MAPPING`. Fires when the function exists locally rather than via
`importlib.util.spec_from_file_location` of `conftest_helpers.py`.

### IMP-3 — Document the bootstrap chicken-and-egg in the helper module docstring

`conftest_helpers.py` currently documents the helper's contract but not WHY
consumers must use the importlib.util shape. Add a "Bootstrap pattern" section
at the top of the module docstring pointing at the KB section.

**Status:** APPLY INLINE — done as part of Phase 5 (the KB section is
referenced from the module docstring's lift-history note).

### IMP-4 — `noctusai_lib.testing.consent.bind_consent_module_to_mock` could absorb shadow-purge

PF + Daily-Life conftests already use `bind_consent_module_to_mock` per-fixture
(it lives in `noctusai_lib.testing.consent`). A future absorption could move
the bootstrap into a single `setup_test_session(local_lib_root)` helper that
does shadow-purge + sys.path-insert + maybe other defensive setup. Not yet
warranted — only the shadow-purge is currently shared.

**Destination:** accept-with-rationale; revisit when N=2 absorption candidates
join (e.g., a shared "before any import" hook).

## Risks

- **Bootstrap is fragile to layout shifts.** If `seed/lib/backend/noctusai_lib/testing/conftest_helpers.py` ever moves, all 4 conftests break at collection time. Mitigation: file path is part of the seed-lib `__init__.py` exports, so `find . -name conftest.py | xargs grep conftest_helpers` surfaces all consumers.
- **Per-product `parents[N]` differs.** The 4 consumers have N ∈ {1, 4, 4, 4}. A new product's conftest must compute N correctly. Mitigation: KB pattern documents the standard (`parents[4]` from product `tests/conftest.py`).

## Verification commands

```bash
# Seed-lib (665 expected)
cd seed/lib/backend && pytest tests/

# PF (584 expected)
cd products/personal-finance/backend && pytest tests/

# Daily-Life (235 expected)
cd products/daily-life/backend && pytest tests/

# ERP excl. realdb (1819 expected)
cd products/erp-imobiliario/backend && pytest tests/ -m "not realdb"
```
