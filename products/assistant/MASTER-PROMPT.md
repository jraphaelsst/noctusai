# Assistant — MASTER-PROMPT

> Authoritative development guide for the Assistant product (read-only WhatsApp shadow line, D46).

## Purpose

The Assistant reads ONE personal WhatsApp line and never writes to it. Inbound 1:1 text becomes a pending intake row;
S3 classifies it as about scheduling or not (classification only, D48: no reply, no draft, no send). Plan and council ledger: `project-history/assistant-chatbot/`
(`phase0-d46-shadow-line.md` § 6 wins). Owner decision: a small, simple noc product called Assistant.

## Hard rules

- **Zero writes, three layers.** Edge deny proxy (devops, S6) · this product mounts no send/mark-read/backfill/chat-read
  routes (`whatsapp_router.py`, pinned by `test_whatsapp_shadow.py`) · the seed `WahaClient` refuses writes for a
  `send: disabled` line. Never add a code path that sends; never construct a raw `WahaClient(`.
- **Webhook HMAC is required.** `create_whatsapp_inbox_router(webhook_only=True, require_webhook_hmac=True)`; no secret
  => 401 to everything and a deploy refuses to boot (`required_prod_config`).
- **Webhook base = the line's edge relay.** The WAHA core is on a private network; the seed client accepts `set_webhook`
  only under the policy's `webhook_relay`. `webhook_base_url()` returns that relay when the policy declares one, the
  public product URL otherwise (dev/Fake). Never register the public URL on the shadow line.
- **Input contract before storage:** `inbound_one_to_one_only(excluded)` then `assistant.append_intake`: dedup on the
  WAHA message id, forward-only from `paired_at`, text only. Third parties are an HMAC'd `chat_ref`, never a phone.
  Never log a phone, chat id or body.
- **Intake + event = one transaction.** The only writers are `assistant.append_intake` / `assistant.set_intake_outcome`
  (SECURITY DEFINER, service role); the outcome enum is `pending|classified|failed|skipped_budget|skipped_excluded|skipped`.
  Only `skipped` / `skipped_excluded` clear the body and are terminal (017 redefines `set_intake_outcome`): a budget
  outage never destroys data -- `skipped_budget` keeps the text until `retain_until` and a replay can classify it.
  `intake_messages_eventos` is append-only (GUC carve-out `assistant.retention_purge` for the retention job only).
- **Classifier (S3):** prompt + model only from the registry row `assistant.classificador_agendamento`; the model sees
  the message TEXT and nothing else; strict parse, never a guess; budget refused/unverifiable => `skipped_budget`;
  one `ai_outputs` row per (message, prompt_version, model); runs on the seed jobs Worker only (poll-budget line in
  `shadow/worker.py`); no live LLM call in tests.
- **Evaluation (S4):** the owner labels BLIND on `/avaliacao` (text only, never the verdict); labels are append-only
  `assistant.ai_feedback_events` events (seed template `ai_feedback_events_table_sql`; relabel = next `rodada`);
  `shadow/avaliacao.py` turns `resumo_rotulos` into agreement (`nao_sei` outside the denominator). Contract:
  `project-history/assistant-chatbot/s4-contrato-avaliacao.md`. The page shows third-party text: keep the notice, never log it.
- **Google connection (S7, D50):** the org admin connects Google in `/configuracoes/google`. `connect/start` mints a
  server-bound single-use `state` (SHA-256 stored, 10 min, bound to org/user AND to the starting browser via the host-only
  cookie `__Host-ast_goauth`, carries the PKCE verifier Fernet-encrypted in `oauth_states`); the signed `GET /api/google/oauth/callback` consumes it (unknown/replayed/expired => 400), exchanges
  the code and writes the grant to `oauth_credentials` (seed CredentialStore, one row per org). No route returns a token.
  Scopes are least privilege: openid, userinfo.email, calendar.events, drive.readonly, drive.file (no Gmail, no full
  calendar/drive); incremental auth is off. `disconnect` revokes at Google then deletes; a dead refresh token is the
  state `needs_reconnection`, not a 500. `prova` lists 5 events + 5 Drive file names; no live Google call in tests.
- **Access tiers:** every table `tier:org`, service-role only, no browser grant; every route admin-gated or the signed
  webhook.

## Layout

```
backend/app/
  main.py                 create_product_app + line policy registration + required_prod_config
  config.py               ASSISTANT_* settings (all empty by default, fail loud)
  routers/whatsapp_router.py   connections (admin) + webhook-only inbox
  routers/classificacao_router.py   admin replay + blind stratified sample
  routers/google_router.py   Conectar Google (admin) + the signed OAuth callback
  services/google_connection.py   scopes, stores, provider, status, Google clients (seed factories)
  shadow/classificador.py  registry call + strict parse
  shadow/avaliacao.py     agreement math (verdict x owner label)
  shadow/worker.py        seed jobs Worker handlers, replay enqueue, start/stop
  services/intake.py      IntakeChatStore (the seam the seed ingest writes into) + chat_ref HMAC
  services/pairing.py     paired_at stamp/clear from WAHA session.status
backend/migrations/       001-011 seed spine · 014/016 nav rows · 015 intake (connections, intake, events, writers) · 017 classifier (jobs, ai_outputs, enqueue trigger, record/sample RPCs) · 019 Google connection (oauth_credentials, oauth_states)
frontend/src/pages/       Conexao (seed WhatsAppConnectionsPage organ), Dashboard, Equipe, Configuracoes (+ the Google tab)
```

## Not here (later slices)

S4 labelling page (+ append-only labels), S5 LGPD artefacts + retention job,
S6 probe/personal line instances (devops). Owner-gated: pairing the personal number, the ToS risk acceptance.
