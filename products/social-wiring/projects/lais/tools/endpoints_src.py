# Endpoint catalogue source (hand-curated from tools/methods.txt + mocks + GO()/fetch call sites).
# Each row: domain, method, path, caller, safety, request, response, sig (regex used to locate chunks), ev
# safety: READ | WRITE | SEND | SIDE-EFFECT-GET | AUTH
E = []
def e(domain, method, path, caller, safety, request="", response="", sig=None, ev="C", note=""):
    E.append(dict(domain=domain, method=method, path=path, caller=caller, safety=safety,
                  request=request, response=response, sig=sig, evidence=ev, note=note))

# ---------------- chats / conversations ----------------
D = "chats/conversations"
e(D, "GET", "/web/chats/agency", "chatService.getChats (3b4451b3 `er`, BASE_PATH=/web/chats)", "READ",
  "query: limit(15) page operation suspended leadStatus creditAnalysisStatus teamIds(csv) userAssigneds(csv; '' = unassigned) assignedToMe archived tags(csv) withoutTags pinned",
  "data.chats[], data.pagination{total,nextPage}", r"BASE_PATH\}/agency\?")
e(D, "GET", "/web/chats/agency (pinned=true&limit=5)", "chatService.getPinnedChats", "READ", "query: pinned=true limit=5", "data.chats[], data.pagination.total", r"getPinnedChats")
e(D, "GET", "/web/chats/agency/search", "chatService.searchChats / chatsService.searchAgencyChats", "READ",
  "query: searchText searchIn(csv) limit page operation suspended leadStatus creditAnalysisStatus assignedToMe archived",
  "data.chats[0] = {data:[],meta:{total}} (facet shape)", r"/agency/search")
e(D, "GET", "/web/chats/agency/validate-phone", "chatService.validatePhone", "READ", "query: phoneNumber", "data (validation result; shape U)", r"validate-phone")
e(D, "GET", "/web/chats/:id", "chatService.getChatById / chatsService.getChatById", "READ", "optional request opts", "data = Chat", r"async getChatById")
e(D, "GET", "/web/chats/:id?withFeedback=true", "chatService.getChatWithFeedback", "READ", "", "data = Chat + feedback", r"withFeedback=true")
e(D, "GET", "/web/chats/:id/agency", "chatsService.getChatAgency (skipAgencyId:true)", "READ", "no x-agency-id header", "data = agency owning chat", r"/agency\"\),\{skipAgencyId")
e(D, "PATCH", "/web/chats/:id/suspend", "chatService.suspendChat", "SEND",
  "{suspended:boolean}", "", r"/suspend`,\{suspended", note="C: AI on/off switch. suspended=true -> 'Atendimento manual' (Lais paused); false -> 'Lais atendendo'. UI says AI auto-resumes after 5 days w/o messages")
e(D, "PATCH", "/web/chats/:id", "chatService.updateChatStatus", "WRITE", "{suspended?,unread?,archived?} (at least one)", "", r"At least one parameter \(suspended")
e(D, "PATCH", "/web/chats/:id/pin", "chatService.pinChat/unpinChat", "WRITE", "{pinned:boolean}", "", r"/pin`,\{pinned")
e(D, "POST", "/web/chats/:id/feedback", "chatService.sendFeedback", "WRITE", "feedback body (like/dislike + comment; see domain-model)", "", r"/feedback`,t\)")
e(D, "GET", "/web/chats/:id/credit-analyses", "chatService.getCreditAnalyses", "READ", "", "data[] CreditAnalysis", r"credit-analyses")
e(D, "GET", "/web/chats/:id/interactions", "chatService.getChatInteractions", "READ", "", "data[] Interaction", r"/interactions`")
e(D, "GET", "/web/chats/:id/messages", "messageService.getMessages (t9)", "READ", "query: page limit(25) order_by=created_at order_desc=true", "data{chat, messages[], pagination{nextPage}}", r"/messages\?\$\{a\.toString")
e(D, "POST", "/web/chats/:id/messages/human", "messageService.sendMessage", "SEND", "message body (text/media ref; routes.md Part A)", "", r"/messages/human`,t\)")
e(D, "POST", "/web/chats/:id/media", "messageService.uploadMedia (chat pkg G(); timeout 120s, video 340s w/ retries)", "SEND",
  "multipart: file, voice='true'?", "media ref", r"/media`,\{method:\"POST\"", note="I: upload precedes a human send; treat as SEND-adjacent")
e(D, "GET", "/web/chats/:id/messages/template/draft", "templateService.getTemplateDraft", "READ", "query: templateId", "data = rendered draft", r"/messages/template/draft")
e(D, "GET", "/web/chats/new/messages/template/draft", "templateService.getNewConversationTemplateDraft", "READ", "query: templateId", "data", r"new/messages/template/draft")
e(D, "POST", "/web/chats/:id/messages/human/template", "templateService.sendTemplateMessage", "SEND", "template send body", "", r"messages/human/template`,t\)")
e(D, "POST", "/web/chats/new/messages/human/template", "templateService.sendNewConversationTemplate", "SEND", "new-conversation template body (phone + template + params)", "", r"new/messages/human/template")
e(D, "POST", "/web/chats/:id/user-assignment", "chatAssignService.assignChat / userAssignService.assignUser", "SEND",
  "{userId, reason?, userName?} (userId '' = unassign)", "", r"user-assignment", note="changes who answers the chat (human attendant)")
e(D, "POST", "/web/chats/:id/team-assignment", "chatAssignService.assignTeam", "SEND", "{teamId, reason?}", "", r"team-assignment")
e(D, "POST", "/web/chats/:id/transfer", "transferService.transferChat (B)", "SEND", "{toUserId?, toTeamId?, reason?}", "data{transferId,chatId,toUserId,toTeamId,origin}", r"/transfer\"\),a\)")
e(D, "GET", "/web/chats/:id/transfers", "transferService.getTransferHistory", "READ", "query: page limit", "data[] Transfer", r"/transfers\"\)")
e(D, "POST", "/web/chats/:id/self-assign", "transferService.selfAssign", "SEND", "(no body)", "data{chatId,userAssigned,teamAssigned}", r"/self-assign\"\)\)\)")
e(D, "GET", "/web/chats/:id/visits", "chatVisits.getChatVisits", "READ", "", "data.visits[]", r"/web/chats/\$\{e\}/visits")
e(D, "POST", "/web/chats/:id/kanban-move", "kanbanService.moveChat", "WRITE", "move body (columnId, position; I)", "data", r"kanban-move")
e(D, "GET", "/web/chats/:id/tags", "tagService.getChatTags", "READ", "", "data[] Tag", r"/tags`\)\)\.data\?\?\[\]")
e(D, "PUT", "/web/chats/:id/tags", "tagService.saveChatTags", "WRITE", "{tagIds:[]}", "", r"tagIds:t")
e(D, "GET", "/web/chats/:id/internals", "notesService.listNotes", "READ", "", "data[]{entry,todos} -> flattened", r"/internals`\)")
e(D, "POST", "/web/chats/:id/internals", "notesService.createNote", "WRITE", "note body", "data", r"/internals`,t\)")
e(D, "POST", "/web/chats/:id/internals/audio/process", "notesService.processAudio", "WRITE", "multipart file=audio.webm", "data (transcription/structured note; I)", r"audio/process")
e(D, "DELETE", "/web/chats/:id/internals/:noteId", "notesService.deleteNote", "WRITE", "", "", r"/internals/\$\{t\}`\)")
e(D, "PATCH", "/web/chats/:id/internals/:noteId/todos/:todoId/complete", "notesService.completeTodo", "WRITE", "", "data", r"todos/\$\{a\}/complete")
e(D, "GET", "/web/kanban/columns", "kanbanService.listColumns", "READ", "", "data[] Column", r"listColumns")
e(D, "POST", "/web/kanban/columns", "kanbanService.addColumn", "WRITE", "column body", "data", r"addColumn")
e(D, "DELETE", "/web/kanban/columns/:id", "kanbanService.removeColumn", "WRITE", "", "", r"removeColumn")
e(D, "PATCH", "/web/kanban/columns/reorder", "kanbanService.reorderColumns", "WRITE", "order body", "data[]", r"reorderColumns")
e(D, "GET", "/web/tags", "tagService.getTags", "READ", "", "data[] Tag", r"async getTags\(\)")
e(D, "POST", "/web/tags", "tagService.createTag", "WRITE", "tag body", "data", r"async createTag")
e(D, "PATCH", "/web/tags/:id", "tagService.updateTag", "WRITE", "tag body", "data", r"async updateTag")
e(D, "DELETE", "/web/tags/:id", "tagService.deleteTag", "WRITE", "", "", r"async deleteTag")
e(D, "POST", "/web/users/block", "leadService.blockLeadNumber", "WRITE", "block body {reason:int, reasonDetails, phoneNumber?} (schema sp)", "", r"/block`,e\)|/block\"\),e\)")
e(D, "DELETE", "/web/users/unblock", "leadService.unblockLeadNumber", "WRITE", "query: phoneNumber", "", r"unblock\?")
e(D, "GET", "/auth/users?skipInternal=true[&managedByMe=true]", "assignableUsers.getAssignableUsers", "READ", "query: skipInternal managedByMe", "data[]{id,name,email}", r"skipInternal")
e(D, "GET", "/web/teams[?managedByMe=true]", "teamsLite.getTeams (chat module)", "READ", "query: managedByMe", "data.teams[]{id,name}", r"TEAMS_PATH=\"/web/teams\"")

# ---------------- templates ----------------
D = "templates (WhatsApp/Meta)"
e(D, "GET", "/web/templates/available", "templateService.getAvailableTemplates", "READ", "query: chatId?", "data[] Template", r"/available")
e(D, "GET", "/web/templates/categories", "templateService.getCategories", "READ", "", "data.categories", r"/categories")
e(D, "GET", "/web/templates/params", "templateService.getParams", "READ", "", "data.params", r"/params")
e(D, "POST", "/web/templates", "templateService.createCustomTemplate / createTemplate", "WRITE", "template body (routes.md Part B)", "data", r"createCustomTemplate|createTemplate\(e\)", note="I: likely submits template to Meta for approval")
e(D, "DELETE", "/web/templates/:id", "templateService.deleteTemplate", "WRITE", "", "", r"deleteTemplate")

# ---------------- leads ----------------
D = "leads"
e(D, "GET", "/web/leads/", "leadsService.listLeads (6989)", "READ",
  "query: page limit view phase distinctByPhone suggestionId order_by order_desc + filter fields (i(e): name/number/email/clientListingId/chatId ...)", "data (leads list; routes.md Part A)", r"async listLeads")
e(D, "GET", "/web/leads/origins", "leadsService.listLeadOrigins", "READ", "", "data[]", r"listLeadOrigins")
e(D, "GET", "/web/leads/campaigns", "leadsService.listLeadCampaigns", "READ", "", "data[]", r"listLeadCampaigns")
e(D, "POST", "/web/leads/:id/enhance", "leadsService.enhanceLead", "WRITE", "(no body)", "202 Accepted -> {accepted:true} else data=lead", r"/enhance\"\),void 0",
  note="I: 'enhance' = qualify + send to CRM (mock: enhanced:true, sentToCRM:true)")
e(D, "POST", "/web/leads/batch-enhance", "leadsService.batchEnhanceLeads", "WRITE", "{leadIds[]} | {selectAll:true, filter, excludedLeadIds[]} (max 60)", "data.summary{enhanced,skipped,failed}", r"batch-enhance", note="pushes leads to agency CRM (external side effect)")
e(D, "PATCH", "/web/leads/:id/enhance/force", "leadService.forceEnhance", "WRITE", "(no body)", "data{leadId,enhanced,sentToCRM,timestamp} (mock)", r"enhance/force", note="pushes lead to agency CRM (external side effect)")
e(D, "POST", "/web/leads/export", "leadsService.startLeadExport", "WRITE", "query: filters; body: export options", "data.jobId", r"startLeadExport")
e(D, "GET", "/web/leads/export/:jobId", "leadsService.getLeadExportStatus", "READ", "", "data (job status)", r"getLeadExportStatus")
e(D, "GET", "/web/leads/export/:jobId/download", "leadsService.downloadLeadExport", "READ", "parseAs blob", "file blob", r"downloadLeadExport")

# ---------------- visits ----------------
D = "visits"
e(D, "GET", "/web/visits", "visitsService.getVisits", "READ", "query: view date transactionType clientListingIds status leadIds", "data", r"async getVisits")
e(D, "GET", "/web/visits/:id", "visitsService.getVisitById/getVisitDetails", "READ", "", "data Visit", r"getVisitById")
e(D, "GET", "/web/visits/config", "visitsService.getConfig", "READ", "", "data visit config", r"/visits/config")
e(D, "POST", "/web/visits", "visitsService.createVisit", "WRITE", "visit body", "data", r"async createVisit", note="no call site found (dead code, I)")
e(D, "PATCH", "/web/visits/:id", "visitsService.updateVisit", "WRITE", "visit patch", "data", r"async updateVisit\(", note="no call site found (I)")
e(D, "PUT", "/web/visits/:id", "visitsService.updateVisitGroup", "SEND", "{visitId|alternativeDateTime, confirmedByName, confirmedByEmail} (reschedule) | {propertyId, propertyType} (associate property)", "data", r"updateVisitGroup", note="reschedule: with flag visit_action_notifications Lais WhatsApps the lead")
e(D, "DELETE", "/web/visits/:id", "visitsService.deleteVisit", "WRITE", "", "", r"async deleteVisit")
e(D, "POST", "/web/visits/:id/confirm", "visitsService.confirmVisit", "SEND", "{visitId|alternativeDateTime, confirmedByName, confirmedByEmail}", "data", r"/confirm\"\),t\)", note="with flag visit_action_notifications Lais WhatsApps the lead")
e(D, "POST", "/web/visits/:id/cancel", "visitsService.cancelVisit", "SEND", "{}", "", r"/cancel\"\),\{\}\)")
e(D, "GET", "/web/agency/settings/visits", "visitSettingsService.getSettings (1647)", "READ", "", "data VisitSettings (mock: mode unified, general{...})", r"settings/visits\"\)\)")
e(D, "PUT", "/web/agency/settings/visits", "visitSettingsService.upsertSettings", "WRITE", "VisitSettings", "data", r"settings/visits\",e")

# ---------------- properties / developments ----------------
D = "properties/captacao/developments"
e(D, "GET", "/web/properties/ads", "adsService.searchAds/getAds", "READ", "query: search | arbitrary filters; header x-agency-id override", "data", r"/ads\?")
e(D, "GET", "/web/ads/xml/status", "adsService.getFeedSyncStatus", "READ", "", "data feed sync status", r"getFeedSyncStatus")
e(D, "POST", "/web/ads/xml/sync", "adsService.triggerFeedSync", "WRITE", "(no body)", "", r"triggerFeedSync", note="triggers XML feed re-import; completion via ws feed_sync_completed")
e(D, "GET", "/web/properties/developments", "developmentsService.getDevelopments", "READ", "query: filters", "data", r"getDevelopments")
e(D, "POST", "/web/developments", "developmentsService.createDevelopment", "WRITE", "development body", "data", r"createDevelopment")
e(D, "PATCH", "/web/developments/:id", "developmentsService.updateDevelopment", "WRITE", "development patch", "data", r"updateDevelopment")
e(D, "POST", "/web/developments/bulk", "developmentsService.bulkImport (GO direct)", "WRITE", "multipart file", "data", r"/bulk\"\),\{method")
e(D, "GET", "/web/developments/bulk-imports", "developmentsService.listBulkImports", "READ", "", "data[]", r"listBulkImports")
e(D, "GET", "/web/developments/bulk-imports/:id/status", "developmentsService.getBulkImportStatus", "READ", "", "data", r"getBulkImportStatus")

# ---------------- broadcasts ----------------
D = "broadcasts/campaigns"
e(D, "GET", "/web/broadcasts", "broadcastService.listBroadcasts", "READ", "query: type status(csv) limit offset", "data{total,limit,offset,items[]}", r"async listBroadcasts")
e(D, "GET", "/web/broadcasts/:id", "broadcastService.getBroadcast", "READ", "", "data Broadcast (detail)", r"async getBroadcast\(")
e(D, "GET", "/web/broadcasts/:id/targets", "broadcastService.listTargets", "READ", "query: limit offset", "data{total,limit,offset,targets[]}", r"async listTargets")
e(D, "GET", "/web/broadcasts/property-owners", "broadcastService.listPropertyOwners", "READ", "query: search limit offset", "data{total,limit,offset,items[]{id,name,phoneNumber}}", r"listPropertyOwners")
e(D, "GET", "/web/broadcasts/segments", "broadcastService.listSegments", "READ", "query: type", "data", r"listSegments")
e(D, "GET", "/web/broadcasts/available-dates", "broadcastService.listAvailableDates", "READ", "", "data.dates[]{day,available}", r"listAvailableDates")
e(D, "GET", "/web/broadcasts/plan", "broadcastService.getAgencyPlan", "READ", "", "data (plan limits)", r"getAgencyPlan")
e(D, "POST", "/web/broadcasts", "broadcastService.createBroadcast", "SEND",
  "{type,name,createAsDraft,scheduleDate,templateType|templateRef,templateCustom?,propertyLink?,leads[]|propertyOwners[],wizardStep}", "data{id,type,status,scheduleDate,warnings}", r"async createBroadcast\(",
  note="createAsDraft=false -> status confirmed (scheduled send)")
e(D, "POST", "/web/broadcasts/file", "broadcastService.createBroadcastFromFile", "SEND",
  "multipart: file type createAsDraft name? scheduleDate? scheduledAt? templateRef? templateCustom? templateType? propertyLink?", "data{id,totalValid,warnings,status}", r"createBroadcastFromFile")
e(D, "POST", "/web/broadcasts/validate-file", "broadcastService.validateBroadcastFile", "WRITE", "multipart: file type", "data (validation)", r"validateBroadcastFile", note="I: pure validation, no persistence (U)")
e(D, "POST", "/web/broadcasts/:id/file", "broadcastService.replaceBroadcastFile", "WRITE", "multipart file", "data{totalValid,warnings}", r"replaceBroadcastFile")
e(D, "POST", "/web/broadcasts/:id/confirm-pending", "broadcastService.confirmBroadcast", "SEND", "{}", "", r"confirm-pending", note="draft -> confirmed (scheduled)")
e(D, "PATCH", "/web/broadcasts/:id/schedule", "broadcastService.updateSchedule", "SEND", "{scheduledAt}", "", r"/schedule\"\),t\)")
e(D, "PUT", "/web/broadcasts/:id", "broadcastService.updateBroadcast", "WRITE", "draft body", "data", r"async updateBroadcast")
e(D, "DELETE", "/web/broadcasts/:id", "broadcastService.cancelBroadcast", "WRITE", "", "", r"async cancelBroadcast", note="soft cancel -> status canceled")
e(D, "DELETE", "/web/broadcasts/:id/permanent", "(mock only; no service caller found)", "WRITE", "", "message", r"/permanent", ev="C(mock)")
e(D, "GET", "/web/agency/smart-suggestions", "smartSuggestionService.getSmartSuggestions", "READ", "", "list", r"getSmartSuggestions\(\)")
e(D, "GET", "/web/agency/smart-suggestions/:id", "smartSuggestionService.getSmartSuggestionById", "READ", "", "data", r"getSmartSuggestionById")
e(D, "POST", "/web/agency/smart-suggestions/:id/cooldown", "smartSuggestionService.sendCooldown", "WRITE", "{action}", "", r"sendCooldown")

# ---------------- smart campaigns / catalog ----------------
D = "smart-campaigns/remarketing/meta-catalog"
e(D, "GET", "/web/smart-campaigns/onboarding-state", "smartCampaignsService.getOnboardingState", "READ", "", "data{state:needs_oauth|awaiting_configuration|ready,agencyName,hasPixel,hasToken,hasAdAccount}", r"/onboarding-state\"\)\)")
e(D, "GET", "/web/smart-campaigns/ad-accounts", "smartCampaignsService.getAdAccounts", "READ", "", "data.adAccounts[]{id,adAccountId,name}", r"/ad-accounts\"\)\)")
e(D, "GET", "/web/smart-campaigns/campaigns", "smartCampaignsService.getCampaigns", "READ", "query: from to status(csv) adAccountId", "data{campaigns[],summary,lastUpdatedAt,syncedAt}", r"/campaigns\?\"\)")
e(D, "GET", "/web/smart-campaigns/campaigns/:campaignId/leads", "smartCampaignsService.getCampaignLeads", "READ", "query: from to page limit search", "data{leads[],total,offset,limit}", r"getCampaignLeads")
e(D, "GET", "/web/catalog/listings", "catalogService.getListings", "READ", "query: status search city operation priceMin priceMax limit(<=200) offset", "data{listings[],pagination}", r"/listings\"\)\.concat\(this\.buildListingsQuery")
e(D, "GET", "/web/catalog/listings/stats", "catalogService.getListingsStats", "READ", "query: search priceMin priceMax operation city", "data{total,byStatus,lastSyncedAt}", r"listings/stats")
e(D, "POST", "/web/catalog/listings/include", "catalogService.includeListings", "WRITE", "{adIds[]|selectAll,excludedAdIds[]} + filter query", "data{applied,skipped,failed,summary}", r"listings/include", note="pushes listings to Meta catalog (external side effect)")
e(D, "POST", "/web/catalog/listings/exclude", "catalogService.excludeListings", "WRITE", "same", "same", r"listings/exclude")
e(D, "POST", "/web/catalog/listings/resync", "catalogService.resyncListings", "WRITE", "{adIds[]...}", "same", r"listings/resync")
e(D, "GET", "/web/catalog/product-sets", "catalogService.getProductSets", "READ", "", "data.productSets[]", r"async getProductSets")
e(D, "POST", "/web/catalog/product-sets", "catalogService.createProductSet (retries:0)", "WRITE", "{name,color,filter,adAccountId?}", "data ProductSet (201)", r"createProductSet")
e(D, "PATCH", "/web/catalog/product-sets/:id", "catalogService.updateProductSet", "WRITE", "{name,color,filter}", "data", r"updateProductSet")
e(D, "DELETE", "/web/catalog/product-sets/:id", "catalogService.deleteProductSet", "WRITE", "", "204", r"deleteProductSet")

# ---------------- configs / AI behaviour ----------------
D = "configs/behavior (AI brain)"
e(D, "GET", "/web/agency/settings", "agencyService.getSettings", "READ", "", "data AgencySettings{allowNotifications,useIptu,allowEnhanceAcquisitionLeads,prefixHumanMessagesWithSenderName,overduePaymentSlipAlertDismissedAt,bankslipOccurrences,disableOnboardingTestLeadStep}", r"/web/agency/settings\"\)\)")
e(D, "POST", "/web/agency/settings", "agencyService.updateSettings", "WRITE", "partial AgencySettings (+dismissOverduePaymentSlipAlert)", "data", r"/web/agency/settings\",e")
e(D, "GET", "/web/agency/details", "agencyService.getDetails", "READ", "header x-agency-id override", "data Agency (id,status,modules[],type...)", r"/web/agency/details")
e(D, "GET", "/web/agency/access-code", "agencyService.getAccessCode", "READ", "", "data access code", r"access-code\",e")
e(D, "GET", "/web/audiences/required-informations", "requiredInfoService.getSelected", "READ", "", "data", r"required-informations")
e(D, "GET", "/web/audiences/user-profiles", "audienceService.getUserProfiles", "READ", "", "data[]", r"getUserProfiles")
e(D, "POST", "/web/audiences/user-profiles", "audienceService.createUserProfile", "WRITE", "profile body", "data", r"createUserProfile")
e(D, "PATCH", "/web/audiences/user-profiles/:id", "audienceService.updateUserProfile", "WRITE", "profile patch", "", r"updateUserProfile")
e(D, "GET", "/web/reengage/configs", "reengageService.getConfigs", "READ", "", "data[]{enabled,reengageType:reminder|final,delayMinutes}", r"/web/reengage/configs\"\)\)")
e(D, "GET", "/web/reengage/configs/delay-minutes", "reengageService.getDelayOptions", "READ", "query: reengageType", "data[]{label,value}", r"delay-minutes\"\.concat")
e(D, "PUT", "/web/reengage/configs", "reengageService.upsertConfig", "WRITE", "{enabled,reengageType,delayMinutes}", "data", r"/web/reengage/configs\",e")
e(D, "GET", "/web/reengage/rules/templates", "reengageService.getTemplates", "READ", "", "data[]{slug,name,preview}", r"rules/templates\"\)\)")
e(D, "GET", "/web/reengage/rules", "reengageService.listRules", "READ", "", "data[] Rule", r"async listRules")
e(D, "POST", "/web/reengage/rules", "reengageService.createRule", "WRITE", "{name?,buy,rent}", "data Rule", r"async createRule")
e(D, "GET", "/web/reengage/rules/:id", "reengageService.getRule", "READ", "", "data Rule", r"async getRule\(")
e(D, "PATCH", "/web/reengage/rules/:id", "reengageService.updateRule", "WRITE", "{name?,buy?,rent?}", "data", r"async updateRule\(")
e(D, "POST", "/web/reengage/rules/:id/activate", "reengageService.activateRule", "WRITE", "{}", "data", r"/activate\"\),\{\}")
e(D, "POST", "/web/reengage/rules/:id/deactivate", "reengageService.deactivateRule", "WRITE", "{}", "data", r"/deactivate\"\),\{\}")
e(D, "POST", "/web/reengage/rules/:id/attempts", "reengageService.addAttempt", "WRITE", "{attemptIndex?,delayValue,delayUnit:days|...,templateId,enabled}", "data Attempt (max 3/rule in mock)", r"async addAttempt")
e(D, "PATCH", "/web/reengage/rules/:id/attempts/:attemptId", "reengageService.updateAttempt", "WRITE", "attempt patch", "data", r"async updateAttempt")
e(D, "DELETE", "/web/reengage/rules/:id/attempts/:attemptId", "reengageService.deleteAttempt", "WRITE", "", "", r"async deleteAttempt")
e(D, "DELETE", "/web/reengage/rules/:id", "reengageService.deleteRule", "WRITE", "", "", r"async deleteRule")

# ---------------- facebook / meta ----------------
D = "facebook/meta integration"
e(D, "POST", "/web/facebook/callback", "facebookService.callback", "AUTH", "{code} (OAuth code from facebook dialog v21.0)", "data", r"/callback\"\),\{code")
e(D, "POST", "/web/facebook/connect/finalize", "facebookService.connectFinalize", "WRITE", "finalize body (selected pages/ad account; routes.md Part B)", "", r"connect/finalize")
e(D, "GET", "/web/facebook/pages", "facebookService.getPages", "READ", "", "data[] Page", r"async getPages")
e(D, "DELETE", "/web/facebook/pages/:pageId", "facebookService.deletePage", "WRITE", "", "", r"async deletePage")
e(D, "GET", "/web/facebook/forms", "facebookService.getForms", "READ", "query: pageId?", "data[] Form", r"async getForms")
e(D, "GET", "/web/facebook/forms/local", "facebookService.getFormsLocal", "READ", "", "data[]", r"forms/local")
e(D, "GET", "/web/facebook/forms/meta", "facebookService.getFormsMeta", "READ", "", "data[]", r"forms/meta")
e(D, "POST", "/web/facebook/forms", "facebookService.createForm", "WRITE", "form body", "data", r"async createForm")
e(D, "PUT", "/web/facebook/forms/:formId/toggle", "facebookService.toggleForm", "WRITE", "{active}", "", r"/toggle\"\),\{active")
e(D, "PUT", "/web/facebook/forms/:formId/mapping", "facebookService.updateFormMapping", "WRITE", "{mappings}", "", r"/mapping\"\),\{mappings")
e(D, "GET", "/web/facebook/forms/:formId/questions", "facebookService.getFormQuestions", "READ", "query: pageId?", "data.questions[]", r"getFormQuestions")

# ---------------- reports ----------------
D = "reports/charts"
for name, p, t in [("getPlanConsumption", "plan-consumption", "query (buildQuery: period)"), ("getAlerts", "alerts", "query"), ("getLeadSummary", "lead-summary", "query"),
                   ("getLeadsByChannel", "leads-by-channel", "category query"), ("getLeadStatusByChannel", "lead-status-by-channel", "category query"),
                   ("getLeadsPerHour", "leads-per-hour", "category query"), ("getLeadsPerWeekday", "leads-per-weekday", "category query"),
                   ("getLeadsLastSixMonths", "leads-last-six-months", "category query")]:
    e(D, "GET", "/web/agency/charts/" + p, "chartsService." + name, "READ", t, "chart payload", r"async " + name)
for name, p in [("getVolume", "volume"), ("getOccurrenceRanking", "occurrence-ranking"), ("getConversationResolution", "conversation-resolution")]:
    e(D, "GET", "/web/agency/charts/administrative-report/" + p, "adminReportService." + name, "READ", "query: month year", "chart payload", r"async " + name)
e(D, "GET", "/web/report", "useReport (GO direct)", "READ", "params: date=yyyy-MM-01", "data.metadata.report{rentSection,buySection}", r"\"/web/report\"")
e(D, "GET", "/web/credit-analysis/summary", "creditAnalysisService.getSummary", "READ", "query (month/year)", "summary", r"/summary\?\"\)\.concat")
e(D, "GET", "/web/credit-analysis/chart", "creditAnalysisService.getChart", "READ", "query", "chart", r"/chart\?\"")
e(D, "GET", "/web/credit-analysis", "creditAnalysisService.getList", "READ", "query: month year page limit status", "list", r"async getList")
e(D, "GET", "/web/agency/google-reviews/dashboard", "googleReviewsService.getDashboard", "READ", "", "dashboard", r"google-reviews\",\"/dashboard")

# ---------------- finance ----------------
D = "finance/billing/add-ons"
for name, p, s in [("getSubscriptions", "subscriptions", "READ"), ("getConsumption", "consumption", "READ"), ("getBillingAccount", "billing-account", "READ"),
                   ("getFinancialContacts", "financial-contacts", "READ"), ("getInvoices", "invoices", "READ"), ("getAddOns", "add-on-billing-accounts", "READ")]:
    e(D, "GET", "/web/finance/" + p, "financeService." + name, s, "query (buildQueryString)" if name in ("getSubscriptions", "getConsumption", "getInvoices", "getAddOns") else "", "data", r"async " + name + r"\(")
e(D, "GET", "/web/finance/invoices/:id", "financeService.getInvoice", "READ", "", "data Invoice", r"async getInvoice\(e\)")
e(D, "POST", "/web/finance/financial-contacts", "financeService.createFinancialContact", "WRITE", "{email}", "data", r"createFinancialContact")
e(D, "PUT", "/web/finance/financial-contacts/:id", "financeService.updateFinancialContact", "WRITE", "{email}", "data", r"updateFinancialContact")
e(D, "DELETE", "/web/finance/financial-contacts/:id", "financeService.deleteFinancialContact", "WRITE", "", "", r"deleteFinancialContact")
e(D, "GET", "/web/subscription/premium", "premiumService.getStatus", "READ", "", "data Subscription{active,status,subscriptionId,agencyId,seats,peakSeats,billingPeriod,cycleStart,cycleEnd,activatedAt,cancelledAt?}", r"async getStatus\(\)")
e(D, "POST", "/web/subscription/premium", "premiumService.activate", "WRITE", "{seats,...}", "data Subscription (201)", r"async activate\(", note="contracts a paid module (billing side effect)")
e(D, "PATCH", "/web/subscription/premium", "premiumService.changeSeats", "WRITE", "{seats}", "data", r"async changeSeats")
e(D, "DELETE", "/web/subscription/premium", "premiumService.cancel", "WRITE", "", "data{accepted,effectiveAt}", r"async cancel\(\)")
e(D, "GET", "/web/seats/summary", "seatsService.getSummary", "READ", "", "data{agencyId,period{year,month},summary{paid,free,test,maxPaidSeats},users[]}", r"async getSummary\(\)")
e(D, "GET", "/web/seats/availability", "seatsService.getAvailability", "READ", "", "data{contracted,occupied,extra,pricePerExtra}", r"async getAvailability\(\)",
  note="mock registers it as /seats/* without /web prefix; real service uses /web/seats (C 7531 C=\"/web/seats\")")

# ---------------- users / teams / permissions ----------------
D = "users/teams/seats/permissions"
e(D, "GET", "/auth/users/me", "meService.getMe", "READ", "", "data user + REAs/roles", r"/auth/users/me\"\)")
e(D, "GET", "/auth/users/me/profile", "meService.getMe (2nd half)", "READ", "", "data onboarding profile", r"/auth/users/me/profile\"\)\.catch")
e(D, "PATCH", "/auth/profile", "meService.updateProfile", "WRITE", "profile body", "data", r"/auth/profile\",e")
e(D, "PATCH", "/auth/users/me/profile", "meService.updateProfilePhone", "WRITE", "{phone}", "data", r"/auth/users/me/profile\",e\)")
e(D, "POST", "/auth/users/me/onboarding", "onboardingService.completeOnboarding", "WRITE", "{phone,workAreas[],workAreasOther,jobRoles...}", "data", r"me/onboarding")
e(D, "GET", "/auth/users/check-email", "authService.checkEmail", "READ", "query: email", "data", r"check-email")
e(D, "GET", "/auth/agencies/search", "authService.searchAgencies", "READ", "query: q", "data[]", r"agencies/search")
e(D, "GET", "/auth/users", "usersService.getUsers", "READ", "query: seatType? page? ...", "data[] User{id,name,email,role,seatType,active}", r"async getUsers")
e(D, "POST", "/auth/users", "usersService.createUser", "WRITE", "{name,email,role,seatType}", "data User (upsert by email in mock)", r"async createUser", note="I: may send invite e-mail (Keycloak)")
e(D, "DELETE", "/auth/users/:id", "usersService.deleteUser", "WRITE", "", "", r"async deleteUser")
e(D, "GET", "/web/teams", "teamsService.getTeams", "READ", "query: page limit", "data{teams[],pagination}", r"async getTeams\(e\)\{var")
e(D, "GET", "/web/teams/:id", "teamsService.getTeamById", "READ", "", "data TeamDetail", r"getTeamById")
e(D, "POST", "/web/teams", "teamsService.createTeam", "WRITE", "{name,distributionEnabled,rouletteEnabled,lastAttendantEnabled,autoCrmEnabled,receivesSpecificSubcategories?,classifiers?}", "data Team", r"async createTeam")
e(D, "PATCH", "/web/teams/:id", "teamsService.updateTeam", "WRITE", "partial team", "data", r"async updateTeam")
e(D, "DELETE", "/web/teams/:id", "teamsService.deleteTeam", "WRITE", "", "", r"async deleteTeam")
e(D, "POST", "/web/teams/:id/members", "teamsService.addMember", "WRITE", "{members:[{userId,role}]}", "data[] Member", r"async addMember")
e(D, "DELETE", "/web/teams/:id/members/:userId", "teamsService.removeMember", "WRITE", "", "", r"async removeMember", note="mock transfer origin member_removed -> reassigns chats")
e(D, "PATCH", "/web/teams/:id/members/:userId", "teamsService.updateMember", "WRITE", "{role?,active?,distributionActive?}", "data", r"async updateMember")
e(D, "GET", "/web/teams/:id/distribution", "teamsService.getDistributionConfig", "READ", "", "data{teamId,leadTypes[]}", r"getDistributionConfig")
e(D, "PUT", "/web/teams/:id/distribution", "teamsService.updateDistributionConfig", "WRITE", "{leadTypes[]}", "data", r"updateDistributionConfig")
e(D, "GET", "/web/teams/lead-types", "teamsService.getLeadTypes", "READ", "query: excludeTeamId", "data{leadTypes[]{key,label,available},generalAdmTeamExists}", r"async getLeadTypes")
e(D, "GET", "/web/teams/occurrences/availability", "teamsService.getOccurrencesAvailability", "READ", "query: excludeTeamId", "data[]{classifier,name,linkedTeamId,linkedTeamName}", r"getOccurrencesAvailability")
e(D, "PUT", "/web/teams/:id/roulette", "teamsService.updateRouletteConfig", "WRITE", "{membersOrder[]}", "data{teamId,membersOrder,currentIndex}", r"updateRouletteConfig")
e(D, "GET", "/web/teams/:id/metrics", "teamsService.getTeamMetrics", "READ", "", "data.members[]{userId,userName,tprAvgMinutes,activeConversations,lastAccess}", r"getTeamMetrics")
e(D, "GET", "/web/permissions", "usePagePermissions (GO direct)", "READ", "", "data.permissions{<perm>:{allowed,reason,blockBehavior}}", r"\"/web/permissions\"\)")
e(D, "GET", "/web/permissions/teams", "useTeamPermissions (GO direct)", "READ", "", "data{permissions{team:*},context{managedTeamIds,memberTeamIds,hasPremiumModule,hasPremiumSeat}}", r"\"/web/permissions/teams\"\)")

# ---------------- notifications ----------------
D = "notifications"
e(D, "GET", "/web/notifications", "notificationsService.getNotifications (7531)", "READ", "query: page limit type read", "data[] Notification", r"async getNotifications\(e\)\{let a=")
e(D, "PATCH", "/web/notifications/:id/read", "notificationsService.markAsRead", "WRITE", "", "data{id,read}", r"async markAsRead")
e(D, "PATCH", "/web/notifications/read-all", "notificationsService.markAllAsRead", "WRITE", "", "", r"markAllAsRead")
e(D, "GET", "/web/notification-events", "notificationEventsService.getNotifications (page /notifications)", "READ", "query: page limit createdSince createdUntil transactionType type(repeatable)", "data", r"notification-events")

# ---------------- onboarding / checklist / misc ----------------
D = "onboarding/checklist/test-users/misc"
e(D, "GET", "/web/flows/:flowSlug/onboarding-progress", "onboardingFlowService.getOnboardingProgress", "READ", "flowSlug in {chat-control, add-team, connect-origins, reachout-leads}", "data{steps[]{stepSlug,completed},totalSteps,completedSteps}", r"onboarding-progress")
e(D, "POST", "/web/flows/:flowSlug/steps/:stepSlug/complete", "onboardingFlowService.completeStep", "WRITE", "{}", "", r"/complete\"\),\{\}")
e(D, "GET", "/web/checklist/channels-status", "checklistService.getChannelStatus", "READ", "", "data.channels", r"channels-status")
e(D, "POST", "/web/checklist/channels", "checklistService.saveChannelStatus", "WRITE", "channels body", "", r"/web/checklist/channels\",e")
e(D, "GET", "/web/test-users", "testUsersService.list", "READ", "", "data[] TestUser", r"\"/web/test-users\"\)\)\.data")
e(D, "POST", "/web/test-users", "testUsersService.create", "SEND", "{name,phoneNumber} (test lead)", "", r"\"/web/test-users\",e",
  note="I: registering a test lead likely makes Lais message that WhatsApp number")
e(D, "DELETE", "/web/test-users/:id", "testUsersService.remove", "WRITE", "", "", r"/web/test-users/\"\.concat")
e(D, "GET", "/web/banners/home", "bannersService.getHomeBanners", "READ", "", "data[]{displayOrder,...}", r"getHomeBanners")
e(D, "GET", "/web/whats-new", "whatsNewService.getReleases", "READ", "query", "data", r"getReleases")

# ---------------- Next.js /api routes (same-origin) ----------------
D = "next api routes (casa.lais.ai/api/*)"
e(D, "GET", "/api/analytics", "analytics proxy health", "READ", "", "{status,timestamp} (mock)", r"\"/api/analytics\",\{method:\"GET\"")
e(D, "POST", "/api/analytics", "analytics proxy (Amplitude events)", "WRITE", "event batch JSON", "{success}", r"\"/api/analytics\",\{method:\"POST\"", note="telemetry only")
e(D, "POST", "/api/intercom", "intercom identity hash", "READ", "{user_id}", "{hash}", r"/api/intercom\",\{method", note="POST but idempotent HMAC")
e(D, "GET", "/api/bubble-health", "BubbleIframePage health probe", "READ", "", "{ok}", r"/api/bubble-health")
e(D, "GET", "/api/geocoding/autocomplete", "geocoding.autocomplete", "READ", "query: input", "{predictions[]}", r"geocoding/autocomplete")
e(D, "GET", "/api/geocoding/geocode", "geocoding.geocode", "READ", "query: address", "{status,results[]} (Google Geocoding)", r"geocoding/geocode")
e(D, "POST", "/api/access-code/validate", "history access-code login", "AUTH", "{code (4 digits), chatId}", "session cookie", r"access-code/validate")
e(D, "GET", "/api/access-code/session", "history session", "READ", "", "data (401 = none)", r"access-code/session\",\{credentials")
e(D, "DELETE", "/api/access-code/session", "history logout", "AUTH", "", "", r"access-code/session\",\{method:\"DELETE\"")
e(D, "*", "/api/auth/* (NextAuth: signin, signout, session, csrf, callback/keycloak)", "next-auth client", "AUTH", "", "", r"/api/auth/signin\?|/signout\"\)")

# ---------------- external hosts ----------------
D = "auth (BFF + Keycloak)"
e(D, "DELETE", "https://bff.lastro.services/api/v1/auth/logout", "AuthLogout.performLogout", "AUTH", "Authorization: Bearer", "", r"/api/v1/auth/logout")
e(D, "POST", "{KEYCLOAK_ISSUER}/protocol/openid-connect/token", "TokenService.refreshAccessToken (server-side NextAuth)", "AUTH", "form: client_id client_secret grant_type=refresh_token refresh_token", "{access_token,expires_in,refresh_token}", r"openid-connect/token")
e(D, "GET", "https://sso.lastro.services/realms/lastro-prod/protocol/openid-connect/logout", "logout redirect (browser nav)", "AUTH", "id_token_hint, post_logout_redirect_uri (I)", "", r"openid-connect/logout")
e(D, "GET", "https://www.facebook.com/v21.0/dialog/oauth", "Meta OAuth dialog (browser nav)", "AUTH", "client_id redirect_uri scope state (routes.md Part B)", "", r"v21\.0/dialog/oauth")
