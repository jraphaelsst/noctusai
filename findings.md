# seed-auth-deps-hardening — findings.md

What was learned (not what was done — that lives in commits + PROJECT.md
§11). Five categories: errors, mistakes/slips, lessons, interesting findings,
knowledge pieces. Append in-the-moment; synthesise at project close.

---

## Phase 0 — Orientation (2026-05-06)

### Errors
*(none — orientation only)*

### Mistakes / slips
*(none yet)*

### Lessons
- **Workspace symlink points at noc-main, not at the engineer's worktree.**
  `noctusai-youtube-crawler/seed -> /Users/rapha/Documents/repository/NoctusAI/noctusai/seed`
  (the noc-main worktree, currently on branch
  `seed-hardening-from-youtube-crawler`). My worktree at
  `noctusai-worktrees/seed-auth-deps-hardening/seed/` is its OWN
  checkout — edits there don't reach the workspace runtime until the
  symlink is repointed or the bytes are mirrored. Plan: edit in my
  worktree (committed to my branch), temporarily flip the workspace
  symlink to my worktree's seed for the test runs, restore after each
  test cycle. Architect's FF-merge will reconcile main eventually.
- **Workspace venv resolves `noctusai_lib.api.auth` through the
  symlink** — verified `python -c "import noctusai_lib.api.auth as m;
  print(m.__file__)"` prints the noc-main path. Means: factory
  `make_get_current_user_org` is already present at runtime for the
  workspace product. No `pip install -e` re-run needed; only the file
  bytes matter (symlink target visibility).

### Interesting findings
- **Baseline 94/94 confirmed in <0.5s** on the workspace's `.venv`.
  Two pre-existing warnings (a starlette `multipart` import deprecation
  and a `datetime.utcnow()` usage in `youtube_service.py`) — not
  in-scope here, logged for the cross-product follow-up.
- **`AuthClient.raw()` returns the bare TestClient** — the existing
  `test_status_requires_auth` and `test_unauthenticated_rejected`
  tests use it precisely so the auto-authed wrapper doesn't mask the
  401/403. After the factory swap they should still match
  `assert resp.status_code in (401, 403)` because the factory's
  `make_get_current_user` raises 401 on missing/bad auth header
  before the org-id resolver runs.

### Knowledge pieces
- **Why `Depends(get_org_id)` is broken**: FastAPI introspects the dep
  function's signature when wired through `Depends(...)`. Any
  parameter without an explicit `Depends()` / `Header()` / `Query()` /
  `Body()` annotation, and not of a routing-relevant type, becomes a
  required query parameter. The seed's
  `ProductDependencies.get_org_id(user)` declares `user` positionally
  → `Depends(get_org_id)` makes `user` a required `?user=` query
  param. Same shape for `get_user_role(user)` and `get_user_client(token)`.
- **Why `make_get_current_user_org` chains correctly**: the factory
  returns an async function whose only signature parameter is
  `authorization: Optional[str] = Header(None)`. The org-id resolver
  is captured in the closure and never appears in the FastAPI-visible
  signature, so FastAPI sees only the `Header()` param (correctly
  treated as a header) and resolves the dep at request time without
  inventing query params.

---

## Phase 1 — Wire the factory in YouTube Crawler (2026-05-06)

### Errors
- **First test pass after wiring went 9 red / 85 green** with all
  failures returning 401 from authed routes. Cause: `make_get_current_user`
  was given the bound method `_db.get_client` captured at module
  import time. The conftest patches `app.database._db.get_client` AFTER
  the import → patch reaches `_db.get_client` (instance attribute) but
  not the previously-captured bound-method object. Fix: pass a
  late-binding lambda `lambda: _db.get_client()` so the lookup happens
  at call time, every request. Same fix applied to `get_user_client`
  and `get_admin_client` (now plain wrappers). Restored to 94/94.

### Mistakes / slips
- **Forgot the `Depends`-chain order surfaces auth before route-body
  arg validation.** The pre-refactor `list_upload_history` checked
  `limit` BEFORE calling `_resolve_auth`. Post-refactor, FastAPI runs
  `Depends(get_current_user_org)` first → unauthed `?limit=0` would
  surface 401 instead of 400. The fixture's `client` is auto-authed,
  so existing tests still pass; but the API surface contract subtly
  shifted. Logged so a follow-up project that wants public-pre-auth
  validation knows to pull the limit check into a Pydantic Query
  validator.

### Lessons
- **Bound methods captured at module load are NOT mock-patchable from
  the test fixture.** `_db.get_client` reassignment (`patch.object(
  _db, "get_client", ...)`) replaces the attribute on the instance,
  but any reference grabbed before the patch (`x = _db.get_client` at
  import) holds the original bound method. Use a late-binding
  callable when handing off a "client factory" function — the wrapper
  pattern (`def get_user_client(token): return _db.get_client(token)`)
  is the canonical fix and adds zero runtime cost. Generalizes: ANY
  seed module that stores a `client_fn` reference at config time
  should accept a late-binding zero-arg lambda, not a bound method.

### Interesting findings
- **OAuth callback was using `Depends(get_user_client)` — silently
  broken too.** Google's redirect carries no Authorization header, so
  the broken Depends-style query-param coercion would have rejected
  every callback in production. Fix: switch to `get_admin_client()`
  (RLS bypass is bounded by the opaque `state` token's tenant
  encoding, not blanket trust). Pre-existing bug, surfaced by the
  refactor sweep; not a regression. Worth noting in the canonical KB
  doc as "OAuth-callback shape is its own thing — redirect targets
  carry no JWT, use admin + state-token tenant binding."

### Knowledge pieces
- **`Depends(...)` with `auth: tuple = Depends(get_current_user_org)`**
  is FastAPI-idiomatic for capturing multi-value dep returns. The
  `tuple` annotation is hint-only — FastAPI doesn't validate it; the
  unpacking `user, token, raw_org = auth` is what enforces the shape.
  Works because the dep itself is async/sync-agnostic; FastAPI awaits
  the coro if needed.
- **The `_coerce_org_uuid` fixture-bridge belongs in the route, not
  the seed.** Production carries UUID-strings end-to-end; only some
  test fixtures use opaque strings (`"test-org-123"`). The factory
  itself is correct to return `Optional[str]`. If a future product
  also needs opaque-string fixtures, lift the helper to
  `noctusai_lib.testing` rather than the auth seam — keeps the
  seam's contract pure.

---

## Phase 2 — Deprecate the broken seed export (2026-05-06)

### Errors
- **First-pass `_warn_depends_misuse` violated §3 design principle 3.**
  Initial implementation fired on every imperative call, surfacing
  `DeprecationWarning` from the seed's own `team_router` calls to
  `deps.get_user_role(user)` (line 199 of `noctusai_seed/routers.py`).
  Those calls are the SAFE shape — only `Depends(get_user_role)` is
  broken. PROJECT.md §3 explicitly said warn at the broken shape, not
  the call. Caught by inspecting the workspace test summary (5
  DeprecationWarning lines for legitimate seed-internal calls).
  Fixed by switching to a frame-aware helper.
- **Frame-walking helper "FastAPI in stack" was too loose.** Second
  iteration walked the entire frame chain looking for any
  `fastapi.*` module. False-positive: every imperative call inside a
  route body has FastAPI frames in its stack (the request handler
  runs under `fastapi.routing`). Tightened to "immediate caller's
  module is `fastapi.dependencies.utils`" — narrow but accurate; the
  only frame matching that constraint is the dep-injection solver
  calling `await call(**values)` directly.

### Mistakes / slips
- **Initial test wrote `_warn_if_fastapi_caller` as the entry point**
  for the synthetic FastAPI module, then asserted the warning fired.
  Failed because the helper's frame-walking logic assumes it's called
  from a deprecated METHOD (`get_org_id` / `get_user_role` /
  `get_user_client`), so `f.f_back` = method, `f.f_back.f_back` =
  caller. Calling the helper directly from the synthetic module
  skipped the method frame, putting the synthetic frame in the
  "method" position. Refactored test to invoke
  `ProductDependencies.get_org_id(user)` from the synthetic module —
  honest reproduction of the FastAPI-injection call shape.

### Lessons
- **Frame-inspection-based detection is fragile but sometimes the
  only honest tool.** PEP-8-clean alternatives (warn-at-import,
  warn-on-every-call) either over-fire or unde-fire. The frame check
  honors the design principle exactly. The fragility tax: any FastAPI
  internal restructuring that renames `fastapi.dependencies.utils`
  silently disables the warning. Mitigated by the regression test
  suite — if upstream renames the module, the
  `test_fastapi_dependency_call_emits_warning` test catches it.
- **The "warn on broken shape only" principle is structurally
  unreachable for THIS specific bug.** FastAPI rejects requests with
  422 BEFORE invoking these deps when the missing-query-param
  introspection fires. So the warning at call time NEVER fires in
  production for the bug-shape callers — they fail at request
  rejection, not at function call. The warning is diagnostic, not
  preventative; the keeper-detector (a follow-up project) is the
  real third defense layer. Documented this in the helper's
  docstring + `_warn_if_fastapi_caller`'s "Caveat:" section so
  future maintainers don't try to "fix" the (necessarily) limited
  surface.

### Interesting findings
- **The seed's own team_router uses the broken-shape methods
  imperatively** (`routers.py:112`, `:199`). Per the recurrence rule
  (N=2 if you count the workspace product before this project + the
  seed itself = N=2 within-noc), this is a candidate for an
  absorption pass — the team_router could itself migrate to the
  factory pattern. Out of scope here (PROJECT.md §4 explicitly
  excludes cross-product rollout AND seed-internal cleanup); filed
  as a follow-up via the architect's eventual post-merge sweep.
  Catalog entry deferred to the project-close proposal bundle.

### Knowledge pieces
- **`stacklevel=3` for the warning correctly points at the
  Depends-wiring line in user code.** The frame chain at warning
  time: stacklevel=1 = `warnings.warn` itself, =2 = the deprecated
  method (`get_org_id`), =3 = the caller (FastAPI's solver). Not
  user code in this case (FastAPI is the "caller"), but the warning
  still includes the migration recipe in its message body so the
  user can grep for it. If we wanted to print the user's
  `Depends(get_org_id)` line specifically, we'd need to pass the
  registration-time AST location through — out of scope.
- **`types.ModuleType("fastapi.dependencies.utils")` is enough to
  fool frame-name detection.** `frame.f_globals["__name__"]` is the
  module-dict's `__name__` key, set by `ModuleType.__init__`. Useful
  for testing frame-walking detectors without real FastAPI code.
