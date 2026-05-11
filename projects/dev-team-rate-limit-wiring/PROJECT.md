# dev-team Rate-Limit Wiring — Project Document

- **Created:** 2026-05-11
- **Last updated:** 2026-05-11
- **Status:** Phase 1 in progress
- **Owner / stakeholders:** Architect (orchestrator) · Engineer DT-RATELIMIT
- **Related docs:** `projects/ratelimit-coverage-audit/` (commit 056b6e0 audit), `KB § PATTERNS/llm-bot-security.md`, `KB § PATTERNS/dev-team.md`
- **Project slug:** `dev-team-rate-limit-wiring` (single-product wiring, lives under top-level `projects/` because audit umbrella sits there)

---

## 1. Context & Purpose

The RATELIMIT-AUDIT (commit `056b6e0` on main, 2026-05-11) inventoried rate-limit
coverage across every product backend and discovered that `products/dev-team`
ships **no** `app/rate_limit.py` factory and does **not** pass `limiter=` to
`create_product_app`. Because the dev-team product proxies the agno multi-agent
team — every `POST /api/run` triggers a real LLM call (Anthropic / OpenAI /
Gemini) — leaving the route unlimited is an **unbounded LLM-spend risk**:
a single misbehaving client (or accidental loop in the frontend) can fire
thousands of `team.run` requests in seconds, each spending tokens across the
11-agent ensemble. This project closes the gap.

The fix is byte-mechanical: 10 of 11 sibling products already ship the same
1-line `app/rate_limit.py` factory, and `create_product_app` already has the
`limiter=` seam wired into the seed framework. We mirror the canonical shape
and apply `@limiter.limit("10/minute")` to `POST /api/run`.

---

## 2. Confirmed constraints

- **Audit baseline** — RATELIMIT-AUDIT commit `056b6e0`; dev-team flagged as the lone gap. *(Source of truth for the 10/11 canonical shape.)*
- **Canonical shape** — `from noctusai_seed.rate_limit import create_product_limiter; limiter = create_product_limiter(settings)`. *(Byte-identical across 10 consumers — see §3a.)*
- **Conservative dev default** — 10/minute on `/api/run`. *(Each call fans out across 11 agents → real spend; tune later if user signals tighter / looser bound.)*
- **slowapi requires `request: Request`** — first positional parameter must be `Request` for the `@limiter.limit(...)` decorator to extract the client IP. *(Established slowapi contract.)*

---

## 3. Design principles

1. **Seed-first mechanical replication.** Mirror `products/seed/backend/app/rate_limit.py` byte-for-byte (modulo header comment). The factory IS the seed-shipped pattern.
2. **Decorate the LLM-spend perimeter, not every route.** Only `POST /api/run` proxies the LLM team. `GET /api/agents`, `GET /api/metrics`, `GET /api/configs`, `PATCH /api/configs/{name}` read from local telemetry — they're protected by the seed's default 100/minute global limit but don't need per-route tightening.
3. **AST-first edits** (libcst) on `app/main.py`. The 1-line `app/rate_limit.py` is a new file (Write), not an edit.

---

## 3a. Seed-first analysis

1. **Is the contract identical for every product?** YES — 10/11 ship byte-identical `app/rate_limit.py`. Already absorbed at the seed (`noctusai_seed.rate_limit.create_product_limiter`).
2. **Is the data source product-specific?** N/A — the limiter is a factory call, not a data source.
3. **Is the placement product-specific?** YES — the decorator goes on dev-team's `POST /api/run` (the LLM proxy). The factory itself is universal.
4. **Is the visibility / permission rule the same?** YES — IP-keyed rate limit, identical semantics across products.
5. **Does the seam already exist in seed?** YES — `noctusai_seed.rate_limit.create_product_limiter` (factory) + `create_product_app(limiter=...)` (mount seam). Both ship in main today.
6. **Default-on or opt-in?** DEFAULT-ON — every other product opts in via the 1-line factory call. dev-team is the explicit gap. After this fix, default is "all 11 products limited".

**Litmus — per-product code count this design requires:**
- [x] **A small section** — 1-line `rate_limit.py` (new) + 1-line addition to `main.py` + 1-line decorator on the single LLM route. Acceptable: every consuming product carries this exact small section by design.

**Phase plan implications:** §6 phases work in dev-team (the gap) — the seed and the framework already ship the seam. This is consumer wiring, not seed work.

---

## 4. Scope

**In scope:**
- Ship `products/dev-team/backend/app/rate_limit.py` mirroring seed canonical shape.
- Wire `limiter=limiter` into `create_product_app` call in `app/main.py`.
- Decorate `POST /api/run` with `@limiter.limit("10/minute")` and add `request: Request` parameter.
- Add 2 tests: 429-when-over-limit + 200-when-under-limit (status-code-assertion rule).

**Out of scope:**
- Tightening / loosening the 10/minute default — user can tune in a follow-up.
- Per-org or per-user keying (slowapi default is per-IP). The `get_remote_address` key_func suffices for the dev-spend threat model.
- Other dev-team routes — `/api/run` is the only LLM-proxy; the seed's default 100/minute covers reads.

---

## 5. Architecture / Data Model

Files touched:
- **NEW** `products/dev-team/backend/app/rate_limit.py` — 5 lines, mirror of `products/seed/backend/app/rate_limit.py`.
- **EDIT** `products/dev-team/backend/app/main.py` — add `from app.rate_limit import limiter` + `limiter=limiter,` kwarg.
- **EDIT** `products/dev-team/backend/app/api/run.py` — add `Request` to imports + `@limiter.limit("10/minute")` decorator + `request: Request` parameter.
- **EDIT** `products/dev-team/backend/tests/test_api_smoke.py` — append 2 tests.

---

## 6. Implementation phases

### Phase 1 — Ship the factory + wire main + decorate route + tests ⏳

- [ ] Create `app/rate_limit.py` mirroring seed.
- [ ] AST-edit `app/main.py` to add `limiter` import + kwarg.
- [ ] AST-edit `app/api/run.py` to add `Request` import + decorator + `request: Request` param.
- [ ] Append rate-limit tests to `tests/test_api_smoke.py`.
- [ ] `pytest -q` green (allow 4 pre-existing baseline failures in `test_e2e_flows.py` — unrelated).
- [ ] Boot test: `python -c "from app.rate_limit import limiter; print(limiter)"` returns an instance.
- [ ] Keeper review clean.
- [ ] Commit + branch-push.

---

## 11. Change log

- **2026-05-11** — Project filed; Phase 1 dispatched.

---

