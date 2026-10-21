# Contract — Page 0 "Agente": Julia, the lead-facing WhatsApp agent

> **Superseded in part (2026-10-19):** Julia v2 hosts Julia in the agents app and SW consumes her through the API only -- see `products/agents/projects/julia-v2/CONTRACT.md` (§8 API, §5 controls). Where this document describes the `contexto` content, `salvar_slots` / `definir_operacao` / `qualificar_lead`, the slot-criteria send rules or `agente_pausado` as a gate, the v2 contract wins.

Status: **v3 2026-10-14 — owner answered §9 (§11, binding). Precedence: §11 > §10 > §1–§9. Ready for dispatch.**
Owner decisions: `../DECISIONS.md` (round 3). Reuse inventory and page plan: `../BUILD-ROADMAP.md`.
Existing shapes quoted here were extracted from the tree on 2026-10-13 (file:line in brackets).

## 0. Shape in one paragraph
**Julia is an agent of the `agents` product** (a studio agent: versioned sections compiled into the
system prompt). She runs on a **new provider-neutral runtime** (OpenAI now, Anthropic later, chosen per
agent version). **social-wiring keeps the WhatsApp transport**. On an inbound message from a lead, SW
calls a **new product-to-product turn API** in agents with a product token. Agents runs the turn and
returns the reply parts and actions. SW sends the reply through WAHA. Everything tenant-specific (LLM key,
SW↔agents token, WhatsApp connection, persona, knowledge) is **per-org configuration**, so another client
can be onboarded by configuring it, without code changes. This is the reference implementation for
"product → agent" routing over API.

## 1. Slices and order
| Slice | Product | What | Depends |
| --- | --- | --- | --- |
| S0 | seed | `integrations.llm.chat_with_tools` — provider-neutral tool calling (openai + anthropic + fake). `LLMDispatcher` is rebased on it. | — |
| S1 | seed | Lift Agent Studio's pure compiler to `noctusai_lib.domain.agent_prompt` (`compile_prompt`, `prompt_hash`, `estimate_tokens`, `SectionData`/`SkillData`/`VersionBundle`/`CompileInput`/`CompiledPrompt`). agents re-imports it, with no behaviour change (its tests stay green). | — |
| A1 | agents | `LlmToolRuntime` (an `AgentRuntime` over S0); runtime selected per agent version; widened model allowlist; per-org LLM keys. | S0, S1 |
| A2 | agents | Channel conversations + the product turn API (§3) + the channel token mint (§4) + the `lead-imob` agent seed. | A1 |
| W1 | social-wiring | Routing on the shared WAHA path (§5) + `AgentsClient` Fake/Real/factory + per-chat pause. | A2 contract only (built against Fake) |
| W2 | social-wiring | Page **Lais › Agente** + the pause toggle in Conversas (§6). | W1 |
| X | both | One end-to-end check against real routes (§8). | all |

S0/S1 and W1 (on the Fake client) can run in parallel. A1 → A2 are sequential.

## 2. agents — runtime and model
- `AgentSpec` gains `provider: Literal["anthropic","openai"]` (default `"anthropic"` so Julia-academia is unchanged) [types.py:50].
- `agents.agent_versions` gains `provider text not null default 'anthropic'`. Widen the model CHECK and `MODELS` to a provider-keyed allowlist: anthropic = current 3 [stores/personas.py:43, studio_definitions.py:94, migration 015]; openai = `gpt-5`, `gpt-5-mini` (final names pinned at dispatch from the seed provider's model list).
- `agents.agents.runtime` CHECK gains `'llm'` [migration 006:73]. `get_agent_runtime` dispatches on it: `claude_sdk` → existing `ClaudeAgentSdkRuntime`, `llm` → `LlmToolRuntime`, no key → `FakeAgentRuntime` [__init__.py:90].
- `LlmToolRuntime.run_turn(spec, ctx, prompt, broker, slot)` yields the **same event vocabulary** as today: `message.new`, `tool.started`, `tool.finished`, final `session.status{status:"ociosa", custo_usd, tokens_entrada, tokens_saida, tokens_cache_leitura}` [claude_runtime.py:576-646]. Memory = the agents `messages` table of that conversation (last N turns + the compiled prompt). There is no SDK session.
- **Per-org LLM key.** The key is resolved by `resolve_credential(f"{provider}_api_key", org_id)` through `org_settings` (seed chain [config/credentials.py:146]). agents' anthropic-only override [resolver.py] stays for Julia-academia. Admins set the key in agents › Credenciais through the seed api-keys router (`/api-keys/{key}`, `POST …/test`) [noctusai_seed.api_keys_router]. **No process-wide OpenAI key is read for a lead turn.**
- Budget/usage: seed `integrations.llm` budget + `llm_usage` are applied per org.

## 3. agents — product turn API (new)
Router `channels_router.py`, prefix `/api/channels`. Auth: `require_scopes({"agents:channel-turn"}, restrict="product_only")` plus an issuer allowlist `{"social-wiring"}`, otherwise 403 `{"detail","code":"issuer_not_allowed"}` (same pattern as SW's bridge [agents_bridge_router.py:85-122]). Every call is scoped by `ctx.org_id`. There is no envelope (agents convention): errors are `HTTPException(detail={"detail": str, "code": str})` [conversations_router.py:124].

### 3.1 `POST /api/channels/turns` — run one turn for a channel conversation
Request (`extra="forbid"`):
```
{ "agent_key": "lead-imob",
  "channel": "whatsapp",
  "channel_ref": { "connection_id": UUID, "chat_id": str },      // conversation identity, unique per org+agent
  "contact": { "phone_e164": str|null, "display_name": str|null },
  "messages": [ { "texto": str (1..8000), "provider_message_id": str, "at": datetime } ]  // 1..20, debounced batch, oldest first
}
```
Response 200:
```
{ "conversation_id": UUID,
  "reply": { "partes": [str] },            // 0..n WhatsApp bubbles, in order; empty = stay silent
  "actions": [ { "type": "handoff", "motivo": str } ],   // page 0: only handoff; later pages add slot/lead/visit actions
  "status": "respondido" | "silencio" | "handoff",
  "usage": { "custo_usd": float|null, "tokens_entrada": int|null, "tokens_saida": int|null } }
```
Side effects + state after:
1. A conversation for (org, agent, channel, channel_ref) is created on first call, then reused. The `messages` rows are persisted (user batch + assistant reply). The provider_message_id is idempotent: replaying the same ids returns the stored reply and never runs a second turn.
2. The turn lock is the existing per-conversation lock [conversations.turn_lock_*]; a concurrent call gets 409.
3. Realtime events are published on the conversation scope (the agents UI can watch the turn).

Errors:
| Status | code | Cause | SW behaviour |
| --- | --- | --- | --- |
| 401 | — | bad or expired token | log + mark the connection's agent link "token inválido" in Lais › Agente; no reply sent |
| 403 | `product_required` / `scope_missing` / `issuer_not_allowed` | wrong token | same as 401 |
| 404 | `agent_not_found` | `agent_key` doesn't exist for this org | show it on the page; no reply |
| 409 | `agent_inactive` / `no_active_version` / `prompt_too_large` | agent not publishable/active | show it; no reply |
| 409 | `turn_in_progress` | concurrent turn | SW re-queues the batch once after 5 s |
| 422 | `invalid_field` | schema | bug → error log |
| 424 | `llm_not_configured` | no org key for the provider | show "chave do provedor ausente" |
| 429 | `capacidade` (+`Retry-After`) | slots full / org budget exhausted | re-queue after `Retry-After`, max 3 |
| 502 | `llm_upstream` | provider error after retries | no reply; log |
Timeout: SW waits at most 60 s.

### 3.2 `GET /api/channels/agents/{agent_key}/status`
Returns 200 `{ "agent_key", "nome", "ativo": bool, "versao_ativa": int|null, "provider": str|null, "model": str|null, "llm_configurado": bool }`. 404 `agent_not_found`. Same auth as 3.1. Used by SW to show the link health.

### 3.3 `agents.conversations` changes
Add `channel text null`, `channel_ref jsonb null`, `contact jsonb null`; make `owner_user_id` nullable when `channel is not null` (CHECK); add a unique partial index `(org_id, agent_id, channel, channel_ref)` where `channel is not null`. Channel conversations appear read-only in the agents UI (listed per agent, filterable by channel).

## 4. agents — the channel token (swappable per tenant)
- `POST /api/agents/{agent_key}/channel-token` — admin only (`require_admin`). Request `{ "product": "social-wiring", "label": str }`. Response 201 `{ "token": "pk_…", "expires_at": datetime, "scopes": ["agents:channel-turn"] }`. **The secret is shown once.** It is minted with `ProductTokenAdmin.mint("agents", org_id=ctx.org_id, scopes=("agents:channel-turn",), issuer="social-wiring", expires_at=+90d)` [token_admin.py]. Revocation goes through the existing api-tokens admin.
- The admin pastes the token into SW Lais › Agente. SW stores it per org in its credentials store as `api_key:agents` (Fernet) [SW services/api_keys_store.py]. Swapping tenants = mint for that org + paste; nothing global.
- Agents' base URL for SW = `resolve_product_url("agents")` (same resolver agents uses for SW).

## 5. social-wiring — routing on the shared WAHA path
New per-connection fields (migration in `social_wiring.whatsapp_connections`):
`agente_leads_ativo boolean not null default false`, `agente_leads_key text null` (default `'lead-imob'` when enabled).
New per-chat fields on `whatsapp_chats`: `agente_pausado boolean not null default false`, `agente_conversation_id uuid null`.

In `_process_waha_body` [whatsapp_router.py:492], **after** dedup, media→text and `message_store.record` (unchanged, 603-681), and **before** the bound-chat and authorized gates (810-850), the routing decision is:
1. `sender` ∈ `connection.authorized_numbers` → **operator path, unchanged** (bound gate → One Chat / intake, exactly as today).
2. otherwise, if `connection.agente_leads_ativo` → **lead path**:
   - chat `agente_pausado` → store only, no reply (a human is handling it);
   - otherwise → enqueue on the seed `ConversationBufferService` (same 8 s debounce, key `lead:<connection_id>:<chat_id>`). The worker calls `AgentsClient.run_turn(...)` (§3.1), sends `reply.partes` with `send_paragraphs` [whatsapp_outbound.py:37], records outbound messages, and stores `agente_conversation_id`. On `actions.handoff`: set `agente_pausado=true` + publish a realtime `chat.upsert` so Conversas shows "atendimento humano".
3. otherwise → today's behaviour (denial reply once per 24 h).

Safety rules (tested strictly):
- **Enabling `agente_leads_ativo` requires `authorized_numbers` to be non-empty.** When this was written an empty list meant "everyone is authorized", which would have sent every lead to the operator bot and its tools; since 2026-10-20 (owner) an empty list means nobody, silently. Otherwise: 409 `authorized_numbers_required`.
- The lead path never calls `ChatbotService` and never sees operator tools. The operator path never calls agents.
- Messages the number's owner sends from the phone (`from_me`) are recorded and never trigger a turn.
- Group chats (`@g.us`) never trigger a lead turn.

`AgentsClient` (SW `clients/agents.py`): Protocol `run_turn(req) -> TurnResult`, `agent_status(key) -> AgentStatus`; `FakeAgentsClient` (scripted replies) + `HttpAgentsClient(base_url, token, timeout=60)` + factory (token from `api_key:agents` per org; missing → Fake in dev, "não configurado" status in prod). This follows the seed Fake+Real+factory rule.

SW routes (new, `lais_agente_router.py`, prefix `/api/lais/agente`, member read / admin write, org-scoped, SW envelope convention):
- `GET  /` → `{ data: { conexoes: [{ connection_id, label, agente_leads_ativo, agente_leads_key, authorized_numbers_count }], token_configurado: bool, status_agente: AgentStatus|null, erro: str|null } }`
- `PUT  /conexoes/{connection_id}` body `{ agente_leads_ativo: bool, agente_leads_key: str|null }` → 200 updated row; 409 `authorized_numbers_required`; 404.
- `PUT  /token` body `{ token: str }` → 204 (validated by calling 3.2; 422 `token_invalido` if agents rejects it).
- `PATCH /api/whatsapp/connections/{id}/chats/{chat_id}/agente` body `{ pausado: bool }` → 200 `{ chat_id, agente_pausado }`.

## 6. social-wiring — UI
- **Lais › Agente** (`/lais/agente`, status_pagina `lais_agente`, nav entry in `LAIS_PAGES`):
  - token card (configured or not, paste/replace, link health from 3.2: agent name "Julia", active version, provider/model, LLM key present);
  - per-connection switch "Julia atende leads neste número", disabled with a reason when `authorized_numbers` is empty;
  - explanatory text: numbers in the list → One Chat; everyone else → Julia;
  - a link "Editar Julia no Agents" (persona, knowledge, test chat live in the agents product).
- **Lais › Conversas**: per-chat chip "Julia atendendo / Atendimento humano" + toggle (§5 PATCH). Handoff flips it automatically. Uses the seed ChatWindow header slot.
- All loading/empty/error states follow the two-signal loading rule.

## 7. agents — the `lead-imob` agent and the test chat
- `ensure_default_agents` seeds `lead-imob` (`nome="Julia"`, `runtime="llm"`, `owner_product="social-wiring"`, `ativo=false`) per org on first use. It is a studio agent. Version 1 is drafted with provider `openai`. Its sections come from `[private study: agent-brain]` (persona/greeting, always end with a question, ask "comprar ou alugar" first, partnerships → admin contact, never invent property data, hand off on request/complaint). The owner reviews it before publish.
- **Testar conversa**: the existing agents studio chat runs `lead-imob` on the same `LlmToolRuntime` (user conversation, not a channel one), so the persona can be tuned before switching the number on.
- Tools at page 0: `handoff(motivo)` only. Later pages add `salvar_slot`, `qualificar_lead`, `propor_visita`.

## 8. Tests and acceptance
- seed S0: each provider's tool-call mapping is tested against recorded fixtures; the fake provider is deterministic; `LLMDispatcher` tests are green.
- seed S1: agents' existing compiler tests pass unchanged against the lifted module.
- agents: 3.1 auth matrix with strict `== 401` (no `in (401, …)`); idempotent replay; turn lock 409; per-org key isolation (org B never uses org A's key); `claude_sdk` agents unchanged.
- SW: routing table (authorized → operator, others → lead, `from_me`/group → no turn, paused → no reply); 409 `authorized_numbers_required`; Fake client end to end; handoff pauses the chat.
- X: one real-route contract test in dev: SW `HttpAgentsClient` → agents `/api/channels/turns` with the fake provider, asserting the exact §3.1 response shape.
- Gates: predeploy for agents + social-wiring; LGPD intake (`noctus.dev.lgpd_flag`): lead conversations (retention, consent text in the greeting, deletion on request).

## 9. Open for the owner (answered 2026-10-14 → §11)
1. Same number as One Chat: every contact **not** in that connection's authorized list will be answered by Julia once the switch is on. That includes personal contacts on that number. OK, or should Julia only answer chats that start after the switch is turned on?
2. Julia's first-message wording (it should state it's a virtual assistant — LGPD/transparency).
3. Handoff target: who is notified when Julia hands off (SW notification to the connection's owner? a team?).

## 10. Review fold-in (v2, binding)

### 10.1 Security (H = blocks enabling Julia on any number)
- **H1 Signed webhooks only.** `agente_leads_ativo` can only be turned on when the connection has a webhook HMAC secret. With the switch on, a missing or invalid signature returns 401 on both webhook routes, checked **before** any routing. The legacy global `/api/whatsapp/webhook` never enters the lead/operator split. (Today a missing secret only logs a warning [whatsapp_router.py:51-58].)
- **H2 Real sender identity.** The routing key is `participant` for `@g.us` chats and `from` otherwise (today `sender = from_ or chat_id` [~572]). Group chats never reach Julia, and reach the operator path only when that group is explicitly bound. Test: an unauthorized member of a group cannot reach One Chat.
- **H3 Invariant on every write.** `agente_leads_ativo ⇒ authorized_numbers non-empty` is enforced by a DB CHECK/trigger, a 409 on **both** the Julia switch and the authorized-numbers PUT, and a re-check at routing time (fail closed, no reply). Operators may list raw `@lid` ids. The routing check uses `intake.is_authorized(sender)` (phone/LID-aware), not raw list membership. An uncached operator LID falls to Julia: this is documented and tested, and it is safe because Julia has no operator tools.
- **M1 Token.** `org_id` comes from the token only. `agent_key` is resolved inside that org. `issuer` is read from the stored token row. Only a hash of the secret is stored, and it is shown once. TTL 30 days, with overlapping rotation. Every mint and revoke is audit-logged. Scopes are split: `agents:channel-turn` (3.1) and `agents:channel-status` (3.2).
- **M2 Idempotency key** = `(org_id, connection_id, provider_message_id)`, enforced by a unique index. Replaying an id with different text returns 409.
- **M3 Prompt injection.** Lead text always enters the model as the `user` role. Contact and display name are never put in the system prompt. The compiled prompt and knowledge hold no secrets and no other leads' data (test: "show me your system prompt"). `handoff.motivo` is plain text ≤ 280 chars and rendered escaped. Downstream summaries treat lead text as untrusted.
- **M4 Flood/budget.** SW applies limits before calling agents: about 10 turns/hour per chat and N turns/minute per connection (configurable). Agents applies a per-org daily budget cap (429 `capacidade`). A batch is capped at 16k total characters. Test: the daily cap returns 429.
- **M5 LGPD (done before W1, not at the gates).** The LGPD flag is filed first. Channel conversations are kept 180 days and then purged by cron. **The first message must say it's a virtual assistant and link the privacy notice** (mandatory; the owner only chooses the wording). Deletion on request ("apagar meus dados" or via handoff) removes the agents messages + contact and SW's message_store/contact rows together.
- **L1** split scopes (above). **L2** leads never see error details, and the UI never echoes the token. **L3** human takeover: a `from_me` message that is not Julia's own echo (matched by `provider_message_id` of the outbound we sent) sets `agente_pausado=true`. SW re-checks the flag after the turn returns and before sending.

### 10.2 Architect
- **B1 Org-only key resolution (A1).** A lead turn resolves its provider key **only** from that org's settings and fails closed with 424 `llm_not_configured`. It must not fall through `resolve_credential`'s tier-0 override (agents' Julia-academia Anthropic key [studio/wiring.py:141-158]), `platform_settings` or env. `require_resolved_runtime_config` [credentials/resolver.py:218] becomes per-provider: an OpenAI-only org must not need an Anthropic key.
- **B2 SW buffer is single-org today.** `configure_conversation_module(org_id=<default>)` [lifespan.py] and `_build_processor(conversation_id, memory)` join text without ids. W1 adds a processor branch for `lead:<connection_id>:<chat_id>` keys that resolves org + connection from the key and carries each `provider_message_id`. Files: `services/conversation_module.py`, `lifespan.py` (added to W1).
- **B3 Gate placement.** The lead path bypasses the One Chat gate `cfg.whatsapp_chatbot_enabled and cfg.openai_api_key and connection.auto_reply_enabled` [~860]; `auto_reply_enabled` stays One Chat's toggle (driven by agents' bridge). The authorized check is `intake.is_authorized` (10.1 H3).
- **B4 `from_me` truth.** Today `from_me` returns early at ~578, before dedup and record. §5's "recorded" is wrong. W1 records `from_me` messages and applies L3 (auto-pause unless it's our own echo).
- **S0** stays (provider-neutral tool calling). `LlmToolRuntime` **composes the rebased `LLMDispatcher`** (no fourth tool loop). `OpenAIToolOrchestrator` and SW's `chatbot_service` loop [347-380] are rebased onto it as fix-on-contact. Gemini gets a `NOC-REMEDIATE` marker if tool calling isn't implemented for it. Decide sync vs async in S0's contract.
- **S1 is off page 0's critical path.** Page 0 keeps using agents' compiler in place. The lift happens separately and also updates `agent_package_build.py:622-646`'s loader + test.
- **§4 reuses existing minting.** The admin mints through the existing api-token admin path (seed `POST /api/settings/api-tokens` / agents' `credentials/service.py` ordering; scopes from the server-side registry) with `principal_agent_id = lead-imob` and `issuer="social-wiring"`. `mint(schema, *, org_id, label, scopes, expires_at, principal_agent_id, issuer, minted_by)`. SW's `api_keys_store` allowlist gains an `agents` spec. Mounting the seed `api_keys_router` in agents (for per-org LLM keys) is new A1 work.
- **Shapes.** `TurnContext.requested_by` is non-null: channel turns use a per-agent service principal (the `lead-imob` agent's principal id). `get_agent_runtime(settings)` gains `(agent, org_id)` (signature change, all call sites updated). Why `runtime='llm'` instead of reusing `'external'`: `external` means "another product runs this agent" (One Chat). `llm` means "agents runs it on the provider-neutral loop".
- **Numbers.** Next migrations: social-wiring **255**, agents **024** (re-check at dispatch with `noctus.dev.next_migration_number`). `/lais/agente` needs status_pagina `lais_agente` (pattern of 252, which is now applied in prod). A new seed tool-calling test dir must be covered by CI (`check_seed_test_root_ci_coverage`). Both products are ativo+live → full prod gates.
- **Sequencing with one-ops-agents.** That project is stale since 09-19. Its Phase B (`types.py`, `build_agent_spec`, registry) is superseded by A1. `/api/channels/turns` becomes Phase F's transport primitive. For leads we deliberately choose a synchronous hop (not F's cache variant): one inbound batch → one turn, 60 s budget. A note is added to `projects/one-ops-agents/PROJECT.md` at A1 dispatch.

### 10.3 Slice order (v2)
LGPD flag → S0 → A1 (B1, per-org keys, runtime dispatch) → A2 (turn API, M1/M2, mint reuse) ∥ W1 on the Fake (H1–H3, B2–B4, M4, L3) → W2 (UI) → X (real-route contract test) → owner tunes Julia in agents' test chat → switch on (owner).

## 11. Owner answers (v3, 2026-10-14, binding — wins over §1–§10)

### 11.1 Julia answers only chats that start after she is switched on
Owner: "only chats after her creation". Contacts that already had a chat on the number (personal contacts, One Chat users) are **never** sent to Julia.
- **Snapshot at switch-on.** `PUT /api/lais/agente/conexoes/{id}` with `agente_leads_ativo=true` first lists every chat of that WAHA session (`GET /api/{session}/chats`, paginated to the end) and stores each chat id in `social_wiring.lais_agente_chats_preexistentes (org_id, connection_id, chat_id, capturado_em)`, PK `(connection_id, chat_id)`. Both the `@c.us`/`@s.whatsapp.net` and the `@lid` form are stored when WAHA exposes both. Then it sets `agente_leads_ativo=true` and `agente_leads_ativado_em=now()`. **If the listing fails or is incomplete, the switch stays off** and the call returns 502 `snapshot_falhou` (fail closed). Snapshot + flag are one transaction.
- **Eligibility at routing time** (lead path, §5 step 2): a chat reaches Julia only if (a) it is not in the snapshot table, **and** (b) SW's `whatsapp_chats` row for it did not exist before `agente_leads_ativado_em` (a row created earlier ⇒ not eligible, even if the snapshot missed it). Otherwise the message keeps today's behaviour (stored; operator/denial path as today) and **never** calls agents. A chat Julia already owns (`agente_conversation_id` set) stays eligible.
- **Switch off → on again:** a new snapshot is taken; chats Julia already owns stay hers; every other existing chat is excluded.
- Tests: pre-existing chat → no turn; new chat → turn; snapshot failure → 502 + switch still off; pre-existing `@lid` alias of a snapshotted phone chat → no turn.

### 11.2 Privacy notice page — slice P (built now, owner refines the text later)
Owner: "create a page for it, don't propose, just create". The notice belongs to the **org (the controller, e.g. One Consultoria)**, not to NoctusAI, so it is per-org and swappable.
- **Data (SW):** `social_wiring.lais_aviso_privacidade (org_id pk, slug text unique not null, titulo text, empresa_nome text, contato_email text null, contato_whatsapp text null, secoes jsonb not null, mensagem_inicial text not null, versao int not null default 1, atualizado_em timestamptz, atualizado_por uuid)`. `secoes` uses the seed consent shape (`DocSection[]`: `{n, title, blocks:[{p}|{ul}]}`). On first read, a row is created from a **default pt-BR template** (controller = org name; what is collected — name, phone, messages, property preferences; purpose — answer and qualify real-estate enquiries and pass them to a human broker; legal basis — art. 7º V/IX LGPD; processors — WhatsApp/WAHA host, the AI provider (OpenAI), NoctusAI as operator; retention 180 days; rights of the data subject (art. 18) and how to exercise them — reply "apagar meus dados" or the contact email; no automated decision with legal effect; updates). Placeholders are filled from org data; anything unknown shows "a definir" and the Lais › Agente page warns that the notice is incomplete.
- **Public read:** `GET /api/public/lais/privacidade/{slug}` — no auth, rate-limited, returns only the notice fields (never org ids, users or settings). 404 for an unknown slug. Response `{ data: { titulo, empresa_nome, contato_email, contato_whatsapp, secoes, versao, atualizado_em } }`.
- **Admin:** `GET /api/lais/agente/aviso` (member read) and `PUT /api/lais/agente/aviso` (admin, core org role owner/admin) with `{ titulo, empresa_nome, contato_email, contato_whatsapp, secoes, mensagem_inicial }` → 200 row, `versao += 1`. `slug` is generated once from the org name (unique, URL-safe) and is not editable at page 0.
- **Public page (SW SPA, outside auth):** `/privacidade/:slug`, rendered with the seed `ConsentDocLayout` through a **new named seam**: `ConsentDocLayout` gains an optional `brand` prop (`{ name, homeHref? }`, default = NoctusAI mark) so the org name replaces the NoctusAI header. No local re-declaration of the seed consent pages (`check_consent_routes_mounted`). Loading/empty/error states per the two-signal rule; 404 shows "Aviso não encontrado".
- **Editing UI:** a "Aviso de privacidade" card on Lais › Agente (W2) — form for the fields + a link to the public page. Until W2 ships, the default template is what is served.
- **Promotion:** a per-org public privacy notice is likely needed by other products (store, igig). Built in SW now consuming the seed layout seam; `NOC-REMEDIATE[seed-promotion]` marker on the router names the destination (seed `org_privacy_notice`) at the second consumer.

### 11.3 First message (disclosure) — deterministic, not left to the model
- On the **first turn of a channel conversation** (SW has no `agente_conversation_id` for the chat yet), SW sends `mensagem_inicial` **as its own bubble before** Julia's reply. Default template (owner refines on the Agente page): `Oi! Eu sou a Julia, assistente virtual da {empresa}. 😊 Como tratamos seus dados: {link}` where `{link}` = `<SW public base URL>/privacidade/<slug>`. `{empresa}`/`{link}` are filled by SW; `{link}` is mandatory — `PUT …/aviso` rejects a `mensagem_inicial` without `{link}` (422 `link_obrigatorio`), and the Julia switch refuses to turn on while the notice has no `empresa_nome` (409 `aviso_incompleto`).
- The `lead-imob` prompt states that the introduction was already sent, so Julia does not introduce herself again and goes straight to the question ("comprar ou alugar?").
- Test: first turn → disclosure bubble then reply bubbles, in that order; later turns → no disclosure.

### 11.4 Handoff notification target
Owner: "the connection's owner for now, swappable for an admin. never a member-only directly, nor corretores (for now) nor devs, nor jurídico."
- New per-connection field `agente_handoff_notificar_user_id uuid null`. Null ⇒ notify the connection's owner (`whatsapp_connections.user_id`, the creator).
- When set, the target must hold core org role **owner or admin** in that org (checked with the core role lookup used by `require_org_admin_role`); member, corretor, dev, jurídico or any other role → 422 `destinatario_invalido`. Set via `PUT /api/lais/agente/conexoes/{id}` (admin) with `agente_handoff_notificar_user_id`.
- **Re-checked at send time**: if the configured user is no longer owner/admin (or left the org), the notification goes to the connection owner and an error is logged. The connection owner is always allowed.
- Channel: seed in-app notification (`write_in_app`, type `lais_handoff`) with the chat name, the `motivo` (escaped, ≤ 280 chars) and a deep link to `/lais/conversas?chat=<chat_id>`. Never sent to the lead; never to a team broadcast at page 0.
- Tests: default → connection owner; admin target → that admin; member/corretor target → 422; demoted admin → falls back to owner.

### 11.5 Slice order (v3)
LGPD flag (done with this commit) → **S0 ∥ P** → A1 → **A2 ∥ W1** (Fake; includes 11.1, 11.3, 11.4) → W2 (incl. the notice card + handoff target select) → X → owner tunes Julia → owner switches on.
New migrations (re-check with `noctus.dev.next_migration_number`): SW 255 (connection/chat fields of §5 + 11.1 + 11.4, snapshot table), SW 256 (notice table, slice P — P may take 255 if it lands first; the number tool decides). P adds no status_pagina (public route).

## Lead opt-out (owner decision 2026-10-21)

When a lead asks to stop, agents records a lead-level opt-out (event: who, why, the lead's words), ends every agent's participation and notifies the org admins in-app. SW's side of the contract:

- `POST /api/channels/leads/{ref}/opt-out` takes `origem` (`agente`|`operador`|`integracao`, default `integracao`), `motivo` (<=500), `mensagem_lead` (<=1000), `ator_user_id`; the response carries `evento_id`. SW never sends a second notification for the same event.
- A turn action `encerrar` with `motivo: "lead_pediu_parar"` and/or `lead_opt_out: true` means agents ALREADY recorded it: SW does not call opt-out again; it bumps `gen` + `encerrado_at` (every queued follow-up goes stale) and writes the timeline event `lead_opt_out`.
- Every SW send to a lead that does not pass through an agents turn (regua template, Meta first contact, Google review ask, disparo target, visit notice) re-reads agents' consent state (`GET /api/channels/leads/{ref}/consentimento`, lead-level, no thread needed) and refuses, recording an `envio_bloqueado` event (`motivo` `lead_opt_out`). A lead agents has never seen (404 `lead_desconhecido`) has never opted out and passes (debug log); any other failure refuses (`opt_out_nao_verificavel`). Turn-based sends are refused by agents itself (`status: lead_opt_out`).
- The consent read is `GET /api/channels/leads/{ref}/consentimento` -> `{lead_ref, opt_in_em, opt_in_origem, opt_out_em, opt_out_ativo, opt_out_evento}` (same token auth as the opt-out POST); `AgentsClient.consentimento` returns `None` on `lead_desconhecido`.
- SW has no operator "stop contacting this lead" action for leads (only the proprietario `opt-out` in `julia_cloud_router`, which is a different registry); nothing in SW calls `AgentsClient.opt_out` today.
