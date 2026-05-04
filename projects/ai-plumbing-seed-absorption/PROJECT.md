# ai-plumbing-seed-absorption — Project Document

> **This is a living document, not a rigid checklist.** Revise as we learn.

- **Created:** 2026-05-04
- **Last updated:** 2026-05-04
- **Status:** Phase 0 → Phase 1 ready
- **Owner / stakeholders:** joaoraphaelsst (architect dispatcher) · claude-opus-4-7 (engineer-2-of-3)
- **Related docs:**
  - `products/personal-finance/projects/personal-finance-wiring/proposals/phase-1-seed-absorption-followups.md` (predecessor analysis — Files 2 + 3 of that proposal)
  - `KB § PATTERNS/seed-lib-layout.md`
  - `KB § PATTERNS/project-execution.md § 2.7 The recurrence rule`
  - `KB § 03-SEED-ARCHITECTURE.md § Verify-the-seed-ships-it test`
- **Project slug:** `ai-plumbing-seed-absorption` — cross-product seed gift, lives at `projects/<slug>/` (per scope rule in `KB § PATTERNS/project-execution.md §1`).
- **Branch:** `ai-plumbing-seed-absorption` (worktree at `noctusai-worktrees/ai-plumbing-seed-absorption/`).
- **Sister parallel projects:** `make-get-current-user-org-factory` (Engineer 1) + `metas-domain-seed-absorption` (Engineer 3) — dispatched same turn.

---

## 1. Context & Purpose

The `personal-finance-wiring` Phase 1 audit (closed 2026-05-04, standalone-mode) surfaced an **N=2 recurrence** in AI-plumbing wrappers: PF and ERP each ship local helpers `_persist_indicator(db, ref_type, ref_id, out) -> dict` and `_require_openai(org_id) -> None` that are **byte-for-byte identical** modulo the schema literal (`"personal-finance"` vs `"erp"`). The PF version has no rate-limit; the ERP version's enclosing endpoints carry a `@limiter.limit(...)` decorator at endpoint level. They are **already drifting** (ERP added a `# Persist failure is non-fatal` comment that PF never inherited). A third helper, `check_openai_configured(org_id) -> bool`, is duplicated in both `app/services/ai_service.py` files at one line each (a wrapper around `noctusai_lib.config.credentials.resolve_credential("openai_api_key", org_id)`).

The recurrence rule (`KB § PATTERNS/project-execution.md § 2.7`) at N=2 says: triage time. The triage outcome here is **formalize** — push the wrappers into seed-lib so any future AI-feature-shipping product (daily-life is the obvious next consumer) inherits one helper instead of copying. This project ships the seed surface only. **Wiring PF + ERP to consume it is out of scope** — those are follow-up cycles owned by `personal-finance-wiring` Phase 2 and an `erp-imobiliario-ai-plumbing-rewire` follow-up.

This project is one of three parallel engineers under the architect's branching-first orchestration. Sister branches address an unrelated factory (`make_get_current_user_org`) and the `useMetas` family. Zero file overlap by design.

---

## 2. Confirmed constraints

- **Scope = seed only** — `seed/lib/backend/noctusai_lib/**` + `seed/lib/backend/tests/**`. *(Sister engineers own non-seed files in their respective branches; cross-touch would race them.)*
- **No `products/` edits** — the predecessor's analysis is the source of truth; PF/ERP migration is filed but deferred. *(Prevents collision with sister engineers + keeps this branch's diff reviewable.)*
- **Rate-limit posture must stay flexible** — ERP applies `@limiter.limit("...")` at the **endpoint level**, not on the helper. The seed factor must NOT bake either choice; helpers stay rate-limit-agnostic and products keep using their existing endpoint decorators. *(Ruled out wrapping the seed factor in slowapi — would create a hard dep on slowapi for products that don't use it.)*
- **Non-fatal persist semantics preserved** — both PF and ERP swallow `persist_output` failures and return the would-have-inserted payload with `id=None` + `persist_error=str(e)`, plus a `logger.warning(...)`. The seed surface keeps that behavior identically. *(Production indicator UX: indicator just won't show until next run; not worth a 5xx.)*
- **HTTP-layer 422 on credential miss** — `_require_openai` raises HTTPException 422 with a Portuguese message routing the user to *Configurações > Chaves de API*. Seed surface preserves the message via a default that products can override. *(Default keeps PF/ERP's existing user-facing copy; override keeps the door open for future products with different copy / language.)*
- **AST-first** — Python source edits go through libcst per `KB § 01-PHILOSOPHY.md § AST-first`. *(For appended functions to existing modules, libcst's `cst.parse_module` + `body.extend` is the canonical shape; we use direct module-end appends only for new helper bodies on a verified-trailing-newline module — manual review confirms no formatter regressions.)*
- **Tests stay green** — `seed/lib/backend/tests/` must remain green; new tests added in `tests/domain/ai/test_safe_persist_indicator.py` and `tests/test_auth_credentials.py` (or co-located in `test_auth.py` if `make_require_role` is the sibling shape).

---

## 3. Design principles

1. **One absorption layer at a time.** This project ships the seed surface. Migrating consumers (PF + ERP) is a separate follow-up cycle so the diff reviewer doesn't conflate seed contract design with migration mechanics.
2. **Preserve byte-level behavior.** The two seed helpers must reproduce the existing PF + ERP behavior identically — same exception codes, same payload shapes, same warning-log copy — so the migration can be a one-line passthrough later.
3. **Keep helpers small + freestanding.** No factories where a freestanding function suffices. `safe_persist_indicator` is freestanding (takes `db` + AIOutput fields + optional logger). `require_credential_or_422` is freestanding (takes key + org_id + optional detail). No need for `make_X(...)` factories — there's no per-product binding to defer.
4. **Logger injection over module-level logger.** Each product passes its own `logger` so warnings carry the product's logger name. Default-None is allowed for callers that don't care.

---

## 3a. Seed-first analysis (REQUIRED — the seed is every product's skeleton)

This project IS a seed-first absorption — the §3a checks confirm the design is correctly seed-bound.

1. **Is the contract identical for every product?** YES — both PF and ERP build the same `AIOutput` shape from the same dict keys, persist via the same `persist_output(db, schema=..., output=...)` chain, and apply the same try/except + `logger.warning` + `id=None+persist_error` fallback. Same for `_require_openai`: identical 422 + identical Portuguese detail string + identical `resolve_credential("openai_api_key", org_id)` resolution.
2. **Is the data source product-specific?** YES (the schema literal is) — but it's the only product-specific axis. Solved by passing `schema=` as an arg.
3. **Is the placement product-specific?** NO — this is server-side plumbing, not UI placement.
4. **Is the visibility / permission rule the same?** YES (same 422 on credential miss, same non-fatal swallow on persist failure).
5. **Does the seam already exist in seed?** PARTIAL — `noctusai_lib.domain.ai.persist_output` ships, `noctusai_lib.config.credentials.resolve_credential` ships. The **wrapper layer** (try/except + payload-shaping; HTTPException raise) does NOT ship. We add it.
6. **Default-on or opt-in?** OPT-IN — products import the helper when they want it; nothing changes for products without AI features.

**Litmus — per-product code count this design requires after migration:**

- [x] **0 lines** — both helpers become `from noctusai_lib.domain.ai import safe_persist_indicator` + `from noctusai_lib.api.auth import require_credential_or_422`; the local `_persist_indicator` / `_require_openai` definitions are deleted; callsites already use the same names so no edits there. The `schema=` arg flows through at callsite.

(Migration will land in follow-up cycles — those zero-out PF + ERP local code; this project ships the seed surface that makes the zero possible.)

**Phase plan implications:** §6 phases work IN seed (`seed/lib/backend/noctusai_lib/**` + `tests/`). No "for each product" walk — predecessor already did the audit, this project's deliverables are seed-only.

---

## 4. Scope

**In scope:**
- `noctusai_lib.domain.ai.safe_persist_indicator(db, *, schema, ref_type, ref_id, out, logger=None) -> dict` in `seed/lib/backend/noctusai_lib/domain/ai/outputs.py`. Re-exported from `noctusai_lib.domain.ai.__init__`.
- `noctusai_lib.api.auth.require_credential_or_422(key, org_id=None, *, detail=None) -> str` in `seed/lib/backend/noctusai_lib/api/auth.py` (sits next to `make_require_role` — also an HTTP-layer raise-on-violation helper).
- Tests: `seed/lib/backend/tests/domain/ai/test_safe_persist_indicator.py` + new test class in `seed/lib/backend/tests/test_auth.py` (`TestRequireCredentialOr422`) — co-located with `make_require_role` test class for proximity.

**Out of scope:**
- Migrating PF `routers/ai.py` + `services/ai_service.py` to the seed surface — owned by `personal-finance-wiring` Phase 2 follow-up (sister engineer is NOT doing this; PF is in standalone mode).
- Migrating ERP `routers/ai.py` + `services/ai_service.py` to the seed surface — owned by a future `erp-imobiliario-ai-plumbing-rewire` project. Not yet filed.
- The `check_openai_configured` one-line wrappers in PF + ERP `services/ai_service.py` — once `require_credential_or_422` ships, those one-liners are redundant. Deletion is a migration concern, deferred with the other migration tasks above.
- `make_get_current_user_org` factory — sister Engineer 1's scope.
- `useMetas` / `criar_meta` family absorption — sister Engineer 3's scope.

---

## 5. Architecture / Data Model

### 5.1 New surface: `safe_persist_indicator`

Location: `seed/lib/backend/noctusai_lib/domain/ai/outputs.py` (sits next to `persist_output`).

```python
def safe_persist_indicator(
    db,
    *,
    schema: Optional[str],
    ref_type: str,
    ref_id: str,
    out: dict,
    logger: Optional[logging.Logger] = None,
) -> dict:
    """Wrap an AIOutput-shaped service dict into AIOutput + persist; on failure
    returns the would-have-inserted payload with `id=None` and `persist_error=str(e)`.

    Non-fatal — the indicator just won't show until next run; logger.warning surfaces.
    """
```

Shape of `out` — the dict that AI services build. Keys consumed: `kind` + `label` (required), `score` + `chip` + `explanation` + `confidence` + `model_version` + `prompt_version` (all optional, all `.get(...)`-fetched). Extra keys are ignored (callers may carry e.g. `matched_categoria_id` for downstream merging — that's their concern, not ours).

Return semantics:
- **Happy path** → returns `persist_output(db, schema=schema, output=output)` directly.
- **Persist failure** → returns `{**output.to_insert_payload(), "id": None, "persist_error": str(e)}` and emits `logger.warning(...)` if `logger` is provided.

Re-exported from `noctusai_lib.domain.ai.__init__.__all__`.

### 5.2 New surface: `require_credential_or_422`

Location: `seed/lib/backend/noctusai_lib/api/auth.py` (sits after `make_require_role`).

```python
def require_credential_or_422(
    key: str,
    org_id: Optional[str] = None,
    *,
    detail: Optional[str] = None,
) -> str:
    """Resolve a credential or raise HTTPException 422 with a configurable message.

    Default detail: 'Credential {key} not configured.' Returns the credential value.
    """
```

- Resolves via `noctusai_lib.config.credentials.resolve_credential(key, org_id)`.
- Empty/None → `raise HTTPException(status_code=422, detail=detail or f"Credential {key} not configured.")`.
- Returns the resolved value (so callers can use it directly if useful).

PF/ERP migration callsite (later cycle):
```python
_require_openai = lambda org_id: require_credential_or_422(
    "openai_api_key",
    org_id,
    detail=(
        "OpenAI API Key não configurada. "
        "Acesse Configurações > Chaves de API para configurar."
    ),
)
```
…or inlined directly at endpoint top.

### 5.3 Tests

- `tests/domain/ai/test_safe_persist_indicator.py` — happy path; persist exception → payload + `id=None` + `persist_error`; logger=None is fine; logger non-None gets `.warning` call (assert via stub logger); minimum-keys `out` (only `kind`+`label`) survives; extra keys in `out` are ignored.
- `tests/test_auth.py::TestRequireCredentialOr422` — value present (mocked `resolve_credential`) → returns string; value None → raises 422 with default detail; value None + custom detail → raises 422 with custom detail; org_id=None passes through to resolver.

---

## 6. Implementation phases

### Phase 0 — Project filing ✅

- [x] Inspect predecessor proposal + worktree state
- [x] Verify byte-level identity claim across PF + ERP `_persist_indicator` / `_require_openai`
- [x] Confirm seed-lib placement: `domain/ai/outputs.py` + `api/auth.py`
- [x] Draft + commit PROJECT.md

**Improvements:** none identified at filing.

### Phase 1 — Seed surface + tests ✅

- [x] Add `safe_persist_indicator` to `seed/lib/backend/noctusai_lib/domain/ai/outputs.py`
- [x] Re-export from `noctusai_lib.domain.ai.__init__.__all__`
- [x] Add `require_credential_or_422` to `seed/lib/backend/noctusai_lib/api/auth.py` (after `make_require_role`)
- [x] Write `seed/lib/backend/tests/domain/ai/test_safe_persist_indicator.py` (9 tests)
- [x] Add `TestRequireCredentialOr422` to `seed/lib/backend/tests/test_auth.py` (5 tests)
- [x] Run seed-lib pytest — green (541 passed)
- [x] Commit Phase 1 → branch (no push)

**Improvements:**
- **Parallel-worktree venv shadow** — venv at `noctusai/venv` carries an editable install of `noctusai_lib` whose `MAPPING` resolves to whichever worktree last ran `pip install -e seed/lib/backend`. Running pytest from a sibling worktree silently picks the OTHER worktree's source tree → `ImportError` for new symbols (or worse: green-on-stale). Fixed defensively in `tests/conftest.py` — purges any meta-path finder whose `MAPPING["noctusai_lib"]` resolves outside the local `_LIB`. Generic; benefits every parallel orchestration. Worth surfacing to architect for `findings.md` under `in-flight-execution-rollout`.
- **Lazy import of `resolve_credential` inside `require_credential_or_422`** — added because `noctusai_lib.config.credentials` reaches into `integrations.database.make_supabase_client` at import-time, which is a heavy dep for products that don't gate any HTTP route on a credential. Lazy import keeps `noctusai_lib.api.auth` cheap to import. Documented inline; no further action.
- **`require_credential_or_422` lives in `api/auth.py`** — matches the `make_require_role` neighbor (HTTP-layer raise-on-violation). Revisit if N=2+ HTTP credential helpers ship; promote to `api/credentials.py` then.
- **Test stub `_RecordingChain`** — duplicated from `test_ai_outputs.py::_StubChain` (slightly extended for `raise_on_execute`). N=2 same-shape stub. Catalog as accept-with-rationale (test-fixture recurrence; a shared `seed/lib/backend/tests/_stubs.py` module is the obvious extraction at N=3+).

### Phase 2 — Project close

- [ ] Synthesize one phase proposal (if improvements emerged) — file via `noctus.dev.file_proposal(project="ai-plumbing-seed-absorption", ...)`
- [ ] Final commit + push branch (NOT main)
- [ ] Archive via `noctus.dev.archive` (the platform tool will move the project folder under `projects/absorbed-projects-batch/` per existing convention)

---

## 7. Open questions

1. **Should `safe_persist_indicator` live in `outputs.py` or a new `helpers.py`?** *(Recommendation: `outputs.py` — keeps the dataclass, persist primitive, and the safe-wrap helper in one cohesive file. New `helpers.py` only justified at N=3+ helpers; today this is N=1 wrapper.)* — decided during Phase 0.
2. **Should `require_credential_or_422` live in `api/auth.py` or new `api/credentials.py`?** *(Recommendation: `api/auth.py` — the file already houses `make_require_role` (the other HTTP-layer raise-on-violation helper); adding a tiny new file for one function is overkill at N=1. Revisit if N=2+ HTTP credential helpers ship.)* — decided during Phase 0.

---

## 8. Dependencies & blockers

- **None blocking.** Worktree isolated; pre-commit hook installed; no parallel edits in scope (sister engineers are in their own worktrees).
- **PYTHON env hint** — pre-commit hook may need `PYTHON=/Users/rapha/Documents/repository/NoctusAI/noctusai/venv/bin/python` if `ModuleNotFoundError` surfaces.

---

## 9. Success criteria

- `noctusai_lib.domain.ai.safe_persist_indicator` shipped; importable from `noctusai_lib.domain.ai`.
- `noctusai_lib.api.auth.require_credential_or_422` shipped; importable from `noctusai_lib.api.auth`.
- `seed/lib/backend/tests/` green (preserved + new tests both pass).
- Phase 1 commit on branch; no push to main.
- Project archived; report returned to architect.

---

## 10. How to use this plan

- Live-tick sub-tasks as they complete.
- All work is in seed; **never** edit `products/` from this branch.
- Push branch-to-branch only — `git push origin ai-plumbing-seed-absorption`. Architect handles merge.

---

## 11. Change log

| Date | Change | By |
|---|---|---|
| 2026-05-04 | Initial PROJECT.md drafted from predecessor proposal Files 2 + 3 | claude-opus-4-7 (engineer-2-of-3) |
| 2026-05-04 | Phase 0 ✅ — committed `33a7716` (PROJECT.md filed) | claude-opus-4-7 |
| 2026-05-04 | Phase 1 ✅ — `safe_persist_indicator` + `require_credential_or_422` shipped + 14 new tests; 541 total seed-lib tests passing. Fixed parallel-worktree venv shadow in `tests/conftest.py`. | claude-opus-4-7 |
