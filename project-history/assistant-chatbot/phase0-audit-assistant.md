# Assistant product — Phase 0 audit (2026-11-09)

Read-only audit for slice 1 (spec doc decisions D35–D39: WAHA-first, Google via the existing env trio, store only the self-chat). Evidence paths are relative to the repo root at `feat/assistant-chatbot` 34505217a.

## What the seed ships (consume)
- **WAHA line + QR:** `create_whatsapp_connections_router` (`seed/framework/backend/noctusai_seed/whatsapp_connections_router.py`), FE `WhatsAppConnectionsPage` (`seed/lib/frontend/src/components/whatsapp-connections/`). Monica mounts both in `products/monica/backend/app/routers/whatsapp_router.py:29-34`.
- **Inbox + webhook:** `create_whatsapp_inbox_router` (`seed/framework/backend/noctusai_seed/whatsapp_inbox_router.py:150`), webhook `POST /api/whatsapp/webhook/{token}` (`:399-439`) → `ingest_waha_event` (`seed/lib/backend/noctusai_lib/integrations/whatsapp/inbox/ingest.py:255`). Stores and table DDL helpers in `.../whatsapp/{connection_store.py,inbox/store.py,inbox/ddl.py}`.
- **Google:**
  - Calendar: Protocol + Fake + OAuth + service-account adapters and the factory `get_calendar_adapter` (`.../google_calendar/__init__.py:51`).
  - Drive: `RealDriveReader` and `make_drive_reader` (`real_reader.py:118`, `reader_factory.py:17`). It exports Sheets to CSV and Docs/Slides to text (`real_reader.py:12-15,64-68`).
  - Gmail: `make_gmail_client` (`gmail/factory.py:28`).
  - All three can be built from the env trio; `mcp/noctusai/tools/noctus/dev/notify.py:118-128` already does this for Gmail.
- **Settings:** env `ProductSettings` (`seed/framework/backend/noctusai_seed/config.py:15`). Identity is org + user; per-org credentials go through `CredentialStore` (`seed/lib/backend/noctusai_lib/security/token_store/types.py:45`).

## Gaps (seed-build candidates, each through a named seam)
1. **No chat filter before storage.** Ingest stores everything except `@broadcast` and `@newsletter` (`ingest.py:71,310-313`). `on_message` fires only after the message is stored (`:325`). The seam point is named at `whatsapp_inbox_router.py:419-420`. D38 needs a pre-store predicate seam on the seed ingest; consumer #1 is assistant, and Monica's default stays "store all".
2. **No own-id on the connection.** There is no WAHA `get_me` call in `client.py` and no own-id field on the connection record, so the self-chat (`fromMe` and `chatId == me`, possibly arriving as `@lid`) cannot be identified yet. This is a seed client and store addition.
3. **No env-trio Calendar resolver.** A small `CalendarCredentialResolver` is needed. Product-side for now; it becomes a seed resolver if a second consumer appears.
4. **No WhatsApp→LLM reply loop.** The agents runtime (`products/agents/backend/app/runtime/llm_runtime.py:130,145`) has turn limiting but no inbound WhatsApp entry.
5. **No single-owner or "personal product" concept and no generic settings table.** D39 requires the person, line and Google account to be set explicitly on the branch. This is a learning input for noc's identity model.
