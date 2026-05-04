# make-get-current-user-org-factory — Project Document

> Living document. Phase-by-phase by default. Single source of truth for progress.

- **Created:** 2026-05-04
- **Last updated:** 2026-05-04
- **Status:** Phase 0 ✅ filed → Phase 1 implementation
- **Owner / stakeholders:** joaoraphaelsst (architect) · Engineer 1 of 3 (dispatched in parallel: this branch + `ai-plumbing-seed-absorption` + `metas-domain-seed-absorption`)
- **Related docs:**
  - Predecessor proposal — `products/personal-finance/projects/personal-finance-wiring/proposals/phase-1-seed-absorption-followups.md` (File 1, lines 39-69)
  - `KB § 03-SEED-ARCHITECTURE.md § Verify-the-seed-ships-it test` — the principle this project flows from
  - `KB § PATTERNS/seed-lib-layout.md` — auth.py is in layer `api/` (HTTP-bound)
  - `seed/lib/backend/noctusai_lib/api/auth.py` — file the factory lives in (sibling of `make_require_role`)
- **Project slug:** `make-get-current-user-org-factory` (cross-product seed gift; lives at `projects/<slug>/`)
- **Branch:** `make-get-current-user-org-factory` (worktree: `noctusai-worktrees/make-get-current-user-org-factory/`)

---

## 1. Context & Purpose

`personal-finance-wiring` Phase 1 (the predecessor PF wiring project) ran the **Verify-the-seed-ships-it** test against `noctusai_lib.api.auth` and surfaced a gap: PF's `dependencies.py:17-25` defines a local `get_current_user_org` async dep returning `(user, token, org_id)` with hard-403 on missing org. ERP at `products/erp-imobiliario/backend/app/dependencies.py:28` defines `get_org_id(user, *, required=False) -> Optional[str]` — same `(user.user_metadata or {}).get("org_id")` resolution body, different request-time wrapping.

**N=2 → triage time.** The duplicated body (`(user.user_metadata or {}).get("org_id")` + the missing-org branch) is the recurrence; the right destination is `noctusai_lib.api.auth.make_get_current_user_org` — a factory that mirrors `make_require_role`'s shape (binds product-specific `get_current_user_fn` + `get_org_id_fn` once at module load; returns the request-time async dep).

This project ships the factory + tests in seed only. **PF + ERP wiring to consume the factory is OUT OF SCOPE here** — that's a follow-up cycle once seed-side ships.

---

## 2. Confirmed constraints

- **Scope (architect dispatch)** — `seed/lib/backend/noctusai_lib/api/auth.py` + `seed/lib/backend/tests/test_auth.py` (extend existing) only. *(No products/ changes; sister engineers handle other seed modules.)*
- **Both shapes accommodated** — `required=True` (PF default → 403 on missing) AND `required=False` (org_id may be None). *(Single tuple return shape `(user, token, org_id|None)` — cleaner than two factories + matches existing `make_require_role` 3-tuple convention.)*
- **Configurable error** — `missing_status: int = 403`, `missing_detail: str = "Usuario sem organizacao associada"`. *(PF uses 403 + Portuguese; ERP's local `get_org_id(required=True)` uses 400 — factory accommodates both.)*
- **No monkey-patching, no workarounds** — tests construct fakes via dataclasses + async lambdas (mirrors `TestMakeRequireRole`). *(Per `KB § 01-PHILOSOPHY.md § No workarounds`.)*
- **Tests stay green** — `cd seed/lib/backend && python -m pytest tests/test_auth.py -q` after each phase. *(End-of-session verify rule.)*
- **No `--no-verify`** on hooks. *(`PYTHON=...venv/bin/python` prefix for the worktree pre-commit ModuleNotFoundError gap; documented in Engineer 2's report.)*

---

## 3. Design principles

1. **Mirror `make_require_role`.** Same factory shape: bind `get_current_user_fn` + a pure resolver, return a request-time async dep that produces a 3-tuple. No new conventions.
2. **Single return shape.** `(user, token, org_id)` always — `required=False` lets `org_id` be `None`. Avoids the `Optional[str]` vs tuple branch the brief flagged; both products' callers unpack the tuple identically.
3. **Resolver injection over shape duplication.** `get_org_id_fn(user) -> Optional[str]` is product-supplied (ERP already has it; PF inlines it as a one-liner lambda). Factory body has zero `user_metadata` knowledge — purely composes auth + resolver + missing-branch.
4. **Test-side parity with existing factory tests.** `TestMakeGetCurrentUserOrg` mirrors `TestMakeRequireRole` (FakeUser dataclass, fake async `get_current_user_fn`, fake `get_org_id_fn`, asyncio tests).

---

## 3a. Seed-first analysis (REQUIRED — the seed is every product's skeleton)

1. **Is the contract identical for every product?** YES — every product reads `org_id` from `user_metadata` the same way; the 403-on-missing pattern is universal.
2. **Is the data source product-specific?** NO — `user.user_metadata.org_id` is set by core SSO at `/api/sso/session`; same shape across all products.
3. **Is the placement product-specific?** NO — request-time auth dep mounts at every router that needs `org_id`. Universal.
4. **Is the visibility / permission rule the same?** YES — missing org always blocks (403 PF / 400 ERP — configurable via `missing_status`).
5. **Does the seam already exist in seed?** NO — `make_require_role` covers role gating; `make_get_current_user` covers token validation. Org-id resolution sits between them. Predecessor proposal verified the gap by reading `noctusai_lib.api.auth`'s full surface.
6. **Default-on or opt-in?** OPT-IN — products that need org-scoping bind the factory; products that don't (e.g. core control-plane) skip it.

**Litmus — per-product code count this design requires:**

- [x] **1 line** — `get_current_user_org = make_get_current_user_org(get_current_user, lambda u: (u.user_metadata or {}).get("org_id"), required=True)` per consumer. *(Minimal — replaces PF's 9-line dep + lets ERP gain a parallel `get_current_user_org` in 1 line.)*

**Phase plan implications:** §6 phases work entirely in `seed/lib/backend/`. NO product touch. Correctly seed-bounded.

---

## 4. Scope

**In scope:**
- Add `make_get_current_user_org(get_current_user_fn, get_org_id_fn, *, required=True, missing_status=403, missing_detail=...)` to `seed/lib/backend/noctusai_lib/api/auth.py`.
- Append `TestMakeGetCurrentUserOrg` test class to existing `seed/lib/backend/tests/test_auth.py` (alongside `TestMakeRequireRole`) — covers required=True/missing→403, required=False/missing→tuple-with-None, happy path, custom `missing_status` + `missing_detail`.
- Re-verify `pytest tests/test_auth.py -q` green after each phase.

**Out of scope (deferred to follow-up cycle):**
- PF migration — `products/personal-finance/backend/app/dependencies.py:17-25` swap to factory call. *(Sister-engineer scope discipline; PF is in standalone-mode wiring per Engineer 2's predecessor.)*
- ERP migration — wiring ERP's existing `get_org_id` into a sibling `get_current_user_org`. *(Same — out of dispatch.)*
- `safe_persist_indicator` + `require_credential_or_422` — sister project `ai-plumbing-seed-absorption`.
- `useMetas` / `criar_meta` — sister project `metas-domain-seed-absorption`.

---

## 5. Architecture / Data Model

**File touched (1):** `seed/lib/backend/noctusai_lib/api/auth.py`
- Add `make_get_current_user_org` function after `make_require_role` (line 228) — same module-level position pattern as `make_get_current_user → make_require_role`.

**Test file touched (1):** `seed/lib/backend/tests/test_auth.py`
- Append `TestMakeGetCurrentUserOrg` class after `TestMakeRequireRole` (current EOF: line 296).

**Factory shape (final design):**

```python
def make_get_current_user_org(
    get_current_user_fn,
    get_org_id_fn,
    *,
    required: bool = True,
    missing_status: int = 403,
    missing_detail: str = "Usuario sem organizacao associada",
):
    """Factory: returns an async dep that resolves (user, token, org_id) from
    a Header(Authorization).

    - get_current_user_fn: async (authorization) -> (user, token) — typically
      the result of make_get_current_user(get_supabase_client).
    - get_org_id_fn: sync (user) -> Optional[str] — pure resolver
      (e.g. lambda u: (u.user_metadata or {}).get("org_id")).
    - required=True (default): raises HTTPException(missing_status, missing_detail)
      when org_id is absent. PF's current shape.
    - required=False: returns (user, token, None) on missing. ERP's optional shape.

    Returns: async (authorization: Optional[str]=Header(None)) -> (user, token, org_id|None)
    """
    async def get_current_user_org(authorization: Optional[str] = Header(None)):
        user, token = await get_current_user_fn(authorization)
        org_id = get_org_id_fn(user)
        if not org_id:
            if required:
                raise HTTPException(status_code=missing_status, detail=missing_detail)
            return user, token, None
        return user, token, org_id
    return get_current_user_org
```

---

## 6. Implementation phases

### Phase 0 — File the project ✅ (this commit)

- [x] Create `projects/make-get-current-user-org-factory/PROJECT.md` (this file)
- [x] Document seed-first analysis §3a + factory shape §5
- [x] Phase 0 commit: `feat(make-get-current-user-org-factory): Phase 0 — project filed`

**Improvements:** none identified at filing time.

### Phase 1 — Implement factory + tests

- [ ] Add `make_get_current_user_org(...)` to `seed/lib/backend/noctusai_lib/api/auth.py` after `make_require_role`
- [ ] Append `TestMakeGetCurrentUserOrg` class to `seed/lib/backend/tests/test_auth.py` covering:
  - `test_happy_path_returns_tuple` — `required=True`, org_id present → `(user, token, org_id)`
  - `test_required_true_raises_403_on_missing_org` — `required=True`, org_id None → HTTPException 403 with default detail
  - `test_required_false_returns_none_on_missing_org` — `required=False`, org_id None → `(user, token, None)`
  - `test_required_false_returns_tuple_on_present_org` — `required=False`, org_id present → `(user, token, org_id)`
  - `test_custom_missing_status_used` — `required=True`, `missing_status=400` → HTTPException 400
  - `test_custom_missing_detail_used` — `required=True`, custom detail string → HTTPException detail matches
  - `test_propagates_401_from_get_current_user` — get_current_user_fn raises 401 → resolver never runs, 401 surfaces
- [ ] Run `cd seed/lib/backend && python -m pytest tests/test_auth.py -q` → expect all green (existing 31 tests + 7 new = 38)
- [ ] Phase 1 commit: `feat(make-get-current-user-org-factory): Phase 1 — make_get_current_user_org factory + tests`

**Improvements:** captured live during steps; synthesized at phase close.

### Phase 2 — Project close

- [ ] Verify `pytest tests/test_auth.py -q` still green
- [ ] Update §11 Change Log with phase summaries
- [ ] Archive via `noctus.dev.archive(target_path="projects/make-get-current-user-org-factory", mode="project")` (if available via direct sandbox call) OR leave folder + flag for architect to archive
- [ ] Phase 2 commit: `chore(make-get-current-user-org-factory): Phase 2 — project close + archive`
- [ ] Push branch — `git push -u origin make-get-current-user-org-factory` (branch-to-branch only; main untouched)

---

## 7. Open questions

1. **Should ERP migrate to use this factory in this cycle?** — Recommendation: NO. Architect dispatch explicitly excluded products/. ERP's existing `get_org_id(user, required=False)` resolver stays in place — it's the perfect `get_org_id_fn` to pass into the factory if ERP ever adds a `get_current_user_org` shape. Deferred to follow-up cycle.
2. **Should the factory expose a separate sync `Optional[str]` return path?** — Recommendation: NO. The brief mentioned `Optional[str]` but the cleanest design is single-tuple-shape with `org_id|None` as the third element. ERP's existing sync `get_org_id` is a different concern (pure resolver) and stays product-local until DRY recurrence fires.

---

## 8. Dependencies & blockers

- **None.** Pure seed-side addition; no migrations, no product wiring, no external services.

---

## 9. Success criteria

- `noctusai_lib.api.auth.make_get_current_user_org` shipped, importable.
- `seed/lib/backend/tests/test_auth.py` green; new `TestMakeGetCurrentUserOrg` covers ≥6 cases (happy / required-true-raises / required-false-none / required-false-present / custom-status / custom-detail / 401-propagation).
- Branch `make-get-current-user-org-factory` pushed to `origin`; main untouched.
- `findings.md` (this project's root) captures slips/lessons across phases.

---

## 10. How to use this plan

- Phase 0 ✅ (filed); Phase 1 = implementation; Phase 2 = close.
- Each phase commits to branch `make-get-current-user-org-factory`. Final push is branch-to-branch (no `:main`).
- Architect merges branch into main after evaluation.

---

## 11. Change log

| Date | Change | By |
|---|---|---|
| 2026-05-04 | Phase 0 — project filed; seed-first §3a confirms zero-product-touch design; factory shape locked to `(user, token, org_id|None)` 3-tuple matching `make_require_role` convention | Engineer 1 (claude-opus-4-7) |
