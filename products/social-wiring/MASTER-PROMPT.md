# Social Wiring — MASTER-PROMPT

> Authoritative development guide for the `social-wiring` product (SW).

## Purpose

SW is noc's **real-estate operations hub**: inbound leads (portals, Meta Ads, WhatsApp), the
sales funnel and per-lead cards, properties / owners / condominiums, contracts, matrículas and
certidões, marketing (Meta, Instagram, email, CoreStudio), and the **WhatsApp transport and CRM
side of Julia**, the SDR agent. It started as a media/YouTube/scheduling CMS and absorbed
`mailing`, `imobi-scheduling` and several others; those modules still live here.

**Division of labour with `agents`.** Julia's brain (prompt, tool loop, LLM keys, versions) is
hosted in the `agents` product and consumed over its `/api/channels/*` API. SW owns what
surrounds the turn: webhook intake, the per-chat pause/handoff policy, rate limits, the single
outbound gate, the CRM (contatos, interações, eventos, leads, cards), knowledge/questions the
org configures, follow-ups, notifications and reports. SW never calls an LLM for a Julia turn.

## Julia (renamed from "Lais" on 2026-10-19)

"Lais" is Lastro's product (reverse-engineered in a private study outside git, kept as the vendor
study). Everything we built under that name is Julia: code `julia_*`, tables `julia_*`, API
`/api/julia/*`, pages `/julia/*`, nav group "Julia".

- **Backend**: `app/routers/julia_*_router.py` (agente, conversas, conhecimento, perguntas, visitas, reengajamento, notificacoes, envio, equipes, cloud/modelos/disparos, captacao, credito, avaliacoes, relatorios, painel, ferramentas), `app/services/julia_*` (one service per area), `app/clients/agents.py` (the agents HTTP client; `AgentsClient` / `FakeAgentsClient`).
- **Turn** (julia-v2: Julia is hosted in agents, SW consumes her via the API only): WAHA webhook → `julia_lead_turn_service` (debounce, authorized numbers, limits; NO local pause gate -- `whatsapp_chats.agente_pausado` is a display mirror) → agents `POST /api/channels/turns` with `agent_key="julia"`, the lead ref and a data-only `contexto` → agents answers a `status`: a served one sends the bubbles and its typed actions (`HandoffAction`, `JuliaAction`: `lead_pronto`, `intencao_visita`, …) are applied idempotently by `julia_acoes_service`; every other status, an error or a timeout sends nothing (fail closed). Thread API (append without a turn, per-conversation pause via `PATCH participantes`, hand-offs, consent, LGPD delete-by-lead, controls read, computed qualification) is `AgentsClient`; the SW side is `julia_thread_service` / `julia_espelho_service`.
- **Opt-outs and data requests** (owner 2026-10-21): the lead opt-out is AGENTS' per-org record; SW shows it at **Julia > Opt-outs** (`/julia/opt-outs`, `app/routers/julia_opt_outs_router.py`, `julia_opt_out_service`): history, "Reenviar notificação", "Reativar atendimento" and "Marcar como não contatar" (admin, reason required), and a non-blocking warning for the human operator in Conversas. **No lead message can delete or change anything**: the keyword auto-erase is gone; Julia registers a data-subject request through her tool (`POST /api/julia/ferramentas/solicitacao-titular` -> `julia_solicitacoes_titular`, 15-day deadline), an admin decides it, and an erasure is the admin's "apagar-dados" act (keeper `tests/test_lead_path_never_deletes.py`).
- **Public-number protection** (owner 2026-10-21, GUARDRAILS B2/B5/B8/B10): the org **staff list** (`julia_staff`, **Julia > Equipe do WhatsApp**, `julia_equipe_whatsapp_router`, `julia_staff_service`) is the ONE place staff is decided, by the sender's NUMBER only: any number not on it is a lead, always; an operator-role number keeps the One Chat path (the connection's `authorized_numbers` is now its mirror, written by the connection PATCH through `sincronizar_de_lista`); every other staff role never enters the lead flow (message stored, admins noticed once an hour); the human lines SW appends to an agents thread go on the staff append route with `role: "humano"`, `autor {nome, papel}` and `autor_user_id`. **Julia > Proteção** (`julia_protecao_router`, `julia_protecao_service`, migration 298) holds every limit per org with its default (per-number inbound rate 20/60 s before agents is called; media AI budget 10/chat/day and 200/line/day; the automatic temporary block after 3 abuse signals in 60 min for 24 h, admins notified), the per-org **blocklist** (manual with reason/who/when, or automatic-temporary; a blocked number's inbound is recorded and never reaches agents or an AI call) and the operator-editable lead document prompt. A lead's media travels STRUCTURED (`messages[i].midia {tipo, texto_extraido <= 2000, legenda?}`, never inlined in `texto`) and is resolved under the lead caps (`MediaService.resolve_inbound_lead`: streamed size caps 16 MB/5 min audio, 8 MB image, 10 MB/3-page PDF; no video; no redirects; the WAHA key only to the WAHA host; CPF/RG/CNH masked by `identidade_mascara`); after agents registers the identification SW masks the typed numbers in its stored copy (`MessageStore.redigir_identificacao`) and in the chat's `whatsapp_chats.last_message_preview` while it is still that message's preview (`WhatsAppChatStore.redigir_preview`; each step separate, a failure logged by type only, never blocking the reply) and purges that chat's `message.new` / `chat.upsert` carrying one from the inbox stream's retained window (`bus.redact`; the value masking is the lib's `identificador_redacao`). The Julia/media modules log no text, no raw exception and no bare chat id/LID (`ref_log`; keeper `tests/test_julia_log_hygiene.py`). A 429 `capacidade` that outlasts the re-queues goes to a human, never dropped.
- **Send gate**: every WhatsApp send of Julia code goes through `julia_envio_gate.exigir/conferir`; the keeper `tests/services/test_julia_envio_gate_keeper.py` derives its scope from the filenames (`julia_*`, importers of a `julia_*` service, `atendimento_blocos`, `supervisao`) — keep that predicate in step with any rename. Direct sends to a LEAD (no agents turn) also call `julia_envio_gate.exigir_sem_opt_out` / `motivo_opt_out` (agents' opt-out, fail-closed); the list lives in `ENVIOS_A_LEAD_COM_OPT_OUT` of the same keeper file. `AgentsClient.opt_out(..., origem, motivo, mensagem_lead, ator_user_id)` carries who/why to agents (it notifies the admins itself; SW never sends a second notification for the event).
- **Agent tools**: `POST /api/julia/ferramentas/{nome}` (product token, scope `social-wiring:lais-tools`, issuer `agents`). The scope string and the Meta template-name prefix `lais_<id>` are identities stored outside SW and keep their old spelling (`NOC-REMEDIATE[rename-lais-tools-scope]`, `[rename-lais-meta-template-prefix]`). Tools: `buscar_imoveis` (structured query, `similar_a`, `excluir_codigos`, `limite` 1..5, one-axis-at-a-time widening reported as `relaxado`, `restantes_estimados`; standard item keys — `itens_essenciais` / `caracteristicas` / `itens_desejaveis` — map to catalogue predicates via `ITENS_PADRAO` in `julia_busca_imoveis.py` (e.g. `jardim_quintal` = quintal/jardim but not jardiminverno, `terreo_sem_escadas` = a house with `pavimentos = 1`); items the catalogue cannot verify (pets, proximidades, terreo on a non-house) never filter or rank and come back as `itens_nao_verificaveis`), `imovel_campanha`, `detalhes_imovel`, `horarios_visita`, `consultar_empreendimento`. Stage list for the Envio comparator: `GET /api/julia/qualificacao/estagios` (proxy of agents).
- **Opt-in by construction**: nothing sends until an admin turns Julia on per connection (`agente_leads_ativo`, `authorized_numbers` required); defaults are off. Julia pages are the only UI. FE (julia-v2): SW's `/julia/agente` is line routing only (hooks `useJuliaRoteamento`, `RoteamentoCard`, link `ConfigurarNoAgentes` -> `{agents_url}/studio/julia`); behaviour, prompts, rules, questions and knowledge are edited in the agents app and NEVER rendered or typed in SW's FE (IP). `/julia/perguntas` and `/julia/conhecimento` are read-only `MovidoParaAgentes` notices. The thread header state comes from agents' GET with its `fonte` (`agents` | `espelho` stale | `nenhuma`) — the FE never decides a Julia state itself; the stage chip is label + score only; the handoff notification shows masked identity only (`lib/mascaraIdentidade.ts`). Envio's rule is `estagio_minimo` (dropdown over agents' ordered stages, `GET /api/julia/qualificacao/estagios`); never send `grupos`.
- **One Chat = operator agent, operators only** (owner 2026-10-20; `ChatbotService` + the WhatsApp upload intake): it answers only numbers in the connection's `authorized_numbers`. An EMPTY list means NOBODY — and strangers on such a line get no denial reply (it is a lead line); the denial reply goes out only when the list is non-empty and the sender is not on it. Julia stays leads-only and never gets One Chat's operator tools.
- **Atendimento blocks + Maya** (`app/modules/atendimento_blocos`, `app/modules/supervisao`, contract `projects/maya-blocks/CONTRACT.md`): a closed list of blocks (`sdr` = Julia, then atendimento, negociação, jurídico, financeiro, contador), per-org config (off by default), recorded handoffs, and Maya's nightly scorecards (`sdr.v2`: first response split agent/human; only human acts take a handoff over; the accept's handoff is T3, recorded even with no actor) / handoff sweep / owner-only report. Every swallowed supervision error calls `supervisao.alertas.alertar` (event `supervisao_falha`, owner-only notification, day flagged `dados_incompletos`). The per-turn `contexto` sent to agents is data only and filtered to the keys its schema accepts (`ESTADO_CHAVES_AGENTS`); a 422 raises the owner alert `agents_contrato_invalido`. Studio key `julia` (legacy `lead-imob` is read as `julia`).
- **Database**: migration 287 renamed the 38 `lais_*` tables and their constraints, indexes, triggers, policies and functions to `julia_*`, and left security_invoker views `lais_*` so the previous image keeps working (`NOC-REMEDIATE[drop-lais-compat-views]`). New code uses `julia_*` only. Migrations 255–286 are applied history and keep the old names; never edit them. Migration 289 makes every `julia_*` table / `lais_*` view service-role only (browser roles revoked, policies naming them dropped, default privileges revoked, all views `security_invoker`); the question catalogue's model hints (`dica`) never leave the backend.
- **Compat shims (one release)**: `LegacyLaisPathAlias` serves `/api/lais/*` and `/api/public/lais/*`; `/lais/*` redirects to `/julia/*` in the SPA; `LAIS_*` env names alias the renamed settings; `{{nome_lais}}` still renders as `{{nome_julia}}`. All tagged `NOC-REMEDIATE[drop-lais-*]`.
- **Vendor vocabulary stays**: the `*Lais` lead-channel slugs in `julia_leads_service` and `ZAP/LAIS`-style portal origins in `modules/leads/seed_data.py` are Lastro CRM data values, not our module name.
- **Owner corrections win over re-reads** (owner 2026-10-20; `card_hub/identidade_extracao_service.correcao_do_dono`): a document reading that disagrees with a field the owner corrected in the app becomes an approve/reject warning (`protege_correcao`, migration 291), never a silent overwrite. The same holds when the agreement gate empties a divergent reading while the field already has a value (owner 2026-10-21, `abrir_revisoes_divergencia`): a reading differing from the on-file value opens an approve/reject review (never dropped silently, never blocks generation); an agreeing one opens none; a rejected one is not re-raised. Fix data through the app edit path, never a raw DB patch that keeps a document `origem` — that looks machine-made and gets overwritten (deal 876, 2026-10-19).
- **Certidões grid: manual cells and re-reads** (migration 302): a hand-edited cell (`resultado_origem='manual'`) is locked against "Reler" and the Crednet; `POST /api/certidoes/resultados/{id}/voltar-automatico` ("Voltar à leitura automática") clears the override and re-runs the cell's automatic source (stored PDF, Crednet for serasa, registry response). A CENPROT/Serasa consulta that prints no date takes the PDF CreationDate (same plausibility window as the CENPROT reader), recorded as `emitida_em_origem='metadados_pdf'` and shown as inferred. A complete typed cell (resultado + número + emissão) counts as done. The party summary counts cells being read apart (`totais.processando` / `relendo`, "relendo n/N" with a progress bar; a re-read keeps the previous values visible), and "Editar" writes the saved row into the grid cache at once.
- **Certidões: the card tab owns every emission control** (the standalone /certidoes screen is being retired): per cell "Descartar emissão" (`DELETE /api/clientes/{id}/certidoes/resultados/{rid}`, soft-delete, the previous evidence wins again) and "Cancelar emissão" (`POST …/resultados/{rid}/cancelar`; per party `POST …/partes/{kind}/{alvo}/cancelar`; automatic consultas only, a manual cell is never cancelled); per party "Reemitir com erro" (`POST …/partes/{kind}/{alvo}/reemitir-erros`: only failed automatic cells, in place — same consulta, `erro`→`pendente`, TJSP→`na_fila`) and "Baixar todas (.zip)" (`GET …/download-zip`); "Solicitar emissão (todas)" skips cells already `sucesso` and in date or in emission (`ignoradas`, 409 `NADA_A_EMITIR` when nothing is left). All reuse `certidoes.service` (`cancelar_processamento`, `reprocessar_resultados`, `soft_delete_resultado`, `montar_zip`) and answer with the party as it reads afterwards. Cells carry `aguarda_humano` (the polling stop signal of an untouched manual placeholder — `origem` is now only who produced the values, so "Voltar à leitura automática" is no longer offered on an empty cell) and `emissao_automatica`; `totais.erros` feeds the "n com erro" summary and error text shows inline; "Negativa c/ homônimos" is its own chip.
- **Contract specifications** (migration 308, owner 2026-10-24; contract `projects/sw-lead-to-contract/CONTRACT.md` §10): the kind of contract is a SELECTABLE set of facets from the code catalogue `contrato_gerador/especificacoes.py` (`compra_venda` base; pagamento `a_vista` · `sinal_saldo` · `financiamento_bancario` · `fgts` · `parcelas_diretas` · `intermediarias`; `confissao_divida`; `permuta`; `intermediacao`), each declaring the readiness `falta` keys it asks for. `PUT /api/clientes/{cliente_id}/contratos/{contrato_id}/especificacoes` stores it (`atendimento_contratos.especificacoes` + `especificacoes_versao`; NULL = legacy mode, the derived switches); `sugerir(switches)` is the data-derived suggestion and `derivacao.modelo_derivado` reads off it. The selection SCOPES the readiness (`derivacao.Avaliacao.pede`, one gate on every falta): a key a specification governs is asked only when the selection requires it; a selected specification with no data is a falta `especificacao.<chave>`; data whose specification is not selected is the bloqueio `ESPEC_CONTRADIZ_DADOS`; the `fgts` specification requires the companies' CRF/FGTS. Open owner question G1 (à vista without sinal → multa rescisória base) is asked as the falta `negociacao.multa_rescisoria_base` ("aguardando decisão do escritório") — never ready until decided. `GET …/geracao` carries `especificacoes`, `especificacoes_versao`, `sugeridas`, `conflitos` and the selection's `modelo` (`service.modelo_do_contrato`). The FE selector is the next slice.
- **Contract: Crednet companies and seller obligations** (migration 299, deal 857): a company read off a seller's Serasa Crednet enters the generated contract (with its certidões) only once someone confirms the participação on the card's Empresas section (`PATCH /api/clientes/{cliente_id}/empresas/{empresa_id}/participacao`, `confirmar | descartar | reabrir`; "Não é do vendedor" survives a Crednet re-read). Until then the readiness list names it as the non-blocking aviso `EMPRESA_CREDNET_NAO_CONFIRMADA`. The typed seller obligations print in the ÔNUS clause by default, or — per deal, `termos.obrigacoes_vendedor_local='certidoes'` — as one lettered paragraph "a) …; b) …." inside DAS CERTIDÕES E DOCUMENTOS, right after the seller's last person group (before any company group; no such group ⇒ before the imóvel's).

## Architecture

**Born from the seed framework.** App shell, auth, layout, routing, notifications, health, team
and LLM access come from the factory; SW owns domain modules and its frontend.

### Backend (`products/social-wiring/backend/app/`)

```
main.py        → create_product_app("Social Wiring", "social_wiring", settings); MODULES list assembles
                 module routers; LegacyLaisPathAlias is the outermost middleware
config.py      → ProductSettings subclass
modules/       → leads · pipeline · card_hub · portal_leads · imovel_hub · condominios · permutas ·
                 empresas · matriculas · certidoes · agentes_financeiros · meta_ads · instagram · simec ·
                 media_creation · transcricoes · edicao_fotos · email_marketing · mailchimp · scheduling ·
                 youtube · n8n · atendimento_blocos · supervisao
routers/       → product-level routers (whatsapp*, chat, clientes, imoveis, campanhas, marcas, settings, …)
                 and the julia_* routers
services/      → julia_* services and the other product services
clients/       → agents.py (the agents channel client)
migrations/    → numbered SQL, applied with noctus.dev.migrate_product; migrations-applied.json is the ledger
```

### Frontend (`products/social-wiring/frontend/src/`)

`App.tsx` registers routes via `createProductApp()`; nav groups come from `nav/navGroups.ts`:
Principal · Julia (`nav/julia.ts`, `JULIA_PAGES`) · Imóveis · Leads (incl. Funil, Blocos do Atendimento,
Supervisão) · Clientes · Edição de Fotos · CoreStudio · Marketing · Emissões · Conexões · Configuração.
A page's nav item is gated by its `status_pagina` row (`julia_<page>` keys for the Julia group).
Julia pages live in `pages/julia/`, components in `components/julia/`, hooks `useJulia*`.

### Database

Schema `social_wiring`, RLS own-org plus service role on every table. An imóvel's condomínio is the FK
`imovel_dados.condominio_id` → `condominios` (migration 300) or `casa_de_rua = true` — never both, never a
free boolean (`em_condominio` is legacy read-only; read the derived value). The contract generator
(`carregador._empreendimento` / `_em_condominio`, `derivacao._condominio_do_imovel`) reads the link. A new Julia page needs its
`status_pagina` row in a migration, its entry in `JULIA_PAGES`, and its route in `App.tsx`.

## Seed seams consumed (do NOT re-implement product-locally)

- Chatbot buffer / message store — `noctusai_lib.domain.chatbot`; WhatsApp WAHA + Meta Cloud connector — `noctusai_lib.integrations.whatsapp`
- Google Calendar/Maps/Drive, Meta FB/IG, YouTube, Vista CRM — `noctusai_lib.integrations.*`
- Jobs queue (`social_wiring.jobs`) — `noctusai_lib.domain.jobs`; in-app notifications — `noctusai_lib.domain.notifications`
- Fernet credential vault — `noctusai_lib.security.token_store`
- Frontend WhatsApp hooks — `createWhatsAppConnectionHooks` / `createWhatsAppIntakeHooks` from `@noctusai/lib`

## Rules

- Cross-product capabilities live in the seed; SW composes them. Julia's reasoning lives in `agents`, not here.
- ONE container (`serve_spa`); do not bake `VITE_BACKEND_API_URL`; pass `VITE_SUPABASE_*` as build args.
- A Fake and a Real implementation for every IO seam; tests use the Fake (`FakeAgentsClient`, fake transports).
- Never edit an applied migration; rename or change through a new forward migration (see 287).
- pt-BR UI copy.

## Contract parties (matrícula-driven)

**Contract parties follow the matrícula.** A vendedor typed `proprietário` who is not among the matrícula's current owners (adquirentes of the last transfer act, `titulo_service.titularidade_atual`) blocks generation with `VENDEDOR_NAO_PROPRIETARIO` and the readiness names the right papel (cônjuge of an owner → anuente; doador in the chain → anuente); owners unknown checks nothing. When the sellers hold the imóvel by **doação** (adiantamento de legítima) the doadores are `anuente`s worded as such (`derivacao.doador_anuente`, no extra column); a spouse-anuente keeps its own wording. A CNH-only RG completes itself from the matrícula averbação (`card_hub/rg_matricula_service.py`, `rg_origem='matricula_averbacao'`), nacionalidade is inflected by gênero, and a certidão de casamento hands the linked cônjuge the couple's estado civil/regime/data.

## Testing

```bash
cd products/social-wiring/backend && pytest
cd products/social-wiring/frontend && npx vitest run
cd products/social-wiring/frontend && npx vite build   # must build clean
```

## Dependencies

- Backend: `noctusai_lib` + `noctusai_seed`; Frontend: `@noctusai/lib` + `@noctusai/seed`
- Runtime peer: `agents` (`/api/channels/*`)
