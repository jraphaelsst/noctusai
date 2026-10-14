# Contract — Page 0 "Agente": Julia, the lead-facing WhatsApp agent

Status: **DRAFT 2026-10-13 — waiting for the owner's OK, then architect + security review, then dispatch.**
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
- **Enabling `agente_leads_ativo` requires `authorized_numbers` to be non-empty.** Today an empty list means "everyone is authorized" [whatsapp_connection_store.py:73-92], which would send every lead to the operator bot and its tools. Otherwise: 409 `authorized_numbers_required`.
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
- `ensure_default_agents` seeds `lead-imob` (`nome="Julia"`, `runtime="llm"`, `owner_product="social-wiring"`, `ativo=false`) per org on first use. It is a studio agent. Version 1 is drafted with provider `openai`. Its sections come from `../analysis/agent-brain.md` (persona/greeting, always end with a question, ask "comprar ou alugar" first, partnerships → admin contact, never invent property data, hand off on request/complaint). The owner reviews it before publish.
- **Testar conversa**: the existing agents studio chat runs `lead-imob` on the same `LlmToolRuntime` (user conversation, not a channel one), so the persona can be tuned before switching the number on.
- Tools at page 0: `handoff(motivo)` only. Later pages add `salvar_slot`, `qualificar_lead`, `propor_visita`.

## 8. Tests and acceptance
- seed S0: each provider's tool-call mapping is tested against recorded fixtures; the fake provider is deterministic; `LLMDispatcher` tests are green.
- seed S1: agents' existing compiler tests pass unchanged against the lifted module.
- agents: 3.1 auth matrix with strict `== 401` (no `in (401, …)`); idempotent replay; turn lock 409; per-org key isolation (org B never uses org A's key); `claude_sdk` agents unchanged.
- SW: routing table (authorized → operator, others → lead, `from_me`/group → no turn, paused → no reply); 409 `authorized_numbers_required`; Fake client end to end; handoff pauses the chat.
- X: one real-route contract test in dev: SW `HttpAgentsClient` → agents `/api/channels/turns` with the fake provider, asserting the exact §3.1 response shape.
- Gates: predeploy for agents + social-wiring; LGPD intake (`noctus.dev.lgpd_flag`): lead conversations (retention, consent text in the greeting, deletion on request).

## 9. Open for the owner
1. Same number as One Chat: every contact **not** in that connection's authorized list will be answered by Julia once the switch is on. That includes personal contacts on that number. OK, or should Julia only answer chats that start after the switch is turned on?
2. Julia's first-message wording (it should state it's a virtual assistant — LGPD/transparency).
3. Handoff target: who is notified when Julia hands off (SW notification to the connection's owner? a team?).
