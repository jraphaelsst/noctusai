# LLM Endpoint Rate-Limit Rollout — Project Document

- **Created:** 2026-05-11
- **Status:** Phase 1 complete — 19 decorators across 6 routers + 3 smoke tests landed; branch ready for orchestrator review
- **Owner / stakeholders:** USER · Engineer LLM-RL-TRIO-2 (recovery dispatch after the original LLM-RL-TRIO engineer was disk-blocked pre-commit; original worktree swept by mole before files could be salvaged)
- **Related docs:**
  - `projects/auth-rate-limit-rollout/PROJECT.md` (sibling pattern; same `@limiter.limit` + Request-first-param shape, applied to auth/SSO/onboarding routes)
  - `projects/ratelimit-coverage-audit-2026-05-11/PROJECT.md` (Phase 0 audit that surfaced LLM-fanout gap as a separate priority)
  - `KNOWLEDGE-BASE/CONTEXT/PATTERNS/webhook-signatures.md § Pin 4` (rate-limit contract)
  - `seed/lib/backend/noctusai_lib/api/rate_limit.py` (factory)
  - `products/personal-finance/backend/app/routers/ai.py` (reference adopter — PF-AUTH-MIG already runs 3×`30/minute` on AI endpoints)
- **Project slug:** `llm-endpoint-rate-limit-rollout-2026-05-11`
- **Branch:** `llm-endpoint-rate-limit-rollout-2026-05-11`

---

## 1. Context & Purpose

The auth rollout (`auth-rate-limit-rollout-2026-05-11`) closed the
unauthenticated brute-force vector (login / SSO / OAuth / onboarding /
admin). This rollout closes the **authenticated cost-runaway vector** —
endpoints that fan out to OpenAI / embeddings on every call. Without
per-IP throttling, a single compromised token can drain the org's
OpenAI budget or trigger pgvector embedding storms in seconds.

The PF reference adopter (`personal-finance/backend/app/routers/ai.py`)
already proves the shape: `@limiter.limit("30/minute")` +
`request: Request` as the first param. This rollout extends the same
shape to mailing, daily-life, and therapy-platform routers that fan
out to expensive AI work.

---

## 2. Confirmed constraints

- **Decorator-only rollout.** No new abstractions; no seed-factory edits.
- **`request: Request` MUST be the first param.** slowapi reads it via `key_func=get_remote_address`.
- **`from app.rate_limit import limiter` already wired** in all 3 products (mailing / daily-life / therapy-platform). Factory at `noctusai_seed.rate_limit.create_product_limiter`.
- **Drop `from __future__ import annotations`** in any decorated module. Combined with slowapi's introspection it triggers ForwardRef collapse. Mailing's `ai.py` had this and was the only file that needed the drop (rest used PEP-563-equivalent typing already).
- **`limiter.reset()` autouse fixture** required in each product's conftest. slowapi keeps in-memory counters at module scope; without the reset, a 31-call burst from one test polls 30/minute and bleeds into unrelated tests later in the suite. Therapy already had it; mailing + daily-life conftests added it this rollout.
- **Per-route smoke tests required.** Assert 200×N then 429 on N+1. Status-code-assertion rule (KB).

---

## 3. Design principles

1. **Match the existing pattern.** Reference adopter: PF's `ai.py` running 3×`30/minute` for >2 weeks without incident.
2. **Skip pure-pgvector routes.** `find_matches` (therapy_matching) and `get_match_suggestions` do not call an LLM and need no decorator at this tier.
3. **Tests assert status_code only.** Body shape coverage lives in the existing per-endpoint test files.

---

## 3a. Seed-first analysis

1. **Is the contract identical for every product?** YES at the factory layer — `noctusai_lib.api.rate_limit.create_limiter` + `noctusai_seed.rate_limit.create_product_limiter` already universal. Per-route policy decided per-product per-route at decorator placement.
2. **Is the data source product-specific?** N/A — rate-limit is a transport guard, not data-binding.
3. **Is the placement product-specific?** YES — each product's AI surface differs. Per-product code count for decorator placement is non-zero by design.
4. **Is the visibility / permission rule the same?** YES at the decorator syntax level.
5. **Does the seam already exist in seed?** YES — both the factory (`create_product_limiter`) and the RateLimitExceeded handler (`configure_app` → 429 JSONResponse) ship in seed and are wired by `create_product_app`.
6. **Default-on or opt-in?** OPT-IN per-route.

**Litmus — per-product code count this design requires:**

- [x] **A small section** — `@limiter.limit("N/period")` + `request: Request` param at each policed route. **19 decorators across 6 files in 3 products**. Acceptable for opt-in placement.

**Slip avoided:** No "lift the decorator into seed" — the seam already exists; placement decision is product-knowledge.

---

## 4. Scope

**In scope (this branch):**

| Product | File | Endpoints | Limit |
|---|---|---|---|
| mailing | `routers/ai.py` | subjects, template-draft, reengagement, deliverability, translate, segment-contacts, campaigns/{id}/debrief GET, campaigns/{id}/debrief/send POST | 7×`30/minute` + 1×`10/minute` (segment-contacts is contact-batch intensive) |
| daily-life | `routers/ai.py` | weekly-review, daily-brief | 2×`30/minute` |
| therapy | `routers/therapy_matching.py` | embed, embed-terapeuta, embed-paciente | 3×`30/minute` (skip `find_matches` — pgvector only, no LLM) |
| therapy | `routers/sessions.py` | end_session (fans out transcription + summary + longitudinal) | `10/minute` |
| therapy | `routers/observations.py` | create, update, delete (each triggers ai_pipeline.on_observation_change) | 3×`30/minute` |
| therapy | `routers/patient_notes.py` | create, update (each triggers ai_pipeline.on_patient_note_change) | 2×`30/minute` |

**Total:** 19 decorators across 6 files in 3 products.

**Out of scope:**

- core, ERP, PF (PF already done in PF-AUTH-MIG; core/ERP have no AI-fanout routes).
- adconnect, imobi-scheduling, dev-team, youtube-crawler, media-scheduling (no LLM endpoints, OR limits already shipped via dev-team rollout, OR webhook contract covers them).

---

## 5. Files touched

- `products/mailing/backend/app/routers/ai.py` — 8 decorators + `Request` import + `from app.rate_limit import limiter` + drop `from __future__ import annotations`
- `products/mailing/backend/tests/conftest.py` — `_reset_rate_limiter` autouse fixture
- `products/mailing/backend/tests/routers/test_ai_rate_limits.py` — 1 new smoke test
- `products/daily-life/backend/app/routers/ai.py` — 2 decorators + `Request` import + limiter import
- `products/daily-life/backend/tests/conftest.py` — `_reset_rate_limiter` autouse fixture
- `products/daily-life/backend/tests/routers/test_ai_rate_limits.py` — 1 new smoke test
- `products/therapy-platform/backend/app/routers/therapy_matching.py` — 3 decorators + `Request` import + limiter import
- `products/therapy-platform/backend/app/routers/sessions.py` — 1 decorator + `Request` import + limiter import
- `products/therapy-platform/backend/app/routers/observations.py` — 3 decorators + `Request` import + limiter import
- `products/therapy-platform/backend/app/routers/patient_notes.py` — 2 decorators + `Request` import + limiter import
- `products/therapy-platform/backend/tests/routers/test_ai_rate_limits.py` — 1 new smoke test (therapy conftest already had the autouse reset fixture from `auth-rate-limit-rollout-2026-05-11`)

---

## 6. Validation

- **mailing:** 213 passed / 1 pre-existing failure (`test_full_lifecycle` line 184 — unrelated integration test, out of scope; baseline was 212/1, new total 213/1 = +1 smoke test, no regressions).
- **daily-life:** 209/209 (baseline 208/208 + 1 smoke test, no regressions).
- **therapy-platform:** 1332 passed / 6 pre-existing failures + 14 skipped (baseline was 1331/6 in this worktree base `9fa060f`; same 6 failures are all in session/observation/patient_notes routers and were confirmed pre-existing by temporarily stashing the decorator changes; net +1 smoke test, no regressions).
- **3 smoke tests** added (1 per product), each asserts `200×30` (or `403×30` for therapy where therapist role is forbidden but the decorator runs first) then `429` on call 31.

---

## 7. Lessons captured (returned as findings text per §17.6.1)

See engineer report sent to orchestrator; key items:

1. `Edit` tool with absolute paths writes to the noc-root checkout, NOT the worktree path. Worktree-base preamble must include explicit path-prefix discipline OR engineer must `cd` into worktree before all edits. Recovery: `git stash push` from misrouted location, `git stash pop` in worktree.
2. `from __future__ import annotations` + slowapi = ForwardRef collapse. Confirmed by LLM-RL-TRIO's original block; preserved by dropping the line.
3. `limiter.reset()` autouse fixture is mandatory anywhere `@limiter.limit` is applied + tested. Without it, a single 31-call smoke test pollutes ~3-10 unrelated tests downstream depending on test order.
4. Pre-existing therapy failures (6) are in session/observation/patient_notes routers — exactly the surface I decorated. False-alarm risk avoided by stash-pop diff check.
5. Therapy conftest already had `_reset_rate_limiter` from auth-rate-limit-rollout; mailing + daily-life conftest gap was structural. N=3 (auth-rl, llm-rl-trio, future LLM rollouts) → consider seed-lib `RateLimiterTestSuite` mixin. Recurrence rule logged.

---

## 11. Change log

- 2026-05-11 — Engineer LLM-RL-TRIO-2 recovery dispatch: 19 decorators + 2 conftest fixtures + 3 smoke tests; net +3 passing tests across 3 products; 0 NEW keeper findings; commit + branch-push ready.
