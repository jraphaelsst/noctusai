# orbity · pages, CRUD matrix and dataflow

> Born 2026-10-15 from the re-activation pass (catalog `ativo=true`, `deploy_scope=dev`):
> a read-only code audit of every page + a live browser smoke test against the real
> Supabase project (local backend :8010 / frontend :8140 / Core :8000). Read this before
> touching any orbity page, adding an entity, or wiring an integration seam. It is the
> per-page map; the absorption history lives in `KB § ABSORPTIONS/orbity/`.
>
> **Status column legend** — ✅ verified live (browser) · 🧪 covered by tests only ·
> ⚠️ works with a caveat · 🔴 broken / missing.

## 0 · Shape of every page

```
page (frontend/src/pages/X.tsx)
  └─ hook (frontend/src/hooks/useX.ts, TanStack Query; invalidates its own keys)
       └─ HTTP  /api/<area>/…  (Bearer = Supabase session JWT; org from noctus_users)
            └─ router (backend/app/routers/<area>_router.py — strict Pydantic in/out)
                 └─ service (backend/app/services/<area>_service.py — user-scoped client, RLS)
                      └─ table(s) in schema `orbity` (RLS on every table; migrations 001–017)
```

- **Payload rule:** every router dumps request models with `model_dump(mode="json", …)`
  before they reach supabase-py. Plain `model_dump()` leaks `UUID`/`date`/`Decimal` into
  the JSON encoder → live 502 (this happened on `POST /api/crm/leads`, fixed `5e7c010c3`).
  Regression shape: `backend/tests/routers/test_json_serialization_e2e.py` (router → real
  service → seed `MockSupabaseClient`, which validates JSON-serializability).
- **Destructive actions** confirm through the seed organ `useConfirm()` (`@noctusai/lib`,
  provider mounted by `createProductApp`) — never `window.confirm` (it freezes the renderer
  and breaks browser automation).
- **Loading signals:** `showSkeleton = isPending && !data`, `isRefreshing = isFetching && !!data`
  (`KB § PATTERNS/frontend/lying-loading-state.md`).
- **Shell calls on every page:** `GET /api/me/access` (orbity), `GET /api/notificacoes*`
  (seed), and Core `GET /api/me/consents` + `GET /api/admin/llm-spend/{org}` (port 8000).
  Locally, Core must run too or a "Servidor indisponível" toast fires on every page.
- **Nav visibility:** `App.tsx` `NAV_GROUPS`, filtered by `orbity.status_pagina`
  (all keys seeded `producao` in 001/008/013).

## 1 · Route table

| Path | Page | Nav (group) | Auth |
|---|---|---|---|
| `/` | Dashboard | Dashboard (Principal) | yes |
| `/equipe` | Equipe | Equipe (Principal) | yes |
| `/financeiro/*` | Financeiro (`/contratos`, `/cobrancas` + the finance organ's sections) | Financeiro (Principal) | yes |
| `/clientes` | Clientes | Clientes (CRM) | yes |
| `/funil` | Funil | Funil (CRM) | yes |
| `/tarefas` · `/agenda` · `/rotinas` | Tarefas · Agenda · Rotinas | Operações | yes |
| `/conteudo` · `/trafego` · `/automacao` · `/relatorios` | Conteúdo · Tráfego · Automação · Relatórios | Marketing | yes |
| `/relatorio/:token` | RelatorioPublico | — | public, token + published + expiry, rate-limited |
| `/aprovar/:token` | AprovacaoPublica | — | public, token, rate-limited |
| landing / login / forgot / accept-invite / 404 | seed slots of `createProductApp` | — | public |

## 2 · Per page

### Dashboard
- **Purpose:** landing after login — KPI row + module cards.
- **Dataflow:** composes existing endpoints only (clients, `GET /api/crm/funil`, `GET /api/tasks`,
  `GET /api/financial/cash-flow/{YYYY-MM}`, agenda next 7 days). No dashboard-specific backend.
- **CRUD:** none (navigation hub).

### Clientes — `orbity.clients`
- **Dataflow:** seed `ResourceManager` (list only) + `ClientForm` → `GET/POST /api/clients`, `PATCH /api/clients/{id}`,
  `GET /api/clients/cnpj/{cnpj}` (Razão Social from the public CNPJ registry), `GET /api/clients/{id}/offboarding-preview`,
  `POST /api/clients/{id}/archive` → `clients_router` → `ClientsService` / `services/offboarding.py`.
- **Razão Social:** `legal_name` is REQUIRED (it is what contracts snapshot and what the payment gateway charges); `name` is
  the optional **nome fantasia** and falls back to the legal name. "Buscar CNPJ" prefills an empty Razão Social (a typed one is
  only replaced by an explicit "Usar"). `document` (CPF/CNPJ, validated check digits) is required by the gateway.
- **Inativar (admin only):** never a flag flip. `ClientOffboardingDialog` lists the open charges (pending + overdue); per charge
  **Cancelar** (default) or **Manter**. One server operation: atomic RPC `orbity.offboard_client` (charges + client row) →
  contracts terminated through the seed contracts organ (a kept charge survives the termination) → cancelled charges cancelled at
  the gateway too (failures recorded + retried, never swallowed). `PATCH active=false` is refused (409). Re-running the call finishes
  a half-done offboarding. Reativar = `PATCH active=true` (ended contracts stay ended).
- **CRUD:** C ✅ · R ✅ · U ✅ · D = inativar (soft, with the dialog above) ✅ · "Mostrar inativos" + "Reativar".
- **Fields:** legal_name*, name, document, email, phone, monthly_value, due_date (1–31), billing_type
  (boleto/pix → gateway · cartão/transferência → plain receivable), billing_automation flag (**now live**: with a gateway and a
  boleto/pix client, the contract's monthly receivable is sent to the gateway).

### Funil — `leads`, `lead_stages`, `lead_activities`, `lead_scoring_rules`
- **Dataflow:** `useCrm` → `GET /api/crm/funil` (stages + leads), `POST/PATCH/DELETE /api/crm/leads[/{id}]`,
  `PATCH /leads/{id}/stage` (optimistic), `GET/POST /leads/{id}/activities`,
  `POST /stages/seed-defaults`. Seed `KanbanBoard` organ.
- **CRUD:** Lead C ✅ (was a live 502 — UUID serialization, fixed `5e7c010c3`) · R ✅ · U · D ✅ (in-app
  confirm). Card buttons `stopPropagation`; the detail panel closes on Esc and when its lead
  disappears. Stage: seed-defaults only (no rename/reorder/colour). Activity: C/R only.
- **Orphans (backend without UI):** scoring rules CRUD, `POST /leads/{id}/score`,
  public capture `POST /api/capture/{org_id}` (rate-limited; no embed/URL shown in UI).

### Tarefas — `orbity.tasks`
- **Dataflow:** `useTasks` → `GET /api/tasks` (page_size 200), `POST`, `PATCH /{id}`,
  `PATCH /{id}/status` (optimistic), `DELETE /{id}`.
- **CRUD:** C ✅ · R ✅ · U ✅ (status move verified; `canceled` settable) · D ✅ (in-app confirm).

### Agenda — `orbity.agenda_events`
- **Dataflow:** `useAgenda` → `/api/agenda/events` CRUD + `POST /{id}/sync-gcal`.
- **CRUD:** C ✅ (19:00 BRT stored as 22:00Z, displayed 19:00) · R ✅ · U (local-time edit input,
  `lib/dates.ts`) · D (in-app confirm). Sync button + badge say "simulado".
- **Seam:** Google Calendar = **FakeCalendarAdapter, no env switch** (`agenda_router.py`
  → `agenda_service.py`); UI must label sync as simulated until the Real adapter is wired.

### Rotinas — `orbity.routines` → inserts `orbity.tasks`
- **Dataflow:** `useRoutines` → `/api/routines` CRUD + `POST /api/routines/run-due`.
- **CRUD:** C ✅ · R ✅ · run-due ✅ (created the task, next run +7d) · U · D; run-due is manual (no scheduler).

### Financeiro — seed organs `fin_*` (finance) + `ctr_*` (contracts) + `billing_charges`
- **Shape:** `/financeiro/*` (URL = tab). **Financeiro** = seed `FinanceRoutedPage` (visão geral · receber · pagar · fluxo de caixa ·
  DRE · conciliação · cadastros) over `/api/finance`; **Contratos** = seed `ContractsTable` (editor, aditivos, reajuste, suspender,
  encerrar, prévia das próximas cobranças) over `/api/contracts`, the customer picked from Clientes (`party_id` = client id);
  **Cobranças** = `ChargesPanel` over `/api/financial/*`: month summary + every receivable with its gateway **status banner**
  (queued / generating / retrying / generated / failed + last error / skipped + why).
- **Billing:** the seed job `contracts_generate_billing` (daily) books each active contract's monthly receivable — idempotent per
  contract + cycle (`source='contracts'`, `source_ref=<contract>:<due>`). It books through `OrbityContractsBilling` (the
  `mount_contracts(get_billing=…)` seam), which records the receivable's gateway state in `billing_charges`.
- **Gateway (Asaas, per-org credentials `asaas_api_key` / `asaas_environment` / `asaas_webhook_token`):** the job
  `orbity_billing_process` (2 min) claims queued rows (`billing_reserve_charges`: SKIP LOCKED + recovery of rows a crashed worker
  left in `generating`), creates the PIX/boleto charge with `externalReference=orbity:<entry_id>` on EVERY attempt and asks the gateway
  to reuse a charge already carrying it (a timeout + retry never double-charges), backs off (0/2/10/30/120 min, 5 attempts), and
  records the last error. **No gateway configured ⇒ the receivable stays a plain receivable (`skipped` + the reason) — never faked.**
  Webhook: `POST /api/billing/webhook/asaas/{org_id}` (per-org token, fail-closed, durable inbox) settles the receivable.
- **Cash flow rule** (`GET /api/financial/cash-flow/{month}`): paid always counts, cancelled never, an open charge counts when it was
  **kept after the client's inactivation** or the client was active that month (unit-tested in `test_financial_rules.py`).
- **Data placement:** the organs own their tables (`fin_*`, `ctr_*` — there is no organ-over-product-tables seam), so migration 023
  MOVED `orbity.contracts/revenues/expenses` onto them (ids and cents preserved, SMOKE-TEST rows included); the old tables remain as
  `*_legacy`, and read-only views `orbity.revenues/expenses` keep `reports_service` answering from the new ledger.
- **Caveats:** Conexa has no seed adapter (`NOC-REMEDIATE[orbity-conexa-adapter]` in `app/billing.py`); billing reminders are a separate
  organ; `NOC-REMEDIATE[orbity-reports-on-fin-entries]` (move `reports_service` onto `fin_entries`, drop the views).

### Tráfego — `ad_accounts`, `campaigns`, `campaign_metrics`
- **Dataflow:** `useMetaAds` → `/api/meta-ads/ad-accounts` CRUD, `/campaigns` CRUD,
  `PATCH /campaigns/{id}/situation`, `POST /sync`, `GET /aggregate`,
  `GET|PUT /campaigns/{id}/metrics` (PUT = manual metric entry: date, spend, impressions,
  leads, cpl?; added `5e7c010c3`).
- **Live:** account C ✅ (linked to a client) · campaign C ✅ · manual metric PUT ✅ (spend 120 /
  6 leads → CPL 20 derived) · 30-day aggregate ✅.
- **Seam:** Meta Ads = **Fake client, unconditional** (`NOC-REMEDIATE[orbity-meta-ads-live]`);
  page carries an honesty banner. `sync_campaigns` no longer overwrites `situation`.

### Automação — `automation_flows`, `automation_steps`, `automation_executions`, `automation_pending_actions`
- **Dataflow:** `useAutomacao` → `/api/automation/flows` CRUD, `/flows/{id}/steps` + `/steps/{id}`,
  `POST /flows/{id}/trigger`, `GET/DELETE /executions`, `POST /run-due`.
- **Live:** flow C ✅ · step C ✅ · manual trigger for a lead (LeadSelect) ✅ → execution "Concluída".
- **Seam:** WhatsApp sender = **FakeWhatsAppSender, unconditional** (page banner says "simulado");
  13 of 14 trigger types are never emitted — the select shows them "(em breve)" and disabled
  (`LIVE_TRIGGERS` in `Automacao.tsx`: add a type there in the same commit as its emitter);
  `action` steps are no-ops; no scheduler (`NOC-REMEDIATE[orbity-automation-scheduler]`).

### Conteúdo — `content_campaigns`, `content_posts`, `post_approvals`, `content_plans`, `content_plan_items`
- **Dataflow:** `useConteudo` → `/api/content/campaigns` CRUD, `/posts` CRUD,
  `POST /posts/{id}/approvals` (token link → `/aprovar/{token}`).
- **Live:** post C ✅ (client-linked) → "Enviar para aprovação" ✅ → `/aprovar/{token}` ✅ → client
  "Aprovar" ✅ → post `approved`. Public page type mirrors backend `PublicApprovalView` (FLAT —
  a nested FE type once made every link render "Decisão já registrada"). The decision notifies
  the post assignee, else org `ADMIN_ROLES`, via seed `write_in_app` (kind `aprovacao_conteudo`);
  the page claims "equipe notificada" only when `team_notified > 0`.
- **Caveats:** "Publicado" is a manual status (`NOC-REMEDIATE[orbity-content-publish]`);
  approval history endpoints exist (`GET /approvals*`) without UI.
- **Planejamento tab (migration 020):** `useContentPlans` → `/api/content/plans/*`. A plan
  (client + month + `strategy_context`, `creation_mode` manual|ai) holds ordered
  `content_plan_items` (`order_position`; `planned|task_created|in_progress|published|discarded`).
  **Reuse, not duplication:** `plan.campaign_id` → `content_campaigns`; `item.task_id` → `tasks`
  (via `TasksService`, due = `due_date ?? post_date`, caption + references in the description,
  only items with no task and not discarded); `item.post_id` → a DRAFT `content_posts` row
  (`POST /plans/{id}/items/{item}/post`) that then rides the unchanged approval flow — items never
  carry approval state. Delete item: has task → `discarded` (task kept), else hard delete.
  Card progress excludes discarded; Manual/IA badge from `creation_mode`; the sheet opens editable.
- **AI items:** `POST /plans/{id}/ai-items` → `content_plan_ai_service` → seed
  `chat_completion` (provider abstraction + budget/usage governance; key = org/platform
  `openai_api_key` credential or env `OPENAI_API_KEY`). Strict validation (exact count, dates in
  window + allowed weekdays, requested platforms, no repeated titles; one corrective retry);
  returns a PREVIEW only — the UI appends the checked items. No key → honest **503**, invalid
  output → 502; never fake output. Rate-limited 10/min.
- **Caveats:** "Publicado" is a manual status (`NOC-REMEDIATE[orbity-content-publish]`);
  approval history endpoints exist (`GET /approvals*`) without UI. "Criar tarefas" claims each
  item by compare-and-set (`status='task_pending'` WHERE `task_id IS NULL` and not
  discarded/pending) before creating its task, so concurrent calls never double-create; a failed
  task insert releases the claim. A crash between claim and link leaves the item in `task_pending`
  (needs a manual status reset).

### Relatórios — `reports`, `report_snapshots` (+ reads leads/revenues/expenses/campaign_metrics)
- **Dataflow:** `useRelatorios` → `/api/reports` CRUD, `GET /{id}/snapshots`, `POST /{id}/generate`;
  public read `GET /api/reports/public/{token}` (rate-limited).
- **Scoping (fixed `5e7c010c3`):** a report with `client_id` aggregates ONLY that client's
  leads/revenues/Meta campaigns; `expenses` has no `client_id`, so client reports return
  `{available:false, reason}` instead of the org total. Query failures raise — no silent zeros.
- **Live:** report C ✅ (client-linked, published) → snapshot ✅ (Meta spend/leads/CPL scoped to the
  client) → `/relatorio/{token}` ✅. `lib/reportPayload.ts` `audience:"public"` hides unavailable
  metrics, scope and snapshot metadata from the client page; backend reasons are mapped to pt-BR.

### Equipe
- Seed `TeamPage` + admin-only `StatusPaginaPanel` (`@noctusai/lib`) → seed `/api/team/*`,
  `/api/status-paginas` → `orbity.invitations`, `orbity.status_pagina`.

## 3 · Integration seams (Fake vs Real)

| Seam | Selected at | Today | To go Real |
|---|---|---|---|
| Google Calendar | `agenda_router.py` → `agenda_service.py` | Fake, no switch | settings flag + seed GCal Real adapter + per-org OAuth (`KB § INTEGRATIONS/`) |
| Meta Ads | `meta_ads_service._make_default_client` | Fake, no switch | seed Meta Real client + insights pull into `campaign_metrics` |
| WhatsApp | `automation_service.py` / `automation_engine.py` | Fake, no switch | seed WAHA sender + `whatsapp_connections` organ + inbound webhook to emit triggers |

## 4 · Known debt (named destinations)

`NOC-REMEDIATE[orbity-conexa-adapter]` · `[orbity-reports-on-fin-entries]` · `[orbity-meta-ads-live]` · `[orbity-automation-scheduler]` ·
`[orbity-content-publish]` · `[orbity-agenda-gcal]` · `orbity.examples` scaffold table (drop in a
future migration) · `MetaAdsService.get_spend_leads_aggregate` unbatched `.in_` + unpaged select.
