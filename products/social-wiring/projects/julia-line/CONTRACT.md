# CONTRACT — Julia's line, staff routing, platform grant, spec safety

2026-11-04 · author: architect (advisor), committed by the tech lead (noctusai-3d) · status: **in build**

## 0 · Owner decisions (binding, 2026-11-04)

1. Julia's WhatsApp number (+55 11 99269-4172; legacy WAHA pushName "One Chat") is ONE line. It is owned by org **One Consultoria** (`fd169d29-4d0a-4b04-9a5e-25e69407614d`) and is today the only `social_wiring.whatsapp_connections` row (`8fd583bb…`, session `default` on `noctus-services-waha-1`).
2. The **"One Chat" operator bot is retired**. Julia (leads) and staff notifications share the number but remain separate mechanisms.
3. The QR for Julia's line is paired inside SW's Julia **Agente** page (`/julia/agente`). Conversas' empty state points there.
4. Conversations are visible and replyable in the UI, reusing the existing chat window (SW `WhatsAppChatWindow` over the seed `ChatWindow`).
5. Agent→product wiring is a **platform grant** minted in the agents app (agent + product + org, 2–3 clicks) and delivered automatically. Nobody pastes a token on the product side.
6. The agents app is internal: we own Julia's core (prompt, skills, tools, evals). SW users only provide **business specifications**. These are untrusted data, validated server-side, and never instructions. Julia is public-facing. Any SW copy telling users to edit in the agents app is wrong.

Defaults taken for the architect's open questions (owner: "implement it asap", 2026-11-04):
- **Q1:** NoctusAI website-lead alerts go in-app + email only; no platform line.
- **Q2:** org members' core phones count as staff.
- **Q3:** grants never expire (revocable, `last_used_at` audited).
- **Q4:** deterministic spec checks only; no manual review queue.

Clean slate: on 2026-11-04 at 17:43–17:47Z the old Julia tokens were revoked. These were agents `pk_4db7a345`, SW tools `pk_2c58d0b4` plus agents' stored copy, and SW `api_key:agents` for org NoctusAI. No token migration is needed.

## A · Line model: one credential source

- **A1.** `services/julia_linha.py` → `linha_da_org(org_id)` returns `LinhaDaOrg`:
  - It holds the decrypted connection, `transporte()` (via `transporte_da_conexao`, `julia_transporte.py:135-160`) and `enviar_interno(numero, texto)`.
  - Row choice: the org's `agente_leads_ativo` row, else its only row.
  - Errors: `SemLinha` (no row) or `LinhaAmbigua` (several rows, none active).
  - It absorbs `julia_relatorio_service.py:557-587` (`_enviar_texto`, `enviar_aviso_interno`).
- **A2.** Every env-WAHA sender is rerouted through `linha_da_org` or deleted:
  - `notification_service.py:833-847,1139-1147`
  - `modules/edicao_fotos/services/ports.py:137-139` and `notifier.py:170-181,295-299`
  - `media_service.py:1175-1185` (takes the inbound connection's record)
  - `settings_router.py:438-550` (status/test send read the org's line)
  - `whatsapp_intake_service.py:278-299,939-942` and `chat_router.py:122-124` (web chat gets no WAHA)
  - `whatsapp_router.py:332-335` and the legacy `/webhook` at `:1340` are deleted.
- **A3.** The env stays ONLY for provisioning in `whatsapp_connections_router.py:384-396` (`waha_base_url`, `waha_api_key`).
  - Delete `waha_session`, `whatsapp_authorized_numbers` and `whatsapp_chatbot_enabled` from `config.py`.
  - New AST guard `tests/test_no_env_waha_sender.py`.
  - The env Fake never sends in a deploy context.
- **A4.** A context with no line refuses loudly, per channel:
  - SW: a `sem_linha` failure row in `notification_log` plus at most one in-app notice per org admin per day. Email and in-app continue. There is no fallback to the env or to another org's line.
  - Core `website_lead_fanout.py:49-71,120-124` and `config.py:111-113`: delete the WhatsApp leg and core's `waha_*` settings. If `website_sales_whatsapp` is still set, record `sem_linha_da_plataforma`.

## B · Routing on one number

- **B1.** Staff = active `julia_staff` rows ∪ phones of active members of the line-owning org (`noctus_users.telefone` via seed `resolve_user_phones`, `table_reads.py:189`). One function, `classificar_remetente`, replaces `whatsapp_router.py:595-661`. Staff messages are stored, never sent to Julia, and admins get a notice (`:664-690`). The operator branch (`:1165-1169`) is removed.
- **B2.** Migration SW-A adds:
  - `conversation_messages.origem` CHECK `(lead|julia|humano|interno)`;
  - `whatsapp_chats.categoria` CHECK `(lead|equipe)`.

  Behaviour:
  - `InternoSender` (`julia_relatorio_service.py:459-475`) writes its outbound row itself with `origem='interno'`, so the WAHA echo is deduplicated by the `provider_message_id` UNIQUE constraint. This replaces the 1-hour Redis key (`julia_agente_service.py:684-692`).
  - `_apply_human_takeover` (`whatsapp_router.py:694-708`) skips `interno`.
  - `avaliar_elegibilidade` (`julia_agente_service.py:590`) refuses `equipe`.
  - The inbox shows an "Equipe" badge.
- **B3.** One Chat code is deleted (not flagged):
  - `whatsapp_router.py`: `:1145-1153`, `:1187-1313`, `:1130-1137`, `:908-912`, `:705-708`, `:1340-1383`.
  - The intake builder `:254-371` is replaced by a slim inbound helper built from the connection record.
  - Delete the `julia_staff_service.py:155-192` mirror and the `julia_agente_router.py:293` `exigir_autorizados` call.
  - SW-A drops CHECK `whatsapp_connections_agente_exige_autorizados` (`258:91-101`).
  - SW-B, run only after the code is deployed, drops `authorized_numbers`, `auto_reply_enabled` and `bound_chats`.
  - The One Chat toggle bridge token (`social_wiring.api_tokens` "agents One Chat bridge", scopes `social-wiring:one-chat:*`) and agents' `agents_router.py:94` bridge are removed in the same slice.

## C · SW frontend

- **C1. "WhatsApp da Julia" card on `/julia/agente`.**
  - It reuses a seed `ConnectionPairingPanel` extracted from seed `ConnectionDetailDialog.tsx:77-140` and driven by `createWhatsAppConnectionsHooks`. Do NOT reuse SW's own `components/ConnectionDetailDialog.tsx`.
  - With no line, "Criar linha" POSTs to `/api/whatsapp/connections` and then shows the QR.
  - Logout needs a confirm (it stops Julia and the notifications). Admin-only.
- **C2.** The `WhatsAppWorkspace.tsx:100-117` and `RoteamentoCard.tsx:108` empty-state links point to `/julia/agente#whatsapp`.
- **C3. Copy fixes.**
  - **Delete:** `ConfigurarNoAgentes.tsx` (+ `Agente.tsx:45`), `MovidoParaAgentes.tsx`, and the `agentsUrl` helper (`useJuliaRoteamento.ts:72-74`).
  - **Redirect to `/julia/agente`:** `pages/julia/Perguntas.tsx` and `Conhecimento.tsx`.
  - **Rewrite:**
    - `AgentsLinkCard.tsx:39` becomes a read-only grant status.
    - `useJuliaAgente.ts:66` becomes "ainda não conectada pela plataforma".
    - Also `EnvioWizard.tsx:115,120`, `useJuliaConversaEstado.ts:58`, `JuliaThreadHeader.tsx:100` and `Agente.tsx:5,42`.
  - **Remove the One Chat UI:** `ConnectionDetailDialog.tsx:226-254,717-750,881`, `WhatsAppChatWindow.tsx:150-177` and `MarcaModal.tsx:1140`.
  - **Backend:** drop `agents_url` (`julia_agente_router.py:262-264`). The `ApiKeySpec` "agents" entry (`api_keys_store.py:417-434`) becomes read-only ("gerenciado pela plataforma").
  - **Guard:** an FE test fails on "app de agentes" under `pages/julia` and `components/julia`.
- **C4. Business-specs editor.**
  - `EspecificacoesCard` renders agents' spec declarations generically.
  - The SW proxy `GET/PUT /api/julia/especificacoes` (org admin) calls agents `GET/PUT /api/channels/agents/{key}/specs` with the grant token and passes the actor id.
  - **S9 built:** `GET|PUT /api/julia/especificacoes` (org admin) passes agents' 200/422 bodies verbatim; 409 `agente_nao_conectado` without the `api_key:agents` credential. Agents side: `GET|PUT /api/channels/agents/{key}/specs` (`channel_specs_router`, scope `agents:channel-specs`), sharing `aplicar_org_specs` with the studio PUT. Actor (owner 2026-11-04): the proxy fills `ator {user_id, nome, email}` from the authenticated SW session (never the client body, which is `valores` only) and agents' channel PUT requires it (422 `ator_obrigatorio`), product-attested by the channel token; agents stores `updated_by`/`updated_by_nome`/`updated_by_token` (agents migration 062) and audits token + person; `valores[].updated_by_nome` feeds "alterado por X em Y". `julia_aviso_service` is untouched (the notice URL stays SW-derived and read-only; no S9 change was needed).
  - `aviso_privacidade_url` is SW-derived (`julia_agente_router.py:117`) and read-only in the form.

### C · implementation record (S10a, 2026-11-04)

Frontend, `products/social-wiring/frontend/src`:

- **C1** `components/julia/WhatsAppJuliaCard.tsx` (`id="whatsapp"`): seed `ConnectionPairingPanel` inside a `ConfirmProvider`, bound by `hooks/useJuliaLinhaWhatsapp.ts` (`createWhatsAppConnectionsHooks(api)`). The line is `roteamento.linhas[0]`; "Criar linha" (seed `CreateConnectionDialog`, admin) only while there is none; link to `/julia/conversas`. No "add another connection".
- **C2** the Conversas and Roteamento empty states already point at `/julia/agente#whatsapp` (S10b).
- **C3** `AgentsLinkCard` is now "Conexão com a plataforma" (read-only). `agents_url` / `urlConfigurarJulia` / the paste-token mutation are gone; `useJuliaAgente` messages never name the agents app; the guard also scans `hooks/useJulia*` and forbids "One Chat". One Chat copy removed from the Equipe role text. `JuliaLigadaCard` no longer gates on `numeros_autorizados`.
- **Platform connection** `components/julia/ConexaoPlataforma.tsx`: status badge, masked token (no input, `select-none`), times, pt-BR help per status/motivo, "Testar conexão" -> `POST /api/julia/agente/conexao-plataforma/verificar`, answer written into the `["sw","julia","agente"]` cache. Configurações: `ApiKeyStatus.read_only` renders `ManagedReadOnlyRow` (the `agents` key = the same card; any other read-only key = masked hint, no input).
- **C4** `components/julia/EspecificacoesCard.tsx` + `hooks/useJuliaEspecificacoes.ts`: fields per `tipo` from the declarations (rotulo / descricao / exemplo), PUT sends EVERY declared key (blank clears), `aviso_privacidade_url` read-only, draft flagged "não salvas" until the server accepts, 422 `violacoes` per field (draft kept), report-mode `invalidas` per field, 409 `agente_nao_conectado` -> link to `#conexao-plataforma`, 502/503 named.

Reconciled with S9: the SW proxy passes agents' bodies through bare; a 422's `code`/`violacoes` sit under `detail`; each value carries `updated_by` / `updated_by_nome` ("Alterado por <nome> em <data>"). Dead `useSetAutoReply` and `auto_reply_enabled`/`authorized_numbers` in the connection hooks/types go with S12.

## D · Platform grant (clean slate)

- **D1.** Agents migration AG-B creates `agents.agent_product_grants`:
  - columns: `id`, `org_id` (target), `agent_id` (org instance via `ensure_instancia`), `product` (registry), `status` (`ativo|revogado|falhou`), `channel_token_id`, `product_token_id`, `expires_at` (NULL = no expiry), `created_by`, `revoked_by`, `revoked_at`, `last_delivered_at`, `last_error`;
  - one active grant per (org, agent, product).

  Tokens reuse `api_tokens` unchanged.
- **D2. Minting.** `require_platform_admin` (`dependencies.py:320`). The flow is agent → product → org → confirm, and agents:
  1. Mints the **channel token** into `agents.api_tokens` for the TARGET org: `issuer='social-wiring'`, scopes `agents:channel-turn`, `agents:channel-status` and `agents:channel-specs` (same as `channel_token_router.py:77-125`).
  2. Mints the **tools token** into `social_wiring.api_tokens` via seed `ProductTokenAdmin` (`token_admin.py:1-25`): issuer `agents`, `TOOLS_TOKEN_*` (`julia_contexto_service.py:62-66`). Agents keeps the secret in its tools-token store (`channel_tools_token_router.py:39`).
  3. Mints a one-shot delivery token (scope `platform:grant-receive`, 5-minute TTL).
  4. Calls SW `PUT /api/platform/grants/agents`, which writes `api_key:agents`. SW's read path (`julia_agente_service.py:165-177`) is unchanged.
  5. Revokes the delivery token.

  If any step fails, every token from that attempt is revoked and the grant becomes `falhou`. Secrets come only from seed `mint_token_secret`, so they follow the `noc_` prefix once it lands.
- **D3. Seed (S1).**
  - A `GrantDelivery` sender: Protocol + Fake + Real (HTTP via `resolve_product_url`) + factory.
  - `noctusai_seed/platform_grants_router.py`: a receiver factory. The org comes from the token, never the body; only issuer `agents` is accepted.
- **D4.**
  - **Rotate** = mint + deliver the new pair, then revoke the old pair.
  - **Revoke** = revoke both, then a best-effort DELETE to the product. The product then sees 401 and shows "desconectada".
  - **Scopes** come only from server-side registries (`dependencies.py:229-238`).
- **D5.**
  - `PUT /api/julia/agente/token` (`julia_agente_router.py:338-382`) returns 410 for one release, then is deleted along with `_entregar_token_ferramentas` (`:401-433`).
  - Agents' paste UI (`ChannelTokenCard.tsx`, `ChannelsTab.tsx:89`) and `PUT /ferramentas-token` are deleted.
- **D6.** The M2M token rework is folded into this project (handed over by noctusai-86, 2026-11-04; no code existed). Owner decisions:
  - A new `service_accounts` table plus an `api_tokens.service_account_id` FK ("noc-agent", for automation; not Julia).
  - MFA is required to mint, and there is a rotate endpoint.
  - A no-expiry option, with revocation and `last_used_at` kept.
  - Scopes come from a server-side allow-list.
  - The resolver factory refuses the Fake in deploy (`auth_router.py:395` silent fallback).
  - **Every token becomes `noc_`, and `pk_` is REFUSED afterwards.** Sequence: (1) the resolver accepts both; (2) all live tokens are reissued as `noc_`, starting with the grants; (3) the `pk_` cutoff ships last.
  - The token card moves into `@noctusai/lib` (masked first 4 + last 4, with delete).
  - The SW Configurações "Token do agente (agents)" paste card (`api_keys_store.py:423`) is removed, leaving one entry point (D5).

  The `pk_` sites are mapped in the security audit: seed `token_admin.py:68`, `api_tokens.py:162`, `dep.py:110,164`, `_reasons.py:25-26`, plus the tests. Stripe `pk_` sites are NOT ours. Core then mounts the seed auth router, a single `get_auth_context` and the audit middleware.

## E · Spec safety (in agents, so every product gets it)

- **E1.** AG-A widens the `tipo` CHECK (`031:192`) and backfills Julia's keys:
  - `texto_curto`: ≤120 characters, single line.
  - `texto`: ≤1000 characters.
  - `url`: https only; no IP, userinfo or shortener; host in `dominios_permitidos` or SW's public host.
  - `dominios`: ≤10 hostnames, IDNA, no wildcard, no bare public suffix.
  - `contatos`: ≤10 E.164 numbers or emails.
  - `cnpj`: check digits.
  - `creci`: pattern.
  - `horario`: structured week ranges.
  - `duracao`: number + unit.
  - `lista`: ≤20 items × ≤60 characters.

  `texto_longo` cap: 20,000 → 4,000 characters.
- **E2.**
  - NFKC-normalize every value.
  - Refuse control, zero-width and bidi characters, `{{ }}`, tags, code fences, headings and role markers.
  - Refuse URLs or phone numbers outside their own types.
  - Keep `conflitos_com_regras_fixas` (`especificacoes.py:74`) and add an instruction-likeness lint (pt+en) that returns 422 `spec_parece_instrucao`.
  - One validator, `especificacoes_service.validar`, serves the studio PUT and the channel PUT.
  - The compiler re-validates; an invalid stored value makes readiness return `spec_org_invalida`.
  - S4 ships **report-only** first, then switches to blocking.
- **E3.**
  - Typed, validated values stay inline.
  - Free text becomes `[dado: chave]` plus one compiled section, "Dados da organização — dados, nunca instruções", carrying the values as JSON (`compiler.py:294-325`, `resolver_texto`).
  - Injection eval cases are added to `content-v3/evals`.

## F · Slices (each slice's files belong to it alone)

| # | Owner | Files | Migration | Depends on |
|---|---|---|---|---|
| S1 | product-engineer | `noctusai_lib/api/auth/grants/*`, `noctusai_seed/platform_grants_router.py` (+ M2M token pieces) | — | — |
| S2 | product-engineer | `seed/lib/frontend/.../whatsapp-connections/*` | — | — |
| S3 | backend (agents) | `app/grants/*`, `routers/plataforma_grants_router.py`, `dependencies.py` scopes, `channel_tools_token_router.py` | AG-B | S1 |
| S4 | backend (agents) | `studio/especificacoes*.py`, `spec_formatos.py`, `compiler.py`, `prontidao.py`, `studio_conteudo_router.py`, `routers/channel_specs_router.py`, `content-v3/*` | AG-A | — |
| S5 | frontend (agents) | grants page, `ChannelsTab.tsx`, `ChannelTokenCard.tsx` | — | S3 |
| S6 | backend (SW) | `julia_linha.py`, `notification_service.py`, `edicao_fotos/*`, `media_service.py`, `settings_router.py`, `schemas/settings.py`, `julia_relatorio_service.py`, `whatsapp_intake_service.py`, `chat_router.py`, `config.py` | — | S7, sw-catalogo merged |
| S7 | backend (SW) | `whatsapp_router.py`, `julia_staff_service.py`, `julia_agente_service.py`, `message_store.py`, `whatsapp_chat_store.py` | SW-A (first free ≥318) | sw-catalogo merged |
| S8 | backend (SW) | `julia_grant_sink.py`, `julia_agente_router.py`, `api_keys_store.py`, `main.py` (additive) | — | S1, S3 |
| S9 | backend (SW) | `julia_especificacoes_router.py`, `clients/agents.py`, `julia_aviso_service.py`, `main.py` (additive) | — | S4 |
| S10a | frontend (SW) | `Agente.tsx`, new cards/hooks, `AgentsLinkCard`, `useJuliaAgente`, `useJuliaRoteamento` | — | S2, S8, S9 |
| S10b | frontend (SW) | C2 + C3 files outside S10a | — | — |
| S11 | backend (core) | `website_lead_fanout.py`, `config.py` | — | — |
| S12 | backend (SW) | column drops + dead helpers | SW-B | S6–S8 deployed |

Collisions: `feat/julia-v3-sw-catalogo` touches `whatsapp_router.py`, `settings_router.py`, `chat_router.py`, `config.py` and `main.py`, and claims SW 314/316/317. `feat/nosnolimiar-rename` claims core 098. Agents migrations start after 058.

**Waves:**
- W1 = S1, S2, S4 (report-only), S10b, S11.
- W2 = S3, S7.
- W3 = S5, S6, S8.
- W4 = S9, S10a.
- W5 = grant for One Consultoria, verify, turn Julia on, then S12.

**Tests:**
- Strict `== 401` for unsigned or no-token calls; 403 for wrong scope or issuer.
- A failed delivery revokes all minted tokens; revoking a grant leaves SW `desconectada`.
- `sem_linha` produces a log row and an in-app notice; the AST guard passes.
- A staff or member number never reaches agents; an internal echo is not a takeover even with Redis down.
- Julia can be turned on with no authorized numbers.
- An injection/unicode corpus passes, and free text only ever appears inside the fence.
- QR polling is covered; the copy guard is in place.

**Docs:**
- `INTEGRATIONS/whatsapp.md`: §6, §7, a new §8 "linha da org", and §4d.
- A new `PATTERNS/backend/platform-grants.md` plus `INDEX.md` and `04-SHARED-LIBRARY.md`.
- `julia-v2/CONTRACT.md`: §0.3 Q4, §12.5, the org-specs section, and the removal of One Chat mentions.
- SW and agents READMEs.

## G · Risks

- The connection row's `api_key` must work against `noctus-services-waha-1` before S6 deploys (predeploy probe).
- Blocking spec validation may stop Julia because of existing values, hence report-only first.
- If `pk_` acceptance is dropped before the grants are rotated, Julia's tokens die.
- Retiring the bot also ends the WhatsApp YouTube-upload intake flow.
