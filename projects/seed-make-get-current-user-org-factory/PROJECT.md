# seed-make-get-current-user-org-factory — Project Document

> **STATUS: CLOSED at Phase 0 (Verify-the-seed-ships-it gate).** The brief's premise is invalidated end-to-end: the factory + UserOrg-equivalent shape + tests + KB section + memory entry all ALREADY ship. No seed-side work remained. Phase 0 audit fired loudly per `feedback_phase_zero_audit`; scope revised; per-product adoption (explicit OUT OF SCOPE) parked for follow-up wiring projects.

- **Created:** 2026-05-11
- **Last updated:** 2026-05-11
- **Status:** ✅ Closed — gate-invalidated at Phase 0 (no seed work required; deliverables pre-existing)
- **Owner / stakeholders:** Engineer WWW (architect dispatch)
- **Related docs:**
  - `seed/lib/backend/noctusai_lib/api/auth.py` — factory at lines 231-310
  - `seed/lib/backend/tests/test_auth.py` — `TestMakeGetCurrentUserOrg` class lines 302-440
  - `KNOWLEDGE-BASE/CONTEXT/PATTERNS/backend.md` — `## Auth — canonical pattern` (lines 17-148)
  - Memory: `feedback_auth_factory_pattern.md` (26 lines, covers factory + custom-JWT carve-out + 3-layer defense)
  - Predecessor project (referenced by KB §142): `make-get-current-user-org-factory` (2026-05-04, PF Phase 1 absorption)
  - Sibling rollout project (referenced by memory §22): `seed-auth-deps-cross-product-rollout` (per-product adoption follow-up)
- **Project slug:** `seed-make-get-current-user-org-factory`

---

## 1. Context & Purpose

The architect dispatched this engineer to ship the N=5 MUST-FORMALIZE seed adapter for `make_get_current_user_org` after PF Phase 1 + ERP/therapy/daily-life/mailing Phase 0 audits surfaced imperative auth-triple usage in 5 products. The premise was that the seed lacked the factory.

**Phase 0 audit (Verify-the-seed-ships-it gate) invalidated the premise:**

The factory **already ships** at `seed/lib/backend/noctusai_lib/api/auth.py:231-310`, shipped 2026-05-04 by the `make-get-current-user-org-factory` predecessor project (referenced in `KB § PATTERNS/backend.md § Migration history` line 142). Comprehensive tests already exist (8 methods in `TestMakeGetCurrentUserOrg`, lines 302-440). The KB has a full `## Auth — canonical pattern` section. The memory entry already covers the factory + 3-layer defense + AdConnect custom-JWT carve-out.

What the N=5 audits actually surfaced is **per-product adoption gap**: ERP / therapy / daily-life / mailing / PF have NOT migrated their `dependencies.py` to consume the factory. PF is the most striking — the docstring claims PF as the N=2 trigger (line 247-250 of auth.py), but PF's `app/dependencies.py:17-21` still ships a hand-rolled imperative `get_current_user_org`. The factory's adopters are: `products/seed/`, `products/youtube-crawler/`, `products/imobi-scheduling/`, and `templates/product-seed/` — i.e. all greenfield products instantiated AFTER the factory shipped. Migration of pre-existing products (PF + ERP + therapy + daily-life + mailing) is the work that remains, and the brief explicitly marks it OUT OF SCOPE.

**Why is this dispatch?** Most likely: the architect dispatched this brief without first running the Verify-the-seed-ships-it test on the predecessor's output. The pre-dispatch test is mandated by `CLAUDE.md §1 Verify the seed ships it`. Engineer-side gate-fire is the correct safety net per `feedback_safety_nets_become_learnings`.

---

## 2. Confirmed constraints

- **Brief scope** — "ships the SEED adapter only". *(OOS marker means per-product migration is owned elsewhere.)*
- **Brief constraint** — "Extend, don't replace" existing seed tests. *(Reinforces: factory already exists with tests.)*
- **Brief mentions sibling** — `make_require_role(get_current_user_fn, get_user_role_fn)` exists. *(Correct — same shape, same file.)*
- **Brief presents canonical shape** — `make_get_current_user_org(get_current_user_fn, get_org_id_fn) -> Callable[..., UserOrg]`. *(The shipped factory returns `Callable[..., Tuple[user, token, org_id|None]]` — NOT a `UserOrg` Pydantic. The tuple shape is the canonical pattern that 4 adopters + the KB doc + the memory entry already encode.)*

---

## 3. Design principles

1. **Verify-the-seed-ships-it is a HARD gate before any "ship the seed adapter" work.** Reading the module's `__init__.py` exports + the concrete adapter file BEFORE locking the scope is what `CLAUDE.md §1 Verify the seed ships it` mandates. The brief skipped this gate; the engineer ran it and found the factory already ships.
2. **No `UserOrg` Pydantic — the tuple shape is canonical and locked.** The brief proposed a Pydantic value object as the return type. Doing so would: (a) invalidate `products/seed/`, `youtube-crawler/`, `imobi-scheduling/`, `templates/product-seed/` adopters whose call sites all destructure `user, token, org_id = auth`; (b) invalidate the KB code block at `backend.md` lines 60-72; (c) invalidate the memory entry's documented shape; (d) violate `feedback_no_quick_fixes` (fork the canonical pattern at the seed level instead of going up). The right shape is the existing tuple.
3. **Phase 0 invalidation is expansion-loud, not silent-skip.** Per `feedback_phase_zero_audit` — when the audit invalidates the brief, log the finding, revise the scope in-place, continue with whatever residual remains, do NOT silently mark "done".

---

## 3a. Seed-first analysis

The work was already seed-first by construction (a "seed adapter" dispatch). The Phase 0 audit confirmed it's already shipped, so this section is closed.

1. **Identical contract for every product?** YES — every product calls `make_get_current_user_org(get_current_user_fn, get_org_id_fn, ...)` once at `app/dependencies.py` module load.
2. **Data source product-specific?** Yes — each product injects its own `get_current_user_fn` (which knows its Supabase client) and `get_org_id_fn` (typically `lambda u: (u.user_metadata or {}).get("org_id")`).
3. **Placement product-specific?** No — universal seed-lib placement at `noctusai_lib/api/auth.py`.
4. **Visibility / permission rule same?** Yes — `required=True` raise-on-missing-org is the default; `required=False` for tuple-with-None branch.
5. **Seam already exists?** **YES** — exactly the seam this dispatch was about. Pre-existing at line 231.
6. **Default-on or opt-in?** Opt-in — each product binds explicitly in its own `dependencies.py`.

**Litmus — per-product code count:** 1 line per product (the `make_get_current_user_org(...)` call in `dependencies.py`). Tracked OOS.

---

## 4. Scope

**In scope (revised post-Phase 0 audit):**

- ✅ Verify-the-seed-ships-it gate run (read `auth.py` + `__init__.py` + grep adopters).
- ✅ Verify tests pass (baseline `34 passed` after `pytest-asyncio` installed in the verification venv).
- ✅ Verify KB section exists (`KNOWLEDGE-BASE/CONTEXT/PATTERNS/backend.md § Auth — canonical pattern`).
- ✅ Verify memory entry exists (`feedback_auth_factory_pattern.md`).
- ✅ File this PROJECT.md as a durable record of the Phase 0 gate-fire — so a future agent re-dispatched on the same premise can read this and STOP at the gate (vs re-running the audit).
- ✅ File `findings.md` capturing the slip + the safety-net activation pattern.
- ✅ Log a `phase_learnings` entry so the absence-of-rework is explicit, not silent.

**Out of scope (deferred, with destination):**

- Per-product migration of PF / ERP / therapy / daily-life / mailing `dependencies.py` to consume the factory — explicitly OOS per brief, lives in `seed-auth-deps-cross-product-rollout` (referenced in `feedback_auth_factory_pattern.md` line 22).
- Introducing a `UserOrg` Pydantic — refused per Design Principle 2 (would fork the canonical tuple shape that 4 adopters + KB + memory encode).
- Adding `make_get_current_user_org` to `seed/lib/backend/noctusai_lib/api/__init__.py` exports — currently consumers import from `.auth` directly per the pattern shipped by 4 adopters. Adding a re-export would be safe but is a nice-to-have, not a recurrence-rule fire. Captured in §3a Improvements below as an observation.

---

## 5. Architecture / Data Model

The pre-existing factory shape at `seed/lib/backend/noctusai_lib/api/auth.py:231-310`:

```python
def make_get_current_user_org(
    get_current_user_fn,
    get_org_id_fn,
    *,
    required: bool = True,
    missing_status: int = 403,
    missing_detail: str = "Usuario sem organizacao associada",
):
    """Returns async dep producing (user, token, org_id|None) tuple."""
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

Pre-existing tests at `seed/lib/backend/tests/test_auth.py:302-440` (`TestMakeGetCurrentUserOrg`):

- `test_happy_path_returns_tuple` — required=True, org present → `(user, token, org_id)`
- `test_required_true_raises_403_on_missing_org` — default 403 + Portuguese detail
- `test_required_false_returns_none_on_missing_org` — tuple-with-None branch
- `test_required_false_returns_tuple_on_present_org` — present org returned even with `required=False`
- `test_custom_missing_status_used` — `missing_status=400` matches ERP's local shape
- `test_custom_missing_detail_used` — detail override works
- `test_propagates_401_from_get_current_user` — auth failure short-circuits the resolver
- `test_resolver_receives_user_object` — validates the injection contract

---

## 6. Implementation phases

### Phase 0 — Verify-the-seed-ships-it audit ✅ (invalidated brief; closed project)

- [x] Read `seed/lib/backend/noctusai_lib/api/auth.py` end-to-end.
- [x] Find `make_get_current_user_org` factory at line 231 — fully implemented, with Pydantic-equivalent shape via tuple return.
- [x] Find pre-existing test class `TestMakeGetCurrentUserOrg` at line 319 — 8 test methods, full coverage matrix.
- [x] Grep adopters: `products/seed/`, `youtube-crawler/`, `imobi-scheduling/`, `templates/product-seed/`. 4 products + 1 template already consume.
- [x] Confirm KB `## Auth — canonical pattern` section already exists (lines 17-148 of `KNOWLEDGE-BASE/CONTEXT/PATTERNS/backend.md`).
- [x] Confirm memory `feedback_auth_factory_pattern.md` already covers the factory + 3-layer defense + AdConnect carve-out.
- [x] Run baseline tests: `pytest seed/lib/backend/tests/test_auth.py` → `34 passed` (after installing `pytest-asyncio` into the verification venv).
- [x] Decide: NO seed-side work remained. Scope reduced to "file this project as a Phase 0 invalidation record + findings + phase_learning".

**Improvements:**

- **Pre-dispatch Verify-the-seed-ships-it gate is a procedural gap.** The architect dispatched without running the gate first. The brief lists "Verify the seed ships it (gate)" as a step for the engineer — correct — but the gate is the architect's job pre-dispatch too. The N=5 audit findings about ERP/therapy/daily-life/mailing imperative auth ARE legitimate; the inference that they imply "missing seed adapter" was wrong. Right inference: "factory ships → 4 products adopted → 5 pre-existing products haven't migrated → file `seed-auth-deps-cross-product-rollout` for per-product wiring." That project is in fact referenced in memory (line 22). Architect-side: when a dispatch is about an N≥3 seed adapter, the architect should `grep make_<adapter_name>` BEFORE writing the brief. **Improvement candidate:** amend `KB § PATTERNS/branching-and-merging.md § 17.6` or the dispatch-brief template at `KB § PATTERNS/branching-and-merging.md` to require a pre-dispatch grep audit for any "ship the seed adapter X" brief. Saves an engineer dispatch + worktree cycle.
- **`noctusai_lib/api/__init__.py` doesn't re-export `make_get_current_user_org` (or `make_require_role`, `make_get_current_user`, `require_credential_or_422`).** Consumers import from `.auth` directly. This is fine and consistent across all 4 adopters, but a re-export would let consumers write `from noctusai_lib.api import make_get_current_user_org`. Nice-to-have, not a recurrence-rule fire. Cataloged here for whoever next touches the `api/` layer.
- **Test venv gap.** `seed/lib/backend/` ships no `.venv` and no products' venv has `pytest-asyncio`. I installed `pytest-asyncio` into `mcp/noctusai/.venv` for verification — that venv is shared infra, so the install is benign + useful for any future seed-lib test runs. A dedicated `seed/lib/backend/.venv` provisioned by `bash scripts/setup.sh` would close this gap. Candidate for `KB § GUIDES/setup.md`.
- **Brief proposed `UserOrg` Pydantic — would have forked the pattern.** Engineer refused per Design Principle 2. The brief author may have been working off a different design memory; the canonical shape is `Tuple[user, token, org_id|None]` and is well-encoded across 4 adopters + KB + memory. Cataloging as a near-miss in `accept-with-rationale.md` would be overkill (refusal happened before code touched); recording the reasoning here suffices.

*Phase proposal: not filed — Improvements above are procedural / meta-observations about the dispatch itself, not implementation refactor candidates. Recording them in this §6 block + findings.md is the right home, not a phase proposal (which targets the just-shipped code).*

---

## 7. Open questions

1. **Does the architect want `make_get_current_user_org` (+ siblings) re-exported from `noctusai_lib.api.__init__`?** Captured as an Improvement; needs architect-eyes decision. Default = no change (4 adopters already use the deeper import path).

2. **Should the dispatch-brief authoring methodology amend to require a pre-dispatch grep for "ship the seed adapter X" briefs?** Real candidate for three-way sync — the same shape recurrence could fire again. Filed as a finding for architect review.

---

## 8. Dependencies & blockers

None. The work that remains (per-product adoption) is owned by `seed-auth-deps-cross-product-rollout` per the memory entry.

---

## 9. Success criteria

- [x] Verify-the-seed-ships-it gate run + outcome documented.
- [x] Seed tests green (34 passed).
- [x] No product code touched (brief constraint honored).
- [x] No KB rewrite required (section already exists + comprehensive).
- [x] No memory rewrite required (entry already exists + comprehensive).
- [x] `findings.md` filed with 5-category structure.
- [x] `phase_learnings` entry logged so absence-of-rework is explicit.
- [x] PROJECT.md filed as a durable record of the gate-fire (future re-dispatch on the same premise reads this and STOPs at the gate).
- [x] Branch pushed (engineer's role; architect FFs at project close).

---

## 10. How to use this plan

This project closes at Phase 0. Architect should:

1. Read `findings.md` first.
2. Decide whether to amend the dispatch-brief methodology (Open Question #2 above).
3. Decide whether to surface the `noctusai_lib/api/__init__.py` re-export as an Improvement (Open Question #1).
4. FF-merge this branch to main per the project-close gate (`CLAUDE.md §1 Never auto-commit or push, except project gates`).
5. Optionally dispatch a follow-up engineer on `seed-auth-deps-cross-product-rollout` for the actual per-product adoption work the N=5 audits surfaced.

---

## 11. Change log

| Date | Change | By |
|---|---|---|
| 2026-05-11 | Engineer WWW dispatched on `seed-make-get-current-user-org-factory`; Phase 0 Verify-the-seed-ships-it gate fired loud (factory + tests + KB + memory all pre-existing); scope revised to documentation-only; `findings.md` + this PROJECT.md filed | Engineer WWW (Claude Opus 4.7) |
