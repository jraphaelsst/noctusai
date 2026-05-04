# Metas / goals primitive (seed-lib)

> `noctusai_lib.domain.metas` — value-and-target tracking primitives
> (Goal, Target, Progress, Period, Contribution, status state machine,
> period date-math). Lifted 2026-05-03 from PF (`metas_service.py`,
> `orcamentos_service.py`), ERP (`metas_service.py`,
> `meta_periodos_service.py`) and Daily Life (`goals_service.py`) per
> N=3 MUST-FORMALIZE (`KB § PATTERNS/project-execution.md § 2.7`),
> via `projects/metas-domain-seed-absorption/`.

---

## 1. When to use it

Any product that tracks values toward targets — financial goals,
sales quotas, habit check-ins, budgets, performance KPIs.

Use cases on the platform:

- **Personal Finance** — financial goals (target amount + accumulating
  contributions); per-category monthly budgets (planned vs spent).
- **ERP Imobiliário** — sales targets per period (diaria / semanal /
  mensal / anual) with proportional cascade from monthly to per-period
  via `proportional_target(...)`.
- **Daily Life** — habit check-ins accumulating into a `valor_atual`
  toward a target (count / minutes / kilometers — domain-neutral).

Do NOT use it for: arbitrary number-tracking that has no target
(use a counter table instead), KPI dashboards (the seed has no
visualization opinion), or recurring-task scheduling (use
`noctusai_lib.domain.scheduling`).

---

## 2. Public surface

```python
from noctusai_lib.domain.metas import (
    # value objects
    Goal, Target, Progress, Period, Contribution, ProgressTransition,
    # enums
    GoalStatus, PeriodKind,
    # progress
    compute_progress, accumulate_contribution, project_completion_date,
    # periods
    period_bounds, count_business_days, proportional_target,
    working_days_total_in_month, working_days_remaining_in_week,
    working_days_remaining_in_month, working_days_total_in_year,
    working_days_remaining_in_year,
    # status
    next_status, can_transition, from_pt_string, to_pt_string,
    # repository seam
    GoalRepository, InMemoryGoalRepository,
)
```

| Symbol | Kind | Role |
|---|---|---|
| `Goal` | dataclass | Snapshot — `(id, target, current, period, status, contributions)`. Frozen. |
| `Target` | dataclass | `amount: float`. Validates non-negative. |
| `Progress` | dataclass | Derived view — `(percent_complete, remaining, projected_completion_date, status)`. |
| `Period` | dataclass | `(kind, start, end?)`. Inclusive bounds. |
| `Contribution` | dataclass | `(amount, at)` — single increment toward a goal. |
| `ProgressTransition` | dataclass | `(new_current, completed, crossed_threshold_pct)` — output of `accumulate_contribution`. |
| `GoalStatus` | StrEnum | `pending / in_progress / on_track / at_risk / overdue / completed / abandoned`. |
| `PeriodKind` | StrEnum | `daily / weekly / fortnightly / monthly / quarterly / yearly / open_ended`. |
| `compute_progress(target, current, *, contributions, today, period_remaining_pct)` | fn | Pure derivation of Progress. |
| `accumulate_contribution(target, current, increment) -> ProgressTransition` | fn | Mirrors PF `adicionar_contribuicao` + Daily Life `register_checkin`. Detects 25/50/75/100 milestone crossings. |
| `project_completion_date(target, current, contribs, today)` | fn | Stdlib month-math ETA from monthly avg. |
| `period_bounds(kind, ref) -> (start, end)` | fn | Inclusive bounds. ERP fortnight/quarter conventions baked in. |
| `proportional_target(monthly, kind, ref) -> int` | fn | ERP's `_calcular_meta_proporcional` lifted verbatim + extended to QUARTERLY. |
| `count_business_days(start, end)` | fn | Mon-Fri, inclusive both ends. |
| `working_days_total_in_*` / `working_days_remaining_in_*` | fn | Helpers; `period_bounds + count_business_days` shorthands. |
| `next_status(current, *, percent_complete, period_remaining_pct?)` | fn | State-machine transition. Sticky terminals (COMPLETED / ABANDONED). |
| `can_transition(current, target)` | fn | Guard rail. |
| `from_pt_string` / `to_pt_string` | fn | PT-BR ↔ enum mapping (legacy products: `ativa`/`concluida`/`no_prazo`/`atrasada`). |
| `GoalRepository` | Protocol | Optional persistence seam for consumers that want to inject. |
| `InMemoryGoalRepository` | class | Reference / test default; not for production. |

---

## 3. What stays consumer-side

Same shape as `noctusai_lib.domain.scheduling`: the seed is pure
math + value objects + state machine. Persistence + access control +
schema-naming + status vocabulary stay in the product:

- **Schema names** — `metas` vs `orcamentos` vs `goals` vs `checkins`; product schema columns (`valor_atual` / `meta_realizada` / `valor_gasto`) mapped at the service-layer boundary.
- **Persistence** — Supabase queries with RLS, `org_id` / `user_id` filters, transactions.
- **HTTP / FastAPI** — routers, request DTOs, response envelopes — all product-side.
- **Status vocabulary** — products may persist `GoalStatus.value` directly OR keep their existing PT-BR strings and map via `from_pt_string` / `to_pt_string`.
- **Cron / batch generators** — ERP's `criar_metas_hoje()` (daily seeding from active configs) stays in ERP; the proportional math it calls lifts to seed.
- **Cross-table sync** — PF's `OrcamentosService.sincronizar_gastos()` (pulling actuals from `transacoes`) stays in PF; the percent / saldo math lifts.
- **Period parent-child cascade** — ERP's `gerar_trimestre` (quinzenal → mensal → trimestral nested period auto-generation) stays in ERP at N=1. Re-evaluate when N=2.

---

## 4. Wiring recipe (consumer side)

```python
from datetime import date
from noctusai_lib.domain.metas import (
    Target, Contribution, GoalStatus, PeriodKind,
    accumulate_contribution, compute_progress,
    period_bounds, proportional_target,
    next_status, from_pt_string, to_pt_string,
)


class MetasService:
    """Product-side service mapping schema ↔ seed value objects."""

    def __init__(self, db, org_id):
        self.db = db
        self.org_id = org_id

    async def adicionar_contribuicao(self, meta_id, valor):
        # Read current state from product table
        meta = self.db.table("metas").select("*").eq("id", meta_id).single().execute().data

        # Delegate to seed math
        transition = accumulate_contribution(
            target=float(meta["valor_alvo"]),
            current=float(meta["valor_atual"]),
            increment=float(valor),
        )

        # Persist results product-side
        update = {"valor_atual": transition.new_current}
        if transition.completed:
            update["status"] = "concluida"  # or to_pt_string(GoalStatus.COMPLETED)
        self.db.table("metas").update(update).eq("id", meta_id).execute()

        return transition

    async def obter_progresso(self, meta_id):
        meta = self.db.table("metas").select("*").eq("id", meta_id).single().execute().data
        contribs = self.db.table("meta_contribuicoes").select("*").eq("meta_id", meta_id).execute().data or []

        progress = compute_progress(
            target=Target(float(meta["valor_alvo"])),
            current=float(meta["valor_atual"]),
            contributions=[
                Contribution(amount=float(c["valor"]), at=date.fromisoformat(c["data"]))
                for c in contribs
            ],
            today=date.today(),
        )
        return {
            "percentual": progress.percent_complete,
            "faltam": progress.remaining,
            "data_previsao": progress.projected_completion_date.isoformat() if progress.projected_completion_date else None,
            "status": to_pt_string(progress.status),
        }
```

ERP's daily target seeding uses `proportional_target(...)` instead of
the in-product `_calcular_meta_proporcional`:

```python
target_today = proportional_target(
    monthly_target=cfg["meta_pretendida"],
    kind=PeriodKind.DAILY,
    ref=ref_date,
)
```

---

## 5. Status mapping

| PT-BR string  | `GoalStatus` enum            | Notes |
|---|---|---|
| `pendente`    | `PENDING`                    | Initial / before first contribution. |
| `ativa`       | `IN_PROGRESS`                | PF default after first contribution. |
| `em_andamento`| `IN_PROGRESS`                | Synonym. |
| `no_prazo`    | `ON_TRACK`                   | ERP default when progress keeps pace with period. |
| `atrasada`    | `AT_RISK`                    | ERP — progress lagging behind period elapsed. |
| `vencida`     | `OVERDUE`                    | Period ended without hitting target. |
| `concluida`   | `COMPLETED`                  | PF / ERP / Daily Life — `current >= target`. Sticky. |
| `completada`  | `COMPLETED`                  | Synonym. |
| `pausada`     | `ABANDONED`                  | User-paused; can resume. |
| `abandonada`  | `ABANDONED`                  | User-abandoned; can resume. |

The `*_pt_string` helpers exist so legacy products keep their existing
column values; new products should persist `GoalStatus.value` directly
(string-valued enum).

---

## 6. Tests

`seed/lib/backend/tests/domain/metas/` ships 5 test files / 111 cases:

- `test_value_objects.py` — frozen dataclasses, validators, enum values.
- `test_periods.py` — every `PeriodKind` × edge cases (Feb leap year, December → January, ISO-week Sunday boundary, Q1/Q2/Q4) + ERP's `_calcular_meta_proporcional` cases.
- `test_progress.py` — PF financial goal math (zero target, 25%, 100% cap, ETA from contributions, month-overflow, yyyymm grouping) + Daily Life accumulation + milestone crossings (25/50/75/100).
- `test_status.py` — PT mapping round-trips, transition guard rail, sticky terminals (COMPLETED + ABANDONED), period-remaining ↔ on-track/at-risk/overdue.
- `test_repository.py` — `GoalRepository` Protocol roundtrip via `InMemoryGoalRepository`; `LookupError` on missing.

---

## 7. Recurrence detection

Seed shape mirrors `noctusai_lib.domain.scheduling`. Future seed cycles
should fire on:

- `noctus.dev.scan_recurrence` if `_calcular_meta_proporcional` /
  `_period_end_date` / `obter_progresso` shapes reappear in a product.
- Any helper named `accumulate_*`, `compute_progress`, or
  `project_completion_date` that ships product-side without consuming
  the seed module.

---

## 8. Out-of-scope (deferred)

- **Frontend (TS) seed** — `useMetas` / `useGoals` hook pattern lift is a separate cycle (different layer, different recurrence trigger).
- **Period parent-child cascade** — ERP's quinzenal → mensal → trimestral auto-generation stays in ERP at N=1. Reopen when N=2.
- **Product wiring** — three follow-up cycles (`pf-metas-seed-wiring`, `erp-metas-seed-wiring`, `daily-life-goals-seed-wiring`) refactor each product's service file to call the seed.
- **Migrations** — no schema changes; products keep their tables verbatim. The seed maps to/from existing schema at the service boundary.

---

## 9. Doc-backed

- `seed/lib/backend/noctusai_lib/domain/metas/__init__.py` — public barrel + planned-occupants doc.
- `seed/lib/backend/noctusai_lib/domain/metas/{value_objects,progress,periods,status,repository}.py` — implementations.
- `seed/lib/backend/tests/domain/metas/` — test suite.
- `KB § PATTERNS/seed-lib-layout.md` — layer model the module obeys.
- `KB § PATTERNS/scheduling-seed.md` — canonical reference shape this mirrors.
- `KB § PATTERNS/project-execution.md § 2.7` — recurrence rule that triggered the lift.
- `projects/metas-domain-seed-absorption/PROJECT.md` — design + audit trail.
