# Phase 5 — E2E Real Estate Automation Checklist

> **Purpose**: Track every deliverable needed for end-to-end YouTube upload
> automation. Another agent can pick this up and resume from the last
> checked item.
>
> Legend: `[x]` done · `[/]` in progress · `[ ]` not started

---

## 5a: Infrastructure Bootstrap

- [x] Git initial commit (all existing code) — `17b09b7`
- [x] Create Codex branch — `codex-5.5/sqlite-dev-vista-cf`
- [x] Defer Supabase migration application during development
- [x] Add local SQLite dev backend (`DATABASE_BACKEND=sqlite`)
- [x] Apply local SQLite schema mirror for migrations 001–006 (`tmp/dev.sqlite3`)

---

## 5b: Product Code Field

### Backend
- [x] Create `migrations/006_product_code.sql`
- [x] Modify `schemas/upload.py` — add `product_code` to `UploadMetadata`
- [x] Modify `schemas/upload.py` — add `product_code` to `UploadJobOut`
- [x] Modify `services/upload_service.py` — pass `product_code` through `_insert_job()`
- [x] Modify `routers/upload_router.py` — include `product_code` in `_row_to_out()`

### Frontend
- [x] Modify `hooks/useUpload.ts` — add `product_code` to `UploadMetadata` type
- [x] Modify `hooks/useUpload.ts` — add `product_code` to `UploadJob` type
- [x] Modify `pages/Upload.tsx` — add "Código do Imóvel" input to `MetadataFields`
- [x] Modify `pages/Upload.tsx` — pass `product_code` through `formToMetadata()`

---

## 5c: Google Drive Folder Support

### Backend
- [x] Modify `services/gdrive_service.py` — add `is_folder_url()`
- [x] Modify `services/gdrive_service.py` — add `parse_folder_id()`
- [x] Modify `services/gdrive_service.py` — add `classify_video_format()` (filename + ffprobe)
- [x] Modify `services/gdrive_service.py` — add `download_folder_contents()`
- [x] Modify `services/gdrive_service.py` — add `pick_youtube_video()` orchestrator
- [x] Modify `services/upload_service.py` — folder-aware `_materialise_source()` (call `is_folder_url` → `pick_youtube_video`)
- [x] Modify `services/upload_service.py` — folder-aware `queue_drive_upload()` (accepts folder URLs)

### Infrastructure
- [x] Modify `Dockerfile` — add `ffmpeg` (provides `ffprobe`) to backend container

---

## 5d: CRM Service

### Backend
- [x] Create `services/crm_service.py` — `CRMService`, `PropertyData`, `build_youtube_metadata()`
- [x] Modify `config.py` — add `crm_base_url`, `crm_api_key`
- [x] Modify `.env` — add `CRM_BASE_URL=` and `CRM_API_KEY=` placeholders
- [x] CRM wired into WhatsApp intake (auto-populates title/description from CRM when product_code is sent)
- [x] Replace generic CRM placeholder with Vista `/imoveis/detalhes` integration from local KB
- [x] Copy Vista credentials into local ignored `.env` (`VISTA_*` + `CRM_*`)

---

## 5e: WhatsApp Inbound

### Backend
- [x] Create `schemas/whatsapp.py` — `WAHAMessagePayload`, `WAHAMessage`, `UploadCommand`, `PendingUpload`
- [x] Create `services/whatsapp_intake_service.py` — conversation state machine
- [x] Create `routers/whatsapp_router.py` — webhook endpoint
- [x] Modify `main.py` — register `whatsapp_router`
- [x] Modify `config.py` — add `whatsapp_authorized_numbers` (default: `+5511974693365`)

---

## 5f: Cloudflare Tunnel + CORS

### Backend
- [x] Modify `config.py` — add `tunnel_hostname` + `model_post_init` dynamic CORS
- [x] Modify `.env` — add `TUNNEL_HOSTNAME=` placeholder
- [x] CORS wired: `model_post_init` appends tunnel_hostname to `cors_origins` automatically

---

## 5g: Frontend Polish

- [x] Modify `pages/Upload.tsx` — update Drive tab helper text ("arquivo ou pasta")
- [x] Modify `pages/Upload.tsx` — update Drive tab placeholder (folder URL example)
- [x] Modify `pages/Upload.tsx` — show product_code badge in HistoryRow
- [x] Modify `pages/Dashboard.tsx` — show `product_code` badge in recent uploads rows
- [x] Modify `hooks/useDashboard.ts` — add `product_code` to `RecentUpload` type

---

## 5h: Verification

- [x] Python syntax check — all new/modified `.py` files compile cleanly
- [x] TypeScript type check — no new errors in modified files (4 pre-existing in App.tsx/scroll-area)
- [x] Run `docker compose build` — backend/frontend images build successfully
- [x] PLAN.md reflects final state (Phase 5 added, ~370 lines)
- [ ] Git commit Codex SQLite/Vista/CF continuation changes

---

## 5i: Codex Continuation

- [x] Add SQLite Supabase-like adapter for local dev
- [x] Add SQLite schema application script
- [x] Wire Docker app startup to apply SQLite schema when `DATABASE_BACKEND=sqlite`
- [x] Update `.env.example` + compose env for SQLite, Vista, and tunnel settings
- [x] Cloudflare tunnel — Quick Tunnel for dev (canonical seed pattern `KB § PATTERNS/containerization.md § 5b`, with `--protocol http2` pin) + Named Tunnel for prod (`3b8091a`, `bot.noctusai.com` via cloudflared systemd + DNS CNAME). Cloudflare MCP deferred — not needed; `scripts/deploy/03-setup-tunnel.sh` calls the CF API directly.
- [x] Frontend production build passes; existing 582 KB Vite chunk warning remains
- [/] Backend pytest attempted with seed PYTHONPATH; blocked by missing local Google/httpx dependencies outside Docker

## 5j: Live Integration Readiness

- [x] Add configurable `FRONTEND_BASE_URL` for YouTube OAuth callback redirect
- [x] Add Vista status smoke endpoint: `GET /api/settings/vista/status?product_code=ONE5555`
- [x] Add Gmail SMTP test endpoint: `POST /api/settings/email/test`
- [x] Add WAHA status endpoint: `GET /api/settings/waha/status`
- [x] Add WAHA test-send endpoint: `POST /api/settings/waha/test`
- [x] Add optional WAHA webhook HMAC validation via `WAHA_WEBHOOK_HMAC_SECRET`
- [x] Standardize WAHA URL settings (`WAHA_BASE_URL`, `WAHA_DASHBOARD_URL`, `WAHA_WEBHOOK_URL`)
- [x] Use native WAHA ARM image on Apple Silicon instead of amd64 emulation
- [x] Document WAHA response/webhook formats in `backend/WAHA_RESPONSE_FORMATS.md`
- [x] Live SMTP smoke test passed against configured Gmail account
- [x] Live Vista smoke test passed with `ONE10121`
- [x] Docker CLI build/start verification — compose stack healthy with tunnel profile
- [x] Public tunnel health check passed: `/api/health`
- [x] Public tunnel Vista check passed: `/api/settings/vista/status?product_code=ONE10121`
- [x] Public tunnel SMTP check passed: `POST /api/settings/email/test`
- [/] WAHA session starts via API, but remains `STARTING` until WhatsApp QR pairing is completed
- [x] Add Cloudflare Quick Tunnel runbook: `CF_TUNNEL.md`
- [x] Add tunnel refresh script: `./refresh_cf_tunnel.sh`
- [x] Tunnel refresh updates `.env` `WAHA_WEBHOOK_URL` and best-effort syncs WAHA session webhook config

---

## E2E Live Testing (manual, via CF tunnel)

- [x] `docker compose --profile tunnel up -d` — stack comes up healthy
- [/] Copy tunnel URL → update `.env` YOUTUBE_REDIRECT_URI done by script; GCP OAuth registration remains manual
- [ ] OAuth: Settings → Connect YouTube → channel info appears
- [ ] Platform upload (single file): Upload page → file + ONE5555 → private → submit → YT upload OK
- [ ] Platform upload (folder link): Upload page → folder URL + ONE1234 → picks YT video, skips REELS
- [ ] WhatsApp command: Send `ONE5555 https://drive.google.com/...` from +5511974693365
  - [ ] Bot responds with CRM data + confirmation prompt
  - [ ] Reply "sim" → upload starts
  - [ ] Completion notification arrives
- [ ] Unauthorized sender → silent drop
- [ ] Dashboard → product code visible in recent uploads
- [ ] Notifications → email + WhatsApp delivery after upload

---

## Phase 6 — Conversation buffer + robustness + post-upload tail

Built on top of Phase 5. Architecture shifts: every WhatsApp inbound
flows through a Redis-backed conversation buffer (seed primitive); a
single FIFO queue gates every upload; the post-upload tail polls YT's
processing pipeline before announcing "publicado".

### 6a — Seed buffer + worker

- [x] `app/services/conversation_module.py` — consumes
  `noctusai_lib.domain.chatbot.ConversationBufferService` +
  `ConversationWorker`. Wired via `app/lifespan.py` startup hook.
- [x] Webhook `app/routers/whatsapp_router.py` calls
  `buffer.buffer_inbound(...)` instead of running the chatbot inline.
  Multi-message intents ("ONE7360" + drive URL in two messages) get
  joined within a `MESSAGE_DEBOUNCE_SECONDS` window (default 8s).
- [x] `_dispatch_conversation` routes by intake state: non-idle →
  state-machine; idle + regex match → fast-path; idle + regex miss →
  LLM fallback. Single source of truth for path selection.
- [x] `app/services/whatsapp_outbound.py` — `split_for_whatsapp` +
  `send_paragraphs` for `\n\n`-split outbound messages.
- [x] `MEMORY_PREFIX` unified between chatbot + seed buffer so both
  read/write the same Redis list.

### 6b — Slice 3 robustness

- [x] **A** Multi-video disambiguation. `list_youtube_candidates`
  returns ALL horizontal videos; `awaiting_video_choice` state +
  `_handle_video_choice` lets the user pick `1`/`2`/.../`todos`/
  `cancelar`.
- [x] **B** Bounded retry on transient YT errors. 5xx/429/network →
  retry; 4xx auth/perm → fail fast; `quotaExceeded` →
  `YouTubeQuotaExceededError` with a clear message.
- [x] **C** Global single-flight upload queue
  (`app/services/upload_queue.py`). Position pings via the progress
  poller. `UPLOAD_MAX_CONCURRENT` config flips to bounded parallel.
- [x] **D-backend** `POST /api/videos/upload/{job_id}/retry` re-queues
  failed jobs.
- [x] **D-frontend** Dashboard "🔄 Tentar de novo" button on failed
  rows.

### 6c — Future-improvements

- [x] **F1** Drive download cache. `app/services/download_cache.py`,
  TTL configurable, orphan-sweep at lifespan startup.
- [x] **F2** Bounded parallel queue. `UPLOAD_MAX_CONCURRENT` config.
- [x] **F3** Mid-upload resume on chunk retry. Same `request` object
  across retries so `resumable_uri` survives transient failures.
- [x] **F4** Upload-all-candidates flow. "todos" reply spawns N jobs
  with " · Parte N/M" titles.
- [x] **F5** Retry re-enqueues failed job at back of queue.
- [x] **F6** `cancel_upload` LLM tool — already existed; enhanced to
  clean up `local_video_path` + all `candidate_videos` files on
  disk.
- [x] **F7** Oversized-candidate user-facing message.
- [x] **F8** Queue + status pings cross-reference in the progress
  poller.

### 6d — Post-upload tail (slice 4)

- [x] **S4-1** YT processing-status polling.
  `youtube_service.get_processing_status` + `upload_service`
  `_wait_for_yt_processing` (10min cap).
- [x] **S4-2** Thumbnail upload from Vista property photo.
  `youtube_service.set_thumbnail` + migration `008_thumbnail_url.sql`.
- [x] **S4-3** Notification dispatch enriched (listing URL + product
  code in email body).
- [x] **S4-4** Rich post-upload WhatsApp message via paragraph-split
  (listing URL, property summary, agent `wa.me` CTA).
- [x] **S4-5** Dashboard YT URL inline + "⏳ processando no YouTube"
  pill for `status=processing`.

### 6e — Caveat resolutions

- [x] **C1** Robust Vista photo extraction — prefers `FotoGrande` →
  `FotoMedia` → `Foto` → `FotoPequena`, walks featured entries until
  a valid URL is found.
- [x] **C2** Migration 008 documented in `scripts/deploy/DEPLOY.md`
  with the full per-migration apply order.
- [x] **C3** Per-phone active-job counter so the "todos" parallel
  spawn doesn't have any task prematurely clearing state; "X uploads
  em andamento" reply reflects actual concurrent count.

### 6f — Polish

- [x] Cleanup-on-success-only — failed jobs keep their staged file on
  disk for `retry` button to reuse without re-downloading.
- [x] Queue moved into `run_upload_job` so every entry point
  (WhatsApp / browser / dashboard retry) queues uniformly.
- [x] System prompt updated — LLM knows the buffer accumulates
  fragmented messages, the multi-video menu shape, queue + processing
  states, and how to recognize natural-language cancel intents.
