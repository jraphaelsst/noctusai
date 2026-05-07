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
