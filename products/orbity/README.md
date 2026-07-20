# Orbity

Agency-management SaaS for marketing/digital agencies: client CRM, sales
funnel, tasks, agenda, financials, Meta Ads traffic, WhatsApp automation,
content/social studio, and client-facing reports. Live in production at
orbity.noctusai.com. Built on the NoctusAI seed framework (`noctusai_lib` +
`noctusai_seed` backend, `@noctusai/lib` + `@noctusai/seed` frontend).

## Stack

- **Backend**: FastAPI via `create_product_app()` from `noctusai_seed` (port 8010)
- **Frontend**: React via `createProductApp()` + `createProductLayout()` from `@noctusai/seed` (port 8140)
- **Build**: `createViteConfig()` from seed framework
- **Database**: Supabase (schema: `orbity`)
- **Auth**: SSO (from Core) + direct login

## Modules

- **Clientes** — agency client roster (CRUD)
- **CRM / Funil** — leads, funil kanban, activities, lead scoring, public capture form
- **Financeiro** — contracts, expenses, revenues, monthly cash-flow
- **Tarefas / Agenda / Rotinas** — tasks, calendar events (+ GCal sync seam), recurring routines
- **Tráfego** — Meta Ads accounts, campaigns, metrics, spend-vs-leads aggregate
- **Automação** — WhatsApp automation flow engine (steps, triggers, executions)
- **Conteúdo** — social/content studio: campaigns, posts, client approval flow (public token link)
- **Relatórios** — report definitions, snapshot generation, public token-gated read
- **Equipe** — team management (invite, accept, list, cancel, remove — from the framework)

## Running

```bash
# Backend
uvicorn app.main:app --reload --port 8010 --app-dir products/orbity/backend

# Frontend
cd products/orbity/frontend && npm run dev
```

## Tests

```bash
cd products/orbity/backend && pytest
cd products/orbity/frontend && npx vite build  # must build clean
```
