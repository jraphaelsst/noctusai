# AGENT.md · current state of the NoctusAI chatbot/agent system

> **Scope:** what the agent CAN do today, where each piece lives, and
> which sub-systems ("branches") are stable enough to spec out in
> detail next. This is a state doc, not a plan. The companion
> `PLAN.md` carries forward-looking work; `findings.md` carries the
> per-phase learning log.
>
> **Last refresh:** 2026-05-12 — at the close of the
> `feat/platform-chat-agent` branch work.
>
> **How to use this doc:**
> 1. Skim §1 to know what shipped.
> 2. Read §2 to map the moving pieces.
> 3. Pick a branch from §3 to spec next. Each branch lists its
>    current behavior, files, gaps, and dependencies on other
>    branches — enough to scope a focused project.

---

## 1 · What the agent is, today

A surface-agnostic conversational agent built on OpenAI tool-calling,
reachable from two channels:

- **WhatsApp** — via WAHA inbound webhook → backend → WAHA outbound.
- **Platform UI** — at `/chat` on the React frontend, via the
  `/api/chat/*` HTTP surface. Currently unauthenticated by product
  direction.

Both surfaces share the same brain (`ChatbotService`) and the same
intake (`WhatsAppIntakeService` — historically named, now serves
both). One inbound, one canonical session id, one Redis memory
list, one durable audit row per turn.

**Capabilities active in production today:**

| Capability | How it's exposed | Validated against |
|------------|------------------|-------------------|
| Text chat (general) | natural reply, no tool call | live OpenAI |
| Text chat (capability questions) | conversational, scoped | live OpenAI |
| Voice note → transcript | inbound media auto-resolved to `[Audio transcrito] ...` | live Whisper |
| Photo → description | inbound media auto-resolved to `[Imagem] ...` | live gpt-4o vision |
| Video → scene + audio | parallel ffmpeg keyframes → vision + ffmpeg audio → Whisper | live |
| PDF (text-layer) → summary | PyMuPDF `get_text` + LLM summarize | live |
| PDF (scanned) → summary | PyMuPDF rasterize + vision read | live (CNH-shaped) |
| Other docs | acknowledged with filename, summarize via vision when possible | partial |
| YouTube upload trigger | tool call → CRM lookup → confirm → background upload | needs YouTube OAuth |
| Vista CRM lookup | tool call `lookup_property(ONExxxx)` | live `oneconsu-rest.vistahost.com.br` |
| Polite "you're not on the whitelist" reply | WhatsApp inbound from unknown senders | live |
| Multi-channel memory recall | same Redis key resolves regardless of LID vs phone form | live |

---

## 2 · Architecture, in two diagrams

### 2.1 Container topology

```
  Browser / phone                WhatsApp user
        │                              │
        ↓                              ↓
  ┌─────────────────────────────────────────┐
  │      Cloudflare Quick Tunnel URL        │
  │   fixed-actively-levy-jake.tryCF.com    │
  └────────────────┬────────────────────────┘
                   │
                   ↓
           ┌───────────────┐
           │   proxy:8090  │  nginx, path-routes:
           │  (docker svc) │    /api/*   → app
           └─┬─────┬─────┬─┘    /waha/*  → waha
             │     │     │       /*       → frontend
             ↓     ↓     ↓
   ┌──────────┐ ┌──────────┐ ┌──────────┐
   │ app:8010 │ │waha:3000 │ │frontend  │
   │ FastAPI  │ │  WAHA    │ │  :8150   │
   └────┬─────┘ └────┬─────┘ │ nginx +  │
        │            │       │ Vite SPA │
        │            │       └──────────┘
        │            │
        │   (WhatsApp webhook in)
        │            │
        ↓            ↓
  ┌──────────┐ ┌──────────┐
  │redis:6379│ │sqlite or │
  │  (Redis) │ │ supabase │
  └──────────┘ └──────────┘
```

### 2.2 Inbound turn — one message, end to end

```
WhatsApp message  /  Platform chat POST
        │
        ↓
   webhook OR /api/chat/message handler
        │
        ├─ A. SETNX provider_message_id (Redis dedup pre-filter)
        │     ↳ duplicate? → 200, exit early
        │
        ├─ B. parse sender + body + (optional) media descriptor
        │
        ├─ C. is_authorized(sender)?   [WhatsApp only]
        │     ↳ no  → polite-deny reply (throttled 24h), exit
        │     ↳ yes → continue
        │
        ├─ D. media resolution (if has_media):
        │     MediaService.resolve_inbound(url, mimetype, filename)
        │        ├─ audio  → Whisper            → "[Audio transcrito] ..."
        │        ├─ image  → vision             → "[Imagem] ..."
        │        ├─ video  → ffmpeg-frames + Whisper-audio
        │        │            (parallel)        → "[Video — cena] ...\n
        │        │                                 [Video — audio transcrito] ..."
        │        ├─ pdf    → text-layer OR rasterize+vision
        │        │            (with refusal-retry) → "[Documento — resumo] ..."
        │        └─ other  → "[Anexo recebido: filename]"
        │     enriched text → merged with caption text
        │
        ├─ E. message_store.record(inbound, structured_payload)
        │     ↳ UNIQUE(provider_message_id) tripped? → 200, exit
        │
        ├─ F. canonical_session_id(sender) → phone-form when LID cached
        │     ↳ migrate LID-keyed memory to phone key on first capture
        │
        ├─ G. ChatbotService(session_id).reply(message_body)
        │     - load Redis memory (last 40 items)
        │     - OpenAI loop with tools (max 5 iters)
        │     - tools call back into IntakeService
        │     - append inbound + outbound to memory
        │     - returns reply text
        │
        ├─ H. intake._reply(sender, text)  [WhatsApp]   OR
        │     return ChatReply JSON       [Platform chat]
        │     - WAHA send-text
        │     - capture LID from response into Redis cache
        │     - message_store.record(outbound)
        │
        └─ I. 200 OK
```

---

## 3 · Branches of the agent

Each subsection below is a candidate for a focused spec project. They
share the intake/chatbot seam but are otherwise independent.

### 3.1 Conversation orchestration (the "brain")

The OpenAI tool-calling loop. Surface-agnostic.

**Files:**
- `products/youtube-crawler/backend/app/services/chatbot_service.py`
- Tests: `tests/services/test_chatbot_service.py` (13 cases, all green)

**Current behavior:**
- Single class `ChatbotService` keyed on `session_id`.
- 6 tools registered (see §4 for the inventory).
- Iteration cap: 5 turns of tool dispatch before fallback.
- Memory: Redis list under `whatsapp:chatbot:{stripped_session_id}`,
  max 40 items, 60-minute TTL.
- System prompt: classifies inbound into 3 paths (upload / other
  NoctusAI capabilities / general chat) and dispatches tools only
  for the upload path. Explicit anti-refusal directives for media
  inbound.
- Model: `gpt-4o-mini` for chat, `gpt-4o` for vision, `gpt-4o-mini-transcribe`
  for audio. All overridable via env.
- Extra context injection (`extra_context` kwarg) — used by the
  platform chat router to tell the model about an attached file's
  `file_id` without forcing it into a tool call.

**Known gaps / spec candidates:**
- 🟡 The system prompt is product-specific (real-estate framing).
  Lifting to noc requires extracting it into a constructor arg.
- 🟡 No structured-output tools yet (e.g. `extract_property_data(json
  schema)`); every output is free text or a tool side-effect.
- 🟡 No streaming. UI shows a "typing..." spinner while the full
  reply is generated. Could go SSE / chunked.
- 🟡 No conversation summarization when memory hits the 40-item cap;
  oldest entries just get evicted.
- 🟡 No prompt-cache exploitation. The system prompt is large + stable
  but isn't structured for OpenAI's automatic-cache hit-rate.

**Dependencies:** Redis (3.3), Intake's tool surface (3.6),
canonical_session_id (3.4).

---

### 3.2 Multimodal intake (the "senses")

Turns inbound media (audio/image/video/PDF/other) into enriched
text the chatbot can reason about.

**Files:**
- `products/youtube-crawler/backend/app/services/media_service.py`
  (~900 lines, single class + module helpers)

**Current behavior:**
- `resolve_inbound(url, mimetype, filename, fallback_text)` —
  downloads + routes by mimetype family.
- `_rewrite_waha_url(url)` — swaps WAHA's external-facing
  `localhost:3000` host onto the docker-internal `http://waha:3000`
  before fetching media bytes.
- Audio: Whisper via `client.audio.transcriptions.create`, lang=`pt`.
- Image: vision via `chat.completions.create` with `image_url` content
  block + base64 data URL.
- Video: TWO parallel pipelines:
  - Scene: ffmpeg samples 4 keyframes (10/30/60/90% interior) →
    `_call_vision_multi` sends all 4 in one prompt.
  - Audio: ffmpeg extracts opus 32kbps → Whisper.
- PDF: PyMuPDF `page.get_text()` first; falls back to `_rasterize_pdf_pages`
  (1024px max width, 3 pages) → vision read. Refusal-retry on both
  passes.
- Other documents (doc/docx/xls/xlsx/txt/csv): acknowledged by
  filename + size, no extraction in v1.

**Known gaps / spec candidates:**
- 🟡 Vision multi-image cap is 6 frames — fine for short videos, lossy
  for long-form. Need spec for chunked-video summarization.
- 🟡 No audio language auto-detect — hardcoded `language="pt"`.
- 🟡 Document extraction stops at PDFs. Office formats (docx, xlsx)
  could be parsed via PyMuPDF or via libreoffice→pdf→same pipeline.
- 🟡 No max-size limits — a 4GB video would attempt to ffmpeg + send
  through OpenAI. Whisper has a 25MB upload cap (current code
  pre-compresses to opus), vision payload via data-URL has its own
  ceiling.
- 🟡 No image-OCR-only mode (e.g. user sends a photo of a receipt and
  wants the text extracted verbatim, not described). Matches noc
  ERP's `matricula_service` `_OCR_PROMPT`.
- 🟡 Refusal-detection markers are pt-BR + a handful of English
  phrases. Will miss non-pt-BR / non-English refusals.

**Dependencies:** OpenAI Whisper + vision, ffmpeg (in image), PyMuPDF
+ pdfminer.six (in requirements).

---

### 3.3 Persistence (memory + audit log)

Two parallel persistence layers. Redis for hot-path recall, SQL for
durable audit + idempotency.

**Files:**
- Redis side: `chatbot_service.append_memory()` / `memory_key_for()`
- SQL side: `app/services/message_store.py` +
  `migrations/007_conversation_messages.sql` +
  `apply_sqlite_migrations.py` (SQLite mirror)

**Current behavior:**
- Redis list `whatsapp:chatbot:{stripped_session_id}` — 40 items, 60min TTL.
  Read by the chatbot to build OpenAI message list. Written by every
  outbound boundary (chatbot reply, intake `_reply`, settings/waha/test).
- `youtube_crawler.conversation_messages` — one row per inbound +
  outbound. `UNIQUE(provider_message_id)` drives WAHA dedup.
  `structured_payload` (JSONB) carries the media descriptor + tool
  call results for forensics.
- `MessageStore.record()` raises `DuplicateMessage` on UNIQUE
  violation; the webhook handler catches it and drops the second of
  WAHA's `message + message.any` deliveries.
- Backend-agnostic duplicate detection: sniff the error message first
  (cheap), fall back to a SELECT existence check (durable).

**Known gaps / spec candidates:**
- 🟡 The Redis memory list is NOT recovered from the DB on Redis
  flush. A `MessageStore.list_for_session()` method exists for that
  recovery; nothing calls it yet.
- 🟡 The DB row stores `body` as a single column. Multi-modal
  resolutions stuff the enriched text in there; the original media
  URL lives in `structured_payload`. Querying "all videos the user
  sent" works but is ugly.
- 🟡 No retention policy. Will grow unbounded — needs an archive job
  or TTL on the row level.
- 🟡 RLS policy assumes `auth.jwt()->>'org_id'` but the webhook +
  chat endpoints run service-role. Read access from the UI side
  needs the org_id-from-JWT path which doesn't apply for
  unauthenticated chat. Spec needed for the "transcript viewer" UI.

**Dependencies:** Redis, SQLite (dev) / Supabase (prod).

---

### 3.4 Identity (LID ↔ phone canonical session)

WhatsApp's `@lid` opaque identifier vs. phone-form whitelist.

**Files:**
- `app/services/whatsapp_intake_service.py` — `is_authorized()`,
  `canonical_session_id()`, `remember_lid_for_phone()`, the lid_to_phone
  Redis cache.

**Current behavior:**
- `is_authorized(sender)` resolves in three tiers:
  1. Raw LID literal in the whitelist (`"33613018058989@lid"` listed
     explicitly).
  2. Phone-form match after stripping `@c.us` / `@s.whatsapp.net` and
     prefixing `+`.
  3. Redis-backed lid→phone cache, populated opportunistically on
     every successful outbound (the WAHA send-text response carries
     `_data.id.remote` which is the LID).
- `canonical_session_id(raw_sender)` returns the phone form when the
  cache knows it, falls back to the LID otherwise. So one
  conversation == one Redis memory key.
- `remember_lid_for_phone()` migrates any memory accumulated under
  the LID key onto the phone key on first capture. This prevents
  Case-B (user contacts FIRST, before any outbound) from splitting
  the conversation across two keys after the cache populates.
- Polite "you're not on the whitelist" reply for unauthorized
  senders, throttled to once per 24h via a Redis `whatsapp:denied:*`
  marker so strangers don't get a denial loop.

**Known gaps / spec candidates:**
- 🟡 The whitelist is a comma-separated env var
  (`WHATSAPP_AUTHORIZED_NUMBERS=+5511974693365`). No persistent
  per-org users table. Multi-tenant rollout will need
  `linked_identity` column on users + the
  `AuthorizationService.authorized_user_for_chat_id` pattern from
  `whatsapp-google-scheduling`.
- 🟡 No pending-LID parking. Unknown LIDs get denied + a Redis
  marker. No surface for an operator to later approve them.
- 🟡 Group chats are not supported. LID resolution assumes 1:1 DM.

**Dependencies:** Redis (3.3 partial — separate key namespace),
SETNX'd WAHA dedup (3.7).

---

### 3.5 Surface adapters

Two routers expose the same intake/chatbot to the two channels.

**Files:**
- `app/routers/whatsapp_router.py` — WAHA inbound webhook + the
  unauthorized-reply path.
- `app/routers/chat_router.py` — platform HTTP chat (multipart
  text + file).

**Current behavior:**
- WhatsApp router: HMAC-verifies if `WAHA_WEBHOOK_HMAC_SECRET` is
  set; ignores `from_me` / non-message events; resolves media;
  records inbound; canonicalizes session; runs chatbot; sends
  reply via intake.
- Chat router endpoints:
  - `POST /api/chat/message` — multipart (text + optional file).
    Stages video files for the upload pipeline; routes other
    attachments through media_service for in-place resolution.
    Returns `{ session_id, reply, file_id, pending }`.
  - `POST /api/chat/upload-file` — stage-only (file_id returned).
  - `GET /api/chat/history/{session_id}` — recent memory items.
  - `POST /api/chat/reset/{session_id}` — clears memory + pending.
- Frontend `Chat.tsx` + `useChat.ts` consume the chat endpoints
  with same-origin URLs via `apiUrl()`.

**Known gaps / spec candidates:**
- 🟡 The chat router uses the local-dev org_id by default; needs a
  per-tenant key when real auth lands.
- 🟡 No SSE/streaming for the chat reply — the UI waits for the
  full response.
- 🟡 No image-attach distinct from video-attach in the chat UI.
  Right now the file input is `accept="video/*"`. Spec needed for
  the multi-attachment UX.
- 🟡 No "conversation list" page — the UI starts fresh on every
  load OR continues a localStorage-cached session. No way to see
  past sessions.

**Dependencies:** Chatbot (3.1), Media (3.2), Persistence (3.3),
Identity (3.4), Tool surface (3.6).

---

### 3.6 Tool surface (what the agent can DO)

The 6 tools registered on `ChatbotService`. Each delegates to
`WhatsAppIntakeService`.

**Files:** `chatbot_service._build_tools()`,
`whatsapp_intake_service.{lookup_property, prepare_upload_request,
prepare_upload_from_file_request, get_pending_upload,
confirm_pending_upload, cancel_pending_upload}`.

**Inventory:**

| Tool | Args | Effect |
|------|------|--------|
| `lookup_property` | `product_code: str` | Hits Vista `/imoveis/detalhes`; returns title/address/price/area/etc. |
| `prepare_upload_request` | `product_code, drive_url, manual_title?, privacy_status?` | Validates URL + code; persists a `PendingUpload` in Redis. CRM-fills title/desc. |
| `prepare_upload_from_file` | `product_code, file_id, manual_title?, privacy_status?` | Same as above but for pre-staged browser uploads (file_id resolved against the file registry). |
| `get_pending_upload` | — | Returns the user's current pending upload state. |
| `confirm_upload` | — | Locks the pending state, queues the upload job, fires the YouTube publish + notifications. |
| `cancel_upload` | — | Clears the pending state. |

**Pending state machine:** `idle → awaiting_confirmation →
processing → cleared` (with `awaiting_manual_title` as a side branch
when the CRM lookup fails).

**Known gaps / spec candidates:**
- 🟡 Tools are real-estate-shaped. Any noc product adopting the
  agent will replace this surface (mailing → "schedule send", daily-life
  → "create task", therapy → "log session", etc.). The
  ChatbotIntake protocol shape is the seam.
- 🟡 No `search_videos`, `get_upload_status`, `list_recent_uploads`
  tools — the agent can't talk about what's ALREADY been published.
- 🟡 No structured-output tool for "extract the property fields from
  this PDF" — the document summarization comes back as prose.
- 🟡 No per-user tool-permission gating. Every authorized number has
  access to every tool.

**Dependencies:** Vista CRM client (`crm_service.py`),
UploadService + YouTubeService for the upload tail.

---

### 3.7 Dedup oracle (WAHA's noisy event delivery)

Two-tier idempotency for inbound WhatsApp messages.

**Files:**
- Redis pre-filter: `whatsapp_router.py` (SETNX on
  `whatsapp:msg_seen:{provider_message_id}` with 5-minute TTL).
- DB durable: `MessageStore.record()` raises `DuplicateMessage` on
  the `UNIQUE(provider_message_id)` constraint.

**Current behavior:**
- WAHA subscribes the webhook to BOTH `message` AND `message.any`
  events. Both deliver the same `provider_message_id` within
  milliseconds.
- The SETNX pre-filter catches the second-arriving event in ~25ms
  without touching OpenAI. Cost: $0.001 saved per turn, latency
  halved.
- The DB UNIQUE catches anything that slipped past SETNX (5-minute
  TTL expiry, restart, etc.) — the second INSERT raises, the
  handler catches `DuplicateMessage`, returns 200.

**Known gaps / spec candidates:**
- 🟡 The Redis dedup key isn't namespaced per-session. Cross-session
  collisions are theoretically possible if WAHA issues the same
  `provider_message_id` for two different conversations — unlikely
  but undocumented.
- 🟡 No dedup on OUTBOUND. If the bot somehow sends two messages
  with the same id (it won't today, but defense-in-depth), we
  silently store both because outbound `provider_message_id`
  collisions also raise `DuplicateMessage` (we catch it as "best
  effort dedup" but the second send already went out via WAHA).

**Dependencies:** Redis, SQLite/Supabase, IntakeService.

---

### 3.8 Single-URL proxy + tunnel

Path-routed nginx in front of the whole stack so one Cloudflare
quick-tunnel URL serves backend + frontend + WAHA.

**Files:**
- `proxy/nginx.conf`
- `docker-compose.yml` (proxy service + tunnel service)
- `refresh_cf_tunnel.sh`
- `products/youtube-crawler/frontend/nginx/default.conf` (SPA
  fallback for the frontend's own nginx)
- `products/youtube-crawler/frontend/src/lib/apiBase.ts` (runtime-
  smart URL resolution)

**Current behavior:**
- `proxy` service (nginx:alpine) listens on `:8090`.
  - `/api/*` → `app:8010`
  - `/openapi.json` + `/redoc` → `app:8010`
  - `/waha/*` → `waha:3000`
  - `/*` → `frontend:8150`
- `tunnel` (cloudflared) tunnels `http://proxy:8090` with
  `--protocol http2` pinned.
- `refresh_cf_tunnel.sh` syncs `TUNNEL_HOSTNAME`,
  `YOUTUBE_REDIRECT_URI`, `WAHA_WEBHOOK_URL`, `FRONTEND_BASE_URL`
  to the new URL in one shot. Updates the WAHA session config too.
- Frontend `apiBase()` runtime helper picks behavior based on
  `window.location.port`:
  - port 8150 → use `http://localhost:8010` (direct frontend dev)
  - anything else → same-origin (proxy / tunnel / prod)

**Known gaps / spec candidates:**
- 🟡 Quick Tunnel URL rotates on every recreate. Production needs a
  named tunnel + a stable hostname.
- 🟡 No rate-limiting at the proxy layer.
- 🟡 No header sanitization — the proxy forwards anything WAHA sends.
- 🟡 No body buffering — `proxy_request_buffering off` is set so
  videos stream through, which means slow uploads tie up worker
  connections.
- 🟡 The frontend nginx serves `dist/` content directly. No
  cache-busting for `index.html` — relies on Vite's hashed asset
  filenames.

**Dependencies:** Docker network, cloudflared.

---

### 3.9 Google integrations (Calendar + Maps + Drive-aware)

Ported from `whatsapp-google-scheduling` to give the agent agenda +
travel-time + Drive-URL inspection capabilities.

**Files:**
- `app/services/calendar/` — 6 files (types, _google_api, mappers,
  google_adapter [service-account], oauth_adapter [user-consent],
  fake_adapter, __init__ with factory)
- `app/services/routing/` — 5 files (types, mappers,
  google_maps_adapter [Routes v2 via httpx], static_adapter,
  __init__ with factory)
- `app/routers/calendar_router.py` — `/api/calendar/{status,
  oauth/start, oauth/callback}`
- `app/services/whatsapp_intake_service.py` — four new tool handlers:
  `schedule_calendar_event`, `list_calendar_events`,
  `travel_estimate`, `inspect_drive_url`. Plus a private `_geocode`
  hitting Google Geocoding API with the same Maps key.
- Tests: `tests/services/test_google_integrations.py` (16 cases)

**Current behavior:**
- Calendar factory resolves: OAuth (when client_id/secret configured
  AND org has a stored credential row keyed by
  `(org_id, 'google_calendar')`) → service-account (when SA JSON
  readable) → Fake (dev fallback).
- OAuth bootstrap is a one-time per-org consent flow:
  `GET /api/calendar/oauth/start` → Google consent screen →
  `GET /api/calendar/oauth/callback` exchanges + persists encrypted
  via `CredentialStore` (same Fernet-encrypted table used for YouTube
  OAuth; just a different `provider`).
- Maps adapter calls `routes.googleapis.com/directions/v2:computeRoutes`
  with `X-Goog-Api-Key` + a minimum field mask. Geocoding via
  `maps.googleapis.com/maps/api/geocode/json`. Same API key for both.
- Drive inspection reuses `gdrive_service` parsers — no new download
  path; pure metadata extraction from a URL.

**Known gaps / spec candidates:**
- 🟡 Update-event flow not exposed (create/list/delete only).
- 🟡 No Calendar-watch webhook → agent doesn't react to events
  created outside its own conversations.
- 🟡 Routes uses `TRAFFIC_UNAWARE`. Flip to `TRAFFIC_AWARE` once we
  decide the per-call latency budget.
- 🟡 Geocoding has no caching — same address geocoded twice costs
  twice. Trivial Redis cache would help.
- 🟡 Drive-inspect doesn't probe Drive API for permissions/existence —
  only URL parse. A real probe would need Drive API auth.

**Dependencies:** `CredentialStore` (3.3), `google-api-python-client`
+ `google-auth` (deps), `gdrive_service` (existing), the `secrets/`
volume mount on the docker stack.

---

## 4 · Conversation lifecycle, in pseudocode

The narrative shape of a single inbound turn, all branches stitched.

```python
async def handle_inbound(sender: str, body: str, media: Media | None):
    # ─── Branch 3.7: dedup pre-filter (fast Redis) ──────────────────
    if redis.SETNX("whatsapp:msg_seen:" + msg_id, ttl=5min) is False:
        return 200  # WAHA's duplicate event

    # ─── Branch 3.5: surface-specific auth ──────────────────────────
    if surface == "whatsapp" and not intake.is_authorized(sender):
        await intake.send_reply(sender, "Olá! Este número não está...")
        return 200

    # ─── Branch 3.2: media → text ───────────────────────────────────
    if media:
        resolved = await media_service.resolve_inbound(media.url, ...)
        body = merge(resolved.text, body)  # caption + transcript / desc

    # ─── Branch 3.3: durable audit + UNIQUE-driven idempotency ──────
    try:
        message_store.record(
            session_id=intake.canonical_session_id(sender),
            direction="inbound",
            body=body,
            provider_message_id=msg_id,
            structured_payload=resolved.structured_payload if resolved else None,
        )
    except DuplicateMessage:
        return 200  # WAHA's duplicate that escaped Redis TTL

    # ─── Branch 3.4: canonical session normalization ────────────────
    canonical = intake.canonical_session_id(sender)

    # ─── Branch 3.1: OpenAI tool-call loop ──────────────────────────
    chatbot = ChatbotService(
        redis_client=redis,
        intake_service=intake,
        session_id=canonical,
    )
    reply_text = await chatbot.reply(body)
    # inside the loop, tools may dispatch:
    #   - lookup_property → Vista CRM
    #   - prepare_upload_* → Redis pending state
    #   - confirm_upload → background task (YouTube publish)
    # Each tool call hits the IntakeService methods (Branch 3.6).
    # Memory append happens at the loop level.

    # ─── Branch 3.5: surface-specific outbound ──────────────────────
    if surface == "whatsapp":
        await intake.send_reply(sender, reply_text)
        # _reply captures LID from response + appends outbound to memory
    else:  # platform chat
        return ChatReply(session_id=canonical, reply=reply_text, ...)
```

---

## 5 · Environment + config inventory

Settings the agent reads (from `app/config.py` `CrawlerSettings`):

```
# Chatbot orchestration
OPENAI_API_KEY            (required for any LLM call)
OPENAI_CHAT_MODEL         (default: gpt-4o-mini)
OPENAI_AUDIO_MODEL        (default: gpt-4o-mini-transcribe)
OPENAI_VISION_MODEL       (default: gpt-4o)
WHATSAPP_CHATBOT_ENABLED  (default: true; gates the WhatsApp router)

# WhatsApp
WAHA_BASE_URL              (internal — http://waha:3000)
WAHA_API_KEY
WAHA_SESSION               (default: default)
WAHA_WEBHOOK_URL           (synced by refresh_cf_tunnel.sh)
WAHA_WEBHOOK_HMAC_SECRET   (optional)
WHATSAPP_AUTHORIZED_NUMBERS

# Persistence
REDIS_URL                  (default: redis://redis:6379/0)
DATABASE_BACKEND           (sqlite|supabase; sqlite drives the dev path)
SQLITE_PATH                (default: tmp/dev.sqlite3)
LOCAL_DEV_ORG_ID           (used by chat/whatsapp routers when no JWT)

# CRM
CRM_BASE_URL / CRM_API_KEY (Vista REST)
VISTA_BASE_URL / VISTA_API_KEY (aliases; auto-mapped to CRM_*)

# Tunnel / frontend
TUNNEL_HOSTNAME            (synced from cloudflared logs)
FRONTEND_BASE_URL          (now = TUNNEL_HOSTNAME under single-URL setup)
```

---

## 6 · Per-branch ownership for the next spec round

When you write a focused spec for any branch below, this file is
the starting context. Each branch has a single primary spec author
candidate (the engineer most familiar with its current code) and a
set of dependencies that determine spec order.

| Branch | Where to spec next | Depends on |
|--------|-------------------|------------|
| 3.1 Conversation orchestration | structured outputs / streaming / summarization | 3.3 |
| 3.2 Multimodal intake | doc formats beyond PDF / OCR mode / chunked video | 3.1 |
| 3.3 Persistence | retention policy / transcript viewer UI / RLS hardening | 3.4 |
| 3.4 Identity | multi-tenant users table / pending-LID parking | 3.3 |
| 3.5 Surface adapters | streaming chat / conversation list page / image-attach UX | 3.1, 3.6 |
| 3.6 Tool surface | tool-permission gating / status/list tools / structured extract | 3.1 |
| 3.7 Dedup oracle | session-namespaced dedup keys | 3.3 |
| 3.8 Single-URL proxy | named tunnel / rate-limit / cache-busting | — |

Spec order recommendation: 3.3 first (everything depends on
persistence), then 3.4 (identity is hot-path), then 3.1 + 3.6
together (tool surface co-evolves with the loop), then 3.2 (richer
media), then 3.5 / 3.7 / 3.8 in parallel.

---

## 7 · Pointers to related docs in this workspace

- `PLAN.md` — Phase 5 original plan + sub-phase tracking.
- `CHECKLIST.md` — phase deliverable status.
- `findings.md` — per-phase learning log (5-category format).
- `PROMOTIONS.md` — index of `.promotions/<slug>.md` files (lift
  candidates for noc).
- `CF_TUNNEL.md` — Cloudflare tunnel operational runbook.
- `README.md` — workspace orientation.
- Companion notes in noc root:
  - `noctusai/SESSION-NOTES_chatbot-multichannel-2026-05-12.md` —
    historical narrative of how this agent was built.
  - `noctusai/SEED-NEEDS-DEV-AUTH-AND-SQLITE.md` — orthogonal
    seed-level recommendation from this same session.

---

*Refresh this file at the close of any project that adds or
removes a branch from §3. The history of how each branch came to
be lives in `findings.md` and the commit log; this file is the
current snapshot.*
