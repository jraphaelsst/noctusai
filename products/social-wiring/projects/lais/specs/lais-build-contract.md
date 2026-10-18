# Contract — Lais full rebuild ("go all the way"), waves F + 1–13

Status: **v1 2026-10-15 — owner: "i approve, go on and start the work all the way until done, fully copied".**
Precedence: this file > `sw-reconstruction-map.md` > `BUILD-ROADMAP.md` for anything built after page 0.
Page 0 (Julia, routing, privacy notice) stays governed by `julia-agent-contract.md` v3; this file only EXTENDS it additively.
Field sources: `page-map-v2.md` (§59.0/§59.0b live passes), `mechanisms.md`, `../analysis/bubble-app-definition.md` §4, `../analysis/agent-brain.md` §2–§7.
Existing-code claims cite `path:line` as read on `origin/dev` 82e72b494 (2026-10-15).

---

## 0 · Binding architecture

| # | Rule | Why |
| --- | --- | --- |
| A1 | **SW is the source of truth for every Lais datum.** Per-org tables in schema `social_wiring`, prefix `lais_`. agents stores only the conversation transcript + usage (as today). | Owner 2026-10-15 #5: "sw storage, then Julia consumes it". Lets another client be onboarded by config. |
| A2 | **Per turn, SW sends `contexto`** in `POST /api/channels/turns` (additive field, `extra="forbid"` stays). agents appends it as a dynamic system section after the compiled prompt. | Knowledge/slots change without republishing the agent version. |
| A3 | **Read tools are callbacks:** agents → SW `POST /api/lais/ferramentas/{nome}` with a product token SW mints for agents (scope `social-wiring:lais-tools`, issuer `agents`, per org). | Property data lives in SW (Vista mirror, scheduling). |
| A4 | **Writes are actions** returned in the turn response, applied by SW after the turn, idempotent per batch. agents exposes them to the model as "action tools" whose tool result is always `{"registrado": true}`. | One writer for SW data (SW); agents never writes SW tables. |
| A5 | **Summaries/extraction run in agents** (`POST /api/channels/conversations/{id}/resumo`) so the per-org LLM key never leaves agents. SW calls it when an episode closes. | Contract v3 rule: no process-wide LLM key; keys per org in agents. |
| A6 | **Transport stays WAHA.** Cloud-API-only features are built behind SW's sending seam with a `CloudApiTransport` (Fake + Real + factory). Until the owner verifies the Meta app they show "Aguardando verificação da Meta" and never dispatch. **WAHA free text is never used for mass sends** (number-ban risk). | Owner 2026-10-15 #2. |
| A7 | **History link = login + ownership.** A conversation opens only for its owner (assigned attendant, else connection owner) or an org owner/admin; other members 403; other orgs 404. No shared 4-digit code anywhere. | Owner 2026-10-15 #3. |
| A8 | Lais naming: module label stays the single constant `LAIS_LABEL` (`frontend/src/nav/lais.ts:19`); every new page = one `LAIS_PAGES` entry + a `status_pagina` row + one `App.tsx` route (`nav/lais.ts:9-12`). | Rename later = one string. |
| A9 | **Every automatic Julia send passes ONE outbound gate** (`app/services/lais_envio_gate.py`): gate 1 = `whatsapp_connections.agente_leads_ativo` re-read at send time; gate 2 = the org's opt-in for that flow (`resposta` none · tiers `minutos_ativo`/`horas_ativo` · `regua` the régua `ativa` · `primeiro_contato` an approved first-contact modelo · `avaliacao` `google_review_url`), all default off. A refusal raises `EnvioBloqueado` + event `envio_bloqueado` (never a silent skip). A new sender CALLS `exigir`, or takes the `Liberacao` (sealed: only `exigir` can build one) and calls `conferir` on it. Keeper scope = every `lais_*.py` plus every module that imports a `lais_*` service; the send vocabulary is derived from the seed WhatsApp clients, the `Transporte` Protocol, the intake seam and `whatsapp_outbound`. Boundary: the OPERATOR bot (intake + chatbot in `whatsapp_router` / `conversation_module`) is not Julia and is listed as an exception with `NOC-REMEDIATE[sw-operator-bot-allow-all]` (empty `authorized_numbers` = everyone); every other exception is an operator click, listed with its reason. The worker that sends on its own starts only with `NOCTUS_SCHEDULERS_ENABLED` (deployed container). Keeper: `tests/services/test_lais_envio_gate_keeper.py`. | Owner 2026-10-18: enforced by construction, not re-audited before every ship. |

### 0.1 Conventions every slice follows (verified)
- **SW success envelope** `{"data": …}` (`backend/app/routers/lais_agente_router.py:113,119,253`). **SW error** = `AppException(code, message, status_code)` → `{"error":{"code","message","details?"}}` (`seed/lib/backend/noctusai_lib/primitives/exceptions.py:24,175-189,196-202`). Request models subclass `StrictHttpModel` (unknown fields → 422) (`lais_agente_router.py:26,62`).
- **SW auth**: member read = `Depends(get_current_user_org)`; admin write = `require_org_admin_for` (`lais_agente_router.py:27,218`). Org from `coerce_org_uuid(auth[2])`.
- **agents envelope**: bare body; errors `HTTPException(detail={"detail","code"})` (`agents/backend/app/routers/channels_router.py:115`).
- **RLS**: every `lais_*` table `ENABLE ROW LEVEL SECURITY` + `select_own_org` policy `org_id = (SELECT public.current_org_id_for('social_wiring'))` + `service_role` policy (pattern `migrations/255_lais_aviso_privacidade.sql:37-48`, `258_lais_agente_roteamento.sql:73-84`). Writes go through the backend service client only.
- **status_pagina rows** copy the status of `whatsapp_chat` (pattern `migrations/259_status_pagina_lais_agente.sql`).
- **Timers** use the seed job queue (`noctusai_lib.domain.jobs`, `JobRepository.enqueue(..., scheduled_for, dedupe_key)` `seed/lib/backend/noctusai_lib/domain/jobs/repo.py:165-182`). **There is no cancel**: every Lais job re-reads state at fire time and no-ops when stale (the "stale guard", §0.2).
- **In-app notifications** via `noctusai_lib.domain.notifications.write_in_app` (`seed/lib/backend/noctusai_lib/domain/notifications.py:84`), as page 0 handoff already does (`backend/app/services/lais_agente_service.py:335`).
- **FE**: two-signal loading (`showSkeleton = isPending && !data`, `isRefreshing = isFetching && !!data`); consume seed organs before writing components: `ResourceManager` (lists/CRUD), `kanban`, `ConfirmProvider`, `team`, `notifications.ts`, `realtime.ts`, `whatsapp-connections` (`seed/lib/frontend/src/components/*`, `src/*.ts`). Run `noc-organ-consume-check` per FE slice.
- **Migrations**: numbers are claimed at dispatch with `noctus.dev.next_migration_number product_slug=social-wiring` (today: SW next = **267**, agents next = **029**). The numbers below are the planned order for round 1; later waves claim theirs when dispatched.

### 0.2 The stale guard (all Lais jobs)
Every job payload carries `{org_id, chat_key, gen}` where `gen` = `lais_contatos.gen` at enqueue time. `gen` increments on every inbound lead message, every `encerrar`, every pause/handoff. A job whose `gen` ≠ current `gen` completes as `obsoleto` without side effects. This is how "cancel on inbound" and "never after encerrar" are enforced without a queue cancel.

---

## 1 · Dependency graph and rounds

```
F (foundation) ──┬── 1 Conhecimento ──────────────┐
                 ├── 2 Perguntas ── 3 Envio ───────┼── 9 Painel ── 10 Relatórios
                 ├── 4 Reengajamento ──────────────┤
                 ├── 5 Visitas ────────────────────┤
                 ├── 6 Notificações ── 8 Captação  │
                 ├── 2 ── 7 Conversas v2 ── 11 Distribuição
                 └── 12 Cloud-API pages (needs Meta verification to DISPATCH, not to build)
13 Avaliações + Análise de crédito + CAPI  (after 3, 5, 12)
```

| Round | Slices in parallel | Gate to start |
| --- | --- | --- |
| R1 | F-AG, F-SW (file-disjoint: agents vs SW) | — |
| R2 | 1-BE, 1-FE, 2-BE, 2-FE, 4-BE, 4-FE, 5-BE, 5-FE | F on dev |
| R3 | 3-BE, 3-FE, 6-BE, 6-FE, 7-BE, 7-FE, 12-BE, 12-FE | 2 on dev (3, 7); F (6, 12) |
| R4 | 8, 9, 10, 11 (BE+FE each) | 3, 4, 6, 7 on dev |
| R5 | 13 | 3, 5, 12 |

Shared append zones (one line per slice, integrate serially, rebase conflicts are trivial): `frontend/src/nav/lais.ts` (`LAIS_PAGES`), `frontend/src/App.tsx` (route table near `:53-55`), `backend/app/main.py` router includes, `backend/app/services/lais_contexto_service.py` provider list (F creates it).

---

## 2 · Wave F — Foundation (contexto, actions, tools, episodes, events)

### 2.1 agents (slice F-AG; migration agents **029**)
Files: `app/schemas/channels.py`, `app/channels/tools.py`, `app/routers/channels_router.py`, `app/runtime/llm_runtime.py` (system assembly only), `app/clients/social_wiring.py`, new `app/routers/channel_tools_token_router.py`, `migrations/029_channel_contexto.sql`, tests.

**(a) `ChannelTurnRequest.contexto`** (additive, optional; absent = page-0 behaviour) — extends `app/schemas/channels.py:75-90`:
```
contexto: {
  hash: str (64 hex),                       // SW-computed sha256 of the rest of contexto
  conhecimento_md: str (0..60000),          // rendered by SW (wave 1)
  perguntas: [ { chave: str, label: str, dica: str|null, categoria: str,
                 qualificatoria: bool, operacao: "compra"|"aluguel"|null } ] (0..8),
  estado: { slots: {chave: str}, operacao: "compra"|"aluguel"|"administracao"|null,
            interacao_id: UUID, encerrado: bool },
  ferramentas: [ "buscar_imoveis"|"detalhes_imovel"|"horarios_visita"|"consultar_empreendimento" ],
  acoes: [ "salvar_slots"|"definir_operacao"|"qualificar_lead"|"pedido_visita"|"captacao"|"encerrar"|"handoff" ],
  agora: datetime, fuso: "America/Sao_Paulo"
} | null
```
`extra="forbid"` at every level. Size cap: whole `contexto` ≤ 80 000 chars → 422 `contexto_grande`.

**(b) Prompt assembly.** `llm_runtime.py:310` builds `[system(spec.prompt_append), *history]`. With contexto: a second system message `## Contexto da imobiliária\n{conhecimento_md}\n\n## Perguntas essenciais\n…\n\n## Estado do atendimento\n…` (deterministic render, tested by golden file). `usage` and the stored assistant row stamp gain `contexto_hash`.

**(c) Tools.** `make_channel_tools_factory` (`app/channels/tools.py:98-115`) today exposes only `handoff` (`:32-37`). It becomes: `handoff` (unchanged) + the action tools listed in `contexto.acoes` + the read tools listed in `contexto.ferramentas`.
- **Action tools** (no SW call during the turn): handler validates args, appends to the turn's action collector (generalise `HandoffCollector` `:72-96` to `ActionCollector`), returns `{"registrado": true}`. Schemas:
  | tool | args |
  | --- | --- |
  | `salvar_slots` | `{slots: {chave: valor≤500}}` (keys must be in `contexto.perguntas[].chave` or `nome`/`email`) |
  | `definir_operacao` | `{operacao: compra|aluguel|administracao|atualizacao}` |
  | `qualificar_lead` | `{motivo: str≤300}` |
  | `pedido_visita` | `{codigo_imovel: str|null, inicio: datetime, fim: datetime, cpf: str|null}` |
  | `captacao` | `{descricao: str≤1000, endereco: str|null, operacao: venda|aluguel|null}` |
  | `encerrar` | `{motivo: lead_encerrou|sem_interesse|invalido|outro}` |
- **Read tools** call SW via `SocialWiringClient` (`app/clients/social_wiring.py:46`) — new methods `lais_ferramenta(org_id, nome, args) -> dict` on Fake + Http; Http uses the per-org token from `resolve_org_credential("social_wiring_lais_tools_token", org_id)` (`seed/lib/backend/noctusai_lib/config/credentials.py:211`); none → tool omitted from the toolset (never a process-wide fallback). Timeout 8 s; failure → tool result `{"erro": "indisponivel"}` (model told to apologise and continue).

**(d) Response.** `ChannelActionOut` (`app/schemas/channels.py:97-99`) becomes a discriminated union on `type`: `handoff{motivo}` (unchanged) + the six action shapes above, each with `seq: int` (order in the turn). `status` gains `"encerrado"` when an `encerrar` action is present.

**(e) `POST /api/channels/conversations/{conversation_id}/resumo`** (same auth as `/turns`: product token, scope `agents:channel-turn`, issuer `social-wiring`). Request `{ perguntas: [same as contexto.perguntas], desde: datetime|null }`. Response 200:
```
{ resumo: str (≤1200, pt-BR, no phone/e-mail),
  slots: {chave: str}, operacao: str|null,
  intencoes: [ "encerrar"|"captacao"|"cobranca_atendimento"|"parceria"|"visita"|"reclamacao" ],
  desfecho: "qualificado"|"frio"|"captacao"|"invalido"|"em_andamento",
  usage: {custo_usd, tokens_entrada, tokens_saida} }
```
Uses the seed structured-output path; counts toward the org daily cap. Errors as `/turns` (404 `conversation_not_found`, 424, 429, 502).

**(f) Tools-token intake: `PUT /api/channels/ferramentas-token`** (auth = the org's channel token; issuer `social-wiring`). Body `{token: str}` → stores it in `org_settings` under key `social_wiring_lais_tools_token` through the same per-org writer the agents api-keys router uses (`products/agents/backend/app/routers/api_keys_router.py`; encrypted; read back by `resolve_org_credential`, `seed/lib/backend/noctusai_lib/config/credentials.py:211`) → 204. `DELETE` same path → 204. This is how SW hands agents its callback token without a second paste by the owner.

**(g) Migration 029**: `agents.messages` gains `contexto_hash text null` (only column added).

Legs: side-effects = transcript rows + usage as today; actions are NOT persisted in agents beyond the assistant row's `blocks` (tool calls already stored as blocks). Idempotent replay (`_plan_batch` `channels_router.py:157-182`) must return the SAME actions (store them in the assistant row's blocks and rebuild on replay). Strictness: forbid. Deprecations: `HandoffCollector` name (kept as alias for one release).
Tests: golden prompt render; each action tool arg validation; replay returns identical actions; read-tool omitted without token; resumo shape; per-org token isolation; strict `== 401`.

### 2.2 social-wiring (slice F-SW; migration SW **267** `lais_fundacao.sql`)
Files: `migrations/267_lais_fundacao.sql`, `app/clients/agents.py` (extend), new `app/services/lais_contexto_service.py`, new `app/services/lais_acoes_service.py`, new `app/services/lais_eventos_service.py`, new `app/routers/lais_ferramentas_router.py`, `app/services/lais_lead_dispatcher.py` (call contexto + apply actions), `app/routers/lais_agente_router.py` (`PUT /token` also mints + pushes the tools token), tests.

Tables:
| Table | Columns (all have `org_id uuid not null`, `created_at`) | Notes |
| --- | --- | --- |
| `lais_contatos` | `id`, `connection_id`, `chat_id`, `telefone_e164`, `nome`, `email`, `operacao`, `slots jsonb default '{}'`, `gen int default 0`, `status_envio text check in ('nao_pronto','enviado','erro','enviado_auto') default 'nao_pronto'`, `lead_id uuid null` (→ `leads`), `responsavel_user_id uuid null`, `ultimo_inbound_at`, `ultimo_outbound_at`, `encerrado_at`, `canal text default 'whatsapp'`, `origem_slug text null`, `updated_at`; unique `(org_id, connection_id, chat_id)` | One row per person Julia talks to. "Lead" in Lais' UI. |
| `lais_interacoes` | `id`, `contato_id`, `iniciada_at`, `encerrada_at null`, `operacao`, `tipo text default 'comercial'`, `resumo text`, `slots jsonb`, `intencoes text[]`, `desfecho text`, `custo_usd numeric` | One episode; opened on the first inbound after 24 h of silence or after `encerrar`. |
| `lais_acoes_aplicadas` | `id`, `contato_id`, `conversation_id uuid`, `lote_hash text`, `seq int`, `tipo`, `payload jsonb`, `resultado jsonb`; unique `(org_id, lote_hash, seq)` | Idempotency ledger for A4. |
| `lais_eventos` | `id`, `tipo text` (11 values, §8), `contato_id null`, `payload jsonb`, `lido_por uuid[] default '{}'` | Event bus; wave 6 renders it. |

Services:
- `lais_contexto_service.montar(org_id, contato) -> dict` builds §2.1(a) and its hash; providers: `conhecimento` (wave 1), `perguntas` (wave 2), `estado` (here), `ferramentas` (enabled if the org has a tools token), `acoes` (all enabled; wave 3 may drop `qualificar_lead` when the org has no rule). Until waves 1/2 land, `conhecimento_md=""`, `perguntas=[]`.
- `lais_acoes_service.aplicar(org_id, contato, turn_result)`: per action in `seq` order, insert into `lais_acoes_aplicadas` (ON CONFLICT DO NOTHING → skip), then dispatch to the wave handler registry (`salvar_slots`/`definir_operacao` here; `qualificar_lead` wave 3; `pedido_visita` wave 5; `captacao` wave 8; `encerrar` here: sets `encerrado_at`, bumps `gen`, closes the interação and calls `/resumo`). Unknown handler (wave not yet built) → event `acao_sem_handler` + log, never an exception that drops the reply.
- `lais_eventos_service.emitir(org_id, tipo, contato_id, payload)`.
- Episode close → `AgentsClient.resumo(...)` (new method on Fake + Http in `app/clients/agents.py`), stores into `lais_interacoes`.

Route `POST /api/lais/ferramentas/{nome}` (product token, `require_scopes({"social-wiring:lais-tools"}, restrict="product_only")` + issuer `agents` check, same pattern as `app/routers/agents_bridge_router.py:65,87`). Bodies:
| nome | request | response `data` |
| --- | --- | --- |
| `buscar_imoveis` | `{operacao, bairro?, cidade?, tipo?, preco_max?, quartos_min?, limite≤5}` | `[{codigo, titulo, tipo, bairro, cidade, preco, quartos, link}]` from `/api/imoveis` service (`app/routers/imoveis_router.py:47,105,138`) |
| `detalhes_imovel` | `{codigo}` | `{codigo, titulo, descricao, preco, condominio, iptu|null (wave 1 switch), endereco (full or bairro+cidade per wave 1 switch), caracteristicas[]}` |
| `horarios_visita` | `{codigo?, dias≤7}` | `[{inicio, fim}]` from wave 5 config + `SchedulingEngine` (`app/modules/scheduling/engine.py:13,53`) |
| `consultar_empreendimento` | `{nome}` | wave 12 data; until then `[]` |
Errors: 401 strict; 403 `product_required|scope_missing|issuer_not_allowed`; 404 `ferramenta_desconhecida`; 422 `invalid_field`. The response never contains owner/proprietário personal data.

Token exchange: `PUT /api/lais/agente/token` (`lais_agente_router.py:337`) keeps its contract (204) and, after validating the channel token, mints a SW product token (`ProductTokenAdmin.mint("social_wiring", org_id=…, label="agents · ferramentas lais", scopes=["social-wiring:lais-tools"], expires_at=+90d, issuer="agents")`, signature at `seed/lib/backend/noctusai_lib/api/auth/session/token_admin.py:145-157`; same path agents uses for the channel token, `products/agents/backend/app/routers/channel_token_router.py:47,82`) and pushes it to agents §2.1(f). Push failure → 204 still, page shows "Ferramentas da Julia indisponíveis — reenvie o token" (new `erro` value in `GET /api/lais/agente`).

Legs: state-after a turn = contato updated (`ultimo_*`, `gen+1` on inbound), actions ledgered, events emitted. Errors in action handlers never block sending the reply. Strictness: forbid. Deprecations: none.
Tests: idempotent re-apply of the same `lote_hash`; stale-guard `gen`; tools route auth matrix (strict 401); episode open/close rules; contexto hash stable for equal input.

---

## 3 · Wave 1 — Conhecimento ("Meu negócio" + perfil + IPTU + nome do atendente + recesso)

Page **Lais › Conhecimento** `/lais/conhecimento` (status_pagina `lais_conhecimento`), tabs **Geral · Vendas · Locação · Perfil do WhatsApp · Endereço e IPTU**. Cards with [Editar] → drawer with Cancelar/Salvar; leaving dirty asks "Sair da edição? As modificações feitas não serão salvas." (Lais copy, `bubble-app-definition.md` §3).

Migration SW **268** `lais_conhecimento.sql`: `lais_conhecimento_secoes (org_id, secao text, dados jsonb, versao int, updated_by, updated_at; PK (org_id, secao))` with CHECK `secao in ('politicas','telefones','exibir_atendente','recesso','venda_info','venda_documentos','venda_financiamento','locacao_info','locacao_documentos','locacao_processo','locacao_garantias','perfil_whatsapp','endereco_iptu')` + status_pagina row.

Sections and fields (exact options from `bubble-app-definition.md` §4):
| secao | dados (JSON schema, pydantic per section, forbid) |
| --- | --- |
| politicas | `assinatura: digital_fisico|digital|fisico`, `chaves: acompanhado|cliente_busca|outro`, `chaves_outro: str?` |
| telefones | `[{setor: str≤60, telefone: e164, principal: bool}]` (≤10, exactly one principal) |
| exibir_atendente | `{ativo: bool}` → prefixes human messages with the sender name (applied in SW outbound, see Conversas) |
| recesso | `{ativo: bool, inicio: date, fim: date, mensagem: str≤500}` |
| venda_info | `{atende: bool, nomenclatura_corretor: str≤40}` |
| venda_documentos / locacao_documentos | `{pessoais: [chip], renda: [chip], endereco: [chip], adicionais: str≤1000}` chip vocab from §4 (+ locação extras "fiador imóvel quitado", "matrícula") |
| venda_financiamento | `{acompanha: bool, servicos: [despachantes|simulacao|bancos], custos: [chip], detalhes: str≤1000}` |
| locacao_info | `{atende: bool, nomenclatura_corretor}` |
| locacao_processo | `{prazo_residencial: [12|24|30|36|48|60], prazo_comercial: [...], multa: dez_pct|tres_alugueis, isencao: sim|nao|mediante_proposta}` |
| locacao_garantias | `{caucao:{aceita, oferecer, min_alugueis}, seguro_fianca:{aceita, oferecer, seguradoras:[chip]}, fiador:{aceita, oferecer, nome_limpo, imovel_quitado, localizacao: mesma_cidade|mesmo_estado|null}, titulo:{aceita, oferecer, alugueis:str, inclui_encargos}, outras:{aceita, opcoes:[chip], sem_garantia: bool}}` |
| perfil_whatsapp | `{nome_exibicao: str (read-only = persona), descricao: str≤512, sobre: str≤139, endereco, email, site}` — **stored + shown in the phone mockup; applied to the WhatsApp profile only by the Cloud transport (wave 12)**; WAHA: saved, banner "aplicado quando a API oficial estiver ativa" |
| endereco_iptu | `{endereco_completo: bool, usar_iptu: bool}` (read by the tools route) |

Routes (`app/routers/lais_conhecimento_router.py`, member read / admin write):
- `GET /api/lais/conhecimento` → `{data: {secoes: {secao: {dados, versao, updated_at}}, preview_md: str, hash: str}}` (defaults when never saved).
- `PUT /api/lais/conhecimento/{secao}` body `{dados, versao}` → 200 `{data: {secao, dados, versao}}`; 409 `versao_conflito` (optimistic lock); 422 `secao_invalida` / `invalid_field`; 403 non-admin.
- `GET /api/lais/conhecimento/preview` → `{data: {markdown, hash}}` ("Ver o que a Julia sabe").
Service `lais_conhecimento_service.render_md(org_id)` — deterministic pt-BR markdown, registered as the `conhecimento` contexto provider. Recesso active today → contexto also carries a recesso notice; SW additionally sends the recesso message deterministically on the first turn of an interação inside the period.
Legs: state-after save = next turn's `contexto.hash` changes (no agent republish). Errors above. Strictness forbid per section. Deprecations: none.
FE (`pages/lais/Conhecimento.tsx`, `components/lais/conhecimento/*`, `hooks/useLaisConhecimento.ts`): one drawer component per section; chips via the design-system multi-select; phone mockup for perfil; preview modal.
Tests: each section schema round-trip; optimistic lock; render golden; admin-only write (strict 401 / 403).

## 4 · Wave 2 — Perguntas essenciais

Page **Lais › Perguntas** `/lais/perguntas` (status_pagina `lais_perguntas`): category filter, switch per question, "Qualificatória" checkbox, "Mostrar todas", limit tooltip "Você atingiu o limite de perguntas adicionadas", locked "Objetivo: comprar ou alugar" ("Esta pergunta é essencial para a identificação da operação correta"), a question referenced by a wave-3 criterion can't be switched off ("primeiro desative os critérios de envio").
Migration SW **269** `lais_perguntas.sql`: `lais_perguntas_catalogo` (global, no org: `chave pk, label, dica, categoria, operacao null, numerica bool, moeda bool, ordem`) seeded with the 63 questions of `agent-brain.md` §2 (keys snake_case; `objetivo` locked) + `lais_perguntas_org (org_id, chave, ativa, qualificatoria, PK(org_id,chave))`. Limits: ≤8 active, ≤5 qualifying, `objetivo` always active — enforced by a trigger (DB guard + `verify_db_guards` probe).
Routes (`app/routers/lais_perguntas_router.py`):
- `GET /api/lais/perguntas` → `{data: {catalogo: [{chave,label,dica,categoria,operacao,ativa,qualificatoria,bloqueada,usada_em_criterio}], limites: {max_ativas:8, max_qualificatorias:5}}}`
- `PUT /api/lais/perguntas` body `{selecao: [{chave, qualificatoria}]}` (full replace) → 200 same shape; 422 `limite_ativas` / `limite_qualificatorias` / `objetivo_obrigatorio` / `chave_desconhecida`; 409 `usada_em_criterio` (`details.criterios`).
Per-chat slot state lives in `lais_contatos.slots` (F). Contexto provider `perguntas` = active org questions. Action `salvar_slots` handler (F) validates keys against the active set.
**Slot panel in Conversas**: component `components/lais/PainelLead.tsx` mounted in the Conversas right column through the existing header/side seam (`ThreadHeaderExtra`, seed `ChatThread.meta`); shows operação, each active question → value or "—", qualificatória marked. Read route `GET /api/lais/contatos/{connection_id}/{chat_id}` → `{data: {contato, slots, interacao_atual}}` (F-SW table; route lives in 2-BE).
Legs: changing the selection affects only future turns; existing slot values are kept (hidden if the question is off). Errors above. Strictness: full-replace, forbid. Deprecations: none.
Tests: limits (API + DB guard probe), locked question, criterion lock, provider render.

## 5 · Wave 3 — Envio ao SW (qualification → SW lead + card) + Lais › Leads

Page **Lais › Envio** `/lais/envio` (status_pagina `lais_envio`) — wizard "Envio de leads qualificados" (Passo 1 de 2 critérios, Passo 2 de 2 resumo), checkbox "Configurações diferentes para compra e aluguel", groups OR'd, criteria AND'd, base criterion locked "Comportamento = Qualificado via inteligência da Julia"; plus cards: **Leads frios** (switch, intervalo 30 min…10 h after last reengage attempt **or** "na manhã seguinte 05:00–06:00"), **Potenciais captações** (enviar ao SW | só notificar), **WhatsApp inválido** (enviar | não), **Pesquisa com clientes** (opt-in weekly random survey — stored; sending needs Cloud API, wave 12).
Page **Lais › Leads** `/lais/leads` (status_pagina `lais_leads`): table of `lais_contatos` — Lead (nome + "Atendido pela Julia" | "Sem atendimento") · Contato · Operação (+ imóvel code) · Canal (+ datetime) · Status (**Enviado ao SW** | **Não pronto** | **Erro no envio** + "Enviado pela Julia" / "Enviado automaticamente"); filters = the live "Filtro de leads" (§59.0 a8: data primeiro contato, nome, e-mail, telefone, imóvel, link, operação, atendimento, status, canal, campanha, anúncio); row actions Abrir conversa · Ver resumo · **Enviar ao SW**; bulk Enviar selecionados; "Baixar selecionados" = CSV export (admin only). **SW Leads (`/leads`, `frontend/src/nav/navGroups.ts:107`) is NOT changed**: a sent contato becomes a normal SW lead with source slug `julia` (row added to `lead_sources` per org on first send; `migrations/025_leads.sql:46-58`), and the Lais row links to it.
Migration SW **270** `lais_envio.sql`: `lais_envio_regras (org_id, operacao compra|aluguel|ambas, grupos jsonb, versao)`, `lais_envio_politicas (org_id PK, frios jsonb, captacoes text, whatsapp_invalido bool, pesquisa bool)`, `lais_envio_entregas (id, org_id, contato_id, gatilho qualificado|visita|frio|captacao|invalido|manual, status ok|erro, erro text, lead_id, created_at)` + status_pagina rows.
Criterion vocabulary (grupos = `[[{campo, operador, valor}]]`): `comportamento = qualificado` (locked), `visita_solicitada = true`, any slot key with `preenchido` / `>=` / `<=` / `entre` (numeric slots), `operacao = …`.
Send = `lais_envio_service.enviar(org_id, contato, gatilho)`: **idempotent per phone** — looks up an existing SW lead by normalized phone in the org first (leads contato fields, `app/modules/leads/services/leads_service.py:166-189`); found → attach + update, else `create_lead` (→ trigger `spawn_funil_card` creates the atendimento card, `migrations/240_spawn_funil_card_sem_descarte_silencioso.sql:6`) then `attach_lead_now` (`app/services/clientes_service.py:445`). Writes the interação `resumo` + slots as the card's first note. Sets `status_envio`, inserts `lais_entregas`, emits event `novo_lead`.
Triggers: action `qualificar_lead` (evaluated against rules; no match → stays "Não pronto"), `pedido_visita` (if the rule includes visita), cold timer job (`lais_envio_frio`, stale-guarded), `encerrar(invalido)` + policy, captação + policy, manual.
Routes (`app/routers/lais_envio_router.py`): `GET/PUT /api/lais/envio/regras`, `GET/PUT /api/lais/envio/politicas`, `GET /api/lais/leads?…filters…&page&page_size` → `{data: {items, total}}`, `POST /api/lais/leads/{contato_id}/enviar` → 200 `{data: {status_envio, lead_id}}` / 409 `ja_enviado` (returns the lead) / 422 `contato_sem_telefone`; `POST /api/lais/leads/enviar-lote {ids≤100}` → `{data: {ok:[], erro:[{id, code}]}}`; `GET /api/lais/leads/{id}/resumo`; `GET /api/lais/leads/export.csv` (admin).
Legs: state-after send = SW lead + card exist exactly once per phone per org; repeated triggers no-op. Error taxonomy above; a failed create → status `erro` + retry button. Strictness forbid. Deprecations: none.
Tests: idempotency per phone (2 triggers → 1 lead, 1 card); rule evaluation table; cold timer stale guard; export admin-only.

## 6 · Wave 4 — Reengajamento

Page **Lais › Reengajamento** `/lais/reengajamento` (status_pagina `lais_reengajamento`), tabs **Reengajamento padrão** · **Réguas de reengajamento** (copy exactly as live §59.0 a2, §59.0b).
Migration SW `lais_reengajamento.sql`: `lais_reengajamento_config (org_id PK, minutos_ativo, minutos_intervalo int check in (5..60 step 5), horas_ativo, horas_intervalo int check 1..11)`, `lais_reguas (id, org_id, nome, ativa, compra bool, aluguel bool)`, `lais_regua_tentativas (id, regua_id, ordem 1..3, espera_valor int, espera_unidade minutos|horas|dias, texto str≤1024 null, template_id uuid null, ativa)`; guard: active régua needs ≥1 active tentativa; ≤3 tentativas.
Jobs: `lais_reengajar_minutos` (any hour), `lais_reengajar_horas` (only 08–20 São Paulo; outside → reschedule to 08:00), `lais_regua_tentativa`. Enqueued on each Julia outbound with `gen`; fire only if no inbound since (`gen` equal), contato not `encerrado`, not paused, not handed off. Hours tier also covers leads who never replied. Message: minutes/hours = a turn with `contexto.estado.reengajamento = minutos|horas` (Julia writes it); régua with `texto` → Julia may rewrite (flag `reescrever: true` in contexto) ; with `template_id` → requires Cloud transport (wave 12), else the attempt is skipped with event `regua_sem_transporte`. After the last attempt → cold-lead policy (wave 3). Timeline system event "Lead não respondeu mais. Julia reativou a conversa".
Routes (`app/routers/lais_reengajamento_router.py`): `GET/PUT /api/lais/reengajamento/config`; `GET/POST /api/lais/reengajamento/reguas`; `GET/PATCH/DELETE /api/lais/reengajamento/reguas/{id}`; `POST …/{id}/ativar|desativar` (409 `regua_sem_tentativa`); `POST/PATCH/DELETE …/{id}/tentativas[/{tid}]` (409 `limite_tentativas`, `ultima_tentativa_ativa`).
Legs: inbound bumps `gen` → every pending reengage job becomes obsolete. Never after `encerrar`. Strictness forbid. Deprecations: none.
Tests: stale guard; business-hours reschedule; ≤3; active-needs-attempt; never-replied path.

## 7 · Wave 5 — Visitas (pre-scheduling)

Config drawer **exactly** as live (§59.0 a3): status chip · "Diferenciar configuração para leads de compra e aluguel" · switch "Pré-agendamento de visita" · switch "Solicitação de CPF obrigatória?" · Tempo mínimo (dias + horas) · Tempo máximo (dias) · Horários disponíveis De/Até per weekday · 30-min slots.
Pages: **Lais › Visitas** `/lais/visitas` (status_pagina `lais_visitas`) — empty state "Ative as solicitações de visita…" [Configurar visitas]; list + week/day calendar (no month view — Lais rejects it, `agent-brain.md` §6); filters operação/status/responsável; visit dialog Confirmar / Remarcar / Cancelar (each messages the lead via the transport).
Migration SW `lais_visitas.sql`: `lais_visitas_config (org_id PK, separar_operacao, config jsonb {geral|compra|aluguel: {ativo, cpf_obrigatorio, min_dias, min_horas, max_dias, grade:{seg..dom:[{inicio,fim}]}}})`, `lais_visitas (id, org_id, contato_id, codigo_imovel, inicio, fim, cpf_hash text null, status solicitada|confirmada|remarcada|cancelada, agendamento_id uuid null → atendimento_agendamentos, responsavel_user_id, created_at, updated_at)`.
Flow: action `pedido_visita` → validate against config + `SchedulingEngine` free slots → insert `solicitada` → event `pre_agendamento_visita` → (wave 3) trigger envio if a rule asks. **Confirmar** creates `atendimento_agendamentos` (`tipo='visita'`, `migrations/061_atendimento_agendamentos.sql:47-70`) on the lead's card (envio forced if not yet sent) and sends "Visita confirmada" text (WAHA) or template (Cloud). CPF stored only as a hash + last 3 digits (LGPD).
Routes (`app/routers/lais_visitas_router.py`): `GET/PUT /api/lais/visitas/config`; `GET /api/lais/visitas?view=semana|dia&data=YYYY-MM-DD` (422 `view_invalida` for others); `POST /api/lais/visitas/{id}/confirmar|remarcar{inicio,fim}|cancelar{motivo}` → 200 `{data: visita}`; 409 `transicao_invalida`.
Legs: confirm ⇒ exactly one agendamento; remarcar updates it; cancelar soft-deletes it. Tests: transitions; slot validation; CPF never stored in clear.

## 8 · Wave 6 — Notificações

Page **Lais › Notificações** `/lais/notificacoes` (status_pagina `lais_notificacoes`): feed by day; card = category label + text + datetime + expand; filters Data · Operações (Todas/Aluguel/Compra) · **Tipo** (11, §59.0 a12): `pre_agendamento_visita`, `cobranca_atendimento`, `relatorio`, `remarketing`, `captacao`, `atualizacao_base_imoveis`, `novo_lead`, `novo_atendimento`, `nova_mensagem`, `avaliacao_google`, (+`handoff` from page 0). Toggle **"Notificar lead pronto para atendimento"** (per user). Header bell count (seed `notifications.ts`).
Migration SW `lais_notificacoes.sql`: `lais_notificacao_prefs (org_id, user_id, tipo, in_app bool, PK)`.
Routing: `lais_eventos_service.emitir` → recipients = responsável of the contato, else connection owner, else org admins (same target rule as handoff §11.4) → `write_in_app(kind='lais_'+tipo)` when the user's pref allows. `cobranca_atendimento` comes from the resumo `intencoes` (lead complaining nobody answered).
Routes: `GET /api/lais/notificacoes?tipo&operacao&de&ate&page` → `{data:{items,total,nao_lidas}}`; `POST /api/lais/notificacoes/lidas {ids|todas}` → 204; `GET/PUT /api/lais/notificacoes/preferencias`.
Tests: recipient resolution; prefs; org isolation.

## 9 · Wave 7 — Conversas v2

Extends `/lais/conversas` (`pages/lais/Conversas.tsx`, `WhatsAppWorkspace.tsx`): list tabs **Todas · Minhas · Arquivadas**; filter drawer **Operações / Status SW / Status de atendimento (Julia atendendo | Atendimento manual) / Responsável / Equipe / Etiquetas**; **kanban** `?view=kanban` with fixed "Todas", collapsed "Arquivadas", **one column per etiqueta** ("Adicionar coluna" = tag picker, "Criar nova etiqueta") (seed `kanban` organ); header **Atribuir responsável**, like/dislike/feedback on Julia's service (stored, feeds evals), arquivar (hands chat back to Julia on new inbound), bloquear número; right column **Cliente**: Perfil · Visitas solicitadas · Etiquetas · Notas internas · **Interações** (tipo, iniciada em, chips canal/operação/status, slots, resumo, intenções em itálico); timeline system events; **"Copiar link do histórico"** = `/lais/conversas/h/{contato_id}` (A7).
Migration SW `lais_conversas_v2.sql`: `lais_etiquetas (id, org_id, nome, cor)`, `lais_contato_etiquetas`, `lais_notas (id, org_id, contato_id, autor_user_id, texto≤4000, created_at, deleted_at)`, `lais_feedback (contato_id, interacao_id, user_id, nota like|dislike, comentario)`, `lais_contatos` + `arquivado bool`, `bloqueado bool`.
**History access (A7)** — `GET /api/lais/historico/{contato_id}`: 401 no session; 404 if the contato is in another org (never 403 cross-org); 403 `sem_acesso` if the caller is not owner/admin and not `responsavel_user_id` (fallback owner = connection `user_id`); 200 `{data:{contato, interacoes, mensagens}}`. The same check guards every per-contato route of waves 2–7 for non-admins ("other members can't see data of other members' leads"): members see only contatos where they are responsável; admins/owners see all.
Attendant-name prefix: when `exibir_atendente.ativo` (wave 1), human outbound text from Conversas is prefixed `*{nome}*:\n` in SW outbound.
Routes: `GET /api/lais/conversas?aba=todas|minhas|arquivadas&…filtros`; `PATCH /api/lais/contatos/{id}` `{responsavel_user_id?, arquivado?, bloqueado?, etiquetas?}`; notes CRUD `…/{id}/notas`; `POST …/{id}/feedback`; tags CRUD `/api/lais/etiquetas`.
Tests: the A7 matrix (owner, admin, other member, other org) with strict codes; kanban-by-tag; prefix.

## 10 · Wave 8 — Captação

Page **Lais › Captação** `/lais/captacao` (status_pagina `lais_captacao`): feed "Acompanhe as notificações de imóveis potencialmente captados", cards "CAPTAÇÃO — A Julia identificou uma potencial captação de imóvel", expandable (descrição, endereço, operação, contato link), filters, page sizes 5/10/15/20; action **Registrar captação** → existing `imovel_captacao` flow (`migrations/226_imovel_captacao_manual.sql`) prefilled.
Migration `lais_captacoes.sql`: `lais_captacoes (id, org_id, contato_id, descricao, endereco, operacao, status nova|registrada|descartada, imovel_id null)`.
Flow: action `captacao` → row + event `captacao` → policy (wave 3: enviar ao SW | só notificar).
Routes: `GET /api/lais/captacoes`, `POST …/{id}/registrar` (→ imovel id), `POST …/{id}/descartar`.

## 11 · Wave 9 — Painel (Início)

Page **Lais › Painel** `/lais/painel` (status_pagina `lais_painel`, first item of the group): month picker, refresh; **Atividades** (consumo = Julia turns/cost this month vs org daily-cap budget; cobranças de atendimento count → notificações; pré-agendamentos count → visitas); **Dados gerais**: funnel Topo (contatos) → Atendidos pela Julia → Enviados ao SW; charts Leads por canal, Status por canal, Leads por horário (% fora do horário comercial), Leads semanais (melhor dia), últimos 6 meses (enviado vs não).
Route `GET /api/lais/painel?mes=YYYY-MM` → `{data:{atividades, funil, por_canal, status_por_canal, por_hora[24], por_dia_semana[7], seis_meses[6], consumo:{turnos, custo_usd}}}` — SQL views over `lais_contatos`/`lais_interacoes`/`lais_envio_entregas` + agents usage via a new agents read `GET /api/channels/uso?mes=` (product token; `{turnos, custo_usd}`).
Tests: view math on fixtures; month boundaries in São Paulo time.

## 12 · Wave 10 — Relatórios

Page **Lais › Relatórios** `/lais/relatorios` (status_pagina `lais_relatorios`), tabs **Imóveis · Bairros**, operação + month: Top tipo de imóveis (% leads vs % prateleira = SW `imoveis` active stock), Top 10 imóveis (by leads; **deduplicated** — Lais shows duplicate rows), Top 10 bairros + "Desempenho por bairro" (median desired price, % by tipo, best quartos, mais buscados).
Route `GET /api/lais/relatorios?operacao&mes&aba=imoveis|bairros[&bairro]`. Source: slots (`bairro_desejado`, `tipo_imovel`, `faixa_preco`, `quartos`) + codes mentioned (actions/tool calls). Tests on fixtures.

## 13 · Wave 11 — Distribuição

Page **Lais › Equipes** `/lais/equipes` (status_pagina `lais_equipes`) — mirrors Lais team settings (§59.0b): Nome da equipe* · "Esta equipe atende clientes diretamente após a Julia?" Sim/Não · "Como os leads serão atribuídos?" **Via funil do SW** (padrão: card created unassigned/assigned by the funil rules) / **Via Julia** (Julia assigns an attendant at handoff) · "Manter atribuição ao último responsável" · members (org users) · metrics per member: último acesso, **TPR** (tempo de primeira resposta), conversas, distribuição.
Migration `lais_equipes.sql`: `lais_equipes (id, org_id, nome, atende_apos_julia, modo funil|julia, manter_ultimo)`, `lais_equipe_membros (equipe_id, user_id, ativo, ordem)`, `lais_distribuicao_cursor (equipe_id, ultimo_user_id)`.
Consumption (owner #5): at handoff / qualification SW picks the attendant (round-robin by cursor, or last responsável) **before** notifying, sets `lais_contatos.responsavel_user_id`, and passes `contexto.estado.atendente_nome` on the next turn so Julia can say who will continue. Julia never stores distribution data.
Routes: CRUD `/api/lais/equipes`, members, `GET /api/lais/equipes/{id}/metricas?mes`.
Tests: round-robin fairness; last-responsible; admin-only writes.

## 14 · Wave 12 — Cloud-API pages (build now; dispatch after Meta verification)

Seam: `app/services/lais_transporte.py` — `Transporte` Protocol `{enviar_texto, enviar_template, atualizar_perfil}`; `WahaTransporte` (text only; `enviar_template` raises `TemplateRequerApiOficial`), `CloudApiTransporte` (Fake + Real over seed `MetaCloudClient`, extended with template send + profile update) + factory per connection (`connection.transporte = waha|cloud`, default waha). Page header badge "Aguardando verificação da Meta" while Cloud is not configured.
Pages: **Lais › Modelos** `/lais/modelos` (§59.0 a4: 8 categories Administrativo · Campanha · Cobrança · Documentação · Primeiro contato · Reativação · Visita · Outros; body ≤1024; 10 parameters Nome da pessoa, Nome da Lais→Julia, Nome da imobiliária, Mensagem, Data da visita, Código do imóvel, Link do imóvel, Nome do atendente, Imóvel da visita, Data e horário da visita; preview + "Simule com exemplos"; status rascunho|enviado_meta|aprovado|rejeitado) · **Lais › Disparos** `/lais/disparos` (tabs Todos · Rascunhos · Agendados · Enviados · Cancelados · Erros; types Remarketing · Atualização de anúncios; segments e.g. leads 3–15 / 7–30 days without reply; cap per send = 15 % of month volume; per-chat template cap) · **Lais › Atualização de imóveis** `/lais/proprietarios` (owner conversations to refresh listings: status/price confirm → updates SW `imoveis` via existing service) · Meta lead-form leads → Julia first contact (template "Abordagem comercial|neutra").
Migrations: `lais_modelos`, `lais_disparos` (+ `lais_disparo_alvos` with status flow `pendente→enviado→respondido→enviado_sw|erro`), `lais_proprietarios_contatos`. Remarketing replies re-enter Julia (qualification at no extra step).
Rule: everything can be created/saved/scheduled; **dispatch endpoints return 409 `transporte_indisponivel`** while the connection is not Cloud. No WAHA mass send, ever.

## 15 · Wave 13 — Avaliações no Google · Análise de crédito · CAPI

- **Avaliações** `/lais/avaliacoes`: rule = after an interação closes with desfecho `qualificado` and feedback not negative → ask for a Google review (link from org config `google_review_url`) once per contato per 90 days; KPIs pedidos enviados / novas avaliações; reviews list via Google Business Profile API seam (Fake + Real; Real needs the owner's GBP OAuth — reuse seed Google integration). Ask message: WAHA text allowed (1:1, inside the 24 h window).
- **Análise de crédito** `/lais/credito`: provider seam `CreditoProvider` (Fake + first Real TBD by the owner; Lais uses CredAluga); runs at the visit step for aluguel; **requires explicit lead consent captured in-chat** (action `consentimento_credito{aceito}` added to A4) before any call; result aprovado|reprovado|pendente stored per contato, shown in Interações.
- **CAPI** (sinais de qualificação): events `lead_qualificado`, `visita_agendada`, `resposta_cliente` → Meta Conversions API via the existing meta_ads integration seam, only for leads that came from Meta ads (`meta_ads_leads`), hashed identifiers per Meta rules.

---

## 16 · Slice list — round 1 and 2 (file zones)

| Slice | Agent | Zone (exclusive unless marked shared) |
| --- | --- | --- |
| F-AG | backend-engineer @ agents | `products/agents/backend/app/{schemas/channels.py, channels/tools.py, routers/channels_router.py, routers/channel_tools_token_router.py, runtime/llm_runtime.py, clients/social_wiring.py}`, `migrations/029_*`, tests |
| F-SW | backend-engineer @ SW | `backend/migrations/267_lais_fundacao.sql`, `app/clients/agents.py`, `app/services/lais_{contexto,acoes,eventos}_service.py`, `app/services/lais_lead_dispatcher.py`, `app/routers/lais_ferramentas_router.py`, `app/routers/lais_agente_router.py` (`PUT /token` only), `app/main.py` (shared append), tests |
| 1-BE | backend-engineer | `migrations/268_lais_conhecimento.sql`, `app/routers/lais_conhecimento_router.py`, `app/services/lais_conhecimento_service.py`, `lais_contexto_service.py` (shared append: provider line) |
| 1-FE | frontend-engineer | `frontend/src/pages/lais/Conhecimento.tsx`, `components/lais/conhecimento/**`, `hooks/useLaisConhecimento.ts`, `nav/lais.ts` + `App.tsx` (shared append) |
| 2-BE | backend-engineer | `migrations/269_lais_perguntas.sql`, `app/routers/lais_perguntas_router.py`, `app/services/lais_perguntas_service.py`, contatos read route, provider line (shared) |
| 2-FE | frontend-engineer | `pages/lais/Perguntas.tsx`, `components/lais/perguntas/**`, `components/lais/PainelLead.tsx`, `hooks/useLaisPerguntas.ts`, one mount line in `pages/lais/Conversas.tsx` (shared) |
| 3-BE / 3-FE | R3 | `migrations/270_lais_envio.sql`, `app/routers/lais_envio_router.py`, `app/services/lais_envio_service.py` / `pages/lais/{Envio,Leads}.tsx`, `components/lais/{envio,leads}/**` |
| 4, 5 (R2) | BE+FE each | their own migration/router/service/page/component dirs as named in §6–§7 |

Every slice: contract-first (embed its section of this file verbatim in the brief), tests assert this contract, `predeploy_check` on the merged tip, strict `== 401` auth tests, no PII in fixtures.

## 17 · LGPD (file with `noctus.dev.lgpd_flag` at each wave's dispatch)

| Wave | New personal-data category | Mitigation |
| --- | --- | --- |
| F | Lead contact (phone, name, e-mail) in `lais_contatos`; conversation summaries + extracted slots in `lais_interacoes` | org RLS; deletion on request extends page-0 `apagar-dados` to these tables; retention 180 days for closed contatos without a SW lead |
| 2 | Slots may include CPF, data de nascimento, estado civil, renda, filhos | CPF/renda flagged sensitive: stored hashed/bucketed when the catalogue marks them; never sent in tool payloads |
| 3 | Lead copied into SW CRM | legitimate interest + disclosure message (page 0); source `julia` traceable |
| 5 | Visit requests with CPF | hash + last 3 digits only |
| 7 | Internal notes about leads; feedback | org + ownership access (A7); notes soft-deleted, purged with the contato |
| 11 | Attendant performance metrics (TPR) | admin-only view; employee data — inform the org |
| 12 | Owners (proprietários) contacted for listing updates | owner-side consent/opt-out ("parar") honoured; Cloud templates only |
| 13 | Credit analysis result (financial data); Google review requests; CAPI hashed identifiers | explicit in-chat consent before credit query; review ask once/90 days; CAPI only for Meta-ad leads, SHA-256 hashed per Meta |
| all | Data processed by OpenAI (per-org key) | open item from page 0: DPA per org |

## 18 · Decisions not taken here (owner)
1. Credit-analysis provider (Lais uses CredAluga) and whether the org pays per query.
2. Google review link/account per org (GBP OAuth) — needed to show received reviews; asking works without it.
3. Pesquisa com clientes (weekly random survey) text and frequency — built as opt-in; sends only with the Cloud transport.
