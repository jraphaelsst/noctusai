# SOURCE-MANIFEST — validated source brought in-home

> **Durable, self-contained.** Created 2026-05-16 (Wave-0.5 follow-up). This manifest and the
> `reference/source/` tree it describes are the **authoritative, workspace-independent** copy of the
> validated source the absorption ports from. Every path below is relative to
> `projects/social-wiring-absorption/reference/source/`. No durable doc references the originating
> transient workspace path — it is the user's to retire manually.

## ⭐ Wave-2 port uses THIS, not the workspace

The Wave-1 reconcile proved the prior `reference/` set (promotion manifests + session-notes only)
is **insufficient** for a true reconcile/port — the validated SOURCE CODE is required. That source
now lives here. **Wave 2 (and Wave 1 reconcile) port from `reference/source/`. Zero dependence on
the originating workspace remains** — it may be deleted by the user at any time without blocking
this project.

## Tree summary

```
reference/source/
  backend/
    app/                       (top-level: config, lifespan, main, dependencies,
                                 database, sqlite_client, rate_limit, responses)
      routers/                 10 routers
      schemas/                 5 schema modules
      services/                21 service modules + 4 subpackages
        calendar/  drive_api/  routing/  meta/   (each: Protocol+Fake+Real+OAuth+factory)
    migrations/                8 SQL migrations (001–008)
    tests/                     routers(8) services(18) integration(2) + conftest
    requirements.txt
    apply_sqlite_migrations.py
    WAHA_RESPONSE_FORMATS.md   (carry-forward — see §Carry-forward)
  frontend/
    src/                       App.tsx, main.tsx, pages/(14), hooks/(7),
                                 components/(28, incl. ui/), lib/(apiBase,utils)
    nginx/default.conf
    package.json  vite.config.ts  index.html  tsconfig.json
    tailwind.config.ts  postcss.config.js  eslint.config.js  .env.example
```

**Totals:** 194 files · ~1.5 MB · 103 `.py` · 73 `.ts/.tsx` · 8 `.sql` · 1 `.md`.
EXCLUDED on copy: `node_modules`, `dist`, `.git`, `__pycache__`, `.pytest_cache`,
`.venv`/`venv`, `.noctusai-state`, `tmp/`, `secrets/`, all `.env`/`.env.bak*`
(`.env.example` files WERE copied).

## Backend — routers inventory (filename → purpose)

| Router | Purpose |
|---|---|
| `calendar_router.py` | Google Calendar OAuth bootstrap + status endpoints. |
| `chat_router.py` | Platform-side chat surface for the OpenAI tool-calling chatbot. |
| `dashboard_router.py` | Dashboard HTTP surface — read-only aggregates over the local cache. |
| `google_router.py` | Google-wide introspection endpoints. |
| `intake_monitor_router.py` | Intake/flow monitor — read-only window into live WhatsApp conversations. |
| `meta_router.py` | Meta (Facebook + Instagram) OAuth bootstrap + status endpoints. |
| `settings_router.py` | Settings router — UI-side configuration surface. |
| `upload_router.py` | Upload pipeline HTTP surface. |
| `videos_router.py` | Videos pipeline HTTP surface. |
| `whatsapp_router.py` | WhatsApp inbound webhook — WAHA forwards messages here. |

## Backend — services inventory (filename → purpose)

| Service | Purpose |
|---|---|
| `chatbot_service.py` | OpenAI tool-calling chatbot — surface-agnostic. (52 KB — core orchestrator) |
| `conversation_module.py` | Conversation framework wiring for the bot. |
| `credential_store.py` | Credential persistence with Fernet encryption at rest. |
| `crm_service.py` | Vista CRM integration — fetch real-estate property metadata. |
| `dashboard_service.py` | Read-only aggregates for the Dashboard panels. |
| `download_cache.py` | Redis-backed cache for Drive folder downloads. |
| `email_service.py` | SMTP email sender — upload-completion notifications. |
| `gdrive_service.py` | Google Drive download — link → local file path. |
| `google_scopes.py` | Google OAuth scope catalog + resolver + post-consent introspection. |
| `media_service.py` | Multimodal inbound resolver (audio/vision/PDF/video — 40 KB). |
| `message_store.py` | Durable persistence + idempotency for WhatsApp / chat messages. |
| `notification_service.py` | Notification fan-out — dispatch upload-completion alerts. |
| `upload_queue.py` | Global single-flight upload queue. |
| `upload_service.py` | Upload pipeline orchestrator (32 KB). |
| `video_cache_service.py` | Local mirror of the connected channel's video catalog. |
| `waha_response_registry.py` | Local WAHA response-shape registry. |
| `whatsapp_chatbot_service.py` | Back-compat re-export → chatbot_service. |
| `whatsapp_intake_service.py` | WhatsApp inbound intake — parse commands, manage conversation state (105 KB — largest module). |
| `whatsapp_outbound.py` | WhatsApp outbound emission helpers. |
| `youtube_service.py` | YouTube Data API v3 wrapper (30 KB; query + upload surface). |

### Service subpackages (each: Protocol + Fake + Real/Google + OAuth + factory)

| Subpackage | Purpose | Members |
|---|---|---|
| `services/calendar/` | Calendar package factory. | `_google_api`, `fake_adapter`, `google_adapter`, `oauth_adapter`, `mappers`, `types` |
| `services/drive_api/` | Drive API package factory. | `_drive_api`, `fake_adapter`, `google_adapter`, `oauth_adapter`, `mappers`, `types` |
| `services/routing/` | Routing (Google Maps) package factory. | `google_maps_adapter`, `static_adapter`, `mappers`, `types` |
| `services/meta/` | Meta (FB+IG) Graph API package. | `_meta_api`, `fake_adapter`, `oauth_adapter`, `mappers`, `types` |

### Schemas

`dashboard.py` · `settings.py` · `upload.py` · `video.py` · `whatsapp.py`
(all Pydantic schema modules for their respective surfaces).

### App top-level modules

`config.py` (13 KB settings) · `lifespan.py` (FastAPI lifespan hooks) · `main.py` (app entrypoint) ·
`dependencies.py` (DI wiring) · `database.py` · `sqlite_client.py` (SQLite dev client with a
Supabase-like surface — the SEED-NEEDS dev-auth+sqlite primitive) · `rate_limit.py` (delegates to
framework) · `responses.py`.

### Migrations (001–008)

`001_seed` · `002_credentials` · `003_upload_jobs` · `004_video_cache` ·
`005_notifications` · `006_product_code` · `007_conversation_messages` · `008_thumbnail_url`.

## Frontend inventory

- **Pages (14):** `AcceptInvite`, `Chat`, `Conexao`, `Dashboard`, `Equipe`, `ForgotPassword`,
  `Landing`, `Login`, `Monitor`, `NotFound`, `Settings`, `SSOCallback`, `Upload`, `Videos`.
- **Hooks (7):** `useChat`, `useDashboard`, `useSettings`, `useUpload`, `useVideos`,
  `useWhatsAppConnection`, `useWhatsAppIntake`.
- **Components (28):** shadcn-style UI primitives + `MetricCard`, `UploadZone`, `VideoCard`,
  `ViewsChart`, `page-skeleton`, `ui/`.
- **lib:** `apiBase.ts`, `utils.ts`. **App shell:** `App.tsx`, `main.tsx`.
- `package.json` carries name `seed-frontend` (re-skinned to social-wiring scope in Wave 2.4).

## Carry-forward

`backend/WAHA_RESPONSE_FORMATS.md` lived ONLY in the workspace product tree (not previously copied
to `reference/`, not manifest-covered). It is now in-home at
`reference/source/backend/WAHA_RESPONSE_FORMATS.md` and travels with Wave 1.E2 (whatsapp) / Wave 2.

## Promotion-manifest → source cross-link

The 14 manifests at `reference/.promotions/<slug>.md` map to these `reference/source/...` files:

| `.promotions/<slug>.md` | Maps to `reference/source/...` |
|---|---|
| `platform-chat-agent.md` | `backend/app/services/chatbot_service.py`, `conversation_module.py`, `message_store.py`, `backend/app/routers/chat_router.py` |
| `whatsapp-chatbot-service.md` | `backend/app/services/whatsapp_intake_service.py`, `whatsapp_outbound.py`, `whatsapp_chatbot_service.py`, `backend/app/routers/whatsapp_router.py`, `schemas/whatsapp.py` |
| `whatsapp-connection-page.md` | `frontend/src/pages/Conexao.tsx`, `frontend/src/hooks/useWhatsAppConnection.ts` |
| `whatsapp-intake-monitor.md` | `backend/app/routers/intake_monitor_router.py`, `frontend/src/pages/Monitor.tsx`, `frontend/src/hooks/useWhatsAppIntake.ts` |
| `waha-response-registry.md` | `backend/app/services/waha_response_registry.py`, `backend/WAHA_RESPONSE_FORMATS.md` |
| `google-integrations.md` | `backend/app/services/calendar/`, `routing/`, `gdrive_service.py`, `backend/app/routers/calendar_router.py`, `google_router.py` |
| `drive-api-client.md` | `backend/app/services/drive_api/`, `gdrive_service.py`, `download_cache.py` |
| `google-scope-discovery.md` | `backend/app/services/google_scopes.py`, `backend/app/routers/google_router.py` |
| `meta-integrations.md` | `backend/app/services/meta/`, `backend/app/routers/meta_router.py` |
| `multimodal-stack.md` | `backend/app/services/media_service.py` |
| `single-url-tunnel.md` | `frontend/nginx/default.conf` (proxy redundant under house container model — fold per O.Q.2) |
| `production-deploy-tooling.md` | Workspace-level ops scripts (NOT in product tree; tracked separately, not under `reference/source/`) |
| `recreate-script.md` | Workspace-level recreate script (NOT in product tree) |
| `openssl-tls-workaround.md` | Cross-cutting TLS workaround (config-level; no single source file) |

Notes:
- `settings_router.py` (31 KB) + `schemas/settings.py` are the UI configuration surface spanning
  multiple manifests (credential entry for Google/Meta/Vista/WAHA); reconciled across Wave 1.
- `credential_store.py` underpins all OAuth manifests (the Fernet vault → seed
  `noctusai_lib/security/token_store`, Wave 1.E7).
- `upload_*` + `videos_router` + `youtube_service` + `video_cache_service` are the YouTube
  upload/catalog surface (Wave 1.E6); not a standalone manifest — covered by the product port.

## Secrets — SKIPPED (never copied)

The originating workspace `secrets/` directory contained credential files. They were **NOT copied**
(rsync `--exclude='secrets'`); they are real Google OAuth client/service-account JSON and have no
place in-home. Verified post-copy: zero `.env`, `*secret*.json`, `client_secret*`,
`*credentials*.json`, or `gen-lang-client*` files exist anywhere under `reference/source/`. Only
`.env.example` template files were copied.
