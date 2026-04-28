# Testing Standards

Every product must have three test layers. No product ships without all three.

| Layer | What it tests | Where | When to write |
|-------|---------------|-------|---------------|
| **Unit (routers)** | Individual endpoints — CRUD, auth, validation, error handling | `tests/routers/test_*.py` | One per domain router |
| **Unit (services)** | Business logic in isolation — calculations, transformations, state machines | `tests/services/test_*.py` | One per service with non-trivial logic |
| **Integration** | Cross-service flows — campaign references template + list, automation enrolls contacts | `tests/integration/test_*.py` | When entities reference each other |
| **E2E** | Full user journeys — create contact → template → campaign → send → verify stats | `tests/integration/test_e2e_flows.py` | One per product, covers the golden path |

## Rules

- **Unit tests:** mock the database (`MockSupabaseClient`). Test one endpoint at a time.
- **Integration tests:** mock the database but test multi-step flows where step N depends on step N-1.
- **E2E tests:** simulate a real user journey through multiple endpoints. Each test is a story.
- **Deterministic:** no hardcoded dates (use `date.today()` / `date.today() - timedelta(days=N)`), no external API calls, no network.
- **Auth boundary:** every product must verify that unauthenticated requests return 401 for all protected endpoints.

## Running

```bash
cd <product>/backend && pytest                  # all tests
cd <product>/backend && pytest tests/routers    # just router tests
cd <product>/backend && pytest -k test_contacts # by name
```

## Mock helpers

Import from the seed test kit:
```python
from tests.conftest import (
    MockSupabaseClient,
    MockSelectBuilder,
    MockUser,
    MockUserResponse,
    AuthClient,
)
```

Each product's `conftest.py` re-exports these from the shared seed test helpers. Don't re-implement mocks per product.

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

Shipped 2026-04-24 across 4 phases (originating project archived after close). Parser source: `seed/backend/lib/noctusai_lib/testing/migration_parser.py`. Schema cache: `seed/backend/lib/noctusai_lib/testing/_schema_cache.py`. Error class: `seed/backend/lib/noctusai_lib/testing/schema_errors.py`. Keeper detector for silent opt-outs: `mcp/noctusai/tools/compliance.py::check_mock_schema_validation`.

---

## Seed-layer test harnesses

Two infrastructure-level test suites verify the framework itself, independent of any product:

| Layer | Where | Runner | What it covers |
|---|---|---|---|
| Backend framework (`noctusai_seed`) | `seed/backend/framework/tests/` | `pytest` | `build_standard_routers` registry, opt-in resolution, factory shape. Pure-Python, no DB. |
| Frontend framework (`@noctusai/seed`) | `seed/frontend/framework/tests/` | `vitest` (jsdom) | `createProductApp` auth-branch selection (supabase vs custom `authProvider`), route topology (`unauthRedirect`, conditional `/sso` mount), error guard when neither auth path is provided. |
| Shared library (`noctusai_lib`) | `seed/backend/lib/tests/` | `pytest` | Pure-function helpers: notifications mapper, etc. |

### Running

```bash
cd seed/backend/framework && pytest tests/ -q
cd seed/backend/lib       && pytest tests/ -q
cd seed/frontend/framework && npm test
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

**When to add `core_db` (or any other dependency) as an optional kwarg to a pipeline function.** Default to `None` and lazily resolve via `get_core_client()` when the function actually needs it (the resolve-helper pattern). Production paths keep working without code changes; tests inject the same mock so write side-effects land in a place the test can read. This is **dependency injection**, not patching — the production call site never holds onto the mock; the kwarg defaults to None and the runtime resolves to the real client. Reference: `_resolve_core_db(core_db)` in `products/therapy-platform/backend/app/services/ai_pipeline.py`.

### Per-product frontend hook tests (seed-scoped factory, 2026-04-27)

Every product frontend at `products/<X>/frontend/` ships with a 3-line `vitest.config.ts` that delegates to **`createProductVitestConfig`** at `seed/frontend/framework/vitest.config.factory.ts` — the seed-scoped factory absorbing the canonical config. This is the same skeleton/organ pattern as `createViteConfig` (sibling factory at `vite.config.factory.ts`); changes to the canonical shape land once in seed and propagate to every product at install time. Adopters: erp, mailing, daily-life, personal-finance, therapy-platform, core, adconnect. Seed reference product (`products/seed/`) is intentionally NOT in this list — it's a scaffolding template, not a consumer.

**Canonical config shape** (3 lines, copy verbatim — no per-product mutation):

```ts
// products/<X>/frontend/vitest.config.ts
import { createProductVitestConfig } from "../../../seed/frontend/framework/vitest.config.factory";
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

The factory itself is tested at `seed/frontend/framework/tests/createProductVitestConfig.test.ts` (6 tests covering defaults + each override knob).

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

See also:
- `../06-AGENTS.md` — the MCP heal loop runs tests automatically
- `../../INSTRUCTIONS/05-TESTING-EVALS.md` — eval strategy (beyond unit/integration)
