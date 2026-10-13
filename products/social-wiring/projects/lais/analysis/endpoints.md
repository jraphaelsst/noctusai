# Lais / Lastro BFF — endpoint catalogue (static, from bundle)

Base URL: `https://bff.lastro.services/api/v1` (C 5138 `let t="https://bff.lastro.services/api/v1"` in UrlBuilder). Relative paths below are appended to it.
Every BFF call gets `Authorization: Bearer <keycloak access token>` and `x-agency-id: <selected REA id>` unless `skipAgencyId` (C 5138 `injectAuthHeaders`).
Client retries 3x with exp. backoff (1s,2s,4s) on HTTP>=500 or 429 — for ALL verbs incl. POST (C 5138 `DEFAULT_RETRY_CONFIG={retries:3,delay:1e3,backoff:2}`); only catalog product-set writes pass `retries:0`. => a live POST that 5xx's may be replayed.
HTTP 402 with code `premium_module_required` => `window.location.replace("/add-ons/pro")` except on /add-ons/pro, /acessos and for /agency/details, /subscription/premium (C 5138).

Safety classes: **READ** GET no side effect · **WRITE** create/update/delete · **SEND** sends WhatsApp/broadcast, schedules outreach, or changes AI-vs-human answering · **SIDE-EFFECT-GET** (none found) · **AUTH** auth/session flows.
Counts: AUTH=8, READ=120, SEND=17, WRITE=85, total=230.

Columns: method · path · caller · request · response · routes (page chunks that load the defining chunk; `(layout)` = global shell) · ev (C code / I inferred / C(mock) only in MSW) · mock = MSW handler exists.

## chats/conversations

| safety | method | path | caller | request | response | routes | ev | mock | note |
|---|---|---|---|---|---|---|---|---|---|
| READ | GET | `/web/chats/agency` | chatService.getChats (3b4451b3 `er`, BASE_PATH=/web/chats) | query: limit(15) page operation suspended leadStatus creditAnalysisStatus teamIds(csv) userAssigneds(csv; '' = unassigned) assignedToMe archived tags(csv) withoutTags pinned | data.chats[], data.pagination{total,nextPage} | — | C |  |  |
| READ | GET | `/web/chats/agency (pinned=true&limit=5)` | chatService.getPinnedChats | query: pinned=true limit=5 | data.chats[], data.pagination.total | — | C |  |  |
| READ | GET | `/web/chats/agency/search` | chatService.searchChats / chatsService.searchAgencyChats | query: searchText searchIn(csv) limit page operation suspended leadStatus creditAnalysisStatus assignedToMe archived | data.chats[0] = {data:[],meta:{total}} (facet shape) | (layout), /chats, /history, /visits | C |  |  |
| READ | GET | `/web/chats/agency/validate-phone` | chatService.validatePhone | query: phoneNumber | data (validation result; shape U) | — | C |  |  |
| READ | GET | `/web/chats/:id` | chatService.getChatById / chatsService.getChatById | optional request opts | data = Chat | (layout), /chats, /history, /visits | C | y |  |
| READ | GET | `/web/chats/:id?withFeedback=true` | chatService.getChatWithFeedback |  | data = Chat + feedback | — | C | y |  |
| READ | GET | `/web/chats/:id/agency` | chatsService.getChatAgency (skipAgencyId:true) | no x-agency-id header | data = agency owning chat | (layout), /chats, /history, /visits | C |  |  |
| **SEND** | PATCH | `/web/chats/:id/suspend` | chatService.suspendChat | {suspended:boolean} |  | — | C |  | C: AI on/off switch. suspended=true -> 'Atendimento manual' (Lais paused); false -> 'Lais atendendo'. UI says AI auto-resumes after 5 days w/o messages |
| WRITE | PATCH | `/web/chats/:id` | chatService.updateChatStatus | {suspended?,unread?,archived?} (at least one) |  | — | C | y |  |
| WRITE | PATCH | `/web/chats/:id/pin` | chatService.pinChat/unpinChat | {pinned:boolean} |  | — | C |  |  |
| WRITE | POST | `/web/chats/:id/feedback` | chatService.sendFeedback | feedback body (like/dislike + comment; see domain-model) |  | — | C |  |  |
| READ | GET | `/web/chats/:id/credit-analyses` | chatService.getCreditAnalyses |  | data[] CreditAnalysis | (layout), /chats, /history, /visits | C |  |  |
| READ | GET | `/web/chats/:id/interactions` | chatService.getChatInteractions |  | data[] Interaction | — | C |  |  |
| READ | GET | `/web/chats/:id/messages` | messageService.getMessages (t9) | query: page limit(25) order_by=created_at order_desc=true | data{chat, messages[], pagination{nextPage}} | — | C |  |  |
| **SEND** | POST | `/web/chats/:id/messages/human` | messageService.sendMessage | message body (text/media ref; routes.md Part A) |  | — | C |  |  |
| **SEND** | POST | `/web/chats/:id/media` | messageService.uploadMedia (chat pkg G(); timeout 120s, video 340s w/ retries) | multipart: file, voice='true'? | media ref | — | C |  | I: upload precedes a human send; treat as SEND-adjacent |
| READ | GET | `/web/chats/:id/messages/template/draft` | templateService.getTemplateDraft | query: templateId | data = rendered draft | — | C |  |  |
| READ | GET | `/web/chats/new/messages/template/draft` | templateService.getNewConversationTemplateDraft | query: templateId | data | — | C |  |  |
| **SEND** | POST | `/web/chats/:id/messages/human/template` | templateService.sendTemplateMessage | template send body |  | — | C |  |  |
| **SEND** | POST | `/web/chats/new/messages/human/template` | templateService.sendNewConversationTemplate | new-conversation template body (phone + template + params) |  | — | C |  |  |
| **SEND** | POST | `/web/chats/:id/user-assignment` | chatAssignService.assignChat / userAssignService.assignUser | {userId, reason?, userName?} (userId '' = unassign) |  | (layout), /acessos, /add-ons/administrative, /add-ons/pro, /add-ons/smart-campaigns, /catalogs, /chats, /credit-analysis, /history, /lead… | C |  | changes who answers the chat (human attendant) |
| **SEND** | POST | `/web/chats/:id/team-assignment` | chatAssignService.assignTeam | {teamId, reason?} |  | — | C |  |  |
| **SEND** | POST | `/web/chats/:id/transfer` | transferService.transferChat (B) | {toUserId?, toTeamId?, reason?} | data{transferId,chatId,toUserId,toTeamId,origin} | (layout), /acessos, /add-ons/administrative, /add-ons/pro, /add-ons/smart-campaigns, /catalogs, /chats, /credit-analysis, /history, /lead… | C | y |  |
| READ | GET | `/web/chats/:id/transfers` | transferService.getTransferHistory | query: page limit | data[] Transfer | (layout), /acessos, /add-ons/administrative, /add-ons/pro, /add-ons/smart-campaigns, /catalogs, /chats, /credit-analysis, /history, /lead… | C | y |  |
| **SEND** | POST | `/web/chats/:id/self-assign` | transferService.selfAssign | (no body) | data{chatId,userAssigned,teamAssigned} | (layout), /acessos, /add-ons/administrative, /add-ons/pro, /add-ons/smart-campaigns, /catalogs, /chats, /credit-analysis, /history, /lead… | C | y |  |
| READ | GET | `/web/chats/:id/visits` | chatVisits.getChatVisits |  | data.visits[] | — | C |  |  |
| WRITE | POST | `/web/chats/:id/kanban-move` | kanbanService.moveChat | move body (columnId, position; I) | data | — | C |  |  |
| READ | GET | `/web/chats/:id/tags` | tagService.getChatTags |  | data[] Tag | — | C |  |  |
| WRITE | PUT | `/web/chats/:id/tags` | tagService.saveChatTags | {tagIds:[]} |  | — | C |  |  |
| READ | GET | `/web/chats/:id/internals` | notesService.listNotes |  | data[]{entry,todos} -> flattened | — | C |  |  |
| WRITE | POST | `/web/chats/:id/internals` | notesService.createNote | note body | data | — | C |  |  |
| WRITE | POST | `/web/chats/:id/internals/audio/process` | notesService.processAudio | multipart file=audio.webm | data (transcription/structured note; I) | — | C |  |  |
| WRITE | DELETE | `/web/chats/:id/internals/:noteId` | notesService.deleteNote |  |  | — | C |  |  |
| WRITE | PATCH | `/web/chats/:id/internals/:noteId/todos/:todoId/complete` | notesService.completeTodo |  | data | — | C |  |  |
| READ | GET | `/web/kanban/columns` | kanbanService.listColumns |  | data[] Column | — | C |  |  |
| WRITE | POST | `/web/kanban/columns` | kanbanService.addColumn | column body | data | — | C |  |  |
| WRITE | DELETE | `/web/kanban/columns/:id` | kanbanService.removeColumn |  |  | — | C |  |  |
| WRITE | PATCH | `/web/kanban/columns/reorder` | kanbanService.reorderColumns | order body | data[] | — | C |  |  |
| READ | GET | `/web/tags` | tagService.getTags |  | data[] Tag | — | C |  |  |
| WRITE | POST | `/web/tags` | tagService.createTag | tag body | data | — | C |  |  |
| WRITE | PATCH | `/web/tags/:id` | tagService.updateTag | tag body | data | — | C |  |  |
| WRITE | DELETE | `/web/tags/:id` | tagService.deleteTag |  |  | — | C |  |  |
| WRITE | POST | `/web/users/block` | leadService.blockLeadNumber | block body {reason:int, reasonDetails, phoneNumber?} (schema sp) |  | /add-ons/smart-campaigns, /broadcasts, /catalogs, /chats, /credit-analysis, /history, /leads, /leads-v3, /properties, /relatorio-v2, /rel… | C |  |  |
| WRITE | DELETE | `/web/users/unblock` | leadService.unblockLeadNumber | query: phoneNumber |  | /add-ons/smart-campaigns, /broadcasts, /catalogs, /chats, /credit-analysis, /history, /leads, /leads-v3, /properties, /relatorio-v2, /rel… | C |  |  |
| READ | GET | `/auth/users?skipInternal=true[&managedByMe=true]` | assignableUsers.getAssignableUsers | query: skipInternal managedByMe | data[]{id,name,email} | (layout), /acessos, /add-ons/administrative, /add-ons/pro, /add-ons/smart-campaigns, /catalogs, /chats, /credit-analysis, /history, /lead… | C | y |  |
| READ | GET | `/web/teams[?managedByMe=true]` | teamsLite.getTeams (chat module) | query: managedByMe | data.teams[]{id,name} | — | C |  |  |

## templates (WhatsApp/Meta)

| safety | method | path | caller | request | response | routes | ev | mock | note |
|---|---|---|---|---|---|---|---|---|---|
| READ | GET | `/web/templates/available` | templateService.getAvailableTemplates | query: chatId? | data[] Template | /broadcasts, /configs_templates | C |  |  |
| READ | GET | `/web/templates/categories` | templateService.getCategories |  | data.categories | /configs_templates | C |  |  |
| READ | GET | `/web/templates/params` | templateService.getParams |  | data.params | /configs_templates | C |  |  |
| WRITE | POST | `/web/templates` | templateService.createCustomTemplate / createTemplate | template body (routes.md Part B) | data | /configs_templates | C |  | I: likely submits template to Meta for approval |
| WRITE | DELETE | `/web/templates/:id` | templateService.deleteTemplate |  |  | /configs_templates | C |  |  |

## leads

| safety | method | path | caller | request | response | routes | ev | mock | note |
|---|---|---|---|---|---|---|---|---|---|
| READ | GET | `/web/leads/` | leadsService.listLeads (6989) | query: page limit view phase distinctByPhone suggestionId order_by order_desc + filter fields (i(e): name/number/email/clientListingId/chatId ...) | data (leads list; routes.md Part A) | /add-ons/smart-campaigns, /broadcasts, /catalogs, /chats, /credit-analysis, /history, /leads, /leads-v3, /properties, /relatorio-v2, /rel… | C | y |  |
| READ | GET | `/web/leads/origins` | leadsService.listLeadOrigins |  | data[] | /add-ons/smart-campaigns, /broadcasts, /catalogs, /chats, /credit-analysis, /history, /leads, /leads-v3, /properties, /relatorio-v2, /rel… | C |  |  |
| READ | GET | `/web/leads/campaigns` | leadsService.listLeadCampaigns |  | data[] | /add-ons/smart-campaigns, /broadcasts, /catalogs, /chats, /credit-analysis, /history, /leads, /leads-v3, /properties, /relatorio-v2, /rel… | C |  |  |
| WRITE | POST | `/web/leads/:id/enhance` | leadsService.enhanceLead | (no body) | 202 Accepted -> {accepted:true} else data=lead | /add-ons/smart-campaigns, /broadcasts, /catalogs, /chats, /credit-analysis, /history, /leads, /leads-v3, /properties, /relatorio-v2, /rel… | C | y | I: 'enhance' = qualify + send to CRM (mock: enhanced:true, sentToCRM:true) |
| WRITE | POST | `/web/leads/batch-enhance` | leadsService.batchEnhanceLeads | {leadIds[]} \| {selectAll:true, filter, excludedLeadIds[]} (max 60) | data.summary{enhanced,skipped,failed} | /add-ons/smart-campaigns, /broadcasts, /catalogs, /chats, /credit-analysis, /history, /leads, /leads-v3, /properties, /relatorio-v2, /rel… | C |  | pushes leads to agency CRM (external side effect) |
| WRITE | PATCH | `/web/leads/:id/enhance/force` | leadService.forceEnhance | (no body) | data{leadId,enhanced,sentToCRM,timestamp} (mock) | /add-ons/smart-campaigns, /broadcasts, /catalogs, /chats, /credit-analysis, /history, /leads, /leads-v3, /properties, /relatorio-v2, /rel… | C | y | pushes lead to agency CRM (external side effect) |
| WRITE | POST | `/web/leads/export` | leadsService.startLeadExport | query: filters; body: export options | data.jobId | /add-ons/smart-campaigns, /broadcasts, /catalogs, /chats, /credit-analysis, /history, /leads, /leads-v3, /properties, /relatorio-v2, /rel… | C |  |  |
| READ | GET | `/web/leads/export/:jobId` | leadsService.getLeadExportStatus |  | data (job status) | /add-ons/smart-campaigns, /broadcasts, /catalogs, /chats, /credit-analysis, /history, /leads, /leads-v3, /properties, /relatorio-v2, /rel… | C |  |  |
| READ | GET | `/web/leads/export/:jobId/download` | leadsService.downloadLeadExport | parseAs blob | file blob | /add-ons/smart-campaigns, /broadcasts, /catalogs, /chats, /credit-analysis, /history, /leads, /leads-v3, /properties, /relatorio-v2, /rel… | C |  |  |

## visits

| safety | method | path | caller | request | response | routes | ev | mock | note |
|---|---|---|---|---|---|---|---|---|---|
| READ | GET | `/web/visits` | visitsService.getVisits | query: view date transactionType clientListingIds status leadIds | data | /add-ons/smart-campaigns, /catalogs, /chats, /configs_qualification, /credit-analysis, /history, /leads, /leads-v3, /properties, /relator… | C |  |  |
| READ | GET | `/web/visits/:id` | visitsService.getVisitById/getVisitDetails |  | data Visit | /add-ons/smart-campaigns, /catalogs, /chats, /configs_qualification, /credit-analysis, /history, /leads, /leads-v3, /properties, /relator… | C |  |  |
| READ | GET | `/web/visits/config` | visitsService.getConfig |  | data visit config | /add-ons/smart-campaigns, /catalogs, /chats, /configs_qualification, /credit-analysis, /history, /leads, /leads-v3, /properties, /relator… | C |  |  |
| WRITE | POST | `/web/visits` | visitsService.createVisit | visit body | data | /add-ons/smart-campaigns, /catalogs, /chats, /configs_qualification, /credit-analysis, /history, /leads, /leads-v3, /properties, /relator… | C |  | no call site found (dead code, I) |
| WRITE | PATCH | `/web/visits/:id` | visitsService.updateVisit | visit patch | data | /add-ons/smart-campaigns, /catalogs, /chats, /configs_qualification, /credit-analysis, /history, /leads, /leads-v3, /properties, /relator… | C |  | no call site found (I) |
| **SEND** | PUT | `/web/visits/:id` | visitsService.updateVisitGroup | {visitId\|alternativeDateTime, confirmedByName, confirmedByEmail} (reschedule) \| {propertyId, propertyType} (associate property) | data | /add-ons/smart-campaigns, /catalogs, /chats, /configs_qualification, /credit-analysis, /history, /leads, /leads-v3, /properties, /relator… | C |  | reschedule: with flag visit_action_notifications Lais WhatsApps the lead |
| WRITE | DELETE | `/web/visits/:id` | visitsService.deleteVisit |  |  | /add-ons/smart-campaigns, /catalogs, /chats, /configs_qualification, /credit-analysis, /history, /leads, /leads-v3, /properties, /relator… | C |  |  |
| **SEND** | POST | `/web/visits/:id/confirm` | visitsService.confirmVisit | {visitId\|alternativeDateTime, confirmedByName, confirmedByEmail} | data | /add-ons/smart-campaigns, /catalogs, /chats, /configs_qualification, /credit-analysis, /history, /leads, /leads-v3, /properties, /relator… | C |  | with flag visit_action_notifications Lais WhatsApps the lead |
| **SEND** | POST | `/web/visits/:id/cancel` | visitsService.cancelVisit | {} |  | /add-ons/smart-campaigns, /catalogs, /chats, /configs_qualification, /credit-analysis, /history, /leads, /leads-v3, /properties, /relator… | C |  |  |
| READ | GET | `/web/agency/settings/visits` | visitSettingsService.getSettings (1647) |  | data VisitSettings (mock: mode unified, general{...}) | /configs_visits, /configs_visits_embed | C | y |  |
| WRITE | PUT | `/web/agency/settings/visits` | visitSettingsService.upsertSettings | VisitSettings | data | /configs_visits, /configs_visits_embed | C | y |  |

## properties/captacao/developments

| safety | method | path | caller | request | response | routes | ev | mock | note |
|---|---|---|---|---|---|---|---|---|---|
| READ | GET | `/web/properties/ads` | adsService.searchAds/getAds | query: search \| arbitrary filters; header x-agency-id override | data | /add-ons/smart-campaigns, /catalogs, /chats, /credit-analysis, /history, /leads, /leads-v3, /properties, /relatorio-v2, /relatorio-v3, /s… | C |  |  |
| READ | GET | `/web/ads/xml/status` | adsService.getFeedSyncStatus |  | data feed sync status | /add-ons/smart-campaigns, /catalogs, /chats, /credit-analysis, /history, /leads, /leads-v3, /properties, /relatorio-v2, /relatorio-v3, /s… | C |  |  |
| WRITE | POST | `/web/ads/xml/sync` | adsService.triggerFeedSync | (no body) |  | /add-ons/smart-campaigns, /catalogs, /chats, /credit-analysis, /history, /leads, /leads-v3, /properties, /relatorio-v2, /relatorio-v3, /s… | C |  | triggers XML feed re-import; completion via ws feed_sync_completed |
| READ | GET | `/web/properties/developments` | developmentsService.getDevelopments | query: filters | data | /developments | C |  |  |
| WRITE | POST | `/web/developments` | developmentsService.createDevelopment | development body | data | /developments | C |  |  |
| WRITE | PATCH | `/web/developments/:id` | developmentsService.updateDevelopment | development patch | data | /developments | C |  |  |
| WRITE | POST | `/web/developments/bulk` | developmentsService.bulkImport (GO direct) | multipart file | data | /developments | C |  |  |
| READ | GET | `/web/developments/bulk-imports` | developmentsService.listBulkImports |  | data[] | /developments | C |  |  |
| READ | GET | `/web/developments/bulk-imports/:id/status` | developmentsService.getBulkImportStatus |  | data | /developments | C |  |  |

## broadcasts/campaigns

| safety | method | path | caller | request | response | routes | ev | mock | note |
|---|---|---|---|---|---|---|---|---|---|
| READ | GET | `/web/broadcasts` | broadcastService.listBroadcasts | query: type status(csv) limit offset | data{total,limit,offset,items[]} | /broadcasts | C | y |  |
| READ | GET | `/web/broadcasts/:id` | broadcastService.getBroadcast |  | data Broadcast (detail) | /broadcasts | C | y |  |
| READ | GET | `/web/broadcasts/:id/targets` | broadcastService.listTargets | query: limit offset | data{total,limit,offset,targets[]} | /broadcasts | C | y |  |
| READ | GET | `/web/broadcasts/property-owners` | broadcastService.listPropertyOwners | query: search limit offset | data{total,limit,offset,items[]{id,name,phoneNumber}} | /broadcasts | C | y |  |
| READ | GET | `/web/broadcasts/segments` | broadcastService.listSegments | query: type | data | /broadcasts | C |  |  |
| READ | GET | `/web/broadcasts/available-dates` | broadcastService.listAvailableDates |  | data.dates[]{day,available} | /broadcasts | C | y |  |
| READ | GET | `/web/broadcasts/plan` | broadcastService.getAgencyPlan |  | data (plan limits) | /broadcasts | C |  |  |
| **SEND** | POST | `/web/broadcasts` | broadcastService.createBroadcast | {type,name,createAsDraft,scheduleDate,templateType\|templateRef,templateCustom?,propertyLink?,leads[]\|propertyOwners[],wizardStep} | data{id,type,status,scheduleDate,warnings} | /broadcasts | C | y | createAsDraft=false -> status confirmed (scheduled send) |
| **SEND** | POST | `/web/broadcasts/file` | broadcastService.createBroadcastFromFile | multipart: file type createAsDraft name? scheduleDate? scheduledAt? templateRef? templateCustom? templateType? propertyLink? | data{id,totalValid,warnings,status} | /broadcasts | C | y |  |
| WRITE | POST | `/web/broadcasts/validate-file` | broadcastService.validateBroadcastFile | multipart: file type | data (validation) | /broadcasts | C |  | I: pure validation, no persistence (U) |
| WRITE | POST | `/web/broadcasts/:id/file` | broadcastService.replaceBroadcastFile | multipart file | data{totalValid,warnings} | /broadcasts | C | y |  |
| **SEND** | POST | `/web/broadcasts/:id/confirm-pending` | broadcastService.confirmBroadcast | {} |  | /broadcasts | C | y | draft -> confirmed (scheduled) |
| **SEND** | PATCH | `/web/broadcasts/:id/schedule` | broadcastService.updateSchedule | {scheduledAt} |  | /broadcasts | C | y |  |
| WRITE | PUT | `/web/broadcasts/:id` | broadcastService.updateBroadcast | draft body | data | /broadcasts | C | y |  |
| WRITE | DELETE | `/web/broadcasts/:id` | broadcastService.cancelBroadcast |  |  | /broadcasts | C | y | soft cancel -> status canceled |
| WRITE | DELETE | `/web/broadcasts/:id/permanent` | (mock only; no service caller found) |  | message | — | C(mock) | y |  |
| READ | GET | `/web/agency/smart-suggestions` | smartSuggestionService.getSmartSuggestions |  | list | (layout), /broadcasts | C |  |  |
| READ | GET | `/web/agency/smart-suggestions/:id` | smartSuggestionService.getSmartSuggestionById |  | data | (layout), /broadcasts | C |  |  |
| WRITE | POST | `/web/agency/smart-suggestions/:id/cooldown` | smartSuggestionService.sendCooldown | {action} |  | (layout), /broadcasts | C |  |  |

## smart-campaigns/remarketing/meta-catalog

| safety | method | path | caller | request | response | routes | ev | mock | note |
|---|---|---|---|---|---|---|---|---|---|
| READ | GET | `/web/smart-campaigns/onboarding-state` | smartCampaignsService.getOnboardingState |  | data{state:needs_oauth\|awaiting_configuration\|ready,agencyName,hasPixel,hasToken,hasAdAccount} | (layout), /acessos, /add-ons/administrative, /add-ons/pro, /add-ons/smart-campaigns, /smart-campaigns, /smart-campaigns/remarketing | C | y |  |
| READ | GET | `/web/smart-campaigns/ad-accounts` | smartCampaignsService.getAdAccounts |  | data.adAccounts[]{id,adAccountId,name} | (layout), /acessos, /add-ons/administrative, /add-ons/pro, /add-ons/smart-campaigns, /smart-campaigns, /smart-campaigns/remarketing | C | y |  |
| READ | GET | `/web/smart-campaigns/campaigns` | smartCampaignsService.getCampaigns | query: from to status(csv) adAccountId | data{campaigns[],summary,lastUpdatedAt,syncedAt} | (layout), /acessos, /add-ons/administrative, /add-ons/pro, /add-ons/smart-campaigns, /smart-campaigns, /smart-campaigns/remarketing | C | y |  |
| READ | GET | `/web/smart-campaigns/campaigns/:campaignId/leads` | smartCampaignsService.getCampaignLeads | query: from to page limit search | data{leads[],total,offset,limit} | (layout), /acessos, /add-ons/administrative, /add-ons/pro, /add-ons/smart-campaigns, /smart-campaigns, /smart-campaigns/remarketing | C | y |  |
| READ | GET | `/web/catalog/listings` | catalogService.getListings | query: status search city operation priceMin priceMax limit(<=200) offset | data{listings[],pagination} | /catalogs | C | y |  |
| READ | GET | `/web/catalog/listings/stats` | catalogService.getListingsStats | query: search priceMin priceMax operation city | data{total,byStatus,lastSyncedAt} | /catalogs | C | y |  |
| WRITE | POST | `/web/catalog/listings/include` | catalogService.includeListings | {adIds[]\|selectAll,excludedAdIds[]} + filter query | data{applied,skipped,failed,summary} | /catalogs | C | y | pushes listings to Meta catalog (external side effect) |
| WRITE | POST | `/web/catalog/listings/exclude` | catalogService.excludeListings | same | same | /catalogs | C | y |  |
| WRITE | POST | `/web/catalog/listings/resync` | catalogService.resyncListings | {adIds[]...} | same | /catalogs | C | y |  |
| READ | GET | `/web/catalog/product-sets` | catalogService.getProductSets |  | data.productSets[] | /catalogs | C | y |  |
| WRITE | POST | `/web/catalog/product-sets` | catalogService.createProductSet (retries:0) | {name,color,filter,adAccountId?} | data ProductSet (201) | /catalogs | C | y |  |
| WRITE | PATCH | `/web/catalog/product-sets/:id` | catalogService.updateProductSet | {name,color,filter} | data | /catalogs | C |  |  |
| WRITE | DELETE | `/web/catalog/product-sets/:id` | catalogService.deleteProductSet |  | 204 | /catalogs | C |  |  |

## configs/behavior (AI brain)

| safety | method | path | caller | request | response | routes | ev | mock | note |
|---|---|---|---|---|---|---|---|---|---|
| READ | GET | `/web/agency/settings` | agencyService.getSettings |  | data AgencySettings{allowNotifications,useIptu,allowEnhanceAcquisitionLeads,prefixHumanMessagesWithSenderName,overduePaymentSlipAlertDismissedAt,bankslipOccurrences,disableOnboardingTestLeadStep} | (layout), /, /acessos, /add-ons/administrative, /add-ons/pro, /add-ons/smart-campaigns, /atendimento-administrativo, /broadcasts, /captac… | C | y |  |
| WRITE | POST | `/web/agency/settings` | agencyService.updateSettings | partial AgencySettings (+dismissOverduePaymentSlipAlert) | data | (layout), /, /acessos, /add-ons/administrative, /add-ons/pro, /add-ons/smart-campaigns, /atendimento-administrativo, /broadcasts, /captac… | C | y |  |
| READ | GET | `/web/agency/details` | agencyService.getDetails | header x-agency-id override | data Agency (id,status,modules[],type...) | (layout), /, /acessos, /add-ons/administrative, /add-ons/pro, /add-ons/smart-campaigns, /atendimento-administrativo, /broadcasts, /captac… | C |  |  |
| READ | GET | `/web/agency/access-code` | agencyService.getAccessCode |  | data access code | (layout), /, /acessos, /add-ons/administrative, /add-ons/pro, /add-ons/smart-campaigns, /atendimento-administrativo, /broadcasts, /captac… | C |  |  |
| READ | GET | `/web/audiences/required-informations` | requiredInfoService.getSelected |  | data | /configs, /configs_qualification | C |  |  |
| READ | GET | `/web/audiences/user-profiles` | audienceService.getUserProfiles |  | data[] | /configs, /configs_qualification | C |  |  |
| WRITE | POST | `/web/audiences/user-profiles` | audienceService.createUserProfile | profile body | data | /configs, /configs_qualification | C |  |  |
| WRITE | PATCH | `/web/audiences/user-profiles/:id` | audienceService.updateUserProfile | profile patch |  | /configs, /configs_qualification | C |  |  |
| READ | GET | `/web/reengage/configs` | reengageService.getConfigs |  | data[]{enabled,reengageType:reminder\|final,delayMinutes} | /configs_reengage | C | y |  |
| READ | GET | `/web/reengage/configs/delay-minutes` | reengageService.getDelayOptions | query: reengageType | data[]{label,value} | /configs_reengage | C | y |  |
| WRITE | PUT | `/web/reengage/configs` | reengageService.upsertConfig | {enabled,reengageType,delayMinutes} | data | /configs_reengage | C | y |  |
| READ | GET | `/web/reengage/rules/templates` | reengageService.getTemplates |  | data[]{slug,name,preview} | /configs_reengage | C | y |  |
| READ | GET | `/web/reengage/rules` | reengageService.listRules |  | data[] Rule | /configs_reengage | C | y |  |
| WRITE | POST | `/web/reengage/rules` | reengageService.createRule | {name?,buy,rent} | data Rule | /configs_reengage | C | y |  |
| READ | GET | `/web/reengage/rules/:id` | reengageService.getRule |  | data Rule | /configs_reengage | C | y |  |
| WRITE | PATCH | `/web/reengage/rules/:id` | reengageService.updateRule | {name?,buy?,rent?} | data | /configs_reengage | C | y |  |
| WRITE | POST | `/web/reengage/rules/:id/activate` | reengageService.activateRule | {} | data | /configs_reengage | C | y |  |
| WRITE | POST | `/web/reengage/rules/:id/deactivate` | reengageService.deactivateRule | {} | data | /configs_reengage | C | y |  |
| WRITE | POST | `/web/reengage/rules/:id/attempts` | reengageService.addAttempt | {attemptIndex?,delayValue,delayUnit:days\|...,templateId,enabled} | data Attempt (max 3/rule in mock) | /configs_reengage | C | y |  |
| WRITE | PATCH | `/web/reengage/rules/:id/attempts/:attemptId` | reengageService.updateAttempt | attempt patch | data | /configs_reengage | C | y |  |
| WRITE | DELETE | `/web/reengage/rules/:id/attempts/:attemptId` | reengageService.deleteAttempt |  |  | /configs_reengage | C | y |  |
| WRITE | DELETE | `/web/reengage/rules/:id` | reengageService.deleteRule |  |  | /configs_reengage | C | y |  |

## facebook/meta integration

| safety | method | path | caller | request | response | routes | ev | mock | note |
|---|---|---|---|---|---|---|---|---|---|
| AUTH | POST | `/web/facebook/callback` | facebookService.callback | {code} (OAuth code from facebook dialog v21.0) | data | /configs_meta_integration | C |  |  |
| WRITE | POST | `/web/facebook/connect/finalize` | facebookService.connectFinalize | finalize body (selected pages/ad account; routes.md Part B) |  | /configs_meta_integration | C |  |  |
| READ | GET | `/web/facebook/pages` | facebookService.getPages |  | data[] Page | /configs_meta_integration | C |  |  |
| WRITE | DELETE | `/web/facebook/pages/:pageId` | facebookService.deletePage |  |  | /configs_meta_integration | C |  |  |
| READ | GET | `/web/facebook/forms` | facebookService.getForms | query: pageId? | data[] Form | /configs_meta_integration | C |  |  |
| READ | GET | `/web/facebook/forms/local` | facebookService.getFormsLocal |  | data[] | /configs_meta_integration | C |  |  |
| READ | GET | `/web/facebook/forms/meta` | facebookService.getFormsMeta |  | data[] | /configs_meta_integration | C |  |  |
| WRITE | POST | `/web/facebook/forms` | facebookService.createForm | form body | data | /configs_meta_integration | C |  |  |
| WRITE | PUT | `/web/facebook/forms/:formId/toggle` | facebookService.toggleForm | {active} |  | /configs_meta_integration | C |  |  |
| WRITE | PUT | `/web/facebook/forms/:formId/mapping` | facebookService.updateFormMapping | {mappings} |  | /configs_meta_integration | C |  |  |
| READ | GET | `/web/facebook/forms/:formId/questions` | facebookService.getFormQuestions | query: pageId? | data.questions[] | /configs_meta_integration | C |  |  |

## reports/charts

| safety | method | path | caller | request | response | routes | ev | mock | note |
|---|---|---|---|---|---|---|---|---|---|
| READ | GET | `/web/agency/charts/plan-consumption` | chartsService.getPlanConsumption | query (buildQuery: period) | chart payload | (layout), /, /broadcasts | C |  |  |
| READ | GET | `/web/agency/charts/alerts` | chartsService.getAlerts | query | chart payload | (layout), /, /broadcasts | C |  |  |
| READ | GET | `/web/agency/charts/lead-summary` | chartsService.getLeadSummary | query | chart payload | (layout), /, /broadcasts | C |  |  |
| READ | GET | `/web/agency/charts/leads-by-channel` | chartsService.getLeadsByChannel | category query | chart payload | (layout), /, /broadcasts | C |  |  |
| READ | GET | `/web/agency/charts/lead-status-by-channel` | chartsService.getLeadStatusByChannel | category query | chart payload | (layout), /, /broadcasts | C |  |  |
| READ | GET | `/web/agency/charts/leads-per-hour` | chartsService.getLeadsPerHour | category query | chart payload | (layout), /, /broadcasts | C |  |  |
| READ | GET | `/web/agency/charts/leads-per-weekday` | chartsService.getLeadsPerWeekday | category query | chart payload | (layout), /, /broadcasts | C |  |  |
| READ | GET | `/web/agency/charts/leads-last-six-months` | chartsService.getLeadsLastSixMonths | category query | chart payload | (layout), /, /broadcasts | C |  |  |
| READ | GET | `/web/agency/charts/administrative-report/volume` | adminReportService.getVolume | query: month year | chart payload | /atendimento-administrativo | C |  |  |
| READ | GET | `/web/agency/charts/administrative-report/occurrence-ranking` | adminReportService.getOccurrenceRanking | query: month year | chart payload | /atendimento-administrativo | C |  |  |
| READ | GET | `/web/agency/charts/administrative-report/conversation-resolution` | adminReportService.getConversationResolution | query: month year | chart payload | /atendimento-administrativo | C |  |  |
| READ | GET | `/web/report` | useReport (GO direct) | params: date=yyyy-MM-01 | data.metadata.report{rentSection,buySection} | /relatorio-v2, /relatorio-v3 | C |  |  |
| READ | GET | `/web/credit-analysis/summary` | creditAnalysisService.getSummary | query (month/year) | summary | /credit-analysis | C |  |  |
| READ | GET | `/web/credit-analysis/chart` | creditAnalysisService.getChart | query | chart | /credit-analysis | C |  |  |
| READ | GET | `/web/credit-analysis` | creditAnalysisService.getList | query: month year page limit status | list | /catalogs, /credit-analysis | C |  |  |
| READ | GET | `/web/agency/google-reviews/dashboard` | googleReviewsService.getDashboard |  | dashboard | /avaliacoes | C |  |  |

## finance/billing/add-ons

| safety | method | path | caller | request | response | routes | ev | mock | note |
|---|---|---|---|---|---|---|---|---|---|
| READ | GET | `/web/finance/subscriptions` | financeService.getSubscriptions | query (buildQueryString) | data | (layout), /, /financeiro | C |  |  |
| READ | GET | `/web/finance/consumption` | financeService.getConsumption | query (buildQueryString) | data | (layout), /, /financeiro | C |  |  |
| READ | GET | `/web/finance/billing-account` | financeService.getBillingAccount |  | data | (layout), /, /financeiro | C |  |  |
| READ | GET | `/web/finance/financial-contacts` | financeService.getFinancialContacts |  | data | (layout), /, /financeiro | C |  |  |
| READ | GET | `/web/finance/invoices` | financeService.getInvoices | query (buildQueryString) | data | (layout), /, /financeiro | C |  |  |
| READ | GET | `/web/finance/add-on-billing-accounts` | financeService.getAddOns | query (buildQueryString) | data | (layout), /, /financeiro | C |  |  |
| READ | GET | `/web/finance/invoices/:id` | financeService.getInvoice |  | data Invoice | (layout), /, /financeiro | C |  |  |
| WRITE | POST | `/web/finance/financial-contacts` | financeService.createFinancialContact | {email} | data | (layout), /, /financeiro | C |  |  |
| WRITE | PUT | `/web/finance/financial-contacts/:id` | financeService.updateFinancialContact | {email} | data | (layout), /, /financeiro | C |  |  |
| WRITE | DELETE | `/web/finance/financial-contacts/:id` | financeService.deleteFinancialContact |  |  | (layout), /, /financeiro | C |  |  |
| READ | GET | `/web/subscription/premium` | premiumService.getStatus |  | data Subscription{active,status,subscriptionId,agencyId,seats,peakSeats,billingPeriod,cycleStart,cycleEnd,activatedAt,cancelledAt?} | (layout), /acessos, /add-ons/administrative, /add-ons/pro, /add-ons/smart-campaigns, /catalogs, /chats, /credit-analysis, /history, /lead… | C | y |  |
| WRITE | POST | `/web/subscription/premium` | premiumService.activate | {seats,...} | data Subscription (201) | (layout), /acessos, /add-ons/administrative, /add-ons/pro, /add-ons/smart-campaigns, /catalogs, /chats, /credit-analysis, /history, /lead… | C | y | contracts a paid module (billing side effect) |
| WRITE | PATCH | `/web/subscription/premium` | premiumService.changeSeats | {seats} | data | (layout), /acessos, /add-ons/administrative, /add-ons/pro, /add-ons/smart-campaigns, /catalogs, /chats, /credit-analysis, /history, /lead… | C | y |  |
| WRITE | DELETE | `/web/subscription/premium` | premiumService.cancel |  | data{accepted,effectiveAt} | (layout), /acessos, /add-ons/administrative, /add-ons/pro, /add-ons/smart-campaigns, /catalogs, /chats, /credit-analysis, /history, /lead… | C | y |  |
| READ | GET | `/web/seats/summary` | seatsService.getSummary |  | data{agencyId,period{year,month},summary{paid,free,test,maxPaidSeats},users[]} | (layout), /acessos, /add-ons/administrative, /add-ons/pro, /add-ons/smart-campaigns, /catalogs, /chats, /credit-analysis, /history, /lead… | C |  |  |
| READ | GET | `/web/seats/availability` | seatsService.getAvailability |  | data{contracted,occupied,extra,pricePerExtra} | (layout), /acessos, /add-ons/administrative, /add-ons/pro, /add-ons/smart-campaigns, /catalogs, /chats, /credit-analysis, /history, /lead… | C |  | mock registers it as /seats/* without /web prefix; real service uses /web/seats (C 7531 C="/web/seats") |

## users/teams/seats/permissions

| safety | method | path | caller | request | response | routes | ev | mock | note |
|---|---|---|---|---|---|---|---|---|---|
| READ | GET | `/auth/users/me` | meService.getMe |  | data user + REAs/roles | (layout), /, /acessos, /add-ons/administrative, /add-ons/pro, /add-ons/smart-campaigns, /atendimento-administrativo, /broadcasts, /captac… | C |  |  |
| READ | GET | `/auth/users/me/profile` | meService.getMe (2nd half) |  | data onboarding profile | (layout), /, /acessos, /add-ons/administrative, /add-ons/pro, /add-ons/smart-campaigns, /atendimento-administrativo, /broadcasts, /captac… | C |  |  |
| WRITE | PATCH | `/auth/profile` | meService.updateProfile | profile body | data | (layout), /, /acessos, /add-ons/administrative, /add-ons/pro, /add-ons/smart-campaigns, /atendimento-administrativo, /broadcasts, /captac… | C |  |  |
| WRITE | PATCH | `/auth/users/me/profile` | meService.updateProfilePhone | {phone} | data | (layout), /, /acessos, /add-ons/administrative, /add-ons/pro, /add-ons/smart-campaigns, /atendimento-administrativo, /broadcasts, /captac… | C |  |  |
| WRITE | POST | `/auth/users/me/onboarding` | onboardingService.completeOnboarding | {phone,workAreas[],workAreasOther,jobRoles...} | data | (layout) | C |  |  |
| READ | GET | `/auth/users/check-email` | authService.checkEmail | query: email | data | (layout), /, /acessos, /add-ons/administrative, /add-ons/pro, /add-ons/smart-campaigns, /atendimento-administrativo, /broadcasts, /catalo… | C |  |  |
| READ | GET | `/auth/agencies/search` | authService.searchAgencies | query: q | data[] | (layout), /, /acessos, /add-ons/administrative, /add-ons/pro, /add-ons/smart-campaigns, /atendimento-administrativo, /broadcasts, /catalo… | C |  |  |
| READ | GET | `/auth/users` | usersService.getUsers | query: seatType? page? ... | data[] User{id,name,email,role,seatType,active} | (layout), /acessos, /add-ons/administrative, /add-ons/pro, /add-ons/smart-campaigns, /catalogs, /chats, /credit-analysis, /history, /lead… | C | y |  |
| WRITE | POST | `/auth/users` | usersService.createUser | {name,email,role,seatType} | data User (upsert by email in mock) | (layout), /acessos, /add-ons/administrative, /add-ons/pro, /add-ons/smart-campaigns, /catalogs, /chats, /configs, /configs_qualification,… | C | y | I: may send invite e-mail (Keycloak) |
| WRITE | DELETE | `/auth/users/:id` | usersService.deleteUser |  |  | (layout), /acessos, /add-ons/administrative, /add-ons/pro, /add-ons/smart-campaigns, /catalogs, /chats, /credit-analysis, /history, /lead… | C |  |  |
| READ | GET | `/web/teams` | teamsService.getTeams | query: page limit | data{teams[],pagination} | (layout), /acessos, /add-ons/administrative, /add-ons/pro, /add-ons/smart-campaigns, /catalogs, /chats, /credit-analysis, /history, /lead… | C | y |  |
| READ | GET | `/web/teams/:id` | teamsService.getTeamById |  | data TeamDetail | (layout), /acessos, /add-ons/administrative, /add-ons/pro, /add-ons/smart-campaigns, /catalogs, /chats, /credit-analysis, /history, /lead… | C | y |  |
| WRITE | POST | `/web/teams` | teamsService.createTeam | {name,distributionEnabled,rouletteEnabled,lastAttendantEnabled,autoCrmEnabled,receivesSpecificSubcategories?,classifiers?} | data Team | (layout), /acessos, /add-ons/administrative, /add-ons/pro, /add-ons/smart-campaigns, /catalogs, /chats, /credit-analysis, /history, /lead… | C | y |  |
| WRITE | PATCH | `/web/teams/:id` | teamsService.updateTeam | partial team | data | (layout), /acessos, /add-ons/administrative, /add-ons/pro, /add-ons/smart-campaigns, /catalogs, /chats, /credit-analysis, /history, /lead… | C | y |  |
| WRITE | DELETE | `/web/teams/:id` | teamsService.deleteTeam |  |  | (layout), /acessos, /add-ons/administrative, /add-ons/pro, /add-ons/smart-campaigns, /catalogs, /chats, /credit-analysis, /history, /lead… | C | y |  |
| WRITE | POST | `/web/teams/:id/members` | teamsService.addMember | {members:[{userId,role}]} | data[] Member | (layout), /acessos, /add-ons/administrative, /add-ons/pro, /add-ons/smart-campaigns, /catalogs, /chats, /credit-analysis, /history, /lead… | C | y |  |
| WRITE | DELETE | `/web/teams/:id/members/:userId` | teamsService.removeMember |  |  | (layout), /acessos, /add-ons/administrative, /add-ons/pro, /add-ons/smart-campaigns, /catalogs, /chats, /credit-analysis, /history, /lead… | C | y | mock transfer origin member_removed -> reassigns chats |
| WRITE | PATCH | `/web/teams/:id/members/:userId` | teamsService.updateMember | {role?,active?,distributionActive?} | data | (layout), /acessos, /add-ons/administrative, /add-ons/pro, /add-ons/smart-campaigns, /catalogs, /chats, /credit-analysis, /history, /lead… | C | y |  |
| READ | GET | `/web/teams/:id/distribution` | teamsService.getDistributionConfig |  | data{teamId,leadTypes[]} | (layout), /acessos, /add-ons/administrative, /add-ons/pro, /add-ons/smart-campaigns, /catalogs, /chats, /credit-analysis, /history, /lead… | C | y |  |
| WRITE | PUT | `/web/teams/:id/distribution` | teamsService.updateDistributionConfig | {leadTypes[]} | data | (layout), /acessos, /add-ons/administrative, /add-ons/pro, /add-ons/smart-campaigns, /catalogs, /chats, /credit-analysis, /history, /lead… | C | y |  |
| READ | GET | `/web/teams/lead-types` | teamsService.getLeadTypes | query: excludeTeamId | data{leadTypes[]{key,label,available},generalAdmTeamExists} | (layout), /acessos, /add-ons/administrative, /add-ons/pro, /add-ons/smart-campaigns, /catalogs, /chats, /credit-analysis, /history, /lead… | C | y |  |
| READ | GET | `/web/teams/occurrences/availability` | teamsService.getOccurrencesAvailability | query: excludeTeamId | data[]{classifier,name,linkedTeamId,linkedTeamName} | (layout), /acessos, /add-ons/administrative, /add-ons/pro, /add-ons/smart-campaigns, /catalogs, /chats, /credit-analysis, /history, /lead… | C | y |  |
| WRITE | PUT | `/web/teams/:id/roulette` | teamsService.updateRouletteConfig | {membersOrder[]} | data{teamId,membersOrder,currentIndex} | (layout), /acessos, /add-ons/administrative, /add-ons/pro, /add-ons/smart-campaigns, /catalogs, /chats, /credit-analysis, /history, /lead… | C | y |  |
| READ | GET | `/web/teams/:id/metrics` | teamsService.getTeamMetrics |  | data.members[]{userId,userName,tprAvgMinutes,activeConversations,lastAccess} | (layout), /acessos, /add-ons/administrative, /add-ons/pro, /add-ons/smart-campaigns, /catalogs, /chats, /credit-analysis, /history, /lead… | C | y |  |
| READ | GET | `/web/permissions` | usePagePermissions (GO direct) |  | data.permissions{<perm>:{allowed,reason,blockBehavior}} | (layout), /acessos, /add-ons/pro, /add-ons/smart-campaigns, /catalogs, /chats, /credit-analysis, /history, /leads, /leads-v3, /properties… | C | y |  |
| READ | GET | `/web/permissions/teams` | useTeamPermissions (GO direct) |  | data{permissions{team:*},context{managedTeamIds,memberTeamIds,hasPremiumModule,hasPremiumSeat}} | (layout), /acessos, /add-ons/pro, /add-ons/smart-campaigns, /catalogs, /chats, /credit-analysis, /history, /leads, /leads-v3, /properties… | C | y |  |

## notifications

| safety | method | path | caller | request | response | routes | ev | mock | note |
|---|---|---|---|---|---|---|---|---|---|
| READ | GET | `/web/notifications` | notificationsService.getNotifications (7531) | query: page limit type read | data[] Notification | (layout), /acessos, /add-ons/administrative, /add-ons/pro, /add-ons/smart-campaigns, /catalogs, /chats, /credit-analysis, /history, /lead… | C | y |  |
| WRITE | PATCH | `/web/notifications/:id/read` | notificationsService.markAsRead |  | data{id,read} | (layout), /acessos, /add-ons/administrative, /add-ons/pro, /add-ons/smart-campaigns, /catalogs, /chats, /credit-analysis, /history, /lead… | C | y |  |
| WRITE | PATCH | `/web/notifications/read-all` | notificationsService.markAllAsRead |  |  | (layout), /acessos, /add-ons/administrative, /add-ons/pro, /add-ons/smart-campaigns, /catalogs, /chats, /credit-analysis, /history, /lead… | C | y |  |
| READ | GET | `/web/notification-events` | notificationEventsService.getNotifications (page /notifications) | query: page limit createdSince createdUntil transactionType type(repeatable) | data | /notifications | C |  |  |

## onboarding/checklist/test-users/misc

| safety | method | path | caller | request | response | routes | ev | mock | note |
|---|---|---|---|---|---|---|---|---|---|
| READ | GET | `/web/flows/:flowSlug/onboarding-progress` | onboardingFlowService.getOnboardingProgress | flowSlug in {chat-control, add-team, connect-origins, reachout-leads} | data{steps[]{stepSlug,completed},totalSteps,completedSteps} | (layout), /acessos, /add-ons/pro, /broadcasts, /chats, /checklist, /leads, /leads-v3, /user-management | C |  |  |
| WRITE | POST | `/web/flows/:flowSlug/steps/:stepSlug/complete` | onboardingFlowService.completeStep | {} |  | (layout), /acessos, /add-ons/pro, /broadcasts, /chats, /checklist, /leads, /leads-v3, /user-management | C |  |  |
| READ | GET | `/web/checklist/channels-status` | checklistService.getChannelStatus |  | data.channels | /checklist | C |  |  |
| WRITE | POST | `/web/checklist/channels` | checklistService.saveChannelStatus | channels body |  | /checklist | C |  |  |
| READ | GET | `/web/test-users` | testUsersService.list |  | data[] TestUser | (layout), /chats, /leads, /leads-v3 | C |  |  |
| **SEND** | POST | `/web/test-users` | testUsersService.create | {name,phoneNumber} (test lead) |  | (layout), /chats, /leads, /leads-v3 | C |  | I: registering a test lead likely makes Lais message that WhatsApp number |
| WRITE | DELETE | `/web/test-users/:id` | testUsersService.remove |  |  | (layout), /chats, /leads, /leads-v3 | C |  |  |
| READ | GET | `/web/banners/home` | bannersService.getHomeBanners |  | data[]{displayOrder,...} | / | C |  |  |
| READ | GET | `/web/whats-new` | whatsNewService.getReleases | query | data | /whats-new | C |  |  |

## next api routes (casa.lais.ai/api/*)

| safety | method | path | caller | request | response | routes | ev | mock | note |
|---|---|---|---|---|---|---|---|---|---|
| READ | GET | `/api/analytics` | analytics proxy health |  | {status,timestamp} (mock) | (layout), /, /acessos, /add-ons/administrative, /add-ons/pro, /add-ons/smart-campaigns, /atendimento-administrativo, /broadcasts, /captac… | C | y |  |
| WRITE | POST | `/api/analytics` | analytics proxy (Amplitude events) | event batch JSON | {success} | (layout), /, /acessos, /add-ons/administrative, /add-ons/pro, /add-ons/smart-campaigns, /atendimento-administrativo, /broadcasts, /captac… | C | y | telemetry only |
| READ | POST | `/api/intercom` | intercom identity hash | {user_id} | {hash} | (layout), /atendimento-administrativo, /broadcasts, /captacao, /configs_behavior, /configs_my_business, /configs_property_info, /configs_… | C |  | POST but idempotent HMAC |
| READ | GET | `/api/bubble-health` | BubbleIframePage health probe |  | {ok} | /captacao, /configs_behavior, /configs_my_business, /configs_property_info, /configs_whatsapp_profile, /developments, /history, /leads, /… | C |  |  |
| READ | GET | `/api/geocoding/autocomplete` | geocoding.autocomplete | query: input | {predictions[]} | /add-ons/smart-campaigns, /catalogs, /chats, /credit-analysis, /developments, /history, /leads, /leads-v3, /properties, /relatorio-v2, /r… | C |  |  |
| READ | GET | `/api/geocoding/geocode` | geocoding.geocode | query: address | {status,results[]} (Google Geocoding) | /add-ons/smart-campaigns, /catalogs, /chats, /credit-analysis, /developments, /history, /leads, /leads-v3, /properties, /relatorio-v2, /r… | C |  |  |
| AUTH | POST | `/api/access-code/validate` | history access-code login | {code (4 digits), chatId} | session cookie | /history | C |  |  |
| READ | GET | `/api/access-code/session` | history session |  | data (401 = none) | /history | C |  |  |
| AUTH | DELETE | `/api/access-code/session` | history logout |  |  | /history | C |  |  |
| AUTH | * | `/api/auth/* (NextAuth: signin, signout, session, csrf, callback/keycloak)` | next-auth client |  |  | (layout), /, /acessos, /add-ons/administrative, /add-ons/pro, /add-ons/smart-campaigns, /atendimento-administrativo, /avaliacoes, /broadc… | C |  |  |

## auth (BFF + Keycloak)

| safety | method | path | caller | request | response | routes | ev | mock | note |
|---|---|---|---|---|---|---|---|---|---|
| AUTH | DELETE | `https://bff.lastro.services/api/v1/auth/logout` | AuthLogout.performLogout | Authorization: Bearer |  | (layout), /, /acessos, /add-ons/administrative, /add-ons/pro, /add-ons/smart-campaigns, /atendimento-administrativo, /avaliacoes, /broadc… | C |  |  |
| AUTH | POST | `{KEYCLOAK_ISSUER}/protocol/openid-connect/token` | TokenService.refreshAccessToken (server-side NextAuth) | form: client_id client_secret grant_type=refresh_token refresh_token | {access_token,expires_in,refresh_token} | (layout), /, /acessos, /add-ons/administrative, /add-ons/pro, /add-ons/smart-campaigns, /atendimento-administrativo, /avaliacoes, /broadc… | C |  |  |
| AUTH | GET | `https://sso.lastro.services/realms/lastro-prod/protocol/openid-connect/logout` | logout redirect (browser nav) | id_token_hint, post_logout_redirect_uri (I) |  | (layout), /, /acessos, /add-ons/administrative, /add-ons/pro, /add-ons/smart-campaigns, /atendimento-administrativo, /broadcasts, /captac… | C |  |  |
| AUTH | GET | `https://www.facebook.com/v21.0/dialog/oauth` | Meta OAuth dialog (browser nav) | client_id redirect_uri scope state (routes.md Part B) |  | /configs_meta_integration | C |  |  |
