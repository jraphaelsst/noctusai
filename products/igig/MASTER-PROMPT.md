# IgIg — MASTER-PROMPT

> Authoritative development guide for the agency ERP.
>
> **This file used to describe IgIg as "the simplest possible product — ZERO
> domain code".** That was true at scaffold time (2026-08-09) and false by the
> end of the same day, when all six módulos landed. It stayed wrong until
> 2026-09-01. If you arrived here expecting a seed reference: that role belongs
> to `products/seed/` and `templates/product-seed/`, not to IgIg.

## Purpose

ERP for a **communication agency** (estratégia, design gráfico, copywriting,
gestão de redes sociais). Unlike a manufacturing or retail ERP it is centred on
**time-based project management** — the hours of the team are the cost — plus
rigid scope control, centralised brand intelligence, and automation of the
financial and publishing flows.

Canonical spec: `IgIg Agency/PROJETO-IGIG-ERP.md` (6 módulos).
Progress ledger: `IgIg Agency/CHECKLIST.md`.
Roadmap + promotion record: `project-history/roadmaps/igig-2026-08.md`.

## The six módulos → where they live

| # | Módulo | Backend | Frontend |
|---|---|---|---|
| 1 | CRM, orçamentos, onboarding | `comercial_router` · `cliente_router` | `Comercial` · `Clientes` |
| 2 | Repertório / Central da Marca (+ Cofre) | `marca_router` | `Marca` · `RepertorioSidebar` |
| 3 | Planejamento editorial + copywriting | `pauta_router` | `Calendario` |
| 4 | Esteira de produção + portal de aprovação (**the MVP**) | `esteira_router` | `Esteira` · `AprovacaoPublica` |
| 5 | Distribuição e métricas | `distribuicao_router` · `integracoes_router` | `Distribuicao` · `Integracoes` |
| 6 | Financeiro e contratos | `financeiro_router` | `Financeiro` |
| — | Custo/hora (feeds 1, 5 and 6) | `custos_router` | `Custos` |

## The custo/hora spine — read this before touching pricing

`funcao` (role default) + `profissional` (per-person override), resolved by
`ProfissionalRepository.custo_hora_efetivo`. **One definition, three
consumers**: M1's calculadora de escopo, M5's BI de eficiência, M6's DRE.

Two invariants that are easy to break:

- **`NULL` and `0` are different.** `NULL` override means "inherit the
  função"; `0` is a real rate (an unpaid intern). Collapsing them silently
  reprices people. The API uses `exclude_unset` (never `exclude_none`) so an
  explicitly-sent null survives.
- **An undefined rate is reported, never defaulted to zero.** A person with
  neither a função nor an override comes back as `custo_hora_indefinido:
  true`, and the UI flags them. A zero that actually means "no input" reads as
  a real answer and overstates the margin on every account they touch.

This surface shipped its tables, RLS and repositories on 2026-08-09 but had **no
router and no page** until 2026-09-01, so all three consumers reported R$ 0,00.
That is the shape to watch for: a complete lower stack is not a shipped feature.

## Architecture

Seed-first. Backend is `create_product_app()` from `noctusai_seed`; frontend is
`createProductApp()` + `createProductLayout()` from `@noctusai/seed`; vite via
`createViteConfig({ port: 8170 })`.

- **Persistence** — `noctusai_lib.integrations.persistence` (Protocol + Fake +
  SQLite + Supabase + factory). Domain data goes through `app/store.py`; auth
  stays on Supabase. `get_repositorios` is RLS-scoped from the caller's JWT;
  `get_repositorios_admin` is service-role and is for the **public approval
  portal only**.
- **Schema** — `igig`, dual-dialect. Every `00N_igig_*.sql` needs a
  `migrations/sqlite/` mirror (`tests/test_schema_parity.py` enforces it).
  Framework-table migrations (`005`, `013`, `014`) deliberately omit the
  `_igig_` infix so they are out of that glob.
- **Page visibility** — `status_pagina` gates the nav, and an **unlisted route
  is hidden**. The layout only falls back to the unfiltered nav when the table
  returns EMPTY, so registering a subset is worse than registering none:
  migration `014` registers every shipped route for that reason.

## Rules

- Domain language is pt-BR (cliente, marca, pauta, tarefa, refação,
  apontamento); code constructs are English; user-facing errors pt-BR.
- Never let a missing input render as a confident zero — say it is missing.
- Auth tests assert strict `== 401`.
- Request models are `StrictHttpModel` (unknown key ⇒ 422).
- `IGIG_COFRE_KEY` is a boot requirement; without it the Cofre and Integrações
  refuse every write rather than storing plaintext.

## Deliberately not built (vendor-side, each with a named destination)

Channel publishing (`NOC-REMEDIATE[igig-publishing]`), signature providers
(`NOC-REMEDIATE[igig-assinatura]`), payment gateway + NFS-e, onboarding
dispatch (`NOC-REMEDIATE[igig-onboarding]`), Agenda ↔ Google Calendar.
Nothing is ever marked published or paid without platform confirmation.

## Testing

```bash
cd products/igig/backend  && pytest              # 330 tests
cd products/igig/frontend && npx tsc --noEmit    # must be clean
cd products/igig/frontend && npx vitest run      # 56 tests
cd products/igig/frontend && npx vite build      # must build clean
```

## Dependencies

- Backend: `noctusai_lib` + `noctusai_seed`
- Frontend: `@noctusai/lib` + `@noctusai/seed`
