# Social Wiring

The real-estate operations hub of noc: lead intake, the sales funnel and cards,
properties and owners, contracts and certificates, marketing, and the WhatsApp
transport for **Julia**, the SDR agent. One seed-factory, single-container
product (backend 8011, frontend 8160, Supabase schema `social_wiring`).

Social Wiring is the **transport + CRM + operations** side. The agent's brain
(prompt, tools loop, LLM keys) is hosted in the `agents` product (Agent Studio)
and consumed over `/api/channels/*`; SW never calls an LLM for Julia's turns.

## Stack

- **Backend**: FastAPI via `create_product_app()` from `noctusai_seed`; features are product modules assembled from the `MODULES` list in `app/main.py` (`app/modules/*`) plus the Julia routers in `app/routers/julia_*`.
- **Frontend**: React via `createProductApp()` + `createProductLayout()` from `@noctusai/seed`; nav in `src/nav/navGroups.ts` (Julia group in `src/nav/julia.ts`).
- **Database**: Supabase, schema `social_wiring`; RLS own-org + service role.
- **Auth**: SSO + direct login (seed factory); `/chat` and the Julia privacy notice (`/privacidade/:slug`) are public.
- **Container**: ONE container — uvicorn serves the built SPA + API on one port (`serve_spa`).

## The Julia module

Julia is the WhatsApp SDR for a real-estate org (renamed from "Lais" on
2026-10-19; Lais is Lastro's product, studied in a private study outside git).

- **Julia is hosted in agents** (julia-v2): her prompt, knowledge, qualification standard, controls (ligado/drenando/desligado, per-conversation pause) and the shared lead thread all live there; SW is transport + CRM + operations and consumes her **through the API only** (`app/clients/agents.py`). SW never gates on a cached copy of a control: agents decides on every turn and answers with a `status`; any non-served status, error or timeout sends nothing (fail closed).
- **Turn flow**: WAHA webhook → `services/julia_lead_turn_service.py` → agents `POST /api/channels/turns` (studio key `julia`, formerly `lead-imob`; the request carries the lead ref, `gatilho` and a data-only `contexto`) → on a served turn the bubbles are sent and the typed actions (`handoff`, `lead_pronto`, `intencao_visita`, `captacao`, `encerrar`, …) are applied by `julia_acoes_service`; every outbound WhatsApp send passes the single gate `julia_envio_gate`. A human attendant's outbound and a lead message agents declined to answer are appended to the thread without a turn (`julia_thread_service`).
- **Mirrors, not sources**: `whatsapp_chats.agente_thread_id/agente_estado/agente_pausado` and `julia_contatos.slots/operacao` (+ `ai_outputs` stage history) mirror agents' state, written only from agents' answers. The CRM send fires on the stage agents COMPUTED (`julia_envio_regras.estagio_minimo`) or the `lead_pronto` action. The hand-off note (profile + atendimento summary + masked identity) goes to the org owner by default.
- **Tools for the agent**: agents calls back `POST /api/julia/ferramentas/{nome}` with a product token (scope `social-wiring:lais-tools` — kept under its old spelling until both products rename it).
- **Pages** (`/julia/*`): Painel, Conversas, Configurações, Agente (link to the Agent Studio), Conhecimento, Perguntas, Visitas, Reengajamento (réguas), Notificações, Envio, Leads, Equipes, Modelos, Disparos, Proprietários, Relatórios, Captação, Avaliações, Crédito. Old `/lais/*` URLs redirect.
- **Atendimento in blocks** (`app/modules/atendimento_blocos`, `/atendimento-blocos`): SDR (Julia) → atendimento → negociação → jurídico → financeiro → contador, with recorded handoffs.
- **Maya supervision** (`app/modules/supervisao`, `/supervisao`): nightly scorecards per block (Julia's rubric `sdr.v2`: first response is split agent vs human, only human acts take a handoff over, an accept with no actor still records its juridico handoff), handoff sweep, owner-only daily report; a supervision hook that fails raises a visible owner alert (`supervisao_falha`) and flags the day `dados_incompletos`.
- **Julia ↔ agents contract**: the per-turn `contexto` SW renders is DATA ONLY and carries only the keys agents' schema accepts (`julia_contexto_service.ESTADO_CHAVES_AGENTS`; `tests/services/test_agents_contract_v2.py` validates it against agents' `channels.v2.json`); no prompt text, knowledge, question list or tool list is sent. A 422 from agents is an integration bug and raises an owner alert (`agents_contrato_invalido`). The `/julia/agente` page backend (`/api/julia/roteamento`) is **line routing only** (which numbers feed the agent + the hand-off target), white-label per org; behaviour is configured in agents. The one-time knowledge copy into agents is `python -m app.jobs.julia_conhecimento_backfill` (dry-run by default).
- **Data**: tables `social_wiring.julia_*` (migration 287 renamed them from `lais_*`). Temporary compatibility views `lais_*` remain for the previous image — `NOC-REMEDIATE[drop-lais-compat-views]`. Old `/api/lais/*` URLs are served by a path alias until the next release.
- **Browser access (migration 289)**: every `julia_*` table and `lais_*` view is **service-role only** — no anon/authenticated grant or policy, default privileges revoked for future tables, and every `social_wiring` view runs `security_invoker`. All reads go through the backend API (A7 rules in `julia_acesso`). DB probes `julia_lockdown.*` gate predeploy.

## Other modules

`leads`, `pipeline` (funil + processos de venda), `card_hub`, `portal_leads` (portal ingestion + ROI), `imovel_hub`, `condominios`, `permutas`, `empresas`, `matriculas`, `certidoes`, `agentes_financeiros`, `meta_ads`, `instagram`, `simec`, `media_creation` (CoreStudio), `transcricoes`, `edicao_fotos`, `email_marketing`, `mailchimp`, `scheduling`, `youtube`, `n8n`.

## Running

```bash
# Backend
uvicorn app.main:app --reload --port 8011 --app-dir products/social-wiring/backend

# Frontend (bare Vite dev — talks to a separately-run :8011 backend)
cd products/social-wiring/frontend && npm run dev
```

Same-origin under the single-container model: `VITE_BACKEND_API_URL` is runtime-detected (`src/lib/apiBase.ts`) and not baked. The boot-critical `VITE_SUPABASE_*` vars are Vite-inlined at `vite build` and asserted in `main.tsx`.

## Tests

```bash
cd products/social-wiring/backend && pytest
cd products/social-wiring/frontend && npx vitest run && npx vite build
```

## Dependencies

- Backend: `noctusai_lib` + `noctusai_seed`; Frontend: `@noctusai/lib` + `@noctusai/seed`
- Runtime peer: the `agents` product (Julia's brain)
