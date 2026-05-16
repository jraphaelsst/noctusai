# 📩 Session findings — chatbot/WhatsApp multichannel conversational system

> **Date:** 2026-05-12
> **Source workspace:** `noctusai-youtube-crawler`
> **Source branch:** `feat/platform-chat-agent`
> **Reference scope:** historical / read-before-planning. The pattern
> described below is going to be expanded into noc's own products
> (mailing, daily-life, therapy, ERP triage) — this file captures the
> route we actually walked, including the wrong turns, so the next
> implementer can plan a cleaner path.
>
> **Companion file:** `SEED-NEEDS-DEV-AUTH-AND-SQLITE.md` (filed
> alongside this one) captures a separate seed-level recommendation
> surfaced by the same session.

---

## TL;DR

We took a previously-existing OpenAI-driven WhatsApp chatbot and turned
it into a **surface-agnostic multimodal conversational system**:

- Same brain reachable from WhatsApp (via WAHA) AND from a new
  platform-side `/chat` page.
- Reads text, voice notes, photos, videos, PDFs, scanned docs.
- Talks to Vista CRM, queues YouTube uploads, persists conversations
  durably, dedupes WAHA's noisy duplicate-event delivery, recognizes
  WhatsApp's @lid identifier, and now runs behind a single Cloudflare
  Quick Tunnel URL that fronts backend + frontend + WAHA on one host.

Twelve commits, all green end-to-end against live OpenAI + Vista +
Gmail SMTP + WAHA. Validated by sending real messages to and from
the user's WhatsApp + the platform UI.

When this pattern gets lifted into noc, the three promotion manifests
filed in the workspace's `.promotions/` are the migration map:

1. `whatsapp-chatbot-service` → `noctusai_lib.domain.chatbot.openai_orchestrator`
2. `waha-response-registry` → `noctusai_lib.integrations.whatsapp.response_registry`
3. `platform-chat-agent` (supersedes #1) → adds chat router + Chat UI
4. `multimodal-stack` → `noctusai_lib.integrations.media` + `chatbot.message_store`
5. `single-url-tunnel` → seed-workspace template's `proxy/` + frontend nginx

---

## 1. What we built — architecture in one diagram

```
                                  ┌──── WhatsApp (real users) ────┐
                                  │                                │
                                  ↓                                ↑
                            ┌──────────┐                     ┌──────────┐
                            │   WAHA   │── webhook (inbound)→│  /api/   │
                            │ (Docker) │←── /api/sendText ───│ whatsapp │
                            └──────────┘                     │ /webhook │
                                                             └────┬─────┘
                                                                  │
┌─── Platform users (browser) ─→ /chat (React) ──→ /api/chat/* ──┤
│        ↑                                                        │
│        │                                                        ↓
│  Single Cloudflare         ┌──────────────────────────────────────┐
│  Quick Tunnel URL          │     IntakeService (canonical key)     │
└──── proxy:8090 ─→──┐       │  ┌────────────────────────────────┐  │
                     │       │  │   ChatbotService (OpenAI tool  │  │
       proxy:8090 ───┤       │  │   orchestration loop, surface- │  │
       (nginx) ──→ app:8010 │  │   agnostic, session_id-keyed)  │  │
                ──→ frontend │  └────────┬───────────────────────┘  │
                ──→ waha     │           │                          │
                             │  ┌────────▼───────────────────┐      │
                             │  │ MediaService (audio→Whisper│      │
                             │  │ /image→vision/video→ffmpeg │      │
                             │  │ /pdf→PyMuPDF+vision)       │      │
                             │  └────────┬───────────────────┘      │
                             │  ┌────────▼───────────────────┐      │
                             │  │ MessageStore (conversation_│      │
                             │  │ messages table, UNIQUE     │      │
                             │  │ provider_message_id dedup) │      │
                             │  └────────┬───────────────────┘      │
                             └──────────┼─────────────────────────┘
                                        ↓
                              ┌───────────────────┐
                              │ Vista CRM (live)  │
                              │ Upload pipeline   │
                              │ Redis memory list │
                              │ SQLite audit log  │
                              └───────────────────┘
```

The IntakeService is the seam. Every surface (WhatsApp, platform chat)
flows through ONE intake. The intake builds a canonical session id,
hands the inbound to the chatbot loop, and the chatbot reaches back
into the intake for its tool invocations. **One brain, two surfaces.**

---

## 2. The 13 commits, narrated

Each commit's hash → what it landed → what it taught us. Read top-down.

### Commit `9948b60` — initial WhatsApp chatbot (inherited from Codex)
First OpenAI tool-call loop on top of WAHA inbound. 5 tools:
`lookup_property`, `prepare_upload_request`, `get_pending_upload`,
`confirm_upload`, `cancel_upload`. WhatsApp-only. Redis memory.

**Lesson:** matches the pattern from `../whatsapp-google-scheduling`
(the reference repo) — system prompt + tool registry + iteration cap
+ Redis-backed memory. Validated as a known shape from day one.

### Commit `53a5ed0` — platform chat agent (chat UI + file upload)
Generalized `WhatsAppChatbotService` → `ChatbotService` taking an
opaque `session_id`. WhatsApp passes the phone JID; platform chat
passes `web:<uuid>`. Added 6th tool `prepare_upload_from_file` so
file attachments queue browser-side uploads in addition to Drive
URLs. New `chat_router.py` with multipart `/api/chat/message`.
New `Chat.tsx` page + `useChat.ts` hook. Nav entry.

**Lesson:** the smallest decoupling that works — rename the
constructor arg, accept either form, keep the legacy export alive
as an alias. Zero refactor of the WhatsApp router needed.

### Commit `0226594` — path-separation prompt + bash 3.x hook fix
User caught that the bot was hard-rejecting anything that wasn't a
property upload ("voce cuida apenas desse fluxo"). Widened the
SYSTEM_PROMPT to a 3-path decision (media / other-capabilities /
general chat). Also fixed a pre-commit hook that broke on
modification-only commits under `set -u` (bash 3.x empty-array
expansion).

**Lesson:** be careful with "polite refusal" instructions in
prompts — LLMs follow them too obediently. Frame the prompt
around what the bot DOES, not around what it refuses.

### Commit `598f8f7` — LID-aware auth + memory on every outbound
Two real bugs found in production:
1. WhatsApp's modern `@lid` identifier (e.g.
   `33613018058989@lid`) doesn't contain the phone number. Our
   `is_authorized()` only stripped `@c.us`/`@s.whatsapp.net`, so
   inbound LID messages were silently dropped from the whitelist.
   Fix: 3-tier resolution (raw lid whitelist → phone form →
   Redis-backed lid↔phone cache populated on first successful
   outbound).
2. Memory was only appended by the chatbot's own reply path. The
   `/api/settings/waha/test` send + the legacy state-machine
   `_reply()` were write-and-forget. So when the user asked "what
   did you just send me?" the bot had no record. Fix: shared
   `append_memory()` helper called from every outbound boundary,
   mirroring `whatsapp-scheduling`'s
   `ConversationBufferService.append_to_memory`.

**Lesson:** the durable conversation_messages audit log was the
single most useful tool for debugging. The user's symptom report
("bot replies to nothing") got matched to the actual Redis cache
state in five queries.

### Commit `f9839d4` — real multimodal bot (audio/image/video/PDF)
Added `MediaService` that downloads WAHA media URLs, classifies
by mimetype, and produces enriched text the chatbot reads as a
normal user message. audio→Whisper, image→vision,
video→ffmpeg-extract-audio→Whisper, pdf→pdfminer+summary.
Wired into BOTH whatsapp_router AND chat_router.

Also created the **`conversation_messages` SQLite/Postgres table**
with `UNIQUE(provider_message_id)` for durable dedup of WAHA's
duplicate `message + message.any` event delivery. Mirrors
whatsapp-scheduling's `ConversationMessage` model.

Truthful SYSTEM_PROMPT — bot now claims ONLY what's real.

### Commit `fedd4cf` — WAHA media URL rewrite + early dedup
First multimodal test exposed: WAHA emits media URLs using its
OWN external-facing host (`http://localhost:3000/api/files/...`)
because WAHA was designed assuming the consumer is the operator's
browser. From inside the `app` container, `localhost:3000` IS the
app — TCP connection failed. Fix: `_rewrite_waha_url(url)` swaps
the scheme/host/port of any `/api/*` URL onto our internal
`WAHA_BASE_URL=http://waha:3000`.

Also moved the SETNX dedup pre-filter to BEFORE the media download
so duplicate events don't both pay the OpenAI cost (~$0.001 each
+ 1-2s latency).

**Lesson:** any inter-service URL emitted by a vendor SDK needs
to be inspected before consumed inside the docker network. The
"external-vs-internal hostname" surface is a recurring shape.

### Commit `51be7b7` — video scene-vision + PDF rasterize fallback
User's first video had no speech (pool ambient) → Whisper
returned empty → bot replied "couldn't transcribe". User
correctly pointed out: video should ALSO produce a scene
description (the user's words: "o bot deve reconhecer o video,
com cenario e contexto, e analisar as cenas"). Built parallel
pipelines: ffmpeg extracts 4 keyframes (10/30/60/90% of duration)
→ `_call_vision_multi` sends all in one vision call → bot
describes scene; Whisper runs in parallel for audio.

Added the SAME rasterize-then-vision fallback for scanned PDFs
where pdfminer finds no text layer (CNH-style ID cards).
PyMuPDF rasterizes pages 1-3 at 1024px → vision reads them.

Plus 3 deps: `pdfminer.six`, `PyMuPDF`, both already used by
noc's `erp-imobiliario`. Image rebuild.

### Commit `72f70bf` — PDF prompt + refusal retry + gpt-4o vision
The pipeline worked but the LLM said "Não foi possível extrair
texto" — literally quoting back the over-narrow prompt's fallback
("focus on real-estate fields"). The driver's license had no
real-estate fields → LLM gave up by reciting the prompt.

Fixes: broader document prompt (classify type first, list type-
appropriate fields), filename prime so the model knows what to
expect, refusal-detection retry, vision model bumped to `gpt-4o`
(mini misreads ~8pt text on rasterized scans).

**Lesson:** pathological prompt obedience. LLMs follow narrow
instructions even when they hurt the goal. Frame prompts around
the TYPES of input the system handles, not around one specific
caller's narrow use case.

### Commit `61d684f` — orphan-method bug killed all media inbound
**The most important debugging moment of the session.** User
reported "PDFs still don't work" after the prompt fix. The audit
log in `conversation_messages.structured_payload` had the answer
visible from one query:

```
"error": "download_failed",
"error_message": "'MediaService' object has no attribute '_download'"
```

The previous `_looks_like_refusal` insertion accidentally moved
`_download`, `_rewrite_waha_url`, `_waha_headers` OUTSIDE the
class definition — they became orphan module-level functions.
Every `self._download(url)` raised AttributeError, swallowed by
`resolve_inbound`'s outer try → returned the
`media_type: unknown / error: download_failed` fallback shape.

The "prompt is too narrow" theory we spent a commit on was
WRONG. The LLM was never reached because the download crashed
before it. The visible "couldn't extract text" replies were the
fallback messages from the audit log path, not LLM refusals.

Same commit: switched `_extract_pdf_text` from pdfminer.six to
PyMuPDF's `page.get_text()` to match noc's
`erp-imobiliario/.../certidoes_service.py` convention. Plus
refusal detection on BOTH text-summary AND rasterized-summary
paths. Plus diagnostic logging through `_resolve_document` for
future failures.

**Lesson:** persist failures. The structured audit log made this
diagnosis trivial. Without it we'd have spent another commit on
the wrong theory. **The audit log paid for itself in one session.**

### Commit `b497979` — single-URL tunnel + SPA fallback
User asked for the frontend online via the SAME Cloudflare URL as
the backend. Two related fixes:
1. Frontend nginx had no SPA fallback → `localhost:8150/chat`
   returned a 404 from nginx because `/chat` is a client-side
   route. Added `try_files $uri $uri/ /index.html` in a custom
   nginx config.
2. New `proxy` nginx service on port 8090 that path-routes across
   `app:8010` (`/api/*`, `/openapi.json`, `/redoc`), `waha:3000`
   (`/waha/*`), and `frontend:8150` (`/*`). Cloudflared repointed
   at `proxy:8090`. One tunnel URL serves backend + frontend +
   WAHA.

Frontend `apiBase()` helper made runtime-smart: same build
artifact works for direct (`:8150`), proxied (`:8090`), and
tunneled access — no rebuild on URL changes.

### Commit `10167b0` — `/chat` public route
Final discovery: even with the tunnel routing correctly, the
frontend `createProductApp` auth gate was still suppressing
unauthenticated `/chat` visits. Moved `/chat` into the seed's
`publicRoutes` array so unauth visitors land directly on the
agent (matches the backend's unauthenticated posture). This
triggered a separate seed-level recommendation filed in
`SEED-NEEDS-DEV-AUTH-AND-SQLITE.md`.

---

## 3. The five .promotions/ manifests filed for noc

In order of N=2 readiness:

| Slug | Origin → noc destination |
|------|-------------------------|
| `whatsapp-chatbot-service` | `app/services/chatbot_service.py` → `noctusai_lib.domain.chatbot.openai_orchestrator` |
| `waha-response-registry` | `app/services/waha_response_registry.py` → `noctusai_lib.integrations.whatsapp.response_registry` |
| `platform-chat-agent` | `chat_router.py` + `Chat.tsx` + `useChat.ts` → `noctusai_lib.api.chat_router` + `noctusai_lib.frontend.components.Chat` |
| `multimodal-stack` | `media_service.py` + `message_store.py` + migration 007 → `noctusai_lib.integrations.media` + `noctusai_lib.domain.chatbot.message_store` |
| `single-url-tunnel` | `proxy/nginx.conf` + frontend nginx + `apiBase.ts` → `templates/seed-workspace-docker/proxy/` + `templates/product-seed/frontend/nginx/` + `noctusai_lib.frontend.lib.apiBase` |

Each manifest has full seed_first_analysis (Q1-Q6) + integration
notes. They live at
`noctusai-youtube-crawler/.promotions/<slug>.md`. The workspace's
`PROMOTIONS.md` indexes all five.

---

## 4. Cross-product takeaways for noc planning

Things that are likely to recur when this pattern lands in other
noc products. **Read these before scoping a chatbot integration for
mailing / daily-life / therapy / ERP triage.**

### 4.1 The "duplicate WAHA event" race is real and durable

WAHA subscribes the webhook URL to BOTH `message` AND `message.any`
for every inbound. Same `provider_message_id`, two HTTP calls,
arriving within milliseconds. **Without dedup, every chatbot
invocation runs twice — once per event.** Cost doubles silently.

The whatsapp-scheduling pattern: `UNIQUE(provider_message_id)`
constraint on a `conversation_messages` table; the second INSERT
trips an IntegrityError caught by the webhook handler.

Our pattern: same DB constraint + a Redis SETNX pre-filter at the
TOP of the webhook handler so the second event returns 200 in
~25ms without touching OpenAI. The DB constraint is the durable
backstop for restart-survival.

**Recommendation for noc seed:** ship the SETNX + UNIQUE pattern
as a `noctusai_seed.webhook_dedup(provider_message_id)` decorator
or middleware. Every WAHA consumer needs it.

### 4.2 WhatsApp's @lid hides the phone number

Modern WhatsApp delivers inbound from `<random_digits>@lid`. The
@lid number is OPAQUE — it doesn't contain the phone. Same user
can have different LIDs in different chats. Phone-form authorization
whitelists silently reject @lid senders.

**Recommendation for noc seed:** ship `canonical_session_id()` and
`is_authorized()` patterns in the WAHA integration layer. The
intake-service's lid_to_phone cache (populated opportunistically
from outbound send responses' `_data.id.remote`) is the missing
bridge. Plus a migration helper that copies LID-keyed memory to
the phone-keyed memory on first capture so first-contact-from-LID
conversations stay coherent.

### 4.3 Vendor-emitted URLs need rewriting inside docker

WAHA emits media URLs against `http://localhost:3000/...` (its
own external-facing hostname). The `app` container can't reach
that hostname — `localhost` is the app itself inside the docker
network. **Every chatbot product that downloads media will hit
this on first try.**

Pattern that works: rewrite scheme+host+port of any vendor URL
matching the vendor's internal API path prefix to the docker-DNS
service name (`http://waha:3000`). External CDN URLs pass through
unchanged.

**Recommendation for noc seed:** the WAHA integration adapter
should accept `external_base_url` AND `internal_base_url` and do
the rewrite automatically. Same shape applies to any vendor that
emits self-referential URLs (Supabase storage, MinIO, etc.).

### 4.4 The audit log paid for itself in one session

`conversation_messages` started as a dedup oracle. It became the
primary debugging surface. Every "the bot didn't work for me"
report can be matched to a row with `structured_payload` showing
exactly which path the resolver took. Three diagnoses in this
session came directly from one SELECT.

**Recommendation:** chatbot/agent-style features that ship without
durable per-message persistence will be hard to debug in
production. Make the audit log a first-class part of the seed
chatbot primitive, not a per-product opt-in.

### 4.5 Vision-model refusals are a recurring shape

LLMs refuse politely when prompts are too narrow OR when content
falls outside the prompt's framing. A real-estate-narrow prompt
made vision refuse to read a CNH. **Build refusal detection +
retry into every vision call.** The `_looks_like_refusal()`
helper (short replies, "não foi possível" / "não consegui" /
"unable to" / "i cannot" markers) generalizes.

**Recommendation:** lift `_looks_like_refusal()` into
`noctusai_lib.integrations.llm.vision` alongside the existing
`analyze_image` wrapper. Make refusal-retry an opt-in flag.

### 4.6 SPA frontends need nginx SPA fallback

Every Vite-built React product with React Router will 404 on
direct loads of any deep route unless `try_files $uri $uri/
/index.html` is in the nginx config. **This is a one-line fix
that every product needs and most products forget until they
demo from a phone.**

**Recommendation:** the seed-workspace template's frontend
Dockerfile + nginx config should ship the SPA fallback by
default.

### 4.7 Path-based reverse proxy beats per-service tunnels

Originally each service needed its own tunnel URL (frontend,
backend, WAHA dashboard). Three URLs, three sets of OAuth
callback URIs to register, three sets of webhook URLs to update,
constant rotation when the Quick Tunnel hostname changes.

The single-proxy + path-routing approach folds all of that into
one URL. Refresh script syncs `TUNNEL_HOSTNAME`,
`YOUTUBE_REDIRECT_URI`, `WAHA_WEBHOOK_URL`, `FRONTEND_BASE_URL`
to the same hostname in one shot.

**Recommendation:** ship the proxy as part of `seed-workspace-docker`.

---

## 5. What's still pending (handoff state at session close)

Items the user knows about, NOT silently deferred:

- **PDF understanding end-to-end retest** — the orphan-method fix
  + PyMuPDF switch landed in `61d684f`; the user was about to
  retest with their CNH / `Funcionar Não é Estar bem P2.pdf` /
  `plano-meta-ads.pdf` when the session pivoted to the tunnel +
  feedback files. Should work now per the diagnostic logging, but
  not user-validated as of this writing.

- **YouTube OAuth connection** — `Settings → Connect YouTube` was
  never completed. Every upload-chatbot path that reaches the
  `confirm_upload` tool will fail at `YouTubeNotConnected`. The
  bot relays the error truthfully.

- **Real auth on `/api/chat/*`** — currently unauthenticated by
  product direction. The `/chat` frontend page is in
  `publicRoutes` to match. When auth lands, both move back to the
  protected surface (one-line revert each).

- **Frontend dist artifacts in git** — this repo commits the
  `frontend/dist/` build outputs. Should be added to `.gitignore`
  + CI-built; out of scope for this session.

---

## 6. Validation that ran live (real APIs, not mocks)

For the next implementer's confidence: the following ALL ran end-
to-end against live external services during this session, with
the user as the WhatsApp recipient:

| Surface | Validated against |
|---------|-------------------|
| WAHA inbound webhook | Real WhatsApp messages from +5511974693365 |
| WAHA outbound send | Real WhatsApp delivery, return id `3EB0...` |
| OpenAI chat completion | gpt-4o-mini, ~3-5s end-to-end |
| OpenAI Whisper transcribe | Real voice notes (pt-BR) |
| OpenAI vision describe | Real photos + video keyframes + rasterized PDF pages |
| Vista CRM | Live `/imoveis/detalhes?imovel=ONE10121` returning real property data |
| Gmail SMTP | Real email delivery to joaoraphaelsst@gmail.com |
| Cloudflare Quick Tunnel | https://fixed-actively-levy-jake.trycloudflare.com/* (rotates) |
| ffmpeg keyframe extract | Real videos, 4 frames at 10/30/60/90% of duration |
| ffmpeg audio extract | Real videos → opus 32kbps → Whisper |
| PyMuPDF text-layer extract | Real text-PDFs |
| PyMuPDF rasterize + vision | Real scanned PDFs (CNH) |

165/166 backend pytest cases green throughout the session (the one
failure was a pre-existing team-listing test unrelated to anything
touched in this branch).

---

## 7. How to read this when planning the noc-side rollout

1. Skim §3 (the five promotion manifests) — that's the migration
   map.
2. Read §4 (cross-product takeaways) — those are the bugs you'll
   hit too if you don't lift the patterns.
3. Skim §2 (commit narrative) — gives you the sequence so you can
   plan a clean N=2 implementation without retracing the wrong
   turns we made.
4. Reference §6 (validation) when discussing scope — these are the
   "yes, this actually worked" data points.

The companion file `SEED-NEEDS-DEV-AUTH-AND-SQLITE.md` (filed in
the same commit set) describes a separate seed-level recommendation
unrelated to the chatbot but surfaced by the same session.

---

— filed by Claude (Opus 4.7) working in `noctusai-youtube-crawler`
  on branch `feat/platform-chat-agent`, 2026-05-12, at the user's
  request as historical reference for future expansion into noc.
