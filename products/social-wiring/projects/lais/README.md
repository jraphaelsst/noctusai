# lais — reference material (study only, no build)

Everything extracted from **Lais** (`casa.lais.ai`, vendor **Lastro**) — the real-estate WhatsApp AI agent One Consultoria Imobiliária uses — to understand it and later build our own. Studied **2026-10-13, read-only, on the owner's own account**, with skill `noc-reverse-engineer` (born from this run and CoreStudio's). **Stages 1 (map) and 2 (read-only data + Bubble definition) are done.** Nothing of Lais is being rebuilt yet; our own module will live in SW's "Lais" nav group (see `DECISIONS.md`).

Start with `analysis/SUMMARY.md`, then `specs/page-map.md`.

## Layout

| Path | What |
| --- | --- |
| `specs/page-map.md` | Live UI map: shell, every sidebar page, tabs, fields, buttons, current config values, observed AI script, mechanisms (evidence tags C/I/U). Screenshot names in it refer to `screenshots/` or the private set (see below). |
| `analysis/SUMMARY.md` | Headline of both stages: S2 findings, then S1 counts, findings, unknowns, safe-GET allowlist, never-call list. |
| `analysis/agent-brain.md` | S2: how the agent is configured — compiled prompt, 63-question slot catalogue, CRM forwarding (Vista), reengage, templates + param registry, visits, plans/credits. |
| `analysis/bubble-app-definition.md` | S2: the Bubble app read from `window.app` — data types, option sets, API Connector catalogue, every edit form's fields/options and the endpoint each save calls. |
| `captures/xhr-2026-10-13/` | S2: method, per-call status, response shapes of ~100 read-only GETs (no raw data stored). |
| `analysis/endpoints.{md,json}` | 230 endpoints by domain: method, caller, request/response, routes, **safety class** (READ / WRITE / SEND / AUTH). |
| `analysis/routes.md` | 58 routes: gate/redirect reason, native vs Bubble, sections, fields, validations. |
| `analysis/domain-model.md` | ~35 entities, fields, enums, relations, state machines. |
| `analysis/mocks.md` | The 75 MSW mock handlers shipped in the prod bundle (best shape evidence). |
| `analysis/flags-permissions.md` · `realtime-and-integrations.md` · `bubble-embeds.md` | Flags + permissions + plan gates · websockets, auth, Meta, CRMs/ERPs/portals · the Next↔Bubble iframe protocol. |
| `tools/` | Static-analysis helper scripts (they read the bundles from a scratch path; re-point before re-running). |
| `screenshots/` | 23 screenshots without third-party personal data. |
| `private/` (git-ignored) | Optional local drop zone. The real private set lives **outside the repo** at `~/Documents/repository/NoctusAI/_private-studies/lais/` (`screenshots/` with lead/staff data, `all-screenshots/` = all 35, `js/` = the vendor's 130 bundle chunks). Never commit it. |
| `DECISIONS.md` | Owner answers and open questions. |

## Architecture in one paragraph

Two apps: a Next.js app (`casa.lais.ai`, BFF `bff.lastro.services/api/v1`, Keycloak SSO, LaunchDarkly, Sentry, Intercom) and a legacy **Bubble.io** app (`legado.lais.ai`) embedded per route as iframes, receiving the Keycloak token by `postMessage`. Most of the agent's configurable "brain" (Meu negócio, Perguntas essenciais, Envio ao CRM policies, WhatsApp profile, IPTU) still lives in Bubble. Messaging is the official WhatsApp Business (Cloud) API with Meta-approved templates. Pricing unit: credit per atendimento.

## Sensitivity

Private client material. Lead names/phones/e-mails, staff lists, chat text, the agency access code and tokens are kept out of committed files (summaries only). The Bubble pages select data by a URL `agency` param and client-history links are gated by a 4-digit code — observations, **never tested**; never probe other agency ids.
