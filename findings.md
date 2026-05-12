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

---

## Phase 3 — Document the canonical pattern (2026-05-06)

### Errors
*(none)*

### Mistakes / slips
- **Almost added a §2 Map row in CLAUDE.md** before realizing §2 already
  covers `KB § PATTERNS/backend.md` and §3's table is the right place
  for the trigger phrase ("Wiring auth on a new product / route"). §2
  is a permanent map; §3 is the situational lookup. Auth-wiring is a
  situational read, not a permanent destination — §3 wins.

### Lessons
- **Replacing a section in KB > appending a new one** when the topic
  already has a heading. The legacy `## Auth` section was 4 lines
  and out of date; replacing it with the full canonical pattern doc
  keeps the reader on a single landmark instead of forcing a
  cross-reference jump. Same readability principle as "split
  files when they exceed cohesion" — but inverted: merge fragments
  when they belong together.

### Interesting findings
- **Memory `feedback_*.md` files use a frontmatter contract**
  (`name`, `description`, `type`, `originSessionId`) that the harness
  parses for retrieval. Empirical: matching the existing entries'
  shape (e.g. `feedback_fastapi_dep_factory.md`) keeps the index
  lookup working. The system reminder showed memory files are
  surfaced into auto-loaded context based on this metadata.
- **`bash scripts/verify-kb-sync.sh`** validates three things:
  CLAUDE.md/CLAUDE-* pointers resolve to real KB files, every KB
  doc is in `KNOWLEDGE-BASE/INDEX.md`, AND the index's "Layout tree"
  reflects the actual filesystem. The pre-commit hook runs this
  automatically; manual run as belt-and-suspenders before the
  Phase 3 commit.

### Knowledge pieces
- **The "anti-patterns" subsection is a load-bearing piece of any
  KB pattern doc.** A future agent grepping for `Depends(get_org_id)`
  will land on the canonical pattern doc and see the explicit ❌
  list before they re-introduce the bug. Without that subsection,
  the doc tells the reader what to do but leaves the trap visible
  only to readers who read top-to-bottom. Anti-patterns + migration-
  history are the "memorable corners" of the doc; the code block
  is the working core.
- **Three-way sync ≠ three identical edits.** KB carries the body;
  CLAUDE.md carries the pointer / trigger phrase; memory carries
  the at-a-glance summary + frontmatter for retrieval. Each layer
  has a distinct shape and audience: KB is for the reader who's
  already on the topic, CLAUDE.md is for the reader who needs to
  know which topic to read, memory is for the harness's auto-load.

---

## Phase 4 — Verify + close (2026-05-06)

### Errors
*(none — verification phase)*

### Mistakes / slips
*(none)*

### Lessons
- **The MCP toolkit's compliance / analyzer tests are platform-wide
  audits, not per-project gates.** They surface platform debt
  (openai version drift, dev-team missing E2E, seed-version stamp
  drift, ERP monkey-patching) regardless of the current project's
  scope. Engineer-side: confirm the failures are pre-existing by
  inspecting the issue list for any reference to your edited files
  / your new code; if none, they're noise. Document in the
  end-of-project proposal so the architect doesn't have to re-run
  to triage.
- **The seed-version-stamp pre-commit hook is one commit behind by
  design.** It runs BEFORE the commit being made → it stamps the
  PREVIOUS HEAD into the static-version files. Net effect: the
  stamp lags by one commit, becoming current after the next
  commit. Not a bug; an artifact of the pre-commit-hook
  ordering. Documented in the architect-handoff section of the
  proposal so the FF-merge process knows to expect it.

### Interesting findings
- **Workspace test count grew from 94 → 112 mid-project as parallel
  agents landed new test files.** The dispatch brief said "94/94
  must stay green"; the actual landing is "all collected tests must
  stay green." The right verification semantics is "no
  regressions," not "exact count match." Logged as an architect-
  feedback opportunity: dispatch briefs that anchor on test counts
  may be brittle when the workspace is shared across parallel
  agents.

### Knowledge pieces
- **End-of-project proposal bundle SHAPE** (synthesized from
  templates + practice on this project):
  1. Applied inline — list of changes with location + why,
     organized so an architect-eyes review takes <5 minutes.
  2. Deferred — destinations named: each deferred item gets a
     LETTER (A, B, C…), a status statement, and a destination
     (specific follow-up project name OR "logged here" for catalog
     entries). Letters make cross-references easy in retros.
  3. Verification snapshot: a small table with rows per suite +
     pass/fail + an inline note for any non-green item. Architect
     can scan without re-running.
  4. Notes for architect FF-merge: anything the architect needs
     to know about the worktree state, the noc-main worktree
     state, parallel branches, or seed-stamp lag. Reduces the
     surface for surprises during the merge.
- **The frame-aware deprecation warning is a *narrow but accurate*
  detector.** Pattern generalizes: when you need to warn about a
  specific call shape but not all calls of a function, walk the
  caller's frame and gate on `__name__`. Useful for: (a)
  framework-vs-imperative call distinguishing, (b) test-only
  warnings (gate on `pytest` in the frame), (c) deprecated
  per-context behavior. The fragility tax is the upstream-rename
  risk — mitigated by a regression test that drives the synthetic
  call shape.

---

## Engineer R (BOOTSTRAP-REQS-HYDRATE) — 2026-05-11

### Errors
*(none — clean execution)*

### Mistakes / slips
- **First `find products` pass picked up `products/seed/.backup/backend/requirements.txt`.**
  The original `--check` enumeration was run from inside the worktree
  (which has no `.backup` dir) and showed 12 clean products. When I
  validated the loop standalone from the main checkout I caught a
  13th entry: `products/seed/.backup/backend/requirements.txt`. Backup
  directories aren't real products; their reqs shouldn't hit the shared
  venv. Fix: added `-not -path '*/.*/*'` to both `find` invocations so
  hidden directories (`.backup`, `.git`, etc.) are excluded. Lesson: the
  worktree's filesystem view can DIFFER from the main checkout (because
  worktrees are git checkouts of a branch state — they don't inherit
  ad-hoc backup dirs created in main). Validate cross-tree before
  declaring an enumeration complete.

### Lessons
- **`pip install -r` is naturally idempotent at the request level**
  (already-satisfied packages are no-ops), but the **resolver pass
  still runs**. A 12-product re-bootstrap takes ~50s wall-clock even
  when no installs occur — that's pip resolving the dep graph. Not a
  bug; acceptable for a one-shot bootstrap script. Worth noting so
  future agents don't try to optimize with mtime gates (would add
  surface area for a marginal win).
- **N=2 defusedxml recurrence revealed a structural gap, not a
  per-product oversight.** Both engineers (D + E) hit the same
  missing-import on the SAME day independently — root-cause is that
  bootstrap-worktree.sh + setup.sh both stopped at root requirements +
  seed packages, leaving every product's incremental deps to manual
  pip-install. Per-product reqs are the right level for *isolated
  Docker deploys* (per the root requirements.txt comment), but the
  *shared dev venv* needs the union. The recurrence rule (N=2 →
  triage time) said: fix at the bootstrap layer, not in adconnect or
  erp. Triage outcome: FORMALIZE.

### Interesting findings
- **The root `requirements.txt` is documented as a "unified superset"**
  (line 1-2: "Per-backend requirements.txt files are kept for
  independent Docker deploys"). But it lagged in practice — `defusedxml`
  was only in adconnect's + erp's per-product reqs, never absorbed into
  the root list. This raises a meta-question: should bootstrap install
  per-product reqs (this fix), OR should there be a doc-tool-coherence
  detector that flags drift between root and per-product reqs? Filed
  in §Architect-followup. The new bootstrap behavior closes the gap
  even if the doc lags; a detector would close the SOURCE of the lag.
- **All 12 products' requirements.txt installed cleanly on first
  pass.** No dep conflicts, no resolver flailing. Modest confidence
  that the per-product reqs are currently a clean superset relative
  to the shared venv state. Could break in the future if two products
  pin conflicting versions of the same dep — at which point the right
  fix is to lift the conflicting dep into root reqs with a single
  pinned version. Worth knowing the failure mode exists.

### Knowledge pieces
- **`find ... -not -path '*/.*/*'`** is the cleanest way to exclude
  hidden directories from a find recurse — matches any path containing
  a `/.` segment. More robust than `-not -name '.*'` (only excludes
  hidden basenames) and faster than piping through grep -v. Generalizes
  for any script enumerating product/tenant/module-style trees.
- **The `--check` mode pattern is idempotency-bait — re-running it
  after the live install should report 0 stale items.** Confirmed:
  bootstrap-worktree.sh --check after live run showed "Frontend
  skipped: 14 (already current)". The per-product reqs loop in
  --check mode still ENUMERATES (showing "WOULD install"), which is
  the right behavior for a probe — they're naturally idempotent so
  there's no "stale" state to report on, but the user wants visibility
  on the list.

### Architect-followup
- **Doc-tool-coherence — root requirements.txt vs per-product reqs.**
  The root `requirements.txt` comment claims "unified superset" but
  drifted (defusedxml in 2 products, not in root). Candidate keeper
  detector: `check_root_reqs_superset` — flags any dep in
  `products/*/backend/requirements.txt` not present in root reqs.
  Stage-3 → Stage-4 pipeline candidate. Out of scope here; bootstrap
  fix closes the symptom regardless.
