# Silent test failure from missing optional dep

> A test suite reports "green" while N tests silently fail-to-import — sibling
> of `boundary-contract-tests.md` but at the **dep-declaration boundary**.
> Born 2026-05-26 when `pgvector` dep wasn't declared and 11 tests in
> `test_cache_backend_postgres.py` quietly red'd for weeks.

## The shape

A test file imports a module that conditionally imports a dep (`try/except ImportError`). The production code degrades gracefully — runtime emits a warning, falls back to a less-rich path — but the test suite **needs** that dep to exercise the import-gated code paths. When the dep isn't declared in `requirements.txt` / `pyproject.toml` and isn't installed in the venv:

- `pytest --collect-only` → tests collect fine (the test file imports succeed)
- `pytest` run → each test that uses the optional code path fails with `ModuleNotFoundError`, but the failure is **localized to those tests**
- The overall test count keeps growing (more tests added over time) so the failing N never crosses a threshold that flags attention
- CI greens because the failing tests are <100% of the suite and the suite-level exit code isn't dominated by them
- Net effect: a real validation surface is silently red, and nobody notices

## Concrete instance (the 2026-05-26 surfacing)

`mcp/noctusai/tools/noctus/dev/cache_backend_postgres.py` does:

```python
try:
    from pgvector.psycopg2 import register_vector
    register_vector(conn)
except ImportError:
    logger.warning("pgvector Python package not installed; ...")
```

`test_cache_backend_postgres.py` writes tests that exercise both branches — including ones that assert `register_vector` *did* fire. Without `pgvector` installed, those tests silently fail. The dep was never in `requirements.txt` / `pyproject.toml`. 11 tests stayed red across weeks of activity until a session's infra-polish slice happened to install the dep, watch the failures flip green, and trace the gap to the missing declaration.

The cost was zero (no production bug, just silent dev-time coverage loss) — but the shape itself is the worry, not this instance.

## Why this is a recurrence class

The shape generalizes to **any optional dep referenced by `try: import X / except ImportError`** that has tests exercising the imported-branch path:

- `psycopg2-binary` (this case's sibling — same root cause)
- `redis` / `fakeredis` (only fakeredis is declared; real redis paths are tested under fake)
- `tiktoken` (declared but historically `chars/4` fallback also has tests)
- Any backend-selector pattern with a primary + fallback
- Any feature-flag-gated import

Two of these (`pgvector` + `psycopg2`) showed up the same day on the same module. N=2 already; the next instance promotes this to N=3 and the recurrence rule says formalize-with-a-keeper.

## The right shape (rule)

A test that requires an optional dep to exercise its imported branch needs ONE of:

1. **Declare the dep as required** in `requirements.txt` + `pyproject.toml` (for the MCP toolkit, `mcp/noctusai/requirements.txt` + `mcp/noctusai/pyproject.toml` are the two surfaces that need to stay in lockstep).
2. **Skip-marker the test** with `@pytest.mark.skipif(not <dep_present>, reason="needs X")` — only if the dep is genuinely optional AND the test cannot validate the fallback path through other means.

The default is option 1 — declare the dep. Option 2 is the carve-out for genuinely-optional features (e.g., a vector-backend that supports 3 alternatives).

## Detection (deferred to keeper)

Stage-3 by-design today. Codified as a recurrence pattern; promoted to a Stage-4 keeper when N=3 lands. The keeper shape would be:

`check_test_imports_match_declared_deps` — for each `test_*.py`, parse the source for `import X` / `from X import` statements that aren't stdlib; cross-reference against the package's `requirements.txt` + `pyproject.toml` declared deps; flag tests that import a dep not declared AT ALL (the silent-failure shape). The escape hatch is a `# test-needs-optional-dep: <X>` marker on the line or file, signaling intentional skipif-guarded import.

## Composes with

- `KB § CONTEXT/PATTERNS/backend/boundary-contract-tests.md` — this is a SIBLING shape: that one is "contract at a wire/build boundary untested between sides", this one is "test exists but silently fails because of an environment-declaration boundary". The unit-tests-each-side-but-not-the-contract pattern includes the test↔dep-manifest contract.
- `KB § CONTEXT/01-PHILOSOPHY.md` (codebase-is-source-of-truth) — verify against the running test suite, not the assumption that "all green = all running".
- `KB § CONTEXT/PATTERNS/compliance/testing.md` — adjacent (test discipline).

## How to spot it tomorrow

If you're touching a module whose production code has `try: import X / except ImportError` AND there's a sibling test file:
1. Read the test file → list every external import (non-stdlib, non-test-only)
2. Diff against the package's declared deps (`requirements.txt` ∪ `pyproject.toml`)
3. Any import not in the declared deps is a silent-failure candidate — either declare it, or skip-marker the affected tests

The 30-second version: `pytest <test_file> -v` and look for any `ModuleNotFoundError`/`ImportError` in the failure summary. If you see one and the package is referenced by production code with a `try/except`, the dep needs declaring.
