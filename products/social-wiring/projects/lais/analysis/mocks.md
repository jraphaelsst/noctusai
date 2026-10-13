# MSW mock handlers shipped in the production bundle

Source: `js/9707.a1dffed8ccc77c86.js` module `39707` (exports `worker = setupWorker(...tI)`), plus fixture modules `13940`, `31707`, `68671`, `85376`, `92914` in the same chunk. All evidence below is **C** (code in that chunk) unless marked.
Activation: env `NEXT_PUBLIC_ENABLE_MOCKS` (C 5138 env schema, default `"false"`). Per-domain toggles are a feature map `l` (below); a disabled toggle returns `passthrough()` (`(0,o.l)()`).
Fixture selectors via env: `NEXT_PUBLIC_MOCK_EMPTY`, `NEXT_PUBLIC_MOCK_META_CATALOG_FIXTURE`, `NEXT_PUBLIC_MOCK_META_CATALOG_PRODUCT_SETS_FIXTURE`, `NEXT_PUBLIC_MOCK_CAPI_ONBOARDING`, `NEXT_PUBLIC_MOCK_CAPI_AD_ACCOUNTS`, `NEXT_PUBLIC_MOCK_CAPI_FIXTURE`.

Response envelope convention seen everywhere: `{ "data": <payload>, "message": "<text>" }` or `{ "data": ..., "code": 200 }`; errors `{ "error": "<msg>" }` or `{ "code": "META_CATALOG_0xx", "error": "<pt-BR msg>" }`.

## Mock feature toggles (`l`)
```json
{ "lead": {"enabled":true,"forceEnhance":true},
  "smartCampaigns": {"enabled":true,"getOnboardingState":true,"getAdAccounts":true,"getCampaigns":true,"getCampaignLeads":true},
  "metaCatalog": {"enabled":true,"getListings":true,"getListingsStats":true,"includeListings":true,"excludeListings":true,"resyncListings":true,"getProductSets":true,"createProductSet":true,"updateProductSet":true,"deleteProductSet":true},
  "analytics": {"enabled":true},
  "premium": {"enabled":true,"teams":true,"distribution":true,"roulette":true,"metrics":true,"transfer":true,"notifications":true,"subscription":true,"seats":true,"users":true},
  "reengagement": {"enabled":true,"getConfigs":true,"getDelayMinutes":true,"upsertConfig":true,"getRules":true,"createRule":true,"getRule":true,"updateRule":true,"toggleRule":true,"addAttempt":true,"deleteAttempt":true,"deleteRule":true,"getTemplates":true},
  "visitSettings": {"enabled":true,"getSettings":true,"upsertSettings":true},
  "agency": {"enabled":true,"getSettings":true} }
```
(I) The toggle names mirror the real service method names — handy as a feature inventory.

---
## 1. Agency settings
**GET** `{BFF}/web/agency/settings` →
```json
{ "data": { "allowNotifications": true, "useIptu": false, "allowEnhanceAcquisitionLeads": true,
  "prefixHumanMessagesWithSenderName": false, "overduePaymentSlipAlertDismissedAt": null,
  "bankslipOccurrences": true, "disableOnboardingTestLeadStep": false } }
```

## 2. Broadcasts (`*/web/broadcasts...`) — in-memory list `p`
Seed items (all `wizardStep:1`):
| id | type | name | status | scheduleDate | totalTargets | templateType | extra |
|---|---|---|---|---|---|---|---|
| bc-009 | reachout | Rascunho – Campanha Abril | pending | 2026-04-15T09:00:00 | 0 | recommendation | |
| bc-001 | reachout | Reativação Leads Março | confirmed | 2026-04-02T09:00:00 | 142 | recommendation | |
| bc-002 | reachout | Lançamento Ville Jardins | confirmed | 2026-04-05T10:00:00 | 89 | launch | |
| bc-003 | property_owner | Atualização Zona Sul | pending | 2026-04-08T09:00:00 | 53 | recommendation | |
| bc-004 | reachout | Follow-up Fevereiro | sent | 2026-03-15T09:00:00 | 210 | recommendation | responseRate 12.5, crmSentCount 45 |
| bc-005 | reachout | Reativação Leads Inativos | sent | 2026-03-01T10:00:00 | 178 | custom | responseRate 8.3, crmSentCount 32 |
| bc-006 | property_owner | Captação Centro | sent | 2026-02-20T09:00:00 | 67 | recommendation | responseRate 18.2, crmSentCount 15 |
| bc-007 | reachout | Disparo Teste WhatsApp | error | 2026-03-18T14:00:00 | 45 | recommendation | |
| bc-008 | reachout | Campanha Cancelada Março | canceled | 2026-03-10T09:00:00 | 120 | launch | |

Type normalisation: `b = e => "reachout"===e ? "remarketing" : e` (reachout ≡ remarketing).

- **GET** `*/web/broadcasts?type&status&limit(50)&offset(0)` → `{data:{total,limit,offset,items:[...]},message:"OK"}`; filters by normalised type and exact status. `NEXT_PUBLIC_MOCK_EMPTY=true` → empty items.
- **GET** `*/web/broadcasts/:id/targets` →
```json
{ "data": { "total": 3, "limit": 50, "offset": 0, "targets": [
  {"id":"tgt-1","name":"Maria Silva","phoneNumber":"(11) 99999-0001","email":"maria@example.com","status":"sent","chatId":"chat-001","createdAt":"2026-03-20T09:00:00Z"},
  {"id":"tgt-2","name":"João Santos","phoneNumber":"(11) 99999-0002","email":"joao@example.com","status":"sent","chatId":"chat-002","createdAt":"2026-03-20T09:00:00Z"},
  {"id":"tgt-3","name":"Ana Oliveira","phoneNumber":"(11) 99999-0003","email":"ana@example.com","status":"pending","chatId":"","createdAt":"2026-03-20T09:00:00Z"} ] }, "message": "OK" }
```
- **GET** `*/web/broadcasts/available-dates` → `{data:{dates:[{day:"YYYY-MM-DD",available:true} ×31 starting tomorrow]}}`.
- **GET** `*/web/broadcasts/property-owners` → `{data:{total:3,limit:200,offset:0,items:[{id:"po-1",name:"Carlos Proprietário",phoneNumber:"+5511988001001"},{id:"po-2",...Diana...},{id:"po-3",...Eduardo...}]}}`.
- **GET** `*/web/broadcasts/:id` → list item spread + detail fields:
```json
{ "description": "Disparo mock para teste", "templateText": "Olá, {nome da pessoa}! Mensagem de teste.",
  "statusDetails": "", "targetsFrom": "targets", "propertyLink": "", "retryCount": 0, "lastRetryAt": null,
  "fileUrl": "", "requestId": "req-<id>", "updatedAt": "<createdAt>", "targetsWithMessage": "<totalTargets if sent else 0>" }
```
404 → `{message:"Broadcast not found"}`.
- **POST** `*/web/broadcasts/file` (multipart: `createAsDraft`, `type`, `name`, `scheduleDate`|`scheduledAt`, `templateType`) → creates item (status `pending` if draft else `confirmed`, type `property_owner` or `remarketing`, totalTargets 3) → `{data:{id,totalValid:3,warnings:[],status},message:"Created"}`.
- **POST** `*/web/broadcasts/:id/file` → `{data:{totalValid:3,warnings:[]},message:"OK"}`.
- **POST** `*/web/broadcasts` (JSON: `createAsDraft`, `type`, `name`, `scheduleDate`, `propertyOwners[]` | `leads[]`, `templateType`|`templateRef`, `wizardStep`) → totalTargets = length of leads/propertyOwners; default name `Disparo <dd/mm/aaaa>` → `{data:{id,type,status,scheduleDate,warnings:[]},message:"Created"}`.
- **POST** `*/web/broadcasts/:id/confirm-pending` → sets `confirmed` → `{message:"Broadcast confirmed"}`.
- **PATCH** `*/web/broadcasts/:id/schedule` body `{scheduledAt}` → `{message:"Schedule updated"}`.
- **DELETE** `*/web/broadcasts/:id/permanent` → removes → `{message:"Broadcast deleted permanently"}` (no real service caller found — U whether exposed).
- **DELETE** `*/web/broadcasts/:id` → sets `canceled` → `{message:"Broadcast canceled"}`.

## 3. Leads
**PATCH** `{BFF}/web/leads/:leadId/enhance/force` →
```json
{ "data": { "leadId": "<id>", "enhanced": true, "sentToCRM": true, "timestamp": "<iso>" },
  "message": "Lead enhanced and sent to CRM successfully" }
```
(I) "enhance" = qualify lead + push to the agency CRM.

## 4. Meta catalog (`{BFF}/web/catalog/...`)
Listing factory `T(i, overrides)`:
```json
{ "adId": "ad-0001", "clientListingId": "APTO230426LOCAR", "title": "...", "link": "...", "imageUrl": "...",
  "city": "Mauá", "type": "apartment|house|commercial", "operation": "rent|buy|both", "price": "1500",
  "active": true, "status": "out_of_catalog", "lastSyncedAt": null, "errors": [] }
```
Optional fields: `syncStatus` (`pending|synced|error|submitted`), `deletedAt`, `errors[]{severity:"error|warning",message}`. 13 real-looking sample listings (portals: zobgi.com, suaquadra.com.br, amauridomingues.com.br, remobimoveis; image CDNs ingaiasites, infocenterhost2, cloudinary/suaquadra) then synthetic `IMV-10xx`.
Fixture sets (`NEXT_PUBLIC_MOCK_META_CATALOG_FIXTURE`): `empty, neverSynced, statusMix (default), withErrors, withRemovals, filterMix, large(120, nextPage 2)`. Sample error messages: "Imagem principal inacessível.", "Preço inválido.", "Descrição muito curta." (warning), "Endereço aproximado pela cidade." (warning), "Falha desconhecida no envio.", "A Meta recusou a remoção do anúncio.".
- **GET** `/web/catalog/listings?limit(1..200, default 50)&offset(<= d6)&search&status(csv)&city&operation&priceMin&priceMax` → `{data:{listings,pagination:{total,page,limit,nextPage?}},code:200}`; 400 `{error:"invalid limit: must be an integer"}` / `"invalid offset: must be at most <d6>"`. Search: exact clientListingId or title contains (min length `Z.y8`=3); city diacritic-insensitive; operation matches or listing `both`; price filter excludes 0/NaN.
- **GET** `/web/catalog/listings/stats` (same filters minus status) → `{data:{total,byStatus:{in_catalog,out_of_catalog,error},lastSyncedAt},code:200}`.
- **POST** `/web/catalog/listings/include` | `/exclude` body `{adIds[]} | {selectAll:true, excludedAdIds[]}` (+filter query when selectAll) →
```json
{ "data": { "applied": [{"adId":"ad-0002","status":"pending|synced"}], "skipped": ["ad-..."],
  "failed": [{"adId":"ad-0004","code":"META_CATALOG_003|004|002","reason":"..."}],
  "summary": {"total":n,"applied":n,"skipped":n,"failed":n} }, "code": 200 }
```
codes: `META_CATALOG_002` "Anúncio não pertence a esta imobiliária.", `003` include failure "Falha ao enviar o anúncio para o catálogo.", `004` exclude failure "Falha ao remover o anúncio do catálogo.". Exclude sets `deletedAt`.
- **POST** `/web/catalog/listings/resync` → same shape; out_of_catalog → skipped; failure `META_CATALOG_003` "Falha ao reenviar o anúncio à Meta."; applied → `syncStatus:"pending"`.
- **GET** `/web/catalog/product-sets` → `{data:{productSets:[ProductSet]},code:200}`; ProductSet:
```json
{ "id": "set-0002", "adAccountId": "act_1789455203311000", "createdAt": "2026-08-20T09:12:00-03:00", "updatedAt": "...",
  "metaProductSetId": "1789455203311012", "name": "Locação alto padrão", "color": "#28e4a8",
  "filter": { "and": [ {"availability":{"eq":"for_rent"}}, {"price":{"gte":6000}}, {"num_beds":{"gte":3}} ] },
  "remarketingSubsetType": "buy|rent (system subsets only)" }
```
Fixtures: `basic, empty, nestedFilter, noColor, notPushed (metaProductSetId null), orRootedUnparseable, remarketing` (system subsets named "Remarketing Dinâmico Lais - Venda" / "- Aluguel").
- **POST** `/web/catalog/product-sets` body `{name,color,filter,adAccountId?}` → 201 `{data:ProductSet,code:201}`; validation: blank name → 400 "invalid name: must not be blank"; bad filter → 422 `META_CATALOG_011`; reserved name → 422 `023`; duplicate name → 409 `015`; name "Falha no envio à Meta" → 502 `016`.
- **PATCH** `/web/catalog/product-sets/:id` → 404 `010`, system subset → 409 `022`, else 200.
- **DELETE** `/web/catalog/product-sets/:id` → 204 / 404 `010` / 409 `022`.
Error map `eb`: 010 Subset não encontrado · 011 O filtro informado não é aceito pela Meta · 012 Campo de filtro não suportado · 013 Operador de filtro não suportado · 014 Valor inválido para o campo do filtro · 015 Já existe um subset com este nome · 016 Falha ao enviar o subset à Meta · 017 Nenhum imóvel atende a esta regra no momento · 018 Nenhuma conta de anúncios da Meta conectada · 022 Este subset é gerenciado pelo sistema… · 023 Este nome é reservado….
Filter grammar (modules 13940/31707/68671/92914): fields `availability{for_sale Venda, for_rent Locação}`, `listing_type{for_sale_by_agent, for_rent_by_agent}` (not offered), `property_type{apartment Apartamento, house Casa, land Terreno, other Outro}`, `price` number, `name` (not offered), `city` text, `country` (no), `region` (Estado) text, `postal_code` (no), `num_beds` integer, `num_baths` integer; operators `eq neq lt lte gt gte contains i_contains not_contains i_not_contains`; combinators `and`(all) / `or`(any).

## 5. Permissions
**GET** `{BFF}/web/permissions/teams` →
```json
{ "data": { "permissions": {
  "team:view-page": {"allowed":true,"reason":"","blockBehavior":"hide"}, "team:list-all": hide, "team:create": hide,
  "team:edit": readonly, "team:delete": hide, "team:add-member": readonly, "team:remove-member": readonly,
  "team:set-member-role": readonly, "team:toggle-distribution": readonly, "team:configure-distribution-type": readonly,
  "team:configure-auto-crm": readonly, "team:configure-last-attendant": readonly,
  "team:eligible-as-member": hide, "team:eligible-for-roulette": hide },
  "context": { "managedTeamIds": [], "memberTeamIds": [], "hasPremiumModule": true, "hasPremiumSeat": true } }, "message": "OK" }
```
(`blockBehavior` ∈ hide | readonly; each value object `{allowed, reason, blockBehavior}`.)

## 6. Reengagement (`{BFF}/web/reengage/...`)
- configs seed: `[{enabled:true,reengageType:"reminder",delayMinutes:15},{enabled:true,reengageType:"final",delayMinutes:120}]`.
- **GET** `/configs` → `{data:[...]}`; **PUT** `/configs` body `{enabled,reengageType,delayMinutes}` (400 `invalid reengageType` unless reminder|final).
- **GET** `/configs/delay-minutes?reengageType=` → reminder: 5,10,15,30,45 min, 1 h(60); final: 1 h(60),2 h(120),4 h(240),8 h(480),12 h(720),24 h(1440) — items `{label:"5 minutos",value:5}`.
- **GET** `/rules/templates` →
```json
[ {"slug":"lead_reengage","name":"Mensagem ancorada no imóvel de interesse","preview":"Olá {{1}}. Seu atendimento referente ao imóvel {{2}} ainda está em aberto. Para continuarmos, preciso do seu \"ok\" por aqui."},
  {"slug":"lead_reengage_short","name":"Mensagem retomando atendimento","preview":"Olá {{1}}. Sua solicitação segue sem conclusão, gostaria de dar prosseguimento a ele agora?"},
  {"slug":"lead_reengage_long","name":"Mensagem de encerramento","preview":"Olá, {{1}}. Sua solicitação segue sem atualização há algum tempo e será encerrada.\nCaso deseje retomar o atendimento, pode me chamar por aqui."},
  {"slug":"lead_reengage_brief_message","name":"Mensagem breve","preview":"Sua solicitação ainda está em aberto. Estou à disposição caso queira retomar."} ]
```
(I) These are Meta-approved WhatsApp templates (`{{1}}` = lead name, `{{2}}` = property).
- rules seed: `[{id:"rule-1",realEstateAgencyId:"1111…",name:"Régua 1",buy:true,rent:false,enabled:false,attempts:[]},{id:"rule-2",…,"Régua 2",buy:false,rent:true,enabled:true,attempts:[]}]`.
- **GET** `/rules`, **POST** `/rules` body `{name?,buy,rent}` (default name = next "Régua N", created disabled) → 201; **GET/PATCH/DELETE** `/rules/:id` (PATCH accepts name, buy, rent; DELETE 204); **POST** `/rules/:id/activate|deactivate` → `{data:rule}`.
- **POST** `/rules/:id/attempts` body `{attemptIndex?,delayValue(default 1),delayUnit(default "days"),templateId,enabled(default true)}` → 201 `{data:{id,attemptIndex,delayValue,delayUnit,templateId,enabled}}`; **422 "attempt limit reached" when ≥3 attempts**.
- **DELETE** `/rules/:id/attempts/:attemptId` → 204 / 404 "attempt not found".

## 7. Smart campaigns (CAPI) `{BFF}/web/smart-campaigns/...`
- **GET** `/onboarding-state` → `{data:{state,agencyName,hasPixel,hasToken,hasAdAccount},code:200}`; states: `needs_oauth` (noPixel), `awaiting_configuration` (pixelOnly), `ready`.
- **GET** `/ad-accounts` → `{data:{adAccounts:[{id:"6f1c2c5e-…01",adAccountId:"act_1029384756",name:"Brasil Brokers — Curitiba"},{…02,"act_5566778899","Brasil Brokers — Lançamentos"},{…03,"act_9988776655",null}]}}`.
- **GET** `/campaigns` →
```json
{ "data": { "campaigns": [
  {"id":"120214000000000010","name":"Locação SP — Awareness","capi":true,"status":"active","spend":8740.55,"leads":215,"qualifiedLeads":96,"qualifiedPct":44.65,"cpl":40.65,"cpql":91.05},
  {"id":"120214000000000011","name":"Venda RJ — Conversão","capi":true,"status":"paused","spend":3120,"leads":64,"qualifiedLeads":22,"qualifiedPct":34.38,"cpl":48.75,"cpql":141.82},
  {"id":"120214000000000012","name":"Black Friday Imóveis — encerrada","capi":false,"status":"ended","spend":1500,"leads":12,"qualifiedLeads":0,"qualifiedPct":0,"cpl":125,"cpql":null} ],
  "summary": {"totalLeads":291,"qualifiedLeads":118,"avgCpl":46.94,"avgCpql":109.83,"totalSpend":13360.55},
  "lastUpdatedAt": "2026-04-29T14:08:21-03:00", "syncedAt": "2026-04-29T14:08:21-03:00" }, "code": 200 }
```
fixtures: `empty, syncedEmpty, capiAndNonCapi, fullMix`.
- **GET** `/campaigns/:campaignId/leads?page&limit(10)&search` → `{data:{leads,total,offset,limit}}`; lead row `{id,name,email,phone:"+55 11 9xxxx-xxxx",date,qualificationSource:"lais|manual|none",status,chatId|null}`; statuses `created, pending, enhanced, enhanced-error, message-sent-error`.

## 8. Visit settings
**GET/PUT** `{BFF}/web/agency/settings/visits` default (module 85376):
```json
{ "mode": "unified", "general": { "enabled": true, "documentRequired": false, "daysToOffer": 7, "minDaysToOffer": 1, "minHoursToOffer": 2,
  "schedule": { "monday":[{"start":"09:00","end":"18:00"}], "tuesday":[…], "wednesday":[…], "thursday":[…], "friday":[…] } } }
```
PUT stores body verbatim, returns `{data:body}`.

## 9. Teams / premium (`premium.*`)
Members seed `e2` (fields `id,teamId,userId,userName,userEmail,role:"gestor|attendant",active,distributionActive,createdAt`). Teams seed `e6`:
| id | name | membersCount | distributionEnabled | rouletteEnabled | lastAttendantEnabled | autoCrmEnabled |
|---|---|---|---|---|---|---|
| team-001 | Equipe Aluguel | 4 | ✓ | ✓ | ✓ | ✓ |
| team-002 | Equipe Venda | 3 | ✓ | ✓ | ✗ | ✗ |
| team-003 | Equipe Administrativa | 3 | ✗ | ✗ | ✗ | ✗ |
| team-004 | Equipe Administrativa Geral | 2 | ✗ | ✗ | ✗ | ✗ |
Lead types per team: 001 `[rent]`, 002 `[buy]`, 003 `[administrative, propertyowner]` (+specific subcategories classifiers 37,38), 004 `[administrative]`.
Occurrence classifiers: 37 Boleto em atraso · 38 Segunda via de boleto · 39 Reajuste de aluguel · 40 Rescisão de contrato · 41 Manutenção do imóvel.
- **GET** `/web/teams?page(1)&limit(20)` → `{data:{teams:[team + {leadTypes, administrativeCategories}],pagination:{total,page,limit}}}`.
- **POST** `/web/teams` body `{name,distributionEnabled,rouletteEnabled,lastAttendantEnabled,autoCrmEnabled,receivesSpecificSubcategories?,classifiers?}` → 201.
- **GET** `/web/teams/:id` → `{id,name,lastAttendantEnabled,autoCrmEnabled,members[],distributionConfig:{leadTypes,receivesSpecificSubcategories,classifiers},roulette:{membersOrder[userId of active attendants],currentIndex:0}}`.
- **PATCH** `/web/teams/:id` (merge; split out receivesSpecificSubcategories/classifiers), **DELETE** `/web/teams/:id`.
- **POST** `/web/teams/:id/members` body `{members:[{userId,role}]}` → 201 data[]; **DELETE/PATCH** `/web/teams/:id/members/:userId`.
- **GET** `/web/teams/lead-types?excludeTeamId=` → `{data:{leadTypes:[{key:"rent",label:"Aluguel",available},{key:"buy",label:"Compra"},{key:"administrative",label:"Cliente Administrativo"(always available)},{key:"propertyowner",label:"Proprietário"}],generalAdmTeamExists}}` — rent/buy/propertyowner are exclusive across teams.
- **GET** `/web/teams/occurrences/availability?excludeTeamId=` → `[{classifier,name,linkedTeamId,linkedTeamName}]`.
- **GET/PUT** `/web/teams/:id/distribution` → `{teamId,leadTypes}`; **PUT** `/web/teams/:id/roulette` body `{membersOrder}` → `{teamId,membersOrder,currentIndex:0}`.
- **GET** `/web/teams/:id/metrics` → `{members:[{userId,userName,tprAvgMinutes (null for new),activeConversations,lastAccess?}]}` (TPR = tempo de primeira resposta, I).

## 10. Notifications (`premium.notifications`)
Seed `ta` (15): types `chat_assigned` payload `{chatId,teamId,teamName,leadName,origin:"roulette|manual|redistribution|last_attendant"}`; `chat_queued` payload `{chatId,teamId,teamName,leadName,queuePosition}`; `new_lead_message` payload `{chatId,leadName,messagePreview,messageCount}`; each `{id,type,payload,read,createdAt}`.
- **GET** `/web/notifications?page&limit(10)&type&read` → `{data:[...]}`; **PATCH** `/web/notifications/:id/read` → `{data:{id,read:true}}`; **PATCH** `/web/notifications/read-all`.
(Distinct from `/web/notification-events` used by the /notifications page — see domain-model.)

## 11. Chat transfer
Seed transfers `tb`: `{id,fromUserId?,fromUserName?,toUserId?,toUserName?,toTeamId?,toTeamName?,origin:"manual|roulette|crm_link|member_removed",reason?,createdAt}`.
- **POST** `/web/chats/:id/transfer` body `{toUserId?,toTeamId?,…}` → `{data:{transferId,chatId,toUserId,toTeamId,origin:"manual"}}`.
- **GET** `/web/chats/:id/transfers?page&limit(20)` → `{data:[Transfer]}`.
- **POST** `/web/chats/:id/self-assign` → `{data:{chatId,userAssigned:"user-003",teamAssigned:"team-001"}}`.

## 12. Subscription / seats / users
- **GET** `/web/subscription/premium` → `{active:true,status:"active",subscriptionId:"sub-mock-1",agencyId:"agency-mock-1",seats:10,peakSeats:10,billingPeriod:"YYYY-MM",cycleStart,cycleEnd,activatedAt}`.
- **POST** same, body `{seats}` → 201 activates (resets cycle); **PATCH** body `{seats}` (peakSeats = max); **DELETE** → `status:"pending_cancellation"`, `{data:{accepted:true,effectiveAt:<now+7d>}}`.
- **GET** `/seats/summary` (mock path lacks `/web`; real client uses `/web/seats/summary`) → `{agencyId,period:{year,month},summary:{paid:4,free:0,test:0,maxPaidSeats:4},users:[]}`.
- **GET** `/seats/availability` → `{contracted:5,occupied:4,extra:0,pricePerExtra:24.45}` (R$ per extra seat, I).
- **GET** `/auth/users?seatType=` → `[{id,name,email,role:"member|admin",seatType:"free",active}]`; **POST** `/auth/users` body `{name,email,role,seatType}` upserts by email (200 update / 201 create).

## 13. Analytics / Amplitude
- **GET** `/api/analytics` → `{status:"healthy",timestamp}`; **POST** `/api/analytics` → `{success:true}`.
- **GET** `<AMPLITUDE.CONFIG>/config/*` → `{config:{analyticsOptions:{pageViews:true,sessions:true,formInteractions:false,fileDownloads:false}}}`; **POST** `<AMPLITUDE.API>/2/httpapi` → `{code:200,events_ingested:1,…}`.

## Mocked-but-not-called / called-but-not-mocked
- Mock-only: `DELETE /web/broadcasts/:id/permanent`, `/seats/*` (path variant).
- Most chat, visits, finance, templates, facebook, tags, kanban, notes, developments, reports endpoints have **no** mock (C: absent from 9707) — shapes for those come from call sites only (see endpoints.md / domain-model.md).
