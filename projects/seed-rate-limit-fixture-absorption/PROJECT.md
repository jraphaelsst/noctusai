# seed-rate-limit-fixture-absorption — Project Document

> Engineer SEED-RATELIMIT-FIXTURE dispatched 2026-05-11 to absorb the N=5 byte-identical autouse `_reset_rate_limiter` pytest fixtures into the seed.

- **Created:** 2026-05-11
- **Last updated:** 2026-05-11
- **Status:** Shipped (all 5 phases complete; ready for FF-to-main)
- **Owner / stakeholders:** Architect / Engineer SEED-RATELIMIT-FIXTURE
- **Related docs:** `seed/lib/backend/noctusai_lib/testing/fixtures.py`, `KB § PATTERNS/seed-lib-layout.md`, `KB § PATTERNS/project-execution.md § 2.7 The recurrence rule`
- **Project slug:** `seed-rate-limit-fixture-absorption` — at `projects/` (cross-product seed work)

---

## 1. Context & Purpose

Surveyed N=5 byte-identical autouse pytest fixtures across product conftests:

1. `products/core/backend/tests/conftest.py:299` (from `auth-rate-limit-rollout-2026-05-11`)
2. `products/therapy-platform/backend/tests/conftest.py:57` (auth-rate-limit-rollout)
3. `products/media-scheduling/backend/tests/conftest.py:29` (auth-rate-limit-rollout)
4. `products/mailing/backend/tests/conftest.py:20` (llm-endpoint-rate-limit-rollout-2026-05-11)
5. `products/daily-life/backend/tests/conftest.py:51` (llm-endpoint-rate-limit-rollout)

Each fixture body identical (modulo docstring prose):

```python
@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    from app.rate_limit import limiter
    limiter.reset()
    yield
    limiter.reset()
```

DRY recurrence rule (KB § PATTERNS/project-execution.md § 2.7): N≥3 byte-identical → MUST formalize. The fixture belongs in `noctusai_lib.testing.fixtures` — same layer as the existing `purge_shadowing_editable_finders` testing helper + the `noctusai-product-bootstrap` pytest11 plugin.

---

## 2. Confirmed constraints

- **Option A chosen over Option B** — explicit `from noctusai_lib.testing.fixtures import reset_rate_limiter  # noqa: F401` per product conftest. Brief recommended A; rationale: greppable, aligns with seed's "no magic" stance, avoids autouse-everywhere side effect (the pytest11 plugin already exists for true session-bootstrap work where everywhere-autouse IS desired).
- **Activation mechanism** — pytest's autouse discovery scans the conftest module's namespace for `_pytestfixturefunction`/`_fixture_function_marker` attrs. Re-importing the symbol into the conftest brings it into that namespace → autouse fires for tests under that conftest.
- **Lazy import inside fixture body** — `from app.rate_limit import limiter` stays inside the fixture function, NOT at module top of `fixtures.py`. Keeps the seed-lib module importable from non-product contexts (seed-lib own tests, mcp tests) without triggering `ModuleNotFoundError: No module named 'app'`.
- **AST-first** — libcst for the per-product conftest edits.
- **Coordination** — STRICT-HTTP Waves 2/3 (schemas, not conftest), SLOWAPI-PEP563-DETECTOR / HOUND-ABC-FILTER (mcp/, not seed/), THERAPY-MP-KB-REFRESH (KB docs, not conftest). Disjoint.

---

## 3. Design principles

1. **Re-export over magic.** Products explicitly import the fixture; pytest's standard autouse discovery handles activation.
2. **Lazy import of `app.rate_limit`.** Seed-lib doesn't depend on product modules; the import resolves only when a product test triggers the fixture.
3. **Preserve docstring history.** Per-product test docstrings that reference the fixture were updated from `_reset_rate_limiter` to `reset_rate_limiter` so future readers find the seed source on grep.

---

## 3a. Seed-first analysis (REQUIRED)

1. **Is the contract identical for every product?** YES — N=5 byte-identical fixture bodies.
2. **Is the data source product-specific?** NO — every product imports its own `app.rate_limit.limiter`; the symbol path is uniform.
3. **Is the placement product-specific?** NO — every product's conftest needs the fixture.
4. **Is the visibility / permission rule the same?** N/A — pure test infrastructure.
5. **Does the seam already exist in seed?** PARTIALLY — `noctusai_lib.testing` package exists with mocks/clients/plugin but no shared fixtures module. Adding `fixtures.py` extends the same surface.
6. **Default-on or opt-in?** OPT-IN via explicit import — autouse activates only where the conftest imports the symbol.

**Litmus** — per-product code count: **1 import line per product conftest** (replaces ~12-line fixture def + docstring → net -55 LoC across the 5 conftests).

**Phase plan implications:** §6 phases work in seed (Phase 1) then absorb the seed via simple import line (Phase 2). No "for each product replicate" framing.

---

## 4. Scope

**In scope:**
- Add `noctusai_lib.testing.fixtures.reset_rate_limiter` autouse fixture.
- Re-export from `noctusai_lib.testing.__init__.py` (both binding + `__all__`).
- 2 seed-lib unit tests (fixture-marker assertion + body behavior).
- Migrate 5 product conftests via libcst (remove inline def + insert import).
- Update 5 product test docstrings that reference the old fixture name.
- Per-product baseline verification (PYTHONPATH override for shadowed venvs).

**Out of scope (deferred):**
- pytest11 entry-point auto-load (Option B). Filed as accept-with-rationale: the existing `noctusai-product-bootstrap` plugin already covers the "everywhere autouse" niche; adding a second always-on side-effect would obscure activation flow.

---

## 5. Architecture

```
seed/lib/backend/noctusai_lib/testing/
├── __init__.py                    # re-exports reset_rate_limiter
├── fixtures.py                    # NEW — autouse fixture lives here
├── conftest_helpers.py            # purge_shadowing_editable_finders
├── pytest_plugin.py               # noctusai-product-bootstrap (pytest11)
├── mocks.py                       # MockSupabaseClient + builders
├── clients.py                     # MockUser / AuthClient
├── ...

seed/lib/backend/tests/testing/
├── test_conftest_helpers.py       # existing
└── test_fixtures.py               # NEW — 2 tests
```

Product conftests:

```python
# Before (5 conftests, 12-line def each):
@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    """..."""
    from app.rate_limit import limiter
    limiter.reset()
    yield
    limiter.reset()

# After (5 conftests, 1 line each):
from noctusai_lib.testing.fixtures import reset_rate_limiter  # noqa: F401
```

---

## 6. Phases

### Phase 0 — Audit ✓
- `git grep _reset_rate_limiter` → confirmed N=5 across core/therapy/media/mailing/daily-life.
- All 5 fixture bodies byte-identical (4 lines: import, reset, yield, reset).
- Docstrings vary (project-attribution prose); functionally irrelevant.

### Phase 1 — Seed implementation ✓
- Created `seed/lib/backend/noctusai_lib/testing/fixtures.py` with `reset_rate_limiter` autouse fixture.
- Added re-export to `noctusai_lib.testing.__init__.py` (`__all__` updated).
- Created `seed/lib/backend/tests/testing/test_fixtures.py` with 2 tests:
  - `test_reset_rate_limiter_is_pytest_fixture_marked_autouse` — asserts `_fixture_function_marker.autouse is True` (pytest 8+) with `_pytestfixturefunction` fallback for pytest <8.
  - `test_reset_rate_limiter_resets_pre_and_post_yield` — drives the underlying generator against a stub `app.rate_limit` module; asserts `limiter.reset()` invoked twice.
- Seed-lib pytest: **1178 → 1180 passed** (+2 fixture tests).

### Phase 2 — Per-product migration ✓
- libcst codemod (`migrate_rate_limit_fixture.py`) — single-pass AST transform:
  - `RemoveResetRateLimiterAndImport` transformer: removes any FunctionDef named `_reset_rate_limiter` decorated with `@pytest.fixture(autouse=True)`.
  - `add_seed_fixture_import` post-step: inserts `from noctusai_lib.testing.fixtures import reset_rate_limiter  # noqa: F401` after the last existing `noctusai_lib` import (falls back to top-of-module after docstring if no such import exists).
- Ran on 5 conftests → all 5 migrated cleanly.

### Phase 3 — Tests ✓
- Seed-lib `pytest tests/`: 1178 → **1180 passed** (+2 fixture tests).
- Per-product baselines preserved (PYTHONPATH override to local seed/lib for shadowed-venv products):
  - core: 483p / 9s ✓
  - therapy-platform: 1332p / 14s / 6 pre-existing failures (env-var related, unchanged) ✓
  - media-scheduling: 113p ✓
  - mailing: 213p / 1 pre-existing failure (e2e flow, unchanged) ✓
  - daily-life: 209p ✓
- `git grep _reset_rate_limiter` → 0 hits (all 5 docstring references also updated to `reset_rate_limiter`).

### Phase 4 — Keeper ✓
- 0 new keeper checks per the brief.

---

## 11. Change log

- **2026-05-11** — Engineer SEED-RATELIMIT-FIXTURE: Phases 0-4 shipped same session. N=5 → 0 inline fixture defs; +1 seed fixture symbol; +2 seed-lib tests; 5 conftests carry the import; 5 test docstrings updated.
