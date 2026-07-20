# Orbity -- Master Prompt

## Purpose

Agency-management SaaS for marketing/digital agencies. Handles client CRM,
sales funnel, task/agenda management, financials, Meta Ads traffic tracking,
WhatsApp automation flows, content/social-studio approvals, and client-facing
reports. Live in production at orbity.noctusai.com.

## Architecture

- Schema: `orbity`
- Backend port: 8010 | Frontend port: 8140
- Tenant key: `org_id`
- Auth: SSO (from Core) + direct login
- Backend path: `products/orbity/backend/app/`
- Frontend path: `products/orbity/frontend/src/`

Built on the NoctusAI seed framework — infra (auth, SSO, notifications, team,
rate limiting, CORS, exception handlers, LLM credential wiring) comes from
`create_product_app()` / `createProductApp()` + `createProductLayout()`.
Everything under `app/routers/` + `app/services/` (backend) and
`src/pages/` + `src/hooks/` beyond the framework defaults (frontend) is
Orbity domain code.

## Key Domains

### CRM
- **clients** -- agency client roster (CRUD), `clients_router.py` / `clients_service.py`
- **crm** -- leads, funil kanban stages, stage moves, activities, lead scoring + scoring-rules CRUD, and public lead capture (`crm_router.py` / `crm_service.py`; `capture_router` is the unauthenticated `/api/capture/{org_id}` half of the same router file). `lead_scoring.py` holds the scoring algorithm.

### Financial
- **financial** -- contracts, expenses, revenues, and monthly cash-flow summary (`financial_router.py` / `financial_service.py`)

### Operations
- **tasks** -- task CRUD, status patch, plus routines CRUD + on-demand spawn (`tasks_router.py` / `tasks_service.py`)
- **agenda** -- agenda_events CRUD + optional Google Calendar sync seam (`agenda_router.py` / `agenda_service.py`)

### Traffic / Marketing
- **meta_ads** -- ad accounts, campaigns, campaign metrics, sync seam, spend-vs-leads aggregate (`meta_ads_router.py` / `meta_ads_service.py`)
- **automation** -- WhatsApp automation flow engine: flows, steps, executions, run-due trigger (`automation_router.py`, `automation_service.py` + `automation_engine.py` for execution logic)
- **social_content** -- content/social studio: campaigns, posts, approvals (authed CRUD) plus the public client-approval flow via `approve_router` (`/api/content/approve/{token}`) (`social_content_router.py` / `social_content_service.py`)

### Reporting
- **reports** -- report definitions CRUD, snapshot generation, and the public token-gated read endpoint via `public_reports_router` (`reports_router.py` / `reports_service.py`)

### Framework-provided (zero Orbity code)
- `/api/health`, `/api/team` (invite/accept/list/cancel/remove), `/api/notificacoes`, `/api/status_paginas`
- `/api/llm/providers`, `/api/llm/models`, `/api/llm/preferences` from `noctusai_seed.llm_router`
- Multi-provider LLM access auto-wired in lifespan; products inherit `noctusai_lib.integrations.llm.chat_completion` / `generate_embedding` / `transcribe_audio` / `analyze_image` with zero plumbing
- CORS, Sentry, exception handlers, middleware, rate limiting, logging
- Sidebar, Header, AppShell, page status filtering (`status_pagina`), SSO context, trial/license warnings
- TooltipProvider, QueryClientProvider, AuthProvider, ErrorBoundary, Suspense

## Frontend Pages

Landing, Login, AcceptInvite, ForgotPassword, Dashboard (module-navigation
overview shell — see note below), Equipe, Clientes, Funil, Financeiro,
Tarefas, Agenda, Rotinas, Trafego, Automacao, Conteudo, Relatorios,
RelatorioPublico (public, token-gated), AprovacaoPublica (public,
token-gated), NotFound.

**Dashboard is intentionally KPI-free today.** It renders an honest
welcome + navigation shell into the real modules — no fabricated numbers.
Real-metric widgets (leads this week, tarefas atrasadas, receita do mês,
...) are a future slice: each module owns its own aggregate endpoint +
hook first (`useCrm`, `useFinancial`, ...), then Dashboard composes those
hooks. Do not hardcode a number on Dashboard that isn't backed by a real
hook — render loading/empty/error states instead per
`KB § PATTERNS/frontend/product-internal-wiring.md`.

## Orbity-Specific Patterns

- **Org ID extraction**: use the framework's `get_current_user_org` dependency — never inline `user.user_metadata.get("org_id")`.
- **Public token-gated endpoints**: three modules expose an unauthenticated, token-scoped read/write surface for external parties — `crm.capture_router` (`/api/capture/{org_id}`, public lead capture form), `social_content.approve_router` (`/api/content/approve/{token}`, client approval), `reports.public_reports_router` (`/api/reports/public/{token}`, shareable report link). These are NOT behind `Depends(get_current_user_org)` by design; treat any change to their token-validation logic as security-sensitive.
- **Automation execution**: `automation_engine.py` is the flow-execution engine consumed by `automation_service.py` — the router only handles CRUD + the `run-due` trigger endpoint; step-execution logic lives in the engine module, not the router.
- **Webhook receiver**: `webhook_router.py` ships the seed's generic single-vendor webhook skeleton (`/api/webhooks/example`, gated by `settings.example_webhook_secret`). This is infrastructure scaffolding inherited from the seed template, unrelated to Orbity's domain "Example" module (removed) — rename per real vendor when Orbity wires an inbound webhook (WhatsApp/WAHA, a payment provider, etc.).

## Development Guidelines

- Follow shared patterns from `noctusai_lib` (auth, roles, invitations, responses, exceptions)
- Router → Service → Schema pattern; routers thin, business logic in services
- RLS policies use `(SELECT auth.uid())` / `current_org_id()` pattern on all tables
- Portuguese for business domain names and UI copy, English for technical/framework code
- Products consume canonical seed organs (`ResourceManager`, `StatusPaginaPanel`, ...) from `@noctusai/lib` — no local re-implementations

## Testing

```bash
cd products/orbity/backend && pytest
cd products/orbity/frontend && npx vite build
```

## Dependencies

- Backend: `noctusai_lib` (shared code library) + `noctusai_seed` (framework)
- Frontend: `@noctusai/lib` (code + design-system library) + `@noctusai/seed` (framework)
- LLM access: via `noctusai_lib.integrations.llm` only — per-org key resolution is automatic
- Supabase: Auth, database, storage, RLS
- Meta Ads API, WAHA (WhatsApp), Google Calendar (sync seam)
