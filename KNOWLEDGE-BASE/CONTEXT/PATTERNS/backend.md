# Backend Patterns

FastAPI + Supabase. All products follow the same shape.

## Layer structure

```
routers/ → services/ → schemas/ + dependencies.py, database.py
```

- **Routers** are thin. They parse input, call a service, return a response.
- **Services** hold business logic — calculations, state machines, orchestration.
- **Schemas** are Pydantic models (request/response shapes).
- **dependencies.py** wires `get_current_user`, `get_db`, `get_admin_client`, etc.
- **database.py** creates the DatabaseModule via the seed factory.

## Auth — canonical pattern

The canonical wiring is **`Depends(get_current_user_org)`** built once
per product via the factory `make_get_current_user_org` in
`noctusai_lib.api.auth`. Returns `(user, token, org_id)` to the route
body; only `authorization: Header(None)` is FastAPI-visible in the dep
signature, so the chain Just Works.

### Wire it once in `app/dependencies.py`

```python
from noctusai_seed import create_database_module, create_dependencies
from noctusai_lib.api.auth import (
    make_get_current_user,
    make_get_current_user_org,
)

_db = create_database_module(settings, schema="<product_schema>")
_deps = create_dependencies(_db)

# Late-binding lambda — re-resolves on every request so test patches
# on `_db.get_client` reach the closure (vs capturing the bound
# method at module load).
get_current_user = make_get_current_user(lambda: _db.get_client())

get_current_user_org = make_get_current_user_org(
    get_current_user,
    lambda u: (u.user_metadata or {}).get("org_id"),
    required=True,           # raise 403 if org_id missing; pass False for tuple-with-None
    # missing_status=400,    # ERP-imobiliario uses 400 instead of 403
    # missing_detail="...",  # override the Portuguese default if needed
)

# Late-binding wrappers for imperative call sites (NOT for Depends):
def get_user_client(token: str):
    return _db.get_client(token)


def get_admin_client():
    return _db.get_admin_client()
```

### Use it in routers

```python
from fastapi import APIRouter, Depends
from app.dependencies import get_current_user_org, get_user_client

router = APIRouter(prefix="/api/things")

@router.get("/")
async def list_things(auth: tuple = Depends(get_current_user_org)):
    user, token, org_id = auth
    db = get_user_client(token)              # imperative — fine
    return db.table("things").eq("org_id", org_id).execute().data
```

### Why this chains correctly

`make_get_current_user_org` returns an async function whose **only**
signature parameter is `authorization: Optional[str] = Header(None)`.
The `get_org_id_fn` resolver is closure-bound — invisible to FastAPI's
introspection. Result: FastAPI sees a single `Header()` param, treats
it correctly, runs the dep at request time, and the dep awaits
`get_current_user(authorization)` + resolves the org_id internally.

### Why `Depends(get_org_id)` / `Depends(get_user_client)` is broken

The seed framework's `ProductDependencies` exports these as plain
functions:

```python
# seed/framework/.../dependencies.py
class ProductDependencies:
    @staticmethod
    def get_org_id(user) -> str: ...                # positional `user`
    def get_user_client(self, token: str): ...      # positional `token`
```

When wired through `Depends(...)`, FastAPI introspects the function's
signature. Any parameter without `Depends()` / `Header()` / `Query()` /
`Body()` AND not of a routing-relevant type becomes a **required query
parameter**. Result: every authed request returns 422 with
`loc: ['query', 'user']` or `loc: ['query', 'token']`. The
401/403 paths inside these methods never run.

These methods now emit a `DeprecationWarning` when called by FastAPI's
dep-injection machinery (frame check on `fastapi.dependencies.utils`).
Imperative use (`deps.get_org_id(user)` from a service or route body)
remains silent and continues to work — only the `Depends(...)`-wired
shape is broken.

### OAuth-callback shape (no JWT context)

OAuth redirect endpoints carry no Authorization header, so the
factory dep doesn't apply. Use `get_admin_client()` (RLS bypass) and
bind the tenant via the opaque `state` token (`f"{org_id}:{nonce}"`)
parsed in the callback body. RLS bypass is bounded by state-token
validity, not blanket trust.

### Late-binding rule

Pass `lambda: _db.get_client()` to `make_get_current_user`, NOT
`_db.get_client` (the bound method). The bound-method reference is
captured at module load → the conftest's later
`patch.object(_db, "get_client", ...)` doesn't reach it. The lambda
re-resolves on every request, so both production and test paths see
the right client.

### Anti-patterns

- ❌ `Depends(get_org_id)` / `Depends(get_user_client)` /
  `Depends(get_user_role)` — broken (positional args become query
  params); fires a `DeprecationWarning`.
- ❌ Imperative `_resolve_auth(authorization)` helpers per product —
  N=2+ recurrence, the factory IS the absorption.
- ❌ Capturing `_db.get_client` (bound method) at module load and
  passing it to the factory — breaks test patching.
- ❌ Annotating `-> None` on FastAPI routes with
  `status_code=204` — `fastapi==0.115` trips an assertion. Always
  pass `response_model=None` explicitly on 204 routes (see "204
  response model gotcha" below).

### Migration history

- 2026-05-04: `make_get_current_user_org` shipped to
  `noctusai_lib.api.auth` (predecessor project
  `make-get-current-user-org-factory`).
- 2026-05-06: `seed-auth-deps-hardening` Phase 1 wired the workspace
  YouTube Crawler product end-to-end; Phase 2 added the
  frame-aware deprecation warning. Cross-product rollout (PF /
  Therapy / ERP / etc.) deferred to a follow-up project.

## SSO

- `resolve_sso_role(user)` checks:
  1. `org_role` — owner/admin → `platform_admin`.
  2. `noctus_role` — admin → `platform_admin`.
- Frontend helper: `resolveSSORoles()` → `{ isSSO, isProductAdmin }`.

## 7-role hierarchy

`owner, admin, manager, member, viewer, dev, test`.

- Constants in `noctusai_lib/roles.py`.
- `dev` + `owner` see in-development pages.
- `admin` + `owner` manage team + billing.
- `coordenador` (ERP-specific) = team leader (reused for Metas).

## Page status

- Table `status_pagina` per schema: `producao | desenvolvimento | desativado`.
- Frontend hooks: `usePageStatus()` + `filterNavByPageStatus()`.
- Dev/owner see dev-status pages; others don't.

## Invitations

- Module: `noctusai_lib/invitations.py` → `create_invitation`, `validate_invitation`, `accept_invitation`, `cancel_invitation`.
- Email via `send_product_invitation_email()`.
- Every product ships `routers/team.py` (auto-generated by seed framework).
- Therapy extends with invite types + patient binding.

## Responses

Use the helpers from `noctusai_lib.responses`:
- `success_response(data)` → `{data: ...}`
- `paginated_response(data, total, page, page_size)` → `{data, pagination}`
- `ok_response(message)` → `{ok: true, message}`

## N+1 zero tolerance

- Reads: `.in_("id", ids)` — batch fetch.
- Writes: `.insert(rows)` — batch insert.
- **Never** loop `db.table(...)` inside a request handler.

If you need to fetch related data for N parents, gather parent IDs first, then one `.in_()` per related table.

## Router → Service discipline

- Business logic belongs in `services/*.py`, not `routers/*.py`.
- Routers should be <30 lines in most cases.
- Services receive dependencies explicitly — no globals.

## RLS

- All schemas use `(SELECT auth.uid())` (not bare `auth.uid()` — the subquery is cached per-statement, bare form is re-evaluated per-row).
- All SECURITY DEFINER functions include `SET search_path` to prevent search-path hijacking.
- Service role bypasses RLS via `get_admin_client()`. Use only when necessary.

## Provisioning

Trigger `on_license_change` auto-provisions product defaults (tables, seed rows, permissions) when a tenant adds a product license.

## Health / team / notifications — do not reimplement

These come from the seed framework (`_create_health_router`, `_create_team_router`, `_create_notificacoes_router`). Products get them automatically via `create_product_app()`.

## FastAPI dependency factories with module-level injection (2026-04-27)

Some seed-lib features expose **product-mounted FastAPI dependencies** — callables that products use via `Depends(...)` on their router endpoints. Examples shipped today:

| Helper | Module | Purpose |
|---|---|---|
| `noctusai_lib.ai.consent.consent_required(feature_key)` | `ai/consent.py` | Router-level X6 consent guard (HTTP 412 if not granted). |
| `noctusai_lib.llm.budget.enforce_budget(org_id)` | `llm/budget.py` | Pre-dispatch cost guard inside `chat_completion` (not `Depends`-mounted but uses the same module-level injection wiring). |

These helpers share a structural shape — **module-level injection** — that future similar helpers should follow.

### The boot-order trap

Routers are imported (and their `@router.<verb>(...)` decorators evaluated) **before** `create_product_app(...)` runs. If a factory like `consent_required(feature_key)` does early validation at call time — e.g. `if not is_module_configured(): raise RuntimeError` — it will crash router imports, because `configure_X_module(...)` is called *inside* `create_product_app(...)` *after* the routers have been imported.

**Caught during `consent-guard-rollout` Phase 2 (2026-04-27):** the Phase 1 seed-lib helper `consent_required(feature_key)` did a fail-fast `is_consent_module_configured()` check at factory-call time. Mailing's first attempt to wire it crashed at import — `app/routers/ai.py` couldn't load because the `Depends(consent_required("..."))` line raised before `create_product_app(...)` had a chance to wire the module.

### The pattern (use this for any new FastAPI dep factory)

1. **Module-level state is `None` by default.** Two private module-level slots — one for the FastAPI dep that resolves the user, one for the admin-client factory (or whatever the helper needs).

   ```python
   _get_current_user_dep: Optional[Callable[..., Any]] = None
   _admin_client_factory: Optional[Callable[[], Any]] = None
   ```

2. **`configure_X_module(*, get_current_user, admin_client_factory)`** is the wiring function. It assigns the module-level slots. Called inside `noctusai_seed.app.create_product_app(...)` once per process (when the relevant `settings.X_gating` flag is on, default True for most).

   ```python
   def configure_consent_module(*, get_current_user, admin_client_factory):
       global _get_current_user_dep, _admin_client_factory
       _get_current_user_dep = get_current_user
       _admin_client_factory = admin_client_factory
   ```

3. **The factory itself is lenient at call time.** It returns the dep regardless of whether the module is configured. **All checks happen at request time** inside the returned dep.

   ```python
   def consent_required(feature_key: str):
       async def _dep(authorization: Optional[str] = Header(None)) -> None:
           # Late-binding config check — runs at request time.
           if not is_module_configured():
               raise RuntimeError("configure_consent_module(...) was not called")
           user_dep = _get_current_user_dep
           admin_factory = _admin_client_factory
           # ... resolve user, do the check, raise the right exception or pass.
       _dep.__name__ = f"consent_required__{feature_key.replace('.', '_')}"
       return _dep
   ```

4. **Don't capture references inside the factory at call time.** Read `_get_current_user_dep` / `_admin_client_factory` at REQUEST time inside the dep. This means reconfiguration mid-process (rare; only happens in tests) takes effect immediately. The cost is one indirection per request, which is negligible.

5. **Dep signature uses primitives, not `Depends(...)` indirection.** The dep takes `authorization: Optional[str] = Header(None)` directly and manually invokes the configured `get_current_user(authorization=...)`. **Do not** use `auth = Depends(_get_current_user_dep)` in the signature — it forces FastAPI to resolve `_get_current_user_dep` at decorator-evaluation time (i.e. at import time, before `configure_X_module(...)` ran), which fails.

6. **Helper for tests: `bind_X_module_to_mock(mock_sb)`** in `noctusai_lib.testing` lets product conftests rewire the module per fixture (TestClient caches the app, so the boot-time configure captures the FIRST fixture's mock_sb permanently — re-bind per fixture). See `KB § PATTERNS/testing.md § Consent-guard product conftest pattern` for the canonical conftest shape.

### Reference adopters (read these before designing a new dep factory)

- `seed/lib/backend/noctusai_lib/ai/consent.py::consent_required` — factory shape + module-level state.
- `seed/framework/backend/noctusai_seed/app.py` — the wiring point (search for `configure_consent_module(`).
- `seed/lib/backend/noctusai_lib/testing/consent.py::bind_consent_module_to_mock` — the per-fixture rewire pattern.
- `seed/lib/backend/noctusai_lib/llm/budget.py::configure_budget_module` — sister adopter (no Depends but same module-level injection shape).

### When to use this pattern

- Any seed-lib feature that needs to read **per-request** state (the calling user, the active org, the request-scoped DB client) AND **per-process** wiring (which factories to call). Mounted via `Depends(...)`.
- Any seed-lib feature that needs to be **opt-out via a settings flag** rather than always-on.
- Any feature where the configuration depends on the product's `ProductDependencies` (and therefore can't be hard-coded in the seed lib).

If you're tempted to capture `db.get_admin_client` or `deps.get_current_user` at module-import time, stop — that's the trap. Use this pattern.

---

## Webhook signature carve-outs

Inbound webhook receivers go through `noctusai_lib.security.webhook_signatures`
(four shapes: HMAC-SHA256 prefixed, bare hex, Svix protocol, plus the
Stripe carve-out). Two divergences from "always use the seed-lib helper"
are explicit and load-bearing:

### Stripe SDK is the canonical verifier — don't wrap, don't reinvent

**Use:** `stripe.Webhook.construct_event(payload, sig_header, secret)`
inside `core/backend/app/services/stripe_service.construct_webhook_event`.

**Don't:** call `verify_hmac_sha256` against `Stripe-Signature`. Stripe's
header is multi-version (`t=<ts>,v1=<sig>,v0=<legacy>`), the signed
payload is `f"{t}.{body}"` (not the bare body), and the SDK enforces a
default 5-minute tolerance window — re-implementing it loses every
property at once. The SDK is the canonical verifier; the seed-lib
helper is for non-Stripe webhooks. → `KB § PATTERNS/accept-with-rationale.md
§ Stripe SDK is the canonical webhook verifier`.

### Outbound webhook signing stays in `core/services/webhook_delivery.py`

**Use:** `compute_hmac_sha256_hex(signature_payload, secret)` from the
seed-lib for the cryptographic primitive, but the surrounding signer
(envelope construction `{timestamp}.{body}`, header set
`X-Webhook-Signature` / `X-Webhook-Event` / `X-Webhook-Timestamp`,
delivery row insert into `webhook_deliveries`, retention sweep, retry
loop, payload classification) stays in core.

**Don't:** absorb the outbound signer into `noctusai_lib.security`. The
helper would either drag delivery lifecycle (storage / retention /
retry / classification) into seed-lib (wrong layer — it's a
domain-bounded feature of core's webhook subscription product) or
split the signer from its lifecycle (creating a brittle two-piece API).
Inbound verifiers belong in seed-lib because they're pure crypto;
outbound delivery is a product feature. → `KB § PATTERNS/accept-with-rationale.md
§ Outbound webhook signer stays in core/services/webhook_delivery.py`.

The cryptographic primitive does route through `compute_hmac_sha256_hex`
so the underlying constant-time compare path is one canonical helper —
that's the absorbed layer; the lifecycle is the carved-out layer.

---

## DELETE-with-existence-check helper (2026-05-10)

**Use:** `noctusai_lib.api.crud_safety.delete_with_existence_check` (or the
HTTPException-flavored convenience wrapper `delete_or_404`) for every DELETE
endpoint that needs to distinguish "row absent" from "row present".

**Why:** `db.table("X").delete().eq(...).execute()` + `if not result.data:`
is an unreliable 404 detector. Two failure modes:

1. **RLS-collapsed rows look identical to absent rows.** When RLS hides a row
   from the caller, `.delete()` matches nothing and returns `data=[]` — the
   service incorrectly reports 404 instead of 403, leaking row-existence
   information across tenants.
2. **PostgREST drivers vary on whether DELETE returns the deleted row.**
   Relying on `result.data` couples the service to driver behavior.

**The helper:**

```python
from noctusai_lib.api.crud_safety import delete_with_existence_check, delete_or_404

# ERP convention — LookupError raise shape
def deletar_regra(db, regra_id: str) -> None:
    delete_with_existence_check(
        db,
        "regras_pontuacao",
        ("id", regra_id),
        not_found_exc=lambda: LookupError("Regra não encontrada"),
    )

# PF / router convention — HTTPException(404) raise shape via convenience wrapper
delete_or_404(
    db,
    "recorrentes",
    ("id", recorrente_id),
    ("org_id", org_id),
    message="Recorrente nao encontrado",
)
```

**Variadic predicates.** Pass `(col, val)` tuples — chained as `.eq(col, val)`
on BOTH the SELECT pre-check and the DELETE. Use the same scope predicates on
both so RLS-aware filters match. Most callsites pass `(id,)` (RLS-via-parent
tables like `orcamento_itens`) or `(id, org_id)` (the canonical PF/ERP pair).

**Raise-shape injection.** ERP services raise `LookupError`; PF routers raise
`HTTPException(404)`. The helper accepts a caller-provided zero-arg exception
factory (`not_found_exc=lambda: ...`) so both conventions consume the same
helper without forking.

**N=3 cross-product recurrence (formalize trigger):** `personal-finance`
`routers/recorrentes.py` + `erp-imobiliario` `meta_periodos_service.py` +
`regras_pontuacao_service.py`. Per `KB § PATTERNS/project-execution.md § 2.7
recurrence rule`, N=3 → MUST-FORMALIZE. Filed as `projects/delete-precheck-seed-lift/`.

**N=6 follow-up backlog (Phase 0 grep surfaced N=9 total — 3 in scope, 6 out of scope, deferred):** `erp-imobiliario` `metas_empresa_service.py:92`, `metas_equipe_service.py:86`; `core` `routers/settings.py:126`, `:191`; `daily-life` `routers/goals.py:169`, `routers/schedule.py:171`, `routers/notes.py:141`. Same shape — `result = db.table(X).delete()...execute()` + `if not result.data:`. Deferred to follow-up project to avoid scope-creep; capture in `accept-with-rationale.md` until backfilled.

**Don't:** keep the old `result = db.table().delete()...execute(); if not result.data:` shape in new code. Use the helper. If a callsite raises something other
than `LookupError` / `HTTPException(404)`, pass that factory through — the
helper is shape-agnostic.

---

See also:
- `../03-SEED-ARCHITECTURE.md` — how `create_product_app()` works
- `../04-SHARED-LIBRARY.md` — catalog of reusable helpers
- `database-rls.md` — deeper RLS patterns
- `notifications.md` — notification flow details
- `webhook-signatures.md` — the four-shape catalog + universal rules
- `accept-with-rationale.md` — durable register of legitimate divergences
