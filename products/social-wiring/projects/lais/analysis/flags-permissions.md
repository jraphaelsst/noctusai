# Feature flags, permissions, plan gates, onboarding flows

## 1. LaunchDarkly
Hook (C 7215 module 51562): `u(key, default=false)` → `D0()[key]` if boolean else default; `Cm()` = "flags loaded"; `h()` = all flags. Client id env `NEXT_PUBLIC_LAUNCHDARKLY_CLIENT_ID`; event hosts `events.launchdarkly.com`, `clientstream.launchdarkly.com` (C). Context (C layout): `{kind:"agency", key:<agencyId>, agencyType?, userRole?, isLastro?}`; no agency ⇒ `{kind:"user", key:"anonymous", anonymous:true}`; provider options `useCamelCaseFlagKeys:false, timeout:5`.

| flag key | default | where | effect (evidence) |
|---|---|---|---|
| `broadcasts-enabled` | false | nav item "Disparos em massa"; /broadcasts page guard | C 7533 `c="broadcasts-enabled"`; page: `u=c&&!d → router.replace("/")` (C broadcasts `d=!0===i[o.HA]`) |
| `smart-campaigns-front` | false | nav "Campanhas" (/smart-campaigns), add-ons contracted status, onboarding-state query enable | C 95095 `Wn`; route guard deny → redirect |
| `smart-campaigns-remarketing-front` | false | /smart-campaigns/remarketing create/edit | C 95095 `el`; remarketing page `"denied"===y → a.replace("/")` (needs flag + onboarding-state hasPixel) |
| `ci-catalogs` | false | smart-campaigns page (catalog integration toggle) | C 95095 `eV`, 7808 `en=(0,c.u)(u.eV)` (I: shows catalog link/section) |
| `meta-catalog-front` | false | nav "Catálogo Meta" → /catalogs | C 41415 `i="meta-catalog-front"` + nav `featureFlag:r.q0` |
| `property-page-front` | false | nav "Imóveis integrados" /properties | C 7533 nav |
| `credit-analysis-enabled` | false | nav "Análise de crédito" /credit-analysis; chat credit-analysis panel | C 7533 nav; 9654/chats `V=(0,g.u)("credit-analysis-enabled")` |
| `whats-new-page` | false | /whats-new route gate + header link | C layout `U=[{href:"/whats-new",featureFlag:"whats-new-page",…}]` |
| `checklist` | false | **exempts** agency from checklist: true ⇒ /checklist and /creation-user-test redirect to "/" and onboarding-flow queries disabled | C layout `if(c&&(t===q\|\|t===D))return void e.replace("/")` (`isChecklistExempt:c`) |
| `leads-view` | false | /leads: true ⇒ native LeadsV3, false ⇒ Bubble `leads` | C leads `m.O="leads-view"` |
| `new-relatorio-view` | false | /relatorio-v2: true ⇒ native RelatoriosV3, false ⇒ Bubble | C relatorio-v2 |
| `new-development-page-front` | false | /developments native vs Bubble | C developments |
| `new-access-code-page` | false | /history access-code flow | C history |
| `reengage-rules` | **false** (explicit `,!1`) | /configs_reengage rules ("réguas") section | C configs_reengage |
| `finance-change-plan-front` | false | /financeiro change-plan UI | C financeiro |
| `meta-integration-front` | false | /configs card + /configs_meta_integration | **inverted**: true ⇒ Meta card hidden and page redirects to /configs (C `e&&t.replace("/configs")`); I: being retired in favour of smart campaigns |
| `metricas-gestao-pro` | false | team metrics in /acessos (2800) | C 2800 |
| `message-status-checks` | false | chat message ticks (sent/delivered/read) | C 9654, chats |
| `reply-message-chat-frontend` | false | reply-to-message in chat | C 9654, chats |
| `chat-filter-without-tags` | false | "sem tags" chat filter (`withoutTags=true`) | C 9654, chats |
| `visit_action_notifications` | false | visit action notifications (visits page, 9994 visit modal, chats) | C 9654 module 82361 `P="visit_action_notifications"` |
| `smart-suggestion` | **true** | smart suggestions (layout + broadcasts) | C `(0,X.u)("smart-suggestion",!0)` |
| `attendant-app-migration` | **true** | layout: when false and selected REA role is `attendant` ⇒ `window.location.replace("https://atendimento.casa.lais.ai"+path)` | C layout |
| `em-manutencao` | false | global maintenance screen | C layout |
| `browser-notifications-front` | false | browser (OS) notifications | C layout, notifications |
| `amplitude-session-replay` | false | Amplitude session replay plugin | C 7215 |
Nav-guard semantics (C 7533 `DR`): `featureFlag` value `false` ⇒ deny; undefined after flags loaded ⇒ deny; undefined while LD bootstrapping ⇒ pending.

## 2. Route guard → why routes redirect to "/"
Guard list = nav items (C 7533 module 68544) + extra list (C layout `U`). Decision `DR(rule, ctx)` order: `allowIfLastro&&isLastro` → `featureFlag` → `allowedAgencyTypes/blockedAgencyTypes` → `requiresAdministrative` → `allowed/blockedUserRoles` → `requiresTeamViewPage` (team:view-page) → `pagePermission` (default `page:read`) from `GET /web/permissions`; on permissions error only admin/editor allowed. Deny ⇒ `router.replace(ui(ctx))` = first allowed nav href, else `"/"` (C layout `(0,z.Mw)(I,C)&&r.replace((0,z.ui)(C))`).

| route | gate | likely cause of observed redirect (I unless noted) |
|---|---|---|
| /smart-campaigns | flag `smart-campaigns-front` + perm `smart-campaign:read`; page also replaces "/" when campaigns API returns `ErrSmartCampaignsNotConnected` etc. | flag off (C page `ey&&(eN\|\|et.replace("/"))`) |
| /smart-campaigns/remarketing | flags `smart-campaigns-front` + `smart-campaigns-remarketing-front` and onboarding-state `hasPixel` | C `"denied"===y → replace("/")` |
| /properties | flag `property-page-front` + `integrated-property:read` | flag off |
| /catalogs | flag `meta-catalog-front` | flag off |
| /credit-analysis | flag `credit-analysis-enabled` + `credit-analysis:read` | flag off |
| /performance | `allowedAgencyTypes:["developer"]` + `report-performance:read` (and Bubble iframe enabled only for developer) | agency type ≠ developer (C) |
| /atendimento-administrativo | `requiresAdministrative` (agency has administrative add-on activation) | no administrative module |
| /checklist | extra list `page:all-roles`, but flag `checklist`=true ⇒ replace("/"); also routed away when all onboarding flows complete & outside display window | flag/flows (C layout) |
| /broadcasts | flag `broadcasts-enabled` (page-level) | |
| /owners, /relatorio-v2 | `blockedAgencyTypes:["developer"]` | developers only lose these |
| /acessos | `requiresTeamViewPage` (team:view-page) | |
| /financeiro | `billing:read` or `allowIfLastro` | |
| (any) | 402 `premium_module_required` ⇒ `/add-ons/pro` (C 5138) | |

## 3. Permission keys
Source: `GET /web/permissions` → `data.permissions{key:{allowed,reason,blockBehavior}}` (chat/page perms) and `GET /web/permissions/teams` (team:* + context). Default for missing key: `{allowed:false,reason:"role_restricted",blockBehavior:"hide"}` (C 2800 `let c={allowed:!1,reason:"role_restricted",blockBehavior:"hide"}`). `blockBehavior`: `hide` | `readonly` (renders inert) | other ⇒ disabled + tooltip. Reason messages: `premium_module_required` "A Gestão de atendimentos Pro precisa estar ativa", `premium_seat_required` "Você precisa de um assento Pro para esta ação", `role_restricted` "Você não tem permissão para esta ação", `team_restricted` "Esta ação é restrita à sua equipe". Cache: staleTime 1 h, refetch on focus (C).

Page permissions (nav): `home:read, chat:view, notification:read, notification:menu (menu only, for menuUserRoles ["attendant"]), lead:read, visit:read, credit-analysis:read, property-capture:read, property:read, development:read, integrated-property:read, report-neighborhood:read, report-performance:read, report-google-review:read, smart-campaign:read, lais-settings:read, add-on:read, billing:read, lais-guide:read, whats-new:read, page:all-roles, page:read (default)`.

Chat permissions → UI capability (C 9654 `f()`):
| key | capability |
|---|---|
| chat:send-message | canSendMessage |
| chat:send-template | canSendTemplate |
| chat:create-template | canCreateTemplate |
| chat:assign-label / chat:create-label | tags on chat / create tag |
| chat:create-note / chat:delete-note | internal notes |
| chat:archive | archive |
| chat:block | block lead number |
| chat:assign | assign chat (also grants self-assign) |
| chat:pause-lais **or** chat:suspend | canPauseLais — pause/resume the AI on a chat |
| chat:feedback | like/dislike AI |
| chat:send-to-crm | send lead to CRM |
| chat:view-all / chat:view-team | visibility scope |
| visit:read | canViewVisits |
| chat:create-team / edit-team / delete-team / add-remove-member | team mgmt from chat |
| chat:transfer-to-user / chat:transfer-to-team | transfer |
| chat:self-assign | "assumir conversa" |
| chat:filter-by-responsible / chat:filter-by-team | list filters |
| subscription:purchase / subscription:cancel | Pro module purchase/cancel |
Team permissions (mock + C 2800): `team:view-page, team:list-all, team:create, team:edit, team:delete, team:add-member, team:remove-member, team:set-member-role, team:toggle-distribution, team:configure-distribution-type, team:configure-auto-crm, team:configure-last-attendant, team:eligible-as-member, team:eligible-for-roulette`; actions on a specific team allowed if perm ∧ (list-all ∨ teamId ∈ managedTeamIds) (C 2800 `p=(e,t)=>!!d(e)&&(!!m||o.includes(t))`).
User-management actions (C 7531/2800): `add_user, change_role, change_seat, delete_user` (role-derived; details in routes.md).
UI copy: "Para pausar a Lais, é necessário ser Editor ou Administrador." / "Para reativar a Lais, é necessário ser Editor ou Administrador." (C 3b4451b3) ⇒ (I) server grants chat:pause-lais to admin/editor.

## 4. Roles & seats
- REA (real-estate-agency membership) roles seen: `admin`, `editor`, `member`, `attendant` (C layout `role==="attendant"`, mocks `role:"member|admin"`, team member roles `gestor|attendant`).
- Display roles (C 7531): admin "Administrador", editor "Editor", membro_sem_premium "Membro", membro_com_premium "Membro Pro", atendente_sem_gestor "Atendente", atendente_gestor "Atendente gestor".
- Seat types (C 7531): `paid` "Pro", `test` "Pro (teste)", `free` "Padrão". "Atendente precisa de assento Pro" (validation). Seats 1..100 ("Mínimo de 1 assento", "Máximo de 100 assentos"). Extra seat price mock 24.45.
- Agency types: `developer` (incorporadora) vs others (I: imobiliária) — drives /performance vs /owners,/relatorio-v2.
- `isLastro`/`isInternal`: Lastro staff bypass (`allowIfLastro`).

## 5. Plan / add-on gates
- **Pro module** ("Gestão de atendimentos Pro"): BFF returns 402 `premium_module_required` → redirect `/add-ons/pro`; `usePremiumAccess().hasAccess`; context `hasPremiumModule`, `hasPremiumSeat`; error code `PREMIUM_SUB_001` = not contracted (C 5138). Subscription endpoints `/web/subscription/premium`.
- Add-ons catalogue keys (C 544/7808 `c.U2.pro`, `c.U2.smartCampai…`): pro, smartCampaigns, administrative (details in routes.md routes.md Part B).
- Administrative add-on: `requiresAdministrative` (agency `hasAdministrative`), module name list in agency details `modules[].moduleName` (e.g. `onboarding_automatizado`).
- Smart campaigns: onboarding-state `needs_oauth | awaiting_configuration | ready`; API errors `ErrSmartCampaignsNotConnected | ErrSmartCampaignsAwaitingConfiguration | ErrSmartCampaignsDisabled` (C 95095).
- Broadcast plan limits: `GET /web/broadcasts/plan`; error `BROADCAST_007` "Limite do plano excedido. Reduza o número de contatos.", `BROADCAST_009` "Este recurso ainda não está disponível para a sua imobiliária." (C 3b4451b3/broadcasts).

## 6. Onboarding flows (`/web/flows/:flowSlug/onboarding-progress`, `/web/flows/:flowSlug/steps/:stepSlug/complete`)
| flowSlug | steps (C where seen) | surfaces |
|---|---|---|
| `chat-control` | `open-chat`, `stop-chat`, `send-message`, `reactive-chat` (C chats `P=[…]`) | /chats coach-marks (open a chat, pause Lais, send a human message, reactivate Lais) |
| `add-team` | `add-users`, `go-acess` (C 2800) | /acessos, /user-management banner |
| `connect-origins` | channel selection saved via `POST /web/checklist/channels {leadOriginIDs}` (routes.md Part C §5) | /checklist |
| `reachout-leads` | `go-leads`, `select-lead` → `send-reachout` (banner steps, C leads) + broadcast `sendBroadcast` step (C broadcasts `completeStep(er.sendBroadcast)`) | /leads, /broadcasts |
Progress shape: `{steps:[{stepSlug,completed}],totalSteps,completedSteps}` (C layout `B(e)=e.totalSteps>0&&e.completedSteps===e.totalSteps`). Also `/creation-user-test` forced for non-internal, non-exempt agencies with no test user (C layout).
User onboarding (separate): `/onboarding` when `profile.needsOnboarding`; `POST /auth/users/me/onboarding` {phone, workAreas, workAreasOther, jobRoles…}; job role options realtor "Sou corretor de imóveis", team_manager "Sou gestor de equipe", owner_partner "Sou dono ou sócio", comms_marketing "Atuo com comunicação e marketing", operation_end "Atuo no final da operação" (C 7427).
