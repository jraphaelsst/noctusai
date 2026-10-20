# Orbity rebuild — gap matrix (our side)

> GENERATED from [private study: orbity-live-2026-10] `GAP-MATRIX.md` — do not edit by hand.
> Rows = capabilities of the reference app that our `products/orbity` must cover. How the reference app implements them
> (live behaviour, screenshots, internals) stays in the private study, outside git (`KB § PATTERNS/common/app-reverse-engineering.md`).
> **Ours today** is from a CODE read, not live-validated. `R-n` = requirement in `HARDENING-REQUIREMENTS.md`.
> Decision: COPY · COPY+HARDEN · REDESIGN · SKIP · ALREADY-AHEAD. Priority: P0 = needed for the reference operator's daily cut-over or security/data-loss.

**Counts — 246 capability rows across 18 areas.**

| Decision \ Priority | P0 | P1 | P2 | P3 | Total |
|---|---|---|---|---|---|
| COPY | 3 | 8 | 20 | 11 | **42** |
| COPY+HARDEN | 25 | 71 | 46 | 9 | **151** |
| REDESIGN | 1 | 4 | 10 | 14 | **29** |
| SKIP | 0 | 0 | 0 | 5 | **5** |
| ALREADY-AHEAD | 10 | 4 | 4 | 1 | **19** |
| **Total** | **39** | **87** | **80** | **40** | **246** |

Rows per area: Platform shell & cross-cutting hardening 22 · Dashboard 10 · Notifications 9 · Clientes 20 · Tarefas 24 · Lembretes & Rotinas (personal) 7 · Agenda 14 · CRM & Leads 28 · Administrativo / Financeiro 33 · Social Media 25 · Controle de Tráfego 9 · Relatórios & public report links 3 · Contratos 9 · Importação 7 · Configurações 11 · E-mail Marketing 1 · Help, onboarding & growth 11 · Mobile 3

---

## 1 · Platform shell & cross-cutting hardening

| Capability | Ours today | Gap | Hardening refs | Decision | P |
| --- | --- | --- | --- | --- | --- |
| Grouped sidebar nav + collapse, header bell/theme | have: seed `createProductApp` nav groups (cc App.tsx) | IA/naming differs (Financeiro vs Administrativo) | — | COPY | P1 |
| Login / session | have: seed auth + Core SSO | — | R-298 | ALREADY-AHEAD | P0 |
| Self-service password recovery | ahead: `ForgotPassword.tsx` (cc) | — | R-298 | ALREADY-AHEAD | P0 |
| Single label registry (status/type/source/stage), never render raw slugs | partial: fixed enums, no custom labels | registry incl. custom rows | R-3 R-59 R-104 R-118 R-125 R-143 R-317 | COPY+HARDEN | P0 |
| One date util: date-only = `date` column, local parse | not checked | enforce in every schema/form | R-46 R-90 R-105 R-119 R-128 R-214 R-240 R-244 R-259 | COPY+HARDEN | P0 |
| Dirty-field PATCH + optimistic concurrency on every edit | not checked (FastAPI services) | contract: PATCH diff + `updated_at` check | R-55 R-94 R-124 R-132 R-244 R-276 | COPY+HARDEN | P0 |
| Multi-row writes atomic server-side | partial: server services/RPCs exist (offboard RPC cc) | audit each create path | R-45 R-56 R-113 R-154 R-180 R-207 R-305 | COPY+HARDEN | P1 |
| Shared confirm/undo + soft-delete policy | partial: `useConfirm` from lib in Tarefas (cc) | one policy everywhere + Arquivados/restore | R-6 R-67 R-73 R-96 R-135 R-151 R-359 R-360 R-363 R-367 | COPY+HARDEN | P1 |
| Query-key invalidation across widgets | not checked | invalidate by key family | R-14 R-43 R-176 R-181 | COPY+HARDEN | P1 |
| pt-BR inline validation (zod), dirty-form guard | not checked | shared form shell | R-29 R-269 R-322 R-339 | COPY+HARDEN | P1 |
| Backend errors → pt-BR messages + correlation id | not checked | error-code map | R-290 | COPY+HARDEN | P1 |
| Deep links / action URLs derived from route registry | partial: seed route registry nav (cc) | registry-derived links + test | R-2 R-266 R-330 | COPY+HARDEN | P1 |
| Honest loading/empty states (first-run vs no-results) | partial: seed `check_lying_loading_state` keeper | per-filter empty copy | R-223 R-323 R-332 | COPY+HARDEN | P2 |
| Branded pt-BR 404 inside shell | have: `NotFound.tsx` (cc), branding not checked | verify pt-BR + shell | R-352 | COPY+HARDEN | P2 |
| "Dados desatualizados" refetch-on-return prompt | absent | — | R-39 | COPY | P3 |
| Theme claro/escuro/sistema persisted on profile | not in inventory | persist on profile | R-277 | COPY+HARDEN | P3 |
| pt-BR locale only (no pt-PT tokens) | not checked | locale lint | R-350 | COPY+HARDEN | P3 |
| Secrets never readable by the browser | ahead: vault refs (`access_token_ref`, META  | keeper check on every new secret | R-158 R-253 R-265 R-272 R-286 | ALREADY-AHEAD | P0 |
| PII minimization in list queries | not checked | select displayed cols only | R-293 | COPY+HARDEN | P1 |
| Per-agency AI quota, typed server-side AI endpoints, persisted runs | partial: seed LLM settings | ai_runs + quota | R-320 | REDESIGN | P2 |
| PWA manifest + install prompt + `/install` guide | not in inventory | — | R-42 | COPY | P3 |
| Vendor product analytics (own Pixel + CAPI on app) | absent | The reference operator-specific | R-11 | SKIP | P3 |

## 2 · Dashboard

| Capability | Ours today | Gap | Hardening refs | Decision | P |
| --- | --- | --- | --- | --- | --- |
| Greeting + date + overdue-tasks banner (clickable) | partial: greeting + KPIs (`Dashboard.tsx`) | link banner to filtered tasks | R-17 | COPY+HARDEN | P2 |
| Onboarding checklist (5 steps, one endpoint, dismiss) | absent | single endpoint | R-1 R-9 | COPY+HARDEN | P2 |
| Time-boxed signup bonus incentive (R$100) | absent | owner decision | R-9 | SKIP | P3 |
| Today timeline (payments due + timed routines + tasks + meetings, inline tick) | absent | — | R-14 R-15 | COPY+HARDEN | P1 |
| Minhas Tarefas (assigned to me, overdue group) | absent | — | R-3 | COPY | P1 |
| Tarefas Solicitadas (I requested) + bulk triage/assign | absent | bulk assign | R-10 | COPY+HARDEN | P2 |
| Personal notes (pin, favorite, markdown checklist, search) | absent | flush on blur, undo | R-5 R-6 | COPY+HARDEN | P2 |
| Quick actions open the create form directly | absent | `?new=1` deep links | R-16 R-19 | COPY+HARDEN | P2 |
| Agency metrics cards (clientes, leads, reuniões, conclusão, receita, ads, alertas) | partial: KPI cards | ads + alerts cards | — | COPY | P1 |
| Money privacy toggle on revenue/ad cards | absent | — | R-7 | COPY | P2 |

## 3 · Notifications

| Capability | Ours today | Gap | Hardening refs | Decision | P |
| --- | --- | --- | --- | --- | --- |
| In-app feed: tabs Todas/Reuniões/Tarefas/Alertas, unread filter, priority groups, mark-all-read | partial: seed `NotificationBell`, in-app only | tabs/grouping | R-8 | COPY+HARDEN | P1 |
| Notification action links that resolve | not checked | registry-derived | R-2 | COPY+HARDEN | P1 |
| Payment-due reminders surface as notifications | partial: finance reminders (024) | in-app emit | R-8 | COPY | P1 |
| Snooze menu (Não perturbe 1–24h) | absent | — | R-8 | COPY | P2 |
| Aggregation of repeated notifications (`group_count`) | absent | — | R-8 | COPY | P2 |
| Preferences matrix category × channel (in-app/push/email) + sounds | absent | separate user prefs from agency config 🔒 | R-4 R-8 | COPY+HARDEN | P2 |
| Fixed DND window + weekends + critical bypass | absent | — | R-8 | COPY | P2 |
| Web push (PWA) + browser notifications + test alert | absent | — | R-8 | COPY | P2 |
| E-mail notification channel | absent | — | R-4 | COPY | P3 |

## 4 · Clientes

| Capability | Ours today | Gap | Hardening refs | Decision | P |
| --- | --- | --- | --- | --- | --- |
| Client list: search, Ativos/Inativos, counts, service line | have: `Clientes.tsx` | accent-insensitive search | R-21 | COPY+HARDEN | P0 |
| Billing-grade client form (CPF/CNPJ checksum, Razão Social, Fantasia, billing e-mail, WhatsApp, CEP autofill) | partial: `ClientForm` + CNPJ lookup + `document` col (cc 023); address not seen | address/CEP, billing e-mail | R-146 R-200 | COPY+HARDEN | P0 |
| Billing settings on client (fee, due day w/ month-end clamp, billing method, auto-charge opt-in) | have: `monthly_value`, `due_date` 1–31, `billing_automation_enabled` default false (cc) | month-end clamp | R-148 | COPY+HARDEN | P0 |
| Legacy/imported rows stay editable (fiscal fields required only when billing on) | not checked | conditional + server validation | R-28 R-153 R-191 | COPY+HARDEN | P0 |
| Client deactivation with per-charge cancel/keep (offboarding) | ahead: atomic RPC + gateway-side cancel w/ retry (cc offboarding.py) | — | R-291 | ALREADY-AHEAD | P0 |
| Reactivation that keeps churn history + offers charges | not checked | status-event table | R-292 | COPY+HARDEN | P1 |
| Client detail 360 (contracts, receivables, origin lead, tasks, meetings, posts) | absent | full page | R-23 R-144 | REDESIGN | P1 |
| Typed client timeline (Nota/Ligação/E-mail/Reunião/Ideia/Alerta) with edit | absent | edit + undo | R-26 R-150 R-151 R-152 | COPY+HARDEN | P1 |
| Upcoming tasks on client (overdue badge, clickable, "Ver todas" filtered) | absent | — | R-27 R-143 R-157 | COPY+HARDEN | P1 |
| Quick task from client (atomic, shared type registry) | absent | — | R-154 R-155 | COPY+HARDEN | P2 |
| Recent meetings on client + schedule from client | absent | — | R-157 | COPY | P2 |
| Credentials vault (encrypted, reveal-with-audit, `new-password`) | absent | 🔒 encrypt at rest | R-24 R-145 R-156 | COPY+HARDEN | P1 |
| Client health score (3 configurable pillars, server-side, same in list & detail) | absent | server score + history | R-22 R-25 R-140 R-311 R-313 | COPY+HARDEN | P2 |
| NPS/CSAT collection from clients | absent | survey channel | R-311 | REDESIGN | P3 |
| "Resumo" card (honest label or real LLM summary) | absent | — | R-142 R-312 | REDESIGN | P3 |
| Header actions WhatsApp (wa.me) + Drive link + tenure | absent | — | — | COPY | P2 |
| Contract/fidelity period on client (one model, duration shortcut) | partial: contracts organ periods | single period model | R-315 | REDESIGN | P1 |
| Lead → client conversion (prefill, `lead_id` link, optional contract) | absent (no `lead_id` on clients, cc) | — | R-130 R-149 | REDESIGN | P1 |
| Agency-as-internal-client modelling | not checked | explicit model | R-44 | REDESIGN | P2 |
| Client hard delete gated (inactive only) + LGPD anonymize | not checked | expose in Clientes + anonymize | R-365 | COPY+HARDEN | P2 |

## 5 · Tarefas

| Capability | Ours today | Gap | Hardening refs | Decision | P |
| --- | --- | --- | --- | --- | --- |
| Kanban + list views (persisted view choice) | have: `Tarefas.tsx` kanban | list view parity | R-60 | COPY | P0 |
| Per-agency custom statuses (ordered, colour token, toggle, defaults incl. Em Revisão/Aprovado) | absent: CHECK todo/doing/done/canceled (cc 007) | status registry table | R-32 R-33 R-59 | COPY+HARDEN | P0 |
| Task types registry (defaults as DB rows + custom, never blocks creation) | absent | type registry | R-36 R-38 R-40 R-41 R-155 R-317 | COPY+HARDEN | P0 |
| Edit task without data loss | not checked | dirty PATCH + concurrency | R-53 R-55 R-57 R-244 | COPY+HARDEN | P0 |
| Attachments (≤10, private bucket, signed URLs, upload-on-save, cleanup) | absent | 🔒 private storage | R-249 R-250 R-360 | COPY+HARDEN | P0 |
| Multi-client per task (join table, all shown/duplicated) | partial: single `client_id` | join table | R-44 R-64 R-65 | COPY+HARDEN | P1 |
| Multi-assignee with stable assignment rows | partial: single assignee (007 header, cc) | assignments table | R-45 R-56 R-48 | COPY+HARDEN | P1 |
| Subtasks (per-row writes, history) | absent | — | R-47 R-50 R-53 | COPY+HARDEN | P1 |
| Recurrence daily / weekly (days, every N) / monthly, server-side next occurrence, stop series | partial: routines spawn tasks via scheduler | per-task rule + trigger | R-295 R-296 R-297 | COPY+HARDEN | P1 |
| Filters (priority, user, client, type, period, undated) + sort, URL-synced + saved views | partial: "kanban + filters" | URL state, saved views | R-316 | COPY+HARDEN | P1 |
| Task detail with server-side activity log (human diffs) | not checked | activity table | R-35 R-51 R-54 R-58 R-251 | COPY+HARDEN | P1 |
| Delete with confirm/undo + cascade cleanup (approvals, storage) | partial: confirm dialog (cc) | soft delete + cleanup | R-67 R-360 | COPY+HARDEN | P1 |
| Task templates ({cliente} substituted, subtasks, auto-assign, server usage count, archive/restore) | absent | — | R-61 R-62 R-63 R-367 | COPY+HARDEN | P1 |
| Create wizard (Básico/Detalhes/Revisão incl. recurrence summary) | partial: basic form | wizard | R-49 R-295 | COPY+HARDEN | P2 |
| AI prefill from text ("Preencher com IA") | absent | typed endpoint | R-38 R-320 | COPY+HARDEN | P2 |
| Voice input for task prefill | absent | server transcription (seed organ) | R-321 | REDESIGN | P3 |
| "Melhorar com IA" diff-before-apply | absent | — | R-52 R-53 | COPY+HARDEN | P2 |
| Duplicate task (all clients, subtasks) | absent | — | R-65 R-66 | COPY+HARDEN | P2 |
| Distinct mark-done control + undo | not checked | — | R-34 | COPY+HARDEN | P2 |
| Auto-archive done tasks (server cron, configurable) | absent (scheduler exists) | cron job | R-30 R-221 | REDESIGN | P2 |
| Kanban card badges + readable client chip (AA contrast) | not checked | token variants | R-317 R-318 | COPY+HARDEN | P2 |
| Análises tab (monthly KPIs, team table, workload, by type, by client, insights) | absent | — | R-31 R-319 | COPY+HARDEN | P2 |
| AI team review (score, bottlenecks, suggestions) persisted | absent | typed + stored | R-31 R-320 | REDESIGN | P3 |
| Search with match snippet | not checked | — | R-361 | COPY+HARDEN | P3 |

## 6 · Lembretes & Rotinas (personal)

| Capability | Ours today | Gap | Hardening refs | Decision | P |
| --- | --- | --- | --- | --- | --- |
| Personal reminders CRUD (title, notes, date/time, list, priority, flag) | absent | — | R-68 R-71 R-324 | COPY+HARDEN | P1 |
| Reminder recurrence that really generates next occurrence (+ end/count) | absent | server-side | R-69 R-72 | COPY+HARDEN | P1 |
| Smart filters + groups (Atrasados/Hoje/Mais tarde, completed apart) | absent | correct semantics | R-74 R-323 | COPY+HARDEN | P2 |
| Reminder lists full CRUD + reorder + colour token + "Sem lista" | absent | — | R-75 R-76 R-77 R-325 | COPY+HARDEN | P2 |
| Pre-reminder notifications (na hora … 1 h antes) | absent | needs push | R-71 | COPY | P2 |
| Stats cards Total/Hoje/Concluídos/Atrasados + subtasks | absent | — | R-71 | COPY | P3 |
| Personal routines board weekly/monthly with completions % | partial: `Rotinas.tsx` spawns tasks (different model) | checklist mode + validation | R-12 R-13 R-14 | REDESIGN | P1 |

## 7 · Agenda

| Capability | Ours today | Gap | Hardening refs | Decision | P |
| --- | --- | --- | --- | --- | --- |
| Month/Week/Day views + synced mini-calendar + week summary (excl. cancelled), range queries | partial: `Agenda.tsx` CRUD | views + range | R-78 R-81 R-84 R-92 | COPY+HARDEN | P0 |
| Meeting create/edit (title, type, desc, start, duration, location) with pt-BR picker | have: `agenda_events` CRUD (cc 007) | duration presets, picker | R-83 R-94 | COPY+HARDEN | P0 |
| Meeting types + filters (responsável/tipo/status) | partial: `event_type` meeting/call/visit/other (cc) | type registry | R-78 R-97 | COPY+HARDEN | P1 |
| Meeting status machine (Agendada/Concluída/Cancelada+motivo/Não compareceu) + close-out prompt | absent: no status column (cc) | explicit close-out | R-82 R-86 R-91 R-92 R-95 | COPY+HARDEN | P1 |
| Multi-client + lead link on meeting | partial: single `client_id` (cc) | join table + lead | R-85 | COPY | P1 |
| WhatsApp reminder to client N h before | absent (WAHA sender exists) | job + status | R-85 R-94 | COPY+HARDEN | P1 |
| Google Calendar sync (personal OAuth) + Meet link | partial: Fake adapter seam | real adapter | — | COPY | P1 |
| Meeting templates with {cliente}/{lead} interpolation | absent | — | R-314 | COPY+HARDEN | P2 |
| Ata (minutes templates, notes, action items → tasks idempotent) | absent | — | R-79 R-88 R-89 | COPY+HARDEN | P2 |
| Outcome + follow-up date + one-click follow-up meeting | absent | — | R-87 R-90 R-93 | COPY+HARDEN | P2 |
| Contexto panel (same-client past meetings, open tasks, notes, posts) | absent | — | R-80 R-326 | COPY+HARDEN | P2 |
| Internal/external participants | absent | — | R-85 | COPY | P2 |
| 00–24 hour grid (no clipped meetings) | not checked | — | R-327 | COPY+HARDEN | P2 |
| Duplicate / delete (styled confirm) + activity history | not checked | — | R-93 R-95 | COPY | P2 |

## 8 · CRM & Leads

| Capability | Ours today | Gap | Hardening refs | Decision | P |
| --- | --- | --- | --- | --- | --- |
| Pipeline kanban with drag, counts, hide column | have: `Funil.tsx` seed KanbanBoard | hide column | R-192 | COPY | P0 |
| Lead form (name, email, phone, company, role, source, stage, temperature, value, last/next contact, tags, notes, owner) | partial: leads CRUD | owner select, all fields | R-122 | COPY+HARDEN | P0 |
| Canonical source enum; unknown values preserved on edit | not checked | enum + migration map | R-103 R-120 R-132 | COPY+HARDEN | P0 |
| Lost stage + loss reason | ahead: `is_won/is_lost` stages (cc 005) | loss-reason UI | R-102 | ALREADY-AHEAD | P1 |
| Stage registry with stable keys, rename/reorder/colour, insert mid-funnel | partial: `lead_stages` table; UI missing | settings UI | R-110 R-133 R-329 R-334 | COPY+HARDEN | P1 |
| Server-side stage history for every path, rendered old→new | partial: `lead_activities` + `_emit_stage_change` (META  | render diff, key fields | R-123 R-124 R-131 R-137 R-194 | COPY+HARDEN | P1 |
| List view: search, status/temperature/source filters, export | partial | list + export | R-332 | COPY+HARDEN | P1 |
| Lead detail (badges, value, time-in-funnel stops at won/lost, follow-ups, notes timeline) | not checked | append-only notes | R-106 R-107 R-108 R-139 | COPY+HARDEN | P1 |
| Lead WhatsApp conversation tab (reads never write) | partial: WAHA inbound/sender (`whatsapp_inbound.py`) | read-only tab | R-108 R-331 | COPY+HARDEN | P1 |
| Phone E.164 normalization + duplicate warning | not checked | — | R-121 | COPY+HARDEN | P1 |
| Lead delete: confirm, soft delete, keep history, conversation policy | not checked | — | R-135 R-366 | COPY+HARDEN | P1 |
| Card actions: one modal at a time; "Reunião" opens prefilled meeting; touch-reachable | not checked | — | R-126 R-138 R-332 | COPY+HARDEN | P2 |
| CRM dashboard KPIs (total, conversion, revenue, attention) with ONE server-side period | absent | — | R-98 R-100 R-199 | COPY+HARDEN | P1 |
| Funnel + stage conversions + benchmarks over the stage registry | absent | — | R-99 R-134 R-329 | COPY+HARDEN | P2 |
| Sales velocity per stage from history + stuck leads | absent | — | R-101 R-131 | COPY+HARDEN | P2 |
| Result & cost metrics (ROAS, CPL, CPA, ticket) | absent | — | R-117 | COPY | P2 |
| Manual investments with month picker + list navigation | absent | — | R-117 R-334 | COPY+HARDEN | P2 |
| Exclude test leads from metrics | absent | `is_test` | R-134 | COPY+HARDEN | P3 |
| Public lead-capture webhook (JSON/form/GET, extra fields, default stage/source, test, examples) | partial: `POST /api/capture/{org_id}` rate-limited (cc); no config UI | URL/config UI | R-114 R-308 R-333 | COPY+HARDEN | P1 |
| Capture endpoint security (per-source secret, active flag enforced, honeypot, redirect) | partial: rate limit only; no secret (cc) | secret token + active flag — **our endpoint is live in code today** | R-115 R-333 | COPY+HARDEN | P0 |
| Lead qualification scoring rules + configurable thresholds | partial: scoring + rules BE, no UI | rules UI | R-109 R-198 | COPY+HARDEN | P2 |
| WhatsApp automation flow builder (triggers, 7 step types, conditions, schedule window, stop rules, variables) | partial: flows/steps/executions, 10 triggers, real WAHA (inventory) | 4 triggers, schedule window, editor parity | R-111 | COPY+HARDEN | P1 |
| Flow validation on save (targets, media, stage, canonical values) | not checked | — | R-112 R-306 | COPY+HARDEN | P1 |
| Flow KPIs + execution log feed | partial: executions table | panel | R-304 | COPY | P2 |
| Flow duplicate / delete (confirm, atomic, restore) | not checked | — | R-113 R-305 | COPY+HARDEN | P2 |
| Flow import/export portable JSON (tenant ids stripped) | absent | — | R-304 | COPY | P3 |
| Meta Lead Ads integration (page → form, default stage/temperature, sync) | partial: seed Meta adapter has Lead Ads (META  | product wiring + App Review | R-197 R-307 | REDESIGN | P2 |
| Meta CAPI conversion loop (server outbox, idempotent, forward-only, agency pixel, test code) | partial: server stage-event hook (META  | seed `send_conversion_events` + outbox | R-129 R-193 R-195 R-196 | REDESIGN | P2 |

## 9 · Administrativo / Financeiro

| Capability | Ours today | Gap | Hardening refs | Decision | P |
| --- | --- | --- | --- | --- | --- |
| Month selector + KPI cards (faturamento/recebido, custos/pago, lucratividade, inadimplência) on ONE period | partial: `Financeiro.tsx` FinanceRoutedPage | verify single period | R-161 | COPY+HARDEN | P0 |
| Cash flow tabs (Este mês / Próx. 7 dias / Atrasados), overdue derived from due date | partial: seed finance organ | derived overdue everywhere | R-165 R-335 R-338 | COPY+HARDEN | P0 |
| Monthly invoice generation server-side, idempotent per (client/contract, cycle), tombstoned | ahead: UNIQUE (contract, period, kind) + revenues unique month (cc 021/006) | tombstone on forgive/delete | R-201 R-364 R-163 | ALREADY-AHEAD | P0 |
| Client monthly fee → recurring contract → charge (cut-over data shape) | partial: contracts organ drives billing (cc 021) | mapping for migrated clients | R-19 R-146 | REDESIGN | P0 |
| Dar baixa incl. partial payment (remainder stays open) | ahead: `fin_entries` status open/partial/paid/cancelled (cc 019) | UI verify | R-164 R-186 | ALREADY-AHEAD | P0 |
| Revert to pending (lossless, shared for invoices/salaries) | not checked | one revert() | R-167 R-188 | COPY+HARDEN | P1 |
| Cancel/forgive ≠ delete (delete only cancelled, styled confirms) | partial: `cancelled` status (cc) | UI state machine | R-169 R-362 R-363 | COPY+HARDEN | P1 |
| Invoice sheet: base / surcharge / discount stored, "make new fixed fee" | not checked | persist columns | R-162 R-168 | COPY+HARDEN | P1 |
| One-off revenue with description | have: manual `fin_entries` source (cc) | show description | R-166 | COPY+HARDEN | P1 |
| Gateway charges Asaas (PIX/boleto) + webhook settle | have: Asaas gateway + webhook (inventory) | — | R-163 R-280 | COPY | P0 |
| Conexa gateway (boleto auto, billing methods, manual write-off sync) | absent | owner decision | R-280 R-281 | COPY+HARDEN | P1 |
| Stripe for agency charges | absent | — | R-280 | COPY | P3 |
| Gateway webhook security + health panel | not checked | HMAC/header secret, health | R-281 | COPY+HARDEN | P1 |
| Manual charge via WhatsApp with saved templates | partial: WAHA sender + dunning | template picker | R-203 | COPY | P1 |
| Dunning (régua): before / on day / after rules, multi-step cadence, channels, templates with placeholders | ahead: `fin_reminder_rules` unique (channel, offset) → many offsets (cc 024) | per-gateway templates UI | R-170 R-171 | ALREADY-AHEAD | P0 |
| Régua saved-state chip + unsaved guard + channel health gates toggle | not checked | — | R-171 R-339 | COPY+HARDEN | P1 |
| Dunning send history with filters | partial: `fin_reminder_log` dedup (cc 024) | history UI | R-170 R-171 | COPY+HARDEN | P1 |
| Interest / fine / punctuality discount sent to gateway | not checked | — | R-170 | COPY | P2 |
| Expenses: one-off / recurring / installments with rule ≠ instance | ahead: `fin_recurrences` + installment groups, idempotent (cc 019) | UI parity | R-172 R-177 R-180 R-185 | ALREADY-AHEAD | P0 |
| Cancel subscription/installments never rewrites paid instances | ahead (by model: rules separate from instances) — not checked live | verify | R-178 R-187 | ALREADY-AHEAD | P0 |
| Foreign-currency expenses converted to BRL in one place | absent: no currency column (cc) | amount_brl + rate | R-173 R-176 | COPY+HARDEN | P1 |
| SaaS tracker (subscriptions, pause, savings) | absent | — | R-175 R-176 | COPY+HARDEN | P2 |
| Expense categories seeded (incl. taxes) + inline create + explicit DRE group | partial: `fin_categories` tree seeded per org (cc 019) | DRE group field | R-174 R-336 | COPY+HARDEN | P1 |
| Payroll: employees, monthly salary generation (incl. mid-month hire), payslip breakdown + PDF | absent (inventory) | — | R-182 R-183 | COPY+HARDEN | P1 |
| Employee deactivation with final-pay prompt; delete/anonymize | absent | — | R-184 R-189 | COPY+HARDEN | P2 |
| PPR / bonus eligibility | absent | owner decision | R-340 | SKIP | P3 |
| Análise Avançada: Visão atual / Projeção 90d / DRE (competência + caixa), correct formulas | partial: seed DRE (inventory) | metrics service | R-335 R-336 R-337 | COPY+HARDEN | P1 |
| Copy DRE summary for WhatsApp + PDF export 1–12 months | not checked | — | R-337 | COPY | P2 |
| Forecast months mode (projected rows, costs composition) | not checked | — | R-159 R-161 R-338 | COPY+HARDEN | P2 |
| Profitability per client (allocation by time/tasks, drill-down) | absent | — | R-160 R-204 R-341 | REDESIGN | P2 |
| Gerenciar Carteira churn cockpit (rate, cancellations, MRR lost, 6-mo chart) from status events | absent (inventory) | events table | R-190 R-292 | COPY+HARDEN | P1 |
| Inline fee/status edit from portfolio | absent | — | R-191 | COPY+HARDEN | P2 |
| NFS-e emission | absent (inventory) | owner decision | R-146 | REDESIGN | P2 |

## 10 · Social Media

| Capability | Ours today | Gap | Hardening refs | Decision | P |
| --- | --- | --- | --- | --- | --- |
| Content plans list (search, status filter, card counters from one function) | have: content plans (inventory) | counter fn | R-211 | COPY+HARDEN | P1 |
| Manual plan create (client, title, pt-BR month picker, context, active) | partial | picker | R-218 R-342 | COPY+HARDEN | P1 |
| AI planning wizard 4 steps (context, frequency, style, direction) with per-step validation | partial: `content_plan_ai_service` (cc) | wizard parity | R-206 R-343 | COPY+HARDEN | P1 |
| Plan items CRUD (format, platform, dates within plan period, caption, hashtags, instructions) | partial: plan items | period validation | R-210 R-211 | COPY+HARDEN | P1 |
| AI append items clamped to plan period | partial: AI items | clamp | R-213 | COPY+HARDEN | P2 |
| Items → tasks in bulk with assignees, atomic | have: items → posts/tasks (server) | — | R-207 R-210 | COPY+HARDEN | P1 |
| Discard item: decide linked task + restore | not checked | — | R-208 | COPY+HARDEN | P1 |
| Plan delete with counts + keep/delete tasks | not checked | — | R-359 | COPY+HARDEN | P1 |
| Real "Editar planejamento" form | not checked | — | R-217 | COPY+HARDEN | P2 |
| Weekly summary text for WhatsApp (copy) | absent | — | R-209 | COPY | P3 |
| Calendar month/week/day from tasks + planned items as ghosts; arrows by view unit; range query | absent (only Planejamento in `Conteudo.tsx`) | — | R-215 R-227 R-228 | COPY+HARDEN | P1 |
| Calendar status filter from the status registry | absent | — | R-345 | COPY+HARDEN | P2 |
| Calendar post detail = shared task detail; create/edit in place | absent | — | R-216 R-222 R-226 R-241 | COPY+HARDEN | P1 |
| Caption field on task "para aprovação" (autosave) | not checked | — | R-241 R-242 | COPY+HARDEN | P0 |
| Caption generator (from task / free text) saved to task with versions | absent (inventory "AI captions") | persist | R-229 R-230 | COPY+HARDEN | P2 |
| Send for approval: server token, multi-item link, prerequisite explained, expiry | partial: server-generated token + 7-day expiry (cc); single-item | multi-item one link | R-224 R-246 R-249 | COPY+HARDEN | P0 |
| Public approval page (carousel, approve / request change ≤500, decision-aware copy, E.164 CTA hidden when no phone) | have: `/aprovar/:token` `AprovacaoPublica.tsx` | copy + CTA rules + carousel | R-246 R-247 R-248 R-279 | COPY+HARDEN | P0 |
| Agency notified of client decision (in-app + WhatsApp/e-mail) | not checked | — | R-247 | COPY+HARDEN | P1 |
| Decision reflected on task (banner, history entries) | partial history | not checked | — | R-246 R-251 | COPY+HARDEN | P1 | — |
| Platforms config (defaults as rows + custom, single enums for format/tone/platform) | absent (inventory) | — | R-235 R-236 R-237 R-344 | COPY+HARDEN | P2 |
| Delivery lead-time setting (days before post) | absent | — | R-238 | COPY | P2 |
| Social analytics tab (workflow metrics, forward months, buckets from statuses) | absent | — | R-232 R-233 R-346 | COPY+HARDEN | P3 |
| Real social performance insights (IG/Meta reach, engagement) | absent | — | R-234 | REDESIGN | P3 |
| Approval-flow configuration (approvers, channel) | absent | — | R-239 | REDESIGN | P3 |
| Direct publishing to networks | absent | — | — | SKIP | P3 |

## 11 · Controle de Tráfego

| Capability | Ours today | Gap | Hardening refs | Decision | P |
| --- | --- | --- | --- | --- | --- |
| Honest connection/maintenance state | have: honesty banner on `Trafego.tsx` | — | R-197 R-252 | COPY | P2 |
| Meta Ads OAuth connect + ad-account selection | partial: seed Meta adapter OAuth; product Fake | App Review + wiring | R-197 R-252 | REDESIGN | P2 |
| Ad tokens server-side only | ahead: `access_token_ref` vault (META  | — | R-253 | ALREADY-AHEAD | P2 |
| Manual campaign metrics entry | ahead: manual metrics real (inventory) | — | — | ALREADY-AHEAD | P2 |
| Account detail (spend, impressions, clicks, CTR, charts, campaigns table) | partial: campaigns + aggregate (Fake sync) | real sync | R-252 | COPY | P2 |
| Client balances panel (deposited/spent/available, health, optimize-day badges, min-balance alert) | absent | — | R-252 | COPY | P3 |
| Optimization diary + comments per ad account | absent | — | R-252 | COPY | P3 |
| AI 4-week campaign analysis + WhatsApp report templates | absent | — | R-289 | COPY | P3 |
| Provider-agnostic ads seam (Google/TikTok next) | absent | — | R-254 | REDESIGN | P3 |

## 12 · Relatórios & public report links

| Capability | Ours today | Gap | Hardening refs | Decision | P |
| --- | --- | --- | --- | --- | --- |
| Reports module (CRUD, snapshots, generate) | ahead: `reports_router` + `Relatorios.tsx` | Meta data Fake | R-20 | ALREADY-AHEAD | P2 |
| Public report link in own table (expiry, revoke, views) | ahead: `reports.public_token` + server expiry check (cc 012); also a legacy `clients.report_token` (cc 005) | drop duplicate token model; revoke/views UI | R-347 | ALREADY-AHEAD | P2 |
| Public report error states (not-found ≠ expired), agency-branded | not checked | branding from token's agency | R-351 | COPY+HARDEN | P2 |

## 13 · Contratos

| Capability | Ours today | Gap | Hardening refs | Decision | P |
| --- | --- | --- | --- | --- | --- |
| Contracts list (search by client/CPF, status, values, period) | have: contracts organ in Financeiro › Contratos (billing models cc 021) | — | R-255 R-258 | ALREADY-AHEAD | P1 |
| Lifecycle draft → sent → signed → active → ended, versions, readjust, suspend | ahead: versions, readjust, suspend (inventory) | — | R-257 | ALREADY-AHEAD | P1 |
| Contract templates with magic variables + editor | absent (inventory) | — | R-255 | COPY | P1 |
| Template wizard (base → variables → review) blocking unresolved variables | absent | — | R-256 R-348 | COPY+HARDEN | P1 |
| Contract document PDF / download | partial: "document" endpoint (inventory) | verify render | R-257 | ALREADY-AHEAD | P1 |
| E-signature (D4Sign/Clicksign) | partial: e-sign returns 409 (inventory) | provider | R-257 | REDESIGN | P2 |
| AI contract copilot (same model as template path) | absent | — | R-256 R-260 | COPY+HARDEN | P3 |
| Agency CNPJ in agency profile (not localStorage) | not checked | — | R-262 | COPY+HARDEN | P2 |
| Client PII snapshot masked in lists + LGPD retention | not checked | — | R-261 R-263 | COPY+HARDEN | P2 |

## 14 · Importação

| Capability | Ours today | Gap | Hardening refs | Decision | P |
| --- | --- | --- | --- | --- | --- |
| Bulk import clients + payments and leads (template, upload, summary, confirm) | absent (bank-statement import only) | needed to load the reference operator's data at cut-over (see Open questions) | R-267 R-270 | COPY+HARDEN | P0 |
| Bulk import expenses + salaries | absent | — | R-267 | COPY+HARDEN | P1 |
| Column mapping with suggestions for every type | absent | — | R-269 | COPY+HARDEN | P1 |
| Server-side validation, pt-BR messages, correct invalid-row counts | absent | — | R-268 R-269 | COPY+HARDEN | P1 |
| CSV / Google Sheets input + inline schema | absent | — | R-271 | COPY+HARDEN | P2 |
| Gateway sync + "Adicionar ao MRR" on import | absent | — | R-267 | COPY | P2 |
| Bank statement import | ahead: finance organ (inventory) | — | — | ALREADY-AHEAD | P3 |

## 15 · Configurações

| Capability | Ours today | Gap | Hardening refs | Decision | P |
| --- | --- | --- | --- | --- | --- |
| Team users: invite by e-mail (member sets own password), roles | ahead: seed team + invitations (`AcceptInvite.tsx`) | — | R-273 | ALREADY-AHEAD | P0 |
| Last-owner guard on demote/remove | not checked | server check | R-274 | COPY+HARDEN | P0 |
| Role → permission matrix UI + role-change audit | partial: seed team | — | R-275 | COPY+HARDEN | P2 |
| Profile (name, avatar) with dirty-check | absent (inventory) | — | R-276 | COPY+HARDEN | P1 |
| Change password / 2FA / sign out | partial: seed auth | 2FA unknown | — | COPY | P2 |
| Agency branding for public pages (logo, public contacts, themes w/ preview) | absent (inventory) | — | R-278 R-279 | COPY+HARDEN | P1 |
| WhatsApp connection (QR) + bring-your-own instance, stale QR expiry | have: `Whatsapp.tsx` WAHA connections | expiry | R-205 R-285 | COPY+HARDEN | P0 |
| Separate WhatsApp number for billing | absent | — | R-285 | COPY | P2 |
| Payment-gateway setup screens, secrets write-only (`configured`, last4) | partial: Asaas config (inventory) | Conexa/Stripe screens | R-272 R-280 | COPY+HARDEN | P0 |
| Per-agency AI prompts (enum owned by DB, restore = delete, versions/test) | absent (inventory) | — | R-282 R-283 R-284 R-289 | COPY+HARDEN | P3 |
| Vendor SaaS subscription tab (plan, invoices, portal) | absent (seed billing not wired) | white-label only | R-179 R-231 R-287 R-288 R-302 | REDESIGN | P3 |

## 16 · E-mail Marketing

| Capability | Ours today | Gap | Hardening refs | Decision | P |
| --- | --- | --- | --- | --- | --- |
| E-mail campaigns (SendPulse) | absent | provider-agnostic e-mail seam 🔒 secrets server-side | R-264 R-265 R-266 R-286 | REDESIGN | P3 |

## 17 · Help, onboarding & growth

| Capability | Ours today | Gap | Hardening refs | Decision | P |
| --- | --- | --- | --- | --- | --- |
| Help drawer with AI support chat (agency context, route links) | absent | seed LLM | R-18 R-310 | REDESIGN | P2 |
| Module guides + guided tour (per page, versioned, all modules) | absent | — | R-309 R-310 | COPY+HARDEN | P3 |
| Video tutorial library | absent | content production | R-310 | COPY | P3 |
| Help FAB that never covers actions (safe area) | absent | — | R-328 R-349 | COPY+HARDEN | P3 |
| In-app feedback channel (tenant-configurable) | absent | white-label | R-18 | REDESIGN | P3 |
| Self-service agency signup (company, plan, admin, checkout, trial) with server OTP | partial: seed auth framework | white-label only 🔒 | R-300 R-303 R-358 | REDESIGN | P3 |
| Checkout success/cancel pages verified server-side | absent | — | R-302 | REDESIGN | P3 |
| Platform super-admin console (tenants, billing, suspend/delete) server-protected | absent | platform-admin role | R-301 | REDESIGN | P3 |
| Versioned privacy policy + Terms, linked publicly | partial: seed-mounted consent routes (CLAUDE.md); versioning not checked | version + footer links | R-299 R-356 | COPY+HARDEN | P1 |
| Marketing landing (claims from feature flags) | have: `Landing.tsx` | white-label content | R-355 | REDESIGN | P3 |
| Vendor sales funnel (demo booking + application form on the marketing site) | absent | — | R-357 | SKIP | P3 |

## 18 · Mobile

| Capability | Ours today | Gap | Hardening refs | Decision | P |
| --- | --- | --- | --- | --- | --- |
| Mobile shell drawer (opaque surface) | not checked | visual test at 390px | R-353 | COPY+HARDEN | P1 |
| Card layouts below md for Tarefas/Clientes (title first) | not checked | — | R-354 | COPY+HARDEN | P1 |
| Touch-reachable row/card actions (no hover-only) | not checked | — | R-332 | COPY+HARDEN | P2 |

---

## Cut-over critical path (P0s, in build order)

These must exist before the reference operator can run a normal day on our app. Order = dependency order.

1. **Security by construction on what ships:** secrets write-only (R-158 R-272), capture-endpoint secret + active flag. Our `/api/capture/{org_id}` is already public in code (R-115). Last-owner guard (R-274). Private attachment storage (R-249).
2. **Cross-cutting data integrity:** label registry (R-3 R-59), date-only util (R-240 R-259), dirty-field PATCH + concurrency (R-55 R-132). Every module below depends on these three.
3. **Team access:** login + password recovery + invites (R-298 R-273). The reference operator staff need accounts on day 1.
4. **Data load:** client + lead import, or a one-off back-office migration (R-267). It must handle legacy rows with empty CPF/CEP (R-28 R-153), map sources to the canonical enum (R-103 R-120) and map client fees to recurring contracts.
5. **Clientes:** list + billing-grade form + billing settings (R-146 R-148), with legacy rows still editable.
6. **Finance core:** contract-driven idempotent monthly charges (R-201 R-364), the Asaas gateway + webhook (R-163) or whichever gateway the reference operator uses, partial-payment dar-baixa (R-164), cash-flow tabs with derived overdue (R-165 R-335), and the month KPI cards (R-161).
7. **Collections:** régua/dunning over WAHA (R-170 R-171). WhatsApp connection (R-205) and offboarding with per-charge cancel/keep (R-291).
8. **Expenses:** one-off/recurring/installments that never rewrite paid history (R-178 R-185).
9. **Tarefas:** kanban/list, custom statuses (incl. Em Revisão/Aprovado), type registry that never blocks creation (R-40), lossless edit (R-55), attachments (R-249).
10. **CRM:** pipeline kanban + lead form with an owner field + canonical source (R-122 R-132).
11. **Agenda:** views + meeting CRUD with a pt-BR picker (R-83).
12. **Social approval loop:** caption on the task, a multi-item server-token approval link, and the public approval page (R-246 R-247 R-249).

## White-label blockers (hard-coded vendor identity found in the inputs)

Hard-coded vendor identity found in the reference app is listed in the private study. Our requirement: zero operator branding in code — every name, URL, support contact, webhook and legal link comes from per-tenant / per-deployment config (R-351, R-355, R-356, R-357).

## Where we are ahead (code-read; live validation pending)

- **Relatórios:** a real module with snapshots and a public token (R-20). The reference operator's page is "Em breve". Our token lives in its own table with server-side expiry (R-347).
- **Offboarding:** an atomic RPC that also cancels the charge at the gateway, with retry (R-291; the reference operator warns it does not).
- **Partial payments:** a partial status, so the receivable is not overwritten (R-164).
- **Invoice generation:** idempotent per contract/period on the server (R-201 R-364).
- **Dunning:** a multi-offset cadence per channel (R-171). Expenses keep recurrence rules separate from instances, with idempotent generation (R-177 R-178).
- **Contracts:** a full lifecycle with versions, readjust, suspend and billing models (R-257 R-258).
- **CRM:** a lost stage (`is_lost`, R-102), and server-side stage events with dedup keys that fix R-195 by construction.
- **Approval token** is generated on the server with an expiry (R-249).
- **Auth:** password recovery (R-298) and an invite flow instead of admin-set passwords (R-273).
- **Secrets:** a vault-ref pattern for ad tokens (R-253) and keeper-guarded secrets.
- **Tráfego:** manual traffic metrics work while Meta is unavailable (R-197).
- **Imports:** bank-statement import, which the reference operator does not have.
- **Task delete** asks for confirmation (R-67).

## Open questions for the owner

1. **Payment gateway:** which one does the reference operator actually run (Asaas, Conexa or Stripe)? This decides whether Conexa is P0 or P1 (R-280).
2. **Data migration:** do we load the reference operator's data one-off on the back office (export from their Orbity) or ship the import wizard first? Also, may we read their production export (PII/LGPD)?
3. **Billing model:** our billing is contract-driven, theirs is a fee on the client row (R-19). OK to auto-create one recurring contract per migrated client?
4. **Routines:** keep their personal checklist model, our spawn-a-task routines, or both ?
5. **Navigation and naming:** keep the reference operator's layout (Administrativo / Centro de Comando, client creation under finance) for user familiarity, or keep ours (Financeiro)?
6. **NFS-e:** in scope for cut-over (R-146 copy promises it)? Which provider?
7. **E-mail marketing:** does the reference operator use SendPulse campaigns today? If not, SKIP (R-264).
8. **Meta:** when do we start Meta App Review? It gates Lead Ads, CAPI and Tráfego sync (R-197).
9. **Disclosure:** do we tell the reference operator about the live security findings in their app (R-158 R-272 R-300 R-115 R-24)?
10. **Delete policy:** global soft-delete with an "Arquivados" view, or hard delete with undo (R-367)?
11. **Help:** do we build the AI help assistant and videos for white-label (R-18 R-310), and who produces the content?
12. **Optional modules:** PPR/bonus (R-340), NPS collection channel (R-311) and the voice-transcription processor (R-321). Build or drop?
13. **White-label identity:** product name and branding (rename "Orbity"?), and whether the public landing stays ours or goes per tenant (R-355).
14. **The reference operator's own subscription:** comped or billed through our seed billing (R-287)?
