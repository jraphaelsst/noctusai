# seed-hardening-from-youtube-crawler — Project Document

> Living document. Phases evolve as work progresses. Authored zero-context.

- **Created:** 2026-05-04
- **Last updated:** 2026-05-04
- **Status:** Phase 0 ✅ → Phase 1 ✅ → Phase 2 ready
- **Owner / stakeholders:** jraphaelsst · architect (Claude Opus 4.7)
- **Related docs:** `KB § 03-SEED-ARCHITECTURE.md` · `KB § PATTERNS/seed-fake-real-adapter.md` · `KB § PATTERNS/branching-and-merging.md` · `KB § PATTERNS/master-tree-parallel-batches.md` · sibling workspace at `~/Documents/repository/NoctusAI/noctusai-youtube-crawler/`
- **Project slug:** `seed-hardening-from-youtube-crawler` (intent = `hardening`; lives at `projects/<slug>/` because the work is platform-wide seed/lib changes that propagate to every product)

---

## 1. Context & Purpose

A YouTube-uploader product (`youtube-crawler`) was scaffolded into a sibling seed workspace on 2026-05-04 (workspace bootstrap + `noctus.dev.scaffold_product`). An out-of-scope agent then drafted a build plan for that product. Reviewing the plan against the workspace's seed-first methodology surfaced **eleven candidate seed-or-platform changes** — five from the critique itself (SMTP backend, encrypted-tokens helper, youtube integration, FakeMode UX, generic worker / oauth router / health endpoints), six from architect-side observations (jobs primitive, storage adapter, quota tracker, scaffold template fixes, migration scaffolder MCP tool, port-range reservation).

The youtube-crawler product would consume these seed surfaces in its own Phase 1. Building them in the product first = consumer-side fork. Building them in seed first = next-product-too gets them automatically. **This project lifts them into seed BEFORE youtube-crawler consumes them.**

Win condition: youtube-crawler's PROJECT.md Phase 1 reads "consume Batch A surfaces" instead of "rebuild SMTP / encrypted-tokens / youtube-client in product code."

---

## 2. Confirmed constraints

- **User explicitly authorized SMTP-as-second-provider before canonical refactor** — "we are good to implement the smtp, even having the resend. It's gonna get absorbed in the future, so we have an additional provider." *(Rules out blocking on the Protocol+Fake+Real+factory absorption; SMTP lands as parallel provider in the existing flat module; canonical refactor stays a follow-up.)*
- **End-to-end execution authorized** — "Branch it and let's roll end-to-end." *(Rules out per-phase user check-in; architect drives phase progression; engineer dispatch in parallel; user is consulted only on hard ambiguity.)*
- **Branching-first orchestration** — three Phase 1 items are independent → parallel engineers in worktrees, single dispatch turn. *(Rules out serial execution where chunks don't collide.)*
- **Seed-as-safe-home framing** — "the intent of the seed is giving a stable and safe home for new products and functionalities to grow healthy." *(Rules out junk-drawer accumulation; every absorb/build is judged by "does this catch a class of slips at the next scaffold?" not just "is this reused?".)*

---

## 3. Design principles

1. **Lift to seed BEFORE consumer ships.** Every Batch A item is a youtube-crawler dependency. Building in seed first eliminates the consumer-side fork at the source.
2. **Canonical Fake+Real+factory shape for new IO modules.** New work (encrypted_tokens is pure-crypto so exempt; youtube IS IO so canonical) ships in Protocol+Fake+Real+factory mirroring `integrations/google_calendar` + `google_maps`. Half-shipped (Protocol+Real or Protocol+Fake only) generates consumer forks.
3. **Existing flat-shape modules extend in place; refactor to canonical is a separate follow-up.** Email module is flat-function shape — SMTP added as parallel provider (already done). Don't double-scope: refactor-to-canonical is a project of its own.
4. **Engineer briefs are self-contained + zero-context.** Architect plans, engineers execute. Each brief includes Write-authorization for `findings.md` / proposal `.md` (else subagents refuse per "NEVER create *.md files" default).
5. **Parallel dispatch in worktrees.** No two engineers share a working tree. Master-tree parallel-batches pattern: engineers commit + branch-push from their worktree; architect merges branches back into the integration branch.

---

## 3a. Seed-first analysis (REQUIRED)

The six-question checklist applied to the project as a whole:

1. **Is the contract identical for every product?** YES — every product needing email-with-SMTP, encrypted token storage, YouTube data, generic worker, OAuth callback, health endpoint, file storage, or quota tracking gets the SAME seed shape. Variations (which YouTube quota? which SMTP backend?) are configuration, not code. Per-product code count for the contract = 0.
2. **Is the data source product-specific?** Mixed — *yes for "what to store"* (each product has its own DB / its own YouTube quota / its own job types), *no for "how to store / send / track"* which is the seed concern. Seed ships the shape; products bring the data.
3. **Is the placement product-specific?** No. Seed-lib modules live in `noctusai_lib/integrations/` + `noctusai_lib/security/` + `noctusai_lib/domain/` (already existing layer split per `KB § PATTERNS/seed-lib-layout.md`). MCP tools live in `mcp/noctusai/tools/noctus/dev/` (already existing). Frontend primitives live in `seed/lib/frontend/` (already existing).
4. **Is the visibility / permission rule the same?** Yes for the seed primitives (cross-product). Per-product gates (e.g. "only admin sees API keys tab") remain product concerns.
5. **Does the seam already exist in seed?** Mixed:
   - SMTP — `integrations/email/digest.py` exists with Resend; SMTP added as second provider (DONE — Phase 1.1).
   - Encrypted tokens — `security/` exists; only `webhook_signatures.py` ships; new `encrypted_tokens.py` adds. Phase 1.
   - YouTube — `integrations/google_calendar/` + `google_maps/` are the canonical templates; new `integrations/youtube/` mirrors. Phase 1.
   - Migration scaffolder — `mcp/noctusai/tools/noctus/dev/scaffold.py` exists for products; new `scaffold_migration` is a sibling MCP tool. Phase 1.
   - Generic worker — `domain/chatbot/worker.py` ships chatbot-shaped; lift to `domain/jobs/worker.py` (or `runtime/worker.py`). Phase 2.
   - OAuth router — `integrations/google_calendar/oauth_adapter.py` is coupled; lift to `security/oauth/`. Phase 2.
   - Health endpoints — `noctusai_seed.create_product_app` exists; extend with `/_health` + `/_ready`. Phase 2.
   - FakeMode badge — `seed/lib/frontend/` exists; new `<FakeModeBadge>` + `useEnvMode()`. Phase 3.
   - Storage — no `integrations/storage/` exists; new module. Phase 3.
   - Quota tracker — no module exists; new `integrations/quota/`. Phase 3.
   - Scaffold polish — `scaffold.py` exists; extend (slug placeholder, .env.example whitelist, validate_product enforcement). Phase 3.
   - Port reservation — `available_ports` exists greedy; extend to range-reservation. Phase 3.
6. **Default-on or opt-in?** Mostly opt-in by configuration (SMTP, YouTube integration, OAuth providers, storage, quota). Health endpoints + FakeMode badge are default-on (every product gets them via `create_product_app` / sidebar inheritance). Encrypted tokens + worker + jobs + migration scaffolder are opt-in toolkits (you reach for them when you need them).

**Litmus — per-product code count for cross-cutting work:**
- [x] **0 lines** for the seed primitives themselves. youtube-crawler will consume `noctusai_lib.integrations.youtube.make_client(...)`, `noctusai_lib.security.encrypted_tokens.encrypt(...)`, `noctusai_lib.integrations.email.send_to_one(...)` (already shipped) — all imports, no copies.
- [x] **A small section** of product-specific data wiring (which channel? which org token? which quota cap?) is acceptable because the configuration IS product-specific.

**Phase plan implications:** §6 phases work in seed (correct). No phase walks through products. Single sister product (youtube-crawler) consumes after this project closes.

---

## 4. Scope

**In scope (Batch A — Phase 1):**
- SMTP email backend alongside Resend in `integrations/email/digest.py`. **DONE 2026-05-04** (Phase 1.1, committed pre-project per architect-decision; folded in here as the project's first phase task).
- `noctusai_lib/security/encrypted_tokens.py` — Fernet helper for OAuth-token-at-rest encryption. N=2 trigger (whatsapp-google-scheduling + youtube-crawler).
- `noctusai_lib/integrations/youtube/` — Protocol+Fake+Real+factory. Encodes correct quota math (`channels.list` → `uploads` playlist → `playlistItems.list`).
- `noctus.dev.scaffold_migration` MCP tool — emits next-numbered SQL pre-wired with `set_search_path` + `updated_at_trigger` + `rls_subquery_policy` from `noctusai_lib.domain.sql_templates`.

**In scope (Batch B — Phase 2):**
- Generic worker — lift `domain/chatbot/worker.py` shape into `domain/jobs/worker.py` (or `runtime/worker.py`).
- Jobs primitive — `domain/jobs/` with Job entity + status state machine + retry policy + repo Protocol+Fake+RealSupabase.
- OAuth router — `noctusai_lib/security/oauth/` Protocol + Google provider (lifted from google_calendar) + Fake + factory + a seed-side `oauth_router(*providers)` for `create_product_app` to mount.
- Health endpoints — `/_health` + `/_ready` baked into `create_product_app()` with vendor-ping hooks (DB, Redis, key vendors).

**In scope (Batch C — Phase 3):**
- Frontend `<FakeModeBadge>` + `useEnvMode()` in `seed/lib/frontend/`.
- `noctusai_lib/integrations/storage/` — Supabase Storage + Local + Fake.
- `noctusai_lib/integrations/quota/` — quota / rate-limit tracker, Redis-backed counter + Fake.
- Scaffold template fixes: README slug placeholder, `.env.example` whitelist, `validate_product` enforcement of `next_steps`, `available_ports` named-range reservation.

**Out of scope (deferred — with reason):**
- Canonical refactor of email module from flat-function shape to Protocol+Fake+Real+factory — *deferred because user explicitly authorized SMTP-as-parallel-provider with absorption later; refactor is a project of its own.*
- youtube-crawler product implementation itself — *deferred to its own product project; this project ships the surfaces it consumes.*
- Per-product token-encryption migration (existing whatsapp-google-scheduling stored creds) — *deferred to a separate `whatsapp-google-scheduling-encrypt-tokens-migration` follow-up; this project ships the helper, not the data migration.*

---

## 5. Architecture / Data Model

**Seed-lib additions** (under `seed/lib/backend/noctusai_lib/`):

```
integrations/
  email/digest.py             # EXTEND — SMTP backend (Phase 1.1, DONE)
  youtube/                    # NEW — Phase 1.3
    __init__.py               # public exports
    protocol.py               # YoutubeClient Protocol
    fake.py                   # FakeYoutubeClient
    real.py                   # RealYoutubeClient (google-api-python-client)
    factory.py                # make_youtube_client(...)
  storage/                    # NEW — Phase 3
  quota/                      # NEW — Phase 3
security/
  encrypted_tokens.py         # NEW — Phase 1.2 (Fernet helper)
  oauth/                      # NEW — Phase 2
domain/
  jobs/                       # NEW — Phase 2
    __init__.py
    entity.py                 # Job + status state machine
    repo.py                   # JobRepository Protocol + Fake + RealSupabase
    worker.py                 # generic worker (lifted from chatbot/worker.py shape)
```

**MCP toolkit additions** (under `mcp/noctusai/tools/noctus/dev/`):

```
scaffold_migration.py         # NEW — Phase 1.4 (emits numbered SQL pre-wired)
```

**Frontend additions** (under `seed/lib/frontend/src/`):

```
components/FakeModeBadge.tsx  # NEW — Phase 3
hooks/useEnvMode.ts           # NEW — Phase 3
```

**Branching topology:**

```
seed-hardening-from-youtube-crawler  (integration branch)
  ├── sh-yt-encrypted-tokens         (Phase 1.2 worktree)
  ├── sh-yt-youtube                  (Phase 1.3 worktree)
  ├── sh-yt-migration-scaffolder     (Phase 1.4 worktree)
  └── ... (Phase 2 + 3 branches as work progresses)
```

Master-tree parallel-batches pattern (per `KB § PATTERNS/master-tree-parallel-batches.md`): engineers in worktrees, architect on integration branch, merge after each phase, run pytest at the integration branch boundary.

---

## 6. Implementation phases

### Phase 0 — File project + branch ✅
- [x] File `projects/seed-hardening-from-youtube-crawler/PROJECT.md` (this doc)
- [x] Create branch `seed-hardening-from-youtube-crawler` from origin/main

**Improvements:** none identified — Phase 0 is the project-creation gate; no code changed.

### Phase 1 — Batch A (blocks youtube-crawler) ✅

**Phase 1 close summary:** All four Batch-A surfaces shipped in seed before youtube-crawler ships. 738/738 seed-lib backend tests green at integration tip; 26/26 MCP scaffold-suite tests green. Three engineers ran in parallel via worktrees + single dispatch turn; integration branch absorbed each via `--no-ff` merges (3acc958 → 3c7d305 → 64ebc1c → fe6988f).

**Phase 1 improvements (5 cross-cutting findings — triaged at close):**
- **APPLIED INLINE** Pre-commit hook venv-discovery fixed for worktrees (`scripts/pre-commit` blocks 2 + 5): when `$REPO_ROOT/venv/bin/python` misses, now falls back to the main repo's venv via `git rev-parse --git-common-dir`. Hit by all 3 engineers; structural fix prevents recurrence on every future parallel-dispatch.
- **APPLIED INLINE** `cryptography>=42.0` promoted to explicit dependency in `seed/lib/backend/pyproject.toml` (Engineer A bystander finding). Was transitive via google-auth/PyJWT; both `webhook_signatures.py` and new `encrypted_tokens.py` rely on it. Promotion prevents silent break on a future transitive drop.
- **ACCEPTED-WITH-RATIONALE** `TestSqlTemplatesIntegration` test class duplicated in `test_scaffold.py` + `test_scaffold_migration.py` (N=2). Cataloged in `KB § PATTERNS/accept-with-rationale.md` — extraction destination depends on whether Phase 2/3 adds a third SQL-emitting tool; revisit at N=3.
- **ACCEPTED-WITH-RATIONALE** `tests/test_youtube_integration.py` flat path (sibling integrations are nested under `tests/integrations/<name>/`). Cataloged. Cosmetic; aligns at next integration add.
- **DEFERRED** MCP test path-fragility (8 pre-existing failures using `Path.relative_to(REPO_ROOT)` that break in worktrees). Out of scope for this project; filed as future project candidate `mcp-tests-worktree-aware-path-resolution`.

**Phase 1.1 ✅** — SMTP backend alongside Resend in `integrations/email/digest.py` (2026-05-04, landed pre-project, folded in here).
- [x] **1.1** `_resolve_smtp_config` + `_resolve_email_backend` + `_send_via_smtp` (sync stdlib smtplib, async via asyncio.to_thread). Three security modes: ssl / starttls / none. Resend wins by default when both configured (back-compat); explicit override via `email_backend` credential. 19 new tests, 35/35 email tests green, 684/684 seed-lib tests green.

**Improvements (Phase 1.1):**
- Pre-existing email-module tests use `monkeypatch.setattr(digest_module, "_post_to_resend", ...)` — patches our own internal function name (no-monkeypatch rule's anti-pattern). Module pre-dates the rule (2026-04-25). New SMTP tests patch at `smtplib.SMTP` / `SMTP_SSL` boundary directly (external-service carve-out), correct shape. Test-shape gap acknowledged not fixed in this scope; canonical Protocol+Fake+Real+factory refactor is a follow-up project of its own.
- Module is half-shipped per the `KB § PATTERNS/seed-fake-real-adapter.md` rule (Real-only, no Protocol, dry-run logs serve as fake). SMTP added today is the second `Real`-shaped consumer that makes the canonical lift cheaper. Filed as out-of-scope deferred (§4).

- [x] **1.2** `security/encrypted_tokens.py` (Fernet helper) — Engineer A in `sh-yt-encrypted-tokens` worktree. Module: `generate_key` / `encrypt` / `decrypt` / `rotate_key` + `MultiKeyDecryptor` class. 20 new tests.
- [x] **1.3** `integrations/youtube/` (Protocol+Fake+Real+factory) — Engineer B in `sh-yt-youtube` worktree. 6 files under `noctusai_lib/integrations/youtube/` + 34 tests. Encodes channel→uploads-playlist→playlistItems trick at the seed level; quota math documented in Protocol docstrings + asserted by Fake (1 unit `get_channel`, 2 units `list_channel_videos` page, 100 units `search`).
- [x] **1.4** `noctus.dev.scaffold_migration` MCP tool — Engineer C in `sh-yt-migration-scaffolder` worktree. New `mcp/noctusai/tools/noctus/dev/scaffold_migration.py` + 19 tests covering numbering / schema-default / schema-override / `with_table=` block / 6 error paths / 3 keeper-detector-style integration assertions vs the canonical `sql_templates` helpers. `products_dir=` injection seam added during build to keep tests hermetic without monkey-patching the module binding (lesson logged).

### Phase 2 — Batch B (structural lifts)
- [ ] **2.1** Generic worker — lift `domain/chatbot/worker.py` to `domain/jobs/worker.py`
- [ ] **2.2** Jobs primitive — `domain/jobs/` (Job + repo + state machine)
- [x] **2.3** OAuth router — `security/oauth/` + seed-side `oauth_router(*providers)`
- [ ] **2.4** Health endpoints — `/_health` + `/_ready` baked into `create_product_app`

### Phase 3 — Batch C (polish + propagation)
- [ ] **3.1** Frontend `<FakeModeBadge>` + `useEnvMode()`
- [ ] **3.2** `integrations/storage/` (Supabase Storage + Local + Fake)
- [ ] **3.3** `integrations/quota/` (Redis + Fake)
- [ ] **3.4** Scaffold polish: README slug placeholder, `.env.example` whitelist, `validate_product` enforcement, `available_ports` range reservation

### Phase 4 — Project close
- [ ] Final pytest green across seed/lib/backend + mcp/noctusai
- [ ] One bundled phase proposal per phase filed in `proposals/`
- [ ] Three-way sync: KB depth + CLAUDE.md pointers + memory entries
- [ ] `noctus.dev.archive` move to `archive/projects/<today>/<NN>-seed-hardening-from-youtube-crawler/`
- [ ] Final commit + push to `main` (project-close gate)

---

## 7. Open questions

1. **Worker home — `domain/jobs/worker.py` vs `runtime/worker.py`?** — needs answer before Phase 2.1. Recommendation: `domain/jobs/worker.py` because the worker IS the job consumer (couples cleanly with the jobs primitive). Architect-decided unless user redirects.
2. **OAuth provider abstraction — provider-per-vendor or single-Google-with-scopes?** — needs answer before Phase 2.3. Recommendation: provider-per-vendor (Google, future Slack, Stripe, etc.) since scopes + token refresh + revocation differ by vendor; "Google" is one provider with multiple scope sets. Architect-decided unless user redirects.
3. **Health endpoint convention — `/_health` (underscore) vs `/health`?** — needs answer before Phase 2.4. Recommendation: `/_health` underscore-prefix to denote system / non-business endpoint, matching the `_*` convention used in framework debug routes elsewhere. Architect-decided unless user redirects.
4. **Quota tracker storage — Redis-only or Redis+SQL fallback?** — needs answer before Phase 3.3. Recommendation: Redis with hourly persist-to-SQL for audit trail. Defer to architect.

---

## 8. Dependencies & blockers

- **`noctusai_lib.config.credentials.resolve_credential` + `configure_credentials`** — used by SMTP backend (DONE) and youtube backend (will use). No blocker.
- **`cryptography` package** — needed by Fernet helper. Already in `seed/lib/backend/requirements.txt` (used by webhook signatures). No blocker.
- **`google-api-python-client`** — needed by RealYoutubeClient. Already used by `google_calendar`. No blocker.
- **Pre-commit hook** — KB-sync verifier may flag if KB pointers are added before KB docs. Land KB depth first, then CLAUDE.md pointers (per "Docs KB first, CLAUDE.md second" rule).

---

## 9. Success criteria

- [ ] `seed/lib/backend` pytest green at the integration-branch tip after every phase merge.
- [ ] `mcp/noctusai/tests/` pytest green when MCP-toolkit changes land (Phase 1.4 + 3.4).
- [ ] youtube-crawler product (in sibling workspace) can `from noctusai_lib.integrations.youtube import make_youtube_client` AND `from noctusai_lib.security.encrypted_tokens import encrypt, decrypt` AND consume `send_to_one(...)` with SMTP backend — without touching its own product code for these concerns.
- [ ] `noctus.dev.scaffold_migration --product youtube-crawler --name oauth_credentials` produces a numbered migration file with the canonical helpers pre-applied.
- [ ] Three-way sync done: `KB § PATTERNS/seed-fake-real-adapter.md` references the new modules; `CLAUDE.md` § Map gets pointers if needed; memory gets entries for any new methodology rule.
- [ ] Final fast-forward push to `main`.

---

## 10. How to use this project

- Phase-by-phase, but architect drives progression in this case (user said "roll end-to-end").
- Engineers (subagents) execute Phase 1 sub-tasks 1.2, 1.3, 1.4 IN PARALLEL via worktrees + single dispatch turn.
- Each engineer commits + pushes to its own branch; architect merges branches back to `seed-hardening-from-youtube-crawler` and runs pytest.
- `findings.md` aggregates engineer slips / lessons / surprises across phases.
- Per-phase commit at phase close (no push). Final commit + push at project close.

---

## 11. Change log

| Date | Change | By |
|---|---|---|
| 2026-05-04 | Phase 1 close ✅ — all 4 Batch-A surfaces merged into integration branch (3acc958→3c7d305→64ebc1c→fe6988f); 738/738 seed-lib + 26/26 MCP-scaffold tests green. Triage applied: pre-commit worktree-venv fixed inline, `cryptography` promoted to explicit dep, 2 N=2 recurrences cataloged in accept-with-rationale, MCP test path-fragility deferred to its own project. | architect (Claude Opus 4.7) |
| 2026-05-04 | Phase 1.4 — `noctus.dev.scaffold_migration` MCP tool landed in `mcp/noctusai/tools/noctus/dev/scaffold_migration.py` + 19 tests covering numbering / schema-default / schema-override / `with_table=` block / six error paths / three keeper-detector-style integration assertions vs the canonical helpers. Registered alphabetically in `__init__.py`. Engineer C, branch `sh-yt-migration-scaffolder`. | Engineer C (Claude Opus 4.7) |
| 2026-05-04 | Phase 1.3 — `integrations/youtube/` landed in seed (canonical Protocol+Fake+Real+factory). 6 source files + 1 test file (34 tests). Encodes channel→uploads-playlist→playlistItems quota-cheap path so consumers never re-derive it. Engineer B, branch `sh-yt-youtube`. | Engineer B (Claude Opus 4.7) |
| 2026-05-04 | Phase 1.2 — Fernet helper `security/encrypted_tokens.py` (`generate_key` / `encrypt` / `decrypt` / `rotate_key` / `MultiKeyDecryptor`); 20 new tests. Engineer A, branch `sh-yt-encrypted-tokens`. | Engineer A (Claude Opus 4.7) |
| 2026-05-04 | Phase 1.1 — SMTP backend landed in seed `integrations/email/digest.py` + 19 new tests; 35/35 email tests green; 684/684 seed-lib tests green. | architect (Claude Opus 4.7) |
| 2026-05-04 | Phase 0 — Project filed; branch `seed-hardening-from-youtube-crawler` created from origin/main. | architect (Claude Opus 4.7) |
