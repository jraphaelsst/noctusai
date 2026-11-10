# Assistant

A small, simple noc product: a **read-only shadow of one personal WhatsApp line**. It pairs the line (QR), receives
inbound 1:1 text messages through a signed webhook and appends each as a pending **intake** row for a later slice (S3)
to classify for scheduling intent. It never sends, marks as read or shows presence.

## Stack

- **Backend**: FastAPI via `create_product_app()` (port 8021), schema `assistant`.
- **Frontend**: `createProductApp()` + the seed `WhatsAppConnectionsPage` organ (port 8250), pt-BR.
- **Catalog**: `deploy_scope = 'dev'` (core migration 119). Prod exposure is the owner's decision.

## What is mounted

- `/api/whatsapp/connections*` (admin) - QR pairing, status, start/restart/logout/recover.
- `POST /api/whatsapp/webhook/{token}` - the inbound webhook. **HMAC required**: no `ASSISTANT_WAHA_WEBHOOK_HMAC_SECRET`
  means every call is a 401 and a deploy refuses to boot.
- Nothing else: no send, mark-read, backfill, chat or message reads, SSE.

## Input contract (before anything is stored)

Inbound only (no `from_me`, no API-sourced), 1:1 only (no groups / status / broadcast), minus
`ASSISTANT_EXCLUDED_NUMBERS`; then `assistant.append_intake` dedups on the WAHA message id, keeps text only (media
without text is `skipped`), and is forward-only from the connection's `paired_at` (stamped when WAHA reports
`WORKING`). The third party is stored as an HMAC'd `chat_ref` (`ASSISTANT_IDENTITY_HMAC_KEY`), never a phone.

## Data (migration 015)

`whatsapp_connections` (+ `paired_at`), `intake_messages` (outcome enum, `retain_until` = 90 days) and the append-only
`intake_messages_eventos` (one row per outcome change, same transaction, via `append_intake` / `set_intake_outcome`).
All tables are service-role only.

## Config

`ENCRYPTION_KEY`, `ASSISTANT_WAHA_BASE_URL`, `ASSISTANT_WAHA_SESSION`, `ASSISTANT_WAHA_LINE_POLICY`,
`ASSISTANT_WAHA_WEBHOOK_HMAC_SECRET`, `ASSISTANT_IDENTITY_HMAC_KEY`, `ASSISTANT_EXCLUDED_NUMBERS`.

## Running

```bash
uvicorn app.main:app --reload --port 8021 --app-dir products/assistant/backend
cd products/assistant/frontend && npm run dev
```
