# Test harness playbook — how to build, run and debug the house test harness

> **What it is.** The HOW-TO half of testing at NoctusAI: the seed test kit
> (`noctusai_lib.testing`), the mock PostgREST client and its schema/CHECK validation,
> fixtures, real-database tiers (opt-in Supabase branch, PGlite), framework-test suites,
> the frontend vitest factory, running suites, and the harness gotchas that cost us a red.
> Owned by `test-engineer` (`.claude/agents/test-engineer.md`).
>
> **What it is not.** The POLICY — which layers every product must have, the no-self-patch
> rule and its gates, the status-code and strict-401 rules, the regression-test contract,
> the keeper trio, coverage gaps — stays in `KB § PATTERNS/compliance/testing.md`
> (compliance-owned). The craft — strategy per layer, doubles taxonomy, property and
> mutation testing, flaky policy, smells — is `KB § PATTERNS/compliance/test-engineering-canon.md`.
> Review-side judgement is `KB § PATTERNS/compliance/code-review-craft.md §6–§8`.
>
> **Provenance (lossless split, 2026-11-05).** §1–§3 and §5–§7 below were MOVED verbatim
> from `testing.md` (its `## Running`, `## Mock helpers` incl. the schema-validation and
> CHECK-constraint mechanics, `## Seed-layer test harnesses`, `## Test-isolation pollution
> detection`, `## TS outline-corpus baseline` sections) per
> `KB § PATTERNS/common/lossless-doc-refactor.md`; `testing.md` keeps a redirect table naming
> each moved heading. Moved headings keep their original text so old `§` references
> still find them. Sections marked *(added 2026-11-05)* are new, grounded in the files they cite.
>
> **Section map** (moved headings keep their original, unnumbered text): §0 kit at a glance ·
> §1 = `## Running` · §2 = `## Mock helpers` · §3 = `### Schema validation` + `### CHECK constraints` ·
> §4 real-database tiers · §5 = `## Seed-layer test harnesses` (consent conftest, framework suites,
> frontend vitest factory) · §6 = `## Test-isolation pollution detection` · §7 = `## TS outline-corpus
> baseline` · §8 environment the suite owns · §9 gotchas index.

## 0 · The kit at a glance *(added 2026-11-05)*

| You need | Use | Where |
|---|---|---|
| A PostgREST double that refuses unknown columns/tables and CHECK violations | `MockSupabaseClient(schema=...)` | `seed/lib/backend/noctusai_lib/testing/mocks.py:1934` |
| Rows to read | `set_table_data(table, rows)` · sequenced replies `set_sequential_responses` · RPC replies `set_rpc_data` | `mocks.py:2109`, `:2118`, `:2160` |
| What the code WROTE | `db.table(t).inserted_payloads` / `updated_payloads` (upserts mirrored) | `mocks.py:1502-1545` |
| An authed client / a different role | `AuthClient` + `bind_user_metadata(client, role=..., org_id=...)` | §2 |
| Owner ids in fixture rows | `TEST_USER_ID` / `TEST_ORG_ID` — never a typed literal | §2 |
| Consent guards that see this test's mock | `bind_consent_module_to_mock(mock_sb)` | §5 |
| Framework endpoints tested once, inherited everywhere | `HealthCheckSuite` … `AuthBoundarySuite` | §5 |
| Error-body and edge-status assertions | `assert_error_contains`, `handler_status` (502/504 behind `EdgeSafeStatusMiddleware`) | `testing/assertions.py:12`, `:42` |
| A migration by name, not number | `migration_path` / `migration_sql` | `testing/migrations.py:40`, `:57` |
| Env the suite owns (never `setdefault`) | `own_test_env({...}, clear=(...))` | `testing/conftest_helpers.py:206` · §8 |
| Process-global state reset per test | `seed_singleton_guard` (+ `extra_specs`), autouse license-gate snapshot | §2 · `testing/pytest_plugin.py:121-136` |
| A slowapi limiter that does not leak 429s | `reset_rate_limiter` (autouse via re-export) | `testing/fixtures.py:33` |
| A real Postgres | PGlite replay (in-process) or the opt-in `realdb` tier | §4 |
| Frontend vitest config | `createProductVitestConfig()` (3 lines) | §5 |


## Running

```bash
cd <product>/backend && pytest                  # all tests
cd <product>/backend && pytest tests/routers    # just router tests
cd <product>/backend && pytest -k test_contacts # by name
```

**Stale-bytecode gotcha — verify test COUNTS against fresh bytecode.** When verifying pytest **test counts** (especially inside a git worktree), a stale `__pycache__` / `.pytest_cache` can make pytest import an OLD compiled module ⇒ it collects the wrong number of tests (we hit 11-vs-13: an appended test class was on disk but pytest ran cached bytecode). Remedy: nuke caches first (`find <dir> -name '*.pyc' -delete && rm -rf __pycache__ .pytest_cache`), or run with `PYTHONDONTWRITEBYTECODE=1 … -p no:cacheprovider`, or trust the OS line-count (`git diff --numstat`) over a cached pytest collection. An "absence of N tests" is a claim — confirm against fresh bytecode (`KB § 01-PHILOSOPHY.md § No silent errors`).

### Running — the house wrappers and their traps *(added 2026-11-05)*

- **Heavy runs go through the hardware gate.** A product's full pytest, any vitest/Playwright
  run, a mutation run: `python mcp/noctusai/tools/noctus/dev/hw_admission.py run --job <kind:target> -- <cmd>`
  (job names are `kind:target`; vitest/e2e/playwright jobs get a worker cap,
  `hw_admission.py:327-332`). Ungated parallel suites swapped the 8 GB machine on 2026-11-04 →
  `KB § PATTERNS/devops/hardware-admission-budget.md`. A single test file to check one claim may run directly.
- **Order is random locally, fixed in CI.** The repo venv carries `pytest-randomly` (and
  `pytest-timeout`); the CI product jobs install only `pytest pytest-asyncio`
  (`.github/workflows/test.yml:386`, `:462`, `:1472`). "Green in CI, red locally with different
  tests each run" is therefore order-dependent pollution until proven otherwise (§6) — reproduce
  with `-p randomly --randomly-seed=<N>` and keep the seed pinned for any A/B.
- **A pytest ERROR is not a failure.** A roll-up that keys on `failed == 0` reads green over a
  product whose tests died at setup (2026-08-10: `all_green: true` over adconnect's 15 setup
  errors). Read `errors` and the per-product `success`, never the aggregate alone.
- **Resolve the interpreter, never bare `python`.** A tool that shells pytest uses
  `settings.resolve_test_python()`; bare `python` without pytest false-BLOCKS `predeploy_check`
  and false-GREENs a parser that counts 0 passed / 0 failed.
- **Know which tree you measured.** Product conftests prepend their own tree's `seed/lib/backend`,
  so a "baseline" run inside a worktree tests the worktree's seed; run the baseline from the primary
  checkout and print `noctusai_lib.<module>.__file__` on both sides. The mock's schema follows
  `Path.cwd()` before the executing module (`testing/_schema_cache.py::_find_repo_root`) — run a
  worktree's tests from inside that worktree.
- **The fleet gate is `noctus.dev.gate_sweep`** (unmeasurable ⇒ `inconclusive`, never `red`;
  harness preconditions refuse to run on an invalid setup). Its internals and the CI test matrix
  belong to the CI/merge redesign (noctusai-3d) — pointer only:
  `KB § PATTERNS/common/methodology-execution-discipline.md` (§10, §10a).

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

### Canonical test identity — `TEST_USER_ID` / `TEST_ORG_ID` (since 2026-05-25)

Mock DB rows MUST reference the seed constants for owner ids — **never a hand-typed literal**:

```python
from noctusai_lib.testing import TEST_USER_ID, TEST_ORG_ID, MockUser

SAMPLE_TASK = {"id": "t1", "user_id": TEST_USER_ID, "org_id": TEST_ORG_ID, "title": "…"}
```

`TEST_USER_ID == MockUser().id` and `TEST_ORG_ID` is exactly what the framework suites assert against — single source in `noctusai_lib.testing.clients`. **Why it matters:** a row whose `user_id` / `org_id` drifts from the `MockUser` default (the `"test-user-id"` vs `"test-user-123"` typo) silently fails every `.eq(user_id|org_id, …)` predicate once `MockRequestBuilder` filtering is accurate — surfacing as a spurious `assert 0 == N`. Importing the constant makes the drift structurally impossible. Promoted from a private `_DEFAULT_USER_ID` to a public export after the N=2 daily-life + erp recurrence (test mocks are shareable seed content). Straggler tell: grep `user_id": "test-user` in a product's tests.

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

### CHECK constraints (default-on since 2026-10-10)

The same default-on validation now also enforces every **CHECK constraint** the migrations declare — cross-column and single-column alike. Examples: `ends_at > starts_at`, `pct_a + pct_b + pct_c = 100`, `num_nonnulls(lead_id, meta_ads_lead_id) = 1`, `(origem = 'gerado' AND docx_path IS NOT NULL) OR origem = 'upload'`. A write the real table would refuse raises `MockRowCheckViolation` at the write. No manifest is needed, and a new migration's CHECK is enforced the day it lands.

```
MockRowCheckViolation: igig.negocio: row violates check constraint "negocio_perdido_com_motivo"
(called via insert). CHECK (status <> 'perdido' OR (motivo_perda IS NOT NULL AND perdido_em IS NOT NULL))
is FALSE for motivo_perda=None, perdido_em=None, status='perdido'. The real database would reject this write (SQLSTATE 23514).
```

How it works:
- **Parsing.** `migration_parser.parse_check_files` reads the CHECKs as they stand after the migrations apply in order (`DROP CONSTRAINT`, re-add, `RENAME COLUMN`, `DROP COLUMN`, `RENAME TO`). `parse_default_files` reads which columns carry a DEFAULT.
- **Translation.** `sql_check.compile_check` turns each body into a predicate with Postgres three-valued logic: NULL passes, and only FALSE fails.
- **Omitted columns.** On INSERT, a column the row omits is NULL, as in Postgres, unless it has a DEFAULT; then it isn't guessed. That NULL rule catches the original `atendimento_contrato_versoes` incident: an INSERT that left out the columns its `_por_origem` CHECK required. On UPDATE or UPSERT, omitted columns keep their old values, so a CHECK that reads one isn't judged.
- **What the mock can't judge** (incomparable types, a naive vs a timezone-aware timestamp, a date vs a timestamp) counts as unknown and passes. The mock may miss a violation; it never fails a test on a guess.
- **Unsupported SQL.** SQL outside the modelled subset (a user-defined function, `LIKE`, a subquery, `CASE`) doesn't compile. `check_stand_in_conformance` leg B(iv) reports a cross-column CHECK like that as a finding unless a `ConditionalPresenceManifest` covers it or it's named, with its reason, in `_KNOWN_UNENFORCEABLE_CROSS_COLUMN_CHECKS`. The gate and the mock share one compile path (`sql_check.compile_cross_column_checks`), so what the gate calls covered is exactly what the mock enforces.

At rollout (2026-10-10):
- **Cross-column:** 89 CHECKs on 58 tables. The 75-finding B(iv) backlog closed, and the rollout surfaced a production bug: `atendimento_intermediarios` document CHECKs vs the canonical punctuated identifiers (social-wiring migration 231).
- **Single-column:** 821 CHECKs, enforced the same day. The only finding fleet-wide was another production bug: igig wrote its own kinds into `public.notifications.type`, whose CHECK refused them, so no igig notification was ever stored. Fixed by the seed's one writer, `noctusai_lib.domain.notifications.write_in_app`.

The opt-in `CheckManifest` / `ConditionalPresenceManifest` remain for constraints the migrations don't declare.

**Bypass for complex PostgREST expressions.** The validator bails (returns silently) on:
- `.select("*, products(*)")` style joined selects (any `(` or `!` in the expression)
- `.or_("status.eq.a,tier.gte.3")` PostgREST OR expressions
- Unknown tables (not in any migration file) — logged as WARNING, not raised (Q4 of the mock-supabase project)

Shipped 2026-04-24 across 4 phases (originating project archived after close). Parser source: `seed/lib/backend/noctusai_lib/testing/migration_parser.py`. Schema cache: `seed/lib/backend/noctusai_lib/testing/_schema_cache.py`. Error class: `seed/lib/backend/noctusai_lib/testing/schema_errors.py`. Keeper detector for silent opt-outs: `mcp/noctusai/tools/noctus/dev/compliance.py::check_mock_schema_validation`. Live-schema drift gate (a DIFFERENT, complementary check — migrations/ORM vs. the real DB, not code vs. migrations): `noctus.dev.schema_drift`, `KB § PATTERNS/backend/database-rls.md § Migrations mirror the code`.

> The opt-out POLICY (the false-green framing, the `check_mock_schema_validation` guardrail, the derived opt-out set, known and remediated opt-outs) stays in `KB § PATTERNS/compliance/testing.md § Schema validation`.


## 4 · Real-database tiers — PGlite in-process and the opt-in `realdb` tier *(added 2026-11-05)*

The mock cannot enforce unique indexes, FKs, RLS, grants, triggers or RPC bodies, and
`MockSupabaseClient.range()` replays the whole table (`mocks.py:1231`), so an unpaged select and a
correct pager look the same to it. Two real-Postgres tiers close that gap. Choosing between them
and the mock is canon §4 (`KB § PATTERNS/compliance/test-engineering-canon.md`).

### 4a · PGlite — real PG16 in-process, no server, no credentials

- **What:** `noctus.dev.migration_replay` replays a product's chain on a fresh PGlite (PG16
  compiled to WASM) after versioned Supabase-surface stubs, core first, then twice
  (`mcp/noctusai/tools/noctus/dev/migration_replay.py:1-12`; contract in
  `KB § PATTERNS/backend/migration-chain-replay.md`). Pre-commit runs it on a staged migration.
- **Inside a test:** drive the same node harness with your DDL + a `DO $$ … $$` block that
  exercises every DB-side rule. Reference: `seed/lib/backend/tests/domain/finance/test_sql_on_real_postgres.py:1-30`
  (generator DDL applied twice, then unique/CHECK/FK rules asserted) and its sibling
  `test_settle_rpc_on_real_postgres.py` (an RPC body on real Postgres).
- **Skip, visibly, when the harness is absent** — `pytest.mark.skipif(... reason="PGlite replay
  harness unavailable (needs node and mcp/noctusai/node/node_modules)")`
  (`test_sql_on_real_postgres.py:25-28`). A skip is not a pass: a suite whose real-Postgres tests
  are all skipped has not tested its SQL. Count skips when you read a result.

### 4b · `realdb` — a live Supabase BRANCH, never prod

- **Credentials only through `get_realdb_credentials()`** (`testing/realdb.py:75-108`): it skips
  unless `NOCTUS_REALDB_TESTS=1` is set explicitly, both `SUPABASE_URL` and
  `SUPABASE_SERVICE_ROLE_KEY` are present, and the URL's project ref is NOT the production ref —
  refused even with the opt-in. Why: every dev `.env` carries PROD credentials (the dev fleet is
  dormant), and the old "credentials present ⇒ run" helper created `RealDB Test test-realdb-*`
  orgs in production that the append-only `audit_logs` trigger then made undeletable
  (`realdb.py:1-35`).
- **Mark the module** `pytestmark = pytest.mark.realdb` and resolve credentials in a
  session fixture (`products/core/backend/tests/realdb/conftest.py:22-28`).
- **The hermetic guard backs it up.** Every session goes through `assert_hermetic`
  (`testing/live_db_guard.py:66-89`, wired in `pytest_plugin.py:73-84`): if the env or the
  resolved settings point at the prod ref or any `*.supabase.co` host and ANY collected test is
  not marked `realdb`, the session aborts before a test body runs (2026-10-09 ghost-org incident:
  fixture rows written into production, real leads routed to them).
- **Teardown must not swallow.** Clean up per test; never `except Exception: pass` around a
  delete — that is exactly how the prod orgs leaked. FK-ordered cleanup lists live next to the
  fixture (`core/backend/tests/realdb/conftest.py:31-40`).
- **Adopters today:** `products/{adconnect,core,erp-imobiliario,orbity,personal-finance,social-wiring,therapy-platform}/backend/tests/realdb/`
  (7 dirs, 2026-11-05; of the awake products, only `core` and `social-wiring`).
- **Not adopted:** container Postgres (testcontainers). Propose it before adding a dependency
  (`KB § PATTERNS/common/silent-test-failure-from-missing-dep.md`).


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

**The same pattern applies to seed-side Real adapter tests.** When a seed module ships a `RealSupabase<X>Repository` (per `KB § PATTERNS/backend/seed-fake-real-adapter.md`), the Real-adapter tests use `MockSupabaseClient` exactly like product-service tests do — `inserted_payloads` for inserts, `updated_payloads` for updates, `set_rpc_data(rpc_name, return_value)` for RPC stubbing, `set_table_data(table, rows)` for select fixtures. The Real adapter is verified end-to-end (table name, schema, query shape, payload mapping) without a single monkey-patch on our own code. Reference: `seed/lib/backend/tests/test_jobs.py::TestRealSupabaseJobRepository` (added 2026-05-04 in `seed-hardening-from-youtube-crawler` Phase 2.1+2.2 by Engineer D; reused by Engineer H in Phase 3.2 for `test_storage.py::TestSupabaseStorageBackend`). Pattern shape: `mock = MockSupabaseClient(); repo = Real<X>Repository(mock, schema_name="public"); await repo.<method>(...); assert mock._tables["<table>"].inserted_payloads == [...]`. Zero monkey-patching of any seed code.

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

5. **Path setup borrowed from a sibling test file (2026-09-21, `abf7711f`).** One file does `sys.path.insert(...)` at import time, and a later file imports a module that only resolves because the earlier file ran first. Sharding or reordering the suite breaks it. **Rule:** shared path setup lives in `conftest.py`, never in a test module.

6. **Import-time side effects triggered inside a test (2026-09-21, `abf7711f`).** `import server` inside a test body ran `configure_logging`, which replaced the root handlers and stripped `caplog`'s. Every later `caplog` assertion then failed. **Rule:** import modules that have import-time side effects (logging configuration, registries, env reads) at COLLECTION time, at module top or in conftest, never inside a test function.

Both shapes show up as soon as a suite is sharded or split across CI jobs, so treat the first "passes alone, fails in the full run" report as a polluter hunt, not a flake.

**Rule out chance before bisecting (2026-09-30).** "Fails in the full suite, passes alone" can also be a probabilistic assertion that just lost a coin toss. `test_access_token_also_encrypted_at_rest` asserted that the 3-char plaintext `"rt2"` was absent from Fernet ciphertext. Random base64url contains it about 0.07% of the time (measured: 2 of 3000). Re-run the single test in a loop before hunting a polluter. An "absent from ciphertext" check needs a long, distinctive needle, never a short one.

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

### Process-global seams the seed plugin already resets *(added 2026-11-05)*

The seed's `pytest11` plugin (`seed/lib/backend/noctusai_lib/testing/pytest_plugin.py`) is the
place a NEW process-global seam gets its reset — never a per-file fixture:

- `declare_hermetic_seams()` sets `NOCTUS_SETTINGS_NO_ENV_FILE=1` and
  `NOCTUS_RATE_LIMIT_MEMORY_ONLY=1` in the earliest hook (`pytest_load_initial_conftests`),
  because settings and the limiter are built at import time (`pytest_plugin.py:40-70`).
- `_isolate_license_gate` (autouse) snapshots and restores the license gate around every test
  (`pytest_plugin.py:121-136`) — born 2026-10-22 when a latency test left an enforcing gate
  behind and auth tests failed at random under `pytest-randomly`.
- `pytest_configure` imports `app.main` so the consent catalog is loaded even for unit tests
  that import a service directly (`pytest_plugin.py:87-118`).



## TS outline-corpus baseline — a safety net, not a wall (frozen corpus)

`mcp/noctusai/tests/test_outline_typescript_corpus.py` snapshots the per-file
**top-level-symbol count** of a small, FROZEN, vendored corpus
(`mcp/noctusai/tests/fixtures/outline_corpus/`) into
`mcp/noctusai/tests/fixtures/outline_corpus_baseline.json` (±5%/±1-symbol
tolerance). Its job is to catch **TS-outliner regressions** (if the extractor
breaks, counts drop). The corpus is a copy, not a live scan of
`products/**` — editing product frontend code does **not** touch it and
never drifts the baseline; a drift here is always an outliner change, never
legitimate feature growth. Bump the fixture + re-snapshot the baseline only
when deliberately changing the outliner (new syntax shape to cover) or
replacing a stale corpus example — see
`mcp/noctusai/tests/fixtures/outline_corpus/README.md`.

Decided 2026-09-23 — this used to snapshot the LIVE `products/*/frontend/src/`
tree, so any legitimate symbol-count change (new route, new hook return
value, a component split) tripped it: 9 baseline-bump-only commits since
2026-08 with no sanctioned per-entry re-ratification path. Freezing the
corpus removed the coupling at the root instead of adding a refresh
ritual on top of it. A separate `TestLiveTreeParses` guard still scans the
live tree, but asserts only parse-success (no symbol-count comparison) — a
pure pass/fail that never drifts on ordinary feature work.

**Backend (`.py`) evaluation — do we need the same?** No (today). Backend AST
*exploration* already works: `noctus.dev.outline_python` (libcst — the AST-first
mandate) + `noctus.dev.outline_python_benchmark` + the noc-graph all read Python
structure. There is **no Python outline-corpus baseline test**, so a product-`.py`
symbol-count change drifts **nothing** — no analogous friction exists. Adding one
(`test_outline_python_corpus.py`) would only add outliner-**regression** protection
for the Python extractor, at the cost of the same refresh-friction the TS one
imposes; it would **not** "ease exploration" (the outline tools already do that).
Recommendation: add a Python corpus baseline **only if** the Python outliner needs
regression protection — not for exploration (already served).

## 8 · Environment the suite owns *(added 2026-11-05)*

- **Assign, never `setdefault`.** `own_test_env({...}, clear=(...))`
  (`testing/conftest_helpers.py:206`) assigns the suite's values and clears keys whose mere
  presence flips a code path. `setdefault` means "whatever the developer exported wins": on
  2026-08-19 an empty `ASAAS_WEBHOOK_TOKEN=` in `.env` turned 15 p-studio webhook tests red under
  `predeploy_check`, and the same file would have built a real service-role client from real
  exported values. Keeper `check_conftest_env_setdefault` (pre-commit on staged product conftests).
- **Playwright's `webServer.env` carries the boot-critical `VITE_SUPABASE_*` placeholders**
  (`products/core/frontend/playwright.config.ts:21-37`) — without them the React tree never mounts
  in CI and every spec fails "element(s) not found". Keeper `check_playwright_supabase_env`
  (boundary B6, `KB § PATTERNS/backend/boundary-contract-tests.md`).
- **"Passes in a plain shell, fails in the runner" ⇒ suspect the environment before the code.**

## 9 · Harness gotchas — index *(added 2026-11-05)*

| Symptom | Likely cause | Where |
|---|---|---|
| Wrong number of tests collected | stale bytecode / `.pytest_cache` | §1 Stale-bytecode gotcha |
| Passes alone, fails in the full run | pollution: module-level dicts, singletons, `sys.path`, import-time side effects | §6 |
| Different tests fail each run | random order + a process-global without reset | §6 · seed plugin seams above |
| `MockSchemaError` on a column that exists | the mock read another tree's migrations (cwd) | §1 added notes |
| Consent test sees stale grants | consent module bound to the FIRST fixture's mock | §5 consent pattern |
| `assert 0 == N` on an `.eq(user_id, …)` read | hand-typed owner id | §2 `TEST_USER_ID` |
| Render test: `Cannot read properties of null (reading 'useState')` | dual React copies | `KB § PATTERNS/frontend/frontend-craft-canon.md §10` |
| E2E green locally, every spec red in CI | `VITE_SUPABASE_*` missing from `webServer.env` | §8 |
| Fleet roll-up green, product never ran | setup ERRORS not counted | §1 added notes |
| Real-Postgres tests "pass" in 0.0s | skipped — harness absent | §4a |
