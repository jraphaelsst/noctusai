# Auth-boundary false-green anti-pattern

## What it is

An auth-boundary test that pairs `401` with a **maskable** status code:

```python
assert resp.status_code in (401, 404)   # route-absent mask
assert resp.status_code in (401, 422)   # validation-before-auth mask
```

is a **false-green**: the test passes via the *non-401* branch even when
authentication never fired, so it cannot detect an auth regression. The green
light means nothing — the system under test may be silently broken.

Two codes mask the auth boundary:

- **`404`** — the route is absent (e.g. `standard_routers=[...]` omitted the
  router), so the request 404s before any auth dependency runs.
- **`422`** — FastAPI request-body validation fires before / independent of the
  auth dependency, so an unauthenticated request with an *invalid* body returns
  422. If auth were removed entirely, the invalid body would still 422 → the
  test stays green.

`403` is **not** a mask (it is a second legitimate auth outcome —
authenticated-but-forbidden), so `in (401, 403)` is not flagged.

## Canonical example

`products/dev-team` omitted `"team"` from `create_product_app(standard_routers=[...])`,
so the seed Team-Management organ (`/api/team`) was never mounted. Four tests in
`TestDevTeamAPISurfaceAuthBoundary` asserted `resp.status_code in (401, 404)` against
paths the product never served. They PASSED via the `404` branch — never exercising
auth. Fixed in commit `9d6bf79c`: assertions changed to strict `== 401` against paths
the product actually serves (`/api/run`, `/api/metrics`, `/api/agents`, `/api/configs`).

This bug also produced a paired **RED drift** class (inherited auth tests FAIL because
the route is absent → `404` instead of `401`), caught by the canonical test runner
(see §3 below).

## The two failure classes

| Class | Shape | Detectable by |
|---|---|---|
| **RED drift** | Inherited test asserts `== 401`; route absent → `404` → test FAILS | Test-executing runner (test goes red) |
| **FALSE-GREEN** | Test asserts `in (401, 404)` or `in (401, 422)`; the mask branch is reachable without auth → test passes, auth never exercised | Static AST analysis ONLY — a test runner can never catch this |

## The false-green predicate

Flag a membership test where `401` is paired with a **maskable** code
(`404` *or* `422` — see `_AUTH_FALSE_GREEN_MASKABLE`):

```python
# Flagged — false-green shapes (tuple / set / list, any order):
assert resp.status_code in (401, 404)
assert resp.status_code in (404, 401)
assert resp.status_code in {401, 404}
assert resp.status_code in (401, 422)   # validation-before-auth mask

# NOT flagged — these are legitimate:
assert resp.status_code == 401           # strict auth check
assert resp.status_code in (401, 403)   # 403 = a 2nd legit auth outcome
assert resp.status_code in (404, 500)   # resource-error range, no 401
assert resp.status_code in (200, 201)   # success range
```

`401` is the "auth works" signal; `404`/`422` is the escape hatch that lets the
test pass without auth ever firing.

## The fix

Replace the disjunction with a strict `== 401`:

1. **404 mask** → assert `== 401` against a path the product *actually serves*
   (verify the route is wired first: `standard_routers=[..., "team"]` or
   `routers=[team.router]` in `create_product_app`).
2. **422 mask** → send a **valid request body** so body-validation passes and the
   auth dependency is what fires, then assert `== 401`. Worked example: dev-team's
   `POST /api/run` test sends `{"task": "x"}` (a valid `RunRequest` field) so the
   body parses → strict 401 (an unknown field like `{"prompt": ...}` would 422 on
   the `StrictHttpModel` *before* auth, which is exactly the trap).

## Detection mechanism

`check_auth_boundary_false_green` in `mcp/noctusai/tools/noctus/dev/compliance.py`:

- AST-first (`ast.walk` over `ast.Compare` nodes with `ast.In` op over a tuple/set/list
  where `401` is present alongside a maskable code in `_AUTH_FALSE_GREEN_MASKABLE`
  = `{404, 422}`). Regex would miss the `{401, 404}` set form and multiline variants.
- Never silent: SyntaxError or OS error in a test file → `warning` finding requesting
  manual review, not `except: pass`.
- Scope: `products/*/backend/tests/**/*.py`.
- Severity: `warning` (advisory — surfaces debt, never blocks a commit).

CLI: `python mcp/noctusai/cli.py --check-auth-boundary-false-green`

### Current fleet state (2026-05-29)

- `dev-team` — **clean** (fixed in `9d6bf79c`).
- `personal-finance` — **87 known `in (401, 422)` findings**, surfaced as warnings
  and tracked for remediation (send valid bodies + assert strict 401). The keeper
  exists precisely to make this previously-invisible backlog visible; it is
  advisory so it does not block unrelated commits while the backlog is worked down.

## Canonical test runner (RED drift)

The **red-drift** class (test FAILS because route is absent) is caught by running
the inherited seed-canonical tests fleet-wide. See `noctus.dev.canonical_test_audit`
(`mcp/noctusai/tools/noctus/dev/canonical_test_audit.py`) which:

1. Discovers products whose `backend/tests/` tree contains inherited seed-canonical
   test files (the `test_*_auth_boundary.py` / `test_e2e_flows.py` pattern).
2. Reports which products have inherited canonical tests and lists them for
   execution-based audit.
3. Actual test execution via per-product `.venv` is scoped as
   `NOC-REMEDIATE[canonical-runner-exec]` — see that module for rationale.

## Composes-with

- `KB § PATTERNS/compliance/testing.md` — auth-boundary test discipline
- `KB § PATTERNS/backend/backend.md` — `standard_routers=[...]` opt-in
- `check_standard_routers_audit` — detects the WIRING gap that makes 404 possible
