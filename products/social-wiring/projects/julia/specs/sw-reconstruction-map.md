# Lais → social-wiring reconstruction map

Where every Lais page lands in social-wiring (SW), page by page, and how the data wires into what SW already has. Written 2026-10-14, offline, from the private study (58 routes), `[private study: page-map]`, `[private study: mechanisms]`, `BUILD-ROADMAP.md`, `DECISIONS.md` and a read of SW code at `origin/dev` 6529ffa89. Every claim about SW code names the file it was checked in.

Same role as `../../core-studio/MENUS.md` + the module plan for Criação de Mídia: the build list, before building.

## 0 · Ground rules (owner decisions, `DECISIONS.md` + `specs/julia-agent-contract.md` §11)

- All Lais pages live in SW's sidebar group **Lais** (`LAIS_LABEL` in `frontend/src/nav/lais.ts`; adding a page = one entry in `LAIS_PAGES` + a `status_pagina` row + a route in `frontend/src/App.tsx`). The name will change; it is spelled once.
- The agent itself ("Julia", key `lead-imob`) lives in the **agents** product (`products/agents/backend/app/studio/lead_imob.py`, channel API `products/agents/backend/app/routers/channels_router.py`); SW owns transport (WAHA now, Cloud API later), routing, pages and data.
- Qualified leads go **into SW itself** (SW is the CRM), not to Vista. Real Lais keeps running on its own number.
- Everything personal-data-related is per org and swappable (keys, tokens, number, notice).

**Status legend:** **SHIPPED** live in prod · **PLANNED** in `BUILD-ROADMAP.md` pages 1–5 · **NEW** not yet in the roadmap (proposed here) · **EXISTS** an SW page already covers it (reuse, extend) · **NOT REBUILT** (reason given).

---

## 1 · Route-by-route map (58 routes, grouped by Lais' sidebar)

### 1.1 Início
| # | Lais route | What it is | SW target | Status | Reuses / tables | Depends on |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | `/` | Home: plan consumption, follow-up alerts, visit requests, funnel (chegaram → atendidos → encaminhados), leads by channel/hour/weekday, 6-month trend | **Lais › Painel** `/lais/painel` | NEW | SW leads analytics (`backend/app/modules/leads/routers/analytics.py`), `leads`, `lead_sources`, `whatsapp_chats` (mig 042), agents usage (`llm_usage`-style budget, `channel_daily_budget_usd`) | pages 2–4 (needs qualification + forwarding outcomes to be meaningful) |

### 1.2 Conversas and history
| # | Lais route | What it is | SW target | Status | Reuses / tables | Depends on |
| --- | --- | --- | --- | --- | --- | --- |
| 2 | `/chats` | 3-pane operator workspace; AI on/off; assignment; tags; notes; interactions; kanban; feedback | **Lais › Conversas** `/lais/conversas` (`frontend/src/pages/lais/Conversas.tsx` over `WhatsAppWorkspace.tsx`; Julia chip/pause/LGPD delete in `JuliaThreadHeader.tsx`) | SHIPPED (core) · NEW **Conversas v2** for the missing panes | `whatsapp_chats`, `whatsapp_connections`, `lais_agente_chats_preexistentes` (mig 258); for v2: `clientes`, `cliente_notas`, `cliente_tags`/`cliente_tag_links` (verified as tables in SW migrations) instead of new note/tag tables | v2 needs page 2 (slots) for the Interações panel |
| 3 | `/history` | Read-only conversation link opened with a 4-digit agency code | Deep link `/lais/conversas?chat=<id>` for logged-in org members | NOT REBUILT as-is (shared 4-digit code is weak auth); replaced by an authenticated deep link inside Conversas v2 | seed auth | Conversas v2 |

### 1.3 Gestão de leads
| # | Lais route | What it is | SW target | Status | Reuses / tables | Depends on |
| --- | --- | --- | --- | --- | --- | --- |
| 4 | `/leads` | Lead table: attendance, operation, channel, CRM status; send to CRM; export; remarketing | **EXISTS** `/leads` (`frontend/src/App.tsx` route; `backend/app/modules/leads/routers/leads.py`) | EXISTS — extend with a "Julia" source + attendance/qualification columns | `leads`, `lead_sources` (mig 025), `lead_corretores` | page 3 (Envio ao SW writes the lead) |
| 5 | `/leads-v3` | Successor of `/leads` | same as #4 | EXISTS | — | — |
| 6 | `/visits` | Visit requests (week view), confirm/reschedule/cancel | **EXISTS** `/agendamentos` (`frontend/src/App.tsx`), plus filter "Solicitadas pela Julia" | PLANNED (page 5) | `atendimento_agendamentos` (mig 061), `visitas`/`roteiros` (mig 082), seed scheduling `sched_*` (mig 001), `backend/app/modules/scheduling/engine.py` | page 5 |
| 7 | `/credit-analysis` | CredAluga credit checks for rentals | — | NOT REBUILT (partner integration, flag-off for this agency, extra LGPD burden) | — | owner decision later |

### 1.4 Gestão de imóveis
| # | Lais route | What it is | SW target | Status | Reuses / tables | Depends on |
| --- | --- | --- | --- | --- | --- | --- |
| 8 | `/captacao` (nav → `/notifications?type=lead-property-acquisition&view=acquisition`) | Feed of conversations where the person wants to list a property | **Lais › Captação** `/lais/captacao` → each item can become an `imovel_captacao` | NEW | `imovel_captacao` (mig 226, table already exists for manual captação) | intent classification (page 2 extraction) + notifications (§1.6) |
| 9 | `/owners` | Bubble: conversations with owners to refresh listings | **Lais › Atualização de imóveis** `/lais/proprietarios` | NEW (late) | `imovel_proprietarios` (mig 183), `imoveis` (mig 040) | outbound to owners = needs templates/Cloud API (#32); WAHA bulk outbound risks a ban |
| 10 | `/developments` | Developments catalogue the agent uses | **EXISTS** `/imoveis` (empreendimento fields, mig 158) — read by Julia as knowledge | EXISTS (data) · NEW tool for Julia to read it | `imoveis`, `imovel_dados` | page 1 / property tool |
| 11 | `/properties` | Integrated listings (XML shelf) | **EXISTS** `/imoveis` (Vista mirror, `backend/app/routers/imoveis_router.py`) | EXISTS — NEW: Julia property-search tool over it | `imoveis` | page 1 |
| 12 | `/catalogs` | Meta product catalog | — | NOT REBUILT (flag-off; Meta catalog is a separate marketing project) | — | — |

### 1.5 Relatórios
| # | Lais route | What it is | SW target | Status | Reuses / tables | Depends on |
| --- | --- | --- | --- | --- | --- | --- |
| 13 | `/relatorio-v2` | Demand vs shelf by property type, top listings, top bairros | **Lais › Relatórios** `/lais/relatorios` | NEW (late) | slot values per lead (page 2) × `imoveis` | page 2 |
| 14 | `/relatorio-v3` | Successor | same | NEW | — | — |
| 15 | `/performance` | Developer-agency report (Bubble) | — | NOT REBUILT (agency type `developer` only) | — | — |
| 16 | `/avaliacoes` | Google review requests + dashboard | **Lais › Avaliações** `/lais/avaliacoes` | NEW (late) | SW Google OAuth (`backend/app/routers/google_router.py` — scopes only today; Business Profile API not integrated) | Google Business Profile integration; a "good conversation" signal |
| 17 | `/atendimento-administrativo` | Admin add-on report (boletos, ocorrências, ERPs) | — | NOT REBUILT (add-on for property managers; One does not use it) | — | — |

### 1.6 Notificações and campaigns
| # | Lais route | What it is | SW target | Status | Reuses / tables | Depends on |
| --- | --- | --- | --- | --- | --- | --- |
| 18 | `/notifications` | Event feed (new qualified lead, visit request, cobrança, captação, reports, remarketing) + "notify lead ready" toggle | **Lais › Notificações** `/lais/notificacoes` | NEW | seed in-app notifications `write_in_app` (`seed/lib/backend/noctusai_lib/domain/notifications.py`, already used by Julia's handoff in `backend/app/services/lais_agente_service.py`); WhatsApp alerts via `notification_recipients`/`notification_log` (mig 001) | handoff (shipped) is event #1; others arrive with pages 3–5 |
| 19 | `/smart-campaigns` | Meta CAPI qualification signals, CPL/CPQL | **EXISTS** `/meta` + `/campanhas` for ads; CAPI signals = NEW | NEW (late) | `backend/app/modules/meta_ads/routers/ads_router.py`, `campanhas`/`campanha_veiculacoes` (mig 065) | page 3 (qualified event) |
| 20 | `/smart-campaigns/remarketing` | Remarketing wizard on top of CAPI | — | NOT REBUILT now (flag-off; folds into #21) | — | — |
| 21 | `/broadcasts` | Bulk WhatsApp: remarketing + Atualização de anúncios | **Lais › Disparos** `/lais/disparos` | NEW (late) | SW email campaigns pattern (`/email/campanhas`), `contact_lists` (mig 001) | Cloud API + approved templates (#32); WAHA bulk sends are a ban risk |

### 1.7 Minha Lais (configuration)
| # | Lais route | What it is | SW target | Status | Reuses / tables | Depends on |
| --- | --- | --- | --- | --- | --- | --- |
| 22 | `/configs` | Hub of config cards | **Lais › Configurações** `/lais/configuracoes` (`frontend/src/pages/lais/Configuracoes.tsx`, today the WhatsApp connections) + **Lais › Agente** `/lais/agente` (`frontend/src/pages/lais/Agente.tsx`) | SHIPPED — becomes the card hub as pages 1–5 land | `whatsapp_connections`, `lais_agente_*` | — |
| 23 | `/configs_behavior` | Bubble: Perguntas essenciais + Envio ao CRM policies | **Lais › Perguntas** `/lais/perguntas` + **Lais › Envio ao SW** `/lais/envio` | PLANNED (pages 2, 3) | seed `domain/chatbot/summary.py` (structured extraction), agents studio compiler | page 0 |
| 24 | `/configs_my_business` | Bubble: typed knowledge base (Geral · Vendas · Locação) | **Lais › Conhecimento** `/lais/conhecimento` | PLANNED (page 1) | agents studio compiler `products/agents/backend/app/studio/compiler.py`, studio knowledge router | page 0 |
| 25 | `/configs_whatsapp_profile` | Bubble: number's profile photo, description, about | card in Conhecimento (profile text) + WAHA profile on the connection | PLANNED (page 1) | `backend/app/routers/whatsapp_connections_router.py` | page 1 |
| 26 | `/configs_property_info` | Full address / IPTU switches | two switches in Conhecimento | PLANNED (page 1) | `imoveis` | property tool |
| 27 | `/configs_qualification` | Rule builder (OR of AND) for the CRM push | part of **Lais › Envio ao SW** | PLANNED (page 3) | `leads_service.create_lead` + trigger `spawn_funil_card` (mig 240) | page 2 |
| 28 | `/configs_visits` | Visit pre-scheduling settings | **Lais › Visitas** `/lais/visitas` (settings) | PLANNED (page 5) | `backend/app/modules/scheduling/engine.py`, `sched_*` | page 5 |
| 29 | `/configs_visits_embed` | Same, embedded in Bubble | same | PLANNED | — | — |
| 30 | `/configs_display_attendant_name` | Prefix human messages with the sender's name | switch in Configurações | NEW (small) | `whatsapp_outbound.py` (`backend/app/services/`) | — |
| 31 | `/configs_reengage` (+ `/configs_reengage/rules/:id`) | Two-tier reengage + réguas | **Lais › Reengajamento** `/lais/reengajamento` | PLANNED (page 4) | seed `jobs` (`seed/lib/backend/noctusai_lib/domain/jobs`) | page 0 |
| 32 | `/configs_templates` | WhatsApp templates (Meta) | **Lais › Modelos** `/lais/modelos` | NEW (late, with Cloud API) | seed `integrations.whatsapp` MetaCloudClient (send_text only today) | Cloud API transport |
| 33 | `/configs_meta_integration` | Meta Lead Ads forms → Lais | **EXISTS** `/meta` + `/api/meta/leadgen` (`backend/app/modules/meta_ads/routers/leadgen_router.py`) — NEW: route Meta form leads to Julia for first contact | EXISTS + NEW wiring | `meta_ads_leads` (mig 033) | page 3 + outbound first contact |

### 1.8 Usuários, plano, conta, onboarding
| # | Lais route | What it is | SW target | Status | Reuses / tables | Depends on |
| --- | --- | --- | --- | --- | --- | --- |
| 34 | `/acessos` | Users, seats, teams, TPR, distribution | **EXISTS** `/equipe` (`frontend/src/pages/Equipe.tsx`); distribution (roleta) = **Lais › Distribuição** `/lais/distribuicao` | EXISTS + NEW (late) | seed org members; `lead_corretores` (`backend/app/modules/leads/routers/corretores.py`) | page 3 |
| 35 | `/user-management` | Bubble users page | same as #34 | EXISTS | — | — |
| 36 | `/add-ons` | Vendor add-on catalogue | — | NOT REBUILT (vendor commerce) | — | — |
| 37 | `/add-ons/pro` | Pro add-on onboarding | — | NOT REBUILT (teams fold into #34) | — | — |
| 38 | `/add-ons/smart-campaigns` | Add-on sales page | — | NOT REBUILT | — | — |
| 39 | `/add-ons/administrative` | Add-on sales page | — | NOT REBUILT | — | — |
| 40 | `/pacotes-adicionais/gestao-de-atendimentos-pro` | Alias of #37 | — | NOT REBUILT | — | — |
| 41 | `/financeiro` | Vendor plan, credits, invoices | usage card on **Lais › Agente** (tokens/cost per day vs cap) | NOT REBUILT as billing · NEW small usage card | agents budget (`channel_daily_budget_usd`) | — |
| 42 | `/plans` | Bubble plans page | — | NOT REBUILT | — | — |
| 43 | `/perfil` | User profile (phone, role, area) | seed account/profile | EXISTS (seed) | — | — |
| 44 | `/checklist` | Onboarding checklist | setup steps on **Lais › Agente** | EXISTS (Agente page shows the setup cards) | `frontend/src/pages/lais/Agente.tsx` | — |
| 45 | `/onboarding` | First-login profile | — | NOT REBUILT (vendor onboarding) | — | — |
| 46 | `/onboarding/sucesso` | Same | — | NOT REBUILT | — | — |
| 47 | `/creation-user-test` | Forced test lead for new agencies | "Testar conversa" in the agents studio test chat | EXISTS (agents studio) | `products/agents` studio | — |
| 48 | `/platform` | Bubble onboarding platform | — | NOT REBUILT | — | — |
| 49 | `/platform-meeting-schedule` | Book an onboarding call | — | NOT REBUILT | — | — |
| 50 | `/whats-new` | Vendor changelog | — | NOT REBUILT | — | — |
| 51 | `/trainings` | Bubble trainings | — | NOT REBUILT (later: help content) | — | — |
| 52 | `/trainings_page` | "Guia da Lais" videos | — | NOT REBUILT | — | — |
| 53 | `/access-code` | Access-code session for history links | — | NOT REBUILT (weak auth, see #3) | — | — |
| 54 | `/debug` | Internal | — | NOT REBUILT | — | — |
| 55 | `/facebook/callback` | Meta OAuth callback | **EXISTS** SW Meta OAuth (`backend/app/routers/_oauth_state.py`, `/meta`) | EXISTS | — | — |
| 56 | `/unauthorized` | Error page | seed | EXISTS (seed) | — | — |
| 57 | `/auth/signin` | vendor SSO sign-in | seed SSO login (`frontend/src/pages/Login.tsx`) | EXISTS (seed) | — | — |
| 58 | `/auth/error` | Auth error | seed | EXISTS (seed) | — | — |

### 1.9 Counts (primary status per route; 58 total)
| Status | Count | Routes |
| --- | --- | --- |
| SHIPPED | 2 | #2 Conversas (core), #22 Configurações/Agente |
| EXISTS in SW (reuse/extend) | 14 | #4, 5, 10, 11, 33, 34, 35, 43, 44, 47, 55, 56, 57, 58 |
| PLANNED (roadmap pages 1–5) | 9 | #6, 23, 24, 25, 26, 27, 28, 29, 31 |
| NEW (not in the roadmap) | 11 | #1, 8, 9, 13, 14, 16, 18, 19, 21, 30, 32 |
| NOT REBUILT | 22 | #3 (as-is), 7, 12, 15, 17, 20, 36–42, 45, 46, 48–54 |

Two NEW extensions ride on existing rows: **Conversas v2** (on #2) and **Distribuição** (on #34).

--- | --- |
| SHIPPED (Conversas, Configurações/Agente) | 2 (#2 core, #22) |
| EXISTS in SW (reuse/extend) | 16 (#4, 5, 10, 11, 33, 34, 35, 43, 44, 47, 55, 56, 57, 58, and the data side of #6 and #19) |
| PLANNED (roadmap pages 1–5) | 9 (#6, 23, 24, 25, 26, 27, 28, 29, 31) |
| NEW (not in the roadmap) | 11 (#1, 8, 9, 13, 14, 16, 18, 21, 30, 32, + Conversas v2 / Distribuição as extensions of #2 / #34) |
| NOT REBUILT | 22 (#3 as-is, 7, 12, 15, 17, 20, 36–42, 45, 46, 48–54) |

Some routes carry two statuses (an existing page plus new wiring); the counts use the primary one, so they add to 60.

---

## 1.10 · Owner decisions that change this map (2026-10-15, `DECISIONS.md`)

- **Histórico do cliente** → no shared 4-digit code. A per-conversation link (`/lais/conversas/<id>`-style) that opens only after login, and only for the conversation's owner (assigned attendant / connection owner) or an org owner/admin; same-org members without ownership get 403, other orgs never resolve it. Lives in **Conversas v2 (wave 7)**.
- **Distribuição (wave 11)** → SW stores teams, members, mode (**Via Lais** = Julia assigns at handoff / **Via CRM-equivalent** = card created unassigned in the funil) and "keep last responsible"; **Julia reads it** through the agents API at handoff (SW is the source of truth).
- **Análise de crédito** and **Avaliações no Google** → moved from "not rebuilt" to **NEW (build)**, late waves (13+); credit analysis needs a provider choice + an LGPD consent step.
- **Cloud API pages (wave 12)** wait for the owner's Meta app verification.

## 2 · Proposed build order (extends `BUILD-ROADMAP.md` 0–5)

| Wave | Page (Lais ›) | Why here |
| --- | --- | --- |
| 0 | Agente — SHIPPED 2026-10-14 | Julia exists |
| 1 | Conhecimento (+ WhatsApp profile text, address/IPTU switches) | answers grounded in typed facts |
| 2 | Perguntas (slot catalogue + extraction) | everything downstream reads slots |
| 3 | Envio ao SW (rules, cold/invalid/captação policies, lead + card) | the business value: qualified leads in the funnel |
| 4 | Reengajamento | recovers silent leads |
| 5 | Visitas (pre-scheduling) | visits into `/agendamentos` |
| **6** | **Notificações** (in-app + WhatsApp alerts; events from waves 3–5) | humans react to what Julia produces |
| **7** | **Conversas v2** (Interações panel with summary + slots, notes, tags, assignment, authenticated history link, attendant-name prefix) | operator parity with Lais' workspace |
| **8** | **Captação** (intent → `imovel_captacao`) | uses wave 2 intents + wave 6 events |
| **9** | **Painel** (funnel + channels + consumption) | needs waves 2–4 outcomes to show real numbers |
| **10** | **Relatórios** (demand vs shelf, bairros) | needs a month of slot data |
| **11** | **Distribuição** (roleta / last attendant per team) | after the funnel volume justifies it |
| **12** | **Modelos + Disparos + Atualização de imóveis + Meta form leads first contact** | all need WhatsApp Cloud API + approved templates |
| **13** | **Avaliações** (Google review requests) and **CAPI signals** | external integrations, last |

---

## 3 · Cross-module wiring (Lais data → SW tables)

| Lais concept | SW destination | How | Verified in |
| --- | --- | --- | --- |
| Inbound WhatsApp message | `whatsapp_chats` + message store; routed to Julia when the connection has the agent on and the chat is not pre-existing/authorized | `_process_waha_body` routing → agents `POST /api/channels/turns` | `backend/app/routers/whatsapp_router.py`, `backend/app/services/lais_lead_dispatcher.py`, mig 258 |
| Portal lead (Grupo OLX/Zap, ImovelWeb) | `leads` (+ outbox forwarding) | existing portal webhooks; NEW: hand the phone to Julia for first contact | `backend/app/modules/portal_leads/routers/olx_webhook.py`, `imovelweb_webhook.py`, mig 066 |
| Meta Lead Ads lead | `meta_ads_leads` → `leads` | existing leadgen ingest; NEW: Julia first contact | `backend/app/modules/meta_ads/routers/leadgen_router.py`, `backend/app/modules/leads/routers/meta_ingest.py` |
| Qualified lead ("Enviado ao CRM") | `leads` (source = Julia) → trigger `spawn_funil_card` → `atendimentos` card in `/funil` | page 3; idempotent per phone | mig 025, 240; `atendimentos` = renamed `negociacoes_venda` (mig 060) |
| Lead ↔ person | `clientes` (person layer) via the lead | existing cliente identity linking | mig 048, 220 (`chat_cliente_link`) |
| Interaction summary + slots | NEW `lais_interacoes` (per chat episode: summary, slots JSON, intent flags, outcome) → copied into the card note | page 2/3 | — (new) |
| Visit request | `atendimento_agendamentos` / `visitas` | page 5 tool proposes slots from `SchedulingEngine` | mig 061, 082; `backend/app/modules/scheduling/engine.py` |
| Captação | `imovel_captacao` | wave 8 | mig 226 |
| Owner update answers | `imovel_proprietarios` / `imoveis` status | wave 12 | mig 183, 040 |
| Handoff / cobrança / new qualified lead / visit request | seed in-app notifications + WhatsApp alert to the connection owner (or the swapped admin) | shipped for handoff (contract §11.4) | `backend/app/services/lais_agente_service.py` (`write_in_app`) |
| Internal notes, tags | `cliente_notas`, `cliente_tags` | Conversas v2 | migrations listing `cliente_notas`, `cliente_tag_links` |
| Assignment / distribution | `lead_corretores` + org members | wave 11 | `backend/app/modules/leads/routers/corretores.py` |
| Knowledge base (Meu negócio) | agents studio typed sections (per org) → compiled prompt → published version | wave 1 | `products/agents/backend/app/studio/compiler.py` |
| Property answers | `imoveis` (Vista mirror) read through an agent tool | wave 1 | `backend/app/routers/imoveis_router.py` |
| Usage / cost | agents per-org budget + daily cap | shipped | agents A1/A2 (`llm_daily_budget_usd`, `channel_daily_budget_usd`) |

---

## 4 · Mismatches with `BUILD-ROADMAP.md`

1. The roadmap's page-0 row still describes an SW-local runtime ("`agent_mode ∈ {operator, lead}`", `LeadAgentService`); what shipped is the agents-product runtime (contract v3). The row says "supersedes", but the "Main pieces" text is stale.
2. Its header "No code yet" is stale — page 0 is in prod (2ca3372b5).
3. It lists nothing for Notificações, Conversas v2, Captação, Painel, Relatórios, Distribuição — waves 6–11 above are new.
4. It calls page 3 "Envio ao SW" but the Lais policies (cold leads, invalid WhatsApp, captação) are not listed there; they belong in page 3.
5. "Later (not scheduled)" groups templates with broadcasts; templates are also a prerequisite for Meta-form first contact and owner updates (wave 12).
