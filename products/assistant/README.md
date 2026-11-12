# Assistant

A small, simple noc product around **one personal WhatsApp line**. It pairs the line (QR), receives inbound 1:1 text
messages through a signed webhook, appends each as a pending **intake** row and classifies it as about scheduling or
not (S3, classification only - D48). Since 2026-11-12 it can also **answer** (live reply, below): the owner's assistant
agent, hosted in the `agents` product, replies on the same line. It never marks as read, shows typing or presence.

## Stack

- **Backend**: FastAPI via `create_product_app()` (port 8021), schema `assistant`.
- **Frontend**: `createProductApp()` + the seed `WhatsAppConnectionsPage` organ (port 8250), pt-BR.
- **Catalog**: `deploy_scope = 'dev'` (core migration 119). Prod exposure is the owner's decision.

## What is mounted

- `/api/whatsapp/connections*` (admin) - QR pairing, status, start/restart/logout/recover.
- `POST /api/whatsapp/webhook/{token}` - the inbound webhook. **HMAC required**: no `ASSISTANT_WAHA_WEBHOOK_HMAC_SECRET`
  means every call is a 401 and a deploy refuses to boot.
  The line is the owner's personal live line (`send: enabled`, no edge, no `webhook_relay`): WAHA posts DIRECT to the
  product URL (`webhook_base_url`, pinned by `test_webhook_relay_base.py`).
- `POST /api/classificacao/replay` (admin) - re-classify chosen rows under the registry's current prompt/model
  (new `ai_outputs` rows only).
- `GET /api/classificacao/amostra` (admin) - stratified sample for labelling; `modo=cego` (default) hides the
  model's verdict and skips messages the caller already labelled.
- `POST /api/classificacao/rotulos` (admin) - one owner label (`agendamento|nao_agendamento|nao_sei`, `rodada`) as an
  append-only event (`ai_feedback_events`, migration 018); a relabel is a new `rodada`, never an update.
- `GET /api/classificacao/rotulos/progresso` and `.../rotulos/concordancia` (admin) - own progress; model verdict vs
  owner label as counts (the only place the verdict is shown). UI: page `/avaliacao` (blind, keyboard 1/2/3).
- `POST /api/google/connect/start`, `GET /api/google/status`, `POST /api/google/disconnect`, `GET /api/google/prova`
  (admin) - the in-app "Conectar Google" (S7, D50); `GET /api/google/oauth/callback` - the signed redirect target.
- Nothing else: no send route, mark-read, backfill, chat or message reads, SSE (the only sender is the live reply,
  an internal path of the webhook, below).

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

## Live reply (owner decision 2026-11-12, migration 021)

**Off by default** (`ASSISTANT_REPLY_ENABLED=false`): the product only shadows. When on, each admitted inbound text (the
intake contract above, 1:1 only, never a group/status/broadcast, never pre-pairing history) is handed - after the intake
row is committed, scheduled in the background so the webhook still acks WAHA at once - to `app.live.resposta.LiveReplier`:

1. **Turn**: `AgentsClient.run_turn` (seed `noctusai_lib.integrations.agents_channel`, same shape as social-wiring's lead
   path; `agent_key` = `ASSISTANT_AGENT_KEY`, conversation key = the HMAC'd `chat_ref`, the number rides only in the
   request's `contact.phone_e164` so `agents` can match its own list). `agents` decides on/off and the allow-list: a
   not-served status (`agente_desligado`, `restrito_avaliacao`, limits...) means NO reply and never an error to the
   contact; a typed client error means no reply + a log + an event.
2. **Send-seam guard** (defence in depth, independent of the turn): before any send it re-reads the agent's on/off +
   allow-list from `agents` (`app/live/controles.py`, ONE adapter: `CAMPO_LISTA = "contatos_permitidos"`, parsed by the seed `ControleInfo`/`AgentStatus`; absent = unreadable = closed). Off, or a non-empty list that
   does not name this number, refuses; **unreadable (error / field absent) refuses - fail closed**. **Empty list = every
   number allowed.** The allow-list and the agent on/off live in `agents` (owner-edited there), not here.
3. **Send**: one WhatsApp message per paragraph through the seed WAHA client under the line policy (`send: enabled`),
   `ASSISTANT_REPLY_PARAGRAPH_DELAY_SECONDS` apart; no mark-read / typing / presence. A partial delivery is recorded, never
   blindly retried.
4. **Event**: every attempt appends ONE immutable event to `assistant.respostas_eventos` (migration 021, tier:service,
   INSERT-only, `UNIQUE (intake_id)`): `enviada | enviada_parcial | recusada_lista | agente_desligado |
   controle_indisponivel | sem_atendimento | erro_turno | erro_envio | mensagem_antiga`, a reason code and counts. No phone
   number, message text or reply text is stored. Silent no-ops (switch off, group, history) write nothing.

Boot refuses (`LiveReplyConfigError`) when the switch is on and any of `ASSISTANT_AGENT_KEY`, `ASSISTANT_AGENTS_BASE_URL`,
`ASSISTANT_AGENTS_TOKEN`, the WAHA base URL / line policy (must be `send: enabled`), the identity key or `ENCRYPTION_KEY` is
missing. A missing agents token never falls back to a Fake. Messages older than `ASSISTANT_REPLY_MAX_AGE_SECONDS` (900)
are not answered. Debounce: a conversation must be quiet for `ASSISTANT_REPLY_DEBOUNCE_SECONDS` (4 s) and its whole burst becomes ONE turn and ONE reply (one event per message, same outcome, `dados.lote`); one turn at a time per conversation (in-process lock). The attempt's event is written after the send, so a crash mid-reply can leave no row (`NOC-REMEDIATE[assistant-reply-claim-before-send]`).

## Google connection (S7, migration 019)

Settings tab `/configuracoes/google` (admin): Conectar / Desconectar, the connected account, the granted scopes and a
"Testar conexao" proof (next 5 calendar events + 5 most recent Drive files, names only; each half fails on its own).

- **Flow**: `connect/start` mints a server-bound single-use `state` (10 min, SHA-256 stored, bound to the org/user AND to the
  starting browser through the host-only cookie `__Host-ast_goauth` (Secure, HttpOnly, SameSite=Lax, Max-Age=600; the
  callback must present it, else 400 and the state is burned), one flow in flight per user, 10/min on `connect/start`,
  carries the PKCE verifier Fernet-encrypted in `assistant.oauth_states`) and returns the consent URL; Google redirects the browser
  to the callback, which consumes the state (unknown / replayed / expired / other-provider => 400), exchanges the code
  with the verifier and writes the grant to `assistant.oauth_credentials` (seed `CredentialStore`, Fernet at rest, one
  row per org). No route ever returns a token. The callback re-checks the starter is still an org admin; a reconnect revokes the previous refresh token; a persist failure
  revokes the new grant. Every connect/disconnect/reconnect_needed is an append-only row of `google_conexao_eventos`
  (trigger, same transaction). `disconnect` revokes at Google, then deletes (an unreachable Google still
  deletes locally and answers `revoked: false`). A dead refresh token flags `needs_reconnection` instead of a 500.
- **Scopes (least privilege)**: `openid`, `userinfo.email`, `calendar.events`, `drive.readonly`, `drive.file`. No Gmail,
  no full `calendar`, no full `drive`. Incremental auth is off, so the token carries exactly these.
- **Google Cloud Console** (the NoctusAI project, D39; OAuth consent screen -> Scopes must list the five above; OAuth
  client -> Authorised redirect URIs):
  - prod: `https://assistant.noctusai.com/api/google/oauth/callback`
  - local dev (only if used): `http://localhost:8250/api/google/oauth/callback` (+ `GOOGLE_OAUTH_REDIRECT_URI` to match)
- **Deploy needs** (assistant container env): `GOOGLE_OAUTH_CLIENT_ID`, `GOOGLE_OAUTH_CLIENT_SECRET` (the app identity,
  shared by every org - the only Google values in env), `ENCRYPTION_KEY` (already required). The redirect URI is derived
  from the product URL (`PRODUCT_URL_ASSISTANT` / registry). Missing any => the routes answer 503, never a Fake.

## Config

`ENCRYPTION_KEY`, `ASSISTANT_WAHA_BASE_URL`, `ASSISTANT_WAHA_SESSION`, `ASSISTANT_WAHA_LINE_POLICY`,
`ASSISTANT_WAHA_WEBHOOK_HMAC_SECRET`, `ASSISTANT_IDENTITY_HMAC_KEY`, `ASSISTANT_EXCLUDED_NUMBERS`,
`GOOGLE_OAUTH_CLIENT_ID`, `GOOGLE_OAUTH_CLIENT_SECRET`, `GOOGLE_OAUTH_REDIRECT_URI` (optional), `ASSISTANT_CLASSIFIER_ENABLED`, `ASSISTANT_CLASSIFIER_MAX_CHARS`, `LLM_SPEND_LIMITS` (enforced entry required),
`NOCTUS_SCHEDULERS_ENABLED`; live reply: `ASSISTANT_REPLY_ENABLED` (kill switch, default off), `ASSISTANT_AGENT_KEY`,
`ASSISTANT_AGENTS_BASE_URL`, `ASSISTANT_AGENTS_TOKEN`, `ASSISTANT_REPLY_MAX_AGE_SECONDS`, `ASSISTANT_REPLY_PARAGRAPH_DELAY_SECONDS`, `ASSISTANT_REPLY_DEBOUNCE_SECONDS`, `ASSISTANT_OWNER_NUMBERS` (optional; comma-separated E.164 of the owner's other phones: a message from one reaches agents as `remetente=dono`, every other sender as `contato`; empty = nobody is the owner; never logged).

## Running

```bash
uvicorn app.main:app --reload --port 8021 --app-dir products/assistant/backend
cd products/assistant/frontend && npm run dev
```
