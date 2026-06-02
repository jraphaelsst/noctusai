# 09 — Deep-Dive: Financial Management (knowledge capture)

> Faithful capture of Orbity's finance system — the domain noc has **not** matured. All money in `numeric`/`DECIMAL(10,2)`; tenancy keyed on `agency_id`; cash-basis snapshots; pt-BR. Key files: `monthly-closure/`, `process-billing-reminders/`, `settle-gateway-payment/`, `reconcile-conexa-payments/`, `src/hooks/useFinancialMetrics.tsx`, `src/hooks/useDREStatement.ts`, `src/components/admin/*`; migrations `20250922193850` (genesis), `20251008123114` (expense_type), `20260224140801` (PPR genesis), `20260521002151` (PPR refactor), `20260525132252` (PPR DROP).

## 1. Finance domain model

Every money table shares a lifecycle shape: `amount` + `due_date (DATE)` + `status (payment_status ∈ pending|paid|overdue)` + `paid_date (DATE)` + `paid_at (TIMESTAMPTZ)`.

- **`clients`** (revenue source) — `monthly_value` (the MRR contribution), `due_date` (int day-of-month), `active`, `cancelled_at`, `contract_start/end_date`, `has_loyalty`, `default_billing_type ∈ {manual,asaas,conexa}`, `asaas_customer_id`, `conexa_customer_id`, `billing_automation_enabled` (per-client dunning opt-in).
- **`client_payments`** (AR) — one row/monthly invoice: `client_id`, `amount`, `due_date`, `status`, `paid_date/paid_at`, `amount_paid` (what actually landed, ≠ amount), `billing_type`, `gateway_fee`, `invoice_url`, `pix_copy_paste`; Asaas (`asaas_payment_id`) + Conexa block (`conexa_charge_id/sale_id/billet_url/pix_qr_code/pix_copy_paste/invoice_url/billing_status/raw_charge jsonb/last_sync_at`). **Net identity: `net = amount_paid − gateway_fee`.**
- **`expenses`** (AP, overloaded 3 ways via `expense_type ∈ {avulsa,recorrente,parcelada}`) — common: `name/amount/due_date/status/category/is_fixed/is_active`. Recurring: `parent_expense_id` (self-FK), `recurrence_day`, `subscription_status ∈ {active,paused,canceled}` (**kill-switch**); master = `parent_expense_id IS NULL`, children = generated months (`is_active=false`). Installment: `installment_current/total` advance monthly. SaaS/FX: `base_value`, `currency ∈ {BRL,USD,EUR}`, `exchange_rate`, `notification_sent_at`.
- **`expense_categories`** — per-agency `name/icon/color`, joined to expenses **by name string** (no FK — a looseness).
- **`employees`** — `base_salary`, `payment_day`, `is_active`, `role`, PPR cols `eligible_for_ppr`, `eligibility_weight`. **`salaries`** — generated monthly obligations: `employee_id`, `employee_name` (denormalized snapshot), `amount`, `due_date`, `status`.
- **`monthly_closures`** — idempotency+audit per `(agency_id, closure_month)`: counts `payments_generated/recurring_expenses_generated/installments_generated/salaries_generated` + `execution_details jsonb` + `executed_at`.
- **`monthly_snapshots`** — frozen month KPI: `total_revenue/total_expenses/total_salaries/net_profit/active_clients_count` + 7 status counts.
- **`billing_history`** — the OTHER axis: **Orbity charging the agency** (Stripe SaaS sub) — `subscription_id/stripe_invoice_id/billing_period/amount/status/invoice_url`. Don't conflate with agency-charges-its-clients.
- **`agency_payment_settings`** — dunning/gateway config: `active_gateway`, per-gateway keys/flags, `default_fine_percentage/interest_percentage/discount_percentage/discount_days_before` (BR multa/juros/desconto-pontualidade), reminder rules, `block_access_days/enabled`, per-gateway message templates.

## 2. Monthly closure procedure (`monthly-closure`)

Per-agency over `agencies WHERE is_active`, each isolated in try/catch (one failure ≠ abort run).

**Closure-level idempotency:** if a `monthly_closures` row exists for `(agency_id, currentMonth)`, return early (zero stats). Safe to run repeatedly; fires once per calendar month.

Then a fan-out, **each step with its own per-row existence check**:
1. **Client payments** — `clients WHERE active AND monthly_value>0`; `dueDay = due_date||10`; skip if a payment exists this month; else insert `{amount:monthly_value, due_date, status:pending}`.
2. **Recurring expenses** — masters: `expenses WHERE type=recorrente AND is_active AND subscription_status=active AND parent_expense_id IS NULL` (kill-switch filter); skip if child exists this month; else insert child (copy name/amount/category, `parent_expense_id=master`, `is_active=false`).
3. **Installments** — `expenses WHERE type=parcelada AND installment_current/total NOT NULL`; `next=current+1`; skip if exists; if `next≤total` insert at `due_date=orig+1mo`, chaining root. Terminates at last.
4. **Salaries** — `employees WHERE is_active`; `dueDay=payment_day||5`; skip if exists; else insert `{amount:base_salary, employee_name, status:pending}`.
5. **Snapshot** (below). 6. **Record closure** (closes the idempotency gate).

**Snapshot formula** (cash-basis — only `status='paid'` counts):
```
total_revenue  = Σ amount of payments WHERE paid
total_expenses = Σ amount of expenses WHERE paid
total_salaries = Σ amount of salaries WHERE paid
net_profit     = revenue − expenses − salaries
```
⚠️ Snapshot sums `amount` (not `amount_paid`) and ignores `gateway_fee` → snapshot revenue is gross-of-fees; the live FE engine uses `amount_paid` net of fees → **snapshot and live can diverge.**

## 3. DRE & KPIs (`useFinancialMetrics`, `useDREStatement`)

**Architectural fact:** `monthly_snapshots`/`monthly_closures` are **written by closure but never read by the FE** — every dashboard KPI recomputes **live** from raw tables. Snapshots are audit-only (effectively dead read-path).

**Two accounting bases side-by-side:** accrual/competência (`totalMRR`, `burnRate`, `profitability`) and cash/caixa (`paidRevenue`, `paidBurnRate`, `realProfitability`).

Core live KPIs:
- **MRR** = Σ `monthly_value` over `wasClientActiveInMonth` (active OR cancelled-after-monthEnd — keeps historical months honest post-churn).
- **burnRate** = expenses + payroll (ex-cancelled). **profitability** = MRR − burnRate; **margin** = profitability/MRR.
- **paidRevenue** = Σ `amount_paid||amount` of paid in month. **realProfitability** = paidRevenue − (paidExpenses+paidPayroll).
- **overdueAmount/Rate** (inadimplência) = pending/overdue with `due_date<today` & client active.
- **gateway fees & net** = `totalNetRevenue = paidRevenue − Σ gateway_fee`.
- **client profitability** = equal-allocation `costPerClient = burnRate/nActive`, per-client `margin=(fee−cost)/fee`, `isAtRisk` if <30%. (Coarse but actionable.)

**DRE income statement** (`useDREStatement`) — a proper Brazilian DRE:
```
Receita Bruta   = paid incomes (or forecast MRR)
(−) Impostos    = expenses whose category matches tax-keywords [imposto,tributo,taxa,das,simples,iss,irpj,csll,pis,cofins]
Receita Líquida = Bruta − Impostos
(−) Custos Oper = non-tax expenses
(−) Folha Pag   = salaries
= EBITDA        = Líquida − Custos − Folha ;  Margem% = EBITDA/Bruta
```
Tax detection is **string-keyword heuristic** on free-text category (fragile). Forecast mode derives an effective tax rate from the previous real month, fallback **6%** (Simples Nacional ballpark).

**Forecast mode** (selectedMonth > current): deterministic projection from sources-of-truth — one virtual revenue line per active client; recurring expenses via **anti-ghost** (active masters, most-recent child price, **drop subscriptions with no activity in 60 days**); payroll per active employee. Honest (zeros cash metrics, flags projected tax).

**Churn** (`ChurnAnalysis`): churnRate = cancelledInMonth/(active+cancelled)×100, lostMRR, 6-month trailing series.

## 4. PPR profit-sharing (built → DROPPED 2026-05-25)

> ⚠️ The PPR (Participação nos Resultados) subsystem was **fully dropped** (`20260525132252` drops 10 tables + 4 functions). The schema + staleness machinery are captured; the **calculation function bodies were created out-of-band (Lovable/dashboard) and are NOT in the repo** (appear only in DROP statements). Formula below reconstructed from schema/config — high-confidence on structure, not exact.

**Period (`bonus_periods`)** — gate + pool: `revenue_target/actual`, `profit_target (default 50k)/actual`, `net_profit`, `nps_target (default 60)/actual`. Pool via `bonus_pool_mode ∈ {percent_of_profit, manual}`: `pool = net_profit × ppr_percent/100` (default 10%) or `manual_amount`. `target_is_blocking` ⇒ revenue+NPS are **hard gates** (miss → no pool). `ppr_period_months` decomposes a period (quarter = Σ monthly pools). `ppr_financial_adjustments` = manual corrections feeding net_profit.

**Employee scorecard (`employee_scorecards`)** — 3 sub-scores (each default 0): `nps_retention_score`, `technical_delivery_score`, `process_innovation_score` → `weighted_average` (weights in `bonus_programs.config` jsonb) → `max_share` cap + `final_bonus`. Lifecycle draft→submitted→locked.

**Result (`ppr_employee_results`)** — reconstructed identity:
```
base_share_i  = pool × (eligibility_weight_i / Σ eligibility_weight)
bonus_amount_i = base_share_i × score_final_i   (capped at max_share)
```
pool → split by head-weight → scaled by weighted performance, capped. `ppr_calculation_logs` audits calc/close/reopen.

**Staleness triggers** (fully captured): `mark_ppr_periods_stale_by_date` + `trg_stale_from_payment_like` (on client_payments/expenses/salaries, derives date from `COALESCE(paid_at::date, paid_date)`, stales both old+new period on a moved date) + `trg_stale_from_adjustment` + `trg_stale_from_scorecard`. **Closed periods never re-staled (frozen).** `check_bonus_period_overlap` prevents two open periods overlapping.

## 5. Business-rule invariants (DB-enforced BEFORE-triggers, fail-closed)

- `validate_client_billing_type` / `validate_payment_billing_type` — billing_type ∈ {manual,asaas,conexa} or reject (protects gateway router from typos).
- `validate_expense_subscription_fields` — subscription_status ∈ {active,paused,canceled} ∧ currency ∈ {BRL,USD,EUR}.
- `check_bonus_period_overlap` — no overlapping open PPR periods.
- **Settlement idempotency** — `settle-gateway-payment` refuses to re-settle a `paid` payment (409); `reconcile-conexa-payments` tracks `already_paid`. Webhooks/polls safe to replay.
- NPS `score BETWEEN 0 AND 10`; PPR adjustments blocked against a **closed** period (RLS `WITH CHECK`).

## 6. Sophistication assessment (neutral)

**Genuinely strong / worth learning:** dual accrual-vs-cash accounting with `amount_paid`/`gateway_fee` netting; a proper BR DRE (tax-aware, history-derived effective rate, Simples fallback); the recurring master/child + kill-switch + anti-ghost forecast; idempotent two-layer closure with per-agency fault isolation; honest forecast mode; a mature dunning engine (opt-in, per-gateway templates, 3 date rules, dedup, BRT, rate-limit); the PPR design (revenue∧NPS-gated pool, eligibility-weight × 3-dim scorecard, staleness machinery).

**Rough / don't copy:** snapshots are write-only and disagree with live (use `amount` not `amount_paid`, ignore fees); category coupling by string + keyword tax detection (fragile); naïve equal-allocation client cost; **the whole PPR subsystem was ripped out** (over-built, formulas outside VCS); **RLS on core finance tables is `USING(true)`** (wide-open; scoping done only in app query — a multi-tenant security smell); `payment_status` enum drift (`cancelled` used in FE, not in captured enum).

**Verdict:** a mature, real-business agency finance module shaped by daily operational pain — the depth comes from real use, not a spec. The rough edges are fast-iteration artifacts. **Absorb the intent on noc's disciplined seam (RLS-via-trusted-table, no silent fallbacks), not the code as-is.**

## 7. Open questions
PPR calc function bodies not in repo (formula structure-confident, not exact); why PPR was dropped; whether an uncaptured migration adds `cancelled` to the enum; what schedules `monthly-closure`/`process-billing-reminders` (external Supabase config); where `gateway_fee` is populated (likely webhook payloads); whether any path was meant to read snapshots.
