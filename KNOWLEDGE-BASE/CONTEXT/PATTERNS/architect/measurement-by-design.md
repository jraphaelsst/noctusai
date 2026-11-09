# Measurement by design — every product feature generates data

> **Owner rule 2026-11-09 (verbatim):** "visitas should be objects in the db and have their own tables so we can track all of them and generate data for metrics and performance analysis in the future. everything inside our products, all of them, must be measured, we are building data-driven organisations, so our design should generate data for us to analyse then. doc this as a rule and please gate this so we always have measurement-data-mindset when we are building. metrics and statistics are life, for that we need data."
>
> Owned by architect; executed by backend-engineer / tooling-engineer. Self-contained. Sources at the end.

## 1. The rule

**A feature is not done until the data it produces can be counted, sliced and trended.** The schema, not a later analytics project, makes that true.

This EXTENDS `KB § PATTERNS/architect/event-oriented-architecture.md` (EOA) and does not replace it:

- EOA says **how a state change is recorded** (immutable, intent-named, same transaction).
- This doc says **what must exist so there is something to measure**: entities as rows, dated, attributed, with enumerated outcomes and one derivation for each metric.
- It is a separate doc because EOA is a storage/architecture decision (E1 vs E2, outbox, CloudEvents). The measurement contract applies to every feature, including ones with no integration event at all, and has its own gate.

## 2. The contract (checklist for every feature)

1. **Business things are rows.** A thing with its own lifecycle gets its own table: a `visita` is a row in `visitas`, never an element of a `jsonb` array or a text field inside `roteiros`. If you would ever count it, filter it or time it, it is a row. `jsonb` holds *extra facts of one row* (an event's `dados`), never a list of entities.
2. **Every row is dated and attributed.** `created_at timestamptz NOT NULL DEFAULT now()` (pt-BR `criado_em` is fine); `updated_at` + trigger where rows mutate; an actor (`created_by` / `ator_id`) where a person, agent or system caused it. Without `created_at` a row cannot be counted per day, week or cohort.
3. **Every lifecycle change is captured, append-only, in the same transaction.** A `status` / `etapa` / `fase` column answers "where is it now"; it cannot answer "how long was it in each stage, who moved it, how many came back". Each change appends one event row: **who, when, from, to** (plus `tipo` = the business intent, past tense). The service inserts the event beside the state `UPDATE`, in one transaction (EOA §5). The event table is append-only (no grant, or a trigger that refuses `UPDATE`/`DELETE`).
4. **Outcomes are enums.** A result (`ganho`/`perdido`, `realizada`/`cancelada`/`nao_compareceu`) is a `CHECK (... IN (...))` column (or a Postgres enum), never free text: free text does not aggregate. Keep the explanation in a separate `*_motivo` / `*_obs` text column.
5. **One derivation per metric.** A metric (conversion, time-in-stage, no-show rate, visits per corretor per week) is computed in ONE place (a SQL view, a service function or a projection, `KB § PATTERNS/backend/projection-reconcile.md`) and consumed by dashboards, reports and agents. Never re-derive it per page.
6. **Money, time and quantities are typed.** Integer cents, `timestamptz`, numeric: never a string that has to be parsed back before it is summed.
7. **The contract names it.** The contract for the feature (skill `noc-contract-first`) has a **"Records / Metrics"** section: *what does this feature record* (tables, events, enums) and *which metrics does that enable*. A feature whose contract lists no metric is asked "so how will we know it works?" before it is built.
8. **Personal data stays out of events** (reference people by id; EOA §5.6, LGPD). Measuring is never a reason to copy PII into a payload.

Pure lookup / catalog / cache / config / join tables carry no lifecycle and are exempt (§4). If you are unsure, the question is "would anyone ever ask *how many / how long / how often* about a row of this table?". If yes, it is measurable.

## 3. Worked example: Roteiro de visitas (social-wiring)

The owner's trigger. Before: a visit was a field inside the roteiro, so nobody could ask how many visits were made, cancelled or rescheduled.

| Rule | How the slice applies it |
|---|---|
| Entities are rows | each visit is its own row (`visitas`) pointing at its roteiro by FK, not an element of a list inside the roteiro. |
| Dated + attributed | every row has `criado_em`; `roteiro_eventos.ator_id` records who acted. |
| Append-only events | `roteiro_eventos` (`tipo` CHECK-enum: `roteiro_criado`, `roteiro_gerado`, `visita_adicionada`, `visita_resultado`, `visita_reagendada`, `data_alterada` ...; `de`, `para`, `dados`, `ator_id`, `criado_em`), no UPDATE/DELETE for anybody, written in the same transaction as the change. |
| Outcome enums | `status` CHECK `('pendente','realizada','cancelada','nao_compareceu','reagendada')`; who cancelled and why are their own CHECK-enums (`cancelada_por`, `cancelada_motivo`), and `resultado_em` / `resultado_por` date and attribute the outcome. |
| Metrics enabled | visits per corretor/week; realised / cancelled / no-show / rescheduled rates, cancellation reasons; time from `roteiro_criado` to `roteiro_gerado`; reschedule chains (`visita_reagendada` → `nova_visita_id`). All are `GROUP BY` over rows, not text parsing. |

(Source: the social-wiring roteiro-ciclo slice: its migration `338_roteiro_ciclo_de_vida` and contract file `roteiro-ciclo-CONTRACT.md`, on branch `feat/sw-roteiro-ciclo-be` until it lands.)

## 4. The gate: `check_measurable_by_design` (build triad)

| Leg | Mechanism |
|---|---|
| **Construction** | `noctus.dev.scaffold_migration` `with_table` already emits `created_at` / `updated_at`; `with_eventos=True` also emits the companion append-only `<table>_eventos` table (who / when / from / to, actor, append-only trigger). Interim shape: when the EOA E1 `transition_log_migration` primitive is on `dev`, the scaffold switches to it (EOA §5.1) and the keeper accepts both. Skill `noc-contract-first` carries the "Records / Metrics" leg. |
| **Backstop** | keeper `check_measurable_by_design` (`--check-measurable-by-design`), pre-commit over the staged ADDED migrations (**WARN-first shadow since 2026-11-09**: it prints and records but does not yet fail the commit; after >=7 days of telemetry a `{since, fires, fix_rate}` record goes in the gate inventory and the hook's failure branch becomes `exit 1`, per `KB § PATTERNS/common/gate-methodology-sync.md`); with no `--paths` it scans the migrations the branch added vs `origin/dev`. **Delta only: the historical tree is never flagged** (that tree is the ratchet baseline; its debt is reported in §5, not blocked). |
| **Telemetry** | every run is a `keeper:check-measurable-by-design` pass/deny event (cli exit wrapper → gate telemetry → `noctus.dev.gate_alignment` walls report); every `-- measurable:` escape is an `allow` event with its reason. |

### What it detects

| Rule id | Detects | Severity |
|---|---|---|
| `missing_created_at` | new domain table with no creation timestamp (`created_at`, `criado_em`, ..., or any `*_at`/`*_em` timestamp defaulting to `now()`) | **high** (blocking class) |
| `lifecycle_no_events` | a table gaining a status/etapa/fase/estado-like column (CHECK-enum or enum type) with no companion append-only capture anywhere in the product's migrations: a `<t>_eventos/_transicoes/_historico/...` table, ANY event-ish table that `REFERENCES` it, an audit/transition trigger on it, a trigger feeding a `*_movimentos` ledger, or the transition-log / event-store primitive | **high** (blocking class) |
| `outcome_free_text` | `resultado` / `outcome` / `desfecho`-like column typed free `text` without CHECK | warning |
| `mutable_no_updated` | lifecycle table with no `updated_at` | warning |
| `event_no_actor` | event/transition table with no actor column | warning |
| `escape_reason_short` | a `-- measurable:` marker with a reason under 10 chars | **high** |

### Exemptions (by heuristic, tuned on evidence)

- tables named `*_cache`, `*_config`, `*_settings`, `*_lookup`, `*_catalog`, `*_locks`, `*_queue`, `*_outbox`, `*_chunks`, `*_embeddings`, `*_sync`/`*_cursor`, `status_pagina`, ...;
- singleton / natural-key settings rows (the primary key is not a surrogate `id`) and pure composite-PK join tables;
- tables that ARE a measurement record (`*_runs`, `*_metrics`, `*_audits`, `*_messages`, `*_deliveries`, `*_execucoes`, `*_snapshots`): the row is its own dated event, no companion needed;
- event tables themselves (never asked for events about events);
- a product's first migration `001_*` (the scaffold copy of the seed baseline) and organ-generated migrations (`generated by noctusai_lib ...`): the seed organ owns that design and it is reviewed once, in the organ.

### Escape

`-- measurable: <reason, >=10 chars>` (whole file) or `-- measurable[<table>]: <reason>` (one table). Valid reasons are real exceptions: "derived read-model rebuilt from visitas_eventos", "static reference data loaded once". "n/a" or "later" fails (`escape_reason_short`). Every escape is recorded as telemetry; a pattern of escapes for the same reason is a gap in the rule or the heuristic, to be fixed there (`noctus.dev.gate_alignment walls`).

## 5. False-alarm research (2026-11-09)

Method: the detector was run over the **60 most recently added product migrations still on disk** (all products) and over the **whole tree (788 files)**, then every distinct hit was read and classified; each false-alarm class found became an exemption in §4 (and a test).

| Scope | First prototype | After tuning |
|---|---|---|
| Last 60 migrations: blocking hits | 27 (15 `lifecycle_no_events` + 12 `missing_created_at`) | **1** (`julia_relatorios.envio_status`, a real lifecycle with no history) |
| Last 60 migrations: warnings | 15 | 0 (warnings are advisory; shown, never blocking) |
| Whole tree (historical debt, NOT blocked): blocking hits | 250 | 123 (115 `lifecycle_no_events`, 8 `missing_created_at`) |

False-alarm classes removed by evidence: the organ-generated finance tables (5 renders of the same 13-table organ, the bulk of the first run); sync cursors / singleton settings / kill-switch rows (`fin_gateway_sync`, `plataforma_controles`, `julia_relatorio_destino`); run/metric/audit tables whose `status` is their own record (`ai_source_sync_runs`, `turn_metrics`, `tool_call_audits`, `imoveis_sync_execucoes`); the seed baseline copied into every scaffold (`invitations`, `status_pagina`); a movement ledger keyed by `entidade_id` instead of a FK (`pipeline_movimentos` for `website_leads`); local timestamp names (`alterado_em` ... `default now()`).

Reading of what remains (a rough manual read of ~23 distinct blocking hits sampled from the historical tree, not a rigorous audit): most are real lifecycle tables with no history (e.g. `roteiros`, `lais_visitas`, `appointments`, `payouts`, `treatment_plans`, `contracts`, `assinaturas`); a minority are residual false alarms (external-mirror metadata such as a vendor `privacy_status`; catalog tables like `cs_nichos`). On recent work the gate fired once in 60 migrations and that hit was correct; the real worked-example migration (338) passes clean. The two blocking-class rules are kept at `high` (shadow now, blocking after the 7-day record) because the gate is delta-only and has a recorded escape; the residual false alarm classes are what the escape telemetry is watched for. **Promotion of the warning rules to blocking waits for escape/deny telemetry, not for a decision made today.**

Debt, not blocked, tracked as a number: 123 historical blocking-class tables. Burn it down opportunistically when a table is next touched (fix-on-contact), not in a sweep.

## 6. Reviews

- `architect`: every new table with a status/etapa column or a lifecycle gets "what does it record, which metrics does it enable?" before the contract is signed.
- `backend-engineer`: writes the event beside the state change, in one transaction; never an `UPDATE` without its event row.
- `frontend-engineer`: a screen that shows a count/duration/rate reads the one derivation (rule 5), and the actions it offers must each correspond to a recorded event.
- `test-engineer`: asserts the event row exists after the action (the event is part of the behaviour, not a side effect).

## 7. Sources (read 2026-11-09)

- EOA in this KB: `KB § PATTERNS/architect/event-oriented-architecture.md` §1, §3, §5 (events are immutable, intent-named, same transaction) and `KB § PATTERNS/backend/audit-trail.md` (request-level history of every mutating call).
- Kimball & Ross, *The Data Warehouse Toolkit*: model business processes as fact rows with a date and a grain, with descriptive attributes as dimensions (the reason a visit is a row, and an outcome an enumerated attribute).
- Martin Fowler, *Audit Log* and *Temporal Property* (martinfowler.com/eaaDev): a current-state column plus an append-only record of changes is how past state is answered.
- Microsoft Azure Architecture Center, *Event Sourcing pattern*: events capture intent; the current row is not enough for "what was true at time T".
- Sadowski et al., *Lessons from Building Static Analysis Tools at Google* (CACM 2018): the false-positive budget used for the keeper (block only on near-zero effective false positives; start advisory; keep an escape).
