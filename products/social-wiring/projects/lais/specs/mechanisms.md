# Lais — Mechanisms behind the pages

How Lais (`casa.lais.ai` + Bubble `legado.lais.ai`, vendor Lastro) works behind each screen. Reconstructed 2026-10-14, **offline**, from what Stages 1 and 2 already hold: `analysis/*.md`, `analysis/endpoints.json`, `specs/page-map.md`, `captures/xhr-2026-10-13/README.md`, `analysis/bubble-app-definition.md`. No new browsing, no conversation content. Page-level detail stays in `specs/page-map.md` and `analysis/routes.md`; where each mechanism lands in social-wiring is in `specs/sw-reconstruction-map.md`.

Modelled on `../../core-studio/specs/mechanisms.md`. The goal is the *intelligence*: what each mechanism stores, how state moves, what triggers it, where an LLM is called, and what we still cannot see.

**Tags:** **C** = CONFIRMED (seen in code, the Bubble definition, a live screen or a captured response shape) · **I** = INFERRED (reasoned, not seen working) · **U** = UNKNOWN. A claim without a tag inherits the tag of its section heading line.

**Sensitivity.** No lead names, phones, e-mails, chat text, staff names or the agency access code appear here. The agency's own *configuration* values (e.g. "reengage after 15 min") are product content and are kept.

---

## 0 · Platform architecture

| Layer | What | Tag |
| --- | --- | --- |
| Front ends | Next.js App Router on Vercel (`casa.lais.ai`) + a legacy **Bubble.io** app (`legado.lais.ai`) embedded per route as an iframe; the parent sends the Keycloak token by `postMessage {type:"AUTH_DATA",token,agencyId,userId}` after `REQUEST_AUTH_DATA`, origin-checked. Separate attendant app `atendimento.casa.lais.ai` + mobile app "Casa da Lais" | C |
| BFF | `bff.lastro.services/api/v1` — **Go** (validator messages) over **Postgres** (`pg:` errors); envelope `{data, message}` / `{code, status, error, category}` | C |
| Core AI service | `{version}-ai.lastro.services`: `prompt/rea/{agency}/refresh|phones|recess`, `chats/{id}/feedback|history`, `dialog360/account-info`, `agents/malicious-instructions/verify`, `users/block/rea/{agency}` | C |
| Auth | Keycloak `sso.lastro.services` realm `lastro-prod`, client `casa-da-lais`; NextAuth JWT session (30 d) with refresh; a second Keycloak client for `/history` access-code sessions (`KEYCLOAK_HISTORICO_*`) | C / I |
| Tenancy | Agency = **REA** (real-estate agency); every call carries `x-agency-id`; a user holds memberships in N REAs with `role`, `seatType`, `isGestor` | C |
| Realtime | EventHub websockets `wss://eventhub.lastro.services/ws/{chats,notifications,properties}?token=…&agencyId=…` (§21) | C |
| Channel | WhatsApp Business (Cloud) API through **360dialog**; Meta Embedded Signup (`waba/onboardings/*`) | C |
| Flags | LaunchDarkly (context kind `agency`), 25 flags; ~90 permission keys with `{allowed, reason, blockBehavior hide|disable}`; plan gate HTTP 402 `premium_module_required` → `/add-ons/pro` | C |
| Third parties | Vista CRM (this agency), 16 ERPs (administrative add-on), CredAluga, Google Reviews, Intercom, Amplitude, Sentry, Vimeo, MapLibre/Carto | C |

---

## 1 · Lead intake per channel

### 1.1 Channels (C)
| Channel | How a lead arrives | First message | Tag |
| --- | --- | --- | --- |
| WhatsApp direct | lead writes to the agency's Lais number | lead speaks first; Lais answers inside the 24 h window | C |
| Portals (33 origin codes `…Lais`, e.g. `GrupoZapLais`, `ImovelWebLais`, `ChavesNaMaoLais`; Bubble option set lists 56 channels) | portal posts the lead to Lastro (the agency points the portal's "send leads to CRM" at Lastro) | **Lais speaks first** with a Meta-approved first-contact template ("Abordagem comercial / neutra") | C (codes) / I (portal webhook) |
| Meta Lead Ads (Facebook/Instagram forms) | `/configs_meta_integration` OAuth → pages → forms → field mapping; leads "go straight to Lais and are auto-served" | template | C |
| Site próprio / Placa / Remarketing | origin codes `SiteProprioLais`, `PlacaLais`, `RemarketingLais` | U per channel | C (codes) |
| Broadcast reply | a remarketing / owner-update broadcast target replies → becomes a conversation again (§10) | — | I |

### 1.2 Data model
`Lead {id, chatId, name, phoneNumber, email, origin, transactionType rent|buy|administrative, type realestate|administrative|propertyowner, status, phase, attendedByLais, attendanceLabel, crmStatus, propertyLink, clientListingId, isDevelopment, development, campaign, ad, conversationSummary, creditAnalysisStatus, vatNumber, isBlocked, isTest, forwardingDeliveries[], createdAt, enhancedAt, metadata}` — one Lead ↔ one Chat. **C**

### 1.3 Lead status state machine (C values, I transitions)
```
created ─► message-processing ─► message-sent ──(lead replies)──► message-replied ──(qualified)──► enhanced
                               └► message-sent-error                                 └► enhanced-error ─(retry)─► enhanced
any non-final ──(timeout / expiry)──► expired
UI: enhanced = "Enviado ao CRM" · enhanced-error | expired = "Erro no envio" · else "Não pronto"
```
"Atendido pela Lais" vs "Sem atendimento" is a separate flag (`attendedByLais`). A portal lead with no conversation can still be pushed (`auto-sent` → "Enviado automaticamente"). **C** (labels) / **I** (exact rule)

### 1.4 Unknown
Exact portal ingestion endpoint (server side) · de-duplication rule when the same phone arrives from two channels (one chat per phone is **I**) · how `phase` differs from `status` · validate-phone runs before the first template (`valid | invalid | existing | archived | blocked | error`, C) but when exactly is **U**.

---

## 2 · Chat lifecycle and AI on/off

### 2.1 Data model (C)
`Chat {id, lead{…}, suspended, canBeSuspended, canSendTemplate, templateSendPolicy{allowed, sentCount, maxAttempts}, archived, unread, pinned, pinnedAt, tagIds[], userAssigned ("none"|userId), teamAssigned, lastActivity, creditAnalysisStatus, feedback{reaction like|dislike, comment}, totalInteractions}`.
`Message {id, content, role user|assistant|human, type, status received|created|pending|read|delivered|failed, chunkReference, replyTo, media links, isAudio|isVoice|isDocument|isVideo, metadata{suspensions[], leadOrigin, isReengage, isPropertyOwner, forwarded, location}, showSender, senderInfo}`; messages come grouped by day. **C**

### 2.2 AI ⇄ human (C)
```
"Lais atendendo" (suspended=false) ──PATCH /web/chats/:id/suspend {suspended:true}──► "Atendimento manual" (suspended=true)
"Atendimento manual" ──(same PATCH false) or (5 days without messages: auto-resume)──► "Lais atendendo"
```
Every switch is stamped in `message.metadata.suspensions[{status, requesterName}]`. `canBeSuspended` hides the switch for some chats. The 5-day auto-resume is UI copy (**C**) — the scheduler is server side (**U**).

### 2.3 WhatsApp window (C)
Composer state `window_open | window_closed | unauthorized | unauthorized_suspended`. Free text only within 24 h of the lead's last message; otherwise a template; template cooldown 24 h; `CHAT_TEMPLATE_PENDING_REPLY` blocks a second template before a reply; per-chat cap `templateSendPolicy.maxAttempts`.

### 2.4 Other chat actions (C; all WRITE/SEND, never exercised)
Assign (`self-assign`, `transfer`), archive, block (`FRAUDULENT_ACTIVITY 0 · SPAM 1 · HARASSMENT 2 · OTHER 3` + details), like/dislike/feedback on the AI's service, pin (≤5, mirrored in `localStorage`), tags, kanban move (`/web/kanban/columns`, `kanban-move`), new conversation by template (`/web/chats/new/messages/human/template`), media upload (`MEDIA_001..006`), human messages optionally prefixed with the sender's name (`prefixHumanMessagesWithSenderName`).

### 2.5 Unknown
Whether opening a chat marks it read (GET side effect) · whether human messages are sent while `suspended=false` (both speak?) · how the AI decides `typing` side `assistant`.

---

## 3 · Interactions (lead-episodes), AI summary and intent flags

### 3.1 Data model (C shape from `chats/:id/interactions`)
`Interaction {id, status, crmStatus{label, color}, type, origin, transactionType, createdAt, metadata, summary, location, budget, forwardingDelivery{status, triggeredBy, enhancedAt}}`. Types seen in code: `PROPERTY_ACQUISITION` "Captação", `VISIT` "Visita"; on screen "Comercial". Property status per interaction `available | unavailable | unknown | available_update | awaiting_dispatch`.

### 3.2 Mechanism (I)
One chat holds N interactions — each time the lead comes back with a new need, a new episode starts. At the end of an episode an LLM writes a **narrative summary**, the **extracted slots** (location, budget …), and **intent flags** shown in italics ("Foi identificado que o lead quis encerrar o atendimento"). The CRM push is per interaction (`forwardingDelivery`), so one lead can be sent several times.

### 3.3 Unknown
What opens/closes an episode (silence timer? operation change? **U**) · the summary prompt (**U**, server side) · full list of intent flags (**Stage 3**: only visible by reading conversations).

---

## 4 · Slot filling — Perguntas essenciais

### 4.1 Data model (C)
- Catalogue: **63 questions in 6 categories** (Operação · Informações do lead · Características do imóvel · Localização · Informações financeiras · Interesses gerais); item = label + LLM hint (`description`) + category + optional operation scope. `GET web/required-information`.
- Selection: `GET/POST web/required-information/selected`; limits from the API: `maxNumberQuestions` **8**, `maxNumberQualifyingQuestions` **5**; "Objetivo: comprar ou alugar" required and locked by support.
- CRM view of the same slots: `GET web/audiences/required-informations` → `{information, category lead|real_estate, required, isNumeric, isCurrency, profileField{fieldName, fieldType string|numeric}}` (e.g. Faixa de preço → `price_max`).

### 4.2 Behaviour (C copy / I mechanism)
The agent does **not** run a questionnaire: it infers what the lead already said and asks only what is missing. A **qualificatória** question is pursued until answered and gates the CRM push. A question used by a CRM criterion cannot be switched off. Changing the selection triggers a prompt rebuild (§5).

### 4.3 Where slots surface
Interaction panel (extracted values), Leads list (operation, property code), Relatórios (bairro, tipo, faixa de preço, quartos aggregated monthly, §8 of page-map), Meta CAPI signals (§17).

### 4.4 Unknown
Extraction call (per message vs end of episode, **U**) · storage of slot values per lead (`profileField` suggests a lead profile with typed fields, **I**).

---

## 5 · Prompt compilation (knowledge base → system prompt)

### 5.1 Data model (C)
`business-settings/{identification · visit-policy · rental-info · rental-documentation · rental-guarantees · rental-contract-terms · sale-info · sale-documentation · sale-financing · bot-work-hours · work-hours · bot-profile}` + `behavior-settings` (+`/info`, `/visit-hours`) + `prompt/rea/{id}/phones` + `prompt/rea/{id}/recess` + agency settings (`useIptu`, `prefixHumanMessagesWithSenderName`, `allowEnhanceAcquisitionLeads`). Every field is typed (enums, chips, numbers); some are support-only.

### 5.2 Save pattern (C, Bubble workflows)
```
[Salvar] in a drawer ─► PUT business-settings/<section>  (or PUT prompt/rea/{id}/phones|recess)
                     ─► POST {core-ai}/prompt/rea/{agency}/refresh
                     ─► toast "Alterações feitas com sucesso!"
```
The customer never sees or edits prompt text. Unsaved drawer → "Sair da edição?" guard.

### 5.3 Guards (C)
`agents/malicious-instructions/verify` (prompt-injection check on inbound text), `users/block/rea/{agency}` (blocked contacts), chat feedback thumbs (training signal, I).

### 5.4 Unknown
The compiled prompt itself · model/provider · tool list (property search, visit slots, CRM) · whether the prompt is versioned.

---

## 6 · CRM forwarding ("Envio ao CRM")

### 6.1 Data model (C)
- Connector: `web/forwardings` `[{type:"vista-v2", enableAutoForwarding}]` — this agency pushes to **Vista**.
- Rules = audience **user-profiles** `{name, identifier, transactionType buy|rent|both, type filter|priority, active, fields[{fieldName, operator filled|greater-than-or-equal|less-than-or-equal|between, value}]}`. Groups are **OR**ed, criteria inside a group **AND**ed. Locked base group "Comportamento = Qualificado via inteligência da Lais" (`type:"filter"`); "Visita pré-agendada via formulário" locked when visits are on.
- Cold leads: `web/auto-forwarding/config {enabled, sendType:"interval", intervalMinutes}`; options 30 min–10 h after the last reengage attempt, or next morning 05:00–06:00.
- Policies (Bubble `configs_behavior`): **potenciais captações** (send to CRM vs notify only) · **leads frios** · **WhatsApp inválido** (auto-send) · weekly satisfaction survey opt-in.
- Delivery record per lead: `forwardingDeliveries[{status, triggeredBy, enhancedAt}]`; `triggeredBy ∈ {auto-sent, enhanced-by-client, qualified-by-client, invalid-phone-number, message-delivery-error, out-of-scope, qualified-by-lais, retry, visit-scheduled}`; `qualificationSource ∈ {lais, manual, auto, none}`.

### 6.2 Endpoints (C; never called)
`POST /web/leads/:id/enhance` (202 async) · `POST /web/leads/batch-enhance` (≤60) · `PATCH /web/leads/:id/enhance/force` · chat action "Enviar ao CRM" (`chat:send-to-crm`). Team flag `autoCrmEnabled` (I: push on distribution).

### 6.3 Triggers (C reasons / I wiring)
qualified by AI · criteria match · visit scheduled · manual · invalid phone · cold timer · out of scope · retry after error.

### 6.4 Unknown
Payload sent to Vista · retry policy · what "expired" means in time.

---

## 7 · Reengagement

### 7.1 Data model (C)
- `ReengageConfig {enabled, reengageType reminder|final, delayMinutes}` — reminder 5–60 min any hour (agency: 15 min); final 1–11 h in Bubble / 1–24 h in code, business hours 08–20 (agency: 4 h).
- `ReengageRule` ("Régua") `{id, name, buy, rent, enabled, attempts[≤3]{attemptIndex, delayValue, delayUnit, templateId, enabled}}`; rule templates by slug `lead_reengage_short · lead_reengage_long · lead_reengage_brief_message · lead_reengage`.

### 7.2 State machine (C copy / I timers)
```
lead silent ─(reminder delay)─► nudge 1 (free text, inside 24 h) ─(final delay, 08–20 h)─► nudge 2
   └─ any reply ⇒ flow restarts · explicit close ⇒ never contacted again
after last standard attempt ─► Régua (≤3 template attempts, outside 24 h) ─► cold-lead CRM push timer (§6)
```
Since 2026-07-29 it also re-contacts leads who **never** replied (on by default); recovered leads return to qualification at no extra credit. System event in the timeline: "Lead não respondeu mais. Lais reativou a conversa". **C** (changelog + timeline).

### 7.3 Unknown
Whether nudge texts are LLM-written or fixed · the régua attempt editor (`/configs_reengage/rules/:id`, not in the bundle).

---

## 8 · Visit pre-scheduling

### 8.1 Data model (C)
`VisitSettings {mode unified|per_operation, general|perOperation{buy,rent}: {enabled, documentRequired (CPF), daysToOffer 3–31, minDaysToOffer 0–31, minHoursToOffer 0–23, schedule{monday..sunday:[{start,end}]}}}` — 30-min grid 07:00–23:30, ≥1 h ranges, no overlap.
`VisitGroup/Visit {id, visitGroupId, status, requestDateTime, alternativeVisitTimes[], transactionType, property, lead, confirmedAt/By, canceledAt/By}`.

### 8.2 State machine (C)
`pending` (Solicitada) → `confirmed` (Agendada) → reschedule (stays confirmed) | `canceled` | `dismissed`. Errors `VISIT_002..009`. Confirm / reschedule / cancel WhatsApp the lead with the visit templates (flag `visit_action_notifications`).

### 8.3 Trigger (C copy / I)
The agent offers a **pre-scheduling link/form** ("Visita solicitada via formulário da Lais") with slots from the settings; the request lands in `/visits` + a notification; a broker confirms. Switching visits off "desativa apenas o envio do link".

### 8.4 Unknown
The form page the lead sees · whether broker availability is checked (no broker calendar seen, **I: no**).

---

## 9 · WhatsApp templates and the parameter registry

`Template {id, metaTemplateName, displayName, bodyText, parameterSchema[{index, name, paramKey, component, required}], category{key}, metaStatus approved|pending|rejected, metaCategory UTILITY|MARKETING, isCustom}`; categories `administrative, campaign, billing, documentation, first_contact, reactivation, visit, other`. Create: name, category, body ≤1024, no links/emojis, ≤3 params. **C**
**Param registry** `web/templates/params`: each param has a `source` — `core` (lead.name, agency.name, lead.client_listing_id, lead.property_link, visit.created_at) · `core_ai` (bot.name) · `session` (current_user.name) · `manual` (message, visit_property, visit_scheduled_at). **C**
Unknown: Meta review latency handling; who submits to Meta (server, I).

---

## 10 · Broadcasts (Disparos em massa): remarketing and Atualização de anúncios

### 10.1 Data model (C)
`Broadcast {id, type reachout(=remarketing)|property_owner, name, status, scheduleDate, totalTargets, templateType recommendation|launch|custom, templateRef|templateCustom, propertyLink, wizardStep, responseRate, crmSentCount, retryCount, fileUrl, requestId}`; `Target {status message-sent|message-replied|enhanced, chatId}`; `SmartSuggestion {type remarketing|property_owner_update|remarketing_development, count}` with `dismiss|later|dispatched`; segments `leads-2plus-bedrooms`, `eligible-leads-3-15-days`, `eligible-leads-7-30-days`; plan `{totalUserPlan, maxPerDispatch (15 %), usedThisMonth}`.

### 10.2 State machine (C)
`pending` (Rascunho) → confirm → `confirmed` (Agendado, ≥24 h ahead, one per day `BROADCAST_005`) → `processing` → `sent` | `error`; `pending|confirmed` → DELETE → `canceled`.

### 10.3 Triggers
Manual wizard; the global upsell popup ("Dispare o Remarketing para N leads") from smart suggestions (C). A reply moves the target back into qualification and can reach the CRM (`crmSentCount`, I).

---

## 11 · Notifications as the event bus

### 11.1 Data model (C)
`NotificationEvent {id, type, isRead, createdAt, successfulOwnerDispatches, referenceID, structContent{leadName, title, description, leadNumber, leadEmail, leadClientListingID, leadConversationSummary, leadPropertyListingURL, leadTransactionType, leadVisitDates[], leadID, leadChatID, visitGroupId}}`.
14 types: `lead-visit-notification · chat-assigned · chat-queued · new-lead-message · lead-user-demanding-followup-notification · real-estate-agency-report-generated · real-estate-agency-reachout · lead-property-acquisition · property-owner · lead-enhanced-group-notification · lead-enhanced-attendant-notification · lead-enhanced-notification · google-review-notification · real-estate-agency-notification`.
A second, Pro-only stream `/web/notifications` (`chat_assigned | chat_queued | new_lead_message`) returns 404 in prod (mock only). **C**

### 11.2 Delivery (C / I)
In-app feed + websocket `notification:created` + favicon badge + optional browser notifications (flag). `successfulOwnerDispatches` and the agency toggle "Notificar lead pronto para atendimento" ⇒ events are **also sent to WhatsApp** of owners/brokers (I). Human-facing labels: Solicitação de pré-agendamento de visita · Cobrança de atendimento · Relatórios da Lais · Remarketing · Comercial (new qualified lead).

### 11.3 "Cobrança de atendimento" (C label / I mechanism)
`lead-user-demanding-followup-notification` = the lead complains nobody answered after a handoff — a classifier over lead messages raises it.

---

## 12 · Captação detection (potential property acquisition)

The agent classifies a conversation as "the person wants to list a property" → notification `lead-property-acquisition` → sidebar "Captação" (`/notifications?type=lead-property-acquisition&view=acquisition`, a filtered feed) → per policy, sent to the CRM or kept in-app (`allowEnhanceAcquisitionLeads`). Interaction type `PROPERTY_ACQUISITION`. Lead metadata `isPropertyAcquisition`. **C** (types, policy) / **I** (classifier) / **U** (prompt).
Observed script (page-map): an off-topic lead was asked "Você possui algum imóvel que gostaria de anunciar ou atualizar?" — the agent probes for acquisitions on its own. **C**

---

## 13 · Owners update (Atualização de imóveis)

Bubble page `/owners` (empty for this agency) + broadcast `type:"property_owner"` (targets from `broadcasts/property-owners`, xlsx upload, schedule) + lead type `propertyowner` + message `metadata.isPropertyOwner` + notification `property-owner`. Mechanism: Lais messages owners of advertised listings to confirm status/price; answers update the listing (`available_update` property status, I). **C** (pieces) / **U** (what is written back where).

---

## 14 · Google review requests

Dashboard `/web/agency/google-reviews/dashboard` (requests sent, new reviews, 1–5★ distribution, latest reviews). Copy: Lais sends review requests "para leads com boas conversas". Notification `google-review-notification`; chat deep link `googleReviewRequested=true`. **C** (surface) / **U** (what "good conversation" means — likely the like/feedback signal or an LLM score).

---

## 15 · Teams and distribution (Pro)

`Team {name, distributionEnabled, rouletteEnabled, lastAttendantEnabled, autoCrmEnabled, leadTypes[], administrativeCategories[]}`; `roulette{membersOrder[], currentIndex}`; `TeamMember {role gestor|attendant, active, distributionActive}`; metrics `{tprAvgMinutes (TPR = tempo de primeira resposta), activeConversations, lastAccess}`; transfer `origin ∈ {manual, roulette, crm_link, member_removed, last_attendant, redistribution}`. leadTypes `rent | buy | propertyowner` exclusive across teams; `administrative` shared. **C**
After pre-service, a team picks who distributes: **the Lais (roleta = round robin, or last attendant)** or **the CRM**. Attendants see only their own leads. Seats: paid/free/test; Pro = R$ 499,50 / 5 seats + R$ 24,50 per extra (max 100). `chats/:id/transfers` is 404 in prod (not deployed). **C**

---

## 16 · Client-history link and the access code

"Copiar link do histórico" → `/history?…` chrome-less read-only conversation + client panel. Brokers outside the platform open it with the agency's **4-digit code** (`POST /api/access-code/validate`, separate Keycloak client). **C**. Observation only, never tested: a shared 4-digit code is weak protection for personal data.

---

## 17 · Credits, plans and add-ons

- Unit = **crédito de atendimento** (one served lead-conversation); plan "Master Anual" 700/month; overage R$ 4,50; administrative add-on consumes ½ credit. `lead-summary` splits consumption into qualified / unqualified / unattended. **C**
- Add-ons: Gestão de atendimentos Pro (§15) · Campanhas inteligentes (§18) · Atendimento administrativo (2ª via de boleto, ocorrências into 16 ERPs, maintenance diagnosis; report "Resolvida pela Lais / Encaminhada ao time") · seat discount policy. **C**

---

## 18 · Meta smart campaigns (CAPI), catalog

- Onboarding `needs_oauth → awaiting_configuration → ready` (pixel, token, ad account). Qualification signals (lead qualificado, visita agendada, resposta do cliente) are sent to Meta as conversion events; campaign metrics CPL / CPQL. Flag-off for this agency. **C** / **I** (CAPI wire format)
- Catalog: listings pushed to a Meta catalog, product sets with a filter grammar, system sets "Remarketing Dinâmico Lais - Venda/Aluguel"; 404 "meta catalog is not enabled" here. **C**

---

## 19 · Credit analysis (CredAluga)

At the visit-scheduling step for rentals, with the lead's consent: `CreditAnalysis {status approved|rejected|pending, externalId, chatId, property, cpf, value, reason}`; summary per month. Flag-off here. **C**

---

## 20 · Property shelf (XML feed) and developments

Inventory = the agency's XML feed (`/web/ads/xml/status|sync`, `feeds[{url, etlStatus, lastSyncTotalAds}]`; Bubble `v2/etl/{agency}/load`); `Ad {clientListingId, link, title, address, rent/buy prices, bedrooms, bathrooms, area, iptu, parkingSpaces, description, location}`. Developments are typed separately (≤9 images, CSV/XLSX bulk import ≤150 rows). The agent answers about listings from this shelf; IPTU only if `useIptu`; full address only if "Envio de endereço completo". Reports compare lead demand with the shelf ("% Prateleira"). **C**

---

## 21 · Realtime

| Socket | Server events | Tag |
| --- | --- | --- |
| `/ws/chats` (join/leave one chat room) | `chat_updated · chat_list_item_updated · chat_list_update (reason unread|user_assigned|team_assigned|archived|chats_template|tags_updated|kanban_move|pinned) · chat_suspended · new_message · typing {side user|assistant} · message_status_updated · tag_definition_updated · feed_sync_completed` | C |
| `/ws/notifications` | `notification:created` | C |
| `/ws/properties` | `feed_sync_completed` | C |

## 22 · HTTP retry hazard

The browser HTTP client retries POST/PATCH/PUT/DELETE up to **3×** on 5xx/429 (C). Any live write could be replayed — a reason (besides policy) never to click a write in Lais. Our rebuild must use idempotency keys on every write that has side effects (Julia's `/api/channels/turns` already does, contract §5).

---

## 23 · Consolidated data model

| Entity | Key fields | Relations | Tag |
| --- | --- | --- | --- |
| Agency (REA) | id, type agency|developer, status, modules[], settings, bot{name} | 1─* everything below | C |
| User / membership | role admin|editor|member|attendant, seatType, isGestor | *─* Agency; *─* Team | C |
| Team / TeamMember | distribution flags, roulette order | 1─* members; receives Chats | C |
| Lead | status, type, transactionType, origin, crm delivery, slots profile (I) | 1─1 Chat; 1─* Visit; 1─* ForwardingDelivery | C |
| Chat | suspended, assignment, tags, pinned, feedback, window state | 1─* Message; 1─* Interaction; 1─* InternalNote(+Todo); *─* Tag; 1─* Transfer; 1─* CreditAnalysis | C |
| Interaction | type, summary, location, budget, crm status | *─1 Chat; 0..1 Property | C |
| RequiredInformation (+ selected) | label, hint, category, numeric/currency | used by UserProfile fields | C |
| UserProfile (CRM rule) | transactionType, type filter|priority, fields[] | *─* RequiredInformation | C |
| Forwarding (CRM connector) | type vista-v2, auto | Lead → CRM | C |
| ReengageConfig / ReengageRule(+Attempt) | delays, templates | Attempt → Template | C |
| VisitSettings / VisitGroup / Visit | slots, status | Visit → Lead, Property | C |
| Template / Param registry | meta status, params with source | used by Broadcast, Reengage, Visit actions, first contact | C |
| Broadcast / Target / SmartSuggestion | type, status, schedule | Target → Lead/Chat or PropertyOwner | C |
| NotificationEvent | 14 types, structContent | → Lead/Chat/VisitGroup | C |
| Ad (shelf) / Development / Feed | XML-fed listings | ← Interaction, Visit, Report | C |
| Business settings (12 sections) + behavior settings | typed KB | → compiled prompt | C |
| Report / charts | monthly demand vs shelf, funnel | derived | C |
| Subscription / Consumption / Invoice / Seat | credits | Agency | C |
| CatalogListing / ProductSet / AdAccount / Campaign | Meta | Agency | C |

---

## 24 · Open questions

### 24.1 Answerable by a read-only live pass (no conversation content)
1. `/configs_qualification` step 2 (open "Próximo" only after confirming in code it does not persist).
2. Régua attempt editor `/configs_reengage/rules/:id` (read the form, close without saving).
3. Broadcast "Novo disparo" wizard steps 1–N (open, never confirm) — fields, segments, template choice.
4. Kanban "+ Adicionar coluna" form; tag and internal-note forms; "+ Nova conversa" form; Leads filter drawer; "Ver resumo" modal *frame* (field names, not content).
5. Equipes edit drawer (distribution / roulette / autoCrm form) and "Adicionar usuário" form.
6. Developments "Adicionar empreendimento" form (Bubble definition may already hold it — check `window.app` first).
7. Notification card expanded layout (structure, with PII masked in the screenshot).
8. Whether a Lais-side "Pesquisa com clientes" (survey) setting is on and what it shows.

### 24.2 Only by reading conversations (Stage 3 — PII-blocked; needs the owner's permission rule or anonymised excerpts)
1. When an interaction opens/closes; full list of intent flags.
2. How slots are asked and inferred in practice; tone and bubble-splitting rules.
3. How captação, cobrança de atendimento and "boa conversa" (Google review) are detected.
4. Reengage message texts actually sent (fixed vs generated).
5. Handoff phrasing when a human takes over; behaviour while suspended.
6. How the agent answers from the shelf (property search behaviour, links sent).

### 24.3 Never answerable from outside (server side)
The compiled system prompt and model · the summary/extraction prompts · CRM (Vista) payload and retry policy · portal ingestion endpoints · 5-day auto-resume scheduler · credit accounting rules · CAPI event schema.
