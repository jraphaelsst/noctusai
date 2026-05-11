# Proposal: Phase 1 seed-absorption follow-ups (PF + ERP shared seams)

**Agent:** claude-opus-4-7
**Origin:** project:personal-finance-wiring:phase-1
**Generated:** 2026-05-04
**Severity:** medium
**Effort:** medium
**Affected products:** personal-finance, erp-imobiliario
**Status:** pending

---

## 1. Context

Phase 1 of `personal-finance-wiring` (per the project §6 Phase 1 sub-tasks) was tasked with adopting seed-seam gifts surfaced in §5.2.6: a `make_get_current_user_org` factory promised at master batch B1, and an audit of the AI-plumbing wrappers (`_persist_indicator` / `_require_openai` / `check_openai_configured`) shared between PF and ERP at N=2. The 2026-05-04 user resolution of master Q3 placed PF in **standalone mode** — the parent `products-wiring-rollout` is archived, B1 is no longer running, and PF's dispatch scope is `products/personal-finance/**` (seed/ and other-product files are explicitly out of scope). This proposal carries the seed-shape designs forward so a future cross-product project can pick them up cleanly. No PF code is changed by this proposal — only documents seed gaps and the absorption shape.

---

## 2. Situation

Two cross-product duplications survive the Phase 1 audit:

1. **`get_current_user_org` shadow.** `products/personal-finance/backend/app/dependencies.py:17` defines an async dep that returns `(user, token, org_id)` and raises HTTPException 403 if `org_id` is missing. ERP at `products/erp-imobiliario/backend/app/dependencies.py:28` defines `get_org_id(user, *, required: bool = False) -> Optional[str]` — same `(user.user_metadata or {}).get("org_id")` resolution body, different return shape (Optional + raise-on-required vs. tuple + always-raise). PF has 90 callsites; ERP has its own count. **`noctusai_lib.api.auth` does NOT export a `make_get_current_user_org` factory** — only `make_require_role`. Verified by reading `seed/lib/backend/noctusai_lib/api/auth.py`.

2. **AI-plumbing wrappers (N=2).** `products/personal-finance/backend/app/routers/ai.py:17,29` and `products/erp-imobiliario/backend/app/routers/ai.py:20,43` define byte-for-byte identical `_persist_indicator` and `_require_openai` (modulo `schema=` arg + ERP's `@limiter.limit` decorator). `products/personal-finance/backend/app/services/ai_service.py:29` and `products/erp-imobiliario/backend/app/services/ai_service.py:24` both define `check_openai_configured(org_id) -> bool` as a one-line wrapper around `noctusai_lib.config.credentials.resolve_credential("openai_api_key", org_id)`. **`noctusai_lib.domain.ai` exports `persist_output` (used directly)** but does NOT expose `safe_persist_indicator` (with try/except + persist_error fallback) or a `require_credential_or_422` HTTP helper. Verified by reading `seed/lib/backend/noctusai_lib/domain/ai/__init__.py` + `outputs.py` + `config/credentials.py`.

The N=2 recurrence rule (`KB § PATTERNS/project-execution.md § 2.7`) fires for both: triage time is now. Standalone mode means PF cannot ship the seed change itself.

---

## 3. Proposed Solution

### 3.1 Linkage — why this solution fits this situation

The two duplications share a shape: each product re-implements a thin convenience around an existing seed primitive (`deps.get_org_id` + auth tuple; `persist_output` + `resolve_credential`). The fix is not a rewrite — it is a small surface extension on the seed side that lets each product's local helper become a one-line passthrough or be deleted entirely. Pushing the wrapper bodies into seed eliminates drift risk between PF and ERP (the bodies are already drifting — ERP added `@limiter.limit` to `_persist_indicator` at some point; PF didn't) without forcing a refactor of the product-specific call sites.

### 3.2 Application instructions

**File 1 — `noctusai_lib.api.auth.make_get_current_user_org` factory:**

1. Add to `seed/lib/backend/noctusai_lib/api/auth.py` after `make_get_current_user`:
   ```
   def make_get_current_user_org(
       get_current_user_fn,
       get_org_id_fn,
       *,
       required: bool = True,
       missing_status: int = 403,
       missing_detail: str = "Usuario sem organizacao associada",
   ):
       """Factory: returns an async dep that resolves (user, token, org_id) from
       a Header(Authorization). When required=True, raises HTTPException with the
       given status/detail; when required=False, org_id may be None.
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
2. Re-export from `noctusai_lib.api.auth.__all__` if such a list exists (none currently — file uses implicit public surface; no change needed).
3. Add tests at `seed/lib/backend/tests/api/test_auth_make_get_current_user_org.py`: required=True + missing → 403; required=False + missing → (user, token, None); happy path → (user, token, org_id).
4. Migrate PF: replace `app/dependencies.py:17-25` body with `get_current_user_org = make_get_current_user_org(get_current_user, deps.get_org_id, required=True, missing_status=403, missing_detail="Usuario sem organizacao associada")`. 90 callsites unchanged (they only consume the function name). Re-run PF pytest — expect 584+10 baseline preserved.
5. Migrate ERP: ERP's `get_org_id(user, *, required=False)` is the dual of PF's. ERP currently has its `get_current_user_org` shape (verify file) — refactor to call `make_get_current_user_org(get_current_user, get_org_id, required=False)`. Run ERP pytest.

**File 2 — `noctusai_lib.domain.ai.safe_persist_indicator`:**

1. Add to `seed/lib/backend/noctusai_lib/domain/ai/outputs.py` (or new `helpers.py`):
   ```
   def safe_persist_indicator(
       db,
       *,
       schema: str,
       ref_type: str,
       ref_id: str,
       out: dict,
       logger: logging.Logger | None = None,
   ) -> dict:
       """Wrap an AIOutput-shaped service dict into AIOutput + persist; on failure
       returns the would-have-inserted payload with `id=None` and `persist_error=str(e)`.
       Non-fatal — the indicator just won't show until next run; logger.warning surfaces.
       """
       output = AIOutput(
           ref_type=ref_type, ref_id=ref_id,
           kind=out["kind"], label=out["label"],
           score=out.get("score"), chip=out.get("chip"),
           explanation=out.get("explanation"), confidence=out.get("confidence"),
           model_version=out.get("model_version"), prompt_version=out.get("prompt_version"),
       )
       try:
           return persist_output(db, schema=schema, output=output)
       except Exception as e:
           if logger is not None:
               logger.warning("ai.persist_indicator failed for %s/%s: %s", ref_type, ref_id, e)
           return {**output.to_insert_payload(), "id": None, "persist_error": str(e)}
   ```
2. Re-export from `noctusai_lib.domain.ai.__init__`.
3. Migrate PF `routers/ai.py:29-48` to one-line call: `_persist_indicator = lambda db, ref_type, ref_id, out: safe_persist_indicator(db, schema="personal-finance", ref_type=ref_type, ref_id=ref_id, out=out, logger=logger)` OR delete the wrapper and inline the call at the 3 callsites.
4. Migrate ERP `routers/ai.py:20-40` similarly (schema="erp"). ERP retains the rate-limit decorator at the endpoint level, not on the helper.
5. Tests at `seed/lib/backend/tests/domain/ai/test_safe_persist_indicator.py`: happy path returns persisted dict; persist_output raising returns payload with `id=None` + `persist_error` key.

**File 3 — `noctusai_lib.api.errors.require_credential_or_422`:**

1. Add to `seed/lib/backend/noctusai_lib/api/auth.py` (HTTP-layer concern, lives in `api/`):
   ```
   def require_credential_or_422(
       key: str,
       org_id: Optional[str] = None,
       *,
       detail: str | None = None,
   ) -> str:
       """Resolve a credential or raise HTTPException 422 with a configurable message.
       Default detail: 'Credential {key} not configured.' Returns the credential value."""
       value = resolve_credential(key, org_id)
       if not value:
           raise HTTPException(
               status_code=422,
               detail=detail or f"Credential {key} not configured.",
           )
       return value
   ```
   (`resolve_credential` import from `noctusai_lib.config.credentials`.)
2. Migrate PF `routers/ai.py:17-26` `_require_openai` to `_require_openai = lambda org_id: require_credential_or_422("openai_api_key", org_id, detail="OpenAI API Key não configurada. Acesse Configurações > Chaves de API para configurar.")` OR delete + inline.
3. Migrate ERP equivalent (same detail string).
4. Drop `check_openai_configured` from PF + ERP `services/ai_service.py` if no other callers (verify with grep).

### 3.3 Seed APIs / shared lib involved

- `noctusai_lib.api.auth.make_get_current_user_org` — new factory; replaces PF `dependencies.py:17` + ERP `get_current_user_org`.
- `noctusai_lib.domain.ai.safe_persist_indicator` — new helper; replaces PF + ERP `_persist_indicator`.
- `noctusai_lib.api.auth.require_credential_or_422` — new helper; replaces PF + ERP `_require_openai`.
- `noctusai_lib.api.auth.make_require_role` — already shipped; PF declines to adopt (no PF-router-side role gating; accepted-with-rationale).

### 3.4 Risks before applying

- **Factory return-shape divergence**: PF expects tuple `(user, token, org_id)` always-with-org; ERP expects scalar `Optional[str]`. The factory must keep both shapes' callers green — the proposed `(user, token, org_id|None)` tuple with `required=False` covers ERP; ERP's `get_org_id` callers (90 in PF, similar in ERP) need a separate audit. Check ERP `dependencies.py` for `get_current_user_org` shape vs. raw `get_org_id` shape before migrating ERP.
- **ERP `@limiter.limit` decorator**: ERP's `_persist_indicator` is invoked from rate-limited endpoints — verify the decorator sits at endpoint level, not on the helper, before deleting the wrapper.
- **Test side-effects**: factory's `Header(...)` default uses FastAPI's Header dependency — must be imported at the seed level, not at call site. Verify by running the seed tests.
- **Mass-replace risk**: PF's 90 callsites of `get_current_user_org` are by name only — the factory result is bound to the same name, so callsites stay untouched.

### 3.5 Alternatives considered

- **Keep PF + ERP local wrappers as accept-with-rationale**: at N=2 the rule allows it, but the bodies are already drifting (`@limiter.limit` divergence above) and the recurrence rule's whole point is to catch this before N=3+. Reject.
- **Inline the seed surface into the existing `get_org_id` / `persist_output`**: would require those primitives to take more args (e.g. `persist_output(..., on_error="return_payload")`); breaks the single-responsibility shape of the existing helpers. Reject — wrappers are correct here.
- **Move PF `_persist_indicator` directly into `noctusai_lib.domain.ai.outputs.py` as a method on `AIOutput`**: ties HTTP-error logging to a domain object that should not know about FastAPI/HTTPException. Reject — `safe_persist_indicator` is a freestanding helper.

---

## 4. Effects

- **Behavior:** identical end-to-end — same routes, same DTOs, same error codes. Only the implementation moves to seed.
- **Risk profile:** safer — N=2 drift surface eliminated; future N=3 (e.g. daily-life adopting AI features) inherits one helper instead of copying.
- **Ergonomics:** clearer — fresh agents reading `routers/ai.py` see one-line passthroughs instead of 30 lines of try/except + AIOutput construction.
- **Coverage:** seed gets 3 new test files (~20 tests); product test counts unchanged.

---

## 5. Acceptance Criteria

- [ ] `noctusai_lib.api.auth.make_get_current_user_org` shipped + tested.
- [ ] `noctusai_lib.domain.ai.safe_persist_indicator` shipped + tested.
- [ ] `noctusai_lib.api.auth.require_credential_or_422` shipped + tested.
- [ ] PF migrated; PF pytest 584+10 baseline preserved.
- [ ] ERP migrated; ERP pytest baseline preserved.
- [ ] `python mcp/noctusai/cli.py --review --product personal-finance` → 0 issues.
- [ ] `python mcp/noctusai/cli.py --review --product erp-imobiliario` → no new keeper findings tied to these wrappers.
- [ ] `noctus.dev.scan_cross_product_helpers` no longer surfaces `_persist_indicator` / `_require_openai` / `check_openai_configured` at N=2.
- [ ] `KB § PATTERNS/accept-with-rationale.md` cleared of any stale entry for these helpers (none expected; absorption catalog filed at master).

---

## 6. Related files

- `seed/lib/backend/noctusai_lib/api/auth.py:94+` — add `make_get_current_user_org` after `make_get_current_user`.
- `seed/lib/backend/noctusai_lib/domain/ai/outputs.py` — add `safe_persist_indicator` (or new helpers.py).
- `seed/lib/backend/noctusai_lib/domain/ai/__init__.py:54` — re-export `safe_persist_indicator`.
- `products/personal-finance/backend/app/dependencies.py:17` — replace body with factory call.
- `products/personal-finance/backend/app/routers/ai.py:17,29` — drop wrappers or one-line passthrough.
- `products/personal-finance/backend/app/services/ai_service.py:29` — drop `check_openai_configured` if no other callers.
- `products/erp-imobiliario/backend/app/dependencies.py:28` — verify shape; refactor to factory.
- `products/erp-imobiliario/backend/app/routers/ai.py:20,43` — drop wrappers or one-line passthrough.
- `products/erp-imobiliario/backend/app/services/ai_service.py:24` — same as PF.

---

## 7. Standalone-mode follow-up dispatches needed

Because PF dispatched standalone (parent `products-wiring-rollout` archived 2026-05-04), the orchestrator needs three follow-up projects to land the seed changes:

1. **`make-get-current-user-org-factory`** — seed gift covering File 1 above.
2. **`ai-plumbing-seed-absorption`** — seed gifts covering Files 2 + 3.
3. **`metas-domain-seed-absorption`** — Phase 0 §5.2.6 N=3 MUST-FORMALIZE (`useMetas` family + `criar_meta` family across PF + ERP + daily-life). This was the Phase 1 sub-task #6 file action — surfaced here because cross-product project filing is out of dispatch scope.

These three are independent and can be parallel-dispatched once PF wiring continues.
