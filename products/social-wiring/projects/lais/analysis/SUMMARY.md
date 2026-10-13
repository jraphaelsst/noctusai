# Lais — static analysis summary (S1, 2026-10-13)

Source: 130 production chunks of casa.lais.ai (never executed). Detail files alongside.

## Counts
230 endpoints (READ 120 · WRITE 85 · SEND 17 · AUTH 8; 216 BFF, 10 Next /api/*, 4 external) · 58 routes (50 with chunk) · 75 MSW mock handlers · 25 LaunchDarkly flags · ~60 permission keys · 3 websockets / 10 server events · ~35 entities.

## Top findings (C = verified in code by tech-lead)
1. Two apps: Next shell iframes Bubble `legado.lais.ai`; sends it the raw Keycloak token via postMessage `{type:"AUTH_DATA",token,agencyId,userId,…}` after `REQUEST_AUTH_DATA`, origin-checked. C — `bubble-embeds.md`
2. AI "brain" config (Comportamento incl. Perguntas essenciais, Meu negócio, Perfil WhatsApp, IPTU) is Bubble-only; native = visits, reengage, CRM-send rules.
3. CRM-send rules = audience user-profiles; fields with operators filled / >= / <= / between; groups OR, criteria AND.
4. AI on/off = `PATCH /web/chats/:id/suspend {suspended}` ("Lais atendendo" / "Atendimento manual"); UI says auto-resume after 5 days. C
5. CRM push = `POST /web/leads/:id/enhance`, `PATCH …/enhance/force`; status enhanced → "Enviado ao CRM", enhanced-error|expired → "Erro no envio", else "Não pronto". C
6. Visit confirm/reschedule/cancel WhatsApp the lead (flag `visit_action_notifications`); base `/web/visits`.
7. Redirect-to-"/" gates: smart-campaigns (+remarketing) flags + Meta pixel · /properties `property-page-front` · /catalogs `meta-catalog-front` · /credit-analysis `credit-analysis-enabled` · /performance agency type `developer` · /atendimento-administrativo admin add-on · /checklist flag or onboarding done.
8. Pro gating: BFF 402 `premium_module_required` → redirect /add-ons/pro. C
9. ⚠ HTTP client retries POST/PATCH/PUT/DELETE up to 3× on 5xx/429 — any live write could replay.
10. WhatsApp Cloud API rules (24h window, approved templates); FB OAuth ids, 33 lead-origin portal codes, 16 ERPs in `realtime-and-integrations.md`.

## Unknowns
Bubble config field schemas (need in-iframe pass) · which CRM the agency uses · uncaptured chunks (/facebook/callback, /onboarding*, /creation-user-test, /access-code, /captacao, reengage attempt editor) · response shapes for notes, interactions, segments, broadcast plan · whether GET /web/chats/:id or template-draft GETs mark read · mock-only paths (DELETE /web/broadcasts/:id/permanent, /seats/* without /web).

## S2 safe-GET allowlist (owner's own ids only)
me/profile · agency details+settings · permissions (+teams) · visits settings/config · reengage configs/rules/templates · audiences · templates · chats list → one read chat's messages/interactions/internals/tags/visits · leads · visits · ads · developments · broadcasts list/detail/targets/plan/dates/segments · /web/report · agency charts · credit analysis · google reviews · notification-events · teams · seats · subscription GET · finance GETs · smart-campaigns · catalog · facebook pages · flows progress.

## Never call
All 17 SEND · CRM enhance(+force) · template create · catalog include/exclude/resync · XML feed sync · subscription writes · Facebook writes · every other non-GET (see `endpoints.json` `safety`). No side-effect GETs found in code (opening chats still treated as possibly mark-read).

## Known weaknesses of this analysis
Endpoint→route mapping by regex/chunk deps (may over-list routes); routes.md sub-agent parts corrected for visits path + Qualificação→Bubble, others may slip.
