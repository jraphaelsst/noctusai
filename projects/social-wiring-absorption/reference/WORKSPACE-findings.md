# YouTube Crawler — findings.md

What was learned (not what was done — that lives in commits + PLAN.md).
Five categories: errors, mistakes/slips, lessons, interesting findings,
knowledge pieces. Append in-the-moment; synthesise at project close.

---

## Phase 1 — Config + YouTube service + Settings page (2026-05-06)

### Errors
- **`asyncio.run()` inside MCP server's running event loop** — scaffold.py
  L348 raised `RuntimeError: cannot be called from a running event loop`
  when invoked through MCP. Fixed at the seed by adding
  `_run_coro_blocking` in scaffold.py (detects running loop, offloads to
  worker thread). Pushed in `04d28f3`. Lesson: any sync wrapper around
  async inside an MCP-exposed tool needs the same pattern — track as
  recurrence if it shows up again.
- **LLM auto-rewrite skipped when scaffold runs from a subprocess** —
  google-auth + LLM config aren't auto-wired outside the `create_product_app`
  lifespan. Surfaced by youtube-crawler's first scaffold attempt; recovered
  by writing README + MASTER-PROMPT by hand from the brief. Filed as a
  known gap for the in-process scaffold path.

### Mistakes / slips
- **Tested with `client.as_user("test-user").get(...)`** — that API doesn't
  exist on `AuthClient`; it's auto-authed and methods are direct
  (`client.get`, `client.post`). Caught by 3 failing tests on first run;
  fixed by sed-replacing the prefix. Lesson: when copying test patterns,
  re-read the helper class in the seed lib instead of guessing the API
  from analogues.
- **Initial commit staged `001_seed.sql → 001_adconnect.sql` rename** —
  git's rename detection auto-staged it when I added unrelated files
  (the `R` was already in the index from a prior session). Caught by
  reviewing `git diff --cached --name-only` before commit; unstaged with
  `git restore --staged` and pushed it into the parallel-agent sweep-up
  commit instead. Lesson: explicit-path `git add` doesn't validate
  authorship — the `commit-only-own-work` memory rule is real, verify
  the cached set every time.

### Lessons
- **Workspace-level test fixtures inherit from `noctusai_lib.testing`** —
  `MockSupabaseClient` + `AuthClient` + `bind_consent_module_to_mock`
  give a green test path without ever hitting Supabase. Adding three
  new test files for credential_store / youtube_service /
  settings_router took the suite from 31 → 54 tests in <30 lines of
  net-new fixture code. The seed-first principle pays compounding
  interest in tests, not just product code.
- **Frontend builds against the seed via three import shapes**:
  `@noctusai/seed` (factories), `@noctusai/seed/infra` (singletons),
  `@noctusai/lib` (types + design-system). The path resolution flows
  through `vite.config.factory.ts` in the seed framework — works
  through symlinks, no aliasing required at the product level.

### Interesting findings
- **The seed product ships shadcn-wrapped Radix primitives per-product**
  (`components/ui/tabs.tsx`, `components/ui/card.tsx`, etc.), not from
  the seed lib. Already a recurrence (every product duplicates the same
  ~20 files); known absorption candidate. For now, copied therapy-
  platform's `components/ui/` wholesale to avoid divergence inside the
  workspace. Filed as an absorb-into-seed follow-up — when the count
  hits N=3+ across products with NO meaningful variance, the seed lib
  should ship `@noctusai/lib/ui` exporting all of them.
- **Resumable upload at chunksize=-1 means single-shot** — `MediaFileUpload(file, chunksize=-1, resumable=True)` lets googleapiclient stream the whole file in one HTTP request while keeping the resumable
  semantics (so a network blip retries from the last chunk, not the start).
  Worth keeping if Phase 2 introduces progress-bar streaming — switch to
  a small chunksize there to surface progress.
- **YouTube quota for the daily-life budget is generous** — full channel
  sync for a typical channel (<500 videos) costs ~10-20 units; an upload
  is 100. We can do 80 uploads + dozens of syncs per day on the default
  10k quota with comfortable headroom.

### Knowledge pieces
- **Fernet round-trip is 4 lines + a key**:
  ```python
  from cryptography.fernet import Fernet
  k = Fernet.generate_key()
  ct = Fernet(k).encrypt(b'plaintext')
  pt = Fernet(k).decrypt(ct)
  ```
  Authenticated encryption — tampered ciphertext raises `InvalidToken`,
  never silently decrypts. The credential_store wraps this with a
  CredentialStoreError so router-level handlers translate to 503 (config
  / encryption issue) instead of 500 (server bug).
- **OAuth state token round-trips org_id**: `state = f"{org_id}:{nonce}"`
  pattern lets the callback bind tokens to the right tenant without
  trusting the redirect_uri alone. The nonce is paranoia — if anyone
  ever wants strict CSRF protection, persist nonces to redis + verify
  on callback.
- **`access_type=offline` + `prompt=consent`** is the only reliable
  combination to get a `refresh_token` from Google's OAuth. Without
  `prompt=consent`, repeat consents skip the refresh-token issuance and
  the bundle becomes stale-only.

---

## Phase 0 — Workspace recreation + docker convention (2026-05-06)

(Pre-Phase-1 setup; some items already three-way-synced into noc memory
+ KB. Listed here for the workspace-local audit trail.)

### Errors
- See "asyncio.run nesting" above — fixed inline.

### Mistakes / slips
- Docker convention was missing from the seeding system entirely.
  Surfaced by the user with "you havent created the docker and
  containers on seeding the product." Closed by adding
  `templates/seed-workspace-docker/` + bootstrap step + scaffold patch
  step. Three-way synced into KB + memory.

### Lessons
- **Docker COPY does NOT follow directory symlinks at build time**. The
  workspace's `seed/` symlinks into noc; pulling its contents into the
  image needs `additional_contexts: noc: ${NOCTUSAI_HOME}` in the
  compose file + `COPY --from=noc seed/...` in the Dockerfile. Trying
  to `cp -L` symlinks pre-build "works" first time then breaks on
  rebuild — the named context is the structural fix.

---

## Phase 2 — Upload pipeline + Drive download + Upload page (2026-05-06)

### Errors

- **`-> None` + `status_code=204` trips a fastapi==0.115 assertion**.
  Mechanism: when `response_model` is unset, FastAPI calls
  `get_typed_return_annotation(endpoint)` and assigns the result to
  `self.response_model`. For `-> None`, that's `<class 'NoneType'>` —
  a class object, which is truthy. Then at routing.py:507 the check
  `if self.response_model: assert is_body_allowed_for_status_code(status_code)`
  fires for 204 routes. FastAPI special-cases `Response` subclasses
  (`lenient_issubclass(return_annotation, Response)` → sets to None),
  but not `type(None)`. Fix: pass `response_model=None` explicitly on
  204 routes; settings_router `disconnect_youtube` + `delete_recipient`
  patched. The cleaner long-term fix is to not annotate `-> None` on
  FastAPI routes — the type system "documents" what FastAPI is
  treating as a response model. Latent in Phase 1 — only surfaced
  when the workspace got a fresh venv.

- **(2026-05-06) → project `seed-auth-deps-hardening` filed; YouTube
  Crawler now uses the canonical `make_get_current_user_org` factory
  (Phase 1 closed). Both routers refactored from imperative
  `_resolve_auth(authorization)` / broken `Depends(get_org_id)` to
  `Depends(get_current_user_org)`. Phase 2 deprecates the seed export;
  Phase 3 documents the canonical pattern in `KB § PATTERNS/backend.md`.**

- **`Depends(seed_dep)` silently turns positional args into query params**.
  Mechanism: FastAPI introspects the dep function's signature when
  wired through `Depends(...)`. Any parameter without `Depends()` /
  `Header()` / `Query()` / `Body()` and without a routing-relevant
  type is treated as a **required query parameter**. The seed's
  `ProductDependencies.get_org_id(user)` declares `user` positionally
  → `Depends(get_org_id)` makes `user` a required `?user=` query
  param. Same for `get_user_client(token)` → `?token=`. Result: 422
  on every authed request, with `loc: ['query', 'user']` /
  `loc: ['query', 'token']` in the body. The 401/403 paths inside
  these deps never run because FastAPI rejects before calling them.
  This generalizes: **any seed-exported function that's wired through
  `Depends(...)` and takes non-FastAPI-injectable positional args
  has the same bug**. Refactored upload_router to the imperative
  pattern (`authorization: Header(None)` + manual call inside the
  route body); see the "imperative auth" note in interesting findings.

### Mistakes / slips

- **Forward-reference FK in migration 003**. Wrote `ALTER TABLE
  notification_log ADD CONSTRAINT ... REFERENCES upload_jobs(id)`
  in 003, but 003 runs BEFORE 005 (which creates notification_log).
  General rule: **when migration numbers express order, the FK
  belongs in whichever migration creates the table that holds the
  FK column** (the "second" table chronologically). Caught before
  commit; moved the FK declaration into the 005 column definition
  inline (`upload_job_id UUID REFERENCES upload_jobs(id) ON DELETE
  CASCADE`). Same rule applies to indexes, triggers, and check
  constraints that reference cross-migration columns.

- **First upload_router draft used the broken `Depends`-style**.
  Wrote `org_id: UUID = Depends(get_org_id), user_supabase = Depends(get_user_client)`
  before checking how other products do it. Tests caught it (422
  instead of expected 401 / 503). Fix took ~5min after grep'ing
  `Depends(get_org_id)` across products/ and finding **zero hits**.
  Lesson: when reaching for a seed-exported helper, run the
  cross-product grep first — if nobody else uses it the way I'm
  about to, that's a signal.

- **Wrote a custom `_MockSupabase` instead of using `MockSupabaseClient`**.
  In `test_upload_service.py` I built a tiny fluent-mock stub
  because the lib's `MockSupabaseClient` returns more than I needed
  (schema-validation, auto-id, response queues). Worked for the
  immediate test, but it's a small recurrence signal: if a second
  service test reaches for the same lean stub, that's an N=2 case
  for "absorb a `MockSupabaseLite` into noctusai_lib.testing" — or
  for refactoring the existing mock to make the lean shape ergonomic
  via a kwarg. Logged here, not refactored — file as N=1.

### Lessons

- **Phase 1's "54/54 passed" was passing-for-the-wrong-reason**. The
  settings_router recipient tests asserted `"at least one of" in
  resp.text` and got status 422 from the broken `Depends` chain
  (missing `user`/`token` query params) AND a 422 from body
  validation. Both errors landed in the same 422 response body,
  so the substring assertion matched, the test went green, and the
  endpoint was unusable for any authed traffic in production.
  **Test-design rule**: a test that asserts on response *text*
  without also asserting status code is asserting a substring, not
  a behavior. Always pair `assert resp.status_code == X` with the
  text check; the status code is what makes the test load-bearing.
  Worth a keeper-detector candidate: scan test files for
  `assert "<text>" in resp.text` / `resp.json()` without a sibling
  `resp.status_code == ...` assertion in the same test method.

- **Dead code that LOOKS correct is worse than no abstraction**.
  The `Depends`-style seed-deps export is **dead code across the
  products tree** (zero `Depends(get_org_id)` / `Depends(get_user_client)`
  usages anywhere). It existed long enough to convince two
  successive sessions of mine to use it, and would have convinced
  a third. The cleanup path is fix-by-deletion: drop the `Depends`-
  style re-exports, document the imperative pattern as canonical
  in `KB § PATTERNS/backend.md`, and add a keeper-detector that
  flags any new `Depends(<seed_dep>)` usage. (See seed-auth-deps-
  cleanup project candidate.)

- **Workspace venvs need explicit Python pinning + the transitive
  closure**. `python3 -m venv .venv` in this workspace defaulted to
  `python3.14` (newest installed homebrew Python) — no pydantic-core
  wheel yet → install fails. Forced `/opt/homebrew/bin/python3.13`
  to fix. Then **three transitive packages** were missing from
  `requirements.txt`: `email-validator` (required by Pydantic
  `EmailStr`, used in `RecipientCreate`), `python-multipart`
  (required by FastAPI when any route uses `File()` / `Form()`),
  and `@radix-ui/react-progress` (required by the shadcn `progress.tsx`
  copy in components/ui). All three are "install on first
  reference" tax. Bootstrap improvement: emit a per-product
  `setup.sh` that pins Python ≤ 3.13 explicitly, installs the
  full transitive set, and runs `pytest --collect-only` as a smoke
  check. Cheap, catches all three classes at scaffold time.

- **shadcn ui/* files don't ship their Radix peer deps**. Every
  component under `components/ui/` is a thin wrapper over a Radix
  primitive (`@radix-ui/react-progress`, `@radix-ui/react-tabs`,
  etc.). Copying the file into a product without checking
  `package.json` produces a build-time "Rollup failed to resolve"
  on first import. Bootstrap should grep ui/*.tsx for
  `@radix-ui/react-*` imports and ensure each lands in
  `package.json` — or, more durably, absorb shadcn UI into
  `noctusai_lib/frontend/ui` so peer deps live with the lib (already
  flagged as N≥3 in Phase-1 findings; this is N=4 confirmation).

### Interesting findings

- **The platform's "imperative auth" pattern is undocumented but
  universal**. PF, Therapy, Mailing, AdConnect, and (post-fix)
  YouTube Crawler all use the same shape:

  ```python
  async def handler(authorization: Optional[str] = Header(None)):
      user, token, org_id = await get_current_user_org(authorization)
      db = get_user_client(token)
      ...
  ```

  `Header(None)` is the only thing wired through FastAPI's machinery;
  every other auth concern is a regular function call inside the
  route body. The convention is so consistent that the seed's
  `Depends`-style export looks like a leftover from an earlier
  attempt that was never deleted. **Empirical evidence**:
  `grep -r "Depends(get_org_id)" products/` → **zero matches** in
  any product. The fix-by-deletion path is justified by this grep,
  not by aesthetics — if products consumed the export, deleting
  would break things; nobody does, so deleting only deletes a trap.

- **Pydantic schema-boundary validation catches a class of bugs
  early**. The `_validate_drive_host` validator on
  `GdriveUploadRequest` rejects non-Google URLs at request-parse
  time, before the service ever opens an httpx connection. Without
  it, a typo'd URL would cost a download attempt + a 60s timeout +
  a vague error. Pattern: **when a service-side method only accepts
  values from a known set (allowed hosts, supported MIME types,
  valid enum strings), the same check at the schema boundary is
  free and improves error locality**. The schema layer is the
  natural place because Pydantic's error path already exists; the
  service-layer check stays as defense-in-depth but rarely fires.

- **JSON-in-form for multipart is ergonomic for nested types**. The
  `/api/videos/upload` endpoint takes `file: UploadFile` + a single
  `metadata: str = Form(...)` field whose value is a JSON-encoded
  `UploadMetadata`. Decoded inside the route via `json.loads` +
  `UploadMetadata(**...)` with `ValidationError → 422`. The
  alternative — one Form field per metadata key — works for flat
  shapes but turns ugly fast for `tags: list[str]` and
  `notify_recipients: list[UUID]` (FastAPI's Form-list
  reconstruction needs `tags[]=a&tags[]=b` plumbing on the client
  and isn't symmetric with the JSON post on the Drive endpoint).
  JSON-in-form keeps both endpoints' metadata shape identical.

- **Staging-then-rename is a clean two-phase handoff**. Browser
  uploads need to land on disk *before* the job_id exists (the
  insert doesn't happen until after we know the file size) but
  the background worker needs a deterministic path to find the
  file *after* the job_id exists. Solution:

  ```
  upload_dir/staging-{uuid}__{filename}    ← request handler stages here
  upload_dir/{job_id}__{filename}          ← request handler renames after insert
  ```

  The staging name has a UUID prefix so two concurrent uploads of
  the same filename don't collide. The `stage_browser_upload`
  context manager unlinks on inner-exception so a failed insert
  doesn't leave orphaned files. Worth promoting to a seed
  primitive if a second product ever needs file-staging (currently
  N=1; logging the shape).

### Knowledge pieces

- **Streaming-with-cap is the right shape for untrusted downloads**.
  `gdrive_service._stream_to_file` increments a counter as it
  writes each chunk and unlinks the partial file when the running
  total exceeds `max_bytes`. Without this, a malicious or
  malformed Drive response that omits Content-Length but sends GBs
  would silently fill the host disk. The pre-check on
  `Content-Length` is necessary but not sufficient — header values
  are caller-controlled and can lie.

- **`MediaFileUpload(file, chunksize=-1, resumable=True)`** sends
  the whole file in one HTTP request while keeping resumable
  semantics. A network blip retries from the last chunk rather
  than from byte zero. Fine for Phase 2 (no progress-bar
  requirement); switch to a smaller `chunksize` when Phase 4 needs
  intermediate progress events emitted to the upload_jobs row.

- **Background tasks own their cleanup, not the request handler**.
  The router stages the multipart body, renames to
  `{job_id}__{file_name}`, and returns 202. The worker reads the
  file then unlinks via `gdrive_service.cleanup` in a `finally`
  block. Putting cleanup in the request handler would race with
  the worker reading the file (request returns → cleanup deletes
  → worker can't find it). Same rule for Drive downloads — the
  worker downloads, uploads, and cleans up; the request just
  queues the row.

- **`MockTransport` for httpx tests is the right level**.
  `httpx.Client(transport=MockTransport(handler))` lets you write
  a per-test response handler that gets the real `httpx.Request`
  + returns a real `httpx.Response`. Unlike `responses` /
  `httpretty` for `requests`, this is built into httpx — no extra
  dependency. Used in `test_gdrive_service.py` to exercise
  oversized-via-Content-Length, oversized-mid-stream, HTML
  consent-page intercept, and unsupported-extension paths
  without ever touching the network.

- **Two-Supabase-client split for queue + worker**. The upload
  service takes both a user-scoped client (from `get_user_client(token)`,
  RLS-bound) and a service-role client (from `get_admin_client()`,
  RLS-bypass). Queue inserts go through the user client so RLS
  ensures `org_id` matches the JWT; status transitions in the
  background worker go through the admin client because the
  worker has no JWT context. The split is enforced at the
  `UploadService.__init__` signature so a future change can't
  accidentally use admin for queue inserts (which would let any
  authed user queue jobs against any org).

---

## Phase 3 — Video listing + cache + Videos page (2026-05-06, in progress)

> **Pre-staged in parallel with the architect-dispatched
> `seed-auth-deps-hardening` + `keeper-test-status-assertion` projects.**
> Phase 3 backend + frontend pieces written using Engineer A's
> already-landed `Depends(get_current_user_org)` pattern. Backend
> 105 → 112 tests (+7 router tests, +11 service tests = +18 since
> Phase 2 close). Frontend vite build green; Videos page lazy-chunks
> at 11.67 KB.

### Errors
- _(none surfaced yet)_

### Mistakes / slips
- **Wrote `_coerce_org_uuid` for the third time** in `videos_router.py`
  knowing it's already in `upload_router.py` + `settings_router.py`.
  N=3 recurrence detected at write-time but deliberately deferred:
  Engineer A's `seed-auth-deps-hardening` is still touching
  `app/dependencies.py`, so lifting now would create a merge
  collision. Logged in the helper's own docstring with explicit
  pointer to lift at end-of-phase / project close. **Lesson:** when
  hitting an N=3 recurrence mid-flight in a parallel-coordinated
  surface, "defer with destination" beats "absorb now" — but only
  when the destination is named in the code (not just in the
  agent's head). **RESOLVED at Phase-3 close**: lifted to
  `app/dependencies.py:coerce_org_uuid` post-merge, all three routers
  import it, leading-underscore dropped (now a public symbol). 112/112
  tests still green after the rename.

### Lessons
- **Pre-staging works.** While Engineer A refactored the auth
  pattern (workspace-side, ~5min worth of reads), I built the
  entire backend cache layer (migration + schemas + service +
  tests + router + main.py wiring) and the entire frontend Videos
  page (hook + component + page + nav). All of it could be written
  before merging because: (a) the auth API surface — `Depends(get_current_user_org)` returning `(user, token, raw_org)` — was published in
  PROJECT.md before dispatch, (b) net-new files don't collide,
  (c) the workspace's `app/main.py` was the only collision point,
  done last. Total wall-clock parallelism gain: ~Phase-3-equivalent
  time saved.
- **~~The deprecation warning Engineer A added is firing inside the
  seed framework's own `routers.py:199`...~~** **RESOLVED at engineer
  A's merge** (commit `c00fb49`). The finalized implementation uses
  a frame-aware `_warn_if_fastapi_caller(qualname)` helper that walks
  the stack and only fires when the IMMEDIATE caller's module is
  `fastapi.dependencies.utils` (FastAPI's dep resolver). Imperative
  calls (`deps.get_user_role(user)` from a route body) stay silent.
  The earlier observation was based on a snapshot before Phase 2 was
  fully finalized. Worth keeping the resolution log: **stack-walk
  gating is the right shape** for "warn at the broken call shape, not
  the broken function." Pattern reusable for future deprecations.

### Interesting findings
- **`@router.get("/{youtube_video_id}")` after `@router.get("")`** —
  the order matters in FastAPI when path-segment-only routes might
  shadow each other. List + get coexist cleanly because the list
  is `""` (router prefix only) and the get is `/{youtube_video_id}`
  — different shapes. The `/sync` route works because it's a POST,
  not a GET, so even string overlap with `/{...}` would be safe.
  But adding e.g. `GET /summary` later would shadow `GET /{youtube_video_id="summary"}`
  unless declared first. Worth noting in a future "Router design"
  KB doc — same shape applies to upload router's `""` + `"-from-drive"`
  endpoints.
- **Cursor encoding choice: `<published_at>|<id>`**. Plain ISO ts
  alone breaks tie-breaking when two videos share `published_at`
  (rare but happens with batched uploads). Adding `|<id>` gives a
  stable secondary sort. The cursor is opaque to the client; no
  contract drift if we change the encoding later.

---

## Phase 4 — Dashboard rewrite + Notifications dispatch (2026-05-06)

> **Phase 4 = the last phase.** PLAN.md complete. 153/153 backend tests
> green; vite build green; Dashboard chunk lazy-loads at 362 KB
> (recharts dominates; acceptable for an analytics page).

### Errors
- _(none surfaced — Phase 4 went clean on first run)_

### Mistakes / slips
- **Initially considered making `run_upload_job` async** to call the
  async `notification_service.notify_upload(...)` directly. Backed off
  because (a) BackgroundTasks runs sync functions in a worker thread
  where `asyncio.run` is safe (no nested loop), (b) flipping the
  function to async would force test updates across the existing 4
  pipeline tests, (c) the sync→async change radius is wider than the
  notification dispatch needed. Used `asyncio.run` inside the sync
  function instead — clean, narrow, no test churn. **Lesson:** when
  bridging async boundaries inside a worker-thread context, prefer
  `asyncio.run` over function-shape changes; reserve the async-flip
  for cases where the parent is already in an event loop.

### Lessons
- **Optional dependency injection beats required for backward compat.**
  `UploadService.__init__` got `notification_service: NotificationService | None = None`.
  Phase 2/3 tests that constructed UploadService without
  notification_service kept passing without modification. New Phase 4
  tests pass an instance to verify the notified-status path. Avoids
  the "rewrite all existing tests" tax that a required parameter
  would have imposed. Pattern reusable for any "hook" added to an
  existing service.
- **Best-effort dispatch + structured log rows beats raise-on-any-failure.**
  The notification fan-out treats per-recipient failures as
  log rows (status='failed' with error_message), never raises
  globally. The upload itself never gets undone by a notification
  problem — the row stays at 'published' even if all sends fail.
  Future dashboard panel (Phase 4 itself) renders the delivery
  health from the log, surfacing partial-failure patterns to the
  operator without breaking the upload pipeline. **Pattern:** when
  a side-effect chain runs after a successful primary action, the
  side-effect failures should NEVER undo the primary; they log +
  surface for human review.
- **Cumulative-views chart on a SNAPSHOT still tells a useful story.**
  The chart sums view counts ordered by published_at ASC — gives a
  "growth over time" feel even though no daily history exists. Daily
  snapshots are deferred (would need a new table + a cron). This
  approach lets the chart ship in Phase 4 without infrastructure
  work; promote to a real time-series when a 2nd product needs the
  same shape.

### Interesting findings
- **The 4-state notification badge** (none / all_sent / partial /
  all_failed) is enough to describe every dispatch outcome the UI
  needs. Avoided a 5th state ("pending") because the dispatcher runs
  synchronously at publish time — log rows arrive before the
  dashboard reads them. If async dispatch lands later, "pending"
  becomes a 5th badge.
- **Two-query Python-side join** for the recent-uploads panel
  (jobs query + log query, then bucket by upload_job_id in Python)
  beats a PostgREST embed (`select=*,notification_log(*)`) for clarity.
  Embed-syntax is fragile when the join is one-to-many + needs
  aggregation; Python with a small bucket dict is honest and easy
  to read. Worth the extra round-trip given the row counts (≤10 jobs).
- **`asyncio.run` inside a sync BackgroundTasks worker is safe.** The
  sync function runs in a thread-pool thread, where no event loop
  is already active — so `asyncio.run` creates a fresh loop, runs
  the coro, tears down. Different from the MCP-server case (where
  the host loop is running and `asyncio.run` raises). The mental
  model: `asyncio.run` is safe in sync code that runs in any thread
  EXCEPT the main event loop's thread.

### Knowledge pieces
- **SMTP gotcha — Gmail App Passwords.** `smtp.gmail.com:465` with
  `SMTP_SSL` works only with App Passwords (not the account
  password); the password lives in `.env` as `SMTP_PASSWORD`. The
  Settings → API Keys tab surfaces "configured/missing" health to
  guide the operator. Documented in `email_service.py`'s
  `EmailNotConfigured` message.
- **`asyncio.gather(*tasks, return_exceptions=True)`** is the right
  shape for fan-out where individual failures shouldn't tank the
  whole batch. The notification dispatcher gathers per-recipient
  per-channel sends; each one's success/failure becomes a log row.
  The `outcome.succeeded`/`failed` count drives the upload-job
  status transition.
- **`additional_contexts` pattern (from Docker)** generalizes to
  Python-side mocking: when a helper has multiple side-effect
  channels (email + WhatsApp), inject the channels as `Optional`
  dependencies + skip-with-log when None. Lets tests pass `None`
  for one channel + a mock for the other without rebuilding the
  whole service.
- **Dashboard chunk size (362 KB ungzipped, 108 KB gzipped) is
  recharts**. Lazy-loaded so the home → upload path doesn't pay
  the cost. If chunk weight becomes a concern, the next step is
  `recharts/lib/chart/LineChart` tree-shaking imports — but Phase 4
  ships at acceptable weight without it.

---

## Project Close — YouTube Crawler (all 4 phases ✅, 2026-05-06)

> **All four phases of PLAN.md complete.** From scaffold-only to a
> working YouTube management tool: OAuth + upload (browser + drive) +
> notifications (WAHA + SMTP) + video listing with cache + analytics
> dashboard. End-state:
>
> - **Backend:** 153/153 tests, 4 routers (settings + upload + videos +
>   dashboard), 7 services, 5 migrations, full Phase-4-grade auth
>   (factory pattern via Engineer A's hardening project).
> - **Frontend:** vite build clean, 5 lazy chunks (Dashboard / Upload /
>   Videos / Settings / Equipe), recharts integrated.
> - **Docker:** compose stack ready (`docker compose up` fires the
>   "deploy drill" per the documented recipe).
> - **Knowledge tracking:** every phase has 5-category findings entries
>   above. Five lessons promoted to noc memory + KB during the parallel
>   engineer dispatch.
>
> Next plausible next-steps the user may want to consider:
> 1. **Bring it online for testing** — `cd noctusai-youtube-crawler &&
>    cp .env.example .env && (fill keys) && docker compose up`. Per
>    `KB § GUIDES/deploy-workspace-online.md`.
> 2. **Promote to noc** — `noctus.dev.promote_from_seed_workspace` to
>    move the workspace product into noc as a real product (this
>    workspace was a "testing ground"; promotion is the path to
>    production).
> 3. **File backlog projects** identified during this session:
>    cross-product seed-auth-deps rollout, ProductDependencies
>    deletion, frontend Vitest variant of the keeper detector,
>    shadcn UI absorption (N=4).

### Knowledge pieces
- **`uploaded_via_app` is a JOIN materialized at sync time, not at
  read time**. The cache row stores the boolean; the sync pipeline
  pre-fetches the set of `upload_jobs.youtube_video_id WHERE status='published'`
  and uses Python set membership. This beats a runtime JOIN on every
  list query (which would need either a view or a JOIN through the
  PostgREST API both fragile + slower).
- **Cursor pagination + `limit + 1` trick**. Asking the DB for
  `limit + 1` rows lets the API detect "has next page" without a
  separate count query. The extra row gets sliced off before the
  response; its `published_at`/`id` becomes the cursor. Cheap +
  correct; no off-by-one.

---

