# Personal Finance -- Master Prompt

## Purpose

Personal finance tracker for individuals. Multi-account transaction management, budgets with category limits, recurring transaction automation, investment portfolio tracking, stock watchlists with real-time quotes, financial goal tracking, and reporting/analytics dashboards.

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
- **categorias** -- hierarchical transaction categories (system defaults + user custom)
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

## Services (15)

ativos, carteira, categorias, contas, cotacoes, dashboard, metas, orcamentos, patrimonio, recorrentes, relatorios, transacoes, watchlist, **ai** (Phase 7 P1 indicators), **monthly_narrative** (Phase 10 P2-opp digest)

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
- **Org ID extraction**: Same as ERP -- `get_org_id(user)` from `dependencies.py`. Never inline metadata access.
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

502 tests across router and service test files.

## Dependencies

- Shared backend: `noctusai_lib`
- Shared frontend: `@noctusai/lib` + `@noctusai/lib/design-system`
- yfinance: real-time stock/asset quotes for watchlists and portfolio valuation
- APScheduler: recurring transaction auto-processing
- Supabase: Auth, database, RLS
