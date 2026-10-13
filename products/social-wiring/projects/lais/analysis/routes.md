# Routes — Casa da Lais (casa.lais.ai), static map

58 app routes in the Next route manifest (C main-app/6084); 50 have a page chunk in our capture (`js/app/<route>/page-*.js`). Detail per route lives in three sections below (Part A chat/leads/visits, Part B configs/broadcasts/campaigns/billing, Part C home/users/reports/misc + layout shell). Evidence: C = code (chunk + excerpt), I = inferred, U = unknown.

## Route index
Kind: **N** native React · **B** Bubble iframe (legado.lais.ai, see bubble-embeds.md) · **N|B** flag-switched · **E** embeddable (rendered inside Bubble drawers) · **R** redirect/thin.

| route | kind | gate (nav guard / page logic) | observed redirect to "/" — cause | detail |
|---|---|---|---|---|
| `/` | N | home:read | | C §1 |
| `/chats` | N (@lastro/chat pkg) | chat:view; flags credit-analysis-enabled, message-status-checks, reply-message-chat-frontend, chat-filter-without-tags, visit_action_notifications; onboarding flow chat-control | | A §2 |
| `/history` | B (`history`, anonymous) / access-code | new-access-code-page | | A §3 |
| `/leads` | N\|B (`leads-view`) | lead:read | | A §4 |
| `/leads-v3` | N | | | A §4 |
| `/visits` | N | visit:read | | A §5 |
| `/credit-analysis` | N | flag credit-analysis-enabled + credit-analysis:read | **flag off** | A §7 |
| `/notifications` | N | notification:read (menu: attendants via notification:menu) | | C §3 |
| `/captacao` | U (no page code captured; nav uses `/notifications?type=lead-property-acquisition&view=acquisition`) | property-capture:read | | C §8 |
| `/owners` | B (`owners`) | property:read; blocked for agencyType developer | | bubble-embeds |
| `/developments` | N\|B (`new-development-page-front`) | development:read | | C §6 |
| `/properties` | N | flag property-page-front + integrated-property:read | **flag off** | C §8 |
| `/catalogs` | N | flag meta-catalog-front | **flag off** | B /catalogs |
| `/relatorio-v2` | N\|B (`new-relatorio-view`) | report-neighborhood:read; blocked for developer | | C §7 |
| `/relatorio-v3` | N | | | C §7 |
| `/performance` | B (`performance`) | report-performance:read; **allowedAgencyTypes developer** | **agency is not a developer** | C §8 |
| `/avaliacoes` | N | report-google-review:read | | C §7 |
| `/atendimento-administrativo` | N | requiresAdministrative (administrative add-on active) | **no administrative module** | C §7 |
| `/smart-campaigns` | N | flag smart-campaigns-front + smart-campaign:read; page also needs Meta connection/pixel | **flag off / not connected** | B /smart-campaigns |
| `/smart-campaigns/remarketing` | N | + flag smart-campaigns-remarketing-front + onboarding-state hasPixel | **flag off / no pixel** | B |
| `/broadcasts` | N | flag broadcasts-enabled (page guard replaces "/") | | B /broadcasts |
| `/configs` | N | lais-settings:read | | B /configs |
| `/configs_behavior` | B | | | B (Bubble) |
| `/configs_my_business` | B | | | B |
| `/configs_whatsapp_profile` | B | | | B |
| `/configs_property_info` | B | | | B |
| `/configs_qualification` | E (native, embedded in Bubble) | | | B |
| `/configs_visits`, `/configs_visits_embed` | N / E | | | B, A §6 |
| `/configs_display_attendant_name` | E | admin/editor manage | | B |
| `/configs_reengage` | N | flag reengage-rules (rules section) | | B |
| `/configs_templates` | N | | | B |
| `/configs_meta_integration` | N | flag meta-integration-front (inverted per Part B: true ⇒ redirect to /configs) | | B |
| `/acessos` | N | requiresTeamViewPage (team:view-page) | | C §2 |
| `/user-management` | B (`user_management`) | | | C §2 |
| `/add-ons`, `/add-ons/pro`, `/add-ons/smart-campaigns`, `/add-ons/administrative` | N | add-on:read | | B /add-ons |
| `/financeiro` | N | billing:read or Lastro staff | | B /financeiro |
| `/plans` | B (`plans`) | | | B |
| `/perfil` | N | page:all-roles | | C §4 |
| `/checklist` | N | page:all-roles; flag `checklist`=true (exempt) ⇒ "/"; flows complete & outside display window ⇒ "/" | **agency exempt or onboarding flows done** | C §5 |
| `/whats-new` | N | flag whats-new-page + whats-new:read | | C §8 |
| `/trainings` | B (`trainings`, fullscreen) | onboarding-platform class | | C §8 |
| `/trainings_page` | N ("Guia da Lais", Vimeo) | lais-guide:read | | C §8 |
| `/platform` | B (`platform`, fullscreen) | forced when agency.status=onboarding ∧ module onboarding_automatizado; otherwise ⇒ "/" | | C §8 |
| `/onboarding`, `/onboarding/sucesso` | N (no chunk) | profile.needsOnboarding | | C §4 |
| `/creation-user-test` | N (no chunk) | forced for new agencies without test lead | | C §5 |
| `/access-code`, `/debug`, `/facebook/callback`, `/pacotes-adicionais/gestao-de-atendimentos-pro`, `/platform-meeting-schedule`, `/unauthorized`, `/auth/signin`, `/auth/error` | no chunk captured | | | C §0 |

Global: a denied route redirects to the first allowed nav entry, else "/" (C layout `(0,z.Mw)(I,C)&&r.replace((0,z.ui)(C))`); HTTP 402 premium_module_required ⇒ `/add-ons/pro`; attendants may be bounced to atendimento.casa.lais.ai (flag attendant-app-migration=false).

---

# Part A — chats, history, leads, visits, credit analysis

Evidence: **C** = seen in code (chunk + excerpt), **I** = inferred, **U** = unknown.
Chunk short names: `CHAT` = `3b4451b3-c014840964a13726.js` (the `@lastro/chat` package — logs prefixed `[@lastro/chat]`), `V` = `9994-2a782b21be023876.js` (visit/chat-detail helpers), `P` = `9654-683df5d447313a6d.js` (property/chat drawer + permissions), `LS` = `6989-48293521f8f0240f.js` (leads service), `LV3` = `9934-22dc5ff232ccd16b.js` (LeadsV3 UI), `VS` = `1647-a3c836255cc3b66e.js` (visit settings), `AUD` = `9013-c982e375dffccbab.js`, `QK` = `4450-fd473c7799b02419.js` (query-key factory module 59365).

---

## 0. Two HTTP stacks (matters for safety)

| Stack | Where | Retries | Notes |
|---|---|---|---|
| Host app client `GO`/class `v` (module 95424/35138) | everything outside CHAT | **retries 3× on 5xx/429 incl. POST/PATCH** (`DEFAULT_RETRY_CONFIG={retries:3,delay:1e3,backoff:2}`) — C `5138-*` | adds `Authorization: Bearer`, `x-agency-id`; 402 `premium_module_required` → `window.location.replace("/add-ons/pro")` |
| CHAT own fetch `G` + class `J` | CHAT | **no retry**, except `t8()` wrapper (3 retries on 502/503/504/TypeError) used ONLY for **video** `uploadMedia` — C CHAT `"video"===a?await t8(()=>t9.uploadMedia(...` | 401 → `onAuthExpired()`; timeout default 10 s, media 120 s, video 340 s |

---

## 1. React-query key factory (module 59365, C `QK`) — full dump

```
auth: all, permissions.{all, chat(agencyId), teamsAll, teams(agencyId)}, profile(), checkEmail(email,?), agencySearch.{all, byQuery(q)}
agency: all, details(), settings(), accessCode()
checklist: all, channelStatus()
testUsers: all, list()
chat: all, chatById(id), agency(id), historicoAccess(a,b), creditAnalyses(id), agencySearch(params)
user: all, profile(id), preferences(), assignableUsers()
assignment: all
visit: all, config(), visits(), single(id), detail(id), calendar(params)
property: all, search(q[,agency]), ads(params), feedSyncStatus()
lead: all, leads(), list(p), detail(id)
notification: all, notifications(p)
facebook: all, pages(), forms(pageId|'all'), formsLocal(), formsMeta(), formQuestions(formId,pageId)
development: all, list(p), bulkImports(), bulkImportStatus(id)
flow: all, onboardingProgress(slug)
premium: teams.{all,list,detail,metrics,distribution,roulette,leadTypes,occurrences}, transfers.{all,history}, notifications.{all,list}, subscription.{all,status}, seats.{all,summary,availability}, users.{all,list}
broadcast: all, list, detail, targets, segments, propertyOwners, plan, availableDates
audience: all, profileFields(), userProfiles()
requiredInformation: all, selected()
creditAnalysis: all, summary(p), chart(p), list(p)
whatsNew: ["whatsNew"], list()
banners: all, home()
template: all, available(), categories(), params()
visitSettings: all, settings()
reengagement: all, configs(), delayOptions(type), templates(), rules(), rule(id)
```

CHAT keeps its **own** factory `L` (C CHAT `var L={chat:{all:["chat"],chats:()=>...`):
`chat.{all, chats(), pinnedChats(), chatById(id), search(), validatePhone(n), newConversationSearch(q), senderFooter(), messages(id), messagesInfinite(id) = ["chat","messages",id,"infinite"], status(id), creditAnalyses(id), interactions(id), visitsAll(), visits(id), feedback(id), notes(id), template.{availableAll, available(chatId|null), categories, params, draft(chatId,templateId), newConversationDraft(templateId)}}`, `tag.{all, byRea(id)}`, `kanban.{all, columns()}`, `user.{all, assignableUsers(managedByMe)}`, `team.{all, list(managedByMe)}`. Leads use a third factory `$` (module 96634: `all, list(), campaigns(), origins(), export(jobId)`) — C `LS`.

---

## 2. Route `/chats`

- Page wrapper: `app/chats/page-96a486208254a018.js`; renders CHAT module `s.Xw` with props `{agencyId, authToken, bffUrl:"https://bff.lastro.services/api/v1", currentUserId, featureFlags, permissions, modules, socketUrl:"wss://eventhub.lastro.services/ws/chats", userRole, onAuthExpired, onExternalAction, onTrack, refreshChatListToken, ...}` — C chats page `socketUrl:"".concat(_,"/ws/chats")`.
- Redirect: no `accessToken` or no `selectedReaId` → `router.replace("/")` — C `Z||G&&ti||Q.replace("/")`.
- `?view=kanban` is stripped from URL on mount (C). `?chatId=` triggers "assume conversation" flow (below). `?phoneNumber=` selects chat by phone.
- **Feature flags passed** (C chats page): `credit-analysis-enabled`, `message-status-checks`, `reply-message-chat-frontend`, `chat-filter-without-tags`, `visit_action_notifications` (82361.P). History page passes `featureFlags:{}`.
- **Gate**: nav `pagePermission:"chat:view"`.
- **Onboarding flow** `chat-control` (C `N="chat-control",P=["open-chat","stop-chat","send-message","reactive-chat"]`): steps completed via `POST …/flows/chat-control/steps/:step/complete` (`e5({flowSlug:N,stepSlug:e})`) when the user opens a chat, pauses Lais, sends a message, resumes Lais — only while LD flags loaded ∧ flag `checklist`=false ∧ flow incomplete; highlights test-user chat (`userTestPhone` = last test user's `whatsappNumber`). Banner copy (C): "Pausar a Lais", "Envie sua mensagem normalmente pelo campo de texto.", "Quando terminar, você pode reativar a Lais para retomar o atendimento automático."
- **Assume via link** (`?chatId=`, requires `canSelfAssign`): GET chat, if unassigned → `POST /web/chats/:id/user-assignment {userId, onlyIfUnassigned:true, origin:"crm_link"}` (C chats page `e0({chatId:eI,userId:eU,onlyIfUnassigned:!0,origin:"crm_link"})` → 7531 `assignUser`). **WRITE**. Errors: "Não foi possível assumir a conversa / Ela já está sendo atendida por outro atendente."; 400 → "Conversa não encontrada".
- Layout-level: `/chats?chatId=X` not accessible → `router.replace("/history?chatid=X")` (C layout).

### 2.1 CHAT module UI (all C in `CHAT` unless noted)
- **List scopes/tabs** `iK={ALL:"all",MINE:"mine",ARCHIVED:"archived"}` labels "Todas" / "Minhas" / "Arquivadas" (`showAllTab` hidden when !canViewAll — I).
- **View toggle**: "Ver como lista" / "Ver como kanban" (module flag `kanbanView`; default modules `{sidebar,chatPane,detailsPanel,composer,chatHeaderActions,kanbanView:true,readOnly:false}`).
- **Pinned**: max 5 ("Só é possível fixar até 5 conversas."), list "Conversas fixadas", localStorage `@lastro/chat:pinned-chats`; `PATCH /web/chats/:id/pin {pinned}`.
- **Row menu**: "Fixar conversa", "Marcar como lido"/"Marcar como não lido" (`PATCH /web/chats/:id {unread}`), label "Atendimento manual" badge on suspended chats; "Sem nome" fallback.
- **Search** (bar): `GET /web/chats/agency/search?searchText&searchIn&limit&page&operation&suspended&leadStatus&creditAnalysisStatus&assignedToMe&archived`. `searchIn` values seen: `["chats"]`, `["messages"]`, `["messages","chats"]`. Result tabs "contacts" / "messages". Response `{data:{chats:[{data,meta:{total,page,limit,nextPage}}], messages:[{data,meta}]}}` (C `chats:s.data.chats?.[0]||{data:[],meta:{total:0,page:1,limit:15}}`).
- **Filters drawer** ("Filter chats", button "Filtrar"; error "Não foi possível aplicar o filtro. Exibindo dados anteriores."):

| category (PT) | name → query param | options |
|---|---|---|
| Operação (I: label) | `operation` | Aluguel=`rent`, Compra=`buy`, Administração=`administrative`, Atualização=`propertyowner` |
| Status CRM | `leadStatus` | Enviado ao CRM=`sent_to_crm`, Não pronto=`not_ready` |
| Status de atendimento | `suspended` | Lais atendendo=`false`, Atendimento manual=`true` |
| Análise de crédito (flag `credit-analysis-enabled`) | `creditAnalysisStatus` | Aprovada=`approved`, Reprovada=`rejected` |
| Responsável (requiresPremium) | `responsibleUserId` → `userAssigneds` (CSV; `"none"`→`""`) | "Sem responsável"=`none` + `GET /auth/users?skipInternal=true[&managedByMe=true]` |
| Equipe (requiresPremium) | `teamId` → `teamIds` (CSV) | `GET /web/teams[?managedByMe=true]` |
| Etiquetas | `tags` (CSV) + `withoutTags=true` (flag `chat-filter-without-tags`, option "Sem etiqueta") | `GET /web/tags` |

  List call: `GET /web/chats/agency?limit=15&page&...&assignedToMe&archived` → `{data:{chats[], pagination:{total,nextPage}}}` (C `er.getChats`). `leadStatus` client-side mapping (C `e1`): `sent_to_crm` ⇐ lead.status ∈ {`enhanced`}; `not_ready` ⇐ {`created`,`expired`,`message-sent`,`message-replied`,`message-processing`,`enhanced-error`,`message-sent-error`}. Operation→lead.type mapping: administrative→`administrative`, propertyowner→`propertyowner`, rent/buy→`realestate` + transactionType.

- **Chat header actions** `sl` (C): `like`("Gostei do atendimento"), `dislike`("Não gostei do atendimento"), `feedback`("Deixar feedback"), `copyLink`("Copiar link do histórico"), `callWhatsApp`("Chamar no WhatsApp"), `sendToCRM`("Enviar ao CRM"), `blockNumber`("Bloquear número"), `archive`("Arquivar conversa"). Analytics events `like_chat`, `dislike_chat`, `access_feedback`, `block_number`, `archive_chat`.
  - like/dislike → `POST /web/chats/:id/feedback {reaction:"like"|"dislike"}`; feedback dialog "Avaliação do atendimento" → `{comment}` zod `max(300,"O comentário deve ter no máximo 300 caracteres")`, required when no prior comment (`min(1,"Por favor, insira seu comentário")`, not whitespace-only). Note text: "As avaliações de conversa são usadas para melhoria contínua da Lais, mas não geram chamado…". Feedback read via `GET /web/chats/:id?withFeedback=true` (`feedback.reaction`, `feedback.comment`). **WRITE**.
  - **Enviar ao CRM** → confirm dialog → `PATCH /web/leads/:leadId/enhance/force` (no body) — toast "Aguarde o processamento, ele pode durar alguns instantes". Disabled when `lead.status==="enhanced"` ("Lead já enviado ao CRM") or `lead.type ∉ {realestate, propertyowner}` ("Não é possível enviar lead ao CRM"). **WRITE + external side effect (pushes lead to customer CRM)**. Mock confirms `{leadId, enhanced:true, sentToCRM:true}` (9707).
  - **Bloquear número** dialog: zod `sp` = `{reason: number ≠ -1 ("Selecione a razão"), reasonDetails: string max 500 ("Os detalhes devem ter no máximo 500 caracteres") optional}`; reasons `sd={FRAUDULENT_ACTIVITY:0,SPAM:1,HARASSMENT:2,OTHER:3}` labels "Atividade fraudulenta","Spam","Assédio","Outro". → `POST /web/users/block {phoneNumber, reason, reasonDetails?}`; unblock → `DELETE /web/users/unblock?phoneNumber=`. **WRITE**.
  - **Arquivar** dialog "Arquivar conversa?" — body: 'Fique tranquilo! Você ainda pode consultá-la na aba "Arquivadas". Sempre que uma nova mensagem chegar, ela será desarquivada automaticamente.' plus "A Lais irá assumir o atendimento nesta conversa" (I: archiving hands chat back to AI). → `PATCH /web/chats/:id {archived:true|false}`. **SEND-class (I: changes who answers)**.
- **AI ↔ human toggle** (`data-testid="attendance-toggle"`), labels `st.LAIS_ATTENDING="Lais atendendo"` (suspended=false) / `st.USER_ATTENDING="Atendimento manual"` (suspended=true): `PATCH /web/chats/:id/suspend {suspended:boolean}` — C `x.mutate({chatId:e,suspended:!a})` → `er.suspendChat`. **SEND-class**: pauses/resumes the AI agent on that chat. Tooltips: "Para pausar a Lais, é necessário ser Editor ou Administrador." / "Para reativar…"; highlights "Clique aqui para pausar a Lais nesta conversa" / "Clique para a Lais retomar a conversa automatica com este lead". Analytics `reactivate_lais` / `confirm_chat_intervention`. Exit dialog "Sair com Lais pausada?" — "Lembre-se de reativar a Lais para este cliente quando finalizar o contato. A Lais será reativada automaticamente após 5 dias sem novas mensagens nesta conversa." (C) → business rule: auto-resume after 5 days idle (I: server-side).
  - Also: sending a human message on a non-suspended chat flips local state to suspended (C `n&&(tM(X,e,!0),R("button_clicked",{action:"auto_chat_intervention"…` ) → I: server auto-pauses Lais on human message.
- **Composer**: placeholder "Digite uma mensagem"; empty-state "Envie uma mensagem diretamente ao lead"; "Gravar áudio"; "Adicionar anexo"; "Selecionar emoji"; reply ("Responder mensagem", "Cancelar resposta"; flag `reply-message-chat-frontend`).
  - Text send: `POST /web/chats/:id/messages/human {content, replyToMessageId?, replyToChunkReference?}` — **SEND (WhatsApp)**.
  - Media send: `POST /web/chats/:id/media` multipart `file` (+`voice=true` for voice notes) → `{data:{url,fileName,size,contentType}}` then `POST …/messages/human {content?, replyToMessageId?, replyToChunkReference?, media:{type,url,fileName,size,contentType}}` — **SEND**. Limits `Y`: image ≤5 MB (jpeg/png/gif/webp), document ≤100 MB (pdf), video ≤100 MB (mp4/quicktime/webm/x-msvideo), audio types ogg/webm/mp4/mpeg. Media error codes `MEDIA_001..006` → "Armazenamento não configurado…","Tipo de arquivo não permitido.","Arquivo muito grande.","Falha no upload…","Serviço indisponível…","Não foi possível converter o vídeo…".
  - **24 h window / permission states** `sW`: `unauthorized` (input disabled, pause tooltip), `unauthorized_suspended`, `window_open` (enabled), `window_closed` (disabled, "Só é possível mandar mensagens livres em conversas durante às 24 horas que sucedem a última mensagem do cliente. Para retomar o contato, envie um modelo de mensagem."). Chat fields driving it: `suspended`, `canBeSuspended` (I = inside 24 h window), `canSendTemplate`, `templateSendPolicy`.
  - **Template policy** `aK(canSendTemplate, templateSendPolicy)`: policy fields `{allowed, maxAttempts, sentCount, allowedCategories[], nextAllowedAt, reason:"cooldown"|…, message}` → states `allowed`/`cooldown`/`exhausted`. Tooltips "Só é possível mandar uma mensagem de template. Aguarde o contato responder para mandar outra.", "Aguarde 24 horas da última mensagem de template para enviar a próxima."
- **Send template drawer** ("Enviar modelo de mensagem", 2 steps; search "Buscar modelos"; empty "Nenhum template disponível / Não encontramos modelos aprovados para envio de mensagens."): `GET /web/templates/available?chatId=` → pick → `GET /web/chats/:id/messages/template/draft?templateId=` (pre-fill params; READ-I) → `POST /web/chats/:id/messages/human/template {templateId, parameters:{…}}` — **SEND**. Success "Mensagem enviada com sucesso".
- **Create template modal** ("Novo modelo de mensagem"; requires `canCreateTemplate`, else "Para criar modelos de mensagem, é necessário ser Editor ou Administrador."): fields `name` ("Nome do modelo", "Nome é obrigatório"), `categoryId` ("Selecione uma categoria", from `GET /web/templates/categories` → `data.categories`), `bodyText` ("Conteúdo da mensagem"; ≤3 parameters from `GET /web/templates/params` → `data.params[{key,displayName}]`). → `POST /web/templates {name, categoryId, bodyText, parameters:[{index, paramKey}]}` — **WRITE (submits to Meta review)**: "Modelo de mensagem em análise — O seu modelo precisa ser aprovado pela Meta para ser utilizado…".
- **New conversation drawer** ("Nova conversa"/"Iniciar nova conversa", 3 steps; requires editor/admin: "Para iniciar nova conversa, é necessário ser Editor ou Administrador."):
  1. "Nome da pessoa" (`personName`, "Informe o nome da pessoa"), "Número do contato" (`contactNumber`) → `GET /web/chats/agency/validate-phone?phoneNumber=` → status ∈ `valid` ("Número válido"), `invalid`, `existing` ("Conversa existente"), `archived` ("Este contato possui uma conversa arquivada."), `blocked` ("Este contato já está em atendimento por outro membro da equipe."), `error`. Button "Ir para a conversa".
  2. template choice (`GET /web/chats/new/messages/template/draft?templateId=` for prefill).
  3. params → `POST /web/chats/new/messages/human/template {templateId, parameters, name, phoneNumber}` — **SEND (opens a new WhatsApp conversation)**. 409 `CHAT_TEMPLATE_PENDING_REPLY` → "Esta conversa já possui um modelo de mensagem aguardando a resposta do contato…".
- **Assignment** ("Atribuir responsável"): `POST /web/chats/:id/user-assignment {userId, reason?, userName?}` / `POST /web/chats/:id/team-assignment {teamId, reason?}`; clearing both = userId `""` + teamId `""`. Toasts "Responsável atribuído com sucesso", "Equipe atribuída com sucesso", "Atribuições removidas com sucesso". **WRITE (routes chat to human; premium)**. Premium transfer variants (7531): `POST /web/chats/:id/transfer {toUserId?, toTeamId?, reason?}`, `GET /web/chats/:id/transfers`, `POST /web/chats/:id/self-assign`.
- **Details panel** sections: "Resumo do chat", "Interações", "Visitas solicitadas", "Notas internas", "Etiquetas", credit analysis. "Primeiro contato hoje às HH:mm"/"em …".
  - **Interactions** `GET /web/chats/:id/interactions` → normalized (C `rf`): `{id, startedAt=createdAt, source=origin, type ∈ administrative|realestate|propertyowner (labels "Administração","Comercial","Atualização"), typeTranslated=metadata.typeTranslated, status, crmStatus{label,color}, property{id=clientListingId|development name, type ad|development, location, budget, link, status}, description=summary, occurrence{type=administrativeOccurence.name, protocol=administrativeOccurence.id}, forwardingDelivery{status, triggeredBy, enhancedAt}, isPotentialCapture=metadata.isPropertyAcquisition, hasBoleto=!!bankslipOccurence, hasVisit, originImageURL}`. Property status labels: `available` "Disponível"(green), `unavailable` "Indisponível"(red), `unknown` "Sem resposta"(gray), `available_update` "Disponível com alteração"(yellow), `awaiting_dispatch` "Agendado"(yellow). Empty: "Nenhuma interação encontrada".
  - **CRM forwarding `triggeredBy`** (`et`) labels: `auto-sent` "Enviado automaticamente em …", `enhanced-by-client` / `qualified-by-client` "Enviado manualmente em …", `invalid-phone-number` "Enviado por telefone inválido em …", `message-delivery-error` "Enviado por falha na entrega da mensagem inicial …", `out-of-scope` "Enviado por estar fora do escopo de atendimento em …", `qualified-by-lais` "Qualificado pela Lais em …", `visit-scheduled` "Visita solicitada em …", `retry` (no label).
  - **Notes** `GET /web/chats/:id/internals` → `[{entry:{…}, todos:[…]}]` flattened; only `type==="annotation"` shown. Create manual: `POST /web/chats/:id/internals {type:"annotation", source:"manual", content, todos:[{text,position}]}` (≤4 todos, "+ Adicionar tarefa"). AI voice note ("Gravar com IA"/"Gravar nota com IA", auto-stop 120 s): `POST /web/chats/:id/internals/audio/process` multipart `file=audio.webm` → `{transcription, summary, todos[]}` then `POST …/internals {type:"annotation", source:"ai_generated", content:"", aiSummary, transcription, todos}`. Delete `DELETE …/internals/:noteId` ("Tem certeza que deseja excluir esta anotação? Esta ação não pode ser desfeita."), todo `PATCH …/internals/:entryId/todos/:todoId/complete` (status→`completed`). Timeline line "{authorName} criou uma nota interna". All **WRITE**.
  - **Tags**: `GET /web/tags` (`[{id,name,color}]`), `POST /web/tags {name,color}` ("Criar etiqueta"), `PATCH /web/tags/:id`, `DELETE /web/tags/:id`, chat tags `GET|PUT /web/chats/:id/tags {tagIds:[]}`. Copy "Adicionar etiqueta", "Editar etiquetas", "Buscar etiquetas", "Nenhuma etiqueta corresponde à busca.".
  - **Visits in chat** `GET /web/chats/:id/visits` → `data.visits[]` (needs `visit:read`; link to `/visits?visitGroupId=` or `?clientListingId=`).
  - **Credit analyses** `GET /web/chats/:id/credit-analyses` → badges "Crédito aprovado"/"Crédito reprovado", link "Ver simulação na CredAluga" → `https://app.credaluga.com.br/requests/simulations/details/:externalId` (C `V`).
- **Kanban** (`GET /web/kanban/columns`; add `POST {kind:"tag",tagID} | {kind:"smart",config:{hasTags:false}}` = "Sem etiqueta" column; remove `DELETE /:id`; reorder `PATCH /reorder {columnIDs:[]}`; move chat `POST /web/chats/:id/kanban-move {from,to}` with targets `{kind:"default"}|{kind:"archived"}|{kind:"smart",columnID}|{kind:"tag",tagID}`). Column = `{id, kind:"tag"|"smart", tagID?, config?, label?, position}`. Errors `KANBAN_001..012` (e.g. 006 "Limite de 50 colunas atingido.", 002 "Esta etiqueta já é uma coluna do kanban", 009 "Esta conversa não pode mais ser movida.", 010 "Status do chat divergente."). Moving to `archived` = archive (**SEND-class I**). "Você realmente deseja remover a coluna … do kanban? A etiqueta continuará existindo…".
- Timeline system lines (from message `metadata`): suspensions → "{requesterName|Agente} assumiu a conversa" / "Lais assumiu a conversa"; `leadOrigin` → "Cliente chegou via {origin}"; `isReengage` → "Lead não respondeu mais. Lais reativou a conversa"; `isPropertyOwner` → "Disparo de mensagem para proprietário".
- Message status ticks (flag `message-status-checks`): "Mensagem enviada"/"Mensagem entregue"/"Mensagem lida"; failure "Erro no envio da mensagem" + "Tentar novamente"/"Cancelar envio".

### 2.2 Chat-scoped permission keys (C `P` QI hook)
`chat:send-message`→canSendMessage · `chat:send-template` · `chat:create-template` · `chat:assign-label` · `chat:create-label` · `chat:create-note` · `chat:delete-note` · `chat:archive` · `chat:block` · `chat:assign` · `chat:pause-lais`∨`chat:suspend`→canPauseLais · `chat:feedback` · `chat:send-to-crm` · `chat:view-all` · `visit:read`→canViewVisits · `chat:view-team` · `chat:create-team` · `chat:edit-team` · `chat:delete-team` · `chat:add-remove-member` · `chat:transfer-to-user` · `chat:transfer-to-team` · `chat:self-assign`∨`chat:assign`→canSelfAssign · `chat:filter-by-responsible` · `chat:filter-by-team` · `subscription:purchase` · `subscription:cancel`. Others seen: `chat:view`, `chat:open-lead`, `chat:open-property`. Source `GET /web/permissions` → `data.permissions[key]={allowed,reason,blockBehavior}`; `blockBehavior` ∈ `hide|readonly|(tooltip)`; reasons `premium_module_required` ("A Gestão de atendimentos Pro precisa estar ativa"), `premium_seat_required`, `role_restricted`, `team_restricted`.

---

## 3. Route `/history`
- Bubble iframe `bubblePath:"history"`, `layout:"fullscreen"`, `allowAnonymous:true`, params `{chatid, agency}` (C history page). Title "Histórico".
- If logged-in user is assigned to the chat → redirected to `/chats?phoneNumber=`/`?chatId=` (C). 400 → "Conversa não encontrada".
- Flag `new-access-code-page` → native access-code gate for anonymous viewers:
  - `POST /api/access-code/validate {code, chatId}` (Next route, same-origin) — 4-digit code ("Dígito n de 4"), 3 attempts tracked in localStorage `access-code:attempts:<chatId>` then `blockedUntil` ("Você excedeu o limite de tentativas", "Duas tentativas restantes", "Uma tentativa restante", "Código inválido"). Dialog "Não sabe o código?" → "Entrar com minha conta".
  - `GET /api/access-code/session` → `{data:{accessToken, agencyId, chatId}}` (401 = none) — historico session token then injected (`preferHistoricoSession`). `DELETE /api/access-code/session` = logout. Env `KEYCLOAK_HISTORICO_*` (C 5138) → I: server exchanges code for a scoped Keycloak token.
  - Code itself comes from `GET /web/agency/access-code` ("Código de acesso — Compartilhe com colaboradores para que acessem links da Lais.").
- Read-only chat modules `{chatPane, detailsPanel, chatHeaderActions, readOnly:true}` (C).

---

## 4. Route `/leads` and `/leads-v3`
- `/leads`: if LD loaded ∧ flag **`leads-view`** (module 40835) → native `LeadsV3` (chunk `LV3`); else Bubble iframe `bubblePath:"leads"`, params whitelist `names, numbers, transactionType, ads, origin, createdAt, status, leadID, campaigns, ads_ids, chatID, email, leadType, conversation, suggestionId`; Bubble messages `LEADS_BANNER_NEXT_STEP|RESET|HIDE` drive the `reachout-leads` onboarding banner (steps `select-lead` → `send-reachout`). Gate `lead:read`.
- `/leads-v3`: thin route that renders `LeadsV3` (module 79934) directly (C leads-v3 page loads 6989/9934).
- **LeadsV3 page** title "Leads", subtitle "Tenha a visão completa e organizada dos leads que entraram em contato com a Lais." Table columns `["Lead","Contato","Operação","Canal","CRM"]` + select checkbox; empty "Nenhum lead encontrado"; page sizes `[10,25,50]` ("itens por página"); test lead badge "TESTE".
- **Filters** ("Filtro de leads"): date range "Data do primeiro contato" (`startDate`,`endDate` yyyy-MM-dd, default = current month); Operação `transactionType` (Aluguel `rent`, Compra `buy`, Administração `administrative` → also sets `leadType` realestate/administrative); Atendimento da Lais `attendanceLais` (Sem atendimento `noAttendance`, Atendido pela Lais `attendedByLais` → `attended=true|false`); Status CRM `status` (Enviado ao CRM `sent_to_crm`, Erro no envio `send_error`, Não pronto `not_ready`); multi-value search chips: Nome `name`, E-mail `email`, Telefone `number`, Imóvel `clientListingId` ("Código do imóvel"), Link da conversa `chatId`; Canal `origin` (`GET /web/leads/origins`); campanhas `campaignIds` (`GET /web/leads/campaigns`); Meta ads `adIds` ("Selecionar anúncios"); `creditAnalysisStatus`.
- **List** `GET /web/leads/?page&limit&view&phase&distinctByPhone&suggestionId&startDate&endDate&name&email&number&clientListingId&transactionType&status&origin&leadType&attended&campaignIds&adIds&creditAnalysisStatus&chatId&order_by&order_desc` (CSV for arrays). Raw lead → normalized (C `LS` `d()`): `id, chatId, name, phoneNumber, email, transactionType, origin, status, phase, attendedByLais, attendanceLabel, crmStatus{deliveryLabel,deliveryAt,deliveredBy}, type(realestate|administrative|propertyowner), createdAt, enhancedAt, updatedAt, metadata, deal, propertyLink, clientListingId, conversationSummary, creditAnalysisStatus, campaign, ad, isDevelopment, development{name,link}, visits[{id,visitGroupId,requestDateTime,property,status,alternativeVisitTimes[],confirmedAt,confirmedByName,confirmedByEmail,createdAt}]`. leadType labels `realestate` "Comercial", `administrative` "Administrativo", `propertyowner` "Proprietário".
- **Actions**:
  - Single "Enviar ao CRM": `POST /web/leads/:id/enhance` (parseAs response; 202 ACCEPTED → `{accepted:true}` else body lead) — **WRITE + CRM side effect**.
  - Batch "Enviar N lead(s) ao CRM?": `POST /web/leads/batch-enhance {leadIds:[]} | {selectAll:true, filter:{…}, excludedLeadIds:[]}` → `{summary:{enhanced,skipped,failed}}` toast "X enviado(s), Y já enviado(s), Z com falha." Max 60 per batch (C `"…".concat(60," leads para enviar.")`). **WRITE**.
  - Export "Baixar selecionados": `POST /web/leads/export?<filters> {selection}` → `jobId`; poll `GET /web/leads/export/:jobId` every 2 s (`status` `done|failed`, `error`); `GET /web/leads/export/:jobId/download` (blob `leads-dd-MM-yyyy.xlsx`). Limits: 5 000 (selected) / 50 000 (filter-match), error code `LEAD_027` with `details.matched` ("Seleção muito grande…"). **WRITE (job)**.
  - "Remarketing" from selection → stores selection then `router.push("/broadcasts")` (C `e.push(u.$W)`).
  - Test lead swap ("Lead teste trocado com sucesso.") via `POST /web/test-users {name, phoneNumber}`; "Copiar link do histórico".
  - Analytics: `trackForceEnhance`, `trackMultipleForceEnhance`, `trackRequestReachout`.

---

## 5. Route `/visits`
- Gate `visit:read`. Title (82361) "Visitas" / "Gerencie solicitações de visita e defina horários de forma simples."
- Calendar (react-big-calendar) views month/week/day; labels "Hoje","Próximo","Anterior","Mês","Semana","Dia","Data","Hora","Visita"; empty "Não há visitas neste período."; selects "Todos os tipos"/Compra `buy`/Aluguel `rent`; input "Filtrar por imóvel"; gear "Configurações" → `/configs_visits?type=visit&agency=`.
- Filter drawer "Filtro de visitas": Operações `transactionType` (rent/buy), Status da visita `status` (Solicitada `pending`, Agendada `confirmed`, Cancelada `canceled`), Busca `clientListingId` ("ID do imóvel"). URL params `transactionType,status,clientListingId,visitGroupId`.
- Not-enabled empty state (page_view `visit_not_enabled`): "Ative as solicitações de visita — Com elas, a Lais agenda visitas no pré-atendimento e cada pedido chega aqui." button "Configurar visitas".
- Data: `GET /web/visits?view&date&transactionType&clientListingIds&status&leadIds` (`date` = yyyy-MM or yyyy-MM-dd per view), `GET /web/visits/config`, `GET /web/visits/:visitGroupId` (detail incl. `propertyDetails`, `lastUpdatedAt`). Service also defines `createVisit` (POST), `updateVisit` (PATCH), `deleteVisit` (DELETE) — **no call sites found** (I: dead code).
- **Visit statuses**: `pending` "Pendente"/"Solicitada", `confirmed` "Agendada", `canceled` "Cancelada", `dismissed` "Dispensada" (C `V` `h()`). Transaction label buy "Compra" else "Locação".
- **Visit detail dialog** ("Visita"): time options = `requestDateTime` + `alternativeVisitTimes[]` (each `{id, requestDateTime, status}`) + "Outra data" custom (`dd/MM/yyyy, HH:mm`, must be future, not duplicate: "Esta data e horário já foram sugeridos nesta visita"). Associate property: "Buscar por código ou link" → `GET /web/properties/ads?search=` → `PUT /web/visits/:visitGroupId {propertyId, propertyType}` ("Imóvel associado com sucesso"). Visit object fields: `id, visitGroupId, status, requestDateTime, alternativeVisitTimes, transactionType, property{id,…}, propertyDetails, lead{name, number, numberLink, vatNumber(CPF)}, createdAt, confirmedAt/By{Name,Email}, canceledAt/By{Name,Email}`.
- **Actions** (`Hy={SCHEDULE,RESCHEDULE,CANCEL}`):
  - Agendar: `POST /web/visits/:visitGroupId/confirm {visitId | alternativeDateTime, confirmedByName, confirmedByEmail}`.
  - Alterar agendamento (when confirmed): with flag `visit_action_notifications` → `PUT /web/visits/:visitGroupId {visitId|alternativeDateTime, confirmedByName, confirmedByEmail}`.
  - Cancelar solicitação: `POST /web/visits/:visitGroupId/cancel {}`.
  - With flag `visit_action_notifications` the confirm dialogs state the effect: SCHEDULE "A Lais assume a conversa e envia ao lead a confirmação com data e horário pelo WhatsApp…", RESCHEDULE "…envia ao lead a nova data e o novo horário pelo WhatsApp…", CANCEL "A Lais assume a conversa e avisa o lead que a visita não vai acontecer… Não é possível desfazer." → **all three are SEND-class**. Without the flag: success dialog "Calendário atualizado — avise o lead…" with "Avisar no WhatsApp" (opens `wa.me` link client-side, text "Sua visita foi confirmada para o dia …").
  - Requires operator identity (session name+email) else "Não foi possível identificar seu usuário…".
  - Errors `VISIT_002..009` (C `V`): 002 "Esta visita não está mais disponível.", 003 "O horário escolhido não pertence a esta visita.", 004 "Esta visita não tem mais um horário confirmado para alterar.", 005 "Esta visita já foi cancelada.", 006 "Escolha uma data e um horário no futuro.", 009 "Escolha um horário diferente do atual.".
- Visit cards also show credit analysis + "Ver simulação na CredAluga", "Ver conversa", "Chamar no WhatsApp", "Copiar telefone", "Copiar CPF".

## 6. Visit settings schema (`VS`, used by `/configs_visits`, `/configs_visits_embed`, chat drawer)
- `GET|PUT /web/agency/settings/visits`. Payload (C `VS` `p()`): `{mode:"unified", general:S}` or `{mode:"per_operation", perOperation:{buy:S, rent:S}}` where `S = {enabled, documentRequired, daysToOffer, minDaysToOffer, minHoursToOffer, schedule:{monday..sunday:[{start:"HH:mm",end:"HH:mm"}]}}`. Default (85376): unified, enabled, documentRequired false, daysToOffer 7, minDaysToOffer 1, minHoursToOffer 2, Mon–Fri 09:00–18:00.
- Labels: "Pré-agendamento de visita" — "Configure a Lais para coletar horários de interesse para visita."; "Diferenciar configuração para leads de compra e aluguel"; enabled "Permita que a Lais aceite solicitações de agendamento de visita para seus imóveis…"; "Solicitação de CPF obrigatória?" ("Exiba o campo de CPF no formulário…"); period "Período disponível para solicitação de visitas" (min/max "Tempo mínimo/máximo para solicitar um horário", units Dias/Horas); "Horários disponíveis" ("A Lais oferecerá opções… 09:00, 09:30, 10:00…"); per-op suffixes buy "envia a solicitação de visita para leads interessados em comprar.", rent "…em alugar.", general "…para seus leads.".
- Validation: minDays 0–31, minHours 0–23, maxDays 3–31 (max ≥ min); slot grid 07:00–23:30 step 30 min; ranges ≥ 1 h, no overlap ("Os horários não podem se sobrepor.", "Horário fora da grade permitida.", "O horário deve ter pelo menos 1 hora."); save blocked messages "Ative o Pré-agendamento de visitas para compra ou aluguel", "Selecione ao menos um horário disponível", etc. Equivalent buy/rent config → confirm dialog "Está tudo certo?".
- Embedded mode posts to parent Bubble (C `VS` 18522): `{type:"SAVE"|"SAVE_ERROR"|"EXIT_DRAWER"|"RELOAD_WITH_PARAMS", source:"casa-da-lais"}` (relevant to bubble-embeds.md).

## 7. Route `/credit-analysis`
- Gate: flag `credit-analysis-enabled` + `credit-analysis:read`. Title "Análise de crédito" — "Acompanhe as análises de crédito dos seus leads."; tab "Visão geral"; "Recarregar dados".
- `GET /web/credit-analysis/summary?month&year` (cards "Análises realizadas", "Análises aprovadas", "Análises reprovadas", "Visitas no período"; fields `totalAnalyses, approved, rejected, percentage, totalVisits`), `GET /web/credit-analysis/chart?month&year` (`data.chartData`, "Análises por dia"; series Aprovadas/Reprovadas), `GET /web/credit-analysis?month&year&page&limit&status` (table "Análises de crédito": Imóvel, CPF, Valor, Status, Motivo, Data, Ações → "Ver simulação" (CredAluga `externalId`), "Ver conversa" (`chatId`)). Status labels `approved` "Aprovado", `rejected` "Reprovado", `pending` "Pendente". All READ.

## 8. Audiences / required information (`AUD`; UI lives in /configs_qualification — fork B)
- `GET /web/audiences/required-informations` (selected), `GET /web/audiences/user-profiles`, `POST /web/audiences/user-profiles`, `PATCH /web/audiences/user-profiles/:id` (soft-delete via `{active:false}`; save = upsert loop with rollback). Operation enum `{BUY:"buy",RENT:"rent",BOTH:"both"}`. Errors "Falha ao salvar configuração de qualificação", "Falha ao remover critério de qualificação".

---

## 9. Domain enums (CHAT, full values)
| Const | Values |
|---|---|
| `U` | `"none"` (= unassigned sentinel) |
| `F` suspension status | `SUSPENDED:"suspended"` |
| `W` lead status | `created, enhanced, enhanced-error, expired, message-processing, message-replied, message-sent, message-sent-error` (+ `pending` seen in mocks) |
| `K` lead type | `administrative, realestate, propertyowner` |
| `_` transaction | `rent, buy` |
| `$` sender | `assistant, human` |
| `ee` message status | `received, created, pending, read, delivered, failed` |
| status tick enum | `none, sent, delivered, read` |
| `et` CRM triggeredBy | `auto-sent, enhanced-by-client, qualified-by-client, invalid-phone-number, message-delivery-error, out-of-scope, qualified-by-lais, retry, visit-scheduled` |
| `e2` CRM filter | `sent_to_crm, not_ready` (leads also `send_error`) |
| `te` chat_updated `triggeredBy` | `unread, user_assigned, team_assigned, archived, chats_template, tags_updated, kanban_move, pinned` |
| `tt` typing side | `user, assistant`; `aY` = `user, human, assistant` |
| `iK` scopes | `all, mine, archived` |
| `sl` header actions | `like, dislike, feedback, copyLink, callWhatsApp, sendToCRM, blockNumber, archive` |
| `sc` | `pending, confirmed` |
| `sd` block reasons | `FRAUDULENT_ACTIVITY:0, SPAM:1, HARASSMENT:2, OTHER:3` |
| `sW` composer | `unauthorized, unauthorized_suspended, window_open, window_closed` |
| media types | `image, video, audio, document` (+ `file`), labels "Imagem","Vídeo","Mensagem de voz","Documento", "Localização" |
| validate-phone | `valid, invalid, existing, archived, blocked, error` |
| interaction property status | `available, unavailable, unknown, available_update, awaiting_dispatch` |
| `MEDIA_00x`, `KANBAN_00x`, `VISIT_00x`, `LEAD_027`, `CHAT_TEMPLATE_PENDING_REPLY` | error codes (see above) |

Chat object fields seen: `id, lead{id,name,email,phoneNumber,isBlocked,origin,status,transactionType,type,vatNumber,created,metadata{canBeSuspended,contacts,dateGroup,hasVisit,isPropertyAcquisition,location,originImageURL,typeTranslated,…}}, suspended, canBeSuspended, canSendTemplate, templateSendPolicy, archived, unread, pinned, pinnedAt, tagIds, assignee{id}, userAssigned, teamAssigned, lastActivity, creditAnalysisStatus, feedback{reaction,comment}`. Message fields: `id, content, role/side, type, status, createdAt, metadata{suspensions[{status,requesterName}], leadOrigin, isReengage, isPropertyOwner, forwarded, frequentlyForwarded, location{latitude,longitude,address}}, imageLinks, audioLinks, documentLinks, videoLinks, isVideo, isAudio, isVoice, isDocument, replyTo, chunkReference, senderInfo, showSender, adImage`. Messages paging: `GET /web/chats/:id/messages?page&limit=25&order_by=created_at&order_desc=true` → `{data:{chat:{…}, messages, pagination:{nextPage}}}`.

## 10. Realtime used by these routes (C CHAT)
- `wss://eventhub.lastro.services/ws/chats?token=<JWT>&agencyId=` ; client sends `{event:"join"|"leave", data:{chatId}}`; receives `chat_updated` (`triggeredBy` above), `chat_list_item_updated`, `chat_list_update`, `chat_suspended`, `new_message`, `feed_sync_completed`, `tag_definition_updated`, `typing` (`{chatId, side}`), `message_status_updated`. Reconnect resyncs caches.

---

## 11. Endpoints NOT in tools/methods.txt (found here)
| Method | Path | Caller | Class |
|---|---|---|---|
| POST | `/web/chats/:id/media` (multipart `file`, `voice`) | CHAT `t9.uploadMedia` via raw `G()` | WRITE (precursor to SEND) |
| POST | `/api/access-code/validate` `{code, chatId}` | history page `f.validateCode` | WRITE (session) |
| GET | `/api/access-code/session` | history page | READ |
| DELETE | `/api/access-code/session` | history page | WRITE |
| POST | `/web/developments/bulk` (multipart) | developments page via `GO` (fork C scope) | WRITE |

## 12. Safety summary for this scope
- **SEND**: `POST /web/chats/:id/messages/human`, `…/messages/human/template`, `/web/chats/new/messages/human/template`, `PATCH /web/chats/:id/suspend` (AI on/off), `PATCH /web/chats/:id {archived}` (I), `POST /web/chats/:id/kanban-move` to archived (I), visit `confirm` / `PUT visits/:id` / `cancel` (with `visit_action_notifications`, Lais messages the lead), user/team assignment & transfer & self-assign (human takeover routing).
- **WRITE + external**: `PATCH /web/leads/:id/enhance/force`, `POST /web/leads/:id/enhance`, `POST /web/leads/batch-enhance` (push to customer CRM); `POST /web/templates` (Meta review).
- **WRITE**: feedback, block/unblock, notes/todos/audio, tags, kanban columns, pin, unread, export jobs, audiences, visit settings, test users.
- **READ (safe to fetch)**: chats list/search/byId/withFeedback, messages, interactions, internals, visits (chat + properties/visits + config + detail), credit-analyses, tags, kanban columns, templates available/categories/params, `/auth/users?skipInternal=true`, `/web/teams`, `/web/leads/` + origins + campaigns, credit-analysis summary/chart/list, `/web/agency/settings/visits`, `/web/audiences/*` GETs, `/web/permissions`. `…/template/draft` GETs are I-READ (render preview) but unverified.
- **U**: whether `GET /web/chats/:id` marks the chat as read server-side (no evidence either way; client sends explicit `unread` PATCH).

---

# Part B — configs, broadcasts, catalog, smart campaigns, add-ons, billing

Evidence tags: **C** = seen in code (chunk + excerpt), **I** = inferred, **U** = unknown.
Chunk paths are relative to `js/`. Strings are decoded from `\xNN` escapes.

Cross-cutting facts used below:
- `canManage` = the user has the role `admin` or `editor`, or is a Lastro internal user. **C** app/configs/page-*: `let r=["admin","editor"];... canManage:t(r)||!0===a`
- **Bridge/embed mode:** several native config pages also run *inside* the Bubble legacy app (in an iframe). `isBridge` comes from hook `(0,l.s)()`. In that mode a page doesn't navigate; it posts to its parent Bubble window (origin `https://legado.lais.ai`) with module 18522. **C** 1647-*: `save:()=>n({type:"SAVE",source:"casa-da-lais"}),saveError:e=>n({type:"SAVE_ERROR",...error:e}),exit:()=>n({type:"EXIT_DRAWER",...}),reloadWithParams:e=>n({type:"RELOAD_WITH_PARAMS",...params:e})`. This is the reverse direction of BubbleIframePage, and it belongs in bubble-embeds.md.
- **Standard error→PT-BR map (module 81661, used by every page):** 400 "Requisição inválida…", 401 "Sua sessão expirou…", 403 "Você não tem permissão…", 404 "Recurso não encontrado.", 409 "Conflito de dados…", 422 "Dados inválidos…", 429 "Muitas tentativas…", 500 "Erro interno do servidor…", 502/503/504 "Serviço temporariamente indisponível…". **C**

---

## /configs — "Minha Lais"
**C** app/configs/page-3a0420037e31350a.js
- Header: title "Minha Lais", subtitle "Configure sua Lais com informações personalizadas."
- Nav entry: pagePermission `lais-settings:read` (sidebar config, chunk 7533).
- **Top grid of image cards (`C`):**

| Card title | Description | Target | Gate |
|---|---|---|---|
| Meu negócio | Funcionamento da imobiliária, documentações exigidas e garantias | Bubble `/configs_my_business` (iframe page) | none |
| Perfil do WhatsApp | Nome da Lais, foto de perfil e descrição | Bubble `/configs_whatsapp_profile` | none |
| Modelos de mensagem | Crie e gerencie modelos de mensagem para o WhatsApp. | `/configs_templates` (native) | shown only if `canManage` |
| Integrações Meta | Receba leads de campanhas Meta | `/configs_meta_integration` (native) | shown only when LD flag **`meta-integration-front` is FALSE** (`e.title===w.META_INTEGRATION?!x:...`) |

- **Section "Comportamento da Lais" (list cards):**

| Card | Description | Target (C) |
|---|---|---|
| Pré-agendamento de visita | Sugerir datas e horários para agendamento de visitas | `/configs_visits` (native page, module 1647) |
| Qualificação e Envio ao CRM | O que a Lais deve perguntar antes de enviar leads ao CRM? | **`/configs_behavior`** (Bubble iframe), built by module 28068 `let t="/configs_behavior"`. The native `/configs_qualification` is opened *from inside* Bubble (I) |
| Reengajamento automático | Como a Lais deve agir com leads que pararam de responder? | `/configs_reengage` (native) |
| Endereço e IPTU dos imóveis | Como a Lais deve agir quando perguntada sobre endereço completo e IPTU? | Bubble `/configs_property_info` |

- The cards support a "NOVO" badge (`isNew`), but no card sets `isNew` in this build. **C**
- Analytics: `button_clicked` with page `configs` and actions `config_my_business`, `config_whatsapp_profile`, `config_meta_integration`, `config_templates`, `config_visits`, `config_qualification`, `config_reengage`, `config_property_info`, plus `learn_more` on page `edit_qualification_forwarding_1`. **C** 9013-* module 29115

## Bubble-wrapped config routes (no native fields in this bundle)
**C** route chunks: each renders `BubbleIframePage({bubblePath, params, title})`. Each forwards only the query params `type` and `tab`.

| Route | bubblePath | title |
|---|---|---|
| /configs_behavior | configs_behavior | Comportamento da Lais |
| /configs_my_business | configs_my_business | Meu negócio |
| /configs_whatsapp_profile | configs_whatsapp_profile | Perfil do WhatsApp |
| /configs_property_info | configs_property_info | Endereço e IPTU dos imóveis |
| /plans | plans | Planos |

**U:** the fields for behavior, my-business, WhatsApp profile and property-info (IPTU/address) live in the Bubble app at legado.lais.ai. They are **not** in this bundle, so a live Bubble capture is required.
**C:** `/configs_qualification` links back to Bubble for "Perguntas essenciais": `V.push("/configs_behavior?type=questions")`, or, embedded, `reloadWithParams({type:"questions"})`. So the "essential questions" (required informations) editor is the Bubble page `configs_behavior?type=questions`.

---

## /configs_qualification — "Envio de leads qualificados" (native; the CRM-send rule builder)
**C** app/configs_qualification/page-67cc9d5093922265.js + 9013-* (audiences service).
- **Data sources (C):**
  - `GET /web/audiences/required-informations` → `[{id, information (label), isNumeric, isCurrency, ...}]` (queryKey `requiredInformation.selected()`). One hidden id is excluded: `11e5f905-67a8-45d2-a9aa-3d45497b8fa1` (`c=new Set([...])`, chunk 9013).
  - `GET /web/audiences/user-profiles` → profiles `[{id, active, transactionType, type, fields:[{fieldName, operator, value, requiredInformation?}], ...}]` (queryKey `audience.userProfiles()`).
  - `GET /web/visits/config` → `{enabled}`. When visits are enabled, a locked, mandatory criterion "Visita" ("Pré-agendada via formulário da Lais") is shown.
- **Write path (C):**
  - Create: `POST /web/audiences/user-profiles` with body `{fields:[{fieldName, operator, value}], identifier:"", name:"<Compra|Aluguel|Compra e aluguel> · <crit> e <crit>", transactionType:"buy"|"rent"|"both", type:"filter"|"priority"}`.
  - Update: `PATCH /web/audiences/user-profiles/:id` with `{...data, active:true}`.
  - Deactivate: `PATCH .../:id {active:false}`.
  - If any create fails, every profile created so far is rolled back (`for(let t of[...e].reverse())...updateUserProfile(t,{active:!1})`).
  - **WRITE class:** this changes when the AI sends leads to the CRM.
- **Operators (C)**, mapping each UI condition to its payload:

| UI condition value | Label | Dropdown label | Payload |
|---|---|---|---|
| selecionar | Selecionar condição | Selecionar condição | `operator:"filled", value:{}` |
| a_partir_de | A partir de | Valores a partir de | `operator:"greater-than-or-equal", value:{value:N}` |
| ate | Até | Valores até | `operator:"less-than-or-equal", value:{value:N}` |
| de_ate | De - Até | Valores dentro de intervalo | `operator:"between", value:{min,max}` (min/max auto-swapped) |
| independente | Independentemente do valor | Independentemente do valor | `operator:"filled", value:{}` |

  - Non-numeric criteria are always `filled` and shown as "informado".
  - Currency criteria show an "R$" prefix.
  - Numbers are parsed pt-BR style: `replace(/\./g,"").replace(",",".")`.
  - Invalid-value tooltip: "Insira um valor válido". **C**
- **Model (C):**
  - Groups are OR'ed together: "A Lais qualifica e envia ao CRM os leads que atenderem algum dos critérios:", with "OU" separators.
  - Criteria inside a group are AND'ed ("E" badge, "Combinar com outro critério").
  - Base group "Comportamento" (`id:"comportamento"`, description "Qualificado via inteligência da Lais", `type:"filter"`, not deletable) = the AI's own judgment. Other groups are `type:"priority"`.
  - Toggle "Configurações diferentes para compra e aluguel" (tabs `compra`/`aluguel`) → separate profiles with transactionType `buy`/`rent`, else `both`.
- **Copy (C):**
  - Step 1 title "Envio de leads qualificados", subtitle "Defina os critérios para que a Lais envie o lead ao CRM.", section "Critérios de envio".
  - Buttons: "Adicionar critério de envio", "Ir para Perguntas essenciais", "Saiba mais" (suporte.lais.ai article 13778963).
  - Nudges: "Faça a Lais filtrar mais." / "Faça a Lais filtrar menos."
  - Step 2 "Resumo": "Leads de **compra**/**aluguel** serão enviados quando atenderem a pelo menos um dos seguintes critérios:".
  - Buttons "Próximo", "Salvar"/"Salvando...".
  - Exit dialog "Sair da edição?" / "As modificações feitas não serão salvas".
- **Save blockers (C):**
  - "Defina ao menos um critério no cartão Comportamento antes de salvar. Sem ele, um lead que não atender a nenhum critério de envio é dispensado em vez de ser avaliado pela inteligência da Lais." (reasons `filter-emptied`, `no-filter-for-priorities`)
  - "Nada para salvar: nenhum critério configurado…"
  - "Nenhuma alteração para salvar."
  - Success toast: "Configuração salva com sucesso."
- When an essential question disappears, its criteria are ignored: "A pergunta "X" saiu de Perguntas essenciais, então este grupo inteiro é ignorado: nenhum lead atende a ele." **C**
- queryKey invalidated on save: `audience.all`. **C**

## /configs_visits and /configs_visits_embed — "Pré-agendamento de visita" (native, module 1647)
**C** 1647-a3c836255cc3b66e.js
- **Endpoints:**
  - `GET /web/agency/settings/visits`
  - `PUT /web/agency/settings/visits` (full document; WRITE)
  - queryKey `visitSettings.settings()`
- **Schema (C, default A4 in 9707 mock):**
  - `{mode:"unified"|"per_operation", general:{...}, perOperation:{buy:{...}, rent:{...}}}`
  - Each operation config: `{enabled, documentRequired, daysToOffer, minDaysToOffer, minHoursToOffer, schedule:{monday..sunday:[{start:"HH:MM",end:"HH:MM"}]}}`
  - Default: unified, enabled, documentRequired false, daysToOffer 7, minDaysToOffer 1, minHoursToOffer 2, Mon–Fri 09:00–18:00.
- **Limits (C, module 41173):**
  - Time grid 420…1410 minutes (07:00–23:30), 30-minute steps.
  - `minDays 0..31`, `minHours 0..23`, `maxDays 3..31`.
  - Rule: `min(days*24+hours) <= maxDays*24`.
- **Labels (C):**
  - title "Pré-agendamento de visita"; description "Configure a Lais para coletar horários de interesse para visita."
  - perOperation "Diferenciar configuração para leads de compra e aluguel"
  - enabledDescription "Permita que a Lais aceite solicitações de agendamento de visita para seus imóveis…"
  - documentLabel "Solicitação de CPF obrigatória?" ("Exiba o campo de CPF no formulário…")
  - period "Período disponível para solicitação de visitas" (minTime / maxTime, Dias / Horas)
  - schedule "Horários disponíveis" (tooltip: slots 09:00, 09:30…)
  - "Adicionar horário" / "Remover horário"
  - Tabs Compra / Aluguel
  - Day names Segunda…Domingo
- **Validations (C):** "Os horários não podem se sobrepor.", "Horário fora da grade permitida.", "O horário deve ter pelo menos 1 hora."
- **Save blockers (C):** "Ative o Pré-agendamento de visitas para compra ou aluguel", "Corrija os horários inválidos", "Revise o período…", "Selecione ao menos um horário disponível".
- Equivalence dialog: "Está tudo certo?" — shown when buy and rent are configured identically; on confirm, saves as unified. **C**
- Summary card text: "{buy|rent|general}: envia a solicitação de visita para leads interessados em comprar/alugar / seus leads."
- Routing: `/configs_visits?type=visit` auto-opens the edit drawer. `/configs_visits_embed?context=platform` uses the platform layout; otherwise the drawer layout. In bridge mode it emits SAVE/EXIT_DRAWER. **C** `path:"/configs_visits_embed",param:{context:"context"},context:{platform:"platform"}`

## /configs_display_attendant_name — "Exibir nome do atendente"
**C** app/configs_display_attendant_name/page-*
- Reads `GET /web/agency/settings` and writes `POST /web/agency/settings {prefixHumanMessagesWithSenderName:boolean}`, with an optimistic update (queryKey `agency.settings()`).
- **This is a SEND-adjacent setting:** it prefixes human messages sent to leads with the attendant's name.
- UI:
  - Switch "Exibir nome do atendente na mensagem?" — "Possibilita que a pessoa atendida veja o nome do atendente que mandou mensagem para ela."
  - Badge Ativo / Inativo.
  - Preview block "Pré-visualização da mensagem" with the sample "Olá! Tudo bem? Muito prazer, serei responsável pelo seu atendimento, vamos dar andamento?"
- Gate: `canManage`, else "Você não tem permissão para acessar esta configuração." Bridge-aware (SAVE / EXIT_DRAWER).
- Other agency settings keys (from mock, chunk 9707): `allowNotifications, useIptu, allowEnhanceAcquisitionLeads, prefixHumanMessagesWithSenderName, overduePaymentSlipAlertDismissedAt, bankslipOccurrences, disableOnboardingTestLeadStep`. **C**

## /configs_reengage — "Reengajamento automático"
**C** app/configs_reengage/page-* and 2470-*
- **Tabs (C):** `?tab=default` "Reengajamento padrão"; `?tab=reengage-rules` "Réguas de reengajamento" (badge "NOVO"). The rules tab is shown only when LD flag **`reengage-rules`** is true (default false).
- **Standard reengage — two configs (C):**

| Kind | `?reengage=` | reengageType | Copy |
|---|---|---|---|
| minutes | minutes | reminder | "Reengajamento em minutos" — retries right after the lead stops answering; works at any hour |
| hours | hours | final | "Reengajamento em horas" — retries after hours; only 08h–20h; also reaches leads that never answered |

  - Endpoints: `GET /web/reengage/configs` → `[{enabled, reengageType, delayMinutes}]`; `GET /web/reengage/configs/delay-minutes?reengageType=` → `[{label, value}]`; `PUT /web/reengage/configs {enabled, reengageType, delayMinutes}` (**WRITE; this governs automatic AI re-sends**).
  - Mock options: reminder 5/10/15/30/45/60 min; final 1/2/4/8/12/24 h.
  - Cross-constraint: the minutes delay must be less than the hours delay (`disabled: a.value>=e.delayMinutes`). **C**
  - Copy: "Sempre que o lead responder, o fluxo de reengajamento recomeça. Leads que encerram o atendimento não são contatados."; active card "A Lais envia uma mensagem *{delayLabel}* depois que o lead para de responder."
- **Rules ("réguas") (C):**
  - `GET/POST /web/reengage/rules`
  - `GET/PATCH/DELETE /web/reengage/rules/:id`
  - `POST .../:id/activate|deactivate`
  - `POST .../:id/attempts`
  - `PATCH|DELETE .../:id/attempts/:attemptId`
  - `GET /web/reengage/rules/templates`
  - Rule shape `{id, realEstateAgencyId, name, buy, rent, enabled, attempts[]}`. Attempt shape (mock) `{id, attemptIndex, delayValue, delayUnit("days"…), templateId, enabled}`.
  - Default name "Régua N" (auto-increment). Max 3 attempts ("Limite de 3 tentativas de contato automatizadas."). The list helper text, however, says "até 5 tentativas … compra ou até 3 para locação" — the two disagree (C, I).
  - Execution window: "Das 8h às 20h".
  - Operation labels: Compra / Aluguel / Aluguel e compra.
  - Active-rule save warning: "As novas configurações valem só para os leads que entrarem na régua depois de salvar."
  - Deleting the last attempt of an active rule is blocked.
  - Templates (mock):
    - `lead_reengage` "Mensagem ancorada no imóvel de interesse"
    - `lead_reengage_short` "Mensagem retomando atendimento"
    - `lead_reengage_long` "Mensagem de encerramento"
    - `lead_reengage_brief_message` "Mensagem breve"
  - **U:** the attempt editor (delay unit picker, template select) is not in the downloaded chunks; it is likely a lazy chunk.
- queryKeys: `reengagement.configs()`, `.delayOptions(type)`, `.rules()`, `.rule(id)`, `.templates()`. **C**

## /configs_templates — "Modelos de mensagem" (WhatsApp/Meta templates)
**C** app/configs_templates/page-698395b00e1df24d.js
- Subtitle: "Gerencie os modelos de mensagem do WhatsApp disponíveis para seu time."
- **Endpoints (C):**
  - `GET /web/templates/available` → templates `[{id, displayName|metaTemplateName, bodyText, parameterSchema:[{index,name}], category:{id,key,name,displayName}, metaStatus, isCustom}]`
  - `GET /web/templates/categories` → `.categories`
  - `GET /web/templates/params` → `.params [{key, displayName}]`
  - `POST /web/templates` (WRITE; it submits the template to Meta for approval)
  - `DELETE /web/templates/:id`
- **Category keys (C, icon map):** administrative, campaign, billing, documentation, other, first_contact, reactivation, visit.
- **metaStatus (C):** approved → "Aprovado" (green), pending → "Pendente" (yellow), rejected → "Reprovado" (red).
- **Create form "Novo modelo de mensagem" (C):**
  - `name` "Nome do modelo de mensagem" — required "Nome é obrigatório".
  - `categoryId` "Categoria" — required "Categoria é obrigatória".
  - `bodyText` "Conteúdo da mensagem" — required "Conteúdo é obrigatório".
  - Body text rules: max 1024 chars ("Limite de 1024 caracteres excedido."); no links/emojis ("Não é possível inserir links ou emojis."); no parameter at the start; must end with a word after the parameter; max **3** parameters inserted as `{{displayName}}`.
  - Body sent: `{name, categoryId, bodyText, parameters:[{index, paramKey}]}`.
  - Toast: "Modelo de mensagem criado. Ele fica disponível após a aprovação da Meta."
- **Delete (C):** only `canManage && isCustom` ("Modelos de mensagem da Lais não podem ser excluídos."). 422 → "Apenas modelos de mensagem personalizados podem ser excluídos."
- Other UI: preview drawer with "Simule com exemplos" (local only); filter chips by category ("Todos"); search "Buscar modelos de mensagem"; empty states "Nenhum modelo com esses filtros" / "Nenhum modelo de mensagem encontrado".
- queryKeys: `template.available()`, `.categories()`, `.params()`. **C**

## /configs_meta_integration — "Integrações Meta" (Facebook Lead Ads forms)
**C** app/configs_meta_integration/page-07e410294b8fdcc1.js
- **Gate:** if LD flag `meta-integration-front` is **true**, the page redirects to `/configs` (`e&&t.replace("/configs")`). The feature is visible only while the flag is false (I: being retired or replaced by Smart Campaigns).
- **OAuth (C):**
  - Opens a popup to `https://www.facebook.com/v21.0/dialog/oauth?client_id=3958667614391745&redirect_uri=<origin>/facebook/callback&state=<32-byte hex>&response_type=code&config_id=1077486161187624`.
  - `state` is kept in `localStorage["fb_oauth_state"]`.
  - The popup page `/facebook/callback` posts `{type:"FB_OAUTH_CALLBACK", code|error, errorDescription}` to the opener; same-origin check.
  - Timeouts: 5 minutes; closed popup → "Login cancelado."
  - **U:** the `/facebook/callback` page chunk is not in the bundle set.
- **Endpoints (C):**
  - `POST /web/facebook/callback {code}` → `{pages:[{pageId,...}]}`
  - `POST /web/facebook/connect/finalize {pageIds:[...]}`
  - `GET /web/facebook/pages` → `[{ID, PageName, IsActive, ...}]`
  - `DELETE /web/facebook/pages/:pageId` ("Desconectar conta Meta?" — "A Lais não receberá mais leads dos formulários vinculados.")
  - `GET /web/facebook/forms?pageId=` and `GET /web/facebook/forms/local` → local forms `[{FbPageID, FormID, ...}]`
  - `GET /web/facebook/forms/meta`
  - `POST /web/facebook/forms {fbPageId, formId, formName}`
  - `PUT /web/facebook/forms/:formId/toggle {active}`
  - `GET /web/facebook/forms/:formId/questions?pageId=` → `.questions [{key}]`
  - `PUT /web/facebook/forms/:formId/mapping {mappings}` — defined but **no UI call site found** (I).
- **UI (C):**
  - Hero "Aumente seus resultados com os leads da Meta", CTA "Conectar à Meta", "Saiba mais" (lastro.notion.site link).
  - Section "Contas vinculadas" with badges Conectada / Inativa and "N formulários na Lais".
  - Page detail "Formulários da conta de {PageName}" — checkbox list, search "Buscar pelo nome", "Salvar", "Desconectar conta Meta".
  - Tooltip "N campos" lists the question keys.
  - Partial failure: "N formulário(s) falharam ao salvar."
- queryKeys: `facebook.all/pages()/forms(pageId)/formsLocal()/formQuestions(id,pageId)`. **C**

---

## /broadcasts — "Disparos em massa" (bulk WhatsApp sends; **SEND**)
**C** app/broadcasts/page-1f968e7e235eb49e.js (+ shared consts in 7533 module 12155)
- **Gate:** LD flag **`broadcasts-enabled`**. A wrapper does `u&&a.replace("/")` when flags are loaded and the flag is not true. **C**
- Header: "Disparos em massa" — "Envie mensagens no Whatsapp para diversos contatos de uma vez."
- **Status filter tabs (C):**

| key | label | API status filter |
|---|---|---|
| all | Todos | — |
| drafts | Rascunhos | pending |
| scheduled | Agendados | confirmed |
| sent | Enviados | sent |
| canceled | Cancelados | canceled,error |
| error | Erros | error |

- **Status labels (C):** canceled "Cancelado", confirmed "Agendado", error "Erro", pending "Rascunho", processing "Processando", sent "Enviado".
- **Type labels (C):** reachout / remarketing "Remarketing", property_owner "Atualização de anúncios". The API returns `remarketing`, which the UI maps back to `reachout`.
- **List:** columns Tipo / Nome / Status / Contatos; infinite list with `limit=20` and `offset`. Empty state "Nenhum disparo ainda" — "Crie o primeiro para falar com muitos leads de uma vez pelo WhatsApp." **C**
- **Wizard (4 steps, C)** — analytics step names `broadcasts_start`, `broadcasts_selection`, `broadcasts_message`, `broadcasts_review`:
  1. **"Informações do disparo"** ("Dê um nome, defina o objetivo e agende a data de envio.")
     - `name` (optional, auto-generated; placeholder "Ex: Reativação Leads Março 2026")
     - `description` ("Opcional: contexto interno")
     - `type` (Remarketing (leads inativos) | Atualização de anúncios (proprietários))
     - date and time (default 09:00); dates come from `GET /web/broadcasts/available-dates` (`{dates:[{day, available}]}`)
     - Rule: "O disparo precisa ser agendado com pelo menos 24 horas de antecedência." / "A Meta pode levar até 24 horas para aprovar o disparo".
  2. **"Selecionar contatos"**, with `contactMethod` one of:
     - `individual` — pick leads from `/web/leads` (`leadType=[realestate]`, `distinctByPhone`, limit 100, or 1000 with a suggestion). Columns Lead / Contato / Operação / Canal. Channel filter uses the origin list below.
     - `segment` — `GET /web/broadcasts/segments?type=` → `{segments:[{id,count,...}]}`.
     - `xls` — "Importação de lista", .xlsx ≤10 MB, validated via `POST /web/broadcasts/validate-file` (multipart `file`, `type`).
     - `property_owner` broadcasts are forced to `xls`.
     - Template sheet columns: remarketing `Nome, Telefone`; owner update `Nome, Link ou Código do Imóvel, Telefone`. Phone format `11999224444`.
     - Plan limit: `GET /web/broadcasts/plan` → `{totalUserPlan (default 1000), maxPerDispatch (default floor(15%))}`. "Você atingiu o limite de N contatos por disparo."
  3. **"Modelo de mensagem"** — templates `recommendation | launch | custom`. Owner update has a single fixed message ("A Meta só permite um modelo de mensagem para a Atualização de anúncios.").
     - Custom text must not be empty and must not start or end with a variable.
     - Variables: `{nome da pessoa}`, `{nome da Lais}`, `{link do imóvel}`.
  4. **"Revisar e confirmar"** → "Agendar".
- **Template bodies (C, verbatim):**
  - recommendation "Mensagem recomendada" (A mais indicada para reativar leads): "Olá, {nome da pessoa}! Você fez contato conosco recentemente procurando um imóvel. Você já encontrou um imóvel ou continua buscando? Entraram umas novas opções recentemente, e me lembrei de você. Gostaria de saber mais sobre este imóvel? {link do imóvel}"
  - launch "Mensagem para lançamentos" (A mais indicada para divulgar novos empreendimentos): "Olá, {nome da pessoa}! Você fez contato conosco recentemente procurando um lançamento. Temos uma novidade incrível para você! Em breve, vamos inaugurar um novo empreendimento. Gostaria de saber mais sobre? {link do imóvel}" (link placeholder "Link do empreendimento")
  - custom "Mensagem personalizada" (Configure a mensagem que desejar): user text.
  - property_owner default: "Olá {nome da pessoa}, tudo bem? Sou {nome da Lais}. Estamos atualizando as informações das propriedades em nosso portfólio e gostaríamos de confirmar se sua propriedade {imóvel} ainda está disponível? {link do imóvel}"
- **Create/confirm payloads (C):**
  - **JSON:** `POST /web/broadcasts {type:"reachout"|"property_owner", createAsDraft, name, description, scheduleDate:"YYYY-MM-DDTHH:MM:00-03:00", wizardStep?, …template, …targets}`
    - template for reachout: `{templateRef, templateCustom?, propertyLink?}`; for owner: `{templateType}`
    - targets for reachout: `{leads:[ids]}` (+`suggestionId`); for owner: `{propertyOwners:[ids]}`
  - **File:** `POST /web/broadcasts/file` (multipart: `file, type, createAsDraft, name, scheduleDate` (reachout) or `scheduledAt` (owner), `templateRef, templateCustom, templateType, propertyLink`)
  - Replace file: `POST /web/broadcasts/:id/file`
  - Edit draft: `PUT /web/broadcasts/:id {name,description,type,scheduleDate,wizardStep,...}`
  - Confirm draft: `PUT` then `POST /web/broadcasts/:id/confirm-pending` (**SEND scheduling**)
  - Reschedule: `PATCH /web/broadcasts/:id/schedule` (`"YYYY-MM-DDTHH:MM:00.000"`, dialog "Reagendar disparo")
  - Cancel: `DELETE /web/broadcasts/:id` (dialog "Cancelar disparo?", "Confirmar cancelamento" / "Manter agendado")
  - Response warnings `[{title, subTitle}]` are shown as toasts.
- Other reads: `GET /web/broadcasts/:id`, `GET /web/broadcasts/:id/targets?limit&offset`, `GET /web/broadcasts/property-owners?search&limit&offset`. **C**
- **Error map (C, verbatim):**
  - BROADCAST_003 "Não foi possível agendar o disparo com estes dados. Revise e tente novamente."
  - BROADCAST_004 "Este disparo não está mais como rascunho e não pode ser editado."
  - BROADCAST_005 "Já existe um disparo agendado para este dia. Escolha outra data."
  - BROADCAST_006 "Todos os contatos selecionados já possuem um disparo agendado."
  - BROADCAST_007 "Limite do plano excedido. Reduza o número de contatos."
  - BROADCAST_009 "Este recurso ainda não está disponível para a sua imobiliária."
  - BROADCAST_010 "A planilha tem erros que impedem o envio. Revise e tente novamente."
  - BROADCAST_011 "A planilha tem nomes inválidos. Corrija e envie novamente."
  - BROADCAST_012 "Nenhum contato válido na planilha. Verifique o arquivo."
  - BROADCAST_013 "Formato de arquivo inválido. Envie uma planilha .xlsx."
  - BROADCAST_014 "Não foi possível processar este disparo. Contate o suporte."
  - Detail overrides:
    - 005 + reason `already_used` → "Esta sugestão já foi usada em um disparo."
    - 001 + field `suggestionId` → "Não encontramos esta sugestão…"
    - 003 + `no_materializable_owner` → "Nenhum proprietário desta sugestão pode ser disparado…"
    - 014 + `suggestion_sourced` → "Este disparo veio de uma sugestão e a lista não pode ser trocada…"
    - 014 + `mirrored_upload` → "A planilha deste disparo não pode ser trocada…"
  - Fallback: `userMessage`, else "Não foi possível agendar o disparo, tente novamente ou contate o suporte".
- **Lead origin (portal) codes → labels (C, used as the channel filter):**
  GrupoZapLais Grupo Zap · SiteProprioLais Site próprio · NetImoveisLais NetImoveis · FacebookAdsLais Facebook Ads · ChavesNaMaoLais Chaves na Mão · ImovelWebLais ImovelWeb · RemarketingLais Remarketing · CasaMineiraLais Casa Mineira · WhatsAppLais WhatsApp · RocketImobLais Rocket Imob · KenloLais Kenlo · PlacaLais Placa · DFImoveisLais DF Imóveis · SUB100Lais SUB100 · InstagramAdsLais Instagram Ads · GoogleAdsLais Google Ads · WImoveisLais WImoveis · ImoblistLais Imoblist · CliqueiMudeiLais Cliquei Mudei · Lead4SalesLais Lead 4 Sales · 123iLais 123i · MappoLais Mappo · GuiaDeImoveisLais Guia de Imóveis · HubWLais Hub W · CasaJauLais Casa Jau · RedeInovaLais Rede Inova · SPImovelLais SP Imóvel · ZNImovelLais ZN Imóvel · ZLImovelLais ZL Imóvel · ZSImovelLais ZS Imóvel · ZOImovelLais ZO Imóvel · ABCImovelLais ABC Imóvel · LitoralSPImovelLais Litoral SP Imóvel
- **Smart suggestions** (also mounted in the layout; LD flag `smart-suggestion`, default true) **(C):**
  - Endpoints:
    - `GET /web/agency/smart-suggestions` → `{data:[{id, type, count}]}`
    - `GET /web/agency/smart-suggestions/:id`
    - `POST /web/agency/smart-suggestions/:id/cooldown {action:"dismiss"|"later"|"dispatched"}` (**WRITE**)
  - Types, in priority order: `remarketing` ("Dispare o Remarketing para N leads"), `property_owner_update` ("Atualize os dados de N imóveis"), `remarketing_development` ("Encontramos leads compatíveis com seu empreendimento recém-ativado…").
  - Shown as a bottom-right "Oportunidade" toast with buttons "Ir para Disparos" / "Ir para Imóveis" and "Depois".
  - The primary button navigates to `/broadcasts?suggestionId=`.
  - Throttling: a 10-minute cross-type throttle in `localStorage["smart-suggestions:cross-type-throttle-until"]`; impressions tracked in `sessionStorage["smart-suggestions:tracked-shown"]`.
  - Analytics: `smart_suggestion_shown`, `smart_suggestion_{dismissed|postponed|dispatched}`.
- queryKeys: `broadcast.all/list({status,type,limit})/availableDates()/segments(type)/plan()/targets(id)`, `["smart-suggestions",{agencyId}]`. **C**

---

## /catalogs — "Catálogo Meta" (Meta product catalog of integrated listings)
**C** app/catalogs/page-8e0a7cec4e0ec046.js; constants module 41415 (chunk 7533)
- **Gate:** LD flag `meta-catalog-front`; it is the nav child of the Smart Campaigns accordion. **C**
- Header: subtitle "Escolha quais imóveis integrados são enviados ao catálogo da Meta e acompanhe o status de cada envio."
- **Status tabs:** all "Todos", in_catalog "No catálogo", out_of_catalog "Fora do catálogo", error "Com erro".
- **syncStatus labels:** error "O último envio falhou", pending "Envio em andamento", submitted "Aguardando confirmação da Meta", synced "Enviado com sucesso".
- **Columns:** Imóvel, Catálogo, plus field labels clientListingId "Código na Meta", deletedAt "Removido em", lastSyncedAt "Última sincronização", syncStatus "Situação do envio".
- **Filters:**
  - search (title or code, min 3 chars), operation (buy/rent), city, priceMin / priceMax ("Preço mínimo não pode ser maior que o máximo").
  - Page size 20, max offset 10000. Bulk "Selecionar todos os N" sends `{selectAll, excludedAdIds}` or `{adIds}` (mock); limit constant 501 (I).
- **Endpoints:**
  - `GET /web/catalog/listings?status,search,priceMin,priceMax,operation,city,limit,offset,sort`
  - `GET /web/catalog/listings/stats`
  - `POST /web/catalog/listings/include|exclude` (same query, body `{adIds|selectAll,excludedAdIds}`)
  - `POST /web/catalog/listings/resync`
  - Result shape `{applied:[{adId,status}], skipped:[ids], failed:[{adId,code,reason}], summary}`; toasts listed in the domain constants.
  - **WRITE** (this pushes listings to Meta).
- **Subsets (product sets):**
  - Endpoints: `GET/POST /web/catalog/product-sets`, `PATCH/DELETE /web/catalog/product-sets/:id`, sent with `retries:0`.
  - Body `{name, color, filter, adAccountId?}`.
  - Filter fields: availability (Operação: for_sale Venda / for_rent Locação), listing_type, property_type (apartment/house/land/other), price, name, city, country, region (Estado), postal_code (CEP), num_beds (Dormitórios), num_baths.
  - Operators: eq/neq/lt/lte/gt/gte/contains/i_contains/not_contains/i_not_contains. Root combinator `and` ("Todos os filtros") / `or` ("Qualquer filtro").
  - Colors: #8354a7, #4dcffc, #ff793e, #545454, #5e5edd, #dc9f00, #f9526f, #28e4a8.
  - Presets: Venda / Locação.
  - Reserved system subsets "Remarketing Dinâmico Lais - Venda/Aluguel" (`remarketingSubsetType`) can't be edited.
  - Error codes: META_CATALOG_010…023 (see mocks).
  - Validation messages: "Informe um nome", "Use no máximo N caracteres" (N unknown, U), "Adicione ao menos um filtro", "Informe um valor", "Informe um número maior ou igual a zero", "Informe um número inteiro".
- **Empty states (C):**
  - "Seu catálogo ainda não foi sincronizado"
  - "Nenhum imóvel integrado"
  - "Nenhum imóvel encontrado"
  - "Nenhum imóvel com esses filtros"
  - "Todos os imóveis estão no catálogo"
  - "Nenhum erro de sincronização"

## /smart-campaigns — "Campanhas inteligentes" (Meta CAPI performance)
**C** 7808-*, 544-*, layout (service `/web/smart-campaigns`)
- **Gate (C):**
  - nav: LD flag `smart-campaigns-front` + permission `smart-campaign:read`.
  - page: `GET /web/smart-campaigns/onboarding-state` → `{state:"needs_oauth"|"awaiting_configuration"|"ready", agencyName, hasPixel, hasToken, hasAdAccount}`.
  - Redirects to "/" if the flag is off or onboarding returns error code `ErrSmartCampaignsNotConnected`.
  - Other error codes: `ErrSmartCampaignsAwaitingConfiguration`, `ErrSmartCampaignsDisabled`.
- Header: "Acompanhe o desempenho das campanhas Meta integradas à Lais."
- **Endpoints (C):**
  - `GET .../ad-accounts` → `{adAccounts:[{id, adAccountId, name}]}`
  - `GET .../campaigns?from&to&status(csv)&adAccountId` → `{campaigns:[{id,name,capi,status,spend,leads,qualifiedLeads,qualifiedPct,cpl,cpql}], summary:{totalLeads,qualifiedLeads,avgCpl,avgCpql,totalSpend}, lastUpdatedAt, syncedAt}`
  - `GET .../campaigns/:campaignId/leads?from&to&page&limit&search` → `{leads:[{id,name,email,phone,date,qualificationSource,status,chatId}], total, offset, limit}`
- **Summary cards:** Investimento total, Total de leads, Leads qualificados ("Apenas leads qualificados automaticamente pela Lais…"), CPL médio, CPQL médio.
- **Table:** Campanha, Status, Invest., Leads, Qual., plus % / CPL / CPQL (sortable; qualified% colored green ≥40, yellow ≥30, else red).
- **Filters:** search, "Apenas com a Lais" (capi), status chips, investment min/max, month.
- **Campaign status:** active "Ativa", paused "Pausada", in_review "Em revisão", rejected "Recusada", ended "Encerrada" (filter set: active, paused, ended).
- **Campaign leads drawer (CRM status), C:**

| lead.status | label |
|---|---|
| enhanced | Enviado ao CRM (green) |
| enhanced-error, expired | Erro no envio (red) |
| anything else (created, pending, message-sent-error) | Não pronto (gray) |

  Columns: Nome / Contato / Data / Status / Qualificado.

| qualificationSource | label |
|---|---|
| lais | Sim |
| manual | Manual |
| auto | Auto-envio |
| other | — |

- Staleness pill: "Atualizado agora/há N min/h/dias". Empty states: "Sincronizando as campanhas", "Nenhuma campanha encontrada para este mês", "Nenhuma campanha com esses filtros".
- Upsell for non-contracted users: "Solicitar demonstração" → modal "Vamos entrar em contato" ("Nosso time entrará em contato com o administrador…"). **This fires only an analytics event `button_clicked{action:"requested_demo"}` — no BFF call (C).**

## /smart-campaigns/remarketing — remarketing wizard (skeleton)
**C** app/smart-campaigns/remarketing/page-*
- **Gate:** `smart-campaigns-front` and `hasPixel===true` (else "denied" → `replace("/")`), plus flag `smart-campaigns-remarketing-front`, plus query `operation=sale|rent` (else it redirects to `/smart-campaigns`).
- Params: `operation`, `campaign` (edit mode), `adAccount`.
- **Steps:**
  1. "Informações": "Como o anúncio vai aparecer?" — "A Lais montou o criativo com os dados do catálogo…"
  2. "Revisão": "Revise antes de ativar" / edit "Revise as alterações".
  - Finish: "Ativar remarketing" / "Salvar alterações".
- **No create/update endpoint is wired:** finish is disabled on the last step (`isNextDisabled:!!E`). (C; I: work in progress.) Operation labels: sale "Venda", rent "Locação".

## /add-ons and its packages
**C** 544-* (module 39019), app/add-ons/*
- **Package catalog** (contracted state from `useContractedPackages`):

| id | Title | Price (C) | Offer href | Contracted href | Contracted when |
|---|---|---|---|---|---|
| gestao-de-atendimentos-pro | Gestão de atendimentos Pro | "a partir de" ~~R$ 999/mês~~ R$ 499/mês ("Preço especial de lançamento") | /add-ons/pro | /add-ons/pro | `usePremiumAccess().hasAccess` |
| smart-campaigns | Campanhas inteligentes | ~~R$ 2.250/mês~~ R$ 1.125/mês | /add-ons/smart-campaigns | /smart-campaigns | flag `smart-campaigns-front` and `onboarding-state.hasPixel===true` |
| atendimento-administrativo | Atendimento administrativo | "Consome meio crédito por atendimento", "Ative gratuitamente" | /add-ons/administrative | /atendimento-administrativo | agency `administrative.enabled===true` |

- Nav: "Pacotes adicionais" (`add-on:read`, isNew). Card labels: new "NOVO", contracted "Contratado", knowPackage "Conhecer pacote", check "Conferir".
- **/add-ons/smart-campaigns:** marketing page.
  - pill "Leads mais qualificados com o mesmo investimento"; callout "…aumentaram a taxa de qualificação de leads entre 25% e 50%…"
  - features: Integração com a Meta; Sinal de qualificação; Formatos compatíveis (Click to WhatsApp, formulário, landing page); Relatório mais fiel.
  - CTA "Solicitar demonstração" = analytics only.
- **/add-ons/administrative:** subtitle "Automatize as demandas que travam sua operação. Da segunda via de boleto ao registro de manutenção."
  - features: Envio de 2ª via de boleto; Registro de ocorrência (no ERP); Diagnóstico de manutenção; Orientação sobre processos administrativos.
  - "Sistemas ERPs integrados": KSI, Universal Software, Apolar Imóveis, Superlógica, Nido ADM, Properfy, apresenta.me, Flexpro Simob, MSYS Imob, Basis Sistemas.
  - CTA → `track("button_clicked",{action:"requested_demo",page:"add-ons/administrative",reaName,userRole})` only.
- **/add-ons/pro:** the route chunk only loads shared chunks 7531/4870/544/2800 (premium subscription UI: `/web/subscription/premium`, `/web/seats/*`). Covered by fork C (users/seats). The 402 interceptor exempts `/add-ons/pro` and `/acessos` from the upsell redirect. **C** 5138-*

## /financeiro — "Plano e cobranças"
**C** app/financeiro/page-bc79ba175a4c0147.js, 4424-* (service `/web/finance`)
- Gate: nav `billing:read` with `allowIfLastro`.
- **Endpoints (all reads except contacts):**
  - `GET /web/finance/subscriptions?status=active` → `[{status, plan:{type("cpa"…), name, displayName, overagePolicy("bump"…)}, validFrom, validTo}]`
  - `GET /web/finance/consumption?referenceMonth=YYYY-MM-01` → `{planType("annual"|"annual-per-exceeding"|monthly…), planCredits, usedCredits, totalCredits}`
  - `GET /web/finance/billing-account` → `{cnpj (14 digits), reas:[{name}]}`
  - `GET /web/finance/financial-contacts` → `{contacts:[{id,email}]}`
  - `POST/PUT/DELETE /web/finance/financial-contacts[/:id] {email}` (**WRITE**)
  - `GET /web/finance/invoices[?status=overdue]` → `[{id, status, billingPeriod, totalAmount, paidAt, cancelledAt, items:[{name, amount, type("overage"…)}], bankSlips:[{status, dueDate, digitableLine, downloadUrl}]}]`
  - `GET /web/finance/invoices/:id`
  - `GET /web/finance/add-on-billing-accounts?status=active` → `[{id, status, quantity, observation, addOn:{name}}]`
- **Enums (C):**
  - subscription status: active, notice-period. "Considered active" = both.
  - invoice status: draft, approved, billed, paid, overdue, cancelled, no-charge. Active = overdue+billed; history = paid+no-charge.
  - bank slip status: pending, issued, paid, overdue, cancelled.
  - add-on status: active.
- **UI (C):**
  - Card "Plano e conta", tabs "Plano atual" / "Conta de faturamento".
  - Plan name: "CPA" when `plan.type==="cpa"` and there are no credits. `monthlyLimit` = annual credits / 12 for annual plans.
  - Usage ring: "Consumo deste mês" | "Consumo da franquia anual"; "N restantes" / "N acima do limite".
  - Annual plans show "Vigência" with "N meses restantes".
  - Overage alert "Consumo acima do limite" with policy text: fixed "Créditos de atendimentos excedentes geram cobrança adicional na próxima fatura." / bump "A próxima fatura será ajustada pontualmente para enquadrar seu consumo no plano adequado."
  - "Valor da próxima fatura" + "Composição do custo".
  - "Cobranças": Baixar boleto / Copiar código do boleto / "Atrasado · N dias" / "Vence em"; empty state "Tudo em dia".
  - History: Pago em / Renegociado em, "Baixar comprovante".
  - "Pacotes adicionais" ("Nenhum pacote adicional ativo").
  - Financial contacts: "Pessoas que recebem boletos e comunicações financeiras.", delete confirm "Excluir contato financeiro?".
- **Change-plan flow (LD flag `finance-change-plan-front`):**
  - Link "Alterar plano" opens the modal "Pensando em trocar de plano?".
  - Field "Motivo principal" options: mais "Preciso de mais atendimentos", menos "Não estou usando o suficiente", custo "Quero reduzir o custo mensal", operacoes "Quero adicionar ou remover operações", addon "Quero alterar meus add-ons", outro "Outro motivo", cancelar "Quero cancelar a Lais"; plus an optional textarea.
  - **"Enviar solicitação" makes NO network call** — it only switches to the success view "Solicitação enviada… Contato via WhatsApp ou e-mail" (C: `onClick:()=>{m&&u("success")}`).
- queryKeys: `["finance","subscriptions",{status}]`, `["finance","billing-account"]`, `["finance","consumption",{referenceMonth}]`, `["finance","financial-contacts"]`, `["finance","invoices",{...}]`, `["finance","invoice",id]`, `["finance","add-ons",{status}]`. **C**
- Chunk 4424 also hosts the home/charts service `/web/agency/charts/*` (plan-consumption, alerts, lead-summary, leads-by-channel…) — fork C scope.

## /plans
Bubble iframe `bubblePath:"plans"`, title "Planos". No native code. **C** app/plans/page-*

---

## Endpoints not already in tools/methods.txt
- `POST /web/developments/bulk` (multipart file) — developments page `bulkImport`, via the `GO` fetch wrapper (fork C scope; seen while scanning).
- `GET /web/permissions`, `GET /web/permissions/teams`, `GET /web/report?date=` — via `GO`; noted by the parent already.
- **Next.js page (not a BFF endpoint):** `/facebook/callback` (OAuth popup target). U: its chunk is absent.

All other endpoints in this fragment are present in methods.txt.

## Gaps (U)
- The behavior, my-business, WhatsApp-profile, property-info and essential-questions editors are Bubble pages; their fields are not in the bundle.
- The reengage attempt editor UI and the remarketing campaign submit endpoint are not present (lazy chunk or not built yet).
- The catalog subset name max length and the BFF response for `/web/broadcasts/plan` beyond `totalUserPlan` / `maxPerDispatch` are unknown.

---

# Part C — home, users/teams, notifications, onboarding, checklist, developments, reports, misc, layout shell

Evidence tags: **C** = seen in code (chunk + excerpt), **I** = inferred, **U** = unknown. Chunk names are shortened (`7531` = `7531-6b46bfec9bcba325.js`, `layout` = `app/layout-cdffc32cc89c2014.js`, `page` = `app/page-1dd97fa3e0c91d44.js`, and so on). All paths are relative to `https://bff.lastro.services/api/v1` unless they start with `/api/` (Next.js route) or `wss://`.

---

## 0. Route manifest and route classes (layout shell)

**Full Next route manifest (C, `main-app`/`6084`, `{"path":"/creation-user-test"}` list):**
`/`, `/access-code`, `/acessos`, `/add-ons`, `/add-ons/administrative`, `/add-ons/pro`, `/add-ons/smart-campaigns`, `/atendimento-administrativo`, `/auth/error`, `/auth/signin`, `/avaliacoes`, `/broadcasts`, `/captacao`, `/catalogs`, `/chats`, `/checklist`, `/configs`, `/configs_behavior`, `/configs_display_attendant_name`, `/configs_meta_integration`, `/configs_my_business`, `/configs_property_info`, `/configs_qualification`, `/configs_reengage`, `/configs_templates`, `/configs_visits`, `/configs_visits_embed`, `/configs_whatsapp_profile`, `/creation-user-test`, `/credit-analysis`, `/debug`, `/developments`, `/facebook/callback`, `/financeiro`, `/history`, `/leads`, `/leads-v3`, `/notifications`, `/onboarding`, `/onboarding/sucesso`, `/owners`, `/pacotes-adicionais/gestao-de-atendimentos-pro`, `/perfil`, `/performance`, `/plans`, `/platform`, `/platform-meeting-schedule`, `/properties`, `/relatorio-v2`, `/relatorio-v3`, `/smart-campaigns`, `/smart-campaigns/remarketing`, `/trainings`, `/trainings_page`, `/unauthorized`, `/user-management`, `/visits`, `/whats-new`.
These routes have no JavaScript chunk in our capture: `/access-code`, `/creation-user-test`, `/debug`, `/facebook/callback`, `/onboarding*`, `/pacotes-adicionais/...`, `/platform-meeting-schedule`, `/unauthorized` (U: their contents were not downloaded).

**Route-class lists (C, `layout` module 22888):**
- `a` (onboarding-platform, **gP**): `/platform`, `/trainings`, `/platform-meeting-schedule`.
- `r` (bare embeds, **dc**): `/configs_qualification`, `/configs_visits_embed`, `/configs_display_attendant_name`.
- `s` (anonymous / access-code, **hc**): `/history`, `/access-code`.
- `i` (no app shell, **_G**): a ∪ `/history`, `/access-code`, `/creation-user-test`, `/auth`, ∪ r.
- `o` (full-bleed, **uf**): r ∪ `/configs_behavior`, `/configs_my_business`, `/configs_property_info`, `/configs_whatsapp_profile`, `/captacao`, `/leads`, `/owners`, `/performance`, `/plans`, `/user-management`, `/chats`, `/leads-v3`, `/acessos`, `/trainings_page`, `/history`, `/access-code`, `/catalogs`, `/developments`, `/properties`, `/smart-campaigns`, `/visits`, `/whats-new`, `/broadcasts`, `/relatorio-v2`, `/onboarding`, `/unauthorized`, `/facebook/callback`.
  - Excerpt (C, `layout`): `let a=["/platform","/trainings","/platform-meeting-schedule"],r=["/configs_qualification",...`

**Extra gate rows besides the sidebar nav (C, `layout`):**
`[{href:"/whats-new",featureFlag:"whats-new-page",pagePermission:"whats-new:read"},{href:"/onboarding",pagePermission:"page:all-roles"},{href:"/perfil",...},{href:"/checklist",...},{href:"/unauthorized",...}]`
These rows are merged with the nav gates (`z.S()`). If a route is **denied**, the layout calls `router.replace(ui(ctx))`, which sends the user to the first allowed nav href, or to `/` (C, `layout`: `(0,z.Mw)(I,C)&&r.replace((0,z.ui)(C))`).

**Shell-level redirects (C, `layout`):**
1. **Attendant app migration.**
   - Condition: the user's REA role is `attendant`, LaunchDarkly is loaded, and flag `attendant-app-migration` (default `true`) is **false**.
   - Effect: `window.location.replace("https://atendimento.casa.lais.ai"+path+search)`.
   - Excerpt: `r=(0,b.u)("attendant-app-migration",!0),s="https://atendimento.casa.lais.ai"`
2. **Platform onboarding.**
   - Condition: the agency has `status==="onboarding"` and has a module named `onboarding_automatizado`.
   - Effect: such an agency is forced to `/platform?agency=<id>`. Agencies without that state that land on an onboarding-platform route are sent back to `/`.
   - Excerpt: `"onboarding"===n.status ... "onboarding_automatizado"===e.moduleName ... e.replace("/platform?agency=")`
3. **Chat deep link to history.**
   - Condition: on `/chats?chatId=X`, the chat is resolved as `not-accessible`.
   - Effect: `replace("/history?chatid=X")`.
4. **Checklist and test-lead redirect.**
   - Flag `checklist` = "isChecklistExempt". If true, `/checklist` and `/creation-user-test` redirect to `/`.
   - Otherwise: a non-internal user who is not exempt, has no test user, has not disabled the test-lead step, and has not completed all flows is forced to `/creation-user-test`. After that, they are sent to `/checklist` inside the display window, otherwise to `/`.
   - Checked flows: `add-team`, `chat-control`, `connect-origins`, `reachout-leads`.
   - Excerpt: `if(c&&(t===q||t===D))return void e.replace("/")`
   - "Test-lead step disabled" = agency setting `disableOnboardingTestLeadStep` (I).
5. **Onboarding gate (C, `7427`).**
   - If `profile.needsOnboarding===true` → redirect to `/onboarding`.
   - Exempt: iframe contexts, emails ending in `@lastro.co`, users already on that path.
   - After submit → `/onboarding/sucesso`, which auto-redirects to `/`.
6. **Maintenance.** Flag `em-manutencao` sets a global maintenance store (`z.set(n)`). Copy (C, `layout`): title "Em manutenção - Casa da Lais"; description "Estamos em manutenção programada para atender você ainda melhor. A Casa da Lais está temporariamente indisponível." The exact rendering condition is I.
7. **Mobile.** On mobile the shell shows "Para utilizar a Casa da Lais em dispositivos móveis, baixe o aplicativo" / "Baixar o aplicativo" (App Store id6749020881, Play `co.lastro.casa_da_lais_mobile`) (C, `layout`/`7531`).
8. **Offline.** "Sem conexão com a internet" / "Verifique sua conexão para continuar de onde parou." Connectivity is probed with `HEAD /favicon.ico?t=` (C, `layout`).
9. **Chunk reload.** `sessionStorage "lastro:chunk-reload-attempt"` (C, `layout`).

**Agency (REA) selector (C, `layout` + `5138` + `4450`):**
- Header copy: "Meus negócios", "Todos os negócios", "Nenhum negócio encontrado", "Não foi possível buscar os negócios", placeholder "Buscar página ou imobiliária...", actions "Copiar ID" / "Copiar nome".
- REAs come from `GET /auth/users/me` merged with `GET /auth/users/me/profile` (`getMe`). Each REA has `id`, `role`, `seatType`, `isGestor` (C, `4870` permission matrix reads `e.role,e.seatType,e.isGestor`).
- Search: `GET /auth/agencies/search?q=` (min 3 chars, debounced; query key `auth.agencySearch.byQuery(q)`) (C, `7531`: `minLength:3`).
- The selected agency is stored in `localStorage "casa-da-lais:selected-rea-id"` (C, `5138`) and sent as the `x-agency-id` header on every BFF call (C, `5138` `injectAuthHeaders`).
- Internal/support agency: `localStorage "casa-da-lais:support-agency"` (C, `4450`).
- `GET /web/agency/details` (with optional `x-agency-id` override) supplies `agencyType` (e.g. `developer`), `status`, `modules[].moduleName` (I from gate usage).

**LaunchDarkly context (C, `layout`):**
```
{kind:"agency", key:<agencyId>, agencyType?, userRole?, isLastro?}
// no agency → {kind:"user", key:"anonymous", anonymous:true}
```
Provider options: `useCamelCaseFlagKeys:false`, `timeout:5`. Excerpt: `let s={kind:"agency",key:t};return n&&(s.agencyType=n),a&&(s.userRole=a),void 0!==r&&(s.isLastro=r)`

**Intercom (C, `2134`):**
- `app_id "cnf8wd9k"`.
- `POST /api/intercom {user_id}` returns `{hash}` (identity verification).
- Boot payload: `{app_id,user_id,user_hash,name,email,company:{company_id:selectedReaId}}`.
- Not booted for the `attendant` role or inside an iframe. Shut down on logout or role change.
- Tracks `button_clicked{action:"intercom"}` when the messenger is shown.

**Browser notifications (C, `layout`/`5435`):**
- Flag `browser-notifications-front`.
- `WebNotificationsProvider` with `socketUrl:"wss://eventhub.lastro.services"` → `/ws/notifications?token=<redacted>&agencyId=`. Event `notification:created` invalidates `notification.all`.
- `localStorage "lais.browser-notifications.enabled"`. The favicon badge counter is canvas-drawn.

**Smart-suggestion popups (C, `layout` + `broadcasts`):**
- Flag `smart-suggestion` (default `true`). Not shown for the `attendant` role.
- Eligibility comes from `GET /web/agency/charts/plan-consumption?month&year`: shown only if `percentageOfConsumption<85` and `projectedConsumption/totalUserPlan<90%`. The popup fires after a random delay of 30–180 s.
- Reads `GET /web/agency/smart-suggestions` → `data:[{id,type,count}]`. Types, in priority order: `remarketing`, `property_owner_update`, `remarketing_development`. CTA → `/broadcasts?suggestionId=<id>`.
- Copy:
  - remarketing → "Dispare o Remarketing para N leads" / "Você tem leads esquecidos na sua base…" / "Ir para Disparos"
  - property_owner_update → "Atualize os dados de N imóveis" / "Sua base de imóveis parece estar desatualizada…" / "Ir para Imóveis"
  - remarketing_development → "…Encontramos leads compatíveis com seu empreendimento recém-ativado…"
- Buttons: dismiss / "Depois" / primary → `POST /web/agency/smart-suggestions/:id/cooldown {action:"dismiss"|"later"|"dispatched"}` (**WRITE**).
- Storage: `localStorage "smart-suggestions:cross-type-throttle-until"` (now+10 min), `"smart-suggestions:tracked-shown"` (last 50 event ids).
- Analytics: `smart_suggestion_shown`; `button_clicked` with action `smart_suggestion_{dismissed|postponed|dispatched}`.
- `GET /web/agency/smart-suggestions/:id` is used by `/broadcasts` (`suggestionId`).

**Other shell banners (C, `layout`):**
- Overdue invoices banner: "Ver boletos →", page `overdue_invoices_banner`, actions `close_invoice_warning` / `see_invoices`. Dismissing it calls `POST /web/agency/settings {…, dismissOverduePaymentSlipAlert:true}`; the optimistic update sets `overduePaymentSlipAlertDismissedAt` (C, `4870` 66541).
- Upsell cards: "Gestão de atendimentos Pro", "Campanhas inteligentes", "Atendimento administrativo", "Vamos entrar em contato" ("Nosso time entrará em contato com o administrador para agendar uma reunião comercial.").

**Storage keys in app code (C):**

| Key | Store | Chunk | Purpose |
|---|---|---|---|
| `casa-da-lais:selected-rea-id` | local | 5138 | selected agency |
| `casa-da-lais:support-agency` | local | 4450 | internal support agency |
| `@lastro/chat:pinned-chats` | local | 3b4451b3 | pinned chats |
| `kanban_defaultHidden_<user>` / `kanban_archiveHidden_<user>` | local | 3b4451b3 | kanban column visibility |
| `sidebar-collapsed` | local | layout | nav state |
| `hidden-values` | local | 4424 | hide money values toggle |
| `lais.browser-notifications.enabled` | local | 5435 | browser notifications opt-in |
| `smart-suggestions:cross-type-throttle-until`, `smart-suggestions:tracked-shown` | local | layout | popup throttle |
| `training-progress:<vimeoId>` | local | trainings_page | video progress |
| `access-code:attempts:<agency>` | local | history | access-code lockout (3 tries → 60 s) |
| `bubble_storage_*` | local | 5812 | Bubble iframe storage proxy |
| `fb_oauth_state` | local | configs_meta_integration | Facebook OAuth CSRF state |
| `analytics_device_id` | local | 7215 | analytics |
| `analytics_session_id`, `analytics_last_activity` | session | 7215 | analytics |
| `bubble_version_override` | session | 5812 | Bubble `/version-x` override |
| `broadcast_lead_selection` | session | 9934/broadcasts | leads → broadcast handoff |
| `post_logout_signal` | session | 6844 | logout |
| `lastro:chunk-reload-attempt` | session | layout | chunk error recovery |

**Analytics (C, `7215` + call sites):**
- Event names: `button_clicked` (main event, with `action`), `page_view`, `smart_suggestion_shown`, `view_property`, `view_on_site`, `toggle_view_mode`, `open_property_modal`, `map_item_click`, `copy_link`, `copy_history_link`, `copy_code`, `change_page`, `access_similars`, `view_similar_property`, `access_property_listing_page`, `administrative_report_menu_clicked`.
- `button_clicked` action values seen:
  - `access_association`, `access_broadcasts`, `access_chat`, `access_filters`, `access_smart_campaigns`
  - `administrative_report_conversations_to_leads`
  - `assign_association`, `atribuir`, `auto_chat_intervention`, `banner_edit_reengage`
  - `cancel_association`, `cancel_paused_lais_popover`, `check_demanding_followup`
  - `clear_filter`, `clear_search`, `close_invoice_warning`
  - `completed_blog`, `completed_podcast`, `completed_specialist_project`
  - `confirm_paused_lais_popover`, `dislike`, `download_document`, `filter_chats`, `intercom`, `learn_more`, `like`
  - `open_audio_recorder`, `open_file_upload`, `open_image_upload`, `open_replied_message`, `open_template_drawer`, `open_video_upload`
  - `play_audio_message`, `remove_association`, `reply_message`, `requested_demo`, `search_chats`, `see_invoices`, `select_emoji`, `send_audio_message`, `send_message`
  - `useful`, `view_property`, `whats_new_banner_{dismiss|see_news|snooze}`, `smart_suggestion_*`
- Standard properties: `agencyID`, `isInternal`, `page`, `userID`, `version`.
- Transport: `/api/analytics` proxy (GET health, POST batch) plus Amplitude (session replay behind flag `amplitude-session-replay`).

---

## 1. `/` Home (`page`)

- **Header.** Title = selected agency name, blurred when the "hidden values" toggle is on (C: `className:I?"select-none blur-sm"`). Actions: "Recarregar dados" (resets all chart queries `x.v.all`) and a `MonthYearPicker`. `?month=&year=` are kept in the URL via `history.replaceState`.
- **Cards and their endpoints.**

| Card | Endpoint | Response fields (C usage) |
|---|---|---|
| **Atividades** | `GET /web/finance/consumption?referenceMonth=YYYY-MM-01` (`fJ`) + `GET /web/agency/charts/alerts?month&year` | consumption: `planType` (monthly/annual/annual-per-exceeding), `usedCredits`, `totalCredits`, `monthConsumption`, `planCredits`; alerts: `totalAlertAttendance`, `totalVisits` |
| **Dados gerais de atendimento** (tooltip "Panorama de todos os atendimentos: leads comerciais, proprietários e inquilinos.") | `GET /web/agency/charts/lead-summary?month&year` | `uniqueClients`, `unattendedConsumption`, `qualifiedConsumption` |
| **Destaques** (carousel; "Slide anterior" / "Próximo slide") | `GET /web/banners/home` (query key `banners.home()`; sorted by `displayOrder`) | `id`, `name`, `title`, `description`, `imageUrl`, `ctaText`, `linkUrl`, `isExternal`, `hexColor`, `displayOrder`. Fallback banner `relatorio_default` → `/relatorio-v2` |
| **Leads por canal** | `GET /web/agency/charts/leads-by-channel?month&year[&category]` | `channels[]` with `originTranslate`, `total`, `sent`, `topStatus` |
| **Status por canal** | `GET …/lead-status-by-channel` | per channel `originTranslate`, `statuses[]{status,count,leads}` |
| **Leads nos últimos 6 meses** | `GET …/leads-last-six-months` | `monthYear`, `count` |
| **Leads por horário em <mês>** | `GET …/leads-per-hour` | `hours[]{hour,count}` |
| **Leads semanais em <mês>** | `GET …/leads-per-weekday` | `weekdays[]{weekday,count}` |
| **Personalizações de comportamento** ("NOVO", "Conferir todas" → `/configs`) | none (links into Bubble configs) | |

  - Atividades rows:
    - "Consumo do plano" or "Consumo do plano anual". Badge `usageCurrent / usageTotal`; tooltip "N atendimentos consumidos em <mês>". Links to `/financeiro` only for admin or internal users.
    - "Cobranças de atendimento" → `/notifications?page=1&type=lead-user-demanding-followup-notification` (tracks `check_demanding_followup`).
    - "Pré-agendamento de visitas" → `/visits`.
  - Dados gerais tiles:
    - "Topo de funil" ("chegaram pelos canais") = `uniqueClients`
    - "Atendimentos" ("foram atendidos pela Lais") = `uniqueClients-unattendedConsumption`
    - "Encaminhados" ("foram enviados ao CRM pela Lais") = `qualifiedConsumption`
  - Status-por-canal legend: "Enviado ao CRM" (status `enhanced`), "Não pronto" (`message-replied`), "Erro no envio" (`enhanced-error`). The 6-month chart uses "Enviado ao CRM" / "Não enviado ao CRM".
  - Personalizações cards: "Pré-agendamento de visita" ("Quando a Lais deve oferecer o Pré-agendamento de visitas?" → `configs_visits?type=visit`); "Perguntas essenciais" ("O que a Lais deve perguntar para seus leads?"); "Reengajamento" ("Como a Lais deve lidar com leads que pararam de responder?" → `configs_reengage?type=reengagement`).
- **Charts service details.**
  - All charts endpoints use the same param builder, which takes `month`, `year`, and an optional `category` (C, `4424` 81570: `buildCategoryQuery`).
  - The category filter tabs are "Visão geral" (`all`), "Compra" (`buy`), "Aluguel" (`rent`) and "Administrativo" (`administrative`).
  - A long timeout is applied (`timeout:o.A`, and `o.D` for six-months; exact values U).
- **Query keys.** `charts.alerts(m,y)`, `leadStatusByChannel(m,y,cat)`, `leadSummary(m,y)`, `leadsByChannel`, `leadsLastSixMonths`, `leadsPerHour`, `leadsPerWeekday`, `planConsumption(m,y,agency)`, `finance.consumption(ref)`, `banners.home()`.
- **Empty state / error.** "Nenhum dado disponível", "Tentar novamente"; error text "Falha ao carregar os banners de destaque".

---

## 2. `/acessos` (native; chunks 2800/7531/4870) and `/user-management` (Bubble `user_management`)

- **`/user-management`** = `BubbleIframePage{bubblePath:"user_management",title:"Acessos"}` plus a coach-mark banner for flow `add-team` (C, `user-management`).
- **`/acessos` gate.** Nav item label "Usuários e equipes" (or "Equipes" for attendants); gate `requiresTeamViewPage` = permission `team:view-page` from `GET /web/permissions/teams` (C, `7533`).
- **Page.** Title "Usuários e equipes" / "Gerencie quem pode acessar e administrar sua Casa da Lais." Tabs: `users` "Usuários", `teams` "Equipes" (badge "NOVO") (C, `7531`). PRO landing title "Gestão de atendimentos Pro".

### Users tab
- **Columns.** "Nome", "E-mail", "Cargo", "Assento", "Status"; pagination 10/20/50; empty "Nenhum usuário encontrado" (C, `2800`).
- **Seat bar.** "Assentos Pro em uso", from `GET /web/seats/availability` → `{contracted,occupied,extra,pricePerExtra}` (C mock + `2800` `W.contracted/W.occupied`). Also `GET /web/seats/summary` → `{agencyId,period{year,month},summary{paid,free,test,maxPaidSeats},users[]}` (C mock). The mock paths lack the `/web` prefix; the real client uses `C="/web/seats"` (C, `7531`).
- **List.** `GET /auth/users?[seatType=]` (key `premium.users.list`) → `[{id,name,email,role,seatType,active}]` (C mock).
- **Row actions** (C, `2800` + copy `7531`), with their gate tooltips:

  | Action | Gate tooltip(s) |
  |---|---|
  | "Editar nível de acesso" | "Apenas Administradores e Editores podem editar"; "Apenas Administradores podem editar"; "Para editar entre em contato com o suporte" (admin cannot edit admin) |
  | "Dar acesso de editor" / "Tornar membro" | none |
  | "Alterar assento" | "Apenas Administradores podem alterar o assento"; "Para adicionar usuários em assentos Pro, ative o pacote" |
  | "Excluir usuário" | "Apenas Administradores podem excluir usuário"; "Para excluir entre em contato com o suporte" |

  - Delete confirmation: "O usuário perderá o acesso à Casa da Lais. Não é possível desfazer." → `DELETE /auth/users/:id`.
  - Seat upgrade: "O usuário poderá usar todas as funcionalidades do assento Pro."
  - Seat downgrade: "O assento utilizado ficará disponível…" → "Remover assento pago".
- **Create / edit user wizard** (C, `4870` 59734 + copy `7531`).
  - Steps: "Informações da conta", "Permissões", "Tipo de assento". Total steps = 3; the simplified variant has 1 step and forces `role:"member",seatType:"free"`.
  - Fields (zod):

    | Field | Label | Rule | Message |
    |---|---|---|---|
    | `name` | "Nome completo" | `min(1)` | "Este campo é obrigatório" |
    | `email` | "E-mail" | `.email()` | "E-mail inválido" |
    | `role` | "Nível de acesso" | `min(1)` | "Este campo é obrigatório" |
    | `seatType` | — | enum `paid` / `free` | "Este campo é obrigatório" |

    - Cross-field refine: `role==="attendant"` requires `seatType==="paid"` → "Atendente precisa de assento Pro".
  - Live email check: `GET /auth/users/check-email?email=` (500 ms debounce) → `{exists}`. States: checking "Verificando e-mail...", available "Este e-mail está disponível", taken "Este e-mail já está em uso", error "Falha ao verificar e-mail. Tente novamente."
  - Role cards (`value`, label, permission bullets):
    - `admin` "Administrador": Acessa a Casa da Lais / Visualiza todos os atendimentos / Edita configurações / Adiciona e edita usuários / Acessa Plano e cobranças e contrata assentos Pro.
    - `editor` "Editor": … / Adiciona usuários membros / ✗ Não acessa Plano e cobranças.
    - `member` "Membro": … Visualiza configurações / ✗ Não adiciona usuários / ✗ Plano.
    - `attendant` "Atendente" (`premiumOnly`): Acessa para atender em equipes / Visualiza apenas os próprios atendimentos / ✗ configurações / ✗ usuários / ✗ Plano.
  - Seat cards:
    - "Padrão" (`free`): "Não tem visão segmentada…", "Não participa de equipes de atendimento"; disabled for attendants ("Atendentes só podem ter assento Pro").
    - "Pro" (`paid`): availability "N disponível(is)" or "R$24,50 por mês".
    - If a `paid` seat is chosen with 0 seats free, the wizard opens "Contratar assento adicional".
  - Submit: `POST /auth/users {name,email,role,seatType}`. Edit uses the **same POST** (`updateUser(e){return this.createUser(e)}`; C, `7531`), so the BFF upserts by email (C mock).
  - Toasts: "Usuário adicionado com sucesso!" / "Usuário editado com sucesso!" / "Usuário removido com sucesso!" / "Assento alterado com sucesso!".
- **Labels.**
  - Role display labels (C, `7531` `K`): admin "Administrador", editor "Editor", membro_sem_premium "Membro", membro_com_premium "Membro Pro", atendente_sem_gestor "Atendente", atendente_gestor "Atendente gestor".
  - Seat labels: `paid` "Pro", `test` "Pro (teste)", `free` "Padrão". `seatType:"test"` is shown as `paid` in forms.
- **Client-side permission matrix** (C, `4870` `usePremiumPermission`).
  - Profile key derivation: role `admin`→`admin`, `editor`→`editor`, `member`+paid/test→`member_premium`, `member`+free→`member_standard`, `attendant`+`isGestor`→`atendente_gestor`, `attendant` without gestor→`atendente_sem_gestor`.
  - Matrix (✓ = allowed; scope shown where set):

    | action | admin | editor | member_standard | member_premium | atendente_sem_gestor | atendente_gestor |
    |---|---|---|---|---|---|---|
    | create_team | ✓(I) | ✓ | ✗ | ✗ | ✗ | ✗ |
    | edit_team | ✓ all | ✓ all | ✗ | ✗ | ✗ | ✓ own_team |
    | subscribe_premium / cancel_premium | ✓ | ✗ | ✗ | ✗ | ✗ | ✗ |
    | filter_by_responsible | ✓ | ✓ | ✗ | ✓ | ✗ | ✓ |
    | view_my_conversations | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
    | view_all_conversations | ✓ | ✓ | ✓ | ✓ | ✗ | ✓ own_team |
    | transfer_to_person | ✓ all | ✓ all | ✗ | ✗ | ✓ own_chats | ✓ own_team |
    | add_user | ✓ | ✓ | ✗ | ✗ | ✗ | ✗ |
    | change_role | ✓ | ✓ | ✗ | ✗ | ✗ | ✗ |
    | change_seat | ✓ | ✗ | ✗ | ✗ | ✗ | ✗ |
    | delete_user | ✓ | ✗ | ✗ | ✗ | ✗ | ✗ |

  - Server-side permissions are separate:
    - `GET /web/permissions` → `{permissions:{<key>:{allowed,reason,blockBehavior}}}`. Default when a key is missing: `{allowed:false,reason:"role_restricted",blockBehavior:"hide"}`.
    - `GET /web/permissions/teams` → `{permissions,context}` (C, `layout` 19513). Query keys `auth.permissions.chat(agency)` and `.teams(agency)`; staleTime 1 h.
    - Reason messages:

      | reason | message |
      |---|---|
      | `premium_module_required` | "A Gestão de atendimentos Pro precisa estar ativa" |
      | `premium_seat_required` | "Você precisa de um assento Pro para esta ação" |
      | `role_restricted` | "Você não tem permissão para esta ação" |
      | `team_restricted` | "Esta ação é restrita à sua equipe" |

    - `blockBehavior`: `hide` or `readonly` (C mock).

### Teams tab (PRO; mock flags `premium.teams`)
- **Empty state.** "Organize os usuários em equipes de atendimento" / "Centralize sua operação…"; tooltip "Para criar equipes de atendimento, ative o pacote". If not admin: "Apenas Administradores podem criar equipes."
- **List.** `GET /web/teams?page&limit[&managedByMe=true]` → `{teams:[{id,name,membersCount,distributionEnabled,rouletteEnabled,lastAttendantEnabled,autoCrmEnabled,createdAt,leadTypes[],administrativeCategories[]}],pagination{total,page,limit}}` (C mock).
- **Detail.** `GET /web/teams/:id` → `{id,name,lastAttendantEnabled,autoCrmEnabled,members[],distributionConfig{leadTypes,receivesSpecificSubcategories,classifiers},roulette{membersOrder,currentIndex}}` (C mock).
- **Detail table** (C, `7531` copy `P`).
  - Columns: "Usuário", "Último acesso", "TPR" (tooltip "TPR (tempo de primeira resposta)": "Tempo médio entre a atribuição da conversa e a primeira resposta do atendente."), "Conversas" ("Conversas atribuídas"), "Distribuição" ("Define se o membro da equipe receberá novas conversas.").
  - Badges: "Gestor"; "Administrativo • Geral" or "Administrativo • N categorias".
  - Menu: "Configurações", "Usuários", "Excluir equipe".
  - Delete confirm: "Ao excluir uma equipe, todos os atendimentos vinculados a ela são desassociados automaticamente: ficam sem equipe e sem usuário atribuído." → `DELETE /web/teams/:id`.
- **Metrics.** `GET /web/teams/:id/metrics` → `{members:[{userId,userName,tprAvgMinutes,activeConversations,lastAccess}]}`.
- **Per-member distribution switch.** `PATCH /web/teams/:id/members/:userId {distributionActive}` (C, `2800`: `data:{distributionActive:s}`).
- **Create-team wizard** (3 steps; C, `7531` copy `S`, payload in `4870`/`2800`).
  - Step 1: "Nome da equipe" (required `*`).
  - Step 2: "Defina as configurações específicas da equipe."
    - "Esta equipe atende clientes diretamente após a Lais?" — "Sim" / "Não" (no = "só recebe atribuições manuais pela página de Conversas") → field `distributionEnabled`.
    - "Como os leads serão atribuídos?" — "Via CRM" (badge "Padrão"; "Leads são enviados ao CRM com link de atribuição.") or "Via Lais" (badge "Atendimento mais rápido") → `rouletteEnabled = distributionEnabled && mode==="lais"`. Warning "Evite atribuições duplicadas".
    - "Distribuição automática de atendimentos": categories `rent`/"Aluguel", `buy`/"Compra", `administrative`/"Administrativo" (UI "Cliente Administrativo" in mock), `propertyowner`/"Proprietário" → `leadTypes[]`, only sent when "Via Lais". Each category can belong to only one team (`GET /web/teams/lead-types?excludeTeamId=` → `{leadTypes:[{key,label,available}],generalAdmTeamExists}`).
    - "Enviar automaticamente ao CRM" → `autoCrmEnabled = rouletteEnabled && toggle`.
    - "Manter atribuição ao último responsável" ("Quando o lead voltar a conversar, ele será atendido pelo mesmo atendente.") → `lastAttendantEnabled`.
    - "Receber apenas categorias específicas" → `receivesSpecificSubcategories` + `classifiers[]`, from `GET /web/teams/occurrences/availability?excludeTeamId=` → `[{classifier,name,linkedTeamId,linkedTeamName}]`. Mock classifiers: 37 "Boleto em atraso", 38 "Segunda via de boleto", 39 "Reajuste de aluguel", 40 "Rescisão de contrato", 41 "Manutenção do imóvel".
    - Conflicts: "Já existe uma equipe administrativa geral"; "Uma das categorias selecionadas já foi vinculada a outra equipe…".
    - Administrative modal: "Antes de continuar" ("…faz parte do Atendimento administrativo da Lais…").
  - Step 3: "Adicionar usuários à equipe"; search "Buscar usuário"; "Tornar gestor" (only Pro-seat users; "Apenas usuários com assento Pro têm acesso…").
  - Submit:
    1. `POST /web/teams {name,distributionEnabled,rouletteEnabled,lastAttendantEnabled,autoCrmEnabled,leadTypes,receivesSpecificSubcategories,classifiers}`
    2. then `POST /web/teams/:id/members {members:[{userId,role:"gestor"|"attendant"}]}`
    - Toast "Equipe criada com sucesso!".
  - Edit: `PATCH /web/teams/:id` with the same body; "Configurações atualizadas com sucesso!".
  - Members edit: add via `POST …/members`, remove via `DELETE /web/teams/:id/members/:userId`. Removal notice: "Ao remover um membro da equipe, os atendimentos atribuídos a ele são redistribuídos automaticamente…" (gestores first, else split equally, else stay on the team unassigned).
- **Defined but no UI call site found** (mock-only?): `PUT /web/teams/:id/distribution {leadTypes}` and `PUT /web/teams/:id/roulette {membersOrder}` (C `7531` service; I).

### PRO module ("Gestão de atendimentos Pro")
- **Status.** `GET /web/subscription/premium` → `{active,status:"active"|"pending_cancellation",subscriptionId,agencyId,seats,peakSeats,billingPeriod,cycleStart,cycleEnd,activatedAt,cancelledAt}` (C mock + `2800`). The 402 discovery endpoint is not redirected.
- **Status badges.** "Pacote contratado" / "Cancelamento agendado" ("Seu acesso Pro permanece até <cycleEnd>.").
- **Activate (admin only).**
  - Prices (C, `7531` `U`): module R$499,50 (was 999,00) for 5 seats; extra seat R$24,50 (was 49,00). Also MONTHLY 49,90 / ANNUAL 39,90 per seat. MAX_SEATS 100.
  - Validation: "Mínimo de 1 assento" / "Máximo de 100 assentos" / "Aceite os termos para continuar" (checkbox "Aceitar termos de contratação", link "aditivo de contratação").
  - Call: `POST /web/subscription/premium {seats}` (I body from mock).
- **Change seats.** `PATCH /web/subscription/premium {seats}` ("Contratar assento adicional"; "1 assento.").
- **Cancel.** `DELETE /web/subscription/premium` → `{accepted,effectiveAt}`. Copy: "Cancelar Gestão de atendimentos Pro?" / "Todos os recursos Pro serão desativados imediatamente. Não é possível desfazer.". Features lost: "Equipes", "Distribuição automática", "Visão segmentada", "Acesso pelo app".
- **"Primeiros passos" guide** (C, `7531` `v`): steps attendants / distribution / teams / instruct, with guide link `suporte.lais.ai/.../19632269-gestao-de-atendimentos-pro`.
- **Access-code card.**
  - Copy: "Código de acesso" / "Compartilhe com colaboradores para que acessem links da Lais." / suffix "Código da Lais".
  - Call: `GET /web/agency/access-code` → `{accessCode}`. "Indisponível" when absent (C, `2800`). Tracks `copy_code`.

---

## 3. `/notifications` (native; chunk `notifications`)

- **Endpoint.** `GET /web/notification-events?page&limit&createdSince&createdUntil&transactionType&type=<repeated>`.
  - Query key `notification.notifications(params)`.
  - Default period: first day of the current month → now.
  - This is a different endpoint from `/web/notifications`, which the PRO mock covers.
- **Item shape** (C mapper): `{id,type,isRead,createdAt,successfulOwnerDispatches,referenceID,structContent:{…}}`.
  - `structContent` fields: `leadName`, `title`, `description`, `createdAtFormatted`, `leadNumber`, `leadEmail`, `leadClientListingID`, `leadVatNumber` (CPF), `leadConversationSummary`, `leadPropertyListingURL`, `leadTransactionType`, `leadVisitDates[]`, `leadID`/`leadId`, `leadChatID`/`chatId`, `visitGroupId`.
- **Types and labels** (C):

| type | label | card actions |
|---|---|---|
| `lead-visit-notification` | Solicitação de pré-agendamento de visita | "Ver conversa", "Ver visita" (→ `/visits?visitGroupId=`), share |
| `chat-assigned`, `chat-queued` | Novo atendimento | "Ver conversa" |
| `new-lead-message` | Nova mensagem | "Ver conversa" |
| `lead-user-demanding-followup-notification` | Cobrança de atendimento | "Ver conversa" |
| `real-estate-agency-report-generated` | Relatórios da Lais | "Acessar relatório" |
| `real-estate-agency-reachout` | Remarketing | "Tabela de leads" (→ `/leads?origin=ReachOutLais&…`) |
| `lead-property-acquisition` | Captação | share |
| `property-owner` | Atualização de base de imóveis | "Ver proprietários" (→ `/owners`) |
| `lead-enhanced-group-notification`, `lead-enhanced-attendant-notification`, `lead-enhanced-notification` | Novo lead gerado | "Ver conversa" |
| `google-review-notification` | Avaliações no Google | (body only) |
| `real-estate-agency-notification` | (raw type) | "Atualizar plano" (→ `/plans`) |

- **Share button.** "Compartilhar link" opens `https://api.whatsapp.com/send?text=` with prefilled text, for example "A Lais pré-agendou uma nova visita: …", "Novo lead: …", "A Lais identificou uma potencial captação: …", "A Lais identificou uma cobrança de atendimento: …". The chat link inside is `<origin>/history?chatid=`. This is a client-side link, not an API call.
- **Filters** ("Filtro de notificações"):
  - "DATA DA NOTIFICAÇÃO"
  - "OPERAÇÕES": Todas / Aluguel (`rent`) / Compra (`buy`)
  - "TIPO DE NOTIFICAÇÃO": the groups above
  - Attendants see only the attendant subset (`attendantTypesOnly`).
- **Acquisition view.** `?view=acquisition` (nav "Captação" = `/notifications?type=lead-property-acquisition&view=acquisition`, permission `property-capture:read`). Title "Captação" / "Acompanhe as notificações de imóveis potencialmente captados."; type filter hidden. Default title "Notificações" / "Mantenha-se atualizado com as notificações personalizadas da Lais."
- **Toggle.** "Notificar lead pronto para atendimento" ("Quando ativo, a Lais notifica quando um novo cliente aguarda atendimento humano.") → `POST /web/agency/settings {allowNotifications:bool}` (**WRITE**, C).
- **Empty state.** "Nenhuma notificação com esses filtros" / "Nenhuma notificação neste período", "Limpar filtros"; error "Erro ao carregar notificações. Tente novamente."
- **Items per page.** "Itens por página".
- **Nav gate.** `notification:read` (page) / `notification:menu` (menu, for the `attendant` role only).

---

## 4. `/perfil` and `/onboarding`

- **`/perfil`** (C, `perfil`). Title "Meu perfil" / "Atualize seu WhatsApp. Nome, e-mail, cargo e área de atuação são apenas leitura."
  - Sections: "Dados pessoais" (Nome, E-mail, "Nível de permissão"), "Contato" ("WhatsApp"), "Cargo e atuação" ("Cargo / Atribuição", "Área de atuação").
  - Field `phone` zod: `trim().refine(valid BR phone)` → "Informe um WhatsApp válido com DDD." Placeholder "(11) 99999-9999".
  - Save: `PATCH /auth/users/me/profile {phone}` (`updateProfilePhone`). Error fallback "Não foi possível salvar as alterações."
  - Another `PATCH /auth/profile {name}` exists (`updateProfile`; optimistic name update; caller I = layout "Editar perfil").
- **`/onboarding`** (C, `7427`). 3 steps, title "Complete seu cadastro na Casa da Lais".
  1. "Qual é o seu WhatsApp?" → `phone`. Zod: `min(1,"WhatsApp é obrigatório").refine(valid,"Informe um WhatsApp válido com DDD")`.
  2. "Em quais áreas você atua?" → `workAreas[]` (`min(1,"Selecione pelo menos uma área de atuação")`). Options: `sales` "Venda de imóveis", `rental` "Locação de imóveis", `capture` "Captação de imóveis", `rental_admin` "Administração de aluguéis", `finance` "Financeiro", `people` "Gestão de pessoas", `marketing` "Marketing". Plus "Não tenho certeza/Nenhum se encaixa bem" → `workAreasOther` (custom "Descreva sua área de atuação"; placeholder "Jurídico, T.I., etc.").
  3. "Qual é a sua função principal na empresa?" → `jobRoles[]` (`min(1,"Selecione pelo menos um cargo")`). Options: `owner_partner` "Sou dono ou sócio", `team_manager` "Sou gestor de equipe", `operation_start` "Atuo no início da operação", `operation_end` "Atuo no final da operação", `realtor` "Sou corretor de imóveis", `comms_marketing` "Atuo com comunicação e marketing".
  - Submit: `POST /auth/users/me/onboarding {phone,jobRoles,workAreas,workAreasOther?}` → `/onboarding/sucesso` ("Obrigado pelas informações"; auto-redirect, "Ir para a Casa da Lais"). If the server returns "invalid phone number" → "Número de WhatsApp inválido. Verifique o DDD e tente novamente."

---

## 5. Onboarding flows and `/checklist`

- **Endpoints** (C, `layout` 21058: `let r="/web"`):
  - `GET /web/flows/:flowSlug/onboarding-progress` → `{totalSteps,completedSteps,steps:[{stepSlug,completed}],…}` (key `flow.onboardingProgress(slug)`).
  - `POST /web/flows/:flowSlug/steps/:stepSlug/complete {}` (**WRITE**).
- **Flows and steps** (C, `checklist`/`chats`/`leads`/`acessos`/`9934`):

| flowSlug | card title | steps (stepSlug → where it is completed) |
|---|---|---|
| `add-team` | "Adicione sua equipe" (2 steps) | `go-acess` → auto-completed on opening `/acessos` (C, `2800`: `ex({flowSlug:"add-team",stepSlug:"go-acess"})`); `add-users` → after creating a user (I) |
| `chat-control` | "Assuma o controle de conversas da Lais" (4) | `open-chat` (onChatOpened), `stop-chat` (onChatSuspended = "Pausar a Lais"), `send-message` (onMessageSent), `reactive-chat` (onChatResumed). All fire from `/chats` with the test lead (`userTestPhone`) (C, `chats`) |
| `connect-origins` | "Informe mais canais para a Lais atender melhor" (0 steps; completed by saving channels) | channel picker (see below) |
| `reachout-leads` | "Recupere leads antigos com o Remarketing" (3) | `go-leads` (open Disparos em massa), `select-lead`, `send-reachout` ("Criar disparo"). `/leads` Bubble posts `LEADS_BANNER_NEXT_STEP` / `LEADS_BANNER_RESET` / `LEADS_BANNER_HIDE` |

- **Page copy.** "Primeiros passos" / "Um guia prático para conhecer a Lais. Configure, explore e acompanhe os resultados acontecendo em poucos cliques." Completion: "Parabéns! Você deu os primeiros passos com a Casa da Lais." Content cards: Projeto Especialista, podcast, blog (actions `completed_*`).
- **Channels (`connect-origins`).**
  - `GET /web/checklist/channels-status` → `data.channels[]{id,displayName,icon,color,status,type}` (key `checklist.channelStatus()`).
  - Status → visual: `configured`/`configured_ocl` → preSelect "Pré-selecionado"; `receiving_leads` → "Recebeu leads recentemente" ("…nos últimos 15 dias"); `informed`/`added`/`not_connected` → "Adicionado nos Primeiros passos".
  - UI: "Canais já sinalizados:", search "Buscar canais de imóveis...", "Não informar agora", "Confirmar canais".
  - Save: `POST /web/checklist/channels {leadOriginIDs:[…]}` (**WRITE**).
- **Test lead (`/creation-user-test`, `9934`).**
  - `GET /web/test-users`, `POST /web/test-users`, `DELETE /web/test-users/:id`.
  - Swap form: "Nome do lead teste" (`name`), "Número de WhatsApp do lead teste" (`phone`).
  - Create body seen: `{name}` and `{phone}` (separate `mutateAsync` calls; full body I).
  - Errors: "Falha ao criar lead de teste" / "Falha ao carregar leads de teste".
  - **SEND risk (I).** Creating a test user probably makes the Lais message that number.
- **Gate.** `/checklist` = `page:all-roles`. Flag `checklist` true → exempt → redirect `/`. A sidebar "Primeiros passos" icon is shown while flows are incomplete.

---

## 6. `/developments`

- **Flag.** `new-development-page-front` → native page. Otherwise `BubbleIframePage{bubblePath:"developments",title:"Empreendimentos"}` (C).
- **Page.** "Empreendimentos" / "Adicione e gerencie empreendimentos." Nav permission `development:read`.
- **List.** `GET /web/properties/developments?<filters>`. Filters: `search` ("Nome ou código do empreendimento"), `status` (`active` "Ativo" / `inactive` "Inativo").
  - Card shows name, price "Mín./Méd./Máx." or "Preço sob consulta", address.
  - Card menu: "Copiar link", "Ver no site", "Editar".
  - Empty: "Nenhum empreendimento encontrado".
- **Detail drawer.** "Detalhes do empreendimento": Endereço, Preço, Código, Link, Descrição.
  - Active switch: "O <nome> está ativo?" / "A Lais poderá oferecer este empreendimento aos seus leads." → `PATCH /web/developments/:id {status}` (I field).
- **Create wizard** (5 steps: "Novo Empreendimento", "Localização", "Descrição", "Imagens", "Resumo").
  - Zod: `name` `min(1,"Nome é obrigatório")`; `description` `min(1,"Descrição é obrigatória")`; the rest optional strings: `avgPrice`, `minPrice`, `maxPrice`, `clientListingId` ("Código", e.g. VM-001), `link` ("Site"), `state` (27 UFs), `city`, `neighborhood`, `street`, `lat`, `lng`, `images` (File[], up to 9), `existingImages`.
  - Address search uses `/api/geocoding/autocomplete?input=` and `/api/geocoding/geocode?address=` (Next proxies to Google).
  - Payload (C): `POST /web/developments {name,description,avgPrice?,minPrice?,maxPrice?,clientListingId?,link?,city?,state?,neighborhood?,street?,images?,location?:{lat,lon}}`. Images are converted client-side (`d(e)`, likely data URLs; I).
  - Edit: `PATCH /web/developments/:id` (tabs Identificação / Descrição / Localização / Imagens). "Sair da edição?" guard.
- **Bulk import.**
  - Copy: "Importar empreendimentos" / "Envie um arquivo CSV ou XLSX…" / "Até 2 MB e 150 linhas" (`maxSize:2097152`).
  - Call: `POST /web/developments/bulk` multipart `file` (via raw `GO` fetch).
  - Then `GET /web/developments/bulk-imports` (history: `fileName`, `processedCount`/`totalCount`, status `pending|processing|completed|failed`) and `GET /web/developments/bulk-imports/:id/status`. Polling uses `refetchInterval`.
  - "Existe uma importação em andamento. Aguarde a conclusão."
- **Errors.** `DEVELOPMENT_001…009`, `AGENCY_006` map (see enums: e.g. `DEVELOPMENT_003` "Máximo de 9 imagens por empreendimento.").

---

## 7. Reports

- **`/avaliacoes`** (perm `report-google-review:read`).
  - Call: `GET /web/agency/google-reviews/dashboard` → `{placeId,currentRating,totalReviews,ratingDistribution[{stars,count,percent}],recentReviews[{authorName,rating,text,publishTime}],reviewRequestsThisMonth,reviewsThisMonth}` (C field accesses).
  - Copy: "A Lais está construindo sua reputação" ("pedidos enviados" / "novas avaliações"), "Distribuição de avaliações por nota", "Últimas avaliações", "Avaliação sem comentário". External link `search.google.com/local/reviews?placeid=`. Empty: "Nenhuma avaliação por aqui".
- **`/atendimento-administrativo`** (nav `requiresAdministrative`).
  - Title "Atendimento administrativo" / "Atenda e resolva casos com inquilinos e proprietários de forma simples e automatizada."
  - Calls (all with `?month&year`; keys `volume(m,y)`, `occurrenceRanking`, `conversationResolution`):

    | Call | Response fields | UI |
    |---|---|---|
    | `GET /web/agency/charts/administrative-report/volume` | `{summary:{conversations,bankslips,occurrences},daily[…],level}` | "Visão geral" tiles "Conversas administrativas", "Boletos enviados", "Ocorrências geradas"; series selector Conversas/Boletos/Ocorrências; table "Dia" |
    | `…/conversation-resolution` | `resolvedByLais`, `forwardedToErp` | "Resolvida pela Lais" / "Encaminhada ao time"; table Tipo/Conversas/Participação |
    | `…/occurrence-ranking` | `categories[{label,total}]` | table "Categoria" |

    - `level==="bankslip_and_occurrence"` enables occurrences. Otherwise: "Sua imobiliária ainda não tem o registro de ocorrências integrado ao ERP…" + "Sinalize interesse na integração".
  - Click-through tracks `administrative_report_conversations_to_leads` (→ leads filtered).
  - Empty: "Nenhum atendimento neste período".
- **`/relatorio-v2`** (perm `report-neighborhood:read`, blocked for `developer` agencies).
  - If flag `new-relatorio-view` → native `RelatoriosV3PageClient`; else Bubble `relatorio-v2` with params `month`, `year`.
- **`/relatorio-v3`** (always native). Same content.
  - Call: `GET /web/report?date=YYYY-MM-01` (key `report(date)`) → `metadata.report.{rentSection,buySection}`, each with:
    - `topNeighborhoods[]{neighborhood,leadCount,median,mostSearchedType,mostSearchedTypePct,bedroomCount,topProperties}`
    - `topHotProperties[]{clientListingID,link,propertyType,priceBuy|priceRent,leads,shelf}`
    - `topPropertyTypes[]{type,…}` (C field accesses; nesting I).
  - UI: "Relatório" / "Confira dados sobre as preferências dos seus leads e otimize suas campanhas e captações."; tabs "Bairros" / "Imóveis"; transaction Aluguel / Venda (only sections with data); "Top 10 bairros", "Desempenho por bairro", "Top 10 imóveis" (cols Ranking, Imóvel, Tipo do imóvel, Preço (R$), Leads, Prateleira), "Top tipo de imóveis".
  - Export: "Download SVG/PNG/CSV" (CSV `Bairro,Leads`). Empty: "Sem bairros neste período.".
- **`/performance`** (nav `allowedAgencyTypes:["developer"]`, perm `report-performance:read`).
  - Bubble `performance`, enabled only when `agency.type==="developer"`.
  - Params `start_date`, `end_date` (default month start → now), `origins`, `campaigns`, `ads_ids`. Bubble `NAVIGATE` messages sync the URL.

---

## 8. Misc routes

- **`/whats-new`** (flag `whats-new-page`, perm `whats-new:read`).
  - Call: `GET /web/whats-new?limit=20&offset=N` (infinite) → `{releases|items[{id,title,description,imageUrl,publishedAt,sections,ctaText,linkUrl,isExternal}],pagination{limit,offset,total}}`.
  - UI: "Novidades", "NOVIDADE", "Depois". Banner actions `whats_new_banner_{see_news,dismiss,snooze}`. Header "Novidades" link hidden for attendants.
- **`/trainings_page`** (perm `lais-guide:read`). "Guia da Lais" / "Aprenda a usar a Lais para vender mais e operar com menos esforço."
  - Static Vimeo-based track ("Trilha de conhecimento"); groups "Boas-vindas", "Introdução à Casa da Lais", "Faça mais com a Casa da Lais".
  - Lesson titles: "Configure acessos da equipe", "Configure e personalize sua Lais", "Gerencie seus leads", "Gerencie todas suas visitas…", "Analise seus resultados mensais", "Consulte pagamentos e plano", "Live: Página de Conversas", "Pré-agendamento de visitas (aba Leads)", "Gestão de prateleira de imóveis (aba Proprietários)", "Cadastro de empreendimentos (aba Empreendimentos)", etc.
  - Progress in `localStorage training-progress:<vimeoId>`. No API.
- **`/trainings`** → Bubble `trainings` (fullscreen; param `s`; agency synced into `?agency=`).
- **`/platform`** → Bubble `platform` (fullscreen; param `s`; `BUBBLE_LOGOUT` message → `/`).
- **`/plans`** → Bubble `plans` ("Planos").
- **`/owners`** → Bubble `owners` ("Atualização de imóveis"; params `status,name,number,clientlistingid,startDate,endDate,suggestionId`; perm `property:read`, blocked for developers).
- **`/captacao`** → only the Bubble iframe client modules load (server component; bubblePath not visible client-side, U — likely `captacao`). The nav "Captação" points to the notifications acquisition view instead.
- **`/properties`** (flag `property-page-front`, perm `integrated-property:read`). Native.
  - Title "Imóveis integrados" / "Confira os imóveis a que a Lais tem acesso pelo XML."
  - List: `GET /web/properties/ads?<filters>` (optional `x-agency-id`) → `{ads[{id,clientListingId,title,link,images,street,neighborhood,city,state,type,priceBuy,priceRent,rent,bedrooms,bathrooms,parkingSpaces,area,iptu,location{lat,lon},…}],…}`.
  - "Filtrar prateleira" filters:
    - `transactionType` (`buy` Venda / `rent` Aluguel)
    - `active` (`true` Ativo / `false` Inativo)
    - `bedrooms` 1–5+, `bathrooms` 1–5+, `parkingSpaces` 1–4+
    - `area` "Área mínima (m²)" ("Área não pode ser negativa")
    - `priceMin`/`priceMax` ("Preço mínimo deve ser menor que o máximo")
    - `search` ("Código ou link do imóvel")
  - Views "Grade" / "Mapa" (map bounds → `lat,lon,range` in km; I).
  - Detail: PropertyInfo / Features / Gallery; "Dados enviados à Meta" (`clientListingId`, `syncStatus`, `lastSyncedAt`, `deletedAt`, "Motivos").
  - "Imóveis similares": filters Operação, Preço mín./máx., "Distância" 5/15/30/60 min walk.
  - InterestedLeads table: Nome, Contato, E-mail, Tipo, Operação, Origem, Status, Criado em, Visita.
  - Feed sync: `GET /web/ads/xml/status` (polls every 5 min while `isProcessing`) and `POST /web/ads/xml/sync` (**WRITE**; "Falha ao sincronizar prateleira").
  - Property socket: `wss://eventhub.lastro.services/ws/properties?token=…&agencyId=` event `feed_sync_completed`.
  - Lookup by code: `getAds({search,active:true})`, then `active:false` → "Imóvel não encontrado".
- **`/leads-v3`** → native `LeadsV3` (module 79934 in shared chunk; fork A scope). `/leads` shows it when flag `leads-view` is on (else Bubble `leads`).

---

## 9. Endpoints seen in my scope but NOT in `tools/methods.txt`

| Method | Path | Caller | Class |
|---|---|---|---|
| GET | `/web/permissions` | raw `GO` in layout/2800/9654 (`auth.permissions.chat`) | READ |
| GET | `/web/permissions/teams` | raw `GO` (`auth.permissions.teams`) | READ |
| GET | `/web/report?date=YYYY-MM-01` | raw `GO` in relatorio-v2/v3 | READ |
| POST | `/web/developments/bulk` (multipart `file`) | `bulkImport` via raw `GO` | WRITE |
| POST | `/auth/users` (as **updateUser**: upsert alias) | 7531 `updateUser` | WRITE |
| POST | `/api/intercom {user_id}` → `{hash}` | 2134 | READ-ish (identity hash) |
| GET | `/api/bubble-health` → `{ok}` | 5812 | READ |
| GET | `/api/geocoding/autocomplete?input=` / `/api/geocoding/geocode?address=` | 9654/developments | READ (Google proxy) |
| HEAD | `/favicon.ico?t=` | layout connectivity probe | READ |
| WS | `wss://eventhub.lastro.services/ws/notifications?token&agencyId` (`notification:created`) | 5435/layout | READ (subscribe) |
| WS | `wss://eventhub.lastro.services/ws/properties?token&agencyId` (`feed_sync_completed`) | 9654 | READ (subscribe) |
| link | `https://api.whatsapp.com/send?text=` | notifications share | client link, not API |

Notes:
- The mock seats paths `/seats/summary` and `/seats/availability` lack `/web`. The real client uses `/web/seats/*` (C, `7531` `C="/web/seats"`).
- The `/web/teams/:id/distribution` (PUT) and `/web/teams/:id/roulette` (PUT) services exist, but I found no UI caller (U).
