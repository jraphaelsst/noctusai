# Personal Finance -- Master Prompt

## Purpose

Personal finance tracker for **organizations** -- companies use it as a financial management tool with multiple operators per org; individuals use it via single-member "personal" orgs (same data model, same RLS). Multi-account transaction management, budgets with category limits, recurring transaction automation, investment portfolio tracking, stock watchlists with real-time quotes, financial goal tracking, and reporting/analytics dashboards.

## Architecture

- Schema: `personal-finance`
- Backend port: 8002 | Frontend port: 8090
- Tenant key: `org_id`
- Auth: SSO (from Core) + direct login
- Backend path: `products/personal-finance/backend/app/`
- Frontend path: `products/personal-finance/frontend/src/`

## Key Domains

### Core
- **contas** -- multi-type bank/investment accounts (checking, savings, credit card, investment, etc.)
- **transacoes** -- income/expense transactions linked to accounts and categories
- **categorias** -- per-org seeded copies (19 starter rows from `PF_DEFAULT_CATEGORIAS` at first signup; each org owns + customizes its set freely)
- **operacoes** -- batch import and auto-categorization of transactions

### Planning
- **orcamentos** -- budget limits per category per month, with tracking and alerts
- **metas** -- savings and debt payoff goals with progress tracking
- **recorrentes** -- recurring transactions (salary, rent, subscriptions) with auto-generation via scheduler

### Investments
- **carteira** -- investment portfolios grouping multiple positions
- **ativos** -- individual asset positions (stocks, funds, crypto) within portfolios
- **watchlist** (favoritos) -- stock/asset watchlists with real-time yfinance quotes
- **cotacoes** -- real-time price fetching service
- **patrimonio** -- net worth calculation aggregating all accounts and investments

### Analytics
- **dashboard** -- summary cards, charts, spending trends
- **relatorios** -- monthly reports, category breakdowns, cash flow analysis

## Services (16)

ativos, carteira, categorias, contas, cotacoes, dashboard, metas, orcamentos, patrimonio, recorrentes, relatorios, transacoes, watchlist, **ai** (Phase 7 P1 indicators), **monthly_narrative** (Phase 10 P2-opp digest), **onboarding** (`ensure_pf_personal_org` + `seed_default_categories`; wraps seed-side `noctusai_lib.domain.org.ensure_personal_org` with PF defaults — 2026-05-03 `pf-org-scoping-migration`)

### AI Service (Phase 7 — 2026-04-25)
- **`categorize_transaction`** (P1-opp) — `POST /api/ai/transacoes/{transacao_id}/categorize`. Suggests a category from the user's existing `categorias` for a transaction; returns `matched_categoria_id` for one-click apply. Hook: `useCategorizeTransaction`. Prompt version `pf-categorize@v1`.
- **`flag_recurring_expense`** (P3-opp) — `POST /api/ai/transacoes/{transacao_id}/recurring-flag`. Decides if a transaction is part of a recurring pattern using up to 12 same-comerciante history rows. Hook: `useRecurringFlag`. Prompt version `pf-recurring@v1`.
- Both call `noctusai_lib.llm.chat_completion(cache=True, temperature=0, org_id=...)` (transactional metadata, not personal narrative). Persist to `"personal-finance".ai_outputs` via `noctusai_lib.ai.persist_output`. Read side: `<AIIndicator refType="transacao" refId={t.id}/>` on `Transacoes.tsx`. Standard router `ai_outputs` opted in via `main.py`. Migration: `006_ai_outputs.sql`.

### Monthly Narrative Service (Phase 10 — 2026-04-25, P2-opp)
- **`build_narrative(db, org_id, period_days=30)`** → `(Digest, summary)` — aggregates `transacoes` over the past month, asks LLM for a 3-paragraph PT narrative, renders html + text. No DB writes, no email send.
- **`send_monthly_narrative(db, org_id, recipient, period_days)`** — same plus delivery via `noctusai_lib.email.digest.send_digest`.
- Endpoints: `GET /api/ai/monthly-narrative?period_days=30` (dashboard card; hook `useMonthlyNarrative`) and `POST /api/ai/monthly-narrative/send {recipient, period_days}` (cron-friendly). Prompt version `pf-monthly-narrative@v1`.

## PF-Specific Patterns

- **Scheduler**: `app/scheduler.py` uses APScheduler to auto-process due recurring transactions, creating corresponding transacoes entries automatically.
- **Org scoping**: 12 op tables + 4 child tables, all `org_id NOT NULL + created_by UUID NULL`. RLS uniform via `public.current_org_id()` (JWT claim). Routers call `get_current_user_org(authorization)` → `Service(db, org_id)`; every service is `__init__(self, db_client, org_id: str)`. Solo users land in `is_personal=true` orgs auto-created via `ensure_pf_personal_org`.
- **Real-DB tests**: Auto-skip when `SUPABASE_URL` or `SUPABASE_SERVICE_ROLE_KEY` not set. Use `ClientOptions(schema="personal-finance")`.

## Frontend Pages

Dashboard, Contas, ContaDetalhes, Categorias, Operacoes, Orcamentos, OrcamentoDetalhes, Metas, MetaDetalhes, Recorrentes, Carteira, CarteiraDetalhes, Patrimonio, Relatorios, Equipe, Landing, Login, ForgotPassword, AcceptInvite, NotFound

## Development Guidelines

- Follow shared patterns from noctusai_lib (auth, roles, invitations, responses, exceptions)
- Router -> Service -> Schema pattern; routers are thin, business logic in services
- RLS policies use `(SELECT auth.uid())` pattern on all tables
- Portuguese for business domain names, English for technical/framework code
- Use `get_org_id(user)` for org extraction -- never access metadata directly
- N+1 zero tolerance: batch all reads and writes
- Schema name is hyphenated (`personal-finance`), requiring `ClientOptions(schema="personal-finance")` in Supabase client calls
- Recurring transaction processing must be idempotent (scheduler may retry)

## Testing

```bash
cd products/personal-finance/backend && pytest
```

595 passed + 10 skipped (Phase 7 close 2026-05-11; +11 from 2026-05-03 baseline of 584 — Phases 1-6 added 6 (5 keeper/Phase-6 tests + 1 carry-forward); Phase 7 adds 5 mount-smoke tests for the seed standard routers).

## Standard Routers Mounted

PF opts into 5 seed standard routers via `app/main.py § standard_routers=`:
`health` | `notificacoes` | `team` | `ai_outputs` | `ai_feedback`. The `health`
router auto-mounts `/api/health` (unauthenticated); `ai_outputs` provides
`GET /api/ai/outputs?ref_type=&ref_id=`; `ai_feedback` provides
`GET|POST /api/ai/feedback` keyed on `output_ref` (NOT `ref_type`/`ref_id`).
`SSOCallback` is seed-factory-mounted at `/sso` (no per-product file).

## Contract Notes (Phase 0-7 — 2026-05-03 to 2026-05-11)

- **`created_by` rename**: post-migration `008_org_scoping`, every PF op table now
  uses `created_by UUID NULL` (replaces the legacy `user_id` column). DTOs in
  `frontend/src/types/` follow the rename — references to `user_id` in older
  code are stale and should be migrated to `created_by` opportunistically.
- **`fonte` field on `transacoes`**: present on `005_transacoes_metadata.sql`;
  identifies the origin of the transaction (`manual`, `recorrente`, `import`,
  `categorize_ai`). Used by AI categorization to distinguish suggested-vs-final.
- **Scheduler standard router**: NOT shipped this project (Phase 5 deferred —
  PF-5 in §5.2.6). Scheduler artifacts surface via per-product `/api/recorrentes/proximas`
  + `/executar` endpoints. Cross-product `scheduler` standard router is a follow-up.
- **Backend orphans** (Phase 7 verification): `GET /api/operacoes/{id}` and
  `GET /api/orcamentos/{id}/itens` have no frontend consumer; marked for
  delete-on-touch (keep for now per §5.2.7 cheap-to-keep policy).

## Dependencies

- Shared backend: `noctusai_lib`
- Shared frontend: `@noctusai/lib` + `@noctusai/lib/design-system`
- yfinance: real-time stock/asset quotes for watchlists and portfolio valuation
- APScheduler: recurring transaction auto-processing
- Supabase: Auth, database, RLS
