# Lais — Page Map v2 (authoritative)

Built 2026-10-14, **offline**, from material already held: the live UI pass of 2026-10-13 (`specs/page-map.md`), the static analysis of 130 production chunks (`analysis/routes.md`, `endpoints.{md,json}`, `flags-permissions.md`, `domain-model.md`, `mocks.md`, `bubble-embeds.md`, `realtime-and-integrations.md`), the Bubble app definition read from `window.app` (`analysis/bubble-app-definition.md`), the agent's configuration (`analysis/agent-brain.md`) and the read-only GET shapes (`captures/xhr-2026-10-13/README.md`). No browser, no network call to Lais and no lead or chat content were used to write it.

Where this file and `specs/page-map.md` disagree, **this file wins**; each disagreement is listed in §0.2. For exhaustive code detail (every copy string, zod rule, error code) the section links to `analysis/routes.md`; this file carries the page → element → data → endpoint → safety chain.

Companion files: `analysis/agent-brain.md` (how the AI is configured), `analysis/bubble-app-definition.md` (Bubble edit forms), `analysis/endpoints.json` (230 endpoints, machine-readable).

## 0 · How to read this

### 0.1 Tags

| Tag | Meaning |
| --- | --- |
| **C** (CONFIRMED) | Seen live, in a chunk, in the Bubble definition, or in a captured response shape. |
| **I** (INFERRED) | Reasoned from code shape, naming or data correlation; not seen working. |
| **U** (UNKNOWN) | Cannot be determined from what we hold; listed in §N. |

Coverage tag, one per route:

| Coverage | Meaning |
| --- | --- |
| **LIVE** | Rendered and seen in the owner's session on 2026-10-13. |
| **BUBBLE-DEF** | Fields and save calls read from the Bubble `window.app` definition (no live data needed). Used together with LIVE when the page body is Bubble. |
| **CODE** | Known from the bundle only; renderable for this agency but not visited. |
| **GATED** | A flag, plan, agency type or onboarding state keeps it from rendering for this agency; code-only is final. |
| **NOT-CAPTURED** | In the route manifest, but no chunk was downloaded; contents unknown. |

Safety (from `endpoints.json`): **R** READ · **W** WRITE · **S** SEND (WhatsApp message, AI on/off or human takeover) · **A** AUTH. `S-I` = SEND-class by inference.

All BFF paths are relative to `https://bff.lastro.services/api/v1`. "Core" = `{ver}.lastro.services/api/v1/real-estate-agency/{agency}/…`, "Core AI" = `{ver}-ai.lastro.services/…` (called from Bubble only).

### 0.2 Corrections and contradictions

| # | Earlier claim (source) | What holds (evidence) |
| --- | --- | --- |
| 1 | Pré-agendamento de visita saves through Bubble `behavior-settings` (`bubble-app-definition.md` §4). | **Two writers.** The native page `/configs_visits` (module 1647) does `PUT /web/agency/settings/visits` with `{mode, general|perOperation}`; the Bubble drawer still writes `behavior-settings`. Which one the agent reads is **U**. C both. |
| 2 | Reengajamento em horas: options 1–11 h (`bubble-app-definition.md`, `agent-brain.md`). | Native mock offers 1/2/4/8/12/24 h; Bubble offers 1–11 h. The live list comes from `GET /web/reengage/configs/delay-minutes?reengageType=final` (captured 200, values not recorded). Treat the server list as truth; **U** which UI the owner sees. |
| 3 | Réguas: "até 5 tentativas para compra ou até 3 para locação" (list helper text). | Validation caps at **3** ("Limite de 3 tentativas de contato automatizadas."); the live card says "até 3 tentativas". C (the helper text is stale). |
| 4 | Flag `reengage-rules` defaults to false, so the Réguas tab is hidden (`flags-permissions.md`). | The tab is **LIVE** for this agency ⇒ the flag is on for it. Same reading for `leads-view` (native Leads table seen) and `new-relatorio-view` (native Bairros/Imóveis tabs seen); `new-development-page-front` is **off** (Bubble Empreendimentos seen). I (from rendered shape). |
| 5 | Visits list "`view=month` is rejected" (`agent-brain.md` §6). | The calendar code calls `GET /web/visits?view=…&date=yyyy-MM` for its month view. Either the backend rejects month and the month view errors, or the S2 call used a wrong date format. **U**. |
| 6 | Flow `add-team` step slug `go-acess`; `connect-origins` has 0 steps (`routes.md` Part C §5). | API returns `go-access` and a step `confirm-origins` (S2 shapes). The client slug `go-acess` is a typo that may never complete the step. C (both sides) / I (effect). |
| 7 | `blockBehavior ∈ {hide, readonly}` (code). | API returns `hide | disable`. C. |
| 8 | Notification inbox `/web/notifications` and chat transfers `/web/chats/:id/transfers` exist (code + mocks). | Both **404 live** ("page not found"); mock-only or not deployed. C. |
| 9 | Two "Usuários e equipes" pages (`page-map.md` §20 Bubble and §25 native). | Sidebar points to native **`/acessos`**; Bubble `/user-management` ("Acessos") is reachable by URL only. C. |
| 10 | Qualificação e Envio ao CRM › Envio ao CRM has 3 policies (`page-map.md`). | The Bubble definition shows **5** sections: Envio automático de leads qualificados (per operation), Leads frios, Potenciais captações, WhatsApp inválido, Pesquisa com clientes. C (BUBBLE-DEF). |
| 11 | Archive is WRITE (`endpoints.json`). | Archiving shows "A Lais irá assumir o atendimento nesta conversa": it hands the chat back to the AI ⇒ **S-I**. Same for kanban-move to `archived`. |
| 12 | Pro extra seat R$ 24,45 (mock). | UI constant R$ 24,50 (was 49,00). C. |
| 13 | Leads table paginates 10/page (`page-map.md`). | Sizes 10 · 25 · 50; default 10. C. |
| 14 | Users table columns Usuário · Nível de acesso · Assento · Status (live). | Code header set is Nome · E-mail · Cargo · Assento · Status; the live table merges name+e-mail into one cell. Cosmetic. C. |
| 15 | Pré-agendamento data = `/web/visits/config` (`page-map.md`). | `/web/visits/config` only says `{enabled}` (also used by `/configs_qualification` to lock the "Visita" criterion); the editor reads `/web/agency/settings/visits`. C. |
| 16 | Perguntas essenciais: "Perguntas ativas (0)" — empty for this agency (`page-map.md`). | The S2 GET `required-information/selected` returned **5** selected (2 qualifying) (`agent-brain.md` §2). Either the Bubble card counts something else or it rendered before data arrived (no token in the standalone tab). **U** — re-check live. |
| 17 | Visits config `daysToOffer` default 7 (code). | This agency stores 3. Config, not a contradiction; listed so nobody copies the default as truth. |

### 0.3 Categories

`Shell` · `Atendimento` (conversations, history, notifications) · `Leads` · `Visitas` · `Disparos` · `Imóveis` (captação, owners, developments, integrated properties, catalog) · `Relatórios` · `Configuração da IA` · `Equipe` · `Conta/Plano` · `Onboarding` · `Integrações` (Meta, smart campaigns).

### 0.4 Sidebar

Live (2026-10-13, accordion, one group open at a time; collapses to an icon rail on `/chats`) **C**:

```
Início                                  /
Conversas                               /chats
Disparos em massa                       /broadcasts            (flag broadcasts-enabled)
Gestão de leads ▾   Leads               /leads
                    Visitas             /visits
Gestão de imóveis ▾ Captação            /notifications?type=lead-property-acquisition&view=acquisition
                    Atualização de imóveis  /owners           (Bubble)
                    Empreendimentos     /developments          (Bubble for this agency)
Relatórios ▾        Bairros e imóveis   /relatorio-v2
                    Avaliações no Google /avaliacoes
Minha Lais                              /configs
Usuários e equipes                      /acessos
Pacotes adicionais [NOVO]               /add-ons
Plano e cobranças                       /financeiro
Guia da Lais                            /trainings_page
Ajuda                                   (Intercom launcher)
```

Nav items in code that this agency does not see (GATED, §0.1): Análise de crédito `/credit-analysis` · Imóveis integrados `/properties` · Campanhas ▾ Campanhas inteligentes `/smart-campaigns`, Catálogo Meta `/catalogs` · Relatórios ▾ Atendimento administrativo `/atendimento-administrativo`, Desempenho `/performance` (developers only) · Notificações `/notifications` (menu item for the `attendant` role only; others use the bell) · "Primeiros passos" icon `/checklist` (while onboarding flows are incomplete). Grouping of the hidden items is I.

Header (every page): agency card ("Lais da <agência>"), breadcrumb, **Novidades** `/whats-new`, bell `/notifications`, user menu (initials). Routes reachable only by URL or deep link: `/leads-v3`, `/relatorio-v3`, `/history`, `/user-management`, `/perfil`, `/plans`, `/trainings`, `/captacao`, `/configs_*`.

---

## 1 · Shell (every page) — category `Shell` — LIVE + CODE

| Element | What it is | Data source | Endpoints | Safety | Ev |
| --- | --- | --- | --- | --- | --- |
| Session | NextAuth JWT (Keycloak `sso.lastro.services`, realm `lastro-prod`, client `casa-da-lais`); bearer + `x-agency-id` on every BFF call | `/api/auth/session` | `/api/auth/*`, Keycloak token refresh | A | C |
| Agency (REA) switcher | "Meus negócios", search "Buscar página ou imobiliária..." (≥3 chars), Copiar ID / Copiar nome; selection in `localStorage casa-da-lais:selected-rea-id` | XHR | `GET /auth/users/me`, `GET /auth/users/me/profile`, `GET /auth/agencies/search?q=` | R | C |
| Shell GETs | agency details/settings, permissions (+teams), premium subscription, smart-campaigns onboarding, test users, 4 onboarding flows, overdue invoices, plan consumption | XHR on every page | `GET /web/agency/details`, `/web/agency/settings`, `/web/permissions`, `/web/permissions/teams`, `/web/subscription/premium`, `/web/smart-campaigns/onboarding-state`, `/web/test-users`, `/web/flows/{chat-control,add-team,connect-origins,reachout-leads}/onboarding-progress`, `/web/finance/invoices?status=overdue`, `/web/agency/charts/plan-consumption` | R | C |
| Route guard | nav rule order: Lastro bypass → flag → agency type → administrative add-on → role → `team:view-page` → page permission; denied ⇒ first allowed nav href or `/` | client | — | — | C |
| 402 interceptor | BFF `premium_module_required` ⇒ `location.replace("/add-ons/pro")` (exempt `/add-ons/pro`, `/acessos`) | client | any | — | C |
| Smart-suggestion popup "OPORTUNIDADE" | e.g. "Dispare o Remarketing para N leads" [Depois] [Ir para Disparos]; types remarketing · property_owner_update · remarketing_development; shown 30–180 s after load when plan consumption < 85 % | XHR | `GET /web/agency/smart-suggestions`; **Depois / dismiss / CTA** ⇒ `POST /web/agency/smart-suggestions/:id/cooldown` | R · **W** | C (seen live: "Remarketing para 105 leads") |
| Overdue-invoice banner | "Ver boletos →"; close ⇒ `POST /web/agency/settings {dismissOverduePaymentSlipAlert:true}` | XHR | as listed | W | C (code; not seen live) |
| Novidades banner | `whats_new_banner_{see_news,dismiss,snooze}` | XHR | `GET /web/whats-new` | R | C (code) |
| Notifications socket + favicon badge | `wss://eventhub.lastro.services/ws/notifications` event `notification:created`; OS notifications behind flag `browser-notifications-front` | WS | — | R | C |
| Intercom ("Ajuda") | identity hash via `POST /api/intercom {user_id}`; not booted for attendants | XHR | `/api/intercom` | R | C |
| Analytics | `/api/analytics` batch + Amplitude | XHR | `/api/analytics` | W (telemetry) | C |
| Maintenance / offline / mobile screens | flag `em-manutencao`; `HEAD /favicon.ico` probe; "Baixar o aplicativo" (App Store / Play) on mobile | client | — | — | C (code) |
| Attendant redirect | role `attendant` ∧ flag `attendant-app-migration`=false ⇒ `atendimento.casa.lais.ai` | client | — | — | C (code) |
| Forced redirects | `/platform` when agency `status=onboarding` ∧ module `onboarding_automatizado`; `/onboarding` when `profile.needsOnboarding`; `/creation-user-test` → `/checklist` for non-exempt agencies without a test lead | client | — | — | C (code) |
| GAP | user menu contents (beyond logout) not opened; Novidades banner not seen | — | — | — | U |

---

## 2 · Início — `/` — `Shell` — LIVE

Native. Gate `home:read`. Params `?month=&year=` (kept by `history.replaceState`). Purpose: monthly dashboard of plan use, lead funnel and channels.

| Element | Detail | Data source | Endpoint | Safety | Ev |
| --- | --- | --- | --- | --- | --- |
| Header | agency name (blurred when "hidden values" on), "Recarregar dados", month picker | — | — | — | C |
| Category tabs (charts) | Visão geral `all` · Compra `buy` · Aluguel `rent` · Administrativo `administrative` → `category=` on chart calls | — | — | — | C (code) |
| **Atividades** | Consumo do plano (anual) `used/total` → `/financeiro` (admin/internal only) · Cobranças de atendimento (count) → `/notifications?type=lead-user-demanding-followup-notification` · Pré-agendamento de visitas (count) → `/visits` | XHR | `GET /web/finance/consumption?referenceMonth=YYYY-MM-01`, `GET /web/agency/charts/alerts?month&year` | R | C |
| **Destaques** carousel | banners sorted by `displayOrder`; fallback `relatorio_default` → `/relatorio-v2` | XHR | `GET /web/banners/home` | R | C |
| **Personalizações de comportamento [NOVO]** | cards Pré-agendamento de visita (→ `/configs_visits?type=visit`) · Perguntas essenciais (→ Bubble `configs_behavior`) · Reengajamento (→ `/configs_reengage?type=reengagement`); "Conferir todas" → `/configs` | static | — | — | C |
| **Dados gerais de atendimento** | Topo de funil = `uniqueClients` · Atendimentos = `uniqueClients − unattendedConsumption` · Encaminhados = `qualifiedConsumption` | XHR | `GET /web/agency/charts/lead-summary` | R | C |
| Leads por canal | per origin: total, sent, topStatus | XHR | `…/charts/leads-by-channel` | R | C |
| Status por canal | Enviado ao CRM (`enhanced`) · Não pronto (`message-replied`) · Erro no envio (`enhanced-error`) | XHR | `…/charts/lead-status-by-channel` | R | C |
| Leads por horário no mês | `hours[{hour,count}]`, % outside business hours | XHR | `…/charts/leads-per-hour` | R | C |
| Leads semanais | best weekday | XHR | `…/charts/leads-per-weekday` | R | C |
| Leads nos últimos 6 meses | Enviado vs Não enviado ao CRM | XHR | `…/charts/leads-last-six-months` | R | C |
| States | "Nenhum dado disponível", "Tentar novamente", "Falha ao carregar os banners de destaque" | — | — | — | C (code) |
| GAP | other months; category tabs other than Visão geral; carousel slides 2–3 | — | — | — | — |

---

## 3 · Conversas — `/chats` — `Atendimento` — LIVE

Native, package `@lastro/chat`. Gate `chat:view`. Params `?chatId=` (**assume flow: may `POST …/user-assignment` — never open such links**), `?phoneNumber=`, `?view=kanban` (stripped on mount). Purpose: the operator workspace over every WhatsApp conversation, with the AI ⇄ human switch. Detail: `analysis/routes.md` Part A §2.

### 3.1 List pane

| Element | Detail | Endpoint | Safety | Ev |
| --- | --- | --- | --- | --- |
| Title, view toggle | "Conversas"; Ver como lista · Ver como kanban | — | — | C live |
| Tabs | Todas `all` · Minhas `mine` · Arquivadas `archived` (Todas hidden without `chat:view-all`) | `GET /web/chats/agency?limit=15&page&…&assignedToMe&archived` | R | C live |
| Pinned | max 5, "Conversas fixadas"; `localStorage @lastro/chat:pinned-chats` | `GET /web/chats/agency?pinned=true&limit=5`, `PATCH /web/chats/:id/pin {pinned}` | R · W | C |
| Search | contacts / messages | `GET /web/chats/agency/search?searchText&searchIn&…` | R | C (code) |
| Filter drawer "Filtro de conversas" | Operação (Aluguel `rent` · Compra `buy` · Administração `administrative` · Atualização `propertyowner`) · Status CRM (`sent_to_crm` · `not_ready`) · Status de atendimento (Lais atendendo `suspended=false` · Atendimento manual `true`) · Análise de crédito (flag off) · Responsável (Pro; "Sem responsável" + users) · Equipe (Pro) · Etiquetas (+ "Sem etiqueta" behind flag `chat-filter-without-tags`) · [Limpar] [Filtrar] | `GET /auth/users?skipInternal=true`, `GET /web/teams`, `GET /web/tags` | R | C live (tag filter seen in code only) |
| Card | name, phone, time, unread dot, channel icon, operation chip, "Atendimento manual" badge, ⋮ menu: Fixar · Marcar como lido/não lido | `PATCH /web/chats/:id {unread}` | W | C |
| "+ Nova conversa" drawer (3 steps) | 1 Nome da pessoa + Número (`validate-phone` → valid · invalid · existing · archived · blocked · error) → 2 template → 3 params; editor/admin only | `GET /web/chats/agency/validate-phone`, `GET /web/chats/new/messages/template/draft`, **`POST /web/chats/new/messages/human/template`** | R · **S** | C (code); GAP: drawer never opened live |

### 3.2 Kanban mode — `/chats?view=kanban`

| Element | Detail | Endpoint | Safety | Ev |
| --- | --- | --- | --- | --- |
| Default column "Todas (n)" + eye toggle; collapsed "Arquivadas" lane | visibility in `localStorage kanban_defaultHidden_<user>` | `GET /web/kanban/columns` | R | C live |
| "+ Adicionar coluna" | column per tag (`{kind:"tag",tagID}`) or smart "Sem etiqueta"; ≤50 columns | `POST /web/kanban/columns`, `DELETE …/:id`, `PATCH …/reorder` | W | C (code); GAP popover not opened |
| Drag a card | `{from,to}` targets default · archived · smart · tag | `POST /web/chats/:id/kanban-move` | W / **S-I** (to archived) | C (code) |

### 3.3 Conversation pane

| Element | Detail | Endpoint | Safety | Ev |
| --- | --- | --- | --- | --- |
| Header | lead name, "Atribuir responsável ▾" (user or team) | `POST /web/chats/:id/user-assignment`, `…/team-assignment` | **S** (human routing) | C live |
| Header actions | Gostei · Não gostei (`POST /web/chats/:id/feedback {reaction}`) · Deixar feedback (dialog, comment ≤300) · Copiar link do histórico (client) · Chamar no WhatsApp (client) · Enviar ao CRM (`PATCH /web/leads/:leadId/enhance/force`) · Bloquear número (reason 0–3 + details ≤500 → `POST /web/users/block`) · Arquivar (`PATCH /web/chats/:id {archived}`) | as listed | W · W · — · — · **W + CRM** · W · **S-I** | C live (buttons) / code (payloads) |
| **"Lais atendendo" ⇄ "Atendimento manual"** | AI on/off per chat; editor/admin; exit dialog "Sair com Lais pausada?" — auto-resume after 5 days idle; a human message auto-pauses the AI | `PATCH /web/chats/:id/suspend {suspended}` | **S** | C live (never toggled) |
| Timeline | messages grouped by day; `chunkReference` groups multi-bubble AI replies; system lines "Cliente chegou via …", "Lead não respondeu mais. Lais reativou a conversa", "{nome} assumiu a conversa", "Disparo de mensagem para proprietário"; ticks behind flag `message-status-checks` | `GET /web/chats/:id/messages?page&limit=25&order_by=created_at&order_desc=true`; WS `new_message`, `typing`, `message_status_updated` | R | C live (content PII, not copied) |
| Composer | text, emoji, anexo (image ≤5 MB · pdf ≤100 MB · video ≤100 MB · audio), "Gravar áudio", reply (flag `reply-message-chat-frontend`); states window_open · window_closed (24 h) · unauthorized · unauthorized_suspended | `POST /web/chats/:id/media`, **`POST /web/chats/:id/messages/human`** | **S** | C live (never used) |
| "Enviar modelo de mensagem" drawer | search, pick, params; per-chat `templateSendPolicy` (allowed / cooldown / exhausted) | `GET /web/templates/available?chatId=`, `GET /web/chats/:id/messages/template/draft`, **`POST …/messages/human/template`** | R · **S** | C (code); GAP not opened |
| "Novo modelo de mensagem" modal | same form as `/configs_templates` | `POST /web/templates` | W (Meta review) | C (code) |
| Pro transfer | Transferir / Assumir | `POST /web/chats/:id/transfer`, `POST /web/chats/:id/self-assign`, `GET …/transfers` (404 live) | **S** | C (code) |

### 3.4 Details pane "Cliente"

| Accordion | Detail | Endpoint | Safety | Ev |
| --- | --- | --- | --- | --- |
| Perfil | name, phone, "Primeiro contato hoje às HH:mm"; actions Chamar no WhatsApp · histórico · Enviar ao CRM | `GET /web/chats/:id?withFeedback=true` | R | C live |
| Resumo do chat | AI summary | (chat payload) | R | C (code) |
| Visitas solicitadas (n) | links `/visits?visitGroupId=` | `GET /web/chats/:id/visits` | R | C live |
| Etiquetas [+] | add/create/edit tags | `GET /web/tags`, `POST/PATCH/DELETE /web/tags[/:id]`, `GET|PUT /web/chats/:id/tags` | R · W | C live (header) |
| Notas internas (n) [+ Nova anotação] | annotation + ≤4 todos; "Gravar nota com IA" (audio → transcription + summary + todos) | `GET/POST /web/chats/:id/internals`, `POST …/internals/audio/process`, `DELETE …/:noteId`, `PATCH …/todos/:todoId/complete` | R · W | C live (header) |
| Interações (n) | per lead-episode: type (Comercial · Administração · Atualização), started at, channel, operation, CRM status + `triggeredBy` label, extracted slots, AI narrative summary, intent flags, property status, occurrence/boleto flags | `GET /web/chats/:id/interactions` | R | C live (content PII) |
| Análise de crédito | badges + CredAluga link | `GET /web/chats/:id/credit-analyses` | R | GATED (flag `credit-analysis-enabled`) |
| GAP | Resumo do chat accordion not seen live; feedback dialog, block dialog, archive dialog, assign popover, tag editor not opened | — | — | — |

---

## 4 · Histórico do Cliente — `/history` — `Atendimento` — LIVE

Bubble `history` (fullscreen, `allowAnonymous`), params `chatid`, `agency`. A logged-in assignee is redirected to `/chats`. Purpose: read-only conversation + Cliente panel shared by "Copiar link do histórico". Native access-code gate behind flag `new-access-code-page`.

| Element | Detail | Endpoint | Safety | Ev |
| --- | --- | --- | --- | --- |
| Conversation + Cliente panel (Perfil, Interações) | read-only CHAT modules | `GET /web/chats/:id`, `/messages`, `/interactions`, `/internals`, `/tags`, `/visits` | R | C live |
| Access-code gate | 4 digits, 3 attempts then lockout (`localStorage access-code:attempts:<chatId>`); "Não sabe o código?" → login | `POST /api/access-code/validate {code, chatId}`, `GET|DELETE /api/access-code/session` | A | C (code; never typed) |
| GAP | anonymous view (not logged in) never seen; whether the gate is the Bubble or the native one for this agency is U | — | — | — |

## 5 · Código de acesso — `/access-code` — `Atendimento` — NOT-CAPTURED

In the anonymous route class with `/history`. No chunk. I: the stand-alone access-code page of flag `new-access-code-page`.

---

## 6 · Notificações — `/notifications` — `Atendimento` — LIVE

Native. Gate `notification:read` (menu item `notification:menu` for attendants only). Params `page`, `type` (repeatable), `view=acquisition`. Purpose: the human-facing event feed of everything the AI decided.

| Element | Detail | Endpoint | Safety | Ev |
| --- | --- | --- | --- | --- |
| Title | "Notificações" — "Mantenha-se atualizado com as notificações personalizadas da Lais." | — | — | C live |
| Toggle "Notificar lead pronto para atendimento" | ON for this agency | `POST /web/agency/settings {allowNotifications}` | **W** | C live (never toggled) |
| Feed | grouped by day; card = category label, text, datetime, expand chevron; page sizes | `GET /web/notification-events?page&limit&createdSince&createdUntil&transactionType&type=` | R | C live |
| Types → label → actions | `lead-visit-notification` Solicitação de pré-agendamento de visita (Ver conversa · Ver visita · share) · `chat-assigned`/`chat-queued` Novo atendimento · `new-lead-message` Nova mensagem · `lead-user-demanding-followup-notification` Cobrança de atendimento · `real-estate-agency-report-generated` Relatórios da Lais · `real-estate-agency-reachout` Remarketing (→ `/leads?origin=ReachOutLais`) · `lead-property-acquisition` Captação · `property-owner` Atualização de base de imóveis (→ `/owners`) · `lead-enhanced-*` (3) Novo lead gerado · `google-review-notification` Avaliações no Google · `real-estate-agency-notification` (→ `/plans`) | — | — | C (code); live saw Comercial "novo lead" cards |
| Share | "Compartilhar link" → `api.whatsapp.com/send?text=` with `/history?chatid=` link | client | — | C (code) |
| Filter drawer "Filtro de notificações" | DATA (range) · OPERAÇÕES (Todas · Aluguel · Compra) · TIPO DE NOTIFICAÇÃO (Solicitação de pré-agendamento de visita · Cobrança de atendimento · Relatórios da Lais · Remarketing) | — | — | C live |
| States | "Nenhuma notificação com esses filtros" / "…neste período", "Limpar filtros" | — | — | C (code) |
| GAP | card expansion (lead PII); type filter option list beyond the 4 seen | — | — | — |

### 6.1 Captação mode — `/notifications?type=lead-property-acquisition&view=acquisition` — `Imóveis` — LIVE

Sidebar "Gestão de imóveis › Captação". Gate `property-capture:read`. Title "Captação" — "Acompanhe as notificações de imóveis potencialmente captados."; type filter hidden; feed of "CAPTAÇÃO — A Lais identificou uma potencial captação de imóvel" cards (15 in ~5 days); page sizes 5/10/15/20. Same endpoint. C live. GAP: card expansion (PII).

### 6.2 Cobranças mode — `/notifications?page=1&type=lead-user-demanding-followup-notification` — CODE

Target of Início › Atividades › Cobranças de atendimento. Same page filtered to one type. Not opened. C (code).

## 7 · Captação (route) — `/captacao` — `Imóveis` — CODE

In the full-bleed class; only the Bubble iframe client modules load; `bubblePath` U (likely `captacao`). The nav does **not** use it (it points to §6.1). Gate `property-capture:read`. GAP: open by URL to see whether it renders a Bubble page.

---

## 8 · Leads — `/leads` — `Leads` — LIVE

Native `LeadsV3` when flag `leads-view` (on for this agency, §0.2 #4), else Bubble `leads` (params `names, numbers, transactionType, ads, origin, createdAt, status, leadID, campaigns, ads_ids, chatID, email, leadType, conversation, suggestionId`; messages `LEADS_BANNER_*`). Gate `lead:read`. Purpose: every lead that reached the AI, with CRM delivery state.

| Element | Detail | Endpoint | Safety | Ev |
| --- | --- | --- | --- | --- |
| Title | "Leads" — "Tenha a visão completa e organizada dos leads que entraram em contato com a Lais." "Exibindo N leads" | — | — | C live |
| Columns | ☐ · Lead (name + "Atendido pela Lais" / "Sem atendimento"; "TESTE" badge) · Contato (phone, e-mail) · Operação (Compra / Aluguel + property code link) · Canal (origin + datetime) · CRM (Enviado ao CRM · Não pronto · Erro no envio + "Enviado pela Lais" / "Enviado automaticamente" / … + datetime) | `GET /web/leads/?page&limit&…&order_by&order_desc` | R | C live |
| CRM `triggeredBy` labels | auto-sent · enhanced-by-client / qualified-by-client (manual) · invalid-phone-number · message-delivery-error · out-of-scope · qualified-by-lais · visit-scheduled · retry | — | — | C (code) |
| Filter drawer "Filtro de leads" | Data do primeiro contato (range, default current month) · Operação (Aluguel · Compra · Administração) · Atendimento da Lais (Sem atendimento · Atendido pela Lais) · Status CRM (`sent_to_crm` · `send_error` · `not_ready`) · chips Nome · E-mail · Telefone · Imóvel · Link da conversa · Canal (origins) · Campanhas · Anúncios Meta · Análise de crédito | `GET /web/leads/origins`, `GET /web/leads/campaigns` | R | C (code); GAP drawer not opened live |
| Row actions | Copiar link do histórico (client) · Abrir conversa (→ `/chats`) · Ver resumo (modal with `conversationSummary`) · **Enviar ao CRM** | `POST /web/leads/:id/enhance` | **W + CRM** | C live (labels) |
| Bulk actions | Baixar selecionados (xlsx job; ≤5 000 selected / 50 000 by filter) · **Enviar selecionados** (≤60, `{summary:{enhanced,skipped,failed}}`) · Programar Remarketing (selection → `sessionStorage broadcast_lead_selection` → `/broadcasts`) | `POST /web/leads/export`, `GET …/export/:jobId`, `GET …/export/:jobId/download`, **`POST /web/leads/batch-enhance`** | W · R · **W + CRM** | C live (labels) |
| Pagination | 10 · 25 · 50 | — | — | C |
| Test lead swap | "Lead teste trocado com sucesso." | `POST /web/test-users` | **S-I** | C (code) |
| Help link | "Como funciona o Remarketing?" → suporte.lais.ai | — | — | C live |
| GAP | Ver resumo modal (PII); filter drawer; empty state "Nenhum lead encontrado" | — | — | — |

## 9 · Leads v3 — `/leads-v3` — `Leads` — LIVE

Thin route rendering `LeadsV3` directly (breadcrumb "Leads v3"). Same elements and endpoints as §8; live it showed leads without operation ("-") and "Não pronto". C live.

---

## 10 · Visitas — `/visits` — `Visitas` — LIVE (empty state only)

Native. Gate `visit:read`. Params `transactionType, status, clientListingId, visitGroupId`. Purpose: calendar of visit requests the AI collected; operators confirm/reschedule/cancel.

| Element | Detail | Endpoint | Safety | Ev |
| --- | --- | --- | --- | --- |
| Title | "Visitas" — "Gerencie solicitações de visita e defina horários de forma simples." | — | — | C |
| Not-enabled empty state | "Ative as solicitações de visita — Com elas, a Lais agenda visitas no pré-atendimento e cada pedido chega aqui." [Configurar visitas] | `GET /web/visits/config` | R | C live |
| Calendar | month / week / day; "Hoje", "Próximo", "Anterior"; type select (Todos · Compra · Aluguel); "Filtrar por imóvel"; gear → `/configs_visits?type=visit` | `GET /web/visits?view&date&transactionType&clientListingIds&status&leadIds` | R | C (code); GAP |
| Filter drawer "Filtro de visitas" | Operações · Status da visita (Solicitada `pending` · Agendada `confirmed` · Cancelada `canceled`; also `dismissed`) · ID do imóvel | — | — | C live (disabled) |
| Visit dialog | time options = requested + alternatives + "Outra data"; associate property ("Buscar por código ou link"); credit-analysis badge; Ver conversa · Chamar no WhatsApp · Copiar telefone · Copiar CPF | `GET /web/visits/:visitGroupId`, `GET /web/properties/ads?search=`, `PUT /web/visits/:id {propertyId, propertyType}` | R · W | C (code) |
| Agendar / Alterar / Cancelar | with flag `visit_action_notifications` the AI messages the lead; without it "Avisar no WhatsApp" (`wa.me` link) | **`POST /web/visits/:id/confirm`**, **`PUT /web/visits/:id`**, **`POST /web/visits/:id/cancel`** | **S** | C (code) |
| GAP | everything except the empty state: visits are disabled for this agency | — | — | — |

## 11 · Análise de crédito — `/credit-analysis` — `Visitas` — GATED

Flag `credit-analysis-enabled` + `credit-analysis:read` (redirect to `/` observed). Native. CredAluga integration at the visit step (lead consent required).

| Element | Detail | Endpoint | Safety | Ev |
| --- | --- | --- | --- | --- |
| Header | "Análise de crédito" — "Acompanhe as análises de crédito dos seus leads."; tab "Visão geral"; Recarregar dados | — | — | C |
| Cards | Análises realizadas · aprovadas · reprovadas · Visitas no período | `GET /web/credit-analysis/summary?month&year` | R | C (200 live) |
| Chart | "Análises por dia" Aprovadas / Reprovadas | `GET /web/credit-analysis/chart` | R | C |
| Table | Imóvel · CPF · Valor · Status (Aprovado · Reprovado · Pendente) · Motivo · Data · Ver simulação (CredAluga) · Ver conversa | `GET /web/credit-analysis?month&year&page&limit&status` | R | C |

---

## 12 · Disparos em massa — `/broadcasts` — `Disparos` — LIVE (list only)

Native. Flag `broadcasts-enabled` (on). Params `suggestionId`. Purpose: scheduled bulk WhatsApp template sends — Remarketing (leads) and Atualização de anúncios (property owners). Detail: `routes.md` Part B /broadcasts.

| Element | Detail | Endpoint | Safety | Ev |
| --- | --- | --- | --- | --- |
| Header | "Disparos em massa" — "Envie mensagens no Whatsapp para diversos contatos de uma vez."; Tipo filter; [+ Novo disparo] | — | — | C live |
| Tabs | Todos · Rascunhos (`pending`) · Agendados (`confirmed`) · Enviados (`sent`) · Cancelados (`canceled,error`) · Erros (`error`) with counts | `GET /web/broadcasts?limit=20&offset&status&type` | R | C live |
| Sections / columns | RASCUNHOS · AGENDADOS · HISTÓRICO; Nome · Status · Tipo · Contatos | same | R | C live |
| Detail | name, status, template text, response rate, CRM-sent count, targets list | `GET /web/broadcasts/:id`, `GET …/:id/targets?limit&offset` | R | C (S2 shape); GAP detail page not opened (targets = PII) |
| Wizard step 1 "Informações do disparo" | name (auto), description, type (Remarketing · Atualização de anúncios), date (from available dates) + time (09:00), ≥24 h ahead | `GET /web/broadcasts/available-dates` | R | C (code) |
| Step 2 "Selecionar contatos" | individual (leads, ≤100/1000), segment (`leads-2plus-bedrooms`, `eligible-leads-3-15-days`, `eligible-leads-7-30-days`), xls (≤10 MB; owners forced to xls); plan cap `maxPerDispatch` (15 %) | `GET /web/leads/`, `GET /web/broadcasts/segments?type=`, `POST /web/broadcasts/validate-file`, `GET /web/broadcasts/plan`, `GET /web/broadcasts/property-owners` | R · W | C (code) |
| Step 3 "Modelo de mensagem" | recommendation · launch · custom (vars `{nome da pessoa}`, `{nome da Lais}`, `{link do imóvel}`); owners: one fixed template | — | — | C (code) |
| Step 4 "Revisar e confirmar" → Agendar | create (draft or not), file variant, edit draft, confirm | **`POST /web/broadcasts`**, **`POST /web/broadcasts/file`**, `PUT /web/broadcasts/:id`, `POST /web/broadcasts/:id/file`, **`POST /web/broadcasts/:id/confirm-pending`** | **S** | C (code) |
| Reagendar / Cancelar | dialogs | **`PATCH /web/broadcasts/:id/schedule`**, `DELETE /web/broadcasts/:id` | **S** · W | C (code) |
| Errors | `BROADCAST_003…014` (see routes.md) | — | — | C |
| GAP | wizard never opened (whether step navigation already creates a draft is U — `wizardStep` is persisted); detail page | — | — | — |

---

## 13 · Atualização de imóveis — `/owners` — `Imóveis` — LIVE (header + empty list)

Bubble `owners`, params `status, name, number, clientlistingid, startDate, endDate, suggestionId` (Bubble `NAVIGATE` syncs them back). Gate `property:read`, blocked for `developer` agencies. Purpose: the AI messages **property owners** to confirm a listing is still available (broadcast type `property_owner`); results per owner.

| Element | Detail | Endpoint | Safety | Ev |
| --- | --- | --- | --- | --- |
| Header | "Conversas com proprietários para atualizar os imóveis anunciados." | — | — | C live |
| List | empty for this agency | Bubble → legacy core `property-owners` (list, available-dates, upload, confirm, schedule, batch-xlsx) | R (list) · S (confirm/schedule) | C (BUBBLE-DEF catalogue) |
| Property status vocabulary (from interactions) | Disponível · Indisponível · Sem resposta · Disponível com alteração · Agendado | — | — | C (code) |
| GAP | filters and row layout (list empty); upload / schedule forms | — | — | — |

## 14 · Empreendimentos — `/developments` — `Imóveis` — LIVE (Bubble variant)

Flag `new-development-page-front` off ⇒ Bubble `developments`; native page otherwise. Gate `development:read`. Purpose: developments the AI can offer ("A Lais usa as informações cadastradas para aquecer seus leads").

| Element | Detail | Endpoint | Safety | Ev |
| --- | --- | --- | --- | --- |
| Bubble page (live) | "Aumente as vendas adicionando empreendimentos"; [Adicionar empreendimento] [Saiba mais]; list "Empreendimentos cadastrados" + search; one item (Inativo) | Bubble → legacy core developments CRUD (+image) | R · W | C live |
| Native list (code) | search "Nome ou código", status Ativo/Inativo; card price Mín./Méd./Máx. or "Preço sob consulta"; menu Copiar link · Ver no site · Editar | `GET /web/properties/developments` | R | C (200 live) |
| Native detail drawer | Endereço · Preço · Código · Link · Descrição; switch "O <nome> está ativo?" | `PATCH /web/developments/:id {status}` | W | C (code) |
| Native create wizard | Novo Empreendimento · Localização (geocoding) · Descrição · Imagens (≤9) · Resumo | `POST /web/developments`, `/api/geocoding/*` | W · R | C (code) |
| Bulk import | CSV/XLSX ≤2 MB, 150 rows; history + status polling | `POST /web/developments/bulk`, `GET …/bulk-imports[/:id/status]` | W · R | C (code) |
| GAP | Bubble "Adicionar empreendimento" form and item detail not opened | — | — | — |

## 15 · Imóveis integrados — `/properties` — `Imóveis` — GATED

Flag `property-page-front` + `integrated-property:read`. Native. "Confira os imóveis a que a Lais tem acesso pelo XML." — the agency's **prateleira** (XML feed) the AI answers from.

| Element | Detail | Endpoint | Safety | Ev |
| --- | --- | --- | --- | --- |
| List (Grade / Mapa) | filters transactionType · active · bedrooms · bathrooms · parkingSpaces · área mínima · price range · search | `GET /web/properties/ads` | R | C (200 live) |
| Detail | info, features, gallery, "Dados enviados à Meta", similares (distance 5/15/30/60 min), interested leads table | — | R | C (code) |
| Feed sync | status poll every 5 min; manual sync | `GET /web/ads/xml/status`, **`POST /web/ads/xml/sync`**; WS `/ws/properties` `feed_sync_completed` | R · W | C |

## 16 · Catálogo Meta — `/catalogs` — `Integrações` — GATED

Flag `meta-catalog-front` (catalog endpoints answer 404 "meta catalog is not enabled for this agency"). Pushes integrated listings to a Meta catalog for dynamic remarketing.

| Element | Detail | Endpoint | Safety | Ev |
| --- | --- | --- | --- | --- |
| Tabs | Todos · No catálogo · Fora do catálogo · Com erro | `GET /web/catalog/listings`, `…/stats` | R | C |
| Bulk include / exclude / resync | `{adIds}` or `{selectAll, excludedAdIds}` | `POST /web/catalog/listings/{include,exclude,resync}` | W (Meta) | C |
| Subsets (product sets) | name, color, filter grammar (availability, type, price, city, …; and/or); system subsets "Remarketing Dinâmico Lais - Venda/Aluguel" locked | `GET/POST /web/catalog/product-sets`, `PATCH/DELETE …/:id` | R · W | C |

---

## 17 · Relatórios › Bairros e imóveis — `/relatorio-v2` — `Relatórios` — LIVE

Flag `new-relatorio-view` on ⇒ native `RelatoriosV3`; else Bubble `relatorio-v2` (params month, year). Gate `report-neighborhood:read`, blocked for developers. Purpose: demand (what leads ask for) vs shelf (what the agency lists), per neighbourhood and property.

| Element | Detail | Endpoint | Safety | Ev |
| --- | --- | --- | --- | --- |
| Header | "Relatório" — "Confira dados sobre as preferências dos seus leads…"; operation (Aluguel / Compra — only sections with data); month | `GET /web/report?date=YYYY-MM-01` (500 when the month is not generated yet) | R | C live |
| Tab Imóveis | Top tipo de imóveis (Ranking · Tipo · % Leads · % Prateleira) · Top 10 imóveis (Ranking · Imóvel · Tipo · Preço · Leads · Prateleira; rows duplicated — vendor bug) | same | R | C live |
| Tab Bairros | Top 10 bairros (bars) · Desempenho por bairro (median price, most searched type %, best bedroom count, IMÓVEIS MAIS BUSCADOS) | same | R | C live |
| Export | Download SVG / PNG / CSV (`Bairro,Leads`) | client | — | C (code); GAP not opened |

## 18 · Relatório v3 — `/relatorio-v3` — `Relatórios` — CODE

Always the native `RelatoriosV3`; same content and endpoint as §17. Not visited. C (code).

## 19 · Avaliações no Google — `/avaliacoes` — `Relatórios` — LIVE

Native. Gate `report-google-review:read`. The AI asks leads with good conversations for a Google review.

| Element | Detail | Endpoint | Safety | Ev |
| --- | --- | --- | --- | --- |
| Banner | "A Lais está construindo sua reputação" — pedidos enviados / novas avaliações this month | `GET /web/agency/google-reviews/dashboard` | R | C live |
| Distribution | 1–5★ bars, average, total | same | R | C live |
| Últimas avaliações | author, date, text, "Avaliação sem comentário"; external link `search.google.com/local/reviews?placeid=` | same | R | C live (texts not copied) |
| GAP | which conversations trigger a review request (rule U) | — | — | — |

## 20 · Atendimento administrativo — `/atendimento-administrativo` — `Relatórios` — GATED

Requires the administrative add-on (`requiresAdministrative`). Report on tenant/owner conversations (2ª via de boleto, occurrences into the ERP).

| Element | Detail | Endpoint | Safety | Ev |
| --- | --- | --- | --- | --- |
| Visão geral | Conversas administrativas · Boletos enviados · Ocorrências geradas; daily series; table Dia | `GET /web/agency/charts/administrative-report/volume?month&year` | R | C (200 live) |
| Resolution | Resolvida pela Lais / Encaminhada ao time | `…/conversation-resolution` | R | C |
| Top categorias | categories ranking | `…/occurrence-ranking` | R | C |
| Not-integrated state | "Sua imobiliária ainda não tem o registro de ocorrências integrado ao ERP…" | — | — | C (code) |

## 21 · Desempenho — `/performance` — `Relatórios` — GATED

Bubble `performance`, only for agency type `developer`; params `start_date, end_date, origins, campaigns, ads_ids`. Gate `report-performance:read`. Contents U (Bubble, not loaded for this agency type).

---

## 22 · Minha Lais — `/configs` — `Configuração da IA` — LIVE

Native. Gate `lais-settings:read`. Hub of the agent's configuration. `canManage` = role admin or editor, or a Lastro user.

| Card | Description | Target | Gate | Ev |
| --- | --- | --- | --- | --- |
| Meu negócio | Funcionamento da imobiliária, documentações exigidas e garantias | Bubble `/configs_my_business` (§23) | — | C live |
| Perfil do WhatsApp | Nome da Lais, foto de perfil e descrição | Bubble `/configs_whatsapp_profile` (§24) | — | C live |
| Modelos de mensagem | WhatsApp templates | `/configs_templates` (§25) | `canManage` | C live |
| Integrações Meta | Receba leads de campanhas Meta | `/configs_meta_integration` (§26) | shown while flag `meta-integration-front` is **false** | C live |
| **Comportamento da Lais** › Pré-agendamento de visita | Sugerir datas e horários… | `/configs_visits` (§28) | — | C live |
| › Qualificação e Envio ao CRM | O que a Lais deve perguntar antes de enviar leads ao CRM? | Bubble `/configs_behavior` (§27) | — | C live |
| › Reengajamento automático | Como a Lais deve agir com leads que pararam de responder? | `/configs_reengage` (§30) | — | C live |
| › Endereço e IPTU dos imóveis | Como a Lais deve agir quando perguntada sobre endereço completo e IPTU? | Bubble `/configs_property_info` (§31) | — | C live |

No API call of its own. Save pattern of every AI setting (C, BUBBLE-DEF): `PUT` the structured section, then **`POST {core-ai}/prompt/rea/{agency}/refresh`** — the system prompt is recompiled server-side; customers never edit prompt text.

## 23 · Meu negócio — `/configs_my_business` — `Configuração da IA` — LIVE + BUBBLE-DEF

Bubble `configs_my_business` (params `type`, `tab`). Tabs **Geral · Vendas · Locação**; every card has [Editar] opening the shared Bubble `drawer` (1,174 elements). Exit guard "Sair da edição? As modificações feitas não serão salvas." Purpose: the typed knowledge base the prompt is compiled from.

| Tab › Card | Fields (type / options) | Save | Safety | Ev |
| --- | --- | --- | --- | --- |
| Geral › Políticas | Assinatura de contrato (Digital e físico · Digital · Físico); Chaves para visitar (Sempre acompanhadas · Cliente pode buscar a chave · Outro) | `PUT business-settings/visit-policy` + refresh | W | C |
| Geral › Telefones da empresa | list {setor, phone mask 55…}; main contact; "Adicionar novo contato" | `PUT {core-ai}/prompt/rea/{id}/phones` + refresh | W | C |
| Geral › Exibir nome do atendente | switch (same setting as §32) | `web/agency/settings.prefixHumanMessagesWithSenderName` | W | C |
| Geral › Recesso | Início / Término (dd/mm/yyyy), switch "Aviso de recesso", message; Inativo here | `PUT {core-ai}/prompt/rea/{id}/recess` + refresh | W | C |
| Vendas › Informações da operação | Lais atende compra? (support-only) · Nomenclatura do corretor de venda | `PUT business-settings/sale-info` | W | C |
| Vendas › Documentos necessários | chip groups Documentos pessoais · Comprovante de renda · Comprovante de endereço · Detalhes adicionais | `PUT …/sale-documentation` | W | C |
| Vendas › Financiamento | Empresa acompanha? · Serviços oferecidos (despachantes · simulação · bancos) · Custos (avaliação, registro, engenharia, matrícula, análise de crédito, …) · Detalhes | `PUT …/sale-financing` | W | C |
| Locação › Informações da operação | Lais atende locação? (support-only) · Nomenclatura | `PUT …/rental-info` | W | C |
| Locação › Documentos necessários | same groups + fiador quitado + matrícula | `PUT …/rental-documentation` | W | C |
| Locação › Processo de locação | Prazo padrão Residencial / Comercial (12 · 24 · 30 · 36 · 48 · 60 meses) · Multa rescisória (10 % proporcional · 3 aluguéis proporcionais) · Isenção de multa (Sim · Não · Mediante proposta) | `PUT …/rental-contract-terms` | W | C |
| Locação › Garantias | Caução (aceito, oferecer, mínimo em aluguéis) · Seguro fiança (seguradoras chips) · Fiador (nome limpo, imóvel quitado, mesma cidade/estado) · Título de capitalização (nº aluguéis, encargos) · Outras (Loft, fianças bancárias…; "alugar sem garantia") | `PUT …/rental-guarantees` | W | C |
| Read side | — | `GET business-settings/{identification, visit-policy, rental-*, sale-*, bot-work-hours, work-hours, bot-profile}` | R | C |
| GAP | `identification`, `bot-work-hours`, `work-hours`, `bot-profile` sections have GET/PUT but no card seen in the three tabs (U where they are edited — onboarding?) | — | — | — |

## 24 · Perfil do WhatsApp — `/configs_whatsapp_profile` — `Configuração da IA` — LIVE + BUBBLE-DEF

Bubble. Card Informações [Editar] with a phone mock-up mapping each field.

| Field | Rule | Save | Safety | Ev |
| --- | --- | --- | --- | --- |
| Foto da Lais | PNG/JPG ≤5 MB, ≥192×192 | `PUT {core-ai}/dialog360/account-info` | W (edits the WhatsApp Business profile at 360dialog) | C |
| Nome da Lais · Telefone · Site | support-only | — | — | C |
| Descrição · Sobre · Endereço · E-mail de contato | free text | same | W | C |
| Read | — | `GET {core-ai}/dialog360/account-info` | R | C |

## 25 · Modelos de mensagem — `/configs_templates` — `Configuração da IA` — LIVE

Native; `canManage`. Meta-approved WhatsApp templates the team and the AI use outside the 24 h window.

| Element | Detail | Endpoint | Safety | Ev |
| --- | --- | --- | --- | --- |
| Header | "Gerencie os modelos de mensagem do WhatsApp disponíveis para seu time."; [↻]; [+ Criar modelo de mensagem]; search | — | — | C live |
| Category chips (counts) | Administrativo · Campanha · Cobrança · Documentação · Primeiro contato · Reativação · Visita · Outros (keys administrative, campaign, billing, documentation, first_contact, reactivation, visit, other) | `GET /web/templates/categories` | R | C live |
| Card | category, name, status (Aprovado · Pendente · Reprovado), body with friendly variables; 11 templates here (3 visit, 2 first contact, 6 reactivation) | `GET /web/templates/available` | R | C live |
| Preview drawer | "Simule com exemplos" (local only) | — | — | C (code); GAP not opened |
| Create modal "Novo modelo de mensagem" | Nome (req) · Categoria (req) · Conteúdo (req, ≤1024, no links/emojis, ≤3 params from registry, not at start/end) | `GET /web/templates/params`, **`POST /web/templates`** | W (submits to Meta) | C (code); GAP not opened |
| Delete | custom templates only | `DELETE /web/templates/:id` | W | C (code) |
| Param registry | sources core · core_ai · session · manual | `GET /web/templates/params` | R | C (S2) |

## 26 · Integrações Meta — `/configs_meta_integration` — `Integrações` — LIVE (not connected)

Native; redirects to `/configs` when flag `meta-integration-front` is true. Facebook/Instagram Lead Ads forms → leads straight to the AI.

| Element | Detail | Endpoint | Safety | Ev |
| --- | --- | --- | --- | --- |
| Hero | "Aumente seus resultados com os leads da Meta"; steps autorizar → escolher formulários; [Conectar à Meta]; Saiba mais | — | — | C live |
| OAuth popup | `facebook.com/v21.0/dialog/oauth` → `/facebook/callback` posts `FB_OAUTH_CALLBACK`; state in `localStorage fb_oauth_state` | `POST /web/facebook/callback {code}`, `POST /web/facebook/connect/finalize {pageIds}` | A · W | C (code; never clicked) |
| Contas vinculadas | Conectada / Inativa, "N formulários na Lais"; Desconectar | `GET /web/facebook/pages`, `DELETE …/pages/:pageId` | R · W | C |
| Formulários da conta | checkbox list, search, Salvar; "N campos" tooltip | `GET /web/facebook/forms?pageId=`, `…/forms/local`, `…/forms/meta`, `…/forms/:formId/questions`, `POST /web/facebook/forms`, `PUT …/:formId/toggle` | R · W | C |
| Field mapping | no UI caller | `PUT …/:formId/mapping` | W | C (code) |
| GAP | connected state never seen (agency not connected) | — | — | — |

## 27 · Qualificação e Envio ao CRM — `/configs_behavior` — `Configuração da IA` — LIVE + BUBBLE-DEF

Bubble `configs_behavior` (params `type`, `tab`; `?type=questions` opens Perguntas essenciais). "Personalize o que a Lais deve fazer com cada tipo de lead." Tabs **Perguntas essenciais · Envio ao CRM**.

| Tab › Section | Fields / behaviour | Save | Safety | Ev |
| --- | --- | --- | --- | --- |
| Perguntas essenciais | "Perguntas ativas (n)" [Editar] → catalogue of **63** questions in 6 categories (Operação · Informações do lead · Características do imóvel · Localização · Informações financeiras · Interesses gerais), switch per question, "Qualificatória" checkbox, "Mostrar todas"; limits **8 active / 5 qualifying**; "Objetivo: comprar ou alugar" locked; a question used by a CRM criterion can't be switched off | `GET web/required-information`, `GET/POST web/required-information/selected` | R · W | C (BUBBLE-DEF; live list showed "Perguntas ativas (0)" while S2 GET returned 5 selected — §N) |
| FAQ (live) | the AI asks only what is missing; a qualifying question is pursued until answered | — | — | C live |
| Envio ao CRM › Envio automático de leads qualificados | per operation: "Visita solicitada via formulário da Lais **OU** Qualificado via Inteligência da Lais" (a partir de / até / independente do valor); opens the native rule builder §29 | `POST web/auto-forwarding/config`, `PUT web/forwardings/{ids}` | W | C (BUBBLE-DEF) |
| › Leads frios | "Encaminhar leads frios": after an interval (30 min … 10 h after the last reengage attempt) or next morning 05:00–06:00 | `GET web/auto-forwarding/intervals`, `…/config` | R · W | C (live: off) |
| › Potenciais captações | send to CRM or notify only | `behavior-settings`, `allowEnhanceAcquisitionLeads` | W | C (live: notify only) |
| › WhatsApp inválido | auto-send to CRM or not | `behavior-settings` | W | C (live: Ativo) |
| › Pesquisa com clientes | opt-in weekly random satisfaction survey | `behavior-settings` | W | C (BUBBLE-DEF; not seen live) |
| CRM connector | `web/forwardings` = `[{type:"vista-v2", enableAutoForwarding:true}]` | `GET web/forwardings` | R | C (S2) |

## 28 · Pré-agendamento de visita — `/configs_visits` — `Configuração da IA` — LIVE (card) + CODE (editor)

Native (module 1647); `?type=visit` auto-opens the edit drawer. Card [Inativo] "A Lais não envia a solicitação de visita para seus leads." [Editar].

| Element | Detail | Endpoint | Safety | Ev |
| --- | --- | --- | --- | --- |
| Editor | switch enabled; "Diferenciar configuração para leads de compra e aluguel" (tabs Compra/Aluguel); "Solicitação de CPF obrigatória?"; período mín (dias 0–31 + horas 0–23) / máx (dias 3–31); "Horários disponíveis" per weekday, ranges ≥1 h on a 07:00–23:30 30-min grid, no overlap; "Está tudo certo?" when buy = rent | `GET|PUT /web/agency/settings/visits` | R · W | C (code); GAP drawer not opened |
| Bubble drawer (legacy) | same knobs | `behavior-settings` | W | C (BUBBLE-DEF) — see §0.2 #1 |

## 29 · Envio de leads qualificados — `/configs_qualification` — `Configuração da IA` — LIVE (step 1)

Native, bare embed (opened from inside Bubble §27). Full-screen wizard, 2 steps.

| Element | Detail | Endpoint | Safety | Ev |
| --- | --- | --- | --- | --- |
| Step 1 "Critérios de envio" | "A Lais qualifica e envia ao CRM os leads que atenderem algum dos critérios:"; groups OR'd ("OU"), criteria AND'd ("E", "+ Combinar com outro critério"); locked base group "Comportamento — Qualificado via inteligência da Lais" (`type:filter`); other groups `type:priority`; locked "Visita — Pré-agendada via formulário da Lais" when visits on; toggle "Configurações diferentes para compra e aluguel" | `GET /web/audiences/required-informations`, `GET /web/audiences/user-profiles`, `GET /web/visits/config` | R | C live |
| Criterion operators | Selecionar condição / Independentemente (`filled`) · A partir de (`>=`) · Até (`<=`) · De – Até (`between`); currency "R$"; pt-BR numbers | — | — | C (code) |
| Buttons | "+ Adicionar critério de envio", "Ir para Perguntas essenciais", "Saiba mais", nudges "Faça a Lais filtrar mais/menos", Próximo | — | — | C live |
| Step 2 "Resumo" | "Leads de compra/aluguel serão enviados quando atenderem a pelo menos um dos seguintes critérios:"; Salvar | `POST /web/audiences/user-profiles`, `PATCH …/:id` (rollback on failure) | **W** (changes when the AI pushes to the CRM) | C (code); GAP step 2 not seen |
| Save blockers | "Defina ao menos um critério no cartão Comportamento…", "Nenhuma alteração para salvar." | — | — | C (code) |

## 30 · Reengajamento automático — `/configs_reengage` — `Configuração da IA` — LIVE + BUBBLE-DEF

Native; params `tab=default|reengage-rules`, `reengage=minutes|hours`, `type=reengagement`. "Recupere leads e aumente suas chances de conversão."

| Element | Detail | Endpoint | Safety | Ev |
| --- | --- | --- | --- | --- |
| Tab Reengajamento padrão | banner (réguas start after the last standard attempt); **Reengajamento em minutos** [Ativo] 15 min, any hour (`reminder`); **Reengajamento em horas** [Ativo] 4 h, 08–20 h only, also reaches leads who never answered (`final`); [Editar] each; minutes < hours; "Sempre que o lead responder, o fluxo… recomeça. Leads que encerram o atendimento não são contatados." | `GET /web/reengage/configs`, `GET …/configs/delay-minutes?reengageType=reminder|final`, **`PUT /web/reengage/configs {enabled, reengageType, delayMinutes}`** | R · **W** (governs automatic AI re-sends) | C live (cards) |
| Tab Réguas de reengajamento [NOVO] | [+ Nova régua]; "Régua 1 [Inativo] — Configure até 3 tentativas…"; rule = name, buy/rent, enabled, attempts[] (≤3; delay value+unit, template); window 08–20 h; templates `lead_reengage`, `_short`, `_long`, `_brief_message` | `GET/POST /web/reengage/rules`, `GET/PATCH/DELETE …/:id`, `POST …/:id/{activate,deactivate}`, `POST …/:id/attempts`, `PATCH/DELETE …/attempts/:attemptId`, `GET …/rules/templates` | R · W | C live (list) |
| GAP | edit drawers for minutes/hours (option lists); rule editor `/configs_reengage/rules/:id` and the attempt editor (lazy chunk not captured) | — | — | — |

## 31 · Endereço e IPTU dos imóveis — `/configs_property_info` — `Configuração da IA` — LIVE + BUBBLE-DEF

Bubble. Two switches: **Acesso ao IPTU** (reads IPTU from the XML shelf; off here — "A Lais NÃO irá acessar o IPTU…") and **Envio de endereço completo** [Ativo] (else bairro + cidade only). Save → `behavior-settings` + `web/agency/settings.useIptu` (W). C.

## 32 · Exibir nome do atendente — `/configs_display_attendant_name` — `Configuração da IA` — LIVE

Native bare embed; `canManage`. Switch [Inativo] "Exibir nome do atendente na mensagem?" with a WhatsApp bubble preview; [Cancelar] [Salvar] → `POST /web/agency/settings {prefixHumanMessagesWithSenderName}` (W; prefixes human messages to leads). C live.

## 33 · Pré-agendamento (embed) — `/configs_visits_embed` — `Configuração da IA` — CODE

Same editor as §28 rendered inside Bubble drawers (`?context=platform` uses the platform layout); posts `SAVE` / `SAVE_ERROR` / `EXIT_DRAWER` / `RELOAD_WITH_PARAMS` to the Bubble parent. C (code).

---

## 34 · Usuários e equipes — `/acessos` — `Equipe` — LIVE

Native. Gate `team:view-page` (`GET /web/permissions/teams`). Label "Equipes" for attendants. Purpose: users, seats, Pro teams and lead distribution after the AI.

| Element | Detail | Endpoint | Safety | Ev |
| --- | --- | --- | --- | --- |
| Código de acesso | 4-digit "Código da Lais" for `/history` links; copy | `GET /web/agency/access-code` | R | C live (value never recorded) |
| Tab Usuários | [+ Adicionar usuário]; seat meter "N de M assentos utilizados"; columns Usuário · Nível de acesso (Administrador · Editor · Membro · Atendente) · Assento (Padrão `free` · Pro `paid` · Pro teste `test`) · Status · ⋮ (Editar nível de acesso · Dar acesso de editor / Tornar membro · Alterar assento · Excluir usuário) | `GET /auth/users`, `GET /web/seats/availability`, `GET /web/seats/summary`, `DELETE /auth/users/:id` | R · W | C live (list PII not copied) |
| Add/edit user wizard | Informações da conta (Nome completo, E-mail + live check) · Permissões (role cards with permission bullets) · Tipo de assento (Padrão / Pro; attendant ⇒ Pro); paid seat with 0 free ⇒ "Contratar assento adicional"; edit = same POST (upsert by e-mail) | `GET /auth/users/check-email`, `POST /auth/users` | R · W | C (code); GAP wizard not opened |
| Tab Equipes [NOVO] | [+ Criar equipe]; team row "N membros [Editar]" → table Usuário · Último acesso · **TPR** · Conversas · Distribuição (switch per member); menu Configurações · Usuários · Excluir equipe | `GET /web/teams`, `GET /web/teams/:id`, `GET …/:id/metrics` (flag `metricas-gestao-pro`), `PATCH …/members/:userId {distributionActive}`, `DELETE /web/teams/:id` | R · W | C live (one team) |
| Create/edit team wizard | 1 Nome · 2 "Esta equipe atende clientes diretamente após a Lais?" (`distributionEnabled`), "Como os leads serão atribuídos?" Via CRM (padrão) / **Via Lais** (roleta, `rouletteEnabled`), categories Aluguel · Compra · Administrativo · Proprietário (one team per category), "Enviar automaticamente ao CRM" (`autoCrmEnabled`), "Manter atribuição ao último responsável" (`lastAttendantEnabled`), "Receber apenas categorias específicas" (administrative classifiers) · 3 members + "Tornar gestor" (Pro seats only) | `GET /web/teams/lead-types?excludeTeamId=`, `GET /web/teams/occurrences/availability`, `POST /web/teams`, `PATCH /web/teams/:id`, `POST/DELETE /web/teams/:id/members[/:userId]` | R · W | C (code); GAP wizard not opened |
| Pro module card | status Pacote contratado / Cancelamento agendado; activate / change seats / cancel (admin) | `GET/POST/PATCH/DELETE /web/subscription/premium` | R · W (billing) | C |
| Member removal rule | conversations redistributed: gestores first, else split equally, else stay unassigned on the team | — | — | C (copy) |
| Permission matrix | admin / editor / member standard / member Pro / atendente / atendente gestor × create_team, edit_team, view_all_conversations, transfer, add_user, change_role, change_seat, delete_user (see `routes.md` Part C §2) | client | — | C |

## 35 · Acessos (legacy) — `/user-management` — `Equipe` — LIVE + BUBBLE-DEF

Bubble `user_management` ("Acessos") with the `add-team` onboarding banner. Reachable by URL. "Acesso por código — Código da Lais" card; users list did not render live. Bubble fields: invite by e-mail + full name (`POST auth/users` + flow step + Bubble `user_invitations` workflow), give/remove editor, delete user/invite (`DELETE auth/users/{email}`), search, paging. W. GAP: users list (did not render).

---

## 36 · Plano e cobranças — `/financeiro` — `Conta/Plano` — LIVE

Native. Gate `billing:read` or Lastro staff. Pricing unit: **crédito de atendimento** (one served lead/conversation; administrative ½).

| Element | Detail | Endpoint | Safety | Ev |
| --- | --- | --- | --- | --- |
| Plano e conta › Plano atual | plan name/type, credits per month, start, "Vigência — N meses restantes"; usage ring "Consumo deste mês" / "Consumo da franquia anual"; overage alert by policy (fixed / bump) | `GET /web/finance/subscriptions?status=active`, `GET /web/finance/consumption?referenceMonth=` | R | C live |
| Plano e conta › Conta de faturamento | CNPJ + agencies; financial contacts (add/edit/delete) | `GET /web/finance/billing-account`, `GET/POST/PUT/DELETE /web/finance/financial-contacts[/:id]` | R · W | C (code); GAP tab not opened live |
| Cobranças | tabs Boletos a pagar · Histórico; month, status, vencimento, value, [Baixar boleto] [Copiar linha digitável]; "Atrasado · N dias"; "Tudo em dia" | `GET /web/finance/invoices[?status=overdue]`, `GET …/invoices/:id` | R | C live |
| Pacotes adicionais | active add-ons (e.g. seat policy 50 % off, quantity) | `GET /web/finance/add-on-billing-accounts?status=active` | R | C live |
| "Alterar plano" (flag `finance-change-plan-front`) | reason select + text; **no network call** on submit | — | — | C (code); GATED? (U whether the link shows) |

## 37 · Planos — `/plans` — `Conta/Plano` — CODE

Bubble `plans` ("Planos"); target of `real-estate-agency-notification` cards. Not visited.

## 38 · Pacotes adicionais — `/add-ons` — `Conta/Plano` — LIVE

Native. Gate `add-on:read` (nav NOVO). Catalogue cards with contracted state:

| Package | Price (copy) | Offer → contracted target | Contracted when | Ev |
| --- | --- | --- | --- | --- |
| Gestão de atendimentos Pro | a partir de R$ 499/mês (was 999) | `/add-ons/pro` | premium subscription active (**contracted here**) | C live |
| Campanhas inteligentes | R$ 1.125/mês (was 2.250) | `/add-ons/smart-campaigns` → `/smart-campaigns` | flag `smart-campaigns-front` ∧ pixel | C live |
| Atendimento administrativo | ½ crédito por atendimento, "Ative gratuitamente" | `/add-ons/administrative` → `/atendimento-administrativo` | `administrative.enabled` | C live |

### 38.1 `/add-ons/pro` — LIVE
"Gestão de atendimentos Pro [Pacote contratado]"; Primeiros passos: 1 add attendant users (1 Pro seat each) · 2 per team choose who distributes after the AI (Lais or CRM) · 3 create teams · 4 attendants install the mobile app. Subscription status/activate/seats/cancel as §34. C live.

### 38.2 `/add-ons/smart-campaigns` — LIVE
Marketing page: Integração com a Meta · Sinal de qualificação (qualified lead, visit scheduled, client reply → Meta) · Formatos (Click to WhatsApp, form, landing page) · Relatório mais fiel; claim +25–50 % qualification. CTA "Solicitar demonstração" = analytics only. C live.

### 38.3 `/add-ons/administrative` — LIVE
Features: 2ª via de boleto · Registro de ocorrência (into the ERP) · Diagnóstico de manutenção · Orientação sobre processos administrativos; ERPs KSI, Universal Software, Apolar, Superlógica, Nido ADM, Properfy, apresenta.me, Flexpro Simob, MSYS Imob, Basis. CTA = analytics only. C live.

## 39 · Gestão de atendimentos Pro (old URL) — `/pacotes-adicionais/gestao-de-atendimentos-pro` — `Conta/Plano` — NOT-CAPTURED

No chunk. I: legacy URL of §38.1.

## 40 · Meu perfil — `/perfil` — `Conta/Plano` — LIVE

Native, `page:all-roles`. "Atualize seu WhatsApp. Nome, e-mail, cargo e área de atuação são apenas leitura." Sections Dados pessoais (Nome, E-mail, Nível de permissão) · Contato (WhatsApp, editable, BR phone rule) · Cargo e atuação (raw enum keys shown, e.g. `owner_partner`, `marketing` — missing i18n). [Salvar] → `PATCH /auth/users/me/profile {phone}` (W). Also `PATCH /auth/profile {name}` (caller I). C live.

---

## 41 · Primeiros passos — `/checklist` — `Onboarding` — GATED

`page:all-roles`, but flag `checklist`=true (exempt) or all flows done ⇒ redirect to `/`. "Primeiros passos — Um guia prático para conhecer a Lais…"

| Flow card | Steps | Endpoint | Safety | Ev |
| --- | --- | --- | --- | --- |
| Adicione sua equipe (`add-team`) | go-access · add-users | `GET /web/flows/:slug/onboarding-progress`, `POST …/steps/:step/complete` | R · W | C |
| Assuma o controle de conversas da Lais (`chat-control`) | open-chat · stop-chat · send-message · reactive-chat (on `/chats` with the test lead) | same | R · W | C |
| Informe mais canais (`connect-origins`) | confirm-origins: channel picker (pre-selected / receiving leads / added) | `GET /web/checklist/channels-status`, `POST /web/checklist/channels {leadOriginIDs}` | R · W | C |
| Recupere leads antigos (`reachout-leads`) | go-leads · select-lead · send-reachout | same | R · W | C |

## 42 · Lead de teste — `/creation-user-test` — `Onboarding` — CODE (no route chunk)

Forced for non-exempt agencies without a test lead. Form "Nome do lead teste" + "Número de WhatsApp do lead teste" → `GET/POST /web/test-users`, `DELETE …/:id` (**S-I**: creating it probably makes the AI message that number). C (form code in a shared chunk).

## 43 · Onboarding do usuário — `/onboarding` — `Onboarding` — CODE (no route chunk)

Forced when `profile.needsOnboarding` (false for this user). 3 steps: WhatsApp · Áreas de atuação (sales, rental, capture, rental_admin, finance, people, marketing + "Outra") · Função (owner_partner, team_manager, operation_start, operation_end, realtor, comms_marketing) → `POST /auth/users/me/onboarding` (W). C (code in module 7427).

## 44 · Onboarding concluído — `/onboarding/sucesso` — `Onboarding` — CODE

"Obrigado pelas informações"; auto-redirect to `/`, "Ir para a Casa da Lais". C (code).

## 45 · Plataforma — `/platform` — `Onboarding` — GATED

Bubble `platform` (fullscreen); forced only when agency `status=onboarding` ∧ module `onboarding_automatizado`; otherwise redirects to `/`. `BUBBLE_LOGOUT` → `/`. Bubble onboarding step slugs (BUBBLE-DEF): whatsapp-profile, whatsapp-config, features, features-visit, business-id, business-phones, business-policy, business-rent(-schedule|-docs|-guarantees|-deadlines), business-sell(-schedule|-docs|-financing), crm, xml, developments, schedule-call; includes the onboarding chat `{core-ai}/chats/onboarding` and WABA Embedded Signup `waba/onboardings/*`. Contents U beyond the definition.

## 46 · Agendar reunião — `/platform-meeting-schedule` — `Onboarding` — NOT-CAPTURED

Onboarding-platform route class; no chunk. I: implementation-analyst calendar (Bubble catalogue lists an "implementation-analyst calendar" call).

## 47 · Treinamentos — `/trainings` — `Onboarding` — CODE

Bubble `trainings` (fullscreen, param `s`, agency synced). Not visited.

## 48 · Guia da Lais — `/trainings_page` — `Onboarding` — LIVE

Native, `lais-guide:read`. "Aprenda a usar a Lais para vender mais e operar com menos esforço." Trilha de conhecimento: Boas-vindas · Introdução à Casa da Lais · Faça mais com a Casa da Lais; Vimeo lessons; progress in `localStorage training-progress:<vimeoId>`. No API. C live.

## 49 · Novidades — `/whats-new` — `Onboarding` — LIVE

Native; flag `whats-new-page` + `whats-new:read`. Dated changelog cards (title, description, image, CTA) → `GET /web/whats-new?limit=20&offset=` (R). Entries seen: Relatório de Atendimento administrativo (03 set) · Disparos em massa page (26 ago) · Reengajamento for never-replied leads + réguas (29 jul) · Campanhas inteligentes (15 jul) · Gestão de atendimentos Pro (08 jul) · Análise de crédito / CredAluga (02 jul) · Integrações Meta (01 jul). C live.

---

## 50 · Campanhas inteligentes — `/smart-campaigns` — `Integrações` — GATED

Flag `smart-campaigns-front` + `smart-campaign:read`; onboarding state here `needs_oauth` (redirect to `/`). Meta CAPI: qualification signals → Meta; campaign performance.

| Element | Detail | Endpoint | Safety | Ev |
| --- | --- | --- | --- | --- |
| Onboarding state | needs_oauth · awaiting_configuration · ready; hasPixel / hasToken / hasAdAccount; budget caps | `GET /web/smart-campaigns/onboarding-state` | R | C (200 live) |
| Summary cards | Investimento total · Total de leads · Leads qualificados · CPL médio · CPQL médio | `GET /web/smart-campaigns/campaigns?from&to&status&adAccountId` | R | C |
| Table | Campanha · Status · Invest. · Leads · Qual. · % · CPL · CPQL; filters search, "Apenas com a Lais", status, investment, month; ad account select | `GET /web/smart-campaigns/ad-accounts` | R | C |
| Campaign leads drawer | Nome · Contato · Data · Status (CRM) · Qualificado (lais Sim · manual · auto) | `GET …/campaigns/:id/leads` | R | C |

## 51 · Remarketing (Meta) — `/smart-campaigns/remarketing` — `Integrações` — GATED

Flags `smart-campaigns-front` + `smart-campaigns-remarketing-front` + pixel; `?operation=sale|rent`, `campaign`, `adAccount`. Two steps (Informações · Revisão); **no create/update endpoint wired** (finish disabled) — work in progress. C (code).

## 52 · Facebook callback — `/facebook/callback` — `Integrações` — NOT-CAPTURED

OAuth popup target; posts `FB_OAUTH_CALLBACK {code|error}` to the opener. Behaviour known from the opener's code; chunk absent.

---

## 53 · `/auth/signin` · 54 · `/auth/error` — `Shell` — NOT-CAPTURED

NextAuth pages (Keycloak redirect). The owner's login went straight to Keycloak; these pages' markup was not captured.

## 55 · `/unauthorized` — `Shell` — NOT-CAPTURED

In the guard's extra list (`page:all-roles`); no chunk. I: shown when no nav entry is allowed.

## 56 · `/debug` — `Shell` — NOT-CAPTURED

No chunk; internal. Never visit.

All 58 routes of the Next route manifest have a section (§2–§56; §38 covers four). Parameter modes (`/chats?view=kanban`, `/notifications?view=acquisition`, `?type=` deep links) are sub-sections, not extra routes.

---

## 57 · Page index by category (all 58 routes, with coverage)

| Category | Routes |
| --- | --- |
| Shell | `/` LIVE · `/auth/signin` NOT-CAPTURED · `/auth/error` NOT-CAPTURED · `/unauthorized` NOT-CAPTURED · `/debug` NOT-CAPTURED |
| Atendimento | `/chats` LIVE (+ `?view=kanban`) · `/history` LIVE · `/access-code` NOT-CAPTURED · `/notifications` LIVE |
| Leads | `/leads` LIVE · `/leads-v3` LIVE |
| Visitas | `/visits` LIVE (empty) · `/credit-analysis` GATED |
| Disparos | `/broadcasts` LIVE (list) |
| Imóveis | `/notifications?view=acquisition` (Captação) LIVE · `/captacao` CODE · `/owners` LIVE · `/developments` LIVE · `/properties` GATED |
| Relatórios | `/relatorio-v2` LIVE · `/relatorio-v3` CODE · `/avaliacoes` LIVE · `/atendimento-administrativo` GATED · `/performance` GATED |
| Configuração da IA | `/configs` LIVE · `/configs_my_business` LIVE+BUBBLE-DEF · `/configs_whatsapp_profile` LIVE+BUBBLE-DEF · `/configs_templates` LIVE · `/configs_behavior` LIVE+BUBBLE-DEF · `/configs_qualification` LIVE (step 1) · `/configs_visits` LIVE (card) · `/configs_visits_embed` CODE · `/configs_reengage` LIVE+BUBBLE-DEF · `/configs_property_info` LIVE+BUBBLE-DEF · `/configs_display_attendant_name` LIVE |
| Equipe | `/acessos` LIVE · `/user-management` LIVE+BUBBLE-DEF |
| Conta/Plano | `/financeiro` LIVE · `/plans` CODE · `/add-ons` LIVE · `/add-ons/pro` LIVE · `/add-ons/smart-campaigns` LIVE · `/add-ons/administrative` LIVE · `/pacotes-adicionais/gestao-de-atendimentos-pro` NOT-CAPTURED · `/perfil` LIVE |
| Onboarding | `/checklist` GATED · `/creation-user-test` CODE · `/onboarding` CODE · `/onboarding/sucesso` CODE · `/platform` GATED · `/platform-meeting-schedule` NOT-CAPTURED · `/trainings` CODE · `/trainings_page` LIVE · `/whats-new` LIVE |
| Integrações | `/configs_meta_integration` LIVE (counted under Configuração da IA) · `/catalogs` GATED · `/smart-campaigns` GATED · `/smart-campaigns/remarketing` GATED · `/facebook/callback` NOT-CAPTURED |

**Totals (58 routes):** LIVE 33 (7 of them also BUBBLE-DEF) · CODE 8 · GATED 9 · NOT-CAPTURED 8.

---

## 58 · Route × endpoint matrix

Generated from `analysis/endpoints.json` (230 endpoints) with route assignment by path, corrected against `routes.md` (the json's own `routes` field over-lists, because it follows chunk dependencies). Codes: `/` Início · `*` every page (shell) · CH `/chats` · HI `/history` · ACC `/access-code` · NO `/notifications` · CP Captação view · LE `/leads` · L3 `/leads-v3` · VI `/visits` · CA `/credit-analysis` · BR `/broadcasts` · DV `/developments` · PR `/properties` · CAT `/catalogs` · RV2/RV3 relatórios · AV `/avaliacoes` · AA `/atendimento-administrativo` · CQ `/configs_qualification` · CV `/configs_visits` · CVE `/configs_visits_embed` · RE `/configs_reengage` · TM `/configs_templates` · MI `/configs_meta_integration` · FBC `/facebook/callback` · CDN `/configs_display_attendant_name` · AC `/acessos` · UM `/user-management` · AP `/add-ons/pro` · AO `/add-ons*` · FI `/financeiro` · PF `/perfil` · OB `/onboarding` · CK `/checklist` · CT `/creation-user-test` · WN `/whats-new` · SC `/smart-campaigns` · SCR `/smart-campaigns/remarketing`.

| Endpoint | Method | Safety | Routes |
| --- | --- | --- | --- |
| `/web/chats/agency` | GET | READ | CH |
| `/web/chats/agency (pinned=true&limit=5)` | GET | READ | CH |
| `/web/chats/agency/search` | GET | READ | CH |
| `/web/chats/agency/validate-phone` | GET | READ | CH |
| `/web/chats/:id` | GET | READ | CH · HI |
| `/web/chats/:id?withFeedback=true` | GET | READ | CH · HI |
| `/web/chats/:id/agency` | GET | READ | CH |
| `/web/chats/:id/suspend` | PATCH | SEND | CH |
| `/web/chats/:id` | PATCH | WRITE | CH · HI |
| `/web/chats/:id/pin` | PATCH | WRITE | CH |
| `/web/chats/:id/feedback` | POST | WRITE | CH |
| `/web/chats/:id/credit-analyses` | GET | READ | CH · HI |
| `/web/chats/:id/interactions` | GET | READ | CH · HI |
| `/web/chats/:id/messages` | GET | READ | CH · HI |
| `/web/chats/:id/messages/human` | POST | SEND | CH |
| `/web/chats/:id/media` | POST | SEND | CH |
| `/web/chats/:id/messages/template/draft` | GET | READ | CH |
| `/web/chats/new/messages/template/draft` | GET | READ | CH |
| `/web/chats/:id/messages/human/template` | POST | SEND | CH |
| `/web/chats/new/messages/human/template` | POST | SEND | CH |
| `/web/chats/:id/user-assignment` | POST | SEND | CH |
| `/web/chats/:id/team-assignment` | POST | SEND | CH |
| `/web/chats/:id/transfer` | POST | SEND | CH (Pro only) |
| `/web/chats/:id/transfers` (404 live; premium mock) | GET | READ | CH |
| `/web/chats/:id/self-assign` | POST | SEND | CH (Pro only) |
| `/web/chats/:id/visits` | GET | READ | CH · HI |
| `/web/chats/:id/kanban-move` | POST | WRITE | CH |
| `/web/chats/:id/tags` | GET | READ | CH · HI |
| `/web/chats/:id/tags` | PUT | WRITE | CH · HI |
| `/web/chats/:id/internals` | GET | READ | CH · HI |
| `/web/chats/:id/internals` | POST | WRITE | CH · HI |
| `/web/chats/:id/internals/audio/process` | POST | WRITE | CH |
| `/web/chats/:id/internals/:noteId` | DELETE | WRITE | CH |
| `/web/chats/:id/internals/:noteId/todos/:todoId/complete` | PATCH | WRITE | CH |
| `/web/kanban/columns` | GET | READ | CH |
| `/web/kanban/columns` | POST | WRITE | CH |
| `/web/kanban/columns/:id` | DELETE | WRITE | CH |
| `/web/kanban/columns/reorder` | PATCH | WRITE | CH |
| `/web/tags` | GET | READ | CH |
| `/web/tags` | POST | WRITE | CH |
| `/web/tags/:id` | PATCH | WRITE | CH |
| `/web/tags/:id` | DELETE | WRITE | CH |
| `/web/users/block` | POST | WRITE | CH |
| `/web/users/unblock` | DELETE | WRITE | CH |
| `/auth/users?skipInternal=true[&managedByMe=true]` | GET | READ | CH |
| `/web/teams[?managedByMe=true]` | GET | READ | CH |
| `/web/templates/available` | GET | READ | CH · TM |
| `/web/templates/categories` | GET | READ | CH · TM |
| `/web/templates/params` | GET | READ | CH · TM |
| `/web/templates` | POST | WRITE | TM · CH |
| `/web/templates/:id` | DELETE | WRITE | TM · CH |
| `/web/leads/` | GET | READ | LE · L3 · BR |
| `/web/leads/origins` | GET | READ | LE · L3 · BR |
| `/web/leads/campaigns` | GET | READ | LE · L3 · BR |
| `/web/leads/:id/enhance` | POST | WRITE | LE · L3 |
| `/web/leads/batch-enhance` | POST | WRITE | LE · L3 |
| `/web/leads/:id/enhance/force` | PATCH | WRITE | LE · L3 |
| `/web/leads/export` | POST | WRITE | LE · L3 |
| `/web/leads/export/:jobId` | GET | READ | LE · L3 |
| `/web/leads/export/:jobId/download` | GET | READ | LE · L3 |
| `/web/visits` | GET | READ | VI |
| `/web/visits/:id` | GET | READ | VI |
| `/web/visits/config` | GET | READ | VI · CQ |
| `/web/visits` (dead code) | POST | WRITE | VI |
| `/web/visits/:id` (dead code) | PATCH | WRITE | VI |
| `/web/visits/:id` | PUT | SEND | VI |
| `/web/visits/:id` (dead code) | DELETE | WRITE | VI |
| `/web/visits/:id/confirm` | POST | SEND | VI |
| `/web/visits/:id/cancel` | POST | SEND | VI |
| `/web/agency/settings/visits` | GET | READ | CV · CVE |
| `/web/agency/settings/visits` | PUT | WRITE | CV · CVE |
| `/web/properties/ads` | GET | READ | PR · VI |
| `/web/ads/xml/status` | GET | READ | PR |
| `/web/ads/xml/sync` | POST | WRITE | PR |
| `/web/properties/developments` | GET | READ | DV |
| `/web/developments` | POST | WRITE | DV |
| `/web/developments/:id` | PATCH | WRITE | DV |
| `/web/developments/bulk` | POST | WRITE | DV |
| `/web/developments/bulk-imports` | GET | READ | DV |
| `/web/developments/bulk-imports/:id/status` | GET | READ | DV |
| `/web/broadcasts` | GET | READ | BR |
| `/web/broadcasts/:id` | GET | READ | BR |
| `/web/broadcasts/:id/targets` | GET | READ | BR |
| `/web/broadcasts/property-owners` | GET | READ | BR |
| `/web/broadcasts/segments` | GET | READ | BR |
| `/web/broadcasts/available-dates` | GET | READ | BR |
| `/web/broadcasts/plan` | GET | READ | BR |
| `/web/broadcasts` | POST | SEND | BR |
| `/web/broadcasts/file` | POST | SEND | BR |
| `/web/broadcasts/validate-file` | POST | WRITE | BR |
| `/web/broadcasts/:id/file` | POST | WRITE | BR |
| `/web/broadcasts/:id/confirm-pending` | POST | SEND | BR |
| `/web/broadcasts/:id/schedule` | PATCH | SEND | BR |
| `/web/broadcasts/:id` | PUT | WRITE | BR |
| `/web/broadcasts/:id` | DELETE | WRITE | BR |
| `/web/broadcasts/:id/permanent` | DELETE | WRITE | mock only |
| `/web/agency/smart-suggestions` | GET | READ | * · BR |
| `/web/agency/smart-suggestions/:id` | GET | READ | * · BR |
| `/web/agency/smart-suggestions/:id/cooldown` | POST | WRITE | * · BR |
| `/web/smart-campaigns/onboarding-state` | GET | READ | SC · SCR · AO |
| `/web/smart-campaigns/ad-accounts` | GET | READ | SC |
| `/web/smart-campaigns/campaigns` | GET | READ | SC |
| `/web/smart-campaigns/campaigns/:campaignId/leads` | GET | READ | SC |
| `/web/catalog/listings` | GET | READ | CAT |
| `/web/catalog/listings/stats` | GET | READ | CAT |
| `/web/catalog/listings/include` | POST | WRITE | CAT |
| `/web/catalog/listings/exclude` | POST | WRITE | CAT |
| `/web/catalog/listings/resync` | POST | WRITE | CAT |
| `/web/catalog/product-sets` | GET | READ | CAT |
| `/web/catalog/product-sets` | POST | WRITE | CAT |
| `/web/catalog/product-sets/:id` | PATCH | WRITE | CAT |
| `/web/catalog/product-sets/:id` | DELETE | WRITE | CAT |
| `/web/agency/settings` | GET | READ | * (GET) · CDN · NO · overdue banner |
| `/web/agency/settings` | POST | WRITE | * (GET) · CDN · NO · overdue banner |
| `/web/agency/details` | GET | READ | * |
| `/web/agency/access-code` | GET | READ | AC · UM · HI |
| `/web/audiences/required-informations` | GET | READ | CQ |
| `/web/audiences/user-profiles` | GET | READ | CQ |
| `/web/audiences/user-profiles` | POST | WRITE | CQ |
| `/web/audiences/user-profiles/:id` | PATCH | WRITE | CQ |
| `/web/reengage/configs` | GET | READ | RE |
| `/web/reengage/configs/delay-minutes` | GET | READ | RE |
| `/web/reengage/configs` | PUT | WRITE | RE |
| `/web/reengage/rules/templates` | GET | READ | RE |
| `/web/reengage/rules` | GET | READ | RE |
| `/web/reengage/rules` | POST | WRITE | RE |
| `/web/reengage/rules/:id` | GET | READ | RE |
| `/web/reengage/rules/:id` | PATCH | WRITE | RE |
| `/web/reengage/rules/:id/activate` | POST | WRITE | RE |
| `/web/reengage/rules/:id/deactivate` | POST | WRITE | RE |
| `/web/reengage/rules/:id/attempts` | POST | WRITE | RE |
| `/web/reengage/rules/:id/attempts/:attemptId` | PATCH | WRITE | RE |
| `/web/reengage/rules/:id/attempts/:attemptId` | DELETE | WRITE | RE |
| `/web/reengage/rules/:id` | DELETE | WRITE | RE |
| `/web/facebook/callback` | POST | AUTH | MI |
| `/web/facebook/connect/finalize` | POST | WRITE | MI |
| `/web/facebook/pages` | GET | READ | MI |
| `/web/facebook/pages/:pageId` | DELETE | WRITE | MI |
| `/web/facebook/forms` | GET | READ | MI |
| `/web/facebook/forms/local` | GET | READ | MI |
| `/web/facebook/forms/meta` | GET | READ | MI |
| `/web/facebook/forms` | POST | WRITE | MI |
| `/web/facebook/forms/:formId/toggle` | PUT | WRITE | MI |
| `/web/facebook/forms/:formId/mapping` (no UI caller) | PUT | WRITE | MI |
| `/web/facebook/forms/:formId/questions` | GET | READ | MI |
| `/web/agency/charts/plan-consumption` | GET | READ | * · / |
| `/web/agency/charts/alerts` | GET | READ | / |
| `/web/agency/charts/lead-summary` | GET | READ | / |
| `/web/agency/charts/leads-by-channel` | GET | READ | / |
| `/web/agency/charts/lead-status-by-channel` | GET | READ | / |
| `/web/agency/charts/leads-per-hour` | GET | READ | / |
| `/web/agency/charts/leads-per-weekday` | GET | READ | / |
| `/web/agency/charts/leads-last-six-months` | GET | READ | / |
| `/web/agency/charts/administrative-report/volume` | GET | READ | AA |
| `/web/agency/charts/administrative-report/occurrence-ranking` | GET | READ | AA |
| `/web/agency/charts/administrative-report/conversation-resolution` | GET | READ | AA |
| `/web/report` | GET | READ | RV2 · RV3 |
| `/web/credit-analysis/summary` | GET | READ | CA |
| `/web/credit-analysis/chart` | GET | READ | CA |
| `/web/credit-analysis` | GET | READ | CA |
| `/web/agency/google-reviews/dashboard` | GET | READ | AV |
| `/web/finance/subscriptions` | GET | READ | FI |
| `/web/finance/consumption` | GET | READ | / · FI |
| `/web/finance/billing-account` | GET | READ | FI |
| `/web/finance/financial-contacts` | GET | READ | FI |
| `/web/finance/invoices` | GET | READ | * (overdue banner) · FI |
| `/web/finance/add-on-billing-accounts` | GET | READ | FI |
| `/web/finance/invoices/:id` | GET | READ | FI |
| `/web/finance/financial-contacts` | POST | WRITE | FI |
| `/web/finance/financial-contacts/:id` | PUT | WRITE | FI |
| `/web/finance/financial-contacts/:id` | DELETE | WRITE | FI |
| `/web/subscription/premium` | GET | READ | AC · AP |
| `/web/subscription/premium` | POST | WRITE | AC · AP |
| `/web/subscription/premium` | PATCH | WRITE | AC · AP |
| `/web/subscription/premium` | DELETE | WRITE | AC · AP |
| `/web/seats/summary` | GET | READ | AC · AP |
| `/web/seats/availability` | GET | READ | AC · AP |
| `/auth/users/me` | GET | READ | * · PF |
| `/auth/users/me/profile` | GET | READ | * · PF |
| `/auth/profile` | PATCH | WRITE | PF |
| `/auth/users/me/profile` | PATCH | WRITE | * · PF |
| `/auth/users/me/onboarding` | POST | WRITE | OB |
| `/auth/users/check-email` | GET | READ | AC |
| `/auth/agencies/search` | GET | READ | * (agency switcher) |
| `/auth/users` | GET | READ | AC |
| `/auth/users` | POST | WRITE | AC |
| `/auth/users/:id` | DELETE | WRITE | AC |
| `/web/teams` | GET | READ | AC |
| `/web/teams/:id` | GET | READ | AC |
| `/web/teams` | POST | WRITE | AC |
| `/web/teams/:id` | PATCH | WRITE | AC |
| `/web/teams/:id` | DELETE | WRITE | AC |
| `/web/teams/:id/members` | POST | WRITE | AC |
| `/web/teams/:id/members/:userId` | DELETE | WRITE | AC |
| `/web/teams/:id/members/:userId` | PATCH | WRITE | AC |
| `/web/teams/:id/distribution` (no UI caller) | GET | READ | AC |
| `/web/teams/:id/distribution` (no UI caller) | PUT | WRITE | AC |
| `/web/teams/lead-types` | GET | READ | AC |
| `/web/teams/occurrences/availability` | GET | READ | AC |
| `/web/teams/:id/roulette` (no UI caller) | PUT | WRITE | AC |
| `/web/teams/:id/metrics` | GET | READ | AC |
| `/web/permissions` | GET | READ | * |
| `/web/permissions/teams` | GET | READ | * |
| `/web/notifications` | GET | READ | mock only (404 live) |
| `/web/notifications/:id/read` | PATCH | WRITE | mock only (404 live) |
| `/web/notifications/read-all` | PATCH | WRITE | mock only (404 live) |
| `/web/notification-events` | GET | READ | NO · CP |
| `/web/flows/:flowSlug/onboarding-progress` | GET | READ | CK · CH · LE · AC · BR |
| `/web/flows/:flowSlug/steps/:stepSlug/complete` | POST | WRITE | CK · CH · LE · AC · BR |
| `/web/checklist/channels-status` | GET | READ | CK |
| `/web/checklist/channels` | POST | WRITE | CK |
| `/web/test-users` | GET | READ | CK · CT · LE |
| `/web/test-users` | POST | SEND | CK · CT · LE |
| `/web/test-users/:id` | DELETE | WRITE | CK · CT · LE |
| `/web/banners/home` | GET | READ | / |
| `/web/whats-new` | GET | READ | WN |
| `/api/analytics` | GET | READ | * |
| `/api/analytics` | POST | WRITE | * |
| `/api/intercom` | POST | READ | * |
| `/api/bubble-health` | GET | READ | every Bubble route |
| `/api/geocoding/autocomplete` | GET | READ | DV · PR |
| `/api/geocoding/geocode` | GET | READ | DV · PR |
| `/api/access-code/validate` | POST | AUTH | HI · ACC |
| `/api/access-code/session` | GET | READ | HI · ACC |
| `/api/access-code/session` | DELETE | AUTH | HI · ACC |
| `/api/auth/* (NextAuth: signin, signout, session, csrf, callback/keycloak)` | * | AUTH | * |
| `https://bff.lastro.services/api/v1/auth/logout` | DELETE | AUTH | * |
| `{KEYCLOAK_ISSUER}/protocol/openid-connect/token` | POST | AUTH | * |
| `https://sso.lastro.services/realms/lastro-prod/protocol/openid-connect/logout` | GET | AUTH | * |
| `https://www.facebook.com/v21.0/dialog/oauth` | GET | AUTH | MI · FBC |

### 58.1 Endpoints called from Bubble only (not in `endpoints.json`)

From the Bubble API Connector catalogue (`bubble-app-definition.md` §2). Hosts are Bubble parameters.

| Group | Calls | Used by | Safety |
| --- | --- | --- | --- |
| Core — business settings | GET/PUT `business-settings/{identification, visit-policy, rental-info, rental-documentation, rental-guarantees, rental-contract-terms, sale-info, sale-documentation, sale-financing, bot-work-hours, work-hours, bot-profile}` | `/configs_my_business`, `/platform` | R · W |
| Core — behaviour | GET/PUT `behavior-settings` (+ `/info`, `/visit-hours`) | `/configs_behavior`, `/configs_property_info`, `/configs_visits` (Bubble drawer), `/configs_reengage` (legacy card) | R · W |
| Core — onboarding | flows progress/complete, lead-origins CRUD, XML validate + ETL load + feed status, forwardings crm-status/validate, forwarding-settings | `/platform` | R · W |
| Core AI — prompt | GET/PUT `prompt/rea/{id}/phones`, `…/recess`; **POST `prompt/rea/{id}/refresh`** | `/configs_my_business` (after every save) | W |
| Core AI — chat | `chats/{id}/feedback` GET/POST, `chats/{id}/history`, onboarding chat `chats/onboarding[/{id}][/message]` | `/history`, `/platform` | R · W · S |
| Core AI — guards | `users/block/rea/{agency}` check/POST/DELETE · `agents/malicious-instructions/verify` | chat (I) | R · W |
| Core AI — WhatsApp | GET/PUT `dialog360/account-info` | `/configs_whatsapp_profile` | R · W |
| BFF via Bubble | `web/auto-forwarding/{intervals,config}`, `web/forwardings` (+PUT `{ids}`), `web/required-information` (+`/selected` GET/POST) | `/configs_behavior` | R · W |
| WABA onboarding | `waba/onboardings/start`, `es-complete`, `es-failed`, `waba/{id}/status`, `waba/count`, `waba/latest` | `/platform` | W (Meta Embedded Signup) |
| Legacy core ("Lastro Refactor") | dashboard, report, leads filter v2, enhance/force/batch, access-code GET+check, developments CRUD, property-owners (list, dates, upload, confirm, schedule, batch-xlsx), reachout (validate, schedule confirm, dates), payments, campaigns-for-filters | `/leads` (Bubble variant), `/developments` (Bubble), `/owners`, `/history` | R · W · S |

### 58.2 Websockets

| Socket | Events | Routes |
| --- | --- | --- |
| `/ws/chats` | join/leave; chat_updated, chat_list_item_updated, chat_list_update, chat_suspended, new_message, typing, message_status_updated, tag_definition_updated, feed_sync_completed | CH · HI |
| `/ws/notifications` | notification:created | * |
| `/ws/properties` | feed_sync_completed | PR |

---

## 59 · GAP list — what is still not seen live

Rules for every live step: owner's session, own agency id only, open → read → close **without saving**, never click a control that maps to a W/S endpoint above, never type in a field that triggers a write. Screenshots with staff or lead data go to the private set outside the repo.

### 59.0 Live gap pass — 2026-10-14 (owner session, read-only, nothing saved)

Every drawer/modal below was opened, read and closed with ✕ / Cancelar / Escape; no Salvar, Criar, Próximo-after-typing, toggle or popup button was pressed. No personal data recorded.

| # | Result | Evidence |
| --- | --- | --- |
| a1 | **Not reachable read-only.** Step 2 needs an edit: "Próximo" is `disabled` until the rule set changes. Stays code-only (`routes.md` /configs_qualification). | C live (button `disabled=true`) |
| a2 | Minutes drawer: switch "Reengajamento em minutos" + **Intervalo** select = 5, 10, 15 … 55 minutos, 1 hora (step 5); copy "Funciona em qualquer horário"; info box: lead reply restarts the flow, leads who closed the conversation are never contacted, never-replied leads are covered by the hours tier. Hours drawer: switch + select **1–11 horas**; copy "Funciona das 8h às 20h"; targets leads who stopped replying **or never replied**. URL mode `?reengage=minutes|hours`. **Resolves §0.2 #2: 1–11 h (Bubble/live) is right; the mock list 1/2/4/8/12/24 is not what ships.** | C live |
| a3 | Visit drawer (`?type=visit`): status chip · checkbox "Diferenciar configuração para leads de compra e aluguel" · switch "Pré-agendamento de visita" · switch "Solicitação de CPF obrigatória?" · "Período disponível": Tempo mínimo (Dias + Horas selects), Tempo máximo (Dias) · "Horários disponíveis": De/Até per weekday Segunda–Domingo (current 09–17 weekdays, 09–18 weekend). `/configs_visits_embed` renders the same editor chrome-less (for the Bubble drawer). | C live |
| a4 | Template preview drawer: name, status, category, WhatsApp-bubble preview, "Simule com exemplos" (one input per variable, local), [Excluir modelo] (W), [OK]. "Novo modelo de mensagem" modal: Nome do modelo · Categoria (Administrativo, Campanha, Cobrança, Documentação, Primeiro contato, Reativação, Visita, Outros) · Conteúdo (max **1024** chars) · "Adicionar parâmetros" chips: Nome da pessoa, Nome da Lais, Nome da imobiliária, Mensagem, Data da visita, Código do imóvel, Link do imóvel, Nome do atendente, Imóvel da visita, Data e horário da visita · [Cancelar] [Criar]. | C live |
| a5 | Bubble `configs_behavior` opened standalone renders the tab headers only (body needs the parent's postMessage token). Not retried inside casa. BUBBLE-DEF (§ Bubble forms) stays the source. | C live (empty body) |
| a6, a7 | **Skipped** — the Conversas page lists lead names/phones; held back with bucket (d). | — |
| a8 | "Filtro de leads": Data do primeiro contato (range) · Nome · E-mail · Telefone · Imóvel · Link da conversa · Operação (Aluguel, Compra, Administração) · Atendimento da Lais (Sem atendimento, Atendido pela Lais) · Status CRM (Enviado ao CRM, Erro no envio, Não pronto) · **Canal: 60 origins** (portals incl. the Guia de Imóveis regional family, Grupo Zap, ImovelWeb, Chaves na Mão, NetImoveis, Kenlo, RD Station; ads Facebook/Instagram/Google; WhatsApp, Site Próprio, Placa, Remarketing, Conversas; **AI assistants ChatGPT, Claude, MCP**) · Campanha de origem · Anúncio de origem · [Limpar] [Filtrar]. | C live |
| a9 | Calendar views not renderable while visits are off (empty state only). Code-only. | C live |
| a10 | "+ Adicionar usuário": drawer "Informações da conta", Passo 1 de 3: Nome completo, E-mail (steps 2–3 need typing — not reached; code: level + seat). "+ Criar equipe": "Configurar nova equipe", Passo 1 de 3: Nome da equipe* + radio "Esta equipe atende clientes diretamente após a Lais?" Sim (assumes conversations when Lais ends pre-service; can receive leads automatically) / Não (manual assignment only). Team row [Editar] = menu Configurações · Usuários · Excluir equipe (W). | C live |
| a11 | Skipped (billing contacts are private). | — |
| a12 | "Filtro de notificações": Data · Operações (Todas, Aluguel, Compra) · **Tipo: 11 types** — Solicitação de pré-agendamento de visita, Cobrança de atendimento, Relatórios da Lais, Remarketing, Captação, Atualização de base de imóveis, Novo lead gerado, Novo atendimento, Nova mensagem, Avaliações no Google (+ the toggle "Notificar lead pronto para atendimento", W, untouched). | C live |
| a13 | `/relatorio-v2`: no export menu exists (gap was speculative); controls = Operação combobox, month picker, tabs Imóveis/Bairros, property codes are buttons. `/relatorio-v3` = same content; the duplicated Top-10 rows bug is present in both. | C live |
| a14, a15 | Bubble (developments, owners) — same standalone-render limit as a5; not retried. | — |
| a16 | Not repeated (S1 already covers Início). | — |
| a17 | `/relatorio-v3` see a13 · `/captacao` renders an **empty** shell (title only — the sidebar uses `/notifications?type=lead-property-acquisition&view=acquisition` instead) · `/plans` = Bubble iframe `legado.lais.ai/plans` · `/configs_visits_embed` see a3. | C live |
| a18 | User menu = **Editar perfil** (`/perfil`) · **Sair**. | C live |

Also seen: the remarketing upsell popup ("Dispare o Remarketing para N leads", [Depois] [Ir para Disparos]) appears mid-session on any page; never touched (b6).

### 59.0b Live pass 2 — 2026-10-15 (owner session, read-only, nothing saved)

| Item | Result | Evidence |
| --- | --- | --- |
| a7 `/chats` "+" | Drawer **"Contato — Escolha quem a Lais deve chamar"**, Passo 1 de 3: Nome da pessoa*, Número do contato* (format `(00) 00000-0000`), [Próximo] disabled until filled. Not advanced (steps 2–3 = template + send, S-class). | C live |
| a6 `/chats?view=kanban` | Board: fixed column **"Todas (n)"** with eye toggle, collapsed **"Arquivadas"** lane, **"Adicionar coluna"** → popover **"Selecionar etiqueta"** (search, "Sem etiqueta", "Criar nova etiqueta"): **kanban columns are tags** (one column per etiqueta), not saved filters. Agency has no tags yet. Closed with Escape. | C live |
| b2 Régua 1 | `/configs_reengage/rules/{uuid}`: card **Regras** [Inativo] Operação "Aluguel e compra", Período "Das 8h às 20h", [Editar] → drawer "Editar régua de reengajamento": switch "Ativar régua" · Nome da régua · Operação checkboxes Aluguel/Compra · notes ("starts after the last default-reengage attempt", "leads who closed are not contacted", **"A Lais pode reescrever o texto da mensagem com as próprias palavras"**, "only leads who interacted then stopped") · [Excluir régua] (W) · [Salvar]. Card **Tentativas de contato 0/3** + "Nova tentativa de contato" (not clicked). **Code (chunk 2470) closes the gap:** client `getConfigs/getDelayOptions/getTemplates/upsertConfig(PUT configs)/listRules/createRule(POST)/getRule/updateRule(PATCH)/activateRule(POST …/activate)/deactivateRule(POST …/deactivate)/addAttempt(POST …/attempts)/updateAttempt(PATCH …/attempts/{id})/deleteAttempt/deleteRule`; attempt = `{attemptIndex, delayValue, delayUnit (default "days"), templateId, enabled}`; an active rule needs ≥1 attempt; attempt without template shows "Sem modelo". Help text says "até 5 tentativas para compra ou até 3 para locação" while the card limit is 3 (`maxCount:3`) — vendor inconsistency (§0.2). | C live + C code |
| a10 team Configurações | Drawer "Editar configurações": Nome da equipe* · "Esta equipe atende clientes diretamente após a Lais?" Sim/Não · **"Como os leads serão atribuídos?" — Via CRM (Padrão: lead sent to CRM with an assignment link) / Via Lais (Atendimento mais rápido: Lais assigns directly to attendants when pre-service ends)** · switch **"Manter atribuição ao último responsável"** (returning lead goes to the same attendant) · [Salvar]. Team menu: Configurações · Usuários · Excluir equipe. | C live |
| a5, a14, a15 Bubble | `/configs_behavior` inside casa: spinner forever (legado iframe blocked by third-party cookies in this Chrome), same as S1. Final: BUBBLE-DEF is the source for these forms. | C live |
| Stage 3 conversations | Owner authorized (2026-10-15); the session's PII classifier denied the read-only `GET /web/chats/agency` again. Not attempted further. | — |

### 59.a Safely viewable read-only (open, capture, close)

| # | Route | Open | Capture | Why it is safe |
| --- | --- | --- | --- | --- |
| a1 | `/configs_qualification` | Próximo (step 1 → 2) | Step 2 "Resumo" copy and layout; then exit "Sair da edição?" → Confirmar | Writes only on Salvar (C code: create/update are in the save handler) |
| a2 | `/configs_reengage` | [Editar] on Reengajamento em minutos, then on horas | option lists (resolves §0.2 #2), copy; Cancelar | `PUT` only on Salvar |
| a3 | `/configs_visits?type=visit` | edit drawer | weekday grid, period fields, CPF switch, per-operation tabs; Cancelar | `PUT` only on Salvar |
| a4 | `/configs_templates` | one card's preview drawer; "+ Criar modelo de mensagem" modal | preview + "Simule com exemplos" (local); form fields; close | `POST /web/templates` only on submit |
| a5 | `/configs_behavior` | tab Perguntas essenciais (count only), tab Envio ao CRM | "Perguntas ativas (n)" again (§0.2 #16); the 5 sections incl. Pesquisa com clientes | read-only view; do not press Editar (BUBBLE-DEF already has the drawers) |
| a6 | `/chats` | kanban "+ Adicionar coluna" popover; filter drawer Etiquetas list | options; close | `POST` only on confirm |
| a7 | `/chats` | "+ Nova conversa" drawer step 1 **without typing a number** | fields, copy; close | validate-phone fires only on typing (GET), send only at step 3 |
| a8 | `/leads` | Filtros drawer | every filter control; Limpar; close | GET-only filters |
| a9 | `/visits` | month / week / day views | empty calendar chrome, type select | GET-only |
| a10 | `/acessos` | "+ Adicionar usuário" wizard steps 1–3 **without typing an e-mail**; "+ Criar equipe" steps 1–2; team [Editar] | wizard layout, role/seat cards, distribution options; close | `POST` only on the last step |
| a11 | `/financeiro` | tab Conta de faturamento | layout only (CNPJ and contacts are private — not recorded) | GET-only |
| a12 | `/notifications` | Filtro de notificações › TIPO list | full type option list | GET-only |
| a13 | `/relatorio-v2` | other operation/month, export menu (do not download) | export options; Bairros for Compra | GET-only |
| a14 | `/developments` | Bubble "Adicionar empreendimento" form; existing item detail | fields; close without saving | Bubble saves only on confirm |
| a15 | `/owners` | filters / date pickers | controls (list empty) | read-only |
| a16 | `/` | months, category tabs, carousel slides 2–3 | chart variants | GET-only |
| a17 | URL-only routes | `/relatorio-v3`, `/captacao`, `/plans`, `/trainings`, `/configs_visits_embed`, `/user-management` users list | what renders | GET / Bubble render |
| a18 | Shell | user menu, Novidades header link | menu items | navigation only |

### 59.b Needs code confirmation first (opening may write)

| # | Route / control | Risk | What to check before opening |
| --- | --- | --- | --- |
| b1 | `/broadcasts` "+ Novo disparo" wizard | `wizardStep` is persisted and `createAsDraft` exists: moving between steps may `POST /web/broadcasts` a draft | find the step-change handler in the broadcasts chunk; open only if Próximo is local |
| b2 | `/configs_reengage` "+ Nova régua" and `/configs_reengage/rules/:id` | "+ Nova régua" may `POST /web/reengage/rules` at once (default name "Régua N"); attempt editor is a lazy chunk we do not hold | fetch/read the lazy chunk; open the existing Régua 1 read-only first |
| b3 | Opening any chat (`/chats` pane, `/history`) | whether `GET /web/chats/:id` marks read server-side is U; `?chatId=` links auto-assign | already-read chats only; never follow `?chatId=` links |
| b4 | `/creation-user-test` | creating the test user probably makes the AI message that number (S-I) | do not open while the agency is checklist-exempt; read the 9934 form handler only |
| b5 | Bubble [Editar] drawers on `/configs_my_business`, `/configs_whatsapp_profile`, `/configs_behavior` | a stray click changed a dropdown once (2026-10-13, discarded) | not needed: BUBBLE-DEF covers the fields; open only if a field is missing from §23–§27 |
| b6 | Smart-suggestion popup, overdue-invoice banner | Depois / dismiss / close all POST | never interact; let them time out |
| b7 | `/visits` visit dialog | needs an existing visit (none); Agendar/Alterar/Cancelar message the lead | n/a until visits exist; never press the actions |

### 59.c Gated or never renderable here — code-only is final

`/credit-analysis` (flag) · `/properties` (flag) · `/catalogs` (flag; API 404) · `/smart-campaigns`, `/smart-campaigns/remarketing` (flag, needs_oauth, no pixel) · `/atendimento-administrativo` (no add-on) · `/performance` (agency type) · `/checklist` (exempt) · `/platform` (agency not onboarding) · `/onboarding`, `/onboarding/sucesso` (user already onboarded). In-page flags off for this agency: message ticks, reply-to, "Sem etiqueta" filter, `visit_action_notifications`, chat credit-analysis panel, browser notifications, team metrics (U), change-plan link (U). Visits module disabled ⇒ the whole visit-handling UI is code-only unless the owner enables visits.
NOT-CAPTURED routes (`/access-code`, `/debug`, `/facebook/callback`, `/pacotes-adicionais/…`, `/platform-meeting-schedule`, `/unauthorized`, `/auth/signin`, `/auth/error`): only a static download of their chunks (owner-approved, per download) could add anything; `/debug` stays out.

### 59.d PII-blocked (Stage 3)

The session's PII check refused reading more lead conversations; continue only with an owner permission rule or anonymised excerpts the owner pastes.

| Surface | What would be learned |
| --- | --- |
| `/chats` conversation pane + Interações + Resumo do chat + Notas | turn structure, slot extraction, summary format, intent flags, reengage wording, handoff moments |
| `/leads` "Ver resumo" modal | the lead-level `conversationSummary` format |
| `/notifications` card expansion (all types) | the event payload a human sees (structContent) |
| Captação cards | how a "potencial captação" is phrased and justified |
| `/broadcasts/:id` targets | per-target status flow (message-sent → replied → enhanced) |
| `/avaliacoes` review texts | n/a for the build (counts suffice) |
| `/acessos` users, `/financeiro` contacts | n/a for the build (shapes suffice) |

---

## 60 · Open questions

1. Visits: which of the two writers (§0.2 #1) does the agent read, and why does `view=month` fail (§0.2 #5)?
2. Perguntas essenciais: 0 active on the card vs 5 selected in the API (§0.2 #16).
3. Reengage hours: which option list is real (§0.2 #2)?
4. Archive and kanban-move-to-archived: confirm they hand the chat back to the AI (S-I) — matters for our pause/resume rules.
5. Auto-resume after 5 days idle and auto-pause on a human message: server rules inferred from copy; never observed.
6. Google review request: which conversations trigger it (quality score? end state?).
7. "Cobrança de atendimento": how the AI decides a lead is demanding follow-up.
8. Captação detection (`isPropertyAcquisition`): rule or LLM classification?
9. `identification`, `bot-work-hours`, `work-hours`, `bot-profile` business-settings: where are they edited after onboarding (§23 GAP)?
10. Bubble `/history` vs native access-code gate: which one is active (`new-access-code-page`)?
11. `/captacao`: does it render a Bubble page, or is it dead?
12. Template send cap per chat (`templateSendPolicy.maxAttempts`) value for this agency.
13. Credits: is one credit charged per lead, per interaction (episode) or per conversation? (`lead-summary` splits qualified / unqualified / unattended consumption.)
14. The 4-digit access code and the URL `agency` param on Bubble pages: owner's call on whether to report to Lastro (observations only, never tested).
