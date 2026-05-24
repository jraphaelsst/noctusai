# Testing Standards

Every product must have all five test layers. No product ships without them.

| Layer | What it tests | Where | When to write |
|-------|---------------|-------|---------------|
| **Unit (routers)** | Individual endpoints — CRUD, auth, validation, error handling | `tests/routers/test_*.py` | One per domain router |
| **Unit (services)** | Business logic in isolation — calculations, transformations, state machines | `tests/services/test_*.py` | One per service with non-trivial logic |
| **Integration** | Cross-service flows — campaign references template + list, automation enrolls contacts | `tests/integration/test_*.py` | When entities reference each other |
| **E2E** | Full user journeys — create contact → template → campaign → send → verify stats | `tests/integration/test_e2e_flows.py` | One per product, covers the golden path |
| **Regression** | Bug-shaped tests pinning behavior that broke in production / detector false-positives / security incidents / known-edge-cases. Names the incident. | `tests/regression/test_<short_case>.py` (or inline `# Regression: ...` docstring inside the closest unit/integration test) | Every time a bug is fixed, a detector misbehaves on a real case, or an incident discovered behavior the unit tests didn't cover |

## Rules

- **Unit tests:** mock the database (`MockSupabaseClient`). Test one endpoint at a time.
- **Integration tests:** mock the database but test multi-step flows where step N depends on step N-1.
- **E2E tests:** simulate a real user journey through multiple endpoints. Each test is a story.
- **Regression tests:** name the case. Every regression test must reference the incident in its docstring or filename — date, project that surfaced it, or original ticket. Without that reference, it's just a unit test that may decay into noise. See `§ Regression tests in practice` below.
- **Deterministic:** no hardcoded dates (use `date.today()` / `date.today() - timedelta(days=N)`), no external API calls, no network.
- **Auth boundary:** every product must verify that unauthenticated requests return 401 for all protected endpoints.
- **No self-monkeypatching:** never `monkeypatch.setattr(<our_module>, "<our_fn>", _noop)` or `patch.object(<our_module>, "<our_fn>", ...)`. If you find yourself reaching for it, the test is asking you to wire a seam differently. See `§ No self-monkeypatching — refactor playbook` for the three legitimate patterns.

## Running

```bash
cd <product>/backend && pytest                  # all tests
cd <product>/backend && pytest tests/routers    # just router tests
cd <product>/backend && pytest -k test_contacts # by name
```

**Stale-bytecode gotcha — verify test COUNTS against fresh bytecode.** When verifying pytest **test counts** (especially inside a git worktree), a stale `__pycache__` / `.pytest_cache` can make pytest import an OLD compiled module ⇒ it collects the wrong number of tests (we hit 11-vs-13: an appended test class was on disk but pytest ran cached bytecode). Remedy: nuke caches first (`find <dir> -name '*.pyc' -delete && rm -rf __pycache__ .pytest_cache`), or run with `PYTHONDONTWRITEBYTECODE=1 … -p no:cacheprovider`, or trust the OS line-count (`git diff --numstat`) over a cached pytest collection. An "absence of N tests" is a claim — confirm against fresh bytecode (`KB § 01-PHILOSOPHY.md § No silent errors`).

## Mock helpers

Import from the seed test kit:
```python
from tests.conftest import (
    MockSupabaseClient,
    MockSelectBuilder,
    MockUser,
    MockUserResponse,
    AuthClient,
    bind_user_metadata,
)
```

Each product's `conftest.py` re-exports these from the shared seed test helpers. Don't re-implement mocks per product.

### Re-binding the auth user — `bind_user_metadata` (since 2026-05-10)

The mock's `auth.get_user` is a `MagicMock` returning a fixed `MockUser` regardless of token bytes. To exercise role-gated routes or distributor/clinic-scoped reads, tests rebind the user_metadata via `bind_user_metadata(...)`:

```python
from noctusai_lib.testing import bind_user_metadata

def test_admin_can_list_distributors(client):
    bind_user_metadata(client, role="admin", org_id="org-1")
    r = client.raw().get("/distributors")
    assert r.status_code == 200
```

Lifted from N=15+ inline `mock.auth.get_user = MagicMock(return_value=MockUserResponse(MockUser(...)))` callsites across product conftests during `adconnect-test-conftest-distributor-binding` Phase 2. **Replaces the inline `auth.get_user = MagicMock(...)` shape; do not roll your own.**

Products with product-specific role names / claim shapes wrap this with a thin product-bound helper in their own conftest (e.g. AdConnect's `bind_adconnect_user(client, *, role, distributor_id, org_id)` mapping `distributor_id` → `extra_metadata["distributor_id"]` → `user["distributorId"]` via `auth_deps`).

### Parallel-worktree shadow purge — `purge_shadowing_editable_finders`

When the host venv carries an editable-install of `noctusai_lib` pointing at one
worktree's `seed/lib/backend`, sibling worktrees that try to run tests will
resolve `noctusai_lib` through the install's pip PEP-660 finder — i.e. against
the **wrong** source tree. The lifted helper at
`noctusai_lib.testing.purge_shadowing_editable_finders` (in
`noctusai_lib/testing/conftest_helpers.py`) drops shadowing finders whose
`MAPPING['noctusai_lib']` points outside the local worktree's `seed/lib/backend`,
and clears cached `noctusai_lib*` from `sys.modules` so re-imports resolve locally.

Handles BOTH `MAPPING` shapes: class-level (legacy) and module-level (the actual
real-world shape pip's `__editable___<pkg>_<version>_finder.py` uses — surfaced
by PF Engineer A 2026-05-04, lifted to seed in `seed-shadow-purge-helper-lift`).

**Bootstrap pattern (4 conftests use this verbatim):**
```python
import sys
from pathlib import Path

_LIB = Path(__file__).resolve().parents[N] / "seed" / "lib" / "backend"  # N varies
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))

# Direct importlib.util load — bypasses sys.meta_path so the shadow-purge
# bootstraps BEFORE any `from noctusai_lib...` resolves through the
# (potentially shadowing) editable finder.
import importlib.util as _ilu
_spec = _ilu.spec_from_file_location(
    "_bootstrap_conftest_helpers",
    _LIB / "noctusai_lib" / "testing" / "conftest_helpers.py",
)
_mod = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
_mod.purge_shadowing_editable_finders(_LIB)
```

The bootstrap shape is unavoidable: the helper must run BEFORE the shadowing
finder is given a chance to satisfy `from noctusai_lib...`. After the purge,
normal `from noctusai_lib.testing import ...` lines resolve correctly to the
local worktree.

### Seed-singleton isolation guard — `seed_singleton_guard` (since 2026-05-17)

`purge_shadowing_editable_finders` fixes the *structural* shadow root. A
distinct, narrower leak class survives it: the seed keeps a handful of
**process-global singletons** a product test can mutate — directly, or via an
interleaved session-wide re-purge that swaps a module object out from under
cached `app.*` imports. With no per-test restoration the mutation leaks
forward and an unrelated later test fails — green in isolation, red in a full
directory run, often only under `pytest-randomly`. The social-wiring
absorption hit this **three times** (N≥3 → MUST formalize): consent
`_CATALOG`, consent module bound deps (`bind_consent_module_to_mock`), the
seed APScheduler jobstore, and the consent/scheduler `sys.modules` identities.

`noctusai_lib.testing.seed_singleton_guard` (in
`noctusai_lib/testing/seed_singleton_guard.py`) is that pattern lifted to the
seed: an **autouse snapshot/restore fixture** built declaratively over a list
of `SingletonSpec` value objects. `DEFAULT_SPECS` encodes exactly the
diagnosed surface; the snapshot is **lazy** (a no-op until the product app is
imported and the singletons populated — inert in seed-lib's own / mcp suites).
It restores **before** yield (a test after an interleaved re-purge starts
clean) and **after** yield (a mutating test cannot leak forward).

**Adoption recipe — one line in a product conftest (autouse via re-export):**
```python
from noctusai_lib.testing import seed_singleton_guard  # noqa: F401
```

**Adding a product-specific process-global to the guarded set:**
```python
from noctusai_lib.testing import SingletonSpec, make_seed_singleton_guard

seed_singleton_guard = make_seed_singleton_guard(extra_specs=[
    SingletonSpec("app.some_module", attr="_CACHE", kind="dict"),
])
```
The seed surface is always covered; `extra_specs` is purely additive and the
product spec stays in the product's own conftest — **no per-product code lands
in the seed**. `SingletonSpec.kind` ∈ `{dict, attr, module_identity,
scheduler_jobs}` (`attr=None` ⇒ guards module-object identity). Non-fixture
callers use the `guarded_seed_singletons(...)` context manager. The ad-hoc
guard formerly in `products/social-wiring/backend/tests/modules/conftest.py`
is the lifted source; products inherit isolation instead of re-finding it.

### Schema validation (default-on since 2026-04-24)

`MockSupabaseClient` now validates column references against the migration-file schema by default. Every `.eq("col", ...)` / `.in_("col", ...)` / `.select("c1,c2")` / `.insert({col: val})` consults the parsed schema from `products/*/backend/migrations/*.sql` and raises `MockSchemaError` when a column doesn't exist on the bound table.

This closes the silent-fail class that shipped the compliance-audit bug (wrong `session_id` / `therapist_id` filters on `therapy.session_summary_versions`).

**Error shape:**
```
MockSchemaError: therapy.session_summary_versions has no column 'session_id' (called via eq).
Valid columns: created_at, id, key_points, observation_snapshot_ids, session_record_id,
source, summary, tags, track, version_number.
```

**Construction knobs:**
```python
# Default — validates against public schema
mock = MockSupabaseClient()

# Product-bound — validates against product schema (therapy, erp, etc.)
mock = MockSupabaseClient(schema="therapy")

# Opt-out (REQUIRES rationale comment near the call — keeper detector enforces)
# Example: known schema drift pending its own reconciliation project.
mock = MockSupabaseClient(validate_schema=False, schema="erp")

# STRICT mode (Tier 1.5 G4, 2026-04-24) — opt-in for products whose schema-drift
# reconciliation has finished. Unknown-table queries raise MockUnknownTableError
# instead of WARN+skip. Closes the second silent-fail vector: an agent adding
# a `.from_("typoed_table")` or a brand-new table without a migration file gets
# caught at test time.
mock = MockSupabaseClient(validate_schema=True, strict_unknown_tables=True, schema="<product>")
```

**Opt-out guardrail.** The keeper `check_mock_schema_validation` detector flags any `validate_schema=False` site that has no nearby rationale keyword (`schema-drift`, `reconciliation`, `follow-up`, `TODO`). Put the rationale inside the module docstring or in a `#` comment above the line.

**Bypass for complex PostgREST expressions.** The validator bails (returns silently) on:
- `.select("*, products(*)")` style joined selects (any `(` or `!` in the expression)
- `.or_("status.eq.a,tier.gte.3")` PostgREST OR expressions
- Unknown tables (not in any migration file) — logged as WARNING, not raised (Q4 of the mock-supabase project)

**Known opt-outs** (expected to flip back once their reconciliation project ships):
- `therapy-platform` — ~20 drifts tracked by `products/therapy-platform/projects/therapy-audio-lifecycle-schema-reconciliation/`.
- `erp-imobiliario` — 8 drifts tracked by `products/erp-imobiliario/projects/erp-schema-drift-reconciliation/`.

Shipped 2026-04-24 across 4 phases (originating project archived after close). Parser source: `seed/lib/backend/noctusai_lib/testing/migration_parser.py`. Schema cache: `seed/lib/backend/noctusai_lib/testing/_schema_cache.py`. Error class: `seed/lib/backend/noctusai_lib/testing/schema_errors.py`. Keeper detector for silent opt-outs: `mcp/noctusai/tools/compliance.py::check_mock_schema_validation`.

---

## Regression tests in practice

Regression tests pin behavior that **broke once and might break again**. Without one, every fix is a one-shot — the next refactor can silently undo it. With one, the test fails the moment the same shape returns.

**When to write one (the trigger list).** ANY of these mandates a regression test:

1. **A production bug got fixed.** The fix landed; before merging, write a test that fails on the pre-fix code and passes on the fix. Reference the date / incident / project that caught it.
2. **A detector / linter / type-check missed a real case.** The keeper detectors, vitest config checks, schema-validation guards, etc. — when one of them lets a real-world case through (false negative) or fires on a legitimate one (false positive), the case becomes a fixture.
3. **A security issue was patched.** Even if the fix is one line, lock the behavior in. Reference the LGPD / OWASP / CVE class so future readers know why the assertion is shaped that way.
4. **A subtle edge case surfaced during code review or incident postmortem.** "We didn't think of this" is the cheapest signal — capture it before it leaves your head.
5. **A migration / schema change broke a query.** Add the regression test in `tests/regression/test_<table>_schema.py` so future migrations catch the same shape.

**Where to put it (two valid shapes):**

- **Dedicated file in `tests/regression/`** — when the regression spans multiple endpoints/services or doesn't fit naturally in any single existing test file. Filename names the case: `tests/regression/test_postgrest_404_on_single.py`, `tests/regression/test_phase_state_consistency_paused_phase_checkmark.py`. Each file's docstring opens with `"""Regression: <one-line description>. Caught <date> by <project|incident>."""`.
- **Inline `# Regression: ...` docstring** inside the closest existing test class — when the regression cleanly belongs with the surrounding behavior tests. Example from `products/core/backend/tests/routers/test_settings_router.py:173`:
  ```python
  def test_falls_back_to_platform_settings(self, client):
      """Regression: when org_settings has no match, must fall back to platform_settings."""
      ...
  ```
  The `Regression:` keyword is grep-able and tells the next reader "don't delete this even if it looks redundant — there was a reason."

**How to name it:**

- Test function: `test_<short_case>_<expected_behavior>` (e.g. `test_paused_project_with_phase_checkmark_does_not_flag_clean_folder`).
- Comment includes the **date caught** + the **project / incident** + the **wrong behavior that USED to ship** (so future readers understand the assertion's intent).

**Worked examples already in the repo:**

| Test | File | Case |
|---|---|---|
| `test_does_not_flag_paused_with_phase_checkmark_in_narrative` | `mcp/noctusai/tests/test_compliance.py:670` | Detector false-positive caught against `repo-state-consolidation` PROJECT.md (Phase 0 ✅ in narrative ≠ project closed) |
| `test_silent_ok_comment_does_NOT_suppress` | `mcp/noctusai/tests/test_compliance.py:601` | Pins removal of `# silent-ok` escape hatch (user directive 2026-04-28). |
| `test_legacy_logger_warn_alias_recognized` | `mcp/noctusai/tests/test_compliance.py:638` | Detector must recognise `_log.warn(...)` (deprecated stdlib alias) as legitimate logging. Caught in code review. |
| `test_postgrest_handler.py` (entire file) | `products/core/backend/tests/test_postgrest_handler.py` + ERP mirror | Lock `.single() on 0 rows → 404 not 500` after the framework handler was added. |

**Anti-patterns (what kills regression tests):**

- Test name like `test_bug_fix_1` — useless to a future reader.
- No reference to the original incident — the test rots; someone deletes it as dead.
- Asserting the implementation, not the symptom — fragile to refactor; passes by coincidence.

### Regression-test-the-detector — platform-wide methodology

**Every keeper detector ships colocated with a regression test.** A `check_*` function in `mcp/noctusai/tools/compliance.py` that has no matching `Test<CamelCase>` class somewhere under `mcp/noctusai/tests/` is itself a violation, flagged by the detector `check_detector_has_regression_test` (severity `high`).

**Why platform-wide.** Detectors fail silently when they regress — they keep returning the same `score: 100` while missing the case they were supposed to catch. The regression test is the only thing that locks the contract: a future refactor that breaks the detector's true-positive shape (or introduces a false-positive) fails CI immediately. Without it, a real-world miss can ship undetected. This applies to every detector for every product the keeper watches over: existing ones, future ones, and any new product's detectors.

**The contract.** A regression test for a detector must:

1. **Pin at least one true positive** — feed the detector a known-bad shape; assert it flags. The shape should mirror a real-world case the detector exists to catch.
2. **Pin at least one false positive that's NOT flagged** — feed the detector a known-good shape that *looks* similar; assert it returns `[]`. This protects against the detector becoming over-aggressive after a refinement.
3. **Pin the severity** — assert `i["severity"]` matches the documented severity from `KB § 06-AGENTS.md § Detectors`. A silently-downgraded severity is the same as a regression.

**Naming.** The test class name is `Test<CamelCase-of-detector>` (e.g. `check_silent_errors` → `TestCheckSilentErrors`). The detector's case-insensitive matcher accepts both the prefixed (`TestCheckSilentErrors`) and unprefixed (`TestSilentErrors`) shapes, plus acronym-preserving forms (`TestAIFeatureCompleteness`). Any other shape requires an entry in `_DETECTOR_TEST_OVERRIDES` mapping the detector to its test target.

**CI integration.** `check_detector_has_regression_test` runs as part of `check_all_products` (i.e. `mcp/noctusai/cli.py --review` / `--validate`), which the test workflow invokes on every PR via `.github/workflows/test.yml`. A new detector merged without its regression test fails the workflow.

**Worked examples** (each detector → its test class):

| Detector | Test class | Test file |
|---|---|---|
| `check_seed_compliance` | `TestSeedCompliance` | `mcp/noctusai/tests/test_compliance.py` |
| `check_silent_errors` | `TestCheckSilentErrors` | `mcp/noctusai/tests/test_compliance.py` |
| `check_no_self_monkeypatch` | `TestCheckNoSelfMonkeypatch` | `mcp/noctusai/tests/test_compliance.py` |
| `check_phase_state_consistency` | `TestPhaseStateConsistency` | `mcp/noctusai/tests/test_compliance.py` |
| `check_clean_folder_violations` | `TestCheckCleanFolderViolations` | `mcp/noctusai/tests/test_compliance.py` |
| `check_ai_feature_completeness` | `TestAIFeatureCompleteness` | `mcp/noctusai/tests/test_compliance.py` |
| `check_mock_schema_validation` | `TestMockSchemaValidation` | `mcp/noctusai/tests/test_compliance.py` |
| `check_path_references` | (override → `TestFindRefs`) | `mcp/noctusai/tests/test_refs.py` |
| `check_standard_routers_audit` | `TestStandardRoutersAudit` | `mcp/noctusai/tests/test_standard_routers_audit.py` |
| `check_frontend_entrypoint`, `check_out_of_contract_trees` | (overrides) | `mcp/noctusai/tests/test_phase5_detectors.py` |
| `check_config_extends_product_settings` | (override) | `mcp/noctusai/tests/test_config_inheritance.py` |
| `check_frontend_config_paths` | `TestRegexMatching` etc. | `mcp/noctusai/tests/test_frontend_config_paths.py` |
| `check_seed_version_propagation` | (functions, override) | `mcp/noctusai/tests/test_seed_version_propagation.py` |
| `check_detector_has_regression_test` | `TestCheckDetectorHasRegressionTest` | `mcp/noctusai/tests/test_compliance.py` |
| `check_test_status_assertion` | `TestCheckTestStatusAssertion` | `mcp/noctusai/tests/test_test_status_assertion_detector.py` |
| `check_seed_export_membership` | `TestCheckSeedExportMembership` | `mcp/noctusai/tests/test_seed_export_and_slug_set_detectors.py` |
| `check_hardcoded_product_slug_set` | `TestCheckHardcodedProductSlugSet` | `mcp/noctusai/tests/test_seed_export_and_slug_set_detectors.py` |

**Adding a new detector?** The recipe (and the order matters):

1. Write the test class **first**, with a true-positive case and a false-positive case (this is the spec).
2. Implement the `check_*` function in `mcp/noctusai/tools/compliance.py` (or a sibling module) until the test passes.
3. Register the detector in `check_all_products()`.
4. Document it in `KB § 06-AGENTS.md § Detectors` with severity + rationale.
5. Run `mcp/noctusai/cli.py --validate` and confirm the detector contributes `[]` to a clean tree.

If you need to land the detector before the test (rare — usually because the detector emerged from a real-world incident), still write the test in the same commit. The CI gate fails otherwise.

---

## Production-correctness keeper detectors — the three-detector trio

**The trio.** Three keeper detectors flag latent production bugs that pass against `MockSupabase` mocks but fail at runtime against real Supabase. Surfaced 2026-05-10 by Engineer GG's `therapy-platform-wiring` Phase 4 audit (commit `a56a39e`) which discovered an N=12 migration drift case that had been silently green for 7+ days.

| Detector | What it catches | Severity |
|---|---|---|
| `check_unknown_table_references` | `<X>.table("name")` where `name` is not declared by any `CREATE TABLE` in `products/<p>/backend/migrations/*.sql`. MockSupabase WARN+skip returns empty results, production fails. | `warning` |
| `check_function_search_path_pinned` | `CREATE [OR REPLACE] FUNCTION ...` blocks without `SET search_path = ...`. Supabase advisor 0011 flags it; per-function risk analysis is cheaper to skip if a detector enforces. | `warning` |
| `check_admin_endpoint_service_role_bypass` | `get_admin_client().table("T")` (chained or bound-var) where `T` has no `CREATE POLICY "service_role_bypass" ... ON <schema>.T` in migrations. Bypass silently fails. | `warning` |

**The slip pattern.** Tests against `MockSupabase` are HAPPY-PATH biased — the mock answers a query against any table name with an empty result-set (WARN+skip mode, default since 2026-04-24). When code drifts (rename, table never landed, schema typo), the test stays green; production fails the moment a real Supabase responds. The three-detector trio uses migrations + AST as the static oracle to close this gap.

**AST shape — `check_unknown_table_references`.**

- Walks every `.py` under `products/<p>/backend/app/` (excludes tests + migrations + caches).
- Matches any `<expr>.table("X")` call where `"X"` is a `Constant[str]` (skips f-strings + name references — false-positive avoidance).
- Diffs against the unqualified table-name set extracted from `CREATE TABLE [IF NOT EXISTS] [<schema>.]<name>` in every `products/<p>/backend/migrations/*.sql`.
- Allowlists Supabase-managed `auth.users` + core-bootstrap `products` / `organizations` / `user_org_roles` to suppress cross-cutting false positives.
- Short-circuits when the product has no migrations directory.

**Regex shape — `check_function_search_path_pinned`.**

- For each `products/<p>/backend/migrations/*.sql`, finds every `CREATE [OR REPLACE] FUNCTION [<schema>.]<name>(` start.
- Walks forward through the dollar-quoted body (`$tag$ ... $tag$` with any tag, including empty) to find the block's end terminator.
- Asserts `\bSET\s+search_path\b` appears somewhere in the block. Missing → warning.
- Anywhere-in-block placement is accepted (the clause may sit in the function header BEFORE `AS`, or in `WITH (SET ...)` style — match is permissive).

**AST + regex hybrid — `check_admin_endpoint_service_role_bypass`.**

- AST-finds local-variable bindings of `get_admin_client()` return values: `admin_db = get_admin_client()` and `db: SomeType = get_admin_client()`.
- AST-walks every `.table("X")` call; flags those where the receiver is either a bound admin-client variable OR the chained shape `get_admin_client().table("X")`.
- Diffs against the table set extracted by regex from `CREATE POLICY "service_role_bypass" ... ON [<schema>.]<table>` across all migration files.
- Same external-tables allowlist as the unknown-table detector.

**False-positive design.** All three detectors are configured for FALSE NEGATIVES over false positives:

1. Non-`Constant[str]` table arguments are skipped (the detector can't resolve runtime-built strings statically; a dataflow pass would be a much larger lift for marginal gain).
2. Cross-product schema references that legitimately live in another product's migrations would false-flag — accept-with-rationale + comment is the escape.
3. Tables accessed via admin client for cross-tenant reads where RLS is intentionally not bypassed (foreign-key tenant-id enforcement) would false-flag — same accept-with-rationale path.

**Worked example — therapy-platform N=12 drift.** Running the trio against `products/therapy-platform/` on 2026-05-11 surfaces:

```
check_unknown_table_references: 37 issues
  distinct tables flagged: ai_prompt_history, ai_prompt_settings, anamneses,
    clinic_therapist_configs, financial_transactions, goals, notifications,
    reminder_configs, sessions, settings_history, therapeutic_journal,
    therapist_reviews                                    # ← exact GG N=12 + 1
check_function_search_path_pinned: 1 issue
  functions flagged: therapy.gcal_authorization_is_fresh # ← exact GG case
check_admin_endpoint_service_role_bypass: 5 issues
  distinct tables flagged: ai_prompt_history, ai_prompt_settings,
    settings_history
```

The detector catch matches GG's manual audit case-for-case. The detectors close the silent-fail vector that allowed the drift to ship for 7+ days.

**Adopters.** Run on every product; current platform-wide counts (2026-05-11):

| Product | unknown_table | search_path | admin_bypass |
|---|---|---|---|
| adconnect | 0 | 0 | 0 |
| core | 2 | 0 | 149 |
| daily-life | 0 | 0 | 0 |
| dev-team | 0 | 0 | 0 |
| erp-imobiliario | 2 | 9 | 34 |
| imobi-scheduling | 0 | 0 | 0 |
| mailing | 0 | 0 | 18 |
| personal-finance | 0 | 0 | 1 |
| seed | 0 | 0 | 0 |
| therapy-platform | 37 | 1 | 5 |
| youtube-crawler | 0 | 0 | 0 |

The numbers are the to-be-triaged backlog — `cli.py --review` authors proposals per finding for explicit accept/refactor decisions.

**Why warning, not high.** All three findings reflect real production gaps but the false-positive risk is non-zero (cross-product schema references, intentionally-not-bypassed admin reads, functions deliberately relying on caller search_path). `warning` lets the trio surface every candidate without blocking validation gates; the accept-with-rationale path handles the legitimate carve-outs.

---

## Status-code-assertion rule — pin the code, not just the body

**The rule.** Every pytest test method that asserts on response BODY (`<resp>.text`, `<resp>.json()`, `<resp>.content`) MUST also assert on response STATUS CODE (`<resp>.status_code <op> <val>`) **in the same method body**. Body-only assertions can go green for the wrong reason.

**Why — the YouTube Crawler Phase 1 case study.** A router test shipped with this shape:

```python
def test_recipient_without_channel_rejected(self, client):
    resp = client.post("/api/settings/recipients", json={"name": "x"})
    assert "at least one of" in resp.text.lower()
```

The test went green. The endpoint was unusable. What actually happened: the request hit a broken `Depends(get_org_id)` chain demanding `?user=` and `?token=` query params; the response was 422 with TWO error entries — (a) the seed's broken auth dep, and (b) the schema-validation `"at least one of"` error. The substring assertion matched (b). The test passed. The endpoint was structurally broken for any authed traffic.

The substring matched. The status code was `422` (not the expected `422` for the right reason — for the WRONG reason). Without `assert resp.status_code == 422` next to the body assertion, the test author had no signal that the endpoint was answering for the wrong reason. The status-code pin would have caught it (the dep-chain failure changes which path the request takes; the right-reason path returns 422-with-one-error-entry, not 422-with-two).

**The structural fix.** A keeper detector — `check_test_status_assertion` (`mcp/noctusai/tools/noctus/dev/compliance.py`) — flags any test method asserting on response body without a sibling status-code check. Severity `warning`. Surfaces via `noctus.dev.review` and `noctus.dev.validate`.

**What the detector catches:**

```python
# FLAGGED — body-only assertion, no status_code pin
def test_x(client):
    resp = client.get("/api/x")
    assert "ok" in resp.text  # ← could be 500, 403, 422 — we don't know

# FLAGGED — JSON body assertion alone
def test_y(client):
    resp = client.get("/api/y")
    assert resp.json()["name"] == "x"  # ← 200? 201? schema-error 422?

# FLAGGED — content (binary body) assertion alone
def test_z(client):
    resp = client.get("/api/img/1")
    assert b"PNG" in resp.content  # ← could be a 500 HTML error page
```

**What the detector accepts:**

```python
# OK — body + status code, both load-bearing
def test_x(client):
    resp = client.get("/api/x")
    assert resp.status_code == 200
    assert "ok" in resp.text

# OK — any comparison op against status_code satisfies
def test_y(client):
    resp = client.get("/api/y")
    assert resp.status_code in (401, 403)
    assert "unauthorized" in resp.text.lower()

# OK — inequality also counts
def test_z(client):
    resp = client.get("/api/z")
    assert resp.status_code != 500
    assert "data" in resp.json()
```

**Conservative gating — false negatives over false positives.** The detector binds a "response variable" set at method scope: only names assigned from `client.<verb>(...)` (or `await client.<verb>(...)`) on the right side of an assignment count as response vars. Body-attr matches against names NOT in that set are silently skipped. Drops false positives on domain-object attributes that happen to share the name (`digest.text`, `result.content` on a tool-result object, etc.) at the cost of missing tests that use helper-returned responses (`resp = _do_request(client, "/x")`). The latter is an intentional miss — extending the helper to assert status_code internally is a valid pattern, and we'd rather skip than noise.

**Method-scope only.** Helper functions (any name not starting with `test_`) are NOT scanned. A `def _assert_payload(resp)` helper that's missing a status_code check internally won't fire the detector — the tests that CALL it will, but only if they don't pin status code at the call site.

**Cross-product cleanup is per-product.** Pre-existing slips at detector-introduction time were catalogued in `KB § PATTERNS/accept-with-rationale.md` (each entry: file / line / why-accept / revisit-trigger) so the platform-wide scan runs clean. Cleanup belongs to per-product test-maintenance follow-ups.

**Frontend (Vitest) coverage:** OOS today — a follow-up `keeper-test-status-assertion-frontend` project will ship a ts-morph-based variant once the Python detector beds in.

---

## No self-monkeypatching — refactor playbook

`monkeypatch.setattr(<our_module>, "<our_fn>", _noop)` and `patch.object(<our_module>, "<our_fn>", ...)` neuter the very logic the test claims to verify. The keeper detector `check_no_self_monkeypatch` flags these; severity is `warning` while a per-product cleanup is in flight, ratcheting to `high` when each product's count reaches zero.

**The three legitimate patterns** — pick by test shape, not by ease.

### Pattern 1: Dependency Injection (DI) — the default

**When.** The unit under test calls a helper or service that does I/O (DB write, external API, audit-log dispatch). Production callers default to a real client; tests pass a mock.

**Shape.**

```python
# Production code — kwarg defaults to None and resolves at call time
async def process_session_end(
    appointment_id: str,
    db: Any,
    *,
    core_db: Any | None = None,
    transcribe: Callable[..., Awaitable[str]] | None = None,
):
    core_db = core_db or get_core_client()                           # production path
    transcribe_fn = transcribe or transcription_service.assemble_transcript
    transcript = await transcribe_fn(appointment_id, db)
    ...
```

```python
# Test — inject the mock, no patching
async def test_process_session_end_happy_path():
    db = _db_with_grants()
    db.set_table_data("appointments", [SAMPLE_APPOINTMENT])

    async def fake_transcribe(*_a, **_kw):
        return "Transcrição completa."

    result = await ai_pipeline.process_session_end(
        appointment_id="appt-001",
        db=db,
        core_db=db,
        transcribe=fake_transcribe,
    )
    assert "summaries" in result
```

**Why it works.** The production call site never holds onto the mock — the kwarg defaults to None, runtime resolves the real client. Tests inject. Zero patching. Reference adopters: `_resolve_core_db(core_db)` in `products/therapy-platform/backend/app/services/ai_pipeline.py`; `consent-guard-rollout` (DI for `bind_consent_module_to_mock`).

**When NOT to use DI.** If the dependency is reached from 8+ call sites scattered across the codebase, threading a kwarg through all of them is more churn than it's worth. Use Pattern 2 instead.

### Pattern 2: Boundary mock at the import site

**When.** The unit under test calls our service helper which calls an external boundary (LLM API, email provider, payment gateway). Patch the **external** symbol at the import site, not our service helper.

**Shape.**

```python
# Wrong — patches our helper, neuters the test
with patch.object(longitudinal_service, "generate_clinical_longitudinal", ...):
    await ai_pipeline.process_session_end(...)
```

```python
# Right — patches the LLM call inside our helper at the boundary
with patch.object(noctusai_lib.llm, "chat_completion", AsyncMock(return_value=FAKE_LLM_RESPONSE)):
    await ai_pipeline.process_session_end(...)
# Real `generate_clinical_longitudinal` runs; only the LLM round-trip is faked.
```

**Why it works.** The boundary belongs to an external library — patching it is the standard mock pattern, allowed by the rule. Our orchestration logic, our error handling, our consent guards — all execute. The test now actually verifies the chain, not just the call order.

**Patch at the consumer-side import binding, never at the producer-side definition.** The mock target is the consumer module's local symbol — `patch("app.services.X.schedule_coro")` (consumer's `from noctusai_lib.primitives.tasks import schedule_coro` binding), NOT `patch("noctusai_lib.primitives.tasks.schedule_coro")` (producer-side definition). The consumer-side path tracks refactors automatically: rename the seed helper or move it to a different layer, the consumer's import re-binds, and the patch path stays accurate. The producer-side path silently no-ops the moment the consumer's import shape changes — a recurring slip class. *Formalized 2026-05-10 from `projects/schedule-coro-fire-and-forget/` Phase 3 proposal item #3.*

**When NOT to use boundary mocks.** When the inner helper does enough work that running it would require seeding more data than the test scope allows. Then Pattern 3.

### Pattern 3: Seed real data via `MockSupabaseClient`

**When.** The function under test reads from the DB and dispatches based on the data. Don't patch the read — seed the table and let the real read run.

**Shape.**

```python
# Wrong — patches the read function, the test no longer exercises the query logic
with patch.object(consent, "require", return_value=None):
    await ai_pipeline.process_session_end(...)
```

```python
# Right — seed `ai_consent` rows; real `require()` reads the mock and returns silently
db = MockSupabaseClient()
db.set_table_data("ai_consent", [
    {"user_id": "patient-001", "feature_key": "therapy.session_summary",
     "granted": True, "granted_at": "2026-04-27T00:00:00Z", "revoked_at": None},
])
await ai_pipeline.process_session_end(db=db, core_db=db, ...)
# Revocation path: same shape, set granted=False or revoked_at=now()
```

**Why it works.** The mock IS the dependency. Seeding rows is identical in cost to a `patch.object` plus correct setup, and now the test exercises the real consent guard. Reference adopter: `_db_with_grants(...)` helper in `products/therapy-platform/backend/tests/services/test_ai_pipeline_service.py`.

**Side-effect verification:** when the production code writes a notification or audit row, read `mock_sb._tables["notifications"].inserted_payloads` after the call. Public list maintained by every `insert(payload)`. Production code stays untouched. Same product reference.

### Picking the pattern

| Test shape | Pattern |
|---|---|
| Orchestrator unit test (verifies "calls A then B then C") | DI — pass each helper as a kwarg with its real default |
| Service unit test (verifies internal logic of the service) | Boundary mock — patch the external lib at the boundary |
| Router unit test (verifies HTTP-shape behavior, including auth/consent) | Seed real data — let routes hit the real guards |
| Integration test (multi-service flow) | Seed real data + boundary mock for the external calls |
| Edge case / error path | Seed the bad data; let the real validator raise |

### Refactor procedure (per site)

1. Find the `monkeypatch.setattr` or `patch.object` line.
2. Identify the symbol's package: ours (`app.*`, `noctusai_lib.*`, `noctusai_seed.*`) → must refactor; external (`openai.*`, `httpx.*`, `stripe.*`) → already correct, the detector allowlists these.
3. Pick the pattern (table above).
4. Apply: add kwarg / change patch target / seed table.
5. Run the test — confirm green AND that the test still exercises a meaningful failure path (try seeding bad data; the test should fail).
6. Re-run keeper: `mcp/noctusai/.venv/bin/python mcp/noctusai/cli.py --validate` — confirm the count dropped.

### Severity ratchet

Detector severity is `warning` by default because the first run flagged 420 sites and tanking score from 100 → 0 was unhelpful. The ratchet flips a product to `high` once it reaches zero, blocking regression.

| When | Action |
|---|---|
| A product reaches 0 self-monkeypatch warnings | Detector severity flips to `high` for that product. New violations block CI. |
| All products at 0 | Detector severity flips to `high` repo-wide; the `warning` carve-out is removed. |

**Implementation** (2026-05-01): the per-product override lives in `mcp/noctusai/tools/compliance.py` as `_NO_SELF_MONKEYPATCH_HIGH_SEVERITY_PRODUCTS: frozenset[str]`. To ratchet a product, add its folder name to that set + extend the keeper test (`test_severity_high_for_ratcheted_product`). Regression tests in `mcp/noctusai/tests/test_compliance.py::TestCheckNoSelfMonkeypatch` cover both branches.

**Currently ratcheted (`high`):**
- `therapy-platform` — 115 → 0 (closed 2026-05-01 via `projects/keeper-warning-triage` Phase 1: pilot pattern-1 DI in `test_ai_pipeline_service.py`, pattern-3 seed-real-data sweep in `test_messaging_router.py`, and Wave C digest absorption side-effect on the remaining service tails).

**Still draining (`warning`):** `erp-imobiliario` (96), `core` (44), `mailing` (18), `personal-finance` (16), `daily-life` (11), `<seed-lib>` (8). Per-product follow-up project slugs: `<product>-tests-no-self-patch` (filed when picked up). Pilot proof + cleanup status lives in `projects/keeper-warning-triage/PROJECT.md` §6.

**Pilot result (2026-04-28).** `products/therapy-platform/backend/app/services/ai_pipeline.py` introduced a `_PipelineHooks` dataclass with the 5 helper functions as fields; production callers omit `hooks=` and resolve to `_DEFAULT_HOOKS` (real services). `tests/services/test_ai_pipeline_service.py` migrated `TestProcessSessionEnd` (8 tests) + `TestPatientConsentGuards.{test_session_summary_consent_revoked, test_longitudinal_consent_revoked}` (2 tests) from `patch.object(<our_module>, ...)` to a `_hooks(...)` factory that returns `_PipelineHooks(transcribe=AsyncMock(...), summarize=AsyncMock(...), ...)`. 33 sites cleared (43 → 10 in that file; 315 → 282 platform-wide). All 17 tests in the file pass; real consent guards execute end-to-end; revoked-feature paths verified via `hooks.<helper>.assert_not_awaited()`.

---

## Coverage gaps + ratchet plan

The "five layers" table at the top is the **target shape** every product should reach. Today, coverage is uneven. This section is the inventory + ratchet plan — open it before adding new tests so you know the highest-leverage gap to fill.

### Backend coverage

| Tier | Status | Gap |
|---|---|---|
| Unit (routers + services) | ✅ Universal | Self-monkeypatch debt being cleaned per `§ No self-monkeypatching — refactor playbook` (315 → 282 as of 2026-04-28 pilot). |
| Integration | ✅ Universal | Healthy — only 7 self-monkeypatch hits across all integration tests platform-wide. |
| E2E (`tests/integration/test_e2e_flows.py`) | ⚠️ Partial | ERP only. Other products: TBD. |
| Regression | ⚠️ Partial — see `§ Regression tests in practice` | No `tests/regression/` dir anywhere yet; informal regressions live in `test_postgrest_handler.py` (core + ERP) + inline `# Regression: ...` docstrings (`test_settings_router.py`, `test_dimob_router.py`, `test_dimob_service.py`). Convention: prefer the dedicated dir for new ones. |
| `tests/realdb/` (real-DB integration) | ⚠️ 3/7 products | Adopters: `core`, `erp-imobiliario`, `personal-finance` — each has a `realdb/` dir with `pytest.mark.realdb` marker, auto-skipped when `SUPABASE_URL`/`SUPABASE_SERVICE_ROLE_KEY` are unset. Missing: `therapy-platform`, `mailing`, `daily-life`, `adconnect`. RLS regressions in those 4 products are caught only at deploy time. |
| Mutation / property-based | ❌ 0/7 | No `hypothesis`, no `pytest-property`, no mutation-test harness anywhere. |

### Frontend coverage

| Tier | Status | Gap |
|---|---|---|
| Hook tests (`*.test.ts` via vitest) | ⚠️ 4/7 products with **just useAI** | Each adopter has exactly one test file (`useAI.test.ts`) with 4-8 `it()` cases. Adopters: erp-imobiliario, mailing, personal-finance, daily-life. **Zero tests in therapy-platform, core, adconnect** — vitest harness is wired but no specs. `npx vitest run` exits 1 ("No test files found") which is the honest signal. |
| Component tests | ❌ 0/7 | No component-level vitest specs anywhere — only the AI hook is tested. |
| Page tests | ❌ 0/7 | Pages are exercised only via Playwright (where it exists) — see next row. |
| Playwright E2E | ⚠️ 2/7 wired, **0 specs** | `playwright.config.ts` exists in core + erp-imobiliario frontends. **Neither has any actual `*.spec.ts` files** — the dependency is dormant. Other 5 products: not even wired. |
| **Boundary-contract tests** (added 2026-05-20) | ⚠️ 2/5 boundaries covered | Named class for "tests-green-dashboard-red" bugs — full spec at `KB § PATTERNS/boundary-contract-tests.md`. **B1** build-injection (vite `define` → bundle literals) — ✅ covered at source by `check_seed_canonical_default`; bundle-side assertion still open. **B2** HTTP schema (FE↔BE cap drift e.g. `le=20`-vs-top-50) — ❌ accept-w/-destination, file `<product>-fe-be-schema-contract` on N=2. **B3** third-party library contract (TanStack v5 `queryFn` return-type) — ✅ Stage-4 `check_query_fn_returns_undefined`. **B4** container env propagation (`.env`→stage→runtime) — ❌ accept-w/-destination, file `smoke-fleet-env-propagation` on N=2 (manual `KB § PATTERNS/containerization.md § 12b` today). **B5** library-default propagation (seed default → N consumers) — ✅ same detector as B1. Authoring-time discipline: every PR adds a "if this contract drifts, what existing test fails?" line per touched seam. |

### Ratchet plan (filling each gap)

Each row below names a follow-up project slug + its trigger to start. **No project here is in flight today** (2026-04-28); they're in the queue.

| Gap | Trigger | Follow-up project |
|---|---|---|
| Frontend hook tests in therapy / core / adconnect | When a product first ships a hook that does I/O (mutation / query) | `<product>-frontend-hook-coverage` |
| Frontend component tests | When N=2 products have a duplicated component bug | `frontend-component-test-pattern` (seed-level — define the pattern, then per-product adoption) |
| Frontend Playwright specs in core + ERP | When a flow goes user-facing (signup, billing, cross-product navigation) | `<product>-playwright-golden-paths` |
| `tests/realdb/` in the 4 missing products | When a product's first RLS-shaped bug ships to prod | `<product>-realdb-rls` |
| Mutation / property-based testing | When a product's bug class is "happy-path tests pass but edge values break it" — typically math-heavy services (PF, ERP metas) | `mutation-test-pilot` (one product, one service, prove the pattern) |
| Self-monkeypatch debt | Per-product cleanup; ratchet detector severity to `high` when count = 0 | `<product>-tests-no-self-patch` |
| B4 row-seeding (only therapy uses it) | When a product's autouse-fixture pattern misses a consent-revocation path | per-product, no umbrella project — small refactor |
| Boundary-contract tests — open boundaries (B2 HTTP schema, B4 container env) | N=2 surfacing of the same shape (per `KB § PATTERNS/boundary-contract-tests.md` recurrence rule) | `<product>-fe-be-schema-contract` (B2) / `smoke-fleet-env-propagation` (B4) |

**Anti-pattern to avoid:** filing a "frontend test coverage" umbrella project that tries to fix every gap at once. Each gap above has a different trigger and a different shape; bundling them produces a project no one finishes. Pick by trigger, not by aspiration.

**Where to track real status:** filename `mcp/noctusai/cli.py --status` will list active projects + flags; this section names what *should* exist, not what does. The section gets updated when a follow-up project ships.

---

## Seed-layer test harnesses

Two infrastructure-level test suites verify the framework itself, independent of any product:

| Layer | Where | Runner | What it covers |
|---|---|---|---|
| Backend framework (`noctusai_seed`) | `seed/framework/backend/tests/` | `pytest` | `build_standard_routers` registry, opt-in resolution, factory shape. Pure-Python, no DB. |
| Frontend framework (`@noctusai/seed`) | `seed/framework/frontend/tests/` | `vitest` (jsdom) | `createProductApp` auth-branch selection (supabase vs custom `authProvider`), route topology (`unauthRedirect`, conditional `/sso` mount), error guard when neither auth path is provided. |
| Shared library (`noctusai_lib`) | `seed/lib/backend/tests/` | `pytest` | Pure-function helpers: notifications mapper, etc. |

### Running

```bash
cd seed/framework/backend && pytest tests/ -q
cd seed/lib/backend       && pytest tests/ -q
cd seed/framework/frontend && npm test
```

### Frontend harness notes

The frontend harness installs its own `node_modules` (mirrors the `@noctusai/lib` pattern — `peerDependencies` for consumer deps, `devDependencies` for test tooling). It stubs `@noctusai/lib/design-system` at the test boundary (alias in `vitest.config.ts`) because the real design-system's transitive graph (lucide-react + radix-ui + …) isn't installed at this level and isn't needed for framework-logic tests. A test that genuinely needs to render a design-system component should override the alias via `vi.doMock` for that file.

### Consent-guard product conftest pattern (default for every product, 2026-04-27)

Products that use `noctusai_seed.create_product_app(...)` automatically get the X6 consent module wired at boot via `configure_consent_module(get_current_user=deps.get_current_user, admin_client_factory=db.get_admin_client)` (when `settings.consent_gating != False`, the default). **This wire-once-at-boot behavior interacts badly with `TestClient` caching** — every product's test conftest needs a per-fixture re-bind so consent guards query the test's mock supabase instead of the FIRST fixture's mock.

#### The boot-order trap (the *why* — preserve this rationale)

1. `TestClient(app)` imports `app.main` once per test process. Python caches the module.
2. `app.main` calls `create_product_app(...)` which calls `configure_consent_module(get_current_user, admin_client_factory)` — the factories are **bound references** captured at boot time.
3. Pytest's `client` fixture creates a NEW `MockSupabaseClient` per test, patches `noctusai_seed.database.DatabaseModule.get_admin_client` to return it, then yields the test client.
4. **Problem:** the consent module's stored `admin_client_factory` was captured during the FIRST fixture's patch context. Subsequent fixtures get new mocks, but the consent dep still queries the FIRST mock_sb. Consent guard tests after the first one read stale data → revoked rows aren't seen → false-pass test.

This was caught during `consent-guard-rollout` Phase 2 (Mailing) when `test_segment_contacts_returns_412_when_user_revoked_consent` failed with 404 instead of 412 — the revoke seed wasn't reaching the consent dep.

#### The fix — `bind_consent_module_to_mock(mock_sb)`

`noctusai_lib.testing.bind_consent_module_to_mock(mock_sb)` is the per-fixture rewire helper. Call it inside the `client` fixture, after `from app.main import app` (so app boot has run) and before `TestClient(app)`. Idempotent — safe to call repeatedly.

```python
# canonical conftest shape — copy this into every product's tests/conftest.py
from noctusai_lib.testing import (
    MockSupabaseClient, MockUser, MockUserResponse, AuthClient,
    bind_consent_module_to_mock,
)

@pytest.fixture
def client():
    mock_sb = MockSupabaseClient(...)
    mock_sb.auth.get_user = MagicMock(return_value=MockUserResponse(MockUser(...)))
    with patch("noctusai_seed.database.DatabaseModule.get_admin_client", return_value=mock_sb), \
         patch("noctusai_seed.database.DatabaseModule.get_client", return_value=mock_sb):
        from app.main import app
        bind_consent_module_to_mock(mock_sb)  # ← always present, default-on
        tc = TestClient(app)
        yield AuthClient(tc, mock_sb)
```

**When to add it:** every product that imports `noctusai_seed.create_product_app(...)` should call it — even if the product currently registers zero consent features. The helper is idempotent (no-op if catalog is empty), and adding it preemptively means the day a product first registers a consent feature, no one has to remember to wire the conftest.

**Reference adopters (2026-04-27):** mailing, ERP, daily-life, personal-finance. The scaffold template `templates/product-seed/backend/tests/conftest.py` ships the call by default — every new product inherits it from day one.

**Default-False / default-True product test pattern.** When a product has features with `default_granted=False` (high-risk: clinical, personal narrative, financial diary), pre-existing happy-path tests fail with 412 because there's no stored grant. Use an autouse fixture in the AI router's test file to seed grants:

```python
@pytest.fixture(autouse=True)
def _grant_all_<product>_consents(client):
    client._mock_supabase.set_table_data("ai_consent", [
        {"feature_key": "<product>.<feature>", "granted": True,
         "user_id": "test-user-123",
         "granted_at": "2026-04-27T00:00:00Z", "revoked_at": None},
        # ... one row per feature
    ])
```

The `TestConsentGuards` class at the end of the file then overrides this seed (calls `set_table_data("ai_consent", [<revoked-row>])`) to test 412 paths. Pattern adopters: daily-life, personal-finance.

**Service-layer guards — same row-seeding pattern, no patching (Therapy, 2026-04-27).** When guards live at the service layer (`ai_pipeline.require(...)` called from background tasks instead of router deps), still seed `ai_consent` rows — never patch `require`. The CLAUDE.md "no monkeypatches" rule applies to test code: if a test patches your own consent guard with a no-op so the rest of the run continues, the test is no longer exercising the consent guard. Use a small helper that builds the mock with the right consent state:

```python
# Catalog is auto-loaded by `noctusai_lib.testing.pytest_plugin` at session
# start (probes `app.main`, imports it, which triggers the framework's
# `create_product_app(consent_features=...)`). No per-test-file import needed.

THERAPY_FEATURES = ("therapy.session_summary", "therapy.longitudinal_narrative")

def _db_with_grants(*, patient_id="patient-001", revoked=None):
    revoked_set = set(revoked or [])
    rows = [{
        "user_id": patient_id,
        "feature_key": f,
        "granted": f not in revoked_set,
        "granted_at": "2026-04-27T00:00:00Z" if f not in revoked_set else None,
        "revoked_at": None if f not in revoked_set else "2026-04-27T00:00:00Z",
    } for f in THERAPY_FEATURES]
    db = MockSupabaseClient()
    db.set_table_data("ai_consent", rows)
    return db
```

Happy-path tests do `db = _db_with_grants()` (default = all granted, real `require()` returns silently). Revocation tests do `db = _db_with_grants(revoked=["therapy.session_summary"])` and let the real guard raise — exercising the actual fallback path.

**Side-effect verification via `inserted_payloads` (no patching).** When the service writes a notification or audit row, pass the same mock as both `db` and `core_db` (proper DI — production callers default to `get_core_client()`, tests inject the mock):

```python
result = await ai_pipeline.process_session_end(..., db=db, core_db=db)

# Read back what the helper actually inserted — no patching of the helper.
notifs = db._tables["notifications"].inserted_payloads
assert len(notifs) == 1
assert notifs[0]["metadata"]["feature_key"] == "therapy.session_summary"
```

`MockRequestBuilder.inserted_payloads` is a public list maintained by every `insert(payload)` call (added to seed-lib 2026-04-27). List-payloads are flattened. **Production code stays untouched** — tests verify the real helper ran by reading what it wrote. Reference adopter: therapy-platform `tests/services/test_ai_pipeline_service.py::TestPatientConsentGuards`.

**The same pattern applies to seed-side Real adapter tests.** When a seed module ships a `RealSupabase<X>Repository` (per `KB § PATTERNS/seed-fake-real-adapter.md`), the Real-adapter tests use `MockSupabaseClient` exactly like product-service tests do — `inserted_payloads` for inserts, `updated_payloads` for updates, `set_rpc_data(rpc_name, return_value)` for RPC stubbing, `set_table_data(table, rows)` for select fixtures. The Real adapter is verified end-to-end (table name, schema, query shape, payload mapping) without a single monkey-patch on our own code. Reference: `seed/lib/backend/tests/test_jobs.py::TestRealSupabaseJobRepository` (added 2026-05-04 in `seed-hardening-from-youtube-crawler` Phase 2.1+2.2 by Engineer D; reused by Engineer H in Phase 3.2 for `test_storage.py::TestSupabaseStorageBackend`). Pattern shape: `mock = MockSupabaseClient(); repo = Real<X>Repository(mock, schema_name="public"); await repo.<method>(...); assert mock._tables["<table>"].inserted_payloads == [...]`. Zero monkey-patching of any seed code.

**When to add `core_db` (or any other dependency) as an optional kwarg to a pipeline function.** Default to `None` and lazily resolve via `get_core_client()` when the function actually needs it (the resolve-helper pattern). Production paths keep working without code changes; tests inject the same mock so write side-effects land in a place the test can read. This is **dependency injection**, not patching — the production call site never holds onto the mock; the kwarg defaults to None and the runtime resolves to the real client. Reference: `_resolve_core_db(core_db)` in `products/therapy-platform/backend/app/services/ai_pipeline.py`.

### Framework-test inheritance suites (2026-05-10)

`noctusai_lib.testing.framework_test_suites` exposes 8 base classes that products inherit instead of copy-pasting framework-test code. Before 2026-05-10, every product carried ~30 LOC of identical assertion classes (`TestHealthCheck`, `TestRemoveMember`, `TestAuthBoundary`, etc.) testing seed-framework code; when the framework changed, all 7 adopters needed updating in lockstep.

**Available suites** (8 total, 31 inherited tests):

| Suite | Tests | Covers |
|---|---|---|
| `HealthCheckSuite` | 1 | `/api/health` shape (`status` / `product` / `version`) |
| `TeamRouterListMembersSuite` | 2 | `GET /api/team/membros` listing |
| `TeamRouterInviteSuite` | 1 | `POST /api/team/convites` |
| `TeamRouterRemoveMemberSuite` | 2 | `DELETE /api/team/membros/{id}` |
| `FrameworkEndpointsSuite` | 10 | All `standard_routers` endpoints exist + respond |
| `TeamFlowSuite` | 2 | Integration: invite → accept → list |
| `NotificationFlowSuite` | 4 | Notification proxy + count endpoints |
| `AuthBoundarySuite` | 9 | Integration: unauth'd → 401 across product endpoints |

**Adopter shape:**
```python
# products/<x>/backend/tests/routers/test_health.py
from noctusai_lib.testing import HealthCheckSuite

class TestHealthCheck(HealthCheckSuite):
    expected_product_name = "<X>"
    # rest is inherited
```

Pytest collects `test_*` methods on any `Test*` class regardless of base. Class attrs on the subclass shadow base defaults at lookup time. The `client` fixture is consumed by name from each adopter's `conftest.py` — suites in `noctusai_lib` don't redefine it.

**Adopters (5 products, ~12 test files refactored):** adconnect, daily-life, mailing, seed, youtube-crawler. Net: −848 LOC product test code, +316 LOC seed-lib (historical — media-scheduling was a 6th adopter; the product was deleted 2026-05-11 in favor of `imobi-scheduling` which consolidates the same WhatsApp/Calendar/Maps scheduling surface).

**The N=4 byte-identical lesson.** The audit flagged `TestRemoveMember` recurring in 7 products — but reading bodies showed only 4 are byte-identical (adconnect / media-scheduling / seed / youtube-crawler). Core / daily-life / erp-imobiliario have **divergent rich tests** using `admin_client` to exercise real business logic (self-removal rejection, role-promotion guards). Those stayed untouched — they're independent test artifacts that share a label, NOT duplicates waiting to be unified. **Content-diff before deciding "this is a duplicate."** (Historical — media-scheduling was deleted 2026-05-11; the byte-identical-4 count at the time of the lesson stands as recorded.)

**Anti-patterns:**
- Hand-writing `TestHealthCheck` inline instead of inheriting `HealthCheckSuite` — seed framework changes will silently miss your tests
- Overriding more than `expected_*` class attrs — if you need to override a test method, the suite's contract is wrong; surface as a finding
- Treating scan-tool helper-name signals as absorption commands — content-diff first, then decide

→ Source: `seed/lib/backend/noctusai_lib/testing/framework_test_suites.py`

### Per-product frontend hook tests (seed-scoped factory, 2026-04-27)

Every product frontend at `products/<X>/frontend/` ships with a 3-line `vitest.config.ts` that delegates to **`createProductVitestConfig`** at `seed/framework/frontend/vitest.config.factory.ts` — the seed-scoped factory absorbing the canonical config. This is the same skeleton/organ pattern as `createViteConfig` (sibling factory at `vite.config.factory.ts`); changes to the canonical shape land once in seed and propagate to every product at install time. Adopters: erp, mailing, daily-life, personal-finance, therapy-platform, core, adconnect. Seed reference product (`products/seed/`) is intentionally NOT in this list — it's a scaffolding template, not a consumer.

**Canonical config shape** (3 lines, copy verbatim — no per-product mutation):

```ts
// products/<X>/frontend/vitest.config.ts
import { createProductVitestConfig } from "../../../seed/framework/frontend/vitest.config.factory";
export default createProductVitestConfig();
```

The factory provides `globals: true`, `environment: 'jsdom'`, the e2e exclude (keeps Playwright out of vitest's collection), and four seed-scope aliases (`@`, `@noctusai/lib`, `@noctusai/seed`, `@noctusai/seed/infra`). Override hooks for advanced needs:

```ts
export default createProductVitestConfig({
  excludeExtra: ["custom-glob/**"],
  aliasExtra: { "@my-pkg": path.resolve(__dirname, "./libs/my-pkg") },
  environment: "happy-dom",
  extend: (cfg) => ({ ...cfg, /* last-mile mutation */ }),
});
```

The factory itself is tested at `seed/framework/frontend/tests/createProductVitestConfig.test.ts` (6 tests covering defaults + each override knob).

**Required devDependencies** in each product's `package.json`: `vitest`, `@testing-library/react`, `@testing-library/jest-dom`, `jsdom`.

**Required scripts**: `"test": "vitest run"`, `"test:watch": "vitest"`.

**Canonical hook-test pattern** (mirrors `products/erp-imobiliario/frontend/src/hooks/__tests__/useAI.test.ts`):

```ts
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

const mockPost = vi.fn();
vi.mock('@noctusai/seed/infra', () => ({ api: { post: mockPost } }));
// Some hooks toast on error — products that import sonner add this:
vi.mock('sonner', () => ({ toast: { error: vi.fn(), success: vi.fn() } }));

function withQueryClient() {
  const client = new QueryClient({
    defaultOptions: { mutations: { retry: false }, queries: { retry: false } },
  });
  return ({ children }: { children: React.ReactNode }) =>
    React.createElement(QueryClientProvider, { client }, children);
}

describe('useFoo', () => {
  beforeEach(() => vi.clearAllMocks());

  it('posts to /api/foo and parses response', async () => {
    mockPost.mockResolvedValue({ data: { ok: true } });
    const { useFoo } = await import('@/hooks/useFoo');
    const { result } = renderHook(() => useFoo(), { wrapper: withQueryClient() });

    result.current.mutate({ id: 'x' });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(mockPost).toHaveBeenCalledWith('/api/foo', { id: 'x' });
  });
});
```

**Pattern rules:**
1. **Mock at the `@noctusai/seed/infra` boundary, not at the network.** This decouples hook tests from Vite/jsdom HTTP plumbing.
2. **Use dynamic `await import('@/hooks/...')` AFTER `vi.mock`** so the mock binds before the hook module evaluates `import { api } from '@noctusai/seed/infra'`.
3. **Each hook gets its own `it(...)`** — no shared mock state across hooks.
4. **No `passWithNoTests`** in any vitest config. A product with vitest configured should have at least one test; until tests land, `npx vitest run` exits with code 1 ("No test files found"), which is the honest signal.

**Adopter status (2026-04-27):**

| Product | Hook tests today | Source |
|---|---|---|
| erp-imobiliario | 4 | ai-expansion Tier 1.5 G2 (2026-04-24) |
| mailing | 8 | `frontend-test-harness` Phase 4 (2026-04-27) — Phase 8 M3 + Phase 14 M1/M2/M5/M6/M7 |
| daily-life | 5 | `frontend-test-harness` Phase 4 (2026-04-27) — Phase 11 D6 + Phase 13 D1 + Phase 16 D4 |
| personal-finance | 4 | `frontend-test-harness` Phase 4 (2026-04-27) — Phase 7 P1/P3-opp + Phase 10 P2-opp |
| therapy-platform | 0 (harness ready) | n/a — no AI-hook G2 backlog at rollout time |
| core | 0 (harness ready) | n/a |
| adconnect | 0 (harness ready) | n/a — product not built |

---

## Test-isolation pollution detection (since 2026-05-11)

**Symptom:** a test passes in isolation but fails when the full suite is run. The classic shape of mutable-shared-state leakage across tests — a *polluter test* mutates state that the *polluted test* reads, with the polluter being upstream in the test-collection order.

**Hallmark check (every triage):**
```bash
# 1. Full-suite failure (reproduces the manifestation)
pytest products/<product>/backend/ -q
# 2. Isolation pass (confirms not a genuine logic bug)
pytest products/<product>/backend/tests/path/to/test::ClassName::test_method -q
# 3. pytest-randomly amplification (if step-2 passes but step-1 fails)
pytest -p randomly --randomly-seed=<N> products/<product>/backend/ -q   # vary N
```

If steps 1 + 2 both fail in the same way → **genuine logic/test bug** (file as separate follow-up). If 1 fails + 2 passes → **isolation pollution** (continue below).

**Common polluter shapes (NoctusAI catalog):**

1. **Module-level mutable fixture dicts (the dominant shape — 2026-05-11).** Tests define `SAMPLE_X = {...}` at module top, then pass `SAMPLE_X` (or `[SAMPLE_X]`) into `MockSupabaseClient.set_table_data(...)`. When the service under test calls `db.table(t).update({...}).eq(...).execute()`, the mock's write-propagation feature mutates the row **in place via `dict.update`** — and that "row" is *the same dict object as `SAMPLE_X`*. Subsequent tests reading `SAMPLE_X` see polluted state. Cured at the polluter source (the seed mock) by deep-copying rows at `MockRequestBuilder.__init__` time, so the shared list within one builder propagates writes (preserves the 2026-05-10 feature) but the caller's input dicts stay pristine. Therapy 4F-set (2026-05-10) was this exact shape; isolation closed by `seed/lib/backend/noctusai_lib/testing/mocks.py` deep-copy guard.

2. **Autouse fixture without teardown.** `@pytest.fixture(autouse=True)` that *sets* but never *resets* module-level state (settings, registries, global counters).

3. **Module-level singleton with lazy init.** First test triggers init with state X; later tests inherit that init even when they want state Y.

4. **`@functools.lru_cache` on test-touching helpers.** Cache key collisions across test runs leak prior-test results.

**Detection recipe — bisecting the polluter:**

```bash
pip install pytest-randomly                            # one-time setup
pytest -p randomly --randomly-seed=42 ... | tee /tmp/order
# Each random seed produces a different ordering; one will fail, others may pass.
# When a failing seed is found, half-split the test list:
pytest -p no:randomly first_half ... target_test       # bisect downward
pytest -p no:randomly second_half ... target_test
# Once the polluter test is identified, instrument it: print/inspect the shared
# object it mutates (e.g. `print(id(SAMPLE_X), SAMPLE_X)` before and after).
```

**Fix at the polluter source, not the polluted test.** Adding `setup_method` cleanup to the failing test is a workaround — it patches the symptom. The fix lives where the mutable state leaks (the polluter or the mutation primitive). For shape #1, the mutation primitive (the mock) gets the deep-copy guard; for shapes #2-4, the fixture/cache/singleton gets a teardown or `clear()` call in its scope.

**Anti-pattern:** treating every full-suite failure as a "test ordering bug to mark `xfail`." If the failure manifests with shared state and disappears in isolation, dig — *the polluter is the methodology gap*.

---

See also:
- `../06-AGENTS.md` — the MCP heal loop runs tests automatically
- `../../INSTRUCTIONS/05-TESTING-EVALS.md` — eval strategy (beyond unit/integration)
