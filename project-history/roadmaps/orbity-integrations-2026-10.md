# orbity-integrations-2026-10 — make orbity talk to the real world, then go live

> **Durable record** (per `KB § PATTERNS/common/roadmap-tracking.md`).
> Origin: the 2026-10-15 re-activation smoke test. Every page's CRUD works, but all three
> integrations (WhatsApp, Meta Ads, Google Calendar) are simulated, the automation engine has
> no scheduler, and 13 of 14 triggers never fire.
> Decision: **integrations first, then AI. Promote orbity to `live` only after the
> automation + WhatsApp phases ship and pass a live smoke.** (owner, 2026-10-15)

## Origin

The owner re-activated orbity on 2026-10-15 and asked for an up-to-date, fully smoke-tested product
plus improvements. The pass is recorded in the assessment doc
(https://claude.ai/code/artifact/6b0c78db-bffe-4d23-b037-ba22d639afda) and
`KB § PRODUCTS/orbity/PAGES-AND-DATAFLOW.md`. It fixed 12 findings, including 3 blockers.

Its "still weak" list ranked the simulated integrations first. The owner then chose:
1. Integrations first.
2. Live promotion only after them.
3. Keep the SMOKE-TEST demo data.
4. A fleet-wide `model_dump(mode="json")` sweep.

The seed was verified on 2026-10-15 (`seed-ships-verified` at `e81be3cbe`):
- **CONSUME:** WhatsApp/WAHA sender, connections organ, inbound webhook, `api.scheduler`, Google Calendar adapter, and the Meta insights adapter.
- **EXTEND:** a Meta per-org OAuth provider (`make_oauth_provider` supports only `google`).
- **BUILD (in orbity):** domain-event emitters. There is no seed bus; the house pattern is igig's direct call after commit.

## Trigger conditions (the "when")

| # | Trigger | Detection signal | Why it tips the balance |
|---|---|---|---|
| T1 | P1+P2 merged and live-smoked locally | A real WhatsApp message is received on the owner's phone from an orbity flow fired by a real event (lead created) | The owner's precondition for live |
| T2 | Owner says "promote orbity" | Canonical phrase in the transcript (`KB § PATTERNS/devops/prod-exposure-consent.md`) | Prod exposure is the owner's decision, never an agent's |
| T3 | An agency client needs real ad metrics or calendar sync | Owner request, or manual metric entry becomes a weekly chore | Meta and GCal need per-org OAuth: real cost, so only on demand |
| T4 | P1–P3 stable for 2 weeks in prod | No automation errors in logs and no owner-reported misfire | AI drafts build on trusted data and working sends |

**Today's status (2026-10-15)**: none fired. P1+P2 dispatched.

## Phase 0 — re-activation pass (SHIPPED 2026-10-15)

| # | Title | Commits | Status | Verify recipe |
|---|---|---|---|---|
| P0.1 | JSON-mode payload dumps (lead-create 502), client-scoped reports, metrics PUT, public rate limits | `5e7c010c3` | **shipped** | Browser: create lead in Funil → 201; report snapshot for a client shows only that client's ads |
| P0.2 | Seed `ConfirmProvider`/`useConfirm` + orbity pilot + fan-out (core, igig, agents, social-wiring) | `43143a48f`, `e81be3cbe` | **shipped** | Delete in any page opens the in-app dialog; no native popup |
| P0.3 | FE page fixes: pickers, honest simulated states, tz, dialog reset, Dashboard KPIs, accents | `697eea6e3` | **shipped** | Dashboard KPI row shows real counts |
| P0.4 | Public approval contract + real team notification; client-safe public report; disabled never-firing triggers | `ba9015cd2`, `b9b489d2a` | **shipped** | `/aprovar/{token}` → Aprovar → post `approved` + notification row |

## Phase 1 — automation that runs by itself (IN PROGRESS, branch `feat/orbity-automation-be`)

| # | Title | Files | Verify recipe |
|---|---|---|---|
| P1.1 | Migration 018: idempotent executions (trigger key), non-lead subjects, action claim/lease | `backend/migrations/018_*.sql` | Applied in Supabase; `select` the new columns; a duplicate event starts one execution |
| P1.2 | Engine: claim due actions atomically, advance executions after each action, failures recorded in pt-BR, `action` steps executed or failed explicitly | `automation_engine.py`, `automation_service.py` | A 3-step flow (send, wait 1 min, send) completes on its own |
| P1.3 | Scheduler: `orbity_automacao_run_due` (1 min) + `orbity_rotinas_run_due` (15 min) via `noctusai_lib.api.scheduler` | `app/scheduler.py`, `main.py` | `GET /api/scheduler/jobs` lists both; a due routine creates its task with nobody clicking |
| P1.4 | Emitters: `automation_triggers.disparar` from routers after commit | `app/services/automation_triggers.py` + routers | Create a lead → the `lead_created` flow's execution appears |
| P1.5 | FE: enable exactly the triggers the backend emits (`LIVE_TRIGGERS`) | `frontend/src/pages/Automacao.tsx` | Only emitted triggers are selectable |

## Phase 2 — real WhatsApp (IN PROGRESS, branches `feat/orbity-automation-be` + `feat/orbity-whatsapp-fe`)

| # | Title | Files | Verify recipe |
|---|---|---|---|
| P2.1 | `orbity.whatsapp_connections` + seed connections router + per-connection inbound webhook | migration 018, `main.py`, router wiring | Connect a WAHA session in the UI → status `WORKING` |
| P2.2 | `RealWhatsAppSender`: org connection → `resolve_fake_or_refuse` → `get_whatsapp_client`; an unconfigured org fails explicitly | `app/services/whatsapp_sender.py` | Fire a flow at a lead with the owner's own phone → the message arrives |
| P2.3 | Inbound triggers `whatsapp_message_received` / `keyword_received` (known leads only) | webhook handler + emitters | Reply from the owner's phone → the keyword flow runs |
| P2.4 | FE: connections page (seed organ), state-driven banner, step-config forms | `frontend/src/pages/*` | Banner disappears once connected |

## Phase 3 — promote to live (DEFERRED — fires on T1 + T2)

| # | Title | Verify recipe |
|---|---|---|
| P3.1 | `deploy_scope=live` in `/admin/products` (owner) → scope bot → build-scope | `deploy/fleet/build-scope.txt` lists orbity |
| P3.2 | `predeploy_check` + CI green → `deploy_image` (auto-rollback is the net) | https://orbity.noctusai.com/api/health 200 |
| P3.3 | Prod smoke of every page (the same matrix as the doc) | Matrix all ✅ in prod |

## Phase 4 — Meta Ads + Google Calendar (DEFERRED — fires on T3)

| # | Title | Verify recipe |
|---|---|---|
| P4.1 | `MetaAdsClient` → thin adapter over seed `get_meta_adapter` (system-user token first) + nightly insights pull into `campaign_metrics` | A real campaign's spend matches Ads Manager for yesterday |
| P4.2 | Per-org Meta OAuth: seed `MetaProvider` for `oauth_router` (EXTEND), not a social-wiring copy | Connect flow stores a token in `credential_store` |
| P4.3 | GCal: `AgendaService(calendar_adapter=get_calendar_adapter(credential_store=…, tenant_id=org))` + Google connect via `oauth_router` | An event appears in the owner's Google Calendar |

## Phase 5 — AI features (DEFERRED — fires on T4)

Ranked in the assessment doc:
1. Report narrative
2. Caption + hashtag assistant
3. Lead triage (fills scoring)
4. Revision summariser
5. Meeting notes → tasks
6. Campaign anomaly alert
7. Ask orbity

All calls go through `noctusai_lib.integrations.llm` (cost-logged), drafts-only, org-scoped.

## Fleet track — `model_dump(mode="json")` (IN PROGRESS, owner-approved 2026-10-15)

| # | Title | Branch | Verify recipe |
|---|---|---|---|
| F.1 | Sweep active products + seed template; router→real-service→MockSupabase regression per product | `feat/fleet-json-dump-sweep` | Keeper full report = 0 in active scope |
| F.2 | Keeper `check_model_dump_json_mode` (delta-scoped pre-commit) + KB rule, same commit | `feat/keeper-model-dump-json` | Staging a new offending dump blocks the commit |

Asleep products (community, erp-imobiliario, …) are swept when they wake; the keeper flags them then.

## Anti-goals

- ❌ No orbity-local event bus or outbox. igig's direct-call-after-commit pattern plus a per-occurrence claim is the house shape; lift it to the seed at the third consumer.
- ❌ No copy of social-wiring's Meta connect handlers. Extend the seed with a `MetaProvider` instead.
- ❌ No fake success anywhere. An unconfigured integration fails visibly, in pt-BR.
- ❌ No promotion to live by an agent.
- ❌ No deletion of SMOKE-TEST demo data.

## Open questions

- **Q1**: Inbound WhatsApp from an unknown number: create a lead, or ignore? (P2.3 starts conservative: known leads only.)
- **Q2**: The resolver for an org's WhatsApp client is now in community and orbity (N=2). Lift `resolve_org_whatsapp_client` to the seed at N=3.
- **Q3**: Should routines move to seed `domain.jobs` for retries/leases, or is the scheduler + claim enough?

## Decision log

- **2026-10-15**: Re-activation pass shipped (Phase 0). The owner chose integrations first, live only after P1+P2, keep demo data, and approved the fleet sweep. The seed was verified at `e81be3cbe`. P1+P2 and the fleet track were dispatched.

## Retrospective (filled at first trigger fire)

*To be filled at T1.*

## Composes with

- `KB § PRODUCTS/orbity/PAGES-AND-DATAFLOW.md` (per-page map)
- `project-history/roadmaps/orbity-2026-06.md` (original build roadmap)
- `KB § PATTERNS/devops/prod-exposure-consent.md` (T2)
- `KB § PATTERNS/architect/product-working-scope.md` (scope toggle)
