# Domain model (inferred from bundle)

Evidence: C = code (chunk named; excerpts in routes.md / mocks.md where the field was seen), I = inferred, U = unknown. Field lists are the union of fields the frontend reads or writes; types are I unless obvious from mocks. All entities are scoped by **Agency (REA)** via `x-agency-id`.

## Entity map
```
Agency(REA) 1─* User(membership: role, seatType, isGestor)      Agency 1─* Team 1─* TeamMember(*─1 User)
Agency 1─* Lead 1─1 Chat 1─* Message;  Chat *─1 User(userAssigned) / Team(teamAssigned);  Chat *─* Tag;  Chat 1─* InternalNote 1─* Todo
Chat 1─* Interaction (property interest);  Chat/Lead 1─* VisitGroup 1─* Visit(slot);  Chat 1─* CreditAnalysis;  Chat 1─* Transfer
Agency 1─* Broadcast 1─* BroadcastTarget(→Lead/Chat | PropertyOwner)   Agency 1─* SmartSuggestion → Broadcast
Agency 1─* Property/Ad (XML feed) ─ Development;  Agency 1─* CatalogListing(adId) ; ProductSet(filter) ; AdAccount
Agency 1─* Template ; ReengageConfig(reminder|final) ; ReengageRule 1─* Attempt(→Template)
Agency 1─* RequiredInformation (essential question) ; UserProfile(CRM-send rule) 1─* Field(→RequiredInformation)
Agency 1─1 AgencySettings ; VisitSettings ; FacebookPage 1─* LeadForm ; NotificationEvent ; Subscription/Invoice/Consumption
```

## Agency / REA (`GET /web/agency/details`, `/auth/users/me`)
- REA (membership in `/auth/users/me`): `id, name, role ("admin"|"editor"|"member"|"attendant"), seatType ("paid"|"test"|"free"), isGestor` (C 4870 `e.role,e.seatType,e.isGestor`).
- Agency details: `id, status ("onboarding"|… ), agencyType ("developer"|other), modules[{moduleName}]` (e.g. `onboarding_automatizado`; administrative activation ⇒ `hasAdministrative`) (C layout; I for full list).
- Access code (4 digits) `GET /web/agency/access-code` — shared with collaborators to open `/history` links.
- **AgencySettings** (C mock + layout): `allowNotifications:bool` ("Notificar lead pronto para atendimento"), `useIptu:bool`, `allowEnhanceAcquisitionLeads:bool`, `prefixHumanMessagesWithSenderName:bool` ("Exibir nome do atendente"), `overduePaymentSlipAlertDismissedAt:ts|null` (write via `dismissOverduePaymentSlipAlert:true`), `bankslipOccurrences:bool`, `disableOnboardingTestLeadStep:bool`.

## User / seat / role
- User (`/auth/users`): `id, name, email, role ("admin"|"editor"|"member"|"attendant"), seatType ("paid"|"test"|"free"), active` (C mock). Display roles: Administrador, Editor, Membro, Membro Pro, Atendente, Atendente gestor. Seat labels: Pro, Pro (teste), Padrão. Attendant requires a paid seat (C zod).
- Seats summary `{agencyId, period{year,month}, summary{paid,free,test,maxPaidSeats}, users[]}`; availability `{contracted, occupied, extra, pricePerExtra}`.
- Premium subscription ("Gestão de atendimentos Pro") `{active, status:"active"|"pending_cancellation", subscriptionId, agencyId, seats, peakSeats, billingPeriod:"YYYY-MM", cycleStart, cycleEnd, activatedAt, cancelledAt?}`; pricing R$499,50 / 5 seats + R$24,50 per extra seat, max 100 (routes.md Part C).

## Team / TeamMember (Pro)
- Team `{id, name, membersCount, distributionEnabled, rouletteEnabled, lastAttendantEnabled, autoCrmEnabled, createdAt, leadTypes[], administrativeCategories[]}`; detail adds `members[]`, `distributionConfig{leadTypes, receivesSpecificSubcategories, classifiers[]}`, `roulette{membersOrder[userId], currentIndex}` (C mocks).
- leadTypes enum `rent` Aluguel · `buy` Compra · `administrative` Cliente Administrativo (always available, multiple teams) · `propertyowner` Proprietário — rent/buy/propertyowner exclusive across teams.
- Occurrence classifiers (administrative sub-categories, mock): 37 Boleto em atraso · 38 Segunda via de boleto · 39 Reajuste de aluguel · 40 Rescisão de contrato · 41 Manutenção do imóvel.
- TeamMember `{id, teamId, userId, userName, userEmail, role:"gestor"|"attendant", active, distributionActive, createdAt}`.
- Metrics `{userId, userName, tprAvgMinutes|null, activeConversations, lastAccess?}`.

## Lead (`/web/leads`, normalized in C 6989)
`id, chatId, name, phoneNumber, email, transactionType ("rent"|"buy"|"administrative"), origin (e.g. "GrupoZapLais"), status, phase, attendedByLais, attendanceLabel, crmStatus{deliveryLabel, deliveryAt, deliveredBy}, type ("realestate" Comercial|"administrative" Administrativo|"propertyowner" Proprietário), createdAt, enhancedAt, updatedAt, metadata, deal, propertyLink, clientListingId, conversationSummary, creditAnalysisStatus, campaign, ad, isDevelopment, development{name,link}, visits[], vatNumber (CPF), isBlocked`.
- **Lead status** (C chat pkg `W`): `created, pending (mock), message-processing, message-sent, message-sent-error, message-replied, enhanced, enhanced-error, expired`.
- **CRM state machine** (I from labels + endpoints):
```
created → message-processing → message-sent ─(lead replies)→ message-replied ─(qualified: AI/criteria/manual "Enviar ao CRM")→ enhanced
                         └→ message-sent-error                                   └→ enhanced-error (retry) ;  … → expired
UI: enhanced = "Enviado ao CRM" | enhanced-error, expired = "Erro no envio" | else "Não pronto"
```
- CRM `triggeredBy` reasons: `auto-sent, enhanced-by-client, qualified-by-client, invalid-phone-number, message-delivery-error, out-of-scope, qualified-by-lais, retry, visit-scheduled`.
- `qualificationSource`: `lais` (Sim), `manual` (Manual), `auto` (Auto-envio), `none`.
- List filters: `status` sent_to_crm|send_error|not_ready; `attended` from attendanceLais noAttendance|attendedByLais; `leadType` realestate|administrative; `origin`; `campaignIds`; `adIds`.
- Lead origins (portal codes): see realtime-and-integrations.md §6.

## Chat (`/web/chats`, @lastro/chat package)
`id, lead{id,name,email,phoneNumber,isBlocked,origin,status,transactionType,type,vatNumber,created,metadata{canBeSuspended,contacts,dateGroup,hasVisit,isPropertyAcquisition,location,originImageURL,typeTranslated}}, suspended, canBeSuspended, canSendTemplate, templateSendPolicy, archived, unread, pinned, pinnedAt, tagIds[], assignee{id}, userAssigned (userId|"none"), teamAssigned, lastActivity, creditAnalysisStatus, feedback{reaction:"like"|"dislike", comment}` (C).
- **AI vs human**: `suspended=false` "Lais atendendo" (AI answers); `suspended=true` "Atendimento manual" (AI paused) via `PATCH /web/chats/:id/suspend`. UI: AI auto-resumes after 5 days without messages; message `metadata.suspensions[{status:"suspended", requesterName}]` (C).
- **Assignment state**: unassigned (`"none"`) → user/team assigned via manual assign, roulette, last_attendant, redistribution, crm_link, member_removed (transfer `origin` enum, C mocks); queue position for `chat_queued`.
- **List scopes** `all | mine | archived`; filters `operation, suspended, leadStatus, creditAnalysisStatus, teamIds, userAssigneds, assignedToMe, archived, tags, withoutTags, pinned`; search `searchText, searchIn[]` (fields: name/phone/… — routes.md Part A).
- **WhatsApp window state** (composer): `window_open | window_closed | unauthorized | unauthorized_suspended`; free text only within 24 h of last lead message, else template; template cooldown 24 h; error `CHAT_TEMPLATE_PENDING_REPLY`.
- validate-phone result: `valid | invalid | existing | archived | blocked | error`.
- Header actions: `like, dislike, feedback, copyLink, callWhatsApp, sendToCRM, blockNumber, archive`. Block reasons: `FRAUDULENT_ACTIVITY 0, SPAM 1, HARASSMENT 2, OTHER 3` (+ reasonDetails).
- Kanban: columns (`/web/kanban/columns`), `kanban-move`; errors `KANBAN_00x`. Pinned chats ≤5 also cached in `localStorage "@lastro/chat:pinned-chats"`.

## Message (`/web/chats/:id/messages`)
`id, content, role/side ("user" lead | "assistant" Lais AI | "human" attendant), type, status, createdAt, metadata{suspensions[], leadOrigin, isReengage, isPropertyOwner, forwarded, frequentlyForwarded, location{latitude,longitude,address}}, imageLinks, audioLinks, documentLinks, videoLinks, isVideo, isAudio, isVoice, isDocument, replyTo, chunkReference, senderInfo, showSender, adImage`.
- Status: `received, created, pending, read, delivered, failed`; UI ticks `none|sent|delivered|read`.
- Media types `image, video, audio, document, file` (+ location); upload `POST /web/chats/:id/media` errors `MEDIA_001` storage not configured · 002 type not allowed · 003 too large · 004 upload failed · 005 service unavailable · 006 conversion failed.
- Paging `page, limit=25, order_by=created_at, order_desc=true` → `{chat, messages, pagination{nextPage}}`.

## Interaction (`/web/chats/:id/interactions`)
Property-interest records shown in chat details; property status `available | unavailable | unknown | available_update | awaiting_dispatch` (C). Types PROPERTY_ACQUISITION "Captação", VISIT "Visita" (C chat pkg). Exact fields: U.

## Internal note / Todo (`/web/chats/:id/internals`)
List item `{entry:{…note}, todos:[…]}` flattened to note + `todos`; audio notes processed server-side (`internals/audio/process`, I: transcription → note/todos); todo completion endpoint. Note fields: U beyond id/content (I).

## Tag (`/web/tags`)
`{id, name, color?}` (I); chat tags = `tagIds`; realtime `tag_definition_updated`.

## Visit (`/web/visits`)
- VisitGroup/Visit: `id, visitGroupId, status, requestDateTime, alternativeVisitTimes[{id, requestDateTime, status}], transactionType, property{id,…}, propertyDetails, lead{name, number, numberLink, vatNumber}, createdAt, confirmedAt, confirmedByName, confirmedByEmail, canceledAt, canceledByName, canceledByEmail, lastUpdatedAt`.
- Status machine: `pending` (Solicitada) → `confirmed` (Agendada) → (reschedule keeps confirmed) | `canceled` (Cancelada) | `dismissed` (Dispensada). Errors `VISIT_002..009`.
- VisitSettings: `{mode:"unified", general:S} | {mode:"per_operation", perOperation:{buy:S, rent:S}}`, `S={enabled, documentRequired, daysToOffer(3–31), minDaysToOffer(0–31), minHoursToOffer(0–23), schedule{monday..sunday:[{start,end}]}}` (slots 07:00–23:30, 30-min grid, ≥1 h, no overlap).

## CreditAnalysis (CredAluga)
`{status:"approved"|"rejected"|"pending", externalId (CredAluga simulation id), chatId, property, cpf, value, reason, date}`; summary `{totalAnalyses, approved, rejected, percentage, totalVisits}`.

## Property / Ad / Development
- Ad (integrated property, `/web/properties/ads`): `clientListingId, title, link, imageUrl, city, type, operation (rent|buy|both), price,…` (I from catalog mocks). Property types: apartment Apartamento, house Casa, commercial Comercial, land Terreno, rural Rural, garage Garagem, warehouse Galpão, office Escritório, store Loja (C 9654). Feed sync status `/web/ads/xml/status`.
- Development: `id, name, description, avgPrice, minPrice, maxPrice, clientListingId, link, city, state(UF), neighborhood, street, location{lat,lon}, images[] (≤9), status:"active"|"inactive"`; bulk import `{fileName, processedCount, totalCount, status:"pending"|"processing"|"completed"|"failed"}` (CSV/XLSX ≤2 MB, 150 rows). Errors `DEVELOPMENT_001..009`, `AGENCY_006`.
- PropertyOwner (broadcast target): `{id, name, phoneNumber}`.

## Meta catalog
- CatalogListing `{adId, clientListingId, title, link, imageUrl, city, type, operation, price, active, status:"in_catalog"|"out_of_catalog"|"error", syncStatus:"pending"|"submitted"|"synced"|"error", lastSyncedAt, deletedAt?, errors[{severity:"error"|"warning", message}]}`.
- ProductSet ("subset") `{id, adAccountId, metaProductSetId|null, name, color|null, filter, remarketingSubsetType?:"buy"|"rent", createdAt, updatedAt}`; filter grammar in mocks.md §4. Errors `META_CATALOG_002..023`.

## Smart campaign (Meta CAPI)
- OnboardingState `{state:"needs_oauth"|"awaiting_configuration"|"ready", agencyName, hasPixel, hasToken, hasAdAccount}`; AdAccount `{id, adAccountId:"act_…", name}`.
- Campaign `{id, name, capi:bool, status:"active"|"paused"|"in_review"|"rejected"|"ended" (Ativa, Pausada, Em revisão, Recusada, Encerrada), spend, leads, qualifiedLeads, qualifiedPct, cpl, cpql}`; summary `{totalLeads, qualifiedLeads, avgCpl, avgCpql, totalSpend}`; campaign lead `{id,name,email,phone,date,qualificationSource,status,chatId}`.

## Broadcast (Disparo em massa)
- `{id, type:"reachout"(=remarketing)|"property_owner", name, description, status, scheduleDate, totalTargets, templateType:"recommendation"|"launch"|"custom", templateRef?, templateCustom?, templateText, propertyLink, wizardStep, createdAt, updatedAt, responseRate?, crmSentCount?, statusDetails, targetsFrom, retryCount, lastRetryAt, fileUrl, requestId, targetsWithMessage}`.
- Status machine: `pending` (Rascunho) →confirm→ `confirmed` (Agendado) → `processing` (Processando) → `sent` (Enviado) | `error` (Erro); `confirmed|pending` →DELETE→ `canceled` (Cancelado). Must be scheduled ≥24 h ahead; one broadcast per day (`BROADCAST_005`); plan limits `{totalUserPlan, maxPerDispatch}`.
- Target `{id, name, phoneNumber, email, status:"sent"|"pending", chatId, createdAt}`.
- SmartSuggestion `{id, type:"remarketing"|"property_owner_update"|"remarketing_development", count}`; cooldown actions `dismiss|later|dispatched`.
- Error codes `BROADCAST_004..013+` (routes.md Part B).

## Template (WhatsApp, `/web/templates`)
`{id, displayName|metaTemplateName, bodyText, parameterSchema[{index,name}], category{id,key,name,displayName}, metaStatus:"approved"|"pending"|"rejected", isCustom}`; categories keys `administrative, campaign, billing, documentation, other, first_contact, reactivation, visit`; params `[{key, displayName}]`; create `{name, categoryId, bodyText (≤1024, no links/emojis, ≤3 params), parameters[{index, paramKey}]}`.

## Reengagement
- ReengageConfig `{enabled, reengageType:"reminder"|"final", delayMinutes}` (reminder 5–60 min any hour; final 1–24 h, 08–20 h; reminder < final).
- ReengageRule ("Régua") `{id, realEstateAgencyId, name, buy, rent, enabled, attempts[]}`; Attempt `{id, attemptIndex, delayValue, delayUnit("days"…), templateId (slug lead_reengage…), enabled}` (≤3).

## Qualification (CRM-send rules)
- RequiredInformation ("Pergunta essencial") `{id, information, isNumeric, isCurrency}` (edited in Bubble).
- UserProfile `{id, name, identifier, transactionType:"buy"|"rent"|"both", type:"filter"|"priority", active, fields[{fieldName, operator:"filled"|"greater-than-or-equal"|"less-than-or-equal"|"between", value}]}`.

## Notification
- NotificationEvent (`/web/notification-events`): `{id, type, isRead, createdAt, successfulOwnerDispatches, referenceID, structContent{leadName,title,description,createdAtFormatted,leadNumber,leadEmail,leadClientListingID,leadVatNumber,leadConversationSummary,leadPropertyListingURL,leadTransactionType,leadVisitDates[],leadID,leadChatID,visitGroupId}}`; types (14): lead-visit-notification, chat-assigned, chat-queued, new-lead-message, lead-user-demanding-followup-notification, real-estate-agency-report-generated, real-estate-agency-reachout, lead-property-acquisition, property-owner, lead-enhanced-group-notification, lead-enhanced-attendant-notification, lead-enhanced-notification, google-review-notification, real-estate-agency-notification.
- Pro Notification (`/web/notifications`, mock): `{id, type:"chat_assigned"|"chat_queued"|"new_lead_message", payload, read, createdAt}` — distinct concept/endpoint from NotificationEvent (C both exist).
- Transfer `{id, fromUserId?, fromUserName?, toUserId?, toUserName?, toTeamId?, toTeamName?, origin:"manual"|"roulette"|"crm_link"|"member_removed"(|"last_attendant"|"redistribution" in notifications), reason?, createdAt}`.

## Finance
- Subscription (plan) `{status:"active"|"notice-period", plan{type:"cpa"|…, name, displayName, overagePolicy:"bump"|fixed}, validFrom, validTo}`.
- Consumption `{planType:"annual"|"annual-per-exceeding"|monthly…, planCredits, usedCredits, totalCredits}` (credits = atendimentos).
- Invoice `{id, status:draft|approved|billed|paid|overdue|cancelled|no-charge, billingPeriod, totalAmount, paidAt, cancelledAt, items[{name, amount, type:"overage"…}], bankSlips[{status:pending|issued|paid|overdue|cancelled, dueDate, digitableLine, downloadUrl}]}`.
- BillingAccount `{cnpj, reas[{name}]}`; FinancialContact `{id, email}`; AddOnBillingAccount `{id, status:"active", quantity, observation, addOn{name}}`.

## Reports
- `/web/report?date=yyyy-MM-01` → `metadata.report{rentSection, buySection}` each with `topNeighborhoods, topHotProperties, topPropertyTypes` (routes.md Part C §7).
- Charts: plan-consumption `{percentageOfConsumption, projectedConsumption, totalUserPlan,…}`, alerts, lead-summary, leads-by-channel, lead-status-by-channel (enhanced/message-replied/enhanced-error), leads-per-hour, leads-per-weekday, leads-last-six-months; administrative report volume (conversations/bankslips/occurrences), occurrence-ranking, conversation-resolution (resolved "Resolvida pela Lais" / forwarded "Encaminhada ao time").
- Google reviews dashboard: fields in routes.md Part C §7.

## Onboarding
- Flow progress `{steps[{stepSlug, completed}], totalSteps, completedSteps}`; flows/steps in flags-permissions.md §6. TestUser `{id, name, phoneNumber}`. Checklist channels `{channels[…]}`, save `{leadOriginIDs[]}`.
- User onboarding profile `{phone, workAreas[], workAreasOther, jobRoles[] (realtor, team_manager, owner_partner, comms_marketing, operation_end), needsOnboarding}`.
