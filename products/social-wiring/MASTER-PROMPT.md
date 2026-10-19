# Social Wiring — MASTER-PROMPT

> Authoritative development guide for the `social-wiring` product (SW).

## Purpose

SW is noc's **real-estate operations hub**: inbound leads (portals, Meta Ads, WhatsApp), the
sales funnel and per-lead cards, properties / owners / condominiums, contracts, matrículas and
certidões, marketing (Meta, Instagram, email, CoreStudio), and the **WhatsApp transport and CRM
side of Julia**, the SDR agent. It started as a media/YouTube/scheduling CMS and absorbed
`mailing`, `imobi-scheduling` and several others; those modules still live here.

**Division of labour with `agents`.** Julia's brain (prompt, tool loop, LLM keys, versions) is
hosted in the `agents` product and consumed over its `/api/channels/*` API. SW owns what
surrounds the turn: webhook intake, the per-chat pause/handoff policy, rate limits, the single
outbound gate, the CRM (contatos, interações, eventos, leads, cards), knowledge/questions the
org configures, follow-ups, notifications and reports. SW never calls an LLM for a Julia turn.

## Julia (renamed from "Lais" on 2026-10-19)

"Lais" is Lastro's product (reverse-engineered under `projects/lais/`, kept as the vendor
study). Everything we built under that name is Julia: code `julia_*`, tables `julia_*`, API
`/api/julia/*`, pages `/julia/*`, nav group "Julia".

- **Backend**: `app/routers/julia_*_router.py` (agente, conversas, conhecimento, perguntas, visitas, reengajamento, notificacoes, envio, equipes, cloud/modelos/disparos, captacao, credito, avaliacoes, relatorios, painel, ferramentas), `app/services/julia_*` (one service per area), `app/clients/agents.py` (the agents HTTP client; `AgentsClient` / `FakeAgentsClient`).
- **Turn**: WAHA webhook → `julia_lead_turn_service` (debounce, authorized numbers, pause, limits) → agents `POST /api/channels/turns` with `agent_key="julia"` → actions parsed (`JuliaAction`) and applied idempotently by `julia_acoes_service` → reply sent.
- **Send gate**: every WhatsApp send of Julia code goes through `julia_envio_gate.exigir/conferir`; the keeper `tests/services/test_julia_envio_gate_keeper.py` derives its scope from the filenames (`julia_*`, importers of a `julia_*` service, `atendimento_blocos`, `supervisao`) — keep that predicate in step with any rename.
- **Agent tools**: `POST /api/julia/ferramentas/{nome}` (product token, scope `social-wiring:lais-tools`, issuer `agents`). The scope string and the Meta template-name prefix `lais_<id>` are identities stored outside SW and keep their old spelling (`NOC-REMEDIATE[rename-lais-tools-scope]`, `[rename-lais-meta-template-prefix]`).
- **Opt-in by construction**: nothing sends until an admin turns Julia on per connection (`agente_leads_ativo`, `authorized_numbers` required); defaults are off. Julia pages are the only UI; the Agente page links to the Agent Studio — agent behaviour is edited there, not in SW.
- **Atendimento blocks + Maya** (`app/modules/atendimento_blocos`, `app/modules/supervisao`, contract `projects/maya-blocks/CONTRACT.md`): a closed list of blocks (`sdr` = Julia, then atendimento, negociação, jurídico, financeiro, contador), per-org config (off by default), recorded handoffs, and Maya's nightly scorecards / handoff sweep / owner-only report. Studio key `julia` (legacy `lead-imob` is read as `julia`).
- **Database**: migration 287 renamed the 38 `lais_*` tables and their constraints, indexes, triggers, policies and functions to `julia_*`, and left security_invoker views `lais_*` so the previous image keeps working (`NOC-REMEDIATE[drop-lais-compat-views]`). New code uses `julia_*` only. Migrations 255–286 are applied history and keep the old names; never edit them.
- **Compat shims (one release)**: `LegacyLaisPathAlias` serves `/api/lais/*` and `/api/public/lais/*`; `/lais/*` redirects to `/julia/*` in the SPA; `LAIS_*` env names alias the renamed settings; `{{nome_lais}}` still renders as `{{nome_julia}}`. All tagged `NOC-REMEDIATE[drop-lais-*]`.
- **Vendor vocabulary stays**: the `*Lais` lead-channel slugs in `julia_leads_service` and `ZAP/LAIS`-style portal origins in `modules/leads/seed_data.py` are Lastro CRM data values, not our module name.

## Architecture

**Born from the seed framework.** App shell, auth, layout, routing, notifications, health, team
and LLM access come from the factory; SW owns domain modules and its frontend.

### Backend (`products/social-wiring/backend/app/`)

```
main.py        → create_product_app("Social Wiring", "social_wiring", settings); MODULES list assembles
                 module routers; LegacyLaisPathAlias is the outermost middleware
config.py      → ProductSettings subclass
modules/       → leads · pipeline · card_hub · portal_leads · imovel_hub · condominios · permutas ·
                 empresas · matriculas · certidoes · agentes_financeiros · meta_ads · instagram · simec ·
                 media_creation · transcricoes · edicao_fotos · email_marketing · mailchimp · scheduling ·
                 youtube · n8n · atendimento_blocos · supervisao
routers/       → product-level routers (whatsapp*, chat, clientes, imoveis, campanhas, marcas, settings, …)
                 and the julia_* routers
services/      → julia_* services and the other product services
clients/       → agents.py (the agents channel client)
migrations/    → numbered SQL, applied with noctus.dev.migrate_product; migrations-applied.json is the ledger
```

### Frontend (`products/social-wiring/frontend/src/`)

`App.tsx` registers routes via `createProductApp()`; nav groups come from `nav/navGroups.ts`:
Principal · Julia (`nav/julia.ts`, `JULIA_PAGES`) · Imóveis · Leads (incl. Funil, Blocos do Atendimento,
Supervisão) · Clientes · Edição de Fotos · CoreStudio · Marketing · Emissões · Conexões · Configuração.
A page's nav item is gated by its `status_pagina` row (`julia_<page>` keys for the Julia group).
Julia pages live in `pages/julia/`, components in `components/julia/`, hooks `useJulia*`.

### Database

Schema `social_wiring`, RLS own-org plus service role on every table. A new Julia page needs its
`status_pagina` row in a migration, its entry in `JULIA_PAGES`, and its route in `App.tsx`.

## Seed seams consumed (do NOT re-implement product-locally)

- Chatbot buffer / message store — `noctusai_lib.domain.chatbot`; WhatsApp WAHA + Meta Cloud connector — `noctusai_lib.integrations.whatsapp`
- Google Calendar/Maps/Drive, Meta FB/IG, YouTube, Vista CRM — `noctusai_lib.integrations.*`
- Jobs queue (`social_wiring.jobs`) — `noctusai_lib.domain.jobs`; in-app notifications — `noctusai_lib.domain.notifications`
- Fernet credential vault — `noctusai_lib.security.token_store`
- Frontend WhatsApp hooks — `createWhatsAppConnectionHooks` / `createWhatsAppIntakeHooks` from `@noctusai/lib`

## Rules

- Cross-product capabilities live in the seed; SW composes them. Julia's reasoning lives in `agents`, not here.
- ONE container (`serve_spa`); do not bake `VITE_BACKEND_API_URL`; pass `VITE_SUPABASE_*` as build args.
- A Fake and a Real implementation for every IO seam; tests use the Fake (`FakeAgentsClient`, fake transports).
- Never edit an applied migration; rename or change through a new forward migration (see 287).
- pt-BR UI copy.

## Testing

```bash
cd products/social-wiring/backend && pytest
cd products/social-wiring/frontend && npx vitest run
cd products/social-wiring/frontend && npx vite build   # must build clean
```

## Dependencies

- Backend: `noctusai_lib` + `noctusai_seed`; Frontend: `@noctusai/lib` + `@noctusai/seed`
- Runtime peer: `agents` (`/api/channels/*`)
