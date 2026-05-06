# youtube-crawler-build — Project Document

> Living document. Phases evolve as work progresses. Authored zero-context.
> Refined 2026-05-05 against noc methodology after the closing of `seed-hardening-from-youtube-crawler` (archive #10, 2026-05-04). The original draft (out-of-environment agent) re-derived ~70% of the seed surfaces that hardening project explicitly lifted into seed *for this product to consume*. This refinement maps every "service" to its existing seed surface and trims the file tree accordingly.

- **Created:** 2026-05-04 (original draft) · refined 2026-05-05
- **Last updated:** 2026-05-05
- **Status:** Refined → ready for Phase 0 audit
- **Owner / stakeholders:** jraphaelsst · architect (Claude Opus 4.7)
- **Related docs:** `KB § 03-SEED-ARCHITECTURE.md` · `KB § PATTERNS/seed-fake-real-adapter.md` · `KB § PATTERNS/template-workspace.md` · archive `archive/projects/2026-05-04/10-seed-hardening-from-youtube-crawler/PROJECT.md` · sibling workspace at `~/Documents/repository/NoctusAI/noctusai-youtube-crawler/`
- **Project slug:** `youtube-crawler-build` (intent = `wiring` — consumer wiring against seed surfaces). **Lives at:** `products/youtube-crawler/projects/youtube-crawler-build/PROJECT.md` (single-product scope; product tree). The original `PLAN.md` at repo root is a clean-folder violation — the file gets moved into the product tree on Phase 0 close.

---

## 1. Context & Purpose

A YouTube management product (`youtube-crawler`) was scaffolded into a sibling seed workspace on 2026-05-04 (`~/Documents/repository/NoctusAI/noctusai-youtube-crawler/`) via `noctus.dev.scaffold_product`. Capabilities to ship:

1. **Upload videos** to YouTube (browser file upload + Google Drive link → download → upload).
2. **Notify recipients** after upload via WhatsApp (WAHA) and email (SMTP via Gmail App Password).
3. **List all channel videos** with metrics (full channel, not just app-uploaded).
4. **Analytics dashboard** with KPIs, charts, recent activity.
5. **Settings UI** for OAuth connection, recipient management, env-key status.

**Why this is mostly a wiring project, not a build project.** Yesterday's `seed-hardening-from-youtube-crawler` shipped — into seed, with Protocol+Fake+Real+factory shape — every IO surface this product needs: SMTP email backend, encrypted-tokens helper, full YouTube client with quota math, generic jobs primitive + worker, OAuth router, storage adapter, quota tracker, FakeMode badge, scaffold-migration MCP tool. **The win condition for hardening was: "youtube-crawler's PROJECT.md Phase 1 reads 'consume Batch A surfaces' instead of 'rebuild SMTP / encrypted-tokens / youtube-client in product code.'"** This refinement makes the project meet that win condition.

The original draft at root proposed `youtube_service.py` (re-derives `noctusai_lib.integrations.youtube`), `email_service.py` (re-derives `noctusai_lib.integrations.email`), an in-repo encryption flow (re-derives `noctusai_lib.security.encrypted_tokens`), an OAuth callback router (re-derives `noctusai_lib.security.oauth.router`), an upload job pipeline (re-derives `noctusai_lib.domain.jobs.worker`), root-level `docker-compose.yml` + `Dockerfile` + `.env.example` (clean-folder violations + per-product .env duplication), and a custom YouTube list strategy using `search.list` (100 units / page) when the seed already documents the `playlistItems`-based strategy at ~2 units / page. The refinement removes every re-derivation and trims the file tree from ~25 new product files down to ~14.

---

## 2. Confirmed constraints

- **WhatsApp** — Use `noctusai_lib.integrations.whatsapp` (WAHA). WAHA + Redis containers brought from `whatsapp-google-scheduling` repo. *(Rules out re-implementing WAHA HTTP client; recipes WAHA container.)*
- **Email** — SMTP via Gmail App Password using `noctusai_lib.integrations.email.send_to_one` / `send_to_many` (SMTP backend lifted into seed Phase 1.1 of hardening). *(Rules out a per-product `email_service.py`; rules out reading SMTP creds from `os.environ` directly — use `resolve_credential`.)*
- **Channels** — Single YouTube channel for now. *(Rules out multi-channel UI / per-channel quota partitioning until N=2.)*
- **Notification recipients** — Fixed list configured in Settings (name, email, whatsapp, active toggle). Per-video override at upload time (deselect from pre-checked list). *(Rules out per-upload manual recipient entry; drives the recipients table.)*
- **Video source** — Browser file upload (drag-drop) + Google Drive shared link (backend downloads via `gdown` / `httpx` then uploads to YouTube). *(Rules out direct Drive→YouTube transfer; we hop through `tmp/` first to honor YouTube resumable-upload contract.)*
- **API keys** — Code references `.env` vars via `noctusai_lib.config.credentials.resolve_credential` (3-tier: env → org_settings → vault). Settings UI shows configured / missing badges. Keys themselves live in repo-root `.env` (single-source rule). *(Rules out a per-product `.env.example`; rules out a Settings UI that writes keys to disk.)*
- **YouTube API auth** — OAuth 2.0 via `noctusai_lib.security.oauth.router` mounted with the Google provider. Refresh token stored encrypted via `noctusai_lib.security.encrypted_tokens`. *(Rules out a per-product OAuth flow; rules out plaintext token storage.)*
- **Single root `.env`** — Per CLAUDE.md "Seed first" + "Finish the session" rules (memory mirror `feedback_seed_first.md` + `feedback_finish_session.md`): one `.env` at repo root, never per-product. *(Rules out the original draft's `.env.example` at the sibling-workspace root.)*
- **Sibling workspace is consume-only** — Per `KB § PATTERNS/template-workspace.md`: the sibling workspace consumes 8 noc surfaces via read-only symlinks. **Edits to the symlinked surfaces (`seed/`, `noctusai_lib/`, `mcp/`, `CLAUDE.md`, etc.) are forbidden** — they belong in noc proper. Anything that surfaces a seed gap during this build files a follow-up project in noc, never edits noc from the workspace. *(Rules out drive-by seed edits during product wiring.)*

---

## 3. Design principles

How we're approaching *this specific problem* (beyond the platform-wide `CLAUDE.md` rules):

1. **Consume, don't re-derive.** Every IO concern (YouTube, SMTP, WAHA, OAuth, encrypted tokens, jobs/worker, storage, quota) lands as an *import* from `noctusai_lib`, not as a per-product `*_service.py`. The four surviving product-side services (§5.2) are orchestrators of seed primitives — no SDK code, no SMTP code, no Fernet code.
2. **Verify the seed ships it before locking each consumption.** For every "consume seed X" line in §3a / §6, the engineer reads `seed/lib/backend/noctusai_lib/<area>/__init__.py` exports + the concrete adapter file before starting. Protocol+Fake without Real = consumer-side fork; we file a follow-up against noc instead of re-deriving. *(Already done at refinement time for the eleven seed-hardening surfaces; redo at execution time for any newly-surfaced dependency.)*
3. **Seed gaps surfaced during build → follow-up project against noc, not drive-by edits.** Sibling workspace cannot modify noc. Anything found missing (e.g. a YouTube channel-stats helper that should live in `integrations/youtube/types.py`) gets logged in `findings.md` + filed as `youtube-crawler-build-followups.md` against noc.
4. **Quota math is non-negotiable.** YouTube allots 10,000 units / day. The seed YouTube client documents that `search.list` burns 100 units / page while `channels.list → uploads playlist → playlistItems.list` burns ~2 units / page (50× cheaper). The product MUST use the cheap path for channel listing — verify the strategy at code-review time.
5. **MCP-first for agent-exposable capabilities.** The four headline capabilities (upload-video, list-videos, dashboard-stats, sync-channel) are agent-actionable. They expose as `noctus.youtube_crawler.*` MCP tools alongside the HTTP routers. Per `KB § PATTERNS/mcp-tool-conventions.md` + memory mirror `feedback_mcp_first.md`. *(One thin shell per capability; logic in the product service which itself is an orchestrator of seed primitives.)*
6. **AST-first for any code edit.** No regex / sed on `.py` or `.ts` / `.tsx`. Use `libcst` (Python) or `ts-morph` (TypeScript). Per CLAUDE.md "AST-first" rule (memory mirror `feedback_ast_first.md`).
7. **Findings.md throughout.** Every non-trivial project maintains `findings.md` at root with the five standard categories. Default-on per CLAUDE.md "Knowledge tracking" rule (memory mirror `feedback_knowledge_tracking.md`).

---

## 3a. Seed-first analysis (REQUIRED)

**Six-question checklist** (`KB § GUIDES/seed-first-design.md`):

1. **Is the contract identical for every product?** Mixed. The IO contracts (YouTube client, SMTP send, WAHA send, OAuth flow, encrypted tokens, jobs worker, storage, quota) are universal — already in seed. The orchestration contracts (which channel? which recipients? which job statuses fire which notification?) are product-specific.
2. **Is the data source product-specific?** Yes. Channel ID, recipient list, upload jobs, video cache, notification log all live in `youtube_crawler.<table>`. The data model is per-product; the *shape* of jobs/credentials is seed-shaped (consumed as templates).
3. **Is the placement product-specific?** Yes. UI pages (Dashboard / Videos / Upload / Settings) live in the product frontend.
4. **Is the visibility / permission rule the same?** Yes for the seed surfaces (org-scoped via `org_id` + RLS). Per-product gates (admin-only API Keys tab) stay product-side.
5. **Does the seam already exist in seed?** **Yes for ten of eleven, no for one.** Mapping below.
6. **Default-on or opt-in?** Opt-in by configuration — YouTube OAuth is consent-flow gated; SMTP / WAHA wired via creds. FakeMode badge is default-on (lights up when `WAHA_BASE_URL` / `SMTP_HOST` empty).

### Service-by-service mapping (the meat of §3a)

Maps every "service" / "router" / "infra" item in the original draft to its seed counterpart. **Anything in the "Seed surface" column = product code does NOT re-implement; it imports.**

| Original-draft item | Seed surface (consume) | Product-side residue | Notes |
|---|---|---|---|
| `youtube_service.py` (~150 LOC SDK wrapper) | `noctusai_lib.integrations.youtube.make_youtube_client(...)` + `Channel` / `Video` / `Playlist` / `ListResult` value objects | **NEW** `services/youtube_orchestrator.py` (~40 LOC) — wires seed client + DB cache + quota tracker | Original burns 100 units / page on `search.list`. Seed-canonical strategy is `playlistItems.list` (~2 / page). MUST use cheap path. |
| `email_service.py` (smtplib SSL sender) | `noctusai_lib.integrations.email.send_to_one(...)` / `send_to_many(...)` (SMTP backend shipped 2026-05-04 Phase 1.1) | **DELETED** — no per-product email service | SMTP creds via `resolve_credential("smtp_host", org_id)` etc. — 3-tier chain, never `os.environ`. |
| `gdrive_service.py` (~80 LOC Drive download) | `noctusai_lib.integrations.google_drive.make_drive_downloader(...)` + `parse_drive_url(...)` (lifted into seed 2026-05-06 — Protocol+Fake+Real+factory shape mirroring `youtube` / `google_calendar` / `google_maps`) | **DELETED** — no per-product `gdrive_downloader.py` | Lift authorized by user under "we'll spread it throughout soon" — seed lands ahead of N=2 rather than after. 30 tests green at lift time; 974/974 seed-lib backend tests green. |
| `notification_service.py` (SMTP code + WAHA code + recipient lookup) | `noctusai_lib.integrations.email` + `noctusai_lib.integrations.whatsapp` + `noctusai_lib.domain.notifications` (PT field mapping) | **NEW** `services/notification_dispatcher.py` (~50 LOC) — pure orchestrator: lookup recipients → loop → call seed senders → write `notification_log` rows | Zero IO code product-side. Templates (subject / message body) live in `app/templates/notification/`. |
| `upload_service.py` (queue + status state machine) | `noctusai_lib.domain.jobs.entity.Job` + `noctusai_lib.domain.jobs.repo.JobRepository` + `noctusai_lib.domain.jobs.worker.run_worker` + `noctusai_lib.domain.jobs.retry_policy` | **NEW** `services/upload_pipeline.py` (~60 LOC) — defines the per-step handlers (`download_drive`, `upload_youtube`, `notify_recipients`); generic worker dispatches | Status enum re-uses `Job.status` shape; no custom state machine. |
| Encrypted token storage (Fernet, in-line) | `noctusai_lib.security.encrypted_tokens.encrypt(...)` / `decrypt(...)` | One call site in `services/youtube_oauth.py` | `ENCRYPTION_KEY` resolved via `resolve_credential("encryption_key")`. |
| OAuth callback flow (Google consent + token exchange) | `noctusai_lib.security.oauth.router(*providers)` + `google_provider` | One mount line in `app/main.py` (`oauth_router(google_provider(...))`) + a `services/youtube_oauth.py` wrapper that maps the post-callback token to the credentials table | Mount pattern follows seed `KB § PATTERNS/seed-lib-layout.md`. |
| Health endpoints (`/_health`, `/_ready`) | Auto-mounted by `noctusai_seed.create_product_app` (Phase 2 of hardening) | **None** — already wired | Verify the scaffold's `app/main.py` calls `create_product_app()` and inherits these. |
| File storage (`tmp/uploads/`) | `noctusai_lib.integrations.storage.make_storage_adapter(use_fake=False, backend="local")` | One call in `services/upload_pipeline.py` for the download step | Local backend in dev; Supabase Storage backend in prod via env flag. |
| Quota tracking | `noctusai_lib.integrations.quota.make_quota_tracker(redis_client, key="youtube_api_units")` | One call site in `services/youtube_orchestrator.py` (decrement before each API call; refuse when budget exhausted) | Redis-backed; `FakeQuotaTracker` in dev when no Redis. |
| FakeMode UX | `<FakeModeBadge>` + `useEnvMode()` from `seed/lib/frontend/src/` | One mount in the app shell (`<FakeModeBadge />` in the header) | Lights up when WAHA / SMTP / YouTube creds missing. Frontend reads via `useEnvMode()` hook. |
| `settings_router.py` | Pattern lifted from seed `core` settings router (verify) | **NEW** `routers/settings_router.py` — endpoints listed in §5.4 below | Endpoints are product-specific (recipient CRUD, OAuth status). |
| `upload_router.py` / `videos_router.py` / `dashboard_router.py` | No seed equivalent (product-domain) | **NEW** product-side; thin REST shells over the orchestrator services | Each gets a sibling MCP tool (§8). |
| Migrations 002-006 | `noctus.dev.scaffold_migration` MCP tool emits with `set_search_path` + `updated_at_trigger` + `rls_subquery_policy` pre-wired | Five generated files (§5.3) with org_id-based RLS | Per `CLAUDE/platform.md` MCP-migrations rule (memory mirror `feedback_mcp_migrations_mirror_file.md`): every Supabase MCP DDL ALSO exists as a numbered migration file. |
| `tool_call_audits` table | `seed/lib/backend/noctusai_lib/domain/ai/migrations/tool_call_audits.sql.template` | One copy of the template into `migrations/006_tool_call_audits.sql` (substitute `{{SCHEMA_NAME}}` = `youtube_crawler`) | Records every YouTube API call (LGPD per `KB § PATTERNS/llm-tool-audit.md` + memory mirror `feedback_lgpd_first.md`). |
| Root `docker-compose.yml` + `Dockerfile` + `.env.example` | n/a — clean-folder violation | **DELETED from sibling workspace root**. Container infra (if needed for WAHA / Redis) goes under `products/youtube-crawler/infra/docker-compose.yml`, never the workspace root | Per `CLAUDE/platform.md` clean-folder rule (memory mirror `feedback_clean_folder_principle.md`). |

**Litmus — per-product code count this design requires:**

- [x] **0 lines** for every IO concern — all imports from `noctusai_lib` / seed.
- [x] **A small section** of product-specific orchestration (~250 LOC across four services) — acceptable because video-cache + recipient + upload-job flows ARE product-specific.
- [ ] ~~Multiple files per concern per product~~ — N/A. The original draft fell here; refinement moves it up two rows.

**Phase plan implications:** §6 phases work product-side because the seed work is done. No phase walks "across products" — single-product scope. **One bystander seed gap surfaced and lifted in-session** (`integrations/google_drive`, 2026-05-06) — Protocol+Fake+Real+factory shape with 30 tests, no consumer-side fork. Per the DRY recurrence rule's spirit (lift to seed when the second consumer is foreseeable, not after the fact).

---

## 4. Scope

**In scope:**
- Settings page: YouTube tab (OAuth connect/disconnect, channel info badge), Notifications tab (recipient CRUD + SMTP/WAHA status display), API Keys tab (env-key configured / missing read-only badges).
- Upload page: file drag-drop + Drive-link entry, metadata form (title / description / tags / privacy / category), recipient checkboxes (active recipients pre-checked, deselectable per upload), upload progress + history.
- Videos page: full-channel listing with view/like/comment metrics, search + filter + sort, "uploaded via app" badge, force-sync button.
- Dashboard page: KPI cards (total videos / views / likes / comments with month-over-month trend), 30-day daily-views line chart, top-5 videos, last-5 uploads with notification status.
- Migrations 002-006 (credentials, upload_jobs, video_cache, notification_recipients + notification_log, tool_call_audits) with org-scoped RLS.
- MCP tool exposure (§8): `noctus.youtube_crawler.upload_video`, `list_videos`, `get_dashboard_stats`, `sync_channel`.
- README + MASTER-PROMPT (created by `scaffold_product`; verify + populate).
- `findings.md` at project root (5 standard categories, append in-the-moment).

**Out of scope (deferred — with reason):**
- Multi-channel support — *N=1 today; revisit when a second channel is requested. Schema is org-scoped not channel-scoped — multi-channel = future migration.*
- Per-recipient delivery preferences (email-only vs whatsapp-only) — *all-active-channels default for v1; preference flags belong in a v2 follow-up if requested.*
- Direct Drive→YouTube transfer (skip the `tmp/` hop) — *requires either Drive→Storage→YouTube streaming or Drive `files.copy` + transfer. Adds complexity; defer.*
- ~~`noctusai_lib.integrations.google_drive`~~ — **LIFTED IN-SESSION 2026-05-06.** Now consumed via seed; product-side downloader retired before it ever shipped.
- Refactor of `noctusai_lib.integrations.email` from flat-function shape to canonical Protocol+Fake+Real+factory — *user-authorized SMTP-as-second-provider with absorption later (per archived hardening project §4); refactor is a project of its own.*
- Production-grade WAHA hardening (auth, multi-session, webhook signature verification on incoming) — *consume-only for outbound today; inbound webhooks are a different product surface.*

---

## 5. Architecture / Data Model

### 5.1 File tree (after refinement)

```
products/youtube-crawler/
├── README.md                         ← created by scaffold_product (verify + populate)
├── MASTER-PROMPT.md                  ← created by scaffold_product (verify + populate)
├── projects/
│   └── youtube-crawler-build/
│       ├── PROJECT.md                ← THIS FILE (relocated from repo root on Phase 0 close)
│       └── findings.md               ← NEW (5 categories; append throughout)
├── infra/
│   └── docker-compose.yml            ← NEW — only if WAHA/Redis containers needed locally; references repo-root .env
├── backend/
│   ├── app/
│   │   ├── main.py                   ← MODIFY — mount oauth_router + new product routers
│   │   ├── config.py                 ← MODIFY — extend ProductSettings with YouTube OAuth fields (creds resolved via resolve_credential at request time, NOT module-load)
│   │   ├── routers/
│   │   │   ├── settings_router.py    ← NEW
│   │   │   ├── upload_router.py      ← NEW
│   │   │   ├── videos_router.py      ← NEW
│   │   │   └── dashboard_router.py   ← NEW
│   │   ├── services/
│   │   │   ├── youtube_oauth.py        ← NEW (~30 LOC — token persistence wrapper around seed encrypted_tokens)
│   │   │   ├── youtube_orchestrator.py ← NEW (~40 LOC — wires seed YT client + DB cache + quota)
│   │   │   ├── upload_pipeline.py      ← NEW (~60 LOC — per-step handlers fed to seed jobs.worker; calls seed google_drive in the download handler)
│   │   │   └── notification_dispatcher.py ← NEW (~50 LOC — recipient lookup + fan-out via seed email + whatsapp)
│   │   └── schemas/
│   │       ├── settings.py           ← NEW
│   │       ├── upload.py             ← NEW
│   │       ├── video.py              ← NEW
│   │       └── notification.py       ← NEW
│   ├── migrations/
│   │   ├── 001_seed_youtube_crawler_product.sql  ← AUTO-EMITTED by scaffold_product (verify; registers product in core dashboard)
│   │   ├── 002_credentials.sql       ← NEW (encrypted_tokens-shaped column)
│   │   ├── 003_upload_jobs.sql       ← NEW (mirrors noctusai_lib.domain.jobs.entity.Job shape)
│   │   ├── 004_video_cache.sql       ← NEW
│   │   ├── 005_notification_recipients.sql + 005b_notification_log.sql  ← NEW (split keeps each migration single-table per platform convention)
│   │   └── 006_tool_call_audits.sql  ← copied from noctusai_lib/domain/ai/migrations/tool_call_audits.sql.template
│   ├── tests/
│   │   ├── routers/                  ← NEW (one file per router)
│   │   ├── services/                 ← NEW (one file per service; FakeYoutubeClient + FakeStorage + FakeQuota)
│   │   └── realdb/                   ← NEW (one realdb conftest mirroring core's pattern)
│   └── requirements.txt              ← MODIFY (gdown only; google-api-python-client + cryptography come from seed deps)
└── frontend/
    ├── src/
    │   ├── App.tsx                   ← MODIFY (routes + nav + <FakeModeBadge/> mount)
    │   ├── pages/
    │   │   ├── Dashboard.tsx         ← REWRITE (real analytics)
    │   │   ├── Videos.tsx            ← NEW
    │   │   ├── Upload.tsx            ← NEW
    │   │   └── Settings.tsx          ← NEW
    │   ├── components/
    │   │   ├── VideoCard.tsx         ← NEW
    │   │   ├── UploadZone.tsx        ← NEW
    │   │   ├── RecipientSelector.tsx ← NEW
    │   │   ├── MetricCard.tsx        ← NEW (check seed/lib/frontend first — possibly already shipped)
    │   │   └── ViewsChart.tsx        ← NEW
    │   └── hooks/
    │       ├── useVideos.ts          ← NEW
    │       ├── useUpload.ts          ← NEW
    │       ├── useDashboard.ts       ← NEW
    │       └── useSettings.ts        ← NEW
    └── package.json                  ← MODIFY (recharts only)
```

**Net LOC delta vs original draft:** -10 files, ~-400 LOC product-side, +0 LOC seed-side. The reduction comes from deleting `email_service.py`, `youtube_service.py`, the in-line OAuth flow, the Fernet wrapper, the custom job state machine, the root `docker-compose.yml` / `Dockerfile` / `.env.example`.

### 5.2 Service layer (orchestrators only — zero IO code product-side)

Brief signatures so the engineer reading this knows the boundary:

```python
# services/youtube_orchestrator.py (~40 LOC)
class YoutubeOrchestrator:
    def __init__(self, client: YoutubeClient, repo: VideoCacheRepo, quota: QuotaTracker): ...
    async def list_channel_videos(self, channel_id: str, *, force_sync: bool = False) -> list[Video]: ...
    async def get_video_stats_batch(self, video_ids: list[str]) -> dict[str, VideoStats]: ...
    async def upload(self, file_path: Path, metadata: VideoMetadata) -> Video: ...

# services/upload_pipeline.py (~60 LOC)
async def handle_download(job: Job, *, drive: DriveDownloader, storage: StorageAdapter) -> None: ...  # `DriveDownloader` from `noctusai_lib.integrations.google_drive`
async def handle_upload_youtube(job: Job, *, orchestrator: YoutubeOrchestrator) -> None: ...
async def handle_notify(job: Job, *, dispatcher: NotificationDispatcher) -> None: ...
# Wired into noctusai_lib.domain.jobs.worker.run_worker(handlers=[...])

# services/notification_dispatcher.py (~50 LOC)
class NotificationDispatcher:
    async def notify_upload(self, job: Job, recipient_ids: list[UUID]) -> None:
        # 1. Look up recipients
        # 2. For each: dispatch via seed email.send_to_one + whatsapp.send_text
        # 3. Write notification_log rows (sent / failed / error_message)

# services/youtube_oauth.py (~30 LOC)
async def store_credentials_for_org(org_id: UUID, raw_tokens: dict) -> None:
    enc = noctusai_lib.security.encrypted_tokens.encrypt(json.dumps(raw_tokens))
    # upsert into youtube_crawler.credentials

# Drive download is now a seed-side import, not a product-side service.
# In services/upload_pipeline.py:
#   from noctusai_lib.integrations.google_drive import (
#       make_drive_downloader, parse_drive_url,
#   )
#   drive = make_drive_downloader(api_key=settings.google_api_key)
#   file_id = parse_drive_url(job.source_url)
#   meta = await drive.download(file_id, dest=tmp_path / file_id)
```

### 5.3 Migrations

All five new migrations get scaffolded via `noctus.dev.scaffold_migration` so they ship pre-wired with `set_search_path` + `updated_at_trigger` + `rls_subquery_policy`. RLS policies use the `org_id` column with the platform-standard `auth.jwt() ->> 'org_id'` subquery. `001_seed_youtube_crawler_product.sql` is auto-emitted by `scaffold_product` (registers the product in the `core` dashboard — verify it landed; memory mirror `feedback_scaffold_auto_registers_products.md`).

Schemas of each table preserve the original draft's columns; no changes to the data model. **The shape of `upload_jobs.status` matches `noctusai_lib.domain.jobs.entity.Job.status`** — same enum, no fork. The original draft's status-enum (`queued / downloading / uploading / processing / published / notified / failed`) is fine; verify it overlaps the seed's `Job.status` enum and align.

### 5.4 Routers (HTTP surface)

Endpoint tables identical to the original draft (§5.7 there) — no changes. Three notes:

1. `/api/youtube/oauth/callback` is mounted by `noctusai_lib.security.oauth.router(google_provider(scopes=["youtube.upload", "youtube.readonly", "youtube.force-ssl"]))` — product code does NOT define the route handler.
2. `/api/settings/keys/status` reports configured / missing per env key by reading `resolve_credential(name)` for each — `not None / empty` = configured.
3. Every router endpoint that hits an external API increments the quota tracker BEFORE the call (decrement-and-check pattern); a 429 returns when the daily budget is exhausted.

### 5.5 Frontend (page specs)

Identical to the original draft (§7 there). Two refinements:

1. `<FakeModeBadge />` mounts in the app shell (top-right, near the user menu). Reads `useEnvMode()` hook from `seed/lib/frontend/src/hooks/useEnvMode.ts`. Lights up amber when any of WAHA / SMTP / YouTube creds are missing, and lists which.
2. `MetricCard` — before creating, grep `seed/lib/frontend/src/components/` for existing card primitive. If shipping, consume; if not, build product-side and flag for absorb on N=2 (mailing dashboard might want it).

---

## 6. Implementation phases

Canonical workflow per `KB § PATTERNS/project-execution.md § 0`: SCAFFOLD → PRE-PHASE → EXECUTE → PHASE-END VERIFICATION → CLOSE-PHASE → PROJECT-END VERIFICATION → PROJECT CLOSE.

**Branching topology:** project-branch `youtube-crawler-build`; engineers in worktrees for parallel phases (Phase 2 + 3 are file-disjoint after Phase 1).

### Phase 0 — Audit + project relocation

- [ ] Verify all eleven seed surfaces shipped (the §3a table maps each to its expected path); read `__init__.py` exports for each. **Hard gate** — any missing surface stops the project and triggers a follow-up against noc.
- [ ] Verify `001_seed_youtube_crawler_product.sql` was emitted by `scaffold_product` and applied (Supabase MCP `list_migrations` for the core schema).
- [ ] Verify `products/youtube-crawler/README.md` + `MASTER-PROMPT.md` exist (created by scaffold).
- [ ] Move this `PLAN.md` from sibling-workspace root → `products/youtube-crawler/projects/youtube-crawler-build/PROJECT.md` (clean-folder).
- [ ] Initialize `findings.md` at the project root with the 5 standard categories (errors / mistakes-slips / lessons / interesting-findings / knowledge-pieces).
- [ ] Run absorption-search sextet baseline: `noctus.dev.scan_cross_product_helpers` + `noctus.dev.scan_within_product_helpers` + `noctus.dev.scan_service_line_recurrence` + `noctus.dev.scan_block_patterns` over the workspace; record baseline counts in `findings.md` so the post-build scan is calibratable.

**Phase 0 close:** commit locally (no push). Update §11 with what shipped vs what's deferred.

### Phase 1 — Backend foundation (config + migrations + OAuth wiring)

Serial — every later phase depends on these tables + OAuth.

- [ ] `app/config.py` — extend `ProductSettings` with the `youtube_*` fields (read at request time via `resolve_credential`; module-load slots default to None per `KB § PATTERNS/backend.md` FastAPI dep-factory rule (memory mirror `feedback_fastapi_dep_factory.md`).
- [ ] Migrations 002-006 via `noctus.dev.scaffold_migration` (one tool call per migration; substitute schema name + table name + columns).
- [ ] Apply migrations via Supabase MCP (`apply_migration`). Verify with `list_migrations` + `list_tables`. Commit DDL.
- [ ] `services/youtube_oauth.py` — token-persistence wrapper around `noctusai_lib.security.encrypted_tokens`.
- [ ] Mount `noctusai_lib.security.oauth.router(google_provider(...))` in `app/main.py`.
- [ ] `routers/settings_router.py` — implement all endpoints (§5.4); recipient CRUD against `notification_recipients` table.
- [ ] Tests: `tests/routers/test_settings_router.py` + `tests/services/test_youtube_oauth.py` + realdb conftest mirroring `core/tests/realdb/conftest.py` shape.

**Phase 1 verification:** `cd products/youtube-crawler/backend && pytest`; Supabase MCP `list_tables` for `youtube_crawler` schema confirms 6 tables; OAuth round-trip (consent → callback → token decryption) succeeds in fake mode (no real Google call).

### Phase 2 — Video listing + cache (parallelizable with Phase 3)

- [ ] `services/youtube_orchestrator.py` — `list_channel_videos`, `get_video_stats_batch`. Uses `noctusai_lib.integrations.youtube.make_youtube_client(use_fake=...)`. Cheap-path strategy (channels.list → playlistItems.list → batched videos.list).
- [ ] `services/youtube_orchestrator.py` — quota-tracker integration (decrement before each external call; refuse when exhausted).
- [ ] `routers/videos_router.py` — `/api/videos` + `/api/videos/{id}` + `/api/videos/sync`.
- [ ] Frontend: `pages/Videos.tsx` + `components/VideoCard.tsx` + `hooks/useVideos.ts`.
- [ ] Tests: `tests/services/test_youtube_orchestrator.py` (FakeYoutubeClient + FakeQuotaTracker); `tests/routers/test_videos_router.py`.

**Phase 2 verification:** unit tests green; realdb test asserts video_cache rows after a force-sync; quota tracker increments visible in Redis (or FakeQuota's history).

### Phase 3 — Upload pipeline + notifications (parallelizable with Phase 2)

- [ ] Wire `noctusai_lib.integrations.google_drive.make_drive_downloader` + `parse_drive_url` into `services/upload_pipeline.py` download handler (no product-side downloader file; seed integration handles metadata + streamed download).
- [ ] `services/notification_dispatcher.py` — recipient lookup → fan-out via `noctusai_lib.integrations.email.send_to_one` + `noctusai_lib.integrations.whatsapp.send_text` → write `notification_log`.
- [ ] `services/upload_pipeline.py` — per-step handlers (`download_drive`, `upload_youtube`, `notify`). Wired into `noctusai_lib.domain.jobs.worker.run_worker`.
- [ ] `routers/upload_router.py` — file-multipart + Drive-link entry; job-status polling.
- [ ] Frontend: `pages/Upload.tsx` + `UploadZone.tsx` + `RecipientSelector.tsx` + `hooks/useUpload.ts`.
- [ ] Tests: handler-by-handler unit tests with FakeStorage + FakeYoutubeClient + FakeWahaClient; pipeline integration test (end-to-end with all fakes).

**Phase 3 verification:** end-to-end fake upload completes (queued → published → notified) and writes 1 `notification_log` row per active recipient; real upload of a small private video succeeds against YouTube test account (manual gate).

### Phase 4 — Dashboard + final polish

- [ ] `routers/dashboard_router.py` — `/api/dashboard/stats` + `/top-videos` + `/recent-uploads`. Aggregates from `video_cache` + `upload_jobs`.
- [ ] Frontend: `pages/Dashboard.tsx` rewrite + `MetricCard.tsx` + `ViewsChart.tsx` (recharts) + `hooks/useDashboard.ts`.
- [ ] App shell: mount `<FakeModeBadge />` + nav update from §5.1.
- [ ] Tests: `tests/routers/test_dashboard_router.py`.
- [ ] Run absorption-search sextet on the project's workspace; triage any new N=2 / N≥3 findings (formalize / refactor / accept-with-rationale).
- [ ] Three-way sync of any methodology learnings (KB / CLAUDE.md / memory) — but ALL such edits land in noc proper, NOT the sibling workspace.

**Phase 4 verification:** `npx vite build` green; `pytest` green; manual sweep of all four pages; dashboard numbers match a YouTube Studio reference for the test channel.

### Project close

- [ ] Final scan rerun (sextet); `findings.md` synthesized into a curated knowledge artifact.
- [ ] If `findings.md` surfaced cross-cutting patterns: file follow-up project(s) against noc (the sibling workspace cannot edit noc).
- [ ] Archive the project: `noctus.dev.archive` moves `products/youtube-crawler/projects/youtube-crawler-build/` → `archive/projects/<today>/<NN>-<slug>/` (per `CLAUDE/projects.md` archive rule (memory mirror `feedback_archive_system.md`).
- [ ] Final commit on `youtube-crawler-build` branch + push. Orchestrator does the fast-forward to main (per CLAUDE.md "Branching-first orchestration" rule; memory mirror `feedback_orchestrator_role.md`).

---

## 7. Open questions (with recommendations)

1. **Where does WAHA actually run for this product?** The original draft proposes a root-level `docker-compose.yml` — clean-folder violation. Options: (a) `products/youtube-crawler/infra/docker-compose.yml` (product-local, references repo-root .env; **recommended**); (b) shared WAHA container across products (a "noc infra" project — premature for N=1 consumer; revisit at N=2). **Recommendation: (a)**.
2. **`gdown` vs Drive API for downloads.** `gdown` is brittle on permission-walled files. Drive API requires OAuth scope `drive.readonly`. Original draft picks `gdown` + `httpx` fallback — fine for v1. **Recommendation: ship `gdown`; capture in `findings.md` if any test file fails the cookie-gate; escalate to OAuth at N=3 failures or first user complaint.**
3. **Upload metadata: persistent or per-upload-only?** The metadata form (title / description / tags / privacy / category) — does it live only on `upload_jobs` (per-upload) or do we surface a "default metadata" in Settings? **Recommendation: per-upload only for v1; defaults are a v2 nicety.**
4. **`MetricCard` already in seed?** Verify before creating product-side. **Recommendation: 30 seconds of grep before Phase 4 starts; if shipping, consume; if not, build product-side and flag for absorb.**
5. **Tool call audit scope.** The `tool_call_audits` template was designed for LLM tool calls. Should we audit YouTube + Gmail SMTP + WAHA calls into the same table? **Recommendation: yes. The table shape covers any "external tool with cost & potential PII" — YouTube uploads carry video metadata that's user-content. Reuse the table, set `tool_name` = `youtube.upload` / `email.send` / `whatsapp.send_text`. Per `KB § PATTERNS/llm-tool-audit.md`.**
6. **Single-org for v1?** RLS uses `auth.jwt() ->> 'org_id'`. The hardening project assumed orgs are part of the JWT. Confirm v1 is single-org-per-tenant or supports multi-org. **Recommendation: single-org-per-tenant for v1 (matches every other product); RLS still uses `org_id` so multi-org is a flag-flip later.**

---

## 8. MCP exposure

Per `KB § PATTERNS/mcp-tool-conventions.md` + memory mirror `feedback_mcp_first.md` — the four headline capabilities expose as MCP tools alongside their HTTP routers. Living organism: register each in `mcp/noctusai/tools/youtube_crawler/` against the noc tree.

**HARD CONSTRAINT:** This step requires editing noc proper (the MCP toolkit is symlinked read-only into the sibling workspace). It happens AFTER project close, in noc, as a follow-up project: `noc-mcp-youtube-crawler-tools-expose`. Filed at Phase 4 close.

Tools to register (4 total):

```python
# noctus.youtube_crawler.upload_video(file_path, title, description?, tags?, privacy?, recipient_ids?)
# noctus.youtube_crawler.list_videos(force_sync?, search?, sort_by?, page?, page_size?)
# noctus.youtube_crawler.get_dashboard_stats(window_days=30)
# noctus.youtube_crawler.sync_channel(force=False)
```

3-segment dotted naming (memory mirror `feedback_mcp_first.md`); Pydantic schemas; lazy `NoctusContext`.

---

## 9. Risks

- **Seed-surface regression.** Eleven dependencies — if any was reverted post-archive, this project's Phase 1 audit catches it; mitigate by hard gating on Phase 0 verification + filing follow-up against noc instead of forking.
- **YouTube quota exhaustion during dev.** Default 10,000 units/day; one upload = 100; full channel re-sync = ~2 / 50 videos. **Mitigation:** quota tracker default-on; FakeYoutubeClient by default in dev (real client only when `YOUTUBE_CLIENT_ID` is set).
- **OAuth token leakage in logs.** Encrypted-tokens helper handles at-rest; the risk is in-flight (logs / error traces). **Mitigation:** never log raw tokens — log `oauth.token_received` events with hashed IDs only. Audit the seed `oauth.router` for log statements at Phase 0.
- **WAHA session loss.** WAHA loses its session if the container dies; recipient delivery silently fails. **Mitigation:** dispatch failures land in `notification_log.status = 'failed'` with `error_message`; settings page surfaces a "WhatsApp disconnected" badge from the FakeMode hook. (This product never auto-restarts WAHA — that's `whatsapp-google-scheduling`'s concern.)
- **Drive-download brittleness.** `gdown` cookie-gating breaks on shared-with-link files when a user account isn't signed in. **Mitigation:** open question §7 #2; failure path tests + clear error messages.
- ~~`gdrive_downloader.py` becoming a fork.~~ **RETIRED 2026-05-06** — seed integration shipped; no product-side fork to monitor.

---

## 10. Verification

**Per-phase checks (copy-paste):**

```bash
# Backend
cd products/youtube-crawler/backend && pytest

# Frontend
cd products/youtube-crawler/frontend && npx vite build

# Realdb
cd products/youtube-crawler/backend && pytest tests/realdb/

# Seed deps still compile (sanity)
cd seed/lib/backend && pytest

# MCP toolkit (only if PHASE-CLOSE touched noc-side MCP — workspace path forbids)
cd mcp/noctusai && pytest tests/

# Absorption-search sextet (run at Phase 0 baseline + Phase 4 close)
python mcp/noctusai/cli.py --scan-helpers
python mcp/noctusai/cli.py --scan-within-product-helpers
python mcp/noctusai/cli.py --scan-service-lines
python mcp/noctusai/cli.py --scan-block-patterns

# KB sync (only if any methodology change landed; workspace forbids)
bash scripts/verify-kb-sync.sh
```

**Manual integration testing:**
- OAuth: Settings → Connect YouTube → consent → callback writes encrypted refresh token → channel name appears.
- Upload: drag a small mp4 → fills metadata → recipients pre-selected → submit → progress goes 0→100 → video appears in Videos page within ~30s.
- Drive: paste a Drive shared link → backend downloads to tmp/ → uploads to YouTube → notifies.
- Notification: verify 1 email arrives + 1 WhatsApp message per active recipient; `notification_log` rows match.
- Dashboard: numbers match YouTube Studio for test channel within ±10% (caching introduces drift).

---

## 11. Change log

- **2026-05-04** — Original draft authored by out-of-environment agent; landed at repo root as `PLAN.md`.
- **2026-05-05** — Refined against noc methodology (this file). Eleven service / infra / migration items mapped to seed surfaces shipped by `seed-hardening-from-youtube-crawler` (archive #10). Net: -10 product files, ~-400 LOC. Filed `gdrive_downloader` as N=1 seed-lift candidate. Filed `noc-mcp-youtube-crawler-tools-expose` as post-close follow-up against noc. Confirmed no symlinked-surface edits proposed (template-workspace rule honored).
- **2026-05-06** — `noctusai_lib.integrations.google_drive` lifted into seed (Protocol+Fake+Real+factory + `parse_drive_url` mapper + 30 tests; 974/974 seed-lib backend tests green at lift time). User authorization: "absorb this google_drive integration. It's N=1 today, but we'll spread it throughout soon." Net: another -1 product file, no consumer-side fork. PLAN.md citations of "per memory" replaced with canonical KB / CLAUDE.md pointers (§3a is documented in CLAUDE.md "Replication-to-seed symmetry" rule + CLAUDE/projects.md workflow + KB § GUIDES/seed-first-design.md + KB § PATTERNS/project-execution.md + templates/PROJECT-TEMPLATE.md — three-way sync intact).

---

## 12. Cleanup (on project close)

- [ ] `noctus.dev.archive` the project folder (per `CLAUDE/projects.md` archive rule (memory mirror `feedback_archive_system.md`).
- [ ] Delete this `PLAN.md` from repo root if it still exists there (relocation should have moved it during Phase 0; this is the safety check).
- [ ] Confirm `findings.md` was synthesized into the project's curated knowledge artifact + relevant cross-cutting findings filed as follow-ups against noc.
- [ ] Final commit + push (orchestrator does the fast-forward to main).
