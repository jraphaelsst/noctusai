# Bubble.io legacy embeds (legado.lais.ai)

## Topology (C + I)
```
casa.lais.ai (Next.js, top window, owns NextAuth session)
 └─ <iframe src="https://legado.lais.ai[/version-X]/<bubblePath>?mode=iframe&agency=<reaId>&parentOrigin=<origin>&<params>">   (BubbleIframePage)
      └─ (some Bubble pages) <iframe src="https://casa.lais.ai/<embeddable Next page>">   (bridge mode)
            reads auth from window.top.__laisAuth (same origin as top), talks to its Bubble parent via postMessage
```
- Two-way: Next hosts Bubble pages (most "legacy" screens), and Bubble in turn embeds a few native Next pages as drawers (qualification, visits, display-attendant-name). C 5138 module 73185: `function o(){if(window.top===window.self…)return"top";try{return window.top.__laisAuth,"nested-same-origin"}catch(e){return"cross-origin"}}`.
- Module `98652` (C 1647, 5812, history, leads, relatorio-v2, configs_qualification, configs_display_attendant_name): `$p` = Bubble base URL `https://legado.lais.ai`, `uR` = Bubble origin `https://legado.lais.ai` (used as postMessage targetOrigin and inbound origin check), `Z_(url, version)` rewrites/inserts `/version-<v>` path segment (regex `/\/version-[^/]+/`).
- Separate notion "version-test": `casa.lais.ai/version-test` (module 99966 `CASA_LAIS_TEST`) and Bubble-style `/version-test/configs_reengage?agency=…`, `/version-test/visits`, `/version-test/chats` links (C 3b4451b3, 9994) — (I) leftover from when casa.lais.ai itself was the Bubble app; `isVersionTest` is compile-time false in prod (`"https://casa.lais.ai".includes("version-test")`).

## BubbleIframePage (C 5812 module 82831 `BubbleIframePage`, duplicated in history/leads/relatorio-v2 chunks)
Props: `bubblePath, title, params, onBubbleMessage, layout ("main"|"fullscreen"), enabled (default true), allowAnonymous (default false), className`.
URL build (C 5812 `let e=new URLSearchParams({mode:"iframe"});if(O&&e.set("agency",O),e.set("parentOrigin",window.location.origin),v)for(…)n&&e.set(t,n);`):
`<Z_(BUBBLE_BASE, versionOverride)>/<bubblePath>?mode=iframe&agency=<selectedReaId>&parentOrigin=<window.location.origin>&<each truthy param>`.
- Not rendered (null src) unless `enabled && (selectedReaId || allowAnonymous)`.
- No token in the URL (C). Token goes by postMessage only (below).
- Version override: `sessionStorage["bubble_version_override"]` read once then removed on navigation (C 5812 `let u="bubble_version_override"`). Where it is written: U (not found in bundle; I: set by an internal/debug link).
- Health probe before showing: `GET /api/bubble-health` (same-origin Next API route) → `{ok}`; `ok:false` → "Página em manutenção — Ela volta em instantes. O resto da Casa da Lais continua funcionando." with "Voltar para o início". Fetch failure is treated as ok (C `catch(t){e||P("ok")}`).
- iframe attrs: `allow="clipboard-read; clipboard-write"`, `sandbox="allow-same-origin allow-scripts allow-forms allow-popups allow-top-navigation-by-user-activation allow-modals allow-downloads"`.
- onLoad → `sendAuthData()` + `postMessage({type:"STORAGE_HYDRATE",data:<bubble_storage_* map>}, uR)`.

### postMessage protocol, Next (parent) ↔ Bubble (child)
All inbound handlers check `event.origin === "https://legado.lais.ai"` (C `if(e.origin!==o.uR)return;`). Outbound always targets `uR`.

Parent → Bubble:
| type | payload | when |
|---|---|---|
| `AUTH_DATA` | `{token:<Keycloak access token>, agencyId, userId(sub), userName, userEmail, userRole (role of selected REA), roles: JSON.stringify(roles[]), expiresAt:""}` | on iframe load, on `REQUEST_AUTH_DATA`, and whenever the access token changes (token value REDACTED here — it is the live bearer token) |
| `STORAGE_HYDRATE` | `{data:{<key>:<value>…}, requestId?}` — all localStorage keys prefixed `bubble_storage_` (prefix stripped) | on load and on `BUBBLE_STORAGE_GET` |

Bubble → parent:
| type | fields | parent action |
|---|---|---|
| `REQUEST_AUTH_DATA` | — | send AUTH_DATA |
| `RELOAD` | — | `location.reload()` (throttled 5 s) |
| `BUBBLE_OPEN_EXTERNAL` | `url` (must match `^https?://`) | `window.open(url,"_blank","noopener,noreferrer")` |
| `BUBBLE_NAVIGATE` | `path` (must start with `/`), `callbackUrl?` (relative, not `//` or `/\`) | `router.push(path[?|&]callbackUrl=…)` |
| `BUBBLE_RELOAD` | — | reload |
| `BUBBLE_RELOAD_CLEAN` | — | `location.href = location.pathname` (drops query) |
| `BUBBLE_OPEN_NEW_TAB` | `path` (`/…`) | open same-origin path in new tab |
| `BUBBLE_OPEN_INTERCOM` | `message` | `Intercom.showNewMessage(message)` |
| `BUBBLE_HIDE_INTERCOM` / `BUBBLE_SHOW_INTERCOM` | — | hide/show launcher |
| `BUBBLE_TRACK_BUTTON_CLICK` | `action` | analytics `button_clicked {action, agencyID, isInternal, page, userID, version}` |
| `BUBBLE_STORAGE_SET` | `key, value` (strings) | `localStorage["bubble_storage_"+key]=value` |
| `BUBBLE_STORAGE_REMOVE` | `key` | remove |
| `BUBBLE_STORAGE_GET` | `requestId` | reply STORAGE_HYDRATE with requestId |
| `NAVIGATE` | page-specific query fields | `useBubbleMessageHandler({onNavigate})` → page rewrites its own URL query (`router.replace`) — keeps deep-links in sync |
| `LEADS_BANNER_NEXT_STEP` / `LEADS_BANNER_RESET` / `LEADS_BANNER_HIDE` | — | /leads onboarding banner step (select-lead → send-reachout) (C leads page) |
| `BUBBLE_LOGOUT` | — | /platform: `router.push("/")` (C platform page) |
Every message is also forwarded to the page's `onBubbleMessage` callback.

### Bubble-embedded child (Next page inside Bubble) → Bubble parent
Helper (C configs_qualification, configs_display_attendant_name, 1647): `if(window.parent!==window.self) window.parent.postMessage(msg, "https://legado.lais.ai")`
| type | extra |
|---|---|
| `SAVE` | `source:"casa-da-lais"` |
| `SAVE_ERROR` | `source, error` |
| `EXIT_DRAWER` | `source` (used instead of `router.push("/configs")` when `isBridge`) |
| `RELOAD_WITH_PARAMS` | `source, params` |
Auth in bridge mode: `window.top.__laisAuth.getSnapshot()` → `{accessToken, agencyId, user, roles}` published by the top Next window (C 73185 `i(e)` sets `window.__laisAuth={getSnapshot,subscribe}`), so the nested page uses the top window's token without its own session.

## Every Bubble embed (route → bubblePath → params)
| Next route | bubblePath | title | params forwarded | gate / notes | ev |
|---|---|---|---|---|---|
| /configs_behavior | `configs_behavior` | Comportamento da Lais | `type`, `tab` from URL | none in Next (AI behaviour knobs live in Bubble — **not in this bundle**) | C configs_behavior |
| /configs_my_business | `configs_my_business` | Meu negócio | type, tab | — | C |
| /configs_whatsapp_profile | `configs_whatsapp_profile` | Perfil do WhatsApp | type, tab | — | C |
| /configs_property_info | `configs_property_info` | Endereço e IPTU dos imóveis | type, tab | — | C |
| /owners | `owners` | Atualização de imóveis | status, name, number, clientlistingid, startDate, endDate, suggestionId (NAVIGATE syncs back) | nav: blockedAgencyTypes developer, perm property:read | C owners |
| /developments | `developments` | Empreendimentos | — (NAVIGATE handler) | used only when flag `new-development-page-front` is false; else native page | C developments |
| /leads | `leads` | Leads | page-specific query (v(e)); banner messages | used when flag `leads-view` false; true → native `LeadsV3` | C leads |
| /relatorio-v2 | `relatorio-v2` | Relatório | month, year | used when flag `new-relatorio-view` false; true → native RelatoriosV3 | C relatorio-v2 |
| /history | `history` | Histórico | chatid, agency | `allowAnonymous:true`, fullscreen; enabled when chatid present or access-code session; flag `new-access-code-page` | C history |
| /trainings | `trainings` | Treinamentos | allow-listed query keys; `agency` kept in sync | fullscreen; waits for agency match | C trainings |
| /platform | `platform` | Plataforma | allow-listed query keys; agency | fullscreen; BUBBLE_LOGOUT → "/"; layout forces /platform when agency.status=="onboarding" && module `onboarding_automatizado` | C platform, layout |
| /performance | `performance` | Desempenho | start_date, end_date (default: month start → now) | `enabled` only when agency type == "developer" | C performance |
| /plans | `plans` | Planos | — | — | C plans |
| /user-management | `user_management` | Acessos | — | with onboarding banner flowSlug add-team | C user-management |
Native-only routes (no Bubble) are listed in routes.md. Bubble pages for /captacao, /properties, /acessos: see routes.md (routes.md Part C) — U here.

## Env schema (C 5138 module 31377, zod; also duplicated in app/error chunk)
| key | type/default |
|---|---|
| NODE_ENV | enum development/production/test, default development |
| NEXT_PUBLIC_BFF_URL | url, default `http://localhost:3000` (prod build inlines `https://bff.lastro.services/api/v1`) |
| NEXT_PUBLIC_APP_NAME | default "Casa da Lais" |
| NEXT_PUBLIC_APP_VERSION | default "1.0.0" |
| NEXT_PUBLIC_APP_URL | url, default `https://casa.lais.ai` |
| NEXTAUTH_URL | url optional |
| NEXTAUTH_SECRET | min 32, default "" |
| NEXTAUTH_COOKIE_DOMAIN | must start with "." (e.g. ".casa.lais.ai"), optional |
| VERCEL_URL, VERCEL_BRANCH_URL | optional (=> hosted on Vercel, I) |
| KEYCLOAK_ID | default "casa-da-lais" |
| KEYCLOAK_SECRET | default "" |
| KEYCLOAK_ISSUER | url, default `https://localhost:3000/realms/lastro-sandbox` (prod realm `lastro-prod` at sso.lastro.services, C 6844) |
| NEXT_PUBLIC_KEYCLOAK_URL | default `https://localhost:3000` |
| NEXT_PUBLIC_KEYCLOAK_REALM | default "lastro-sandbox" |
| NEXT_PUBLIC_KEYCLOAK_CLIENT_ID | default "casa-da-lais" |
| KEYCLOAK_HISTORICO_URL / _CLIENT_ID / _CLIENT_SECRET | optional (separate client for /history access-code sessions, I) |
| NEXT_PUBLIC_SOCKET_URL | url optional (prod inlines `wss://eventhub.lastro.services`) |
| NEXT_PUBLIC_CHAT_SOCKET_URL | must be wss:// optional |
| NEXT_PUBLIC_AGENCY_ID | optional |
| AMPLITUDE_API_KEY, NEXT_PUBLIC_AMPLITUDE_API_KEY | optional |
| ANALYTICS_CAPTURE_PII | "true"/"false", default false |
| NEXT_PUBLIC_SENTRY_DSN | url optional |
| NEXT_PUBLIC_ENABLE_MOCKS | default false (MSW) |
| NEXT_PUBLIC_LAUNCHDARKLY_CLIENT_ID, LAUNCHDARKLY_SDK_KEY | optional |
| NEXT_PUBLIC_BUBBLE_BASE | url, default `https://legado.lais.ai` |
| NEXT_PUBLIC_BUBBLE_ORIGIN | url, default `https://legado.lais.ai` |
| NEXT_PUBLIC_ATTENDANT_REDIRECT_URL | url optional (prod inlines `https://atendimento.casa.lais.ai`) |
| NEXT_PUBLIC_INTERCOM_APP_ID, INTERCOM_IDENTITY_SECRET | optional |
Other `NEXT_PUBLIC_*` referenced outside the schema: `NEXT_PUBLIC_DATEGROUP_TZ` (cn util), `NEXT_PUBLIC_MOCK_*` (see mocks.md).

## Implications for our build (I)
- The AI-agent "brain" screens (behaviour, my business, WhatsApp profile, property info/IPTU) are **Bubble-only**; their field lists cannot be recovered from this bundle. They must be mapped live inside the iframe (legado.lais.ai DOM) in a later stage.
- Bubble receives the raw Keycloak access token via postMessage, so legado.lais.ai calls the same BFF (or its own backend) with that token (I).
