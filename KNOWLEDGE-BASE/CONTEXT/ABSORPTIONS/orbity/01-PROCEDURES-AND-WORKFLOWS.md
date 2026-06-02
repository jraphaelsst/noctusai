# 01 — Procedures & Workflows ⭐

> The centerpiece. This is the **operational knowledge** encoded in Orbity: the automated procedures a marketing agency runs every day, reconstructed step-by-step from the actual code. Each procedure lists its **trigger → steps → outcome → the rules/edge-cases that make it actually work**. These are the flows we must preserve the *intent* of when restructuring into noc.

**Source files referenced throughout** (under `sistema-orbity/`):
`supabase/functions/_shared/automation-engine.ts`, `process-lead-qualification/`, `capture-lead/`, `whatsapp-webhook/`, `process-automation-pending-actions/`, `process-billing-reminders/`, `monthly-closure/`, `send-daily-digest/`, `agency-onboarding/`, plus migrations `20260523123000_whatsapp_automation_flows.sql` (+ `_trigger_conditions`, `_schedule_window`), `20251015230940_*` (contracts), `20260224140801_*` (PPR/NPS/scorecards).

---

## 1. Lead capture → qualification → Meta feedback loop

**The highest-leverage idea in the codebase.** Orbity doesn't just *score* leads — it feeds quality back to Meta's ad algorithm so the platform optimizes for leads that actually convert, not raw volume. Most CRMs miss this.

### 1a. Capture — `capture-lead/{agency_id}` (public endpoint, `verify_jwt=false`)
**Trigger:** a lead arrives from a Facebook lead-ads webhook, a custom web form (GET or POST), or WhatsApp.
**Steps:**
1. Known keys (`name / email / phone / company / source / value`) map to `leads` columns; **everything else lands in `custom_fields` JSONB** (the raw form answers — critical, because scoring reads them).
2. Phone normalized to Brazilian `55…` form (see `_shared/phone.ts`).
3. Insert the `leads` row (default funnel stage "Novo").
4. Fire **two async, non-blocking** calls: `process-lead-qualification` and `automation-trigger` (trigger type `lead_created`).

### 1b. Qualification scoring — `process-lead-qualification` (the crown jewel)
**Trigger:** invoked from capture (and on demand). **Outcome:** lead gets a `temperature` (hot/warm/cold) + `qualification_score`, and Meta is told.
**Steps:**
1. **Resolve which form the lead came from** via a priority chain: `custom_fields.form_id` → `facebook_lead_sync_log.lead_data.form_id` → **infer by question-key overlap** against `lead_scoring_rules`.
2. **Score answers** against that form's `lead_scoring_rules`. **Matching is accent-folded + underscore/space-normalized on BOTH the question and the answer** (NFD strip) — this handles Meta's `full_name` snake_case vs a human rule labeled `"full name"`, and pt-BR accents. (Unglamorous but it's what makes pt-BR form-field matching work at all.)
3. Any rule flagged `is_blocker` short-circuits the score to **−10**.
4. **Classify temperature:** `score ≥ 5 → hot`, `≥ 2 → warm`, else `cold`; a blocker ⇒ cold. Upsert `lead_scoring_results` (unique per lead) and stamp `leads.temperature / qualification_score / qualification_source`.
5. **Fire Meta Conversions API (CAPI) events** — server-side, SHA-256-hashed PII, deduped via `meta_conversion_events` (unique per `lead_id + event_name`):
   - every lead → `Lead`
   - hot → additional `QualifiedLead`
   - cold → additional `ColdLead`
   - lead `value` flows through as `Purchase` conversion value (BRL).
6. **Pipeline-event mode:** CRM stage changes also map to Meta events — `scheduled → Schedule`, `proposal → SubmitApplication`, `won → Purchase`. So both *quality* and *progression* train the ad algorithm.

**Rules that matter:** dedup on `meta_conversion_events` prevents double-counting; PII is always hashed before leaving the server; form resolution degrades gracefully (3-step chain) rather than failing.

---

## 2. The WhatsApp automation flow engine

**A full no-code visual flow-builder + durable state machine** (`_shared/automation-engine.ts`, ~527 lines) that **replaced** all the legacy bespoke ghosting/cadence cron workers. Adding a new automation is now a *row*, not a deploy. This is the closest analog to a noc seed automation/domain organ and the single richest piece to study.

### Data model
| Table | Role |
|---|---|
| `automation_flows` | flow definition: `trigger_type`, `trigger_config` (incl. `schedule_window`, keyword), `stop_rules`, `metrics` counters, `status` |
| `automation_steps` | ordered steps (`position`), soft-delete |
| `automation_executions` | one row per (lead × flow); status `running / waiting / paused / completed / stopped / failed` |
| `automation_pending_actions` | **the durable work queue**: `run_at`, `idempotency_key`, retry `attempts` |
| `automation_execution_logs` | append-only audit trail (`flow_entered`, step events, `schedule_window_rescheduled/resumed`, …) |

### Triggers (the single entry point `triggerAutomationFlows(db, {agencyId, leadId, triggerType, payload})`)
Called from `whatsapp-webhook` (`whatsapp_message_received`, which also matches `keyword_received`), `capture-lead`/`facebook-leads` (`lead_created`), and `automation-trigger`. Plus a PL/pgSQL mirror `start_automation_flows_for_lead()` (SECURITY DEFINER) so a flow can also start from a direct DB insert.
- Loads **active, non-deleted** flows matching the trigger type.
- Per flow: keyword-match gate → **conflict avoidance** (skip if an ACTIVE execution already exists for this lead, unless `avoid_conflicts:false`) → trigger-condition evaluation → `start()`.

### Start → enqueue (`start()`)
1. Insert `automation_executions` (a **unique partial index `(flow_id, lead_id) WHERE status IN (running,waiting)`** enforces one-active-execution-per-lead; a `23505` collision ⇒ "active execution exists" ⇒ skipped). **Concurrency safety lives in the DB, not the worker.**
2. Log `flow_entered`, increment the `entered` metric.
3. Enqueue the first step into `automation_pending_actions`.
4. **Schedule window:** `trigger_config.schedule_window` (timezone default `America/Sao_Paulo`, days default Mon–Fri, start/end times default 08:00–17:00). If "now" is outside the window, defer `run_at` to the next allowed slot (hand-rolled, timezone-correct UTC conversion) — so a drip never fires at 3 a.m.

### Worker → step machine (`process-automation-pending-actions`, cron every 1 min)
1. Select due pending rows (`run_at ≤ now`).
2. **Atomic optimistic lock** per row: `UPDATE … SET status='processing' WHERE status='pending'` returning the row (so two workers can't claim the same action).
3. `processPendingAction()` runs the step. **Step types:**
   - `send_whatsapp` / `send_whatsapp_media` — render `{{var}}` template against lead fields/custom-fields/assignee, call `whatsapp-send` via service-role HTTP.
   - `delay` — re-enqueue with future `run_at`.
   - `condition` — evaluate; `on_false: stop | continue`.
   - `branch` — jump to true/false `position`.
   - `action` — one of `create_task`, `move_lead`/`update_status`, `add_tag`/`remove_tag`, `assign_owner`, `notify_team`, `pause`, `end`.
4. Each step logs an event, increments flow metrics, then `next()` advances by `position` or completes.
5. **Retry backoff** on failure: `1 → 5 → 15 min`, give up at the **4th** attempt (execution → `failed`, `errors` metric++). **Idempotency key `executionId:stepId`** prevents double-enqueue.

### Message templating
`{{nome}} {{telefone}} {{responsavel}} {{servico_interesse}} {{data_reuniao}} {{campanha}} …` rendered from the lead, with assignee-name lookup.

### Stop rules (the ghosting / anti-spam logic) — checked every step + on inbound reply
- `stop_on_reply` — lead answered → halt + count `responses_received`. (This is how a human reply kills the drip — see §6.)
- `stop_on_final_status` — lead reached a won/lost/cliente set → halt.
- `stop_on_tag_added` — a configured tag appears → halt.
- `avoid_conflicts` — only one active execution per lead (DB-enforced, above).
- **Schedule-window re-check on every resume:** out-of-window steps re-park with `__schedule_window_waiting` markers and log `schedule_window_rescheduled / resumed`.

> **Lesson (carry the intent):** this is a clean, durable, self-healing **Postgres-native job queue** — atomic-claim, backoff-retry, idempotency dedup, self-cancellation when state invalidates the action. Orbity deleted a pile of per-concern crons in favor of this one engine.
> **Cost to note:** the start/condition logic is mirrored in BOTH TS (edge) and PL/pgSQL (DB trigger) — two implementations of one contract to keep in sync (noc's DRY / contract-first discipline would flag this; pick one home on absorption).

---

## 3. Billing reminders (`process-billing-reminders`, daily cron, BRT-aware)

**Trigger:** daily pg_cron (`daily-billing-reminders`, 12:00). **Outcome:** clients get WhatsApp dunning on the right dates, never twice a day, only if opted in.
**Steps (per agency where `notify_via_whatsapp`):**
1. **Resolve the right WhatsApp instance** — a dedicated `purpose='billing'` line, **falling back to `general`** (agencies separate dunning from sales chat).
2. Compute three target dates from per-agency settings: due-date reminder, **N-days-before** reminder, **M-days-overdue** chase.
3. Pull `client_payments` (pending/overdue) due on those dates — **only for clients with `billing_automation_enabled`** (per-client opt-in).
4. Pick the gateway-and-type-specific template (`manual_template_reminder`, `conexa_template_overdue`, `asaas_…`).
5. **Deduplicate** via `notification_tracking` keyed `billing_{type}:{today}+payment_id` — never double-dun in a day.
6. Send through unified `whatsapp-send`, **1-second rate-limit between sends**, log every attempt to `billing_message_logs`.

---

## 4. Monthly closure (`monthly-closure`, per-agency, idempotent)

**The financial heartbeat.** **Trigger:** pg_cron `monthly-closure-job` (1st of month, 00:00). **Outcome:** the month's billing + a frozen financial snapshot. Guarded by `monthly_closures` (one run per agency per month; every step existence-checks before insert → fully re-runnable).
**Steps:**
1. Generate a `client_payment` for every active client (amount = `monthly_value`, due on their `due_date` day-of-month).
2. Generate **recurring expenses** from "master" expense rows (`expense_type='recorrente'`, gated by `subscription_status='active'` kill-switch); child rows linked by `parent_expense_id`.
3. Advance **installment expenses** (`parcelada`): next parcel if `installment_current + 1 ≤ installment_total`.
4. Generate **salaries** from active `employees` (amount = `base_salary`, on `payment_day`).
5. Write a **`monthly_snapshots`** record: `total_revenue / total_expenses / total_salaries`, **`net_profit`**, active-client count, paid/pending/overdue counts.

> **Lesson:** `monthly_snapshots` is the **join between finance and everything else** — computed once at closure, then *read* by dashboards, the PPR bonus pool (§8), and reports, instead of recomputing live aggregates. **Frozen-at-event-time financials = consistency + cheap reads + audit trail.**

---

## 5. Daily digest email (`send-daily-digest`, 08:00 BRT cron)

**Trigger:** pg_cron `daily-summary-notification` (~11:00 / 08:00 BRT). Opt-in via `user_notification_channels.email_digest`.
**Steps:** for each opted-in user, roll up the **prior day's** `notifications` into one branded HTML email (via **Resend**); **skip users with zero events**; log to `notification_delivery_logs`. (Digest off ⇒ one email per notification.)
Notifications themselves fan out across channels — in-app, email, push (web-push), Slack, Discord, custom webhooks — governed by a `notification_queue` + per-event preferences matrix (`notification_event_preferences`). Same-user/type/entity events are **aggregated within a 5-minute window** (`insertOrAggregateNotification`). See `RESUMO_EMAIL_DIARIO.md` for the original cron-setup notes.

---

## 6. Inbound WhatsApp reply handling (`whatsapp-webhook` → engine)

**Trigger:** UAZAPI inbound webhook (unauthenticated, `verify_jwt=false`). **Outcome:** message persisted, drips killed, keyword bots started, lead promoted.
**Steps:**
1. Extract message content (defensive normalization across ~10 candidate payload paths — see `_shared/uazapi.ts`).
2. **Idempotent insert** to `whatsapp_messages` (`is_from_me=false`).
3. **Auto-promote the lead** out of its initial column on first reply (respects `whatsapp_auto_contact`).
4. **`stopExecutionsForLeadReply()`** — halt every active automation honoring `stop_on_reply`, bump the `responses_received` metric. (A human reply ends the drip.)
5. **`triggerAutomationFlows('whatsapp_message_received')`** — may start keyword flows.
6. Conversation resolution / merge (`resolve-whatsapp-conversation`, `find_lead_by_normalized_phone`, BR 9th-digit variant matching in `_shared/phone.ts`).

---

## 7. Agency onboarding (`agency-onboarding`, 8 steps, idempotent)

**Trigger:** master/admin provisions a new agency (the SaaS signup). **Outcome:** a ready-to-use tenant on a 7-day trial.
**Steps:**
1. Create the auth user (role `agency_admin`).
2. Create the `agencies` row with an **auto-unique slug**.
3. Add the user as `owner` in `agency_users`.
4. `start_agency_trial` RPC (7-day trial).
5. Write the `agency_onboarding` checklist record (`step_current / step_total`).
6. Send a WhatsApp **welcome** via `master-whatsapp`, stamping `welcome_message_sent_at`.
**Rules:** idempotent throughout (re-runnable; detects existing user/agency/subscription). Plan limits live on the agency row: `max_users / max_clients / max_leads / max_tasks` (enforced by `check_agency_limits`). FE onboarding is a 6-step wizard with a checklist + checkout (`onboarding-checkout`), plus profile flags `onboarding_completed / welcome_seen`.

---

## 8. Client lifecycle, contracts & PPR profit-sharing

### 8a. Client lifecycle inside an agency
A `client` is onboarded with `monthly_value` + `due_date` (day-of-month) → a **contract** is generated → **monthly closure** auto-creates the recurring `client_payment` each month → **billing reminders** chase it via WhatsApp → optionally **fiscal-invoiced** via Conexa. In parallel the client gets paid-traffic management, a social content pipeline, and a public ads report.

### 8b. Contract = fiscal-data snapshot (not FK soup)
The `contracts` table **copies** agency + client CNPJ/address/representative at signing time (plus services JSONB, witnesses, custom clauses — a Brazilian legal document). **Snapshot-on-legal-event** is deliberate: a legal document must reflect facts as-of-signing even if the client later edits their profile. Generated via a multi-step wizard (client → services → witness) with an AI "smart generator" and `@react-pdf/renderer`.

### 8c. PPR (Participação nos Resultados) — profit-sharing
**Trigger:** monthly, fed by `monthly_snapshots.net_profit`. **Outcome:** per-employee bonuses gated by company performance.
**Model:** monthly net-profit → `bonus_pool` (a % of profit, **gated by revenue + NPS targets**) → per-employee `employee_scorecards` (weighted: NPS-retention, technical-delivery, process-innovation) → `final_bonus`. Staleness triggers (`trg_stale_from_payment_like`, `trg_stale_from_scorecard`, `mark_ppr_periods_stale_by_date`) recompute periods when underlying finance/scorecard data changes. Tables: `bonus_programs`/`bonus_periods`, `ppr_employee_results`/`ppr_period_months`/`ppr_calculation_logs`/`ppr_financial_adjustments`, `employee_scorecards`, `nps_*`.

---

## 9. Supporting operational flows (briefer)

- **Paid-traffic optimization cadence** — `traffic_controls` per client (platforms, `daily_budget`, `result` excellent→terrible, `situation` improving/worsening, `last_optimization`); `OptimizationReminder`/`OptimizationSheet` nudge the gestor to tune campaigns on a cadence. FB sync via `facebook-sync-cron` (every 8h) + `facebook-heartbeat` (token health, 4h).
- **Public client report** — `public-client-report` looks up `clients.report_token` (expiry-checked), serves a frozen ad-report `report_snapshot` with no auth. The agency shares a link; the client sees spend/CPA/conversions/top-campaigns.
- **Social content approval** — campaigns → `social_media_posts` (platform, schedule, hashtags, attachments) → role assignments (designer/editor) → `task_approvals`/`social_media_approval_rules` → public `/approve/:token` (`approval-get`/`approval-decide`) with expirations.
- **Bulk import** — `process-batch-import` mass-imports clients/leads/tasks from Excel, **chunked at 50 rows** to avoid trigger-cascade / webhook-loop storms; AI "smart column mapping" suggests the field map.
- **Conexa fiscal reconciliation** — `reconcile-conexa-payments` (cron, 30 min) polls charge status for pending payments the webhook may have missed, enriches URLs/raw regardless of status, and flips `pending → paid`. A **webhook-plus-reconciliation** safety-net pattern.
- **Storage GC** — `storage-garbage-collector` (cron, 03:00) removes orphaned storage objects.
- **Demo seeding** — `setup-demo-account` seeds a full demo agency for sales demos (`data/demoData.ts`).

---

## 10. The 14 pg_cron jobs (the runtime heartbeat)

Almost all behavior-over-time is pg_cron → `pg_net`/`net.http_post` → an edge function. **These schedules live in SQL migrations, not `config.toml`** — easy to miss, must be absorbed or the engines are inert.

| Job | Cadence | Drives |
|---|---|---|
| `process-whatsapp-automation-flows` / `process-automation-pending-actions` | every 1 min | the automation step machine (§2) |
| `process-whatsapp-queue` | every 1 min | **dead schedule** (function is a disabled stub) |
| `process-notifications` | 15 min (+30 min variant) | notification dispatch fan-out (§5) |
| `process-lead-ghosting-hourly` | hourly | **deprecated** (now generic automation steps) |
| `facebook-investment-sync` | every 8h | FB campaign/spend sync |
| `facebook-api-heartbeat` | every 4h | FB token health re-validation |
| `reconcile-conexa-payments` | every 30 min | fiscal payment reconciliation (§9) |
| `daily-billing-reminders` | 12:00 | dunning (§3) |
| `daily-summary-notification` | 11:00 | daily digest (§5) |
| `archive-old-social-media-posts` | 03:00 | social post archival |
| `monthly-closure-job` | 1st of month 00:00 | financial closure (§4) |
| `cleanup-conexa-webhook-log` | 03:17 | log cleanup |

> ⚠️ Two **dead/deprecated schedules** still registered (`process-whatsapp-queue`, `process-lead-ghosting-hourly`) point at disabled stubs — don't port them as live behavior; the lead-ghosting/queue logic is now generic `automation_flows` steps.
