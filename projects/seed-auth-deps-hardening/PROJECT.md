# Seed Auth Deps Hardening — Project Document

> **This is a living document.** Update phases / change log as you build.
>
> **Project slug:** `seed-auth-deps-hardening` — lives at `projects/seed-auth-deps-hardening/` (cross-cutting platform refactor; touches seed framework + lib + at least one product + KB).

- **Created:** 2026-05-06
- **Last updated:** 2026-05-06
- **Status:** All phases ✅ — engineer-side close complete; architect FF-merge pending
- **Owner / stakeholders:** rapha (user) · architect-agent
- **Related docs:**
  - `KB § PATTERNS/backend.md` (target for canonical pattern doc)
  - `seed/lib/backend/noctusai_lib/api/auth.py` (factory already lives here)
  - `seed/framework/backend/noctusai_seed/dependencies.py` (broken class to deprecate)
  - `archive/projects/2026-05-04/<NN>-make-get-current-user-org-factory/` (predecessor — built the factory)
  - `noctusai-youtube-crawler/findings.md § Phase 2` (where the bug surfaced; quoted in §1)

---

## 1. Context & Purpose

Phase 2 of the YouTube Crawler product surfaced a **silent platform-wide bug**:
the seed framework exports `ProductDependencies.get_org_id`,
`ProductDependencies.get_user_role`, and `ProductDependencies.get_user_client`
in a shape that **looks** like a FastAPI dependency but **isn't one**. Wired as
`org_id: UUID = Depends(get_org_id)`, FastAPI introspects the
`get_org_id(user) -> str` signature, sees `user` has no `Depends()` /
`Header()` / `Query()` annotation, and treats it as a **required query
parameter**. Result: every authed request to a route using these deps returns
422 with `loc: ['query', 'user']` / `loc: ['query', 'token']`. The 401/403
paths inside the deps never run.

**Why this lay dormant:** every product (PF, Therapy, Mailing, AdConnect)
**already** uses an imperative pattern (`authorization: Header(None)` +
`await get_current_user_org(authorization)` inside the route body) — the
broken `Depends`-style export is **dead code with no consumers** but
exported by the seed in a way that lures new code into the trap. Phase 1
of YouTube Crawler fell into the trap; Phase 2 fell into it again before
the fix landed in the workspace.

**Why now:** the parallel-agent project `make-get-current-user-org-factory`
shipped `make_get_current_user_org` to `noctusai_lib.api.auth` in 2026-05-04
(already on `origin/main`). The factory **does** chain correctly through
FastAPI because its returned function takes only `authorization: Header(None)`
— the org-id resolver is captured in the closure. Wiring the factory across
products + deprecating the broken class closes the trap.

**The win:** any future code that reaches for `Depends(get_org_id)` either
(a) gets a clear deprecation warning, (b) finds the canonical factory pattern
in KB, and (c) gets caught by a keeper-detector if they slip past the warning.
Three layers of defense; failure becomes structurally impossible.

---

## 2. Confirmed constraints

- **Already-shipped factory** — `make_get_current_user_org(get_current_user_fn, get_org_id_fn, *, required, missing_status, missing_detail)` is on `origin/main` at `seed/lib/backend/noctusai_lib/api/auth.py:231`. Pattern: products call it once at module load; the returned async dep takes `authorization: Header(None)` and yields `(user, token, org_id)`. *(Constraint: don't rebuild what's there.)*
- **Workspace product (YouTube Crawler) is the only product wired imperatively today** — the other products (PF / Therapy / Mailing / AdConnect / etc.) define their own `get_current_user_org` per-product (PF) or use `get_org_id(user)` imperatively (ERP-imobiliario). Cross-product rollout is **out of scope here** (deferred to a follow-up project) — this project only wires the workspace product. *(Constraint: scope discipline; the workspace is the immediate consumer.)*
- **Deprecation, not deletion** — `ProductDependencies.get_org_id` and `get_user_role` and `get_user_client` are unused as `Depends()` (greppable: zero hits across `products/`) but might be imported as plain functions. Tag with `DeprecationWarning` rather than delete; deletion in a follow-up. *(Constraint: avoid unrelated breakage; one change at a time.)*
- **Run before YouTube Crawler Phase 3** — the user explicitly requested this lands before Phase 3 of the workspace product so Phase 3's new code uses the factory pattern from the start. *(Constraint: schedule pressure; keep scope tight.)*
- **Cross-cutting → root projects/** — slug = `seed-auth-deps-hardening`, lives at `projects/seed-auth-deps-hardening/`. Not under `products/` because the project touches the seed framework + at least one product + KB. *(Per `KB § PATTERNS/project-execution.md §1 and §8`.)*

---

## 3. Design principles

1. **Three layers of defense.** A platform-wide trap closes when (a) the canonical pattern is documented, (b) the broken pattern emits a clear warning at use, and (c) a keeper-detector catches new occurrences in code review. Each layer is cheap; the combination makes the failure structurally impossible.
2. **Wire one product end-to-end before generalizing.** The workspace's YouTube Crawler is the smallest blast-radius consumer — refactoring its two routers (`settings_router.py` + `upload_router.py`) proves the pattern works against a real codebase. Cross-product rollout is a separate project.
3. **Deprecation warnings target the *Depends-wiring* shape, not the function call itself.** Many products still call `get_user_role(user)` imperatively — that call works fine. The warning fires only when the function is unwrapped + given to `Depends()` (i.e., when something invokes it as a request-time dep with an empty arg list).
4. **Document the *why*, not just the *how*.** The KB § PATTERNS/backend.md addition explains what makes `make_get_current_user_org` chain correctly (closure-bound resolver) and what made the old shape fail (positional `user` arg → query param). Future agents inherit the reasoning.

---

## 3a. Seed-first analysis (REQUIRED)

1. **Is the contract identical for every product?** YES. Every product needs the same (user, token, org_id) tuple at request time. The factory's parameters (`required`, `missing_status`, `missing_detail`) cover the small per-product variance (PF = 403 / ERP = 400).
2. **Is the data source product-specific?** The org-id resolver IS per-product (PF reads `user.user_metadata.org_id`, ERP has its own). The factory takes the resolver as a closure parameter — the seam is named correctly.
3. **Is the placement product-specific?** NO. Auth wiring lives in every product's `app/dependencies.py` regardless of domain.
4. **Is the visibility / permission rule the same?** YES — every product gates on org_id presence; the missing-org behavior varies (raise 403 vs return None) which is the `required` flag's job.
5. **Does the seam already exist in seed?** YES — `make_get_current_user_org` shipped 2026-05-04. The seam is **already** in the right place (lib, not framework). Verify-the-seed-ships-it: confirmed (Protocol-shape unnecessary; this is a pure factory, not an IO module).
6. **Default-on or opt-in?** OPT-IN today (no products wire it yet); becomes effectively default after this project + the cross-product rollout. The deprecation warning on the broken `ProductDependencies` methods nudges every future use toward the factory.

**Litmus — per-product code count this design requires:**

- [x] **A small section** — each product's `app/dependencies.py` adds ~5 lines wiring the factory; existing per-product `get_current_user_org` helpers (PF) get replaced by the factory call. Acceptable because the resolver IS per-product data.

**Phase plan implications:** §6 phases work in **seed + one product (YouTube Crawler)** first. Cross-product rollout is `§4 out of scope`.

---

## 4. Scope

**In scope:**
- Refactor YouTube Crawler `settings_router.py` + `upload_router.py` to use `make_get_current_user_org` via `Depends(get_current_user_org)` instead of imperative `await _resolve_auth(authorization)`.
- Wire `make_get_current_user_org` into `products/youtube-crawler/backend/app/dependencies.py`.
- Tag `ProductDependencies.get_org_id`, `get_user_role`, `get_user_client(token)` with `DeprecationWarning` raised at module import or first call, with a message pointing at the canonical pattern.
- Add `KB § PATTERNS/backend.md § Auth — canonical pattern` documenting the factory + the trap of the broken `Depends`-style export. Sync via three-way sync (KB + CLAUDE.md pointer + memory).
- Verify with `cd products/youtube-crawler/backend && pytest` (94/94 staying green).

**Out of scope (deferred):**
- **Cross-product rollout** (PF, Therapy, Mailing, AdConnect, ERP, Daily Life, Personal Finance, Media Scheduling, Therapy Platform). File as `seed-auth-deps-cross-product-rollout` follow-up. Reason: each product has a slightly different `get_org_id` resolver shape; rollout is a multi-product orchestration that benefits from the keeper-detector landing first (Project 2) so regression is automatic.
- **Deletion of `ProductDependencies.get_org_id` / `get_user_role` / `get_user_client(token)`**. Deferred until cross-product rollout completes + the deprecation warning has lived for 1+ release. Reason: minimize coupling.
- **Frontend changes**. None required — the API surface is unchanged.
- **`get_current_user` itself** (works correctly as `Depends()` because its only param is the `Header`). Not deprecated.

---

## 5. Architecture / Data Model

### Files touched

**Workspace (noc):**
- `products/youtube-crawler/backend/app/dependencies.py` — add factory wiring (5 new lines):
  ```python
  from noctusai_lib.api.auth import make_get_current_user, make_get_current_user_org
  get_current_user = make_get_current_user(get_supabase_client)
  get_current_user_org = make_get_current_user_org(
      get_current_user,
      lambda u: (u.user_metadata or {}).get("org_id"),
      required=True,
  )
  ```
- `products/youtube-crawler/backend/app/routers/upload_router.py` — replace `await _resolve_auth(authorization)` with `auth = Depends(get_current_user_org)` + `user, token, org_id = auth`. Remove the `_resolve_auth` helper.
- `products/youtube-crawler/backend/app/routers/settings_router.py` — same refactor; the existing per-route `Depends(get_org_id)` shape gets replaced with `Depends(get_current_user_org)`.
- `seed/framework/backend/noctusai_seed/dependencies.py` — add `DeprecationWarning` to the three broken methods. Approach: wrap the methods so the warning fires on first call + include a stable migration message pointing at the factory.
- `KNOWLEDGE-BASE/CONTEXT/PATTERNS/backend.md` — add new "Auth — canonical pattern" section documenting `make_get_current_user_org` + the trap.
- `CLAUDE.md` — add a §2 Map entry pointing at the new KB section (if not already there).
- Memory: add a `feedback_auth_factory_pattern.md` entry + MEMORY.md index line.

### Boundaries

- **Don't touch other products.** A grep across `products/` for `Depends(get_org_id)` / `Depends(get_user_client)` / `Depends(get_user_role)` is the integrity check — if any product currently uses these patterns, it's a bug already and out of scope here.
- **Don't change the existing `get_current_user` shape** — it works correctly as `Depends(get_current_user)` because its only param is the `Header`.

---

## 6. Implementation phases

### Phase 1 — Wire the factory in YouTube Crawler ✅

- [x] In `products/youtube-crawler/backend/app/dependencies.py`, import + bind `make_get_current_user_org`. Export `get_current_user_org` as a module-level dep.
- [x] Refactor `app/routers/upload_router.py` to use `auth = Depends(get_current_user_org)` instead of imperative `_resolve_auth(authorization)`. Delete `_resolve_auth` helper.
- [x] Refactor `app/routers/settings_router.py` similarly. Replace per-route `Depends(get_org_id)` + `Depends(get_user_client)` with the single `Depends(get_current_user_org)` tuple.
- [x] Run `pytest` — must stay 94/94 green. (94 passed, 2 warnings in 0.30s — unrelated pre-existing warnings.)
- [x] Update `noctusai-youtube-crawler/findings.md § Phase 2` with a "→ project seed-auth-deps-hardening filed; YouTube Crawler now uses the factory" pointer.

### Phase 2 — Deprecate the broken seed export ✅

- [x] In `seed/framework/backend/noctusai_seed/dependencies.py`, wrap `ProductDependencies.get_org_id`, `get_user_role`, `get_user_client` so first call emits `DeprecationWarning` with a message including (a) the bug shape, (b) the migration recipe, (c) the KB pattern pointer. Implemented as a frame-aware `_warn_if_fastapi_caller(qualname)` helper that fires ONLY when `fastapi.dependencies.utils` is the immediate caller — honors §3 design principle 3 ("warn on the broken shape only, not imperative use").
- [x] Verify the existing seed-product tests still pass — `cd products/seed/backend && pytest` → 31/31.
- [x] Verify all noc-resident product tests still pass — `cd seed/framework/backend && pytest` → 37/37 (+4 from new `test_dependencies_deprecation.py`); workspace YouTube Crawler → 112/112. Imperative call sites (seed team router → `deps.get_user_role(user)`) no longer fire the warning, confirmed by absence of DeprecationWarning lines in the workspace test summary.

### Phase 3 — Document the canonical pattern ✅

- [x] Add `KB § PATTERNS/backend.md § Auth — canonical pattern` section. Replaced the legacy 4-line `## Auth` section with a full canonical-pattern doc covering: factory wiring (code block), why-it-chains-correctly (closure-bound resolver), why-old-shape-failed (positional args become query params), OAuth-callback carve-out, late-binding-rule, anti-patterns checklist, migration history.
- [x] Updated `CLAUDE.md` §3 (When to read what) with a row "Wiring auth on a new product / route → KB § PATTERNS/backend.md § Auth — canonical pattern". §2 Map already covers `KB § PATTERNS/backend.md` so no further entry needed.
- [x] Added `memory/feedback_auth_factory_pattern.md` + MEMORY.md index line under § Code quality / engineering.
- [x] Ran `bash scripts/verify-kb-sync.sh` → ✓ KB sync OK.

### Phase 4 — Verify + close ✅

- [x] Run end-to-end: `cd products/youtube-crawler/backend && pytest` (workspace) → **112/112** in 0.40s. `cd mcp/noctusai && pytest tests/` → 738 passed / 4 failed (all 4 pre-existing platform issues: dev-team missing E2E, openai version drift across products, ERP monkey-patching, seed-version stamp drift — none caused by this project; see proposal §"Verification snapshot").
- [x] Frontend: `cd products/youtube-crawler/frontend && npx vite build` → ✓ built in 3.07s. No API contract change.
- [ ] Architect review: read the engineer's `findings.md`, decide whether to flip prior-phase improvements to FORMALIZED in `KB § PATTERNS/accept-with-rationale.md`. *(Architect-side step.)*
- [x] Phase proposal at `projects/seed-auth-deps-hardening/proposals/2026-05-06-end-of-project-bundle.md`.
- [ ] Auto-archive on close via `noctus.dev.archive`. *(Architect-side step at FF-merge time.)*

---

## 7. Open questions

1. **Should the deprecation warning use `warnings.warn(..., DeprecationWarning, stacklevel=2)` or raise `HTTPException` immediately?** — Recommend `warnings.warn`. Reason: any caller that currently uses `Depends(get_org_id)` is already broken (returns 422); the warning gives them the migration path without changing the (already-broken) status code. Raising would mask the existing 422 with a 500 and obscure the bug.
2. **Where exactly does the keeper-detector for `Depends(<broken_seed_dep>)` live?** — Out of scope here; that's the third defense layer and is delivered by `keeper-test-status-assertion` (Project 2) using the same AST infrastructure.

---

## 8. Dependencies & blockers

- **`make_get_current_user_org` shipped on origin/main** — verified at `seed/lib/backend/noctusai_lib/api/auth.py:231`. ✅
- **Workspace symlinks noc** — the workspace `products/youtube-crawler/` is in the workspace, but its `seed/lib/backend/...` is symlinked into noc. So changes to noc's seed propagate immediately to the workspace; no `pip install -e` re-run needed.

---

## 9. Success criteria

- YouTube Crawler workspace test suite green (94/94, same count). Status-code assertions in `test_upload_router.py` pass for the right reason (401 / 503 / 400, not 422).
- A grep `grep -rn "Depends(get_org_id\|Depends(get_user_client\|Depends(get_user_role" products/` returns **zero hits** in the noc tree (and the workspace by symlink).
- Importing `ProductDependencies.get_org_id` / `get_user_role` / `get_user_client(token)` from a fresh test prints a `DeprecationWarning` with a non-trivial migration message.
- `KB § PATTERNS/backend.md § Auth — canonical pattern` exists and is cross-referenced from CLAUDE.md.
- `bash scripts/verify-kb-sync.sh` passes.

---

## 10. How to use this plan

- Project owned by **the engineer running in `.claude/worktrees/seed-auth-deps-hardening/`**. The architect reviews + merges to main.
- Engineer authority: Write/Edit on noc (full access). Append to `findings.md`. File phase proposal at close. Make commits per phase (no push — architect pushes).
- Engineer brief: see the dispatch-time prompt; this PROJECT.md is the canonical spec.

---

## 11. Change log

| Date | Change | By |
|---|---|---|
| 2026-05-06 | Project filed from template after architect-side scoping | architect-agent |
| 2026-05-06 | Phase 1 ✅ — factory wired in workspace YouTube Crawler. Both routers refactored to `Depends(get_current_user_org)`; `_resolve_auth` deleted; OAuth callback switched to admin client (was silently broken too). Late-binding lambdas added in `app.dependencies` so test patches on `_db.get_*` reach call sites. Tests: 94/94 green. Drive-by: discovered the OAuth-callback `Depends(get_user_client)` was its own broken instance — fixed inline. | engineer-agent |
| 2026-05-06 | Phase 2 ✅ — frame-aware deprecation warning landed in `seed/framework/.../dependencies.py`. Initial design naively warned on every call → false-positives for the seed's own `team_router` imperative uses. Tightened to `_warn_if_fastapi_caller(qualname)` that walks one frame up and fires ONLY when caller's `__name__ == "fastapi.dependencies.utils"`. New regression suite at `tests/test_dependencies_deprecation.py` (4 tests covering imperative-silent / fastapi-warn / non-fastapi-silent / top-level-no-op). All test suites green: seed/framework 37/37, seed/product 31/31, workspace 112/112. | engineer-agent |
| 2026-05-06 | Phase 3 ✅ — three-way sync. Replaced `KB § PATTERNS/backend.md § Auth` with full canonical-pattern doc (factory wiring + why-it-works + anti-patterns + migration history); added §3 row to CLAUDE.md ("Wiring auth on a new product / route → KB pointer"); created `memory/feedback_auth_factory_pattern.md` + MEMORY.md index line. `bash scripts/verify-kb-sync.sh` → green. | engineer-agent |
| 2026-05-06 | Phase 4 ✅ — verification + close. Workspace 112/112, seed/framework 37/37, seed/product 31/31, frontend build green, MCP 738/4-failed (all 4 pre-existing platform issues not caused by this project). End-of-project bundle filed at `proposals/2026-05-06-end-of-project-bundle.md` covering applied work + 5 deferred follow-ups (cross-product rollout, seed team_router migration, keeper-detector, shadcn UI absorption, ProductDependencies eventual deletion). Architect-side review + auto-archive pending FF-merge. | engineer-agent |
