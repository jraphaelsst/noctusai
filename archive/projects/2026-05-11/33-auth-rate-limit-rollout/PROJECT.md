# Auth Rate-Limit Rollout — Project Document

- **Created:** 2026-05-11
- **Status:** Phase 1 complete — decorator rollout + 429 smoke tests landed; branch ready for orchestrator review
- **Owner / stakeholders:** USER · Engineer AUTH-RL
- **Related docs:**
  - `projects/ratelimit-coverage-audit-2026-05-11/PROJECT.md` (Phase 0 audit — §5.4 table, §7 dispatch shape)
  - `KNOWLEDGE-BASE/CONTEXT/PATTERNS/webhook-signatures.md § Pin 4` (rate-limit contract)
  - `seed/lib/backend/noctusai_lib/api/rate_limit.py` (factory)
  - `seed/lib/backend/noctusai_lib/api/app_factory.py § 95-110` (RateLimitExceeded handler)
- **Project slug:** `auth-rate-limit-rollout-2026-05-11`
- **Branch:** `auth-rate-limit-rollout-2026-05-11` (based on origin/main `03e8db7`)

---

## 1. Context & Purpose

Phase 0 audit (`ratelimit-coverage-audit-2026-05-11`) inventoried decorator
coverage across all 11 products and surfaced 5 uncovered routers in core,
1 uncovered route in therapy-platform, and 1 uncovered file in
media-scheduling. The 5-pin webhook contract polices webhook endpoints
well, but unauth + auth-bearing routes outside webhooks were wide open
to brute-force / scraper / runaway-client abuse.

This project applies `@limiter.limit("N/period")` decorators on those
identified routes, using the policy ladder from the audit's §6
recommendation:

- Login / signup / password-reset: 5/min (defense vs brute force)
- SSO bridge: 20/min (slightly higher; legitimate redirect flows)
- OAuth callback: 10/min (token exchange shouldn't hammer)
- Invitations / onboarding: 30/min (moderate authenticated)
- Sensitive admin (test accounts): 5/min

---

## 2. Confirmed constraints

- **Decorator-only rollout.** No new abstractions; no seed-factory edits; opt-in placement matches Phase 0 audit §3a.6.
- **`request: Request` param required.** slowapi's `key_func=get_remote_address` reads it.
- **`from app.rate_limit import limiter` already wired in all 3 products.** No `app/rate_limit.py` work in this project (factory missing would be DT-RATELIMIT scope).
- **AST-first not applicable.** Simple decorator-and-parameter additions to existing functions; libcst would be heavier than the edit. Edit tool replacement was used with full-context surrounding strings.
- **Per-route smoke tests required.** Asserts 429 on rate-limit exceeded.

---

## 3. Design principles

1. **Match the existing pattern.** Reference adopter: ERP `auth.py` already running 5/min / 10/min / 30/min decorators successfully — copy its shape (request positioned before body in the function signature).
2. **Tests assert status_code only.** Per the status-code-assertion rule, all 429 tests assert on `.status_code`. Body shape coverage lives in the existing per-endpoint test files.
3. **Limiter must reset between tests.** slowapi keeps in-memory counters at module scope; without resetting, tests pollute each other.

---

## 3a. Seed-first analysis

1. **Is the contract identical for every product?** YES at the factory layer — `noctusai_lib.api.rate_limit.create_limiter` + `noctusai_seed.rate_limit.create_product_limiter` already universal. Per-route policy decided per-product per-route at decorator placement.
2. **Is the data source product-specific?** N/A — rate-limit is a transport guard, not data-binding.
3. **Is the placement product-specific?** YES — each product's auth surface is unique. Per-product code count for decorator placement is non-zero by design (Phase 0 audit §3a.3).
4. **Is the visibility / permission rule the same?** YES at the decorator syntax level.
5. **Does the seam already exist in seed?** YES — both the factory (`create_product_limiter`) and the RateLimitExceeded handler (`configure_app` → 429 JSONResponse) ship in seed and are wired by `create_product_app`.
6. **Default-on or opt-in?** OPT-IN per-route (Phase 0 audit §3a.6 confirmed this is correct).

**Litmus — per-product code count this design requires:**

- [x] **A small section** — `@limiter.limit("N/period")` + `request: Request` param at each policed route. **12 decorators in core + 1 in therapy + 3 in media-scheduling = 16 total**. Acceptable for opt-in placement.

**Slip avoided:** No "lift the decorator into seed" — the seam already exists; the placement decision is product-knowledge.

---

## 4. Scope

**In scope (this branch):**

- `products/core/backend/app/routers/sso.py` — 4 routes @ 20/min
- `products/core/backend/app/routers/oauth.py` — 1 route (callback) @ 10/min
- `products/core/backend/app/routers/onboarding.py` — 2 routes @ 30/min
- `products/core/backend/app/routers/test_accounts.py` — 3 routes @ 5/min
- `products/core/backend/app/routers/team.py` — 2 routes (invite, accept-invite) @ 30/min
- `products/therapy-platform/backend/app/routers/auth.py` — 1 route (/me) @ 30/min
- `products/media-scheduling/backend/app/routers/oauth.py` — 3 routes (init GET, init POST, callback) @ 10/min
- 429 smoke test files per product
- conftest `_reset_rate_limiter` autouse fixture per product

**Out of scope:**

- `dev-team-rate-limit-wiring` — separate project (DT-RATELIMIT engineer in parallel).
- `llm-endpoint-rate-limit-rollout` — separate project (LLM-RL engineer queued after MAI-P1).
- `crud-rate-limit-rollout` — lowest priority per Phase 0 §6.4.
- KB pattern doc — deferred to Phase 2 per Phase 0 §6 (pattern docs most accurate when written from a recently-shipped rollout).

---

## 5. Architecture / Data Model

### 5.1 — Files touched

```
products/core/backend/app/routers/
  sso.py          + 4 @limiter.limit("20/minute") + request:Request + drop `from __future__ import annotations`
  oauth.py        + 1 @limiter.limit("10/minute") on callback
  onboarding.py   + 2 @limiter.limit("30/minute")
  test_accounts.py+ 3 @limiter.limit("5/minute")
  team.py         + 2 @limiter.limit("30/minute") on invite + accept-invite

products/core/backend/tests/conftest.py
  + autouse _reset_rate_limiter fixture

products/core/backend/tests/routers/test_auth_rate_limits.py (new)
  + 12 status-pinned 429 smoke tests

products/therapy-platform/backend/app/routers/auth.py
  + 1 @limiter.limit("30/minute") on /me

products/therapy-platform/backend/tests/conftest.py
  + autouse _reset_rate_limiter fixture

products/therapy-platform/backend/tests/routers/test_auth_rate_limits.py (new)
  + 1 status-pinned 429 smoke test

products/media-scheduling/backend/app/routers/oauth.py
  + 3 @limiter.limit("10/minute") on init/init/callback + drop `from __future__ import annotations`

products/media-scheduling/backend/tests/conftest.py
  + autouse _reset_rate_limiter fixture

products/media-scheduling/backend/tests/routers/test_oauth_rate_limits.py (new)
  + 3 status-pinned 429 smoke tests
```

### 5.2 — `from __future__ import annotations` drop

`sso.py` (core) and `oauth.py` (media-scheduling) both used PEP-563 future
annotations. Slowapi's `@limiter.limit` uses `functools.wraps(func)` which
copies `__module__`/`__name__`/`__doc__` but NOT `__globals__`. Pydantic's
ForwardRef resolution falls back to the wrapper's `__globals__` (slowapi's
module), where product-side body classes (`SSOTokenRequest`,
`RedirectResponse`, etc.) are not defined — raising
`PydanticUndefinedAnnotation`.

Solution: drop `from __future__ import annotations` from both files. The
modern syntax in use (`str | None`, `dict[str, Any]`, `list[X]`) is native
in Python 3.10+ at runtime; the repository targets 3.11, so removal is
safe. No type-hint behavior change.

**This is a finding** (knowledge piece in §11 below).

---

## 6. Implementation phases

### Phase 1 — Rollout ✅ (2026-05-11)

- [x] Read RATELIMIT-AUDIT findings (Phase 0 §5.4 inventory + §6 dispatch).
- [x] Read all 7 target router files + reference pattern (core `auth.py` already decorated).
- [x] Verify `app/rate_limit.py` consumer present in core, therapy-platform, media-scheduling.
- [x] Add `request: Request` param + `@limiter.limit("N/period")` decorator on 16 routes.
- [x] Drop `from __future__ import annotations` from 2 router files due to slowapi/Pydantic ForwardRef interaction.
- [x] Add 16 status-pinned 429 smoke tests across 3 new test files.
- [x] Add autouse `_reset_rate_limiter` fixture to 3 conftest files for test isolation.
- [x] Baseline + post-edit pytest green per product (no NEW regressions; 6 pre-existing therapy failures unchanged).
- [x] Keeper review per product → 0 NEW issues.

**Improvements (in-flight):** None — rollout matched the existing ERP/core-auth pattern without surprises.

### Phase 2 — KB pattern doc (deferred — orchestrator dispatches separately)

A `KB § PATTERNS/rate-limit.md` doc should reference:

- The seed seam (`create_limiter` / `create_product_limiter`)
- Recommended policies by route class
- The two-layer model: slowapi (per-IP transport) + `conversation_rate_limit` (per-chat application)
- The slowapi/`from __future__ import annotations` gotcha (so future router authors don't hit it)
- Link from `webhook-signatures.md §Pin 4`

---

## 7. Open questions

1. **Should the limiter-reset fixture move to seed-lib testing?** N=3 conftest fixtures are byte-identical — recurrence rule fires. Triage suggestion: formalize at `noctusai_lib.testing.fixtures.reset_rate_limiter` so future products inherit. (Knowledge piece in §11.)
2. **Should we add a `WARN-on-None-limiter` log line in `create_product_app`?** Phase 0 §7.2 already asked. Out of scope here; flag for DT-RATELIMIT engineer.
3. **Per-conversation limiter seed-lift trigger (N=2)?** Phase 0 §7.3. Out of scope.

---

## 8. Dependencies & blockers

- **None for this branch.** All targets had `app/rate_limit.py` already wired.
- **DT-RATELIMIT engineer (parallel branch, dev-team product)** — no overlap; different product, different files.
- **CORE-ORIGINS engineer (parallel branch, `products/core/backend/app/config.py`)** — different file from `products/core/backend/app/routers/`. Safe parallel; no edit-collisions observed.

---

## 9. Success criteria

- [x] 16 decorators applied per the Phase 0 §6 plan.
- [x] 16 status-pinned 429 smoke tests pass.
- [x] No NEW test regressions in core / therapy-platform / media-scheduling.
- [x] Keeper per product → 0 NEW.
- [x] AST-first respected (only Edit replace on existing function definitions — no regex on source).
- [x] No monkey-patching of our own code.

---

## 10. How to use this project

- **Engineer-facing handoff doc.** Orchestrator reviews this + `findings.md` before FF-merging.
- **Phase 2 (KB pattern doc) belongs to the orchestrator** to dispatch after rollout stabilizes.

---

## 11. Change log

| Date | Change | By |
|---|---|---|
| 2026-05-11 | Phase 1 — 16 decorators + 16 smoke tests + 3 conftest fixtures landed | Engineer AUTH-RL |
