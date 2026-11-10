# Assistant

A small, simple noc product: a **read-only shadow of one personal WhatsApp line**. It pairs the line (QR), receives
inbound 1:1 text messages through a signed webhook, appends each as a pending **intake** row and classifies it as
about scheduling or not (S3, classification only - D48). It never sends, drafts, marks as read or shows presence.

## Stack

- **Backend**: FastAPI via `create_product_app()` (port 8021), schema `assistant`.
- **Frontend**: `createProductApp()` + the seed `WhatsAppConnectionsPage` organ (port 8250), pt-BR.
- **Catalog**: `deploy_scope = 'dev'` (core migration 119). Prod exposure is the owner's decision.

## What is mounted

- `/api/whatsapp/connections*` (admin) - QR pairing, status, start/restart/logout/recover.
- `POST /api/whatsapp/webhook/{token}` - the inbound webhook. **HMAC required**: no `ASSISTANT_WAHA_WEBHOOK_HMAC_SECRET`
  means every call is a 401 and a deploy refuses to boot.
- `POST /api/classificacao/replay` (admin) - re-classify chosen rows under the registry's current prompt/model
  (new `ai_outputs` rows only).
- `GET /api/classificacao/amostra` (admin) - stratified sample for labelling; `modo=cego` (default) hides the
  model's verdict and skips messages the caller already labelled.
- `POST /api/classificacao/rotulos` (admin) - one owner label (`agendamento|nao_agendamento|nao_sei`, `rodada`) as an
  append-only event (`ai_feedback_events`, migration 018); a relabel is a new `rodada`, never an update.
- `GET /api/classificacao/rotulos/progresso` and `.../rotulos/concordancia` (admin) - own progress; model verdict vs
  owner label as counts (the only place the verdict is shown). UI: page `/avaliacao` (blind, keyboard 1/2/3).
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

## Classifier (S3, migration 017)

An insert of a `pending` intake row enqueues `assistant.classificar_intake` (trigger, same transaction) and wakes the
in-process seed jobs `Worker` (idle backoff 1 s to 30 s). The worker sends the message TEXT only to the registry row
`assistant.classificador_agendamento` (`chamar_ia`, Haiku 5.5), parses `{is_scheduling, confidence, reason_code}`
strictly and writes it with `assistant.record_classification` into `ai_outputs` - one row per (message,
prompt_version, model). Budget refused or unverifiable => `skipped_budget` (text KEPT until `retain_until`; the replay
route can classify it later); invalid output => `failed`. The worker does
not start without an enforced `LLM_SPEND_LIMITS` entry (rows stay `pending`). Definition:
`project-history/assistant-chatbot/s3-definicao-agendamento.md`.

## Config

`ENCRYPTION_KEY`, `ASSISTANT_WAHA_BASE_URL`, `ASSISTANT_WAHA_SESSION`, `ASSISTANT_WAHA_LINE_POLICY`,
`ASSISTANT_WAHA_WEBHOOK_HMAC_SECRET`, `ASSISTANT_IDENTITY_HMAC_KEY`, `ASSISTANT_EXCLUDED_NUMBERS`,
`ASSISTANT_CLASSIFIER_ENABLED`, `ASSISTANT_CLASSIFIER_MAX_CHARS`, `LLM_SPEND_LIMITS` (enforced entry required),
`NOCTUS_SCHEDULERS_ENABLED`.

## Running

```bash
uvicorn app.main:app --reload --port 8021 --app-dir products/assistant/backend
cd products/assistant/frontend && npm run dev
```
