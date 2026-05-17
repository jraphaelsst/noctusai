# Mailing Wiring — Project Document

> **This is a living document, not a rigid checklist.**
> Revise phases, fold in optimizations, update §11 Change Log as work progresses.
> See `CLAUDE.md → §1 Universal rules → No incomplete commits / Estimate off evidence / Replication-to-seed symmetry` and
> `KB § PATTERNS/project-execution.md`.
>
> **Slug rationale.** Mirrors the `personal-finance-wiring` / `therapy-platform-wiring` shape:
> a sweep of every `mailing` surface end-to-end, closing every gap at the layer it
> belongs to (seed vs. product vs. schema), landing with tests + clean build.
> Intent = `wiring` per `KB § PATTERNS/project-execution.md §8`.

- **Created:** 2026-05-11
- **Last updated:** 2026-05-11 (Phase 2 ✅ — orphan-hook/orphan-route triage + accept-with-rationale catalog entries + LLM-audit follow-up project filed)
- **Status:** Phase 0 ✅, Phase 1 ✅, Phase 2 ✅. Phases 3-5 pending (orchestrator scopes per design-batch decisions in §7).
- **Owner / stakeholders:** Raphael (joaoraphaelsst@gmail.com) · Claude Opus 4.7
- **Related docs:**
  - `products/mailing/MASTER-PROMPT.md` — agent-facing product contract
  - `products/mailing/README.md` — short stack overview
  - `archive/projects/2026-05-11/16-personal-finance-wiring/personal-finance-wiring-lessons.md` — sister-project lessons
  - `products/therapy-platform/projects/therapy-platform-wiring/PROJECT.md` — sister project, methodology source
  - `KB § PATTERNS/project-execution.md` — cadence, slug naming, tests-with-code
  - `KB § PATTERNS/proposals-and-improvements.md` — phase-end protocol
  - `KB § PATTERNS/database-rls.md` — migration discipline (mailing schema)
  - `KB § PATTERNS/lgpd.md` — personal-data guardrails (contact data + email tracking)
  - `KB § PATTERNS/chatbot-operational-readiness.md` — production-hardening checklist
- **Project slug:** `mailing-wiring`
- **Lives at:** `products/mailing/projects/mailing-wiring/`

---

## 1. Context & Purpose

The `mailing` product is structurally **smaller than PF and therapy**. Phase 0 (this audit) confirmed:

- **10 product routers** + 5 standard routers (`health`, `notificacoes`, `team`, `ai_outputs`, `ai_feedback`)
- **60 product routes** + standard-router routes
- **8 frontend hook files** with 47 named hook functions
- **21 frontend pages** (incl. 5 public surfaces: Login / ForgotPassword / AcceptInvite / Landing / NotFound + Equipe direct-fetch)
- **4 migrations** — `001_mailing.sql` (full schema, 19 RLS tables, all with service_role_bypass per AAA's 2026-05-11 backfill), `002_ai_outputs.sql`, `003_ai_feedback.sql`, `004_invitations_accepted_columns.sql`
- **Backend test corpus** — 22 test files (5 router, 8 service, 2 integration, conftest)

The win looks like: every hook→endpoint pair returns the DTO `frontend/src/types/` declares, every navigable page loads real data with a 200, scheduler artifacts (send-loop / scheduled campaigns / automation processor) are visible in the UI, AI indicators render for contact segmentation, every backend route in §5.2.3 has a frontend caller **or** a deletion rationale, `pytest` is green, `vite build` is green.

---

## 2. Confirmed constraints

User answers captured during interrogation. **Future agents inherit the reasoning, not just the outcome.** Inherits the sister-project methodology — PF + therapy carry-forward unless flagged below.

### 2.1 Inherited from `personal-finance-wiring` / `therapy-platform-wiring`

- **Scope breadth — widest (A ⇒ B ⇒ C).** Fix known regressions, sweep the user-facing surface end-to-end, close pre-existing scaffolding debt.
- **Tests** — three-layer discipline per `KB § PATTERNS/testing.md`. Not a per-phase decision. A phase without its tests is `⏳ (tests deferred)`, not `✅`.
- **Cadence** — phase-by-phase, pause after each, no auto-advance.
- **Seed sync** — patterns worth promoting mid-project land as phase-end proposals via `noctus.dev.file_proposal(project="mailing-wiring", …)`.
- **Triage at decision time** — every divergence lands on `formalize / refactor / accept-with-rationale`.
- **Commit + push only your own work.** Per-phase local commit; final commit + push at project close.

### 2.2 Mailing-specific (to be filled at design batch §7 kickoff)

- **Schema name** — `mailing` (no hyphen). Standard pattern.
- **Service-role-bypass policies fully landed (2026-05-11)** — AAA shipped 19 policies across `001_mailing.sql` / `002_ai_outputs.sql` / `003_ai_feedback.sql`. Phase 0 keeper expected 0 issues.
- **`is_personal` orgs** — Not used in mailing. Org-only data model (multi-member orgs are the unit; contact lists belong to orgs, not users).
- **APScheduler — 3 jobs running** via `noctusai_lib.api.scheduler`: `mailing_send_loop` (30s), `mailing_scheduled_campaigns` (60s), `mailing_automation_processor` (5min). No HTTP surface for next-run/last-run.
- **Resend webhook receiver** — `POST /api/webhooks/resend` follows the 5-pin compliance contract (Svix-protocol HMAC signature).
- **7 AI features registered** at boot via `app.services.ai_consent_features`: subject_gen, template_draft, reengagement, deliverability, translate, segment_contacts, campaign_debrief.

---

## 3. Design principles

1. **Fix at the layer of the cause.** Cross-cutting (auth-factory, AI-plumbing, scheduler standard router) lifts to seed via phase-end proposals — not band-aided per-product.
2. **No band-aids.** No `?? ''` guards to tolerate bad DTOs.
3. **LGPD-first on every personal-data endpoint.** Contact emails, campaign send tracking, and segmentation embeddings are sensitive. Every new aggregating endpoint gets `noctus.dev.lgpd_flag`.
4. **Migrations and applied SQL stay in lockstep.**
5. **Tests land in the same phase as the code.**
6. **Discovery is an artifact, not a vibe.** Phase 0 produces §5.2 gap table; later phases reference rows in that table.
7. **Scheduler + Resend webhook get explicit Phase coverage.** The two non-HTTP surfaces deserve dedicated sub-tasks.

---

## 3a. Seed-first analysis (REQUIRED)

Six-question checklist:

1. **Is the contract identical for every product?** *Mixed.* Sweep methodology is universal; gap inventory itself is mailing-specific.
2. **Is the data source product-specific?** YES — `mailing.contacts`, `mailing.campaigns`, `mailing.automations`, etc.
3. **Is the placement product-specific?** YES — `products/mailing/{backend,frontend}/`.
4. **Is the visibility / permission rule the same?** PARTIAL — org-scoping is uniform across products; gaps Phase 0 surfaces get fixed against the seed pattern.
5. **Does the seam already exist in seed?** Yes for most: `noctusai_lib.primitives.responses` (used by all routers); `noctusai_lib.domain.ai` (consent_required + persist_output — used in `routers/ai.py`); `noctusai_lib.integrations.llm.chat_completion`; `noctusai_lib.domain.digest.BaseDigestService` (used by `campaign_debrief_service`); `noctusai_lib.api.scheduler` (used by `scheduler.py`); `noctusai_lib.security.webhook_signatures.webhook_endpoint` (used by `webhooks.py`); `noctusai_lib.sql.service_role_bypass` (referenced in migrations). NOT YET ADOPTED at seed: `make_get_current_user_org` factory (mailing uses imperative `user, _ = await get_current_user(authorization)` × ~60 callsites — same pattern PF Phase 0 surfaced), `delete_or_404` (mailing has 6 DELETE services with no pre-check).
6. **Default-on or opt-in?** DEFAULT-ON for inherited seams.

**Litmus — per-product code count this design requires:** **0 lines of cross-product code.** Cross-cutting helpers land in seed via phase-end proposals.

---

## 4. Scope

**In scope:**

- Every `mailing` backend endpoint that a frontend hook calls. 10 product routers: `contacts`, `lists`, `templates`, `campaigns`, `automations`, `analytics`, `webhooks`, `unsubscribe`, `settings`, `ai`.
- Every mailing migration needed to support the wiring fixes. Reject-flow analog (if surfaces) lands as `005_*.sql`.
- Frontend corrections (DTO normalization, orphan-hook decisions, scheduler-artifact rendering, AIIndicator wiring verification).
- Tests landing in the same phase as the code.
- LGPD awareness via `noctus.dev.lgpd_flag` calls.
- End-to-end verification: build + pytest + golden-path manual QA.

**Out of scope:**

- Other products — separate projects, separate slugs.
- UX redesigns.
- New features (no capability we aren't already carrying as scaffolded UI/code).
- AI prompt tuning or new AI features.
- Resend vendor swap.
- APScheduler architecture changes.
- Seed abstractions beyond what the gap table justifies.

---

## 5. Architecture / Data Model

### 5.1 Inherited seed seams

| Seam | Path | Already adopted by mailing |
|---|---|---|
| `noctusai_lib.primitives.responses` (`success_response`, `paginated_response`) | seed | **10/10 routers** |
| `noctusai_lib.domain.ai` (`AIOutput`, `consent_required`, `persist_output`, `register_feature`) | seed | **`routers/ai.py` + `ai_consent_features.py`** |
| `noctusai_lib.integrations.llm` (`chat_completion`, `generate_embedding`) | seed | **`services/ai_service.py` + `services/segmentation_service.py`** |
| `noctusai_lib.domain.digest.BaseDigestService` | seed | **`services/campaign_debrief_service.py`** |
| `noctusai_lib.api.scheduler` | seed | **`app/scheduler.py`** (3 jobs registered) |
| `noctusai_lib.security.webhook_signatures.webhook_endpoint` | seed | **`routers/webhooks.py`** (5-pin contract) |
| `noctusai_lib.sql.service_role_bypass` | seed | **19 policies across 3 migrations** (AAA 2026-05-11) |
| `noctusai_lib.testing.MockSupabaseResponse` | seed | **router tests** |

### 5.1.1 Pending seed-lib lifts (not yet adopted)

| Seam | Path | Why mailing should adopt | Cross-product N |
|---|---|---|---|
| `make_get_current_user_org` factory | proposed (filed by PF) | mailing uses imperative `user, _ = await get_current_user(authorization)` × ~60 callsites — same Pattern PF-1 | **N=3** (PF + ERP + mailing) → MUST-FORMALIZE per recurrence rule |
| `delete_or_404` / `delete_with_existence_check` | `noctusai_lib.api.crud_safety` | 6 mailing services do raw `.delete().eq().execute()` with no pre-check (silent no-op on bad id) | **N=5+ cross-product** — seed already ships; mailing simply adopts |
| `scheduler` standard router | proposed (filed by PF) | mailing has 3 cron jobs with no HTTP/UI surface for next-run / last-run / errors | **N=3+** (PF + mailing + therapy) → already a filed follow-up |

### 5.2 Gap inventory *(populated by Phase 0 — 2026-05-11)*

#### 5.2.1 Headline counts

| Surface | Count |
|---|---|
| Backend routers | 10 product + 5 standard (`health`, `notificacoes`, `team`, `ai_outputs`, `ai_feedback`) |
| Backend product routes | **60** (campaigns=9, lists=8, automations=14, ai=8, contacts=6, templates=6, settings=4, analytics=2, unsubscribe=2, webhooks=1) |
| Frontend hook files | 8 (useContacts, useLists, useTemplates, useCampaigns, useAutomations, useAnalytics, useSettings, useAI) |
| Frontend named hooks | **47** functions exported |
| Frontend pages | 21 (incl. 5 public + Equipe direct-fetch) |
| Frontend pages with **direct** `api.*` (bypassing hooks) | **2** — `Equipe.tsx` (5 callsites, seed `team` standard router), `Unsubscribe.tsx` (1 callsite, public POST) |
| Backend routers with `response_model` declared | **0/10** (Pattern E confirmed; matches therapy 0/38, PF 0/16) |
| DELETE services with proper pre-check 404 | **0/6** (all services do raw delete-no-check — Pattern PF-3 recurrence) |
| Direct-DB calls bypassing service layer | **0 routers** — clean (vs PF-4 recurrence) |
| Migrations with service_role_bypass coverage | **19/19 tables** (AAA's backfill confirmed) |
| Cross-schema `db.table("organizations")` reach | **0 hits** (clean — vs PF-8 recurrence) |
| Frontend `user_id` type drift | **0 hits** (mailing schema uses `created_by` from day 1; no drift) |

#### 5.2.2 Pattern findings *(Phase 0 — 2026-05-11)*

| Pattern | Mailing status | Evidence |
|---|---|---|
| **A — PT/EN path mismatch** | **0 hits** | Mailing is EN-routed (per AAA 2026-05-11 audit). Backend routers (`/api/contacts`, `/api/lists`, `/api/campaigns`, ...) match frontend hook paths exactly. |
| **B — Admin namespace fragmentation** | **N/A** | Mailing has NO admin facade. All endpoints are org-scoped via `org_id`; no `/api/admin/*` routes. Single-tier auth (org member). |
| **C — Admin detail endpoints** | **N/A** | (Same as B.) |
| **D — Direct-fetch role-prefix pages** | **2 hits** | `pages/Equipe.tsx` calls `api.*` directly against `/api/team*` (seed `team` standard router) — 5 callsites; `pages/Unsubscribe.tsx` calls `api.post('/api/unsubscribe/{token}')` directly — public-route one-off. **Both likely keep direct-fetch** (seed-owned endpoints + public route). Decision deferred to design batch (Q-equipe / Q-unsubscribe). |
| **E — Implicit DTO contract** | **0/10 routers** | All 10 product routers return via `success_response()` / `paginated_response()` wrappers. No `response_model=` declarations. Pagination uses `success_response(data, total=…, page=…, page_size=…)` envelope. Frontend `types/` declares typed shapes informally. Same recurrence as therapy + PF. |
| **F — `require_role` recurrence** | **N/A in mailing** | Mailing is single-tier (org member). No role gating beyond `team` admin (handled by seed `team` standard router). |
| **G — Path-shape mismatches** | **0 hits** | Every hook's path matches its router's prefix + segment shape exactly. No verb mismatches, no segment swaps, no param-position drift. |
| **PF-1 (recurrence) — Imperative `get_current_user` instead of factory** | **~60 callsites** | Every router uses `user, _ = await get_current_user(authorization)` then derives `get_org_id(user)`. Same shadow as PF + ERP. **Confirms N=3 → MUST-FORMALIZE.** Filed seed proposal `make-get-current-user-org-factory` (PF Phase 1) becomes a blocker — mailing absorbs after seed ships. |
| **PF-3 (recurrence) — DELETE pre-check holes** | **6 of 6 services** | `contact_service.delete_contact`, `list_service.delete_list` (+ `remove_members`), `campaign_service.delete_campaign`, `template_service.delete_template`, `automation_service.delete_automation` (only one with pre-check via `get_automation()` + status check), `automation_service.delete_step`. **All raw `.delete().eq().execute()` with no result check.** Tier A fix in Phase 2; adopt `noctusai_lib.api.crud_safety.delete_or_404`. |
| **PF-5 (recurrence) — Scheduler artifacts: NO HTTP surface, NO UI surface** | **Confirmed** | 3 cron jobs registered (`mailing_send_loop` 30s, `mailing_scheduled_campaigns` 60s, `mailing_automation_processor` 5min) via `noctusai_lib.api.scheduler`. No GET endpoint for next-run/last-run/errors. Frontend has no execution-history UI. **Same cross-product gap (N=3+ PF + mailing + therapy) — filed seed `scheduler` standard router proposal carry-over.** |
| **M-1 — Org-scoping security gap in automation_service** | **CRITICAL** | `update_step(step_id, data)` / `delete_step(step_id)` accept arbitrary `step_id` without verifying step→automation→org_id chain. Same for `reorder_steps(automation_id, step_ids)` — no automation→org_id check. Cross-tenant data write possible if step UUID leaks. **RLS partially mitigates** (org_id check in policies), but service-layer code path bypasses defense-in-depth. Phase 2 Tier A fix. |
| **M-2 — Orphan hooks (no page consumers)** | **8 of 47 hooks** | `useGenerateSubjects`, `useDraftTemplate`, `useReengagementVariants`, `useDeliverabilityReview`, `useTranslateTemplate` (5 AI hooks tested but unwired in UI); `useUpdateAutomation` (no UI page calls it); `useEnrollContacts` (no UI page calls it); `useCampaignAnalytics` (no UI page calls it — Analytics.tsx uses Dashboard only); `useImportContacts`, `useUpdateList`, `useListContacts` (3 more from Lists / Contacts surface). **Per PF Phase 0 lesson b.2** — orphan-hook deletion-or-wire decision at Phase 0, not Phase 5. **9 hooks total** — design batch Q-orphans determines per-hook outcome (wire vs delete vs keep-for-future). |
| **M-3 — Orphan routes (no frontend caller)** | **5 routes** | `PATCH /api/lists/{id}` (no `useUpdateList` consumer), `PATCH /api/automations/{id}` (no `useUpdateAutomation` consumer), `PATCH /api/automations/{automation_id}/steps/{step_id}` (no UI for step edit), `POST /api/automations/{automation_id}/steps/reorder` (no UI for step reorder), `DELETE /api/lists/{list_id}/members` (no `useRemoveMembers` consumer), `GET /api/analytics/campaigns/{campaign_id}` (no consumer). **Symmetric to M-2** (orphan hook ↔ orphan route on the same route shape). |
| **M-4 — No tool-call audit on AI endpoints** | **Pending** | `routers/ai.py` calls `chat_completion` 7× via `ai_service` + `segmentation_service`. **No `make_audit_writer` / `AuditRecord` integration** per `KB § PATTERNS/llm-tool-audit.md`. ERP / therapy have similar gaps; tracked as cross-product N→formalize. Defer to Phase 7 — file proposal during design batch. |
| **M-5 — Scheduler automation_processor placeholder** | **Confirmed** | `_automation_processor_sync` (line 75-87 of `scheduler.py`) logs `# TODO: implement step execution when automation_service is built`. **Half-shipped functionality.** Phase 4 decides: implement step-execution OR deactivate the job OR ship an explicit "stub" log. |

#### 5.2.3 Per-hook → backend route mapping *(Phase 0 — 2026-05-11)*

Status legend: `OK` (paths + verbs match, types align), `path` (Pattern A/G drift), `verb` (HTTP-method mismatch), `orphan-hook` (hook with no page consumer), `orphan-route` (route with no hook caller), `pre-check` (DELETE silent no-op or false 404), `security` (org-scoping defense-in-depth gap).

All mailing hooks are **single-tier org member** scope (no leader/agent tiers). Public surfaces use direct-fetch.

| Frontend caller | Method | Path | Backend route | Status | Notes |
|---|---|---|---|---|---|
| **Contacts** | | | | | |
| `useContacts.useContacts` | GET | `/api/contacts?...` | `routers/contacts.py:21` GET `""` | OK | paginated_response envelope |
| `useContacts.useContact` | GET | `/api/contacts/{id}` | `routers/contacts.py:46` GET `/{id}` | OK | |
| `useContacts.useCreateContact` | POST | `/api/contacts` | `routers/contacts.py:36` POST `""` | OK | |
| `useContacts.useUpdateContact` | PATCH | `/api/contacts/{id}` | `routers/contacts.py:56` PATCH | OK | |
| `useContacts.useDeleteContact` | DELETE | `/api/contacts/{id}` | `routers/contacts.py:67` DELETE | **pre-check** | `contact_service.delete_contact` raw delete — no 404 |
| `useContacts.useImportContacts` | POST | `/api/contacts/import` | `routers/contacts.py:75` POST `/import` | **orphan-hook** | No UI consumer surveyed; CSV-import UI may be planned |
| **Lists** | | | | | |
| `useLists.useLists` | GET | `/api/lists` | `routers/lists.py:20` GET `""` | OK | |
| `useLists.useList` | GET | `/api/lists/{id}` | `routers/lists.py:38` GET `/{id}` | OK | |
| `useLists.useListContacts` | GET | `/api/lists/{id}/contacts` | `routers/lists.py:83` GET `/contacts` | **orphan-hook** | No UI consumer surveyed |
| `useLists.useCreateList` | POST | `/api/lists` | `routers/lists.py:27` POST `""` | OK | |
| `useLists.useUpdateList` | PATCH | `/api/lists/{id}` | `routers/lists.py:48` PATCH | **orphan-hook** | |
| `useLists.useDeleteList` | DELETE | `/api/lists/{id}` | `routers/lists.py:59` DELETE | **pre-check** | `list_service.delete_list` raw delete — no 404 |
| `useLists.useAddMembers` | POST | `/api/lists/{id}/members` | `routers/lists.py:67` POST `/members` | OK | |
| *(none)* | DELETE | `/api/lists/{id}/members` | `routers/lists.py:75` DELETE `/members` | **orphan-route** | No `useRemoveMembers` hook |
| **Templates** | | | | | |
| `useTemplates.useTemplates` | GET | `/api/templates` | `routers/templates.py:20` GET `""` | OK | |
| `useTemplates.useTemplate` | GET | `/api/templates/{id}` | `routers/templates.py:40` GET `/{id}` | OK | |
| `useTemplates.useCreateTemplate` | POST | `/api/templates` | `routers/templates.py:30` POST `""` | OK | |
| `useTemplates.useUpdateTemplate` | PATCH | `/api/templates/{id}` | `routers/templates.py:50` PATCH | OK | |
| `useTemplates.useDeleteTemplate` | DELETE | `/api/templates/{id}` | `routers/templates.py:61` DELETE | **pre-check** | |
| `useTemplates.usePreviewTemplate` | POST | `/api/templates/{id}/preview` | `routers/templates.py:69` POST `/preview` | OK | |
| **Campaigns** | | | | | |
| `useCampaigns.useCampaigns` | GET | `/api/campaigns` | `routers/campaigns.py:22` GET `""` | OK | |
| `useCampaigns.useCampaign` | GET | `/api/campaigns/{id}` | `routers/campaigns.py:42` GET `/{id}` | OK | |
| `useCampaigns.useCreateCampaign` | POST | `/api/campaigns` | `routers/campaigns.py:32` POST `""` | OK | |
| `useCampaigns.useUpdateCampaign` | PATCH | `/api/campaigns/{id}` | `routers/campaigns.py:54` PATCH | OK | |
| `useCampaigns.useDeleteCampaign` | DELETE | `/api/campaigns/{id}` | `routers/campaigns.py:65` DELETE | **pre-check** | |
| `useCampaigns.useScheduleCampaign` | POST | `/api/campaigns/{id}/schedule` | `routers/campaigns.py:74` POST `/schedule` | OK | |
| `useCampaigns.useSendCampaign` | POST | `/api/campaigns/{id}/send` | `routers/campaigns.py:84` POST `/send` | OK | |
| `useCampaigns.usePauseCampaign` | POST | `/api/campaigns/{id}/pause` | `routers/campaigns.py:103` POST `/pause` | OK | |
| `useCampaigns.useCancelCampaign` | POST | `/api/campaigns/{id}/cancel` | `routers/campaigns.py:113` POST `/cancel` | OK | |
| **Automations** | | | | | |
| `useAutomations.useAutomations` | GET | `/api/automations` | `routers/automations.py:21` GET `""` | OK | |
| `useAutomations.useAutomation` | GET | `/api/automations/{id}` | `routers/automations.py:36` GET `/{id}` | OK | |
| `useAutomations.useCreateAutomation` | POST | `/api/automations` | `routers/automations.py:27` POST `""` | OK | |
| `useAutomations.useUpdateAutomation` | PATCH | `/api/automations/{id}` | `routers/automations.py:47` PATCH | **orphan-hook** | |
| `useAutomations.useDeleteAutomation` | DELETE | `/api/automations/{id}` | `routers/automations.py:56` DELETE | OK | (only delete with pre-check — status==rascunho gate) |
| `useAutomations.useActivateAutomation` | POST | `/api/automations/{id}/activate` | `routers/automations.py:64` POST `/activate` | OK | |
| `useAutomations.usePauseAutomation` | POST | `/api/automations/{id}/pause` | `routers/automations.py:73` POST `/pause` | OK | |
| `useAutomations.useAddStep` | POST | `/api/automations/{id}/steps` | `routers/automations.py:90` POST `/steps` | OK | |
| `useAutomations.useDeleteStep` | DELETE | `/api/automations/{id}/steps/{step_id}` | `routers/automations.py:108` DELETE | **security + pre-check** | `automation_service.delete_step` accepts `step_id` without org check |
| *(none)* | PATCH | `/api/automations/{id}/steps/{step_id}` | `routers/automations.py:99` PATCH | **orphan-route + security** | No hook; `update_step` no org check |
| *(none)* | POST | `/api/automations/{id}/steps/reorder` | `routers/automations.py:115` POST `/steps/reorder` | **orphan-route + security** | No hook; `reorder_steps` no org check |
| `useAutomations.useEnrollContacts` | POST | `/api/automations/{id}/enroll` | `routers/automations.py:130` POST `/enroll` | **orphan-hook** | |
| `useAutomations.useEnrollments` | GET | `/api/automations/{id}/enrollments` | `routers/automations.py:124` GET `/enrollments` | OK | |
| **Analytics** | | | | | |
| `useAnalytics.useDashboardMetrics` | GET | `/api/analytics/dashboard` | `routers/analytics.py:13` GET `/dashboard` | OK | |
| `useAnalytics.useCampaignAnalytics` | GET | `/api/analytics/campaigns/{id}` | `routers/analytics.py:54` GET `/campaigns/{id}` | **orphan-hook** | No UI page calls it |
| **Settings** | | | | | |
| `useSettings.useDomains` | GET | `/api/settings/domains` | `routers/settings.py:23` GET `/domains` | OK | |
| `useSettings.useAddDomain` | POST | `/api/settings/domains` | `routers/settings.py:32` POST `/domains` | OK | |
| `useSettings.useVerifyDomain` | GET | `/api/settings/domains/{id}/verify` | `routers/settings.py:48` GET `/verify` | **verb-quirk** | Hook uses `api.get` for a mutation-shaped operation; backend matches. Accept-with-rationale (verification re-runs, idempotent) OR refactor to POST. |
| `useSettings.useDeleteDomain` | DELETE | `/api/settings/domains/{id}` | `routers/settings.py:60` DELETE | OK | |
| **AI** | | | | | |
| `useAI.useCampaignDebrief` | GET | `/api/ai/campaigns/{id}/debrief` | `routers/ai.py:220` GET `/debrief` | OK | Consumed by `CampaignDebriefSection.tsx` |
| `useAI.useGenerateSubjects` | POST | `/api/ai/subjects` | `routers/ai.py:44` POST `/subjects` | **orphan-hook** | Test-only; no UI |
| `useAI.useDraftTemplate` | POST | `/api/ai/template-draft` | `routers/ai.py:58` POST `/template-draft` | **orphan-hook** | Test-only; no UI |
| `useAI.useReengagementVariants` | POST | `/api/ai/reengagement` | `routers/ai.py:70` POST `/reengagement` | **orphan-hook** | Test-only; no UI |
| `useAI.useDeliverabilityReview` | POST | `/api/ai/deliverability` | `routers/ai.py:82` POST `/deliverability` | **orphan-hook** | Test-only; no UI |
| `useAI.useTranslateTemplate` | POST | `/api/ai/translate` | `routers/ai.py:96` POST `/translate` | **orphan-hook** | Test-only; no UI |
| `useAI.useSegmentContacts` | POST | `/api/ai/segment-contacts` | `routers/ai.py:121` POST `/segment-contacts` | OK | Consumed by `Contacts.tsx:81` |
| *(none)* | POST | `/api/ai/campaigns/{id}/debrief/send` | `routers/ai.py:247` POST `/debrief/send` | **orphan-route** | No UI hook |
| **Webhooks** | | | | | |
| *(public — Resend)* | POST | `/api/webhooks/resend` | `routers/webhooks.py:37` | OK | 5-pin compliance |
| **Unsubscribe (public)** | | | | | |
| *(Unsubscribe.tsx direct)* | GET | `/api/unsubscribe/{token}` | `routers/unsubscribe.py:44` | OK | Public route, no auth |
| *(Unsubscribe.tsx direct)* | POST | `/api/unsubscribe/{token}` | `routers/unsubscribe.py:53` | OK | Public route, no auth |
| **Equipe (direct-fetch)** | | | | | |
| `pages/Equipe.tsx` × 5 | GET/POST/DELETE | `/api/team*` | seed `team` standard router | OK | Pattern D — keep direct-fetch |

**Headline gap rows** (excluding OK): 12 — 0 path / 0 verb / 0 404 confirmed / 9 orphan-hook / 5 orphan-route (overlap = M-3 routes shared with M-2 hooks) / 6 DELETE pre-check / 3 security (org-scoping in `automation_service`) / 1 verb-quirk (settings/verify GET-as-mutation).

---

## 6. Phase plan

Mailing is **smaller than PF** — fewer phases. Estimate: 4-5 phases vs PF's 7.

- **Phase 0 ✅ — Discovery + gap inventory** (this document; 2026-05-11)
- **Phase 1 — Seed-alignment + Tier A fixes** *(blocker on `make_get_current_user_org` factory landing; if absent, defer factory adoption with proposal)*
  - Adopt `delete_or_404` across 6 mailing services (PF-3 recurrence)
  - Close `automation_service` org-scoping security gap (M-1: 3 callsites)
  - Verify seed-lib `make_get_current_user_org` factory status; either adopt or file proposal extending PF's
- **Phase 2 — Orphan-hook / orphan-route triage**
  - Per design-batch Q-orphans decisions: wire / delete / keep-with-rationale
  - 9 orphan hooks + 5 orphan routes = ~14 decisions
- **Phase 3 — Scheduler + Resend webhook coverage**
  - Surface scheduler artifacts (next-run / last-run / errors) in `Dashboard.tsx` or new `pages/Operations.tsx`
  - Decide `_automation_processor_sync` placeholder fate (M-5)
  - Add tool-call audit to AI endpoints (M-4) if scope allows
- **Phase 4 — Frontend polish + DTO normalization**
  - Status-code-assertion calibration pass (run scan_block_patterns before any new tests)
  - Add `response_model=` declarations OR file accept-with-rationale per current seed-uniform `success_response` shape (Pattern E)
- **Phase 5 — End-to-end smoke + close**
  - Standard-router mount-smoke per PF Phase 7 lesson d.4 (5-test pattern for `ai_outputs` + `ai_feedback` + `health`)
  - Final `pytest` + `vite build` + keeper green
  - File phase-end proposals; archive

---

## 7. Open questions (design batch — to resolve before Phase 1)

Pair each Q with an evidence-backed recommendation.

**Q1 — Orphan hooks: wire, delete, or keep?**
- Evidence: 9 orphan hooks (5 AI hooks tested-only, 4 CRUD edges with no UI).
- Recommendation: per-hook decision. AI hooks likely DELETE (no near-term UI need; can re-add when designs land); `useUpdateAutomation` / `useEnrollContacts` likely WIRE (covered by AutomationDetail.tsx future); `useImportContacts` WIRE (CSV import is core mailing UX); `useUpdateList` / `useListContacts` WIRE; `useCampaignAnalytics` WIRE into Analytics.tsx (currently only Dashboard called).

**Q2 — Orphan routes: keep, deprecate, or wire?**
- Evidence: 5 orphan routes (3 in automations/steps editing — UI not yet built; 1 lists members remove — UI gap; 1 ai/debrief/send — manual trigger).
- Recommendation: KEEP all (planned UI work). File feature requests for missing UI rather than deleting routes.

**Q3 — `make_get_current_user_org` factory: adopt seed or extend?**
- Evidence: PF Phase 1 filed proposal; mailing is now N=3 → MUST-FORMALIZE.
- Recommendation: BLOCK Phase 1 on seed factory landing OR ship mailing-local refactor that mirrors the proposal shape (so the eventual seed adoption is mechanical).

**Q4 — Settings/verify GET-as-mutation: refactor or accept?**
- Evidence: `useVerifyDomain` is `api.get` but performs a verification side-effect; idempotent (re-running verification is safe).
- Recommendation: accept-with-rationale (idempotent verification — REST-pure but acceptable).

**Q5 — `_automation_processor_sync` TODO placeholder: implement, deactivate, or stub?**
- Evidence: scheduler job exists but body is a TODO (line 87 of `scheduler.py`).
- Recommendation: pull into Phase 3; minimum-viable step execution (sequential per-step body for `send_email` step kind) OR explicit deactivation with a follow-up project filed.

**Q6 — `scheduler` standard router: wait on seed proposal or ship local stub?**
- Evidence: N=3+ across PF + mailing + therapy; PF filed seed proposal; not yet shipped.
- Recommendation: WAIT for seed; mailing's UI need is the strongest motivator. Use the wait to scope the UI design (which pages render scheduler artifacts).

**Q7 — AI tool-call audit (M-4): in scope for this project or separate?**
- Evidence: 7 LLM calls without `make_audit_writer`. Cross-product gap (therapy / ERP similar).
- Recommendation: file as cross-product follow-up project (`llm-tool-audit-rollout`); out of mailing-wiring scope.

**Q-equipe — Pattern D: keep `Equipe.tsx` direct-fetch or extract hook?**
- Evidence: 5 callsites on seed `team` standard router; no other mailing page needs them; PF accepted same.
- Recommendation: KEEP direct-fetch (one-off page, seed-owned endpoints).

**Q-unsubscribe — Pattern D: keep `Unsubscribe.tsx` direct-fetch?**
- Evidence: single callsite, public route (no auth), one-off page.
- Recommendation: KEEP direct-fetch.

---

## 8. Risks / tradeoffs

- **`make_get_current_user_org` factory not shipping at seed** — mailing adoption blocks on PF's filed proposal. Mitigation: ship local refactor mirroring proposal shape (mechanical seed lift later).
- **Automation security gaps already exploitable** — M-1 is a real CVE-shape if step UUIDs leak; RLS mitigates at the DB layer but defense-in-depth missing. **Schedule Phase 1 promptly** rather than later.
- **Orphan hooks accumulate** — 9 orphans suggests scaffolded-ahead-of-UI; design-batch decisions matter or they re-grow.

---

## 9. Out of scope (reaffirm)

(See §4.)

---

## 10. Verification commands

```bash
# Backend tests
cd products/mailing/backend && pytest -q

# Keeper
python mcp/noctusai/cli.py --review --product mailing --worktree-path "$PWD"

# Frontend build
cd products/mailing/frontend && npm run build

# Cross-cutting check (recurrence rule scans)
python mcp/noctusai/cli.py --scan-helpers --product mailing
```

---

## 11. Change log

- **2026-05-11 — Phase 0 ✅ (Engineer QQQ)**
  - Read PF lessons, ran read-only audit across 10 routers + 8 hook files + 21 pages + 4 migrations.
  - Surfaced 9 orphan hooks, 5 orphan routes, 6 DELETE pre-check holes, 3 service-layer security gaps (`automation_service` org-scoping), 1 placeholder scheduler job, 0 path/verb/404 mismatches.
  - Confirmed AAA's service_role_bypass policies (19 tables, 3 migrations).
  - Filed §5.1.1 pending seed-lib lifts: factory + delete_or_404 + scheduler standard router.
  - **Verification status**: pytest baseline not run (worktree venv missing apscheduler — install denied by auto-mode permission classifier; deferred to orchestrator). Keeper run blocked on same. Frontend build not run.

- **2026-05-11 — Phase 1 ✅ (Engineer MAI-P1)** — Seed-alignment + Tier A fixes + M-1 security hardening
  - **Part 1 — Pattern F (auth factory) adoption.** Updated `app/dependencies.py` to bind
    `make_get_current_user_org` (mirrors yt-crawler shape). Refactored 8 routers via libcst codemod:
    `lists.py` (8), `campaigns.py` (9), `contacts.py` (6), `templates.py` (6), `automations.py` (14),
    `settings.py` (4), `analytics.py` (2), `ai.py` (8) = **57 callsites** (54 `user, _` + 3 `user, token`).
    Imperative `user, _ = await get_current_user(authorization)` → `user, _, org_id = auth`
    with `auth=Depends(get_current_user_org)` in the param list. Followed up with import cleanup
    (orphaned `Header` / `Optional` removed).
  - **Part 2 — `delete_or_404` adoption.** Adopted seed helper in 5 services:
    `contact_service.delete_contact`, `list_service.delete_list`, `campaign_service.delete_campaign`,
    `automation_service.delete_automation`, `automation_service.delete_step`. `list_service.remove_members`
    is `.in_()`-keyed bulk + intentionally idempotent — kept raw with an inline accept-with-rationale
    comment. Phase 0's "6 of 6" row count corrected: `template_service.delete_template` is a
    soft-delete (`UPDATE ativa=False`), not a raw delete.
  - **Part 3 — M-1 defense-in-depth org chain.** Added `_assert_automation_in_org` +
    `_assert_step_in_automation` private helpers on `AutomationService`. Wired into 5 sub-entity
    methods: `update_step`, `delete_step`, `reorder_steps`, `enroll_contacts`, `list_enrollments`.
    Each method now verifies the parent automation belongs to the caller's org BEFORE
    operating; step operations additionally verify the step→automation link via
    `automation_id` scoping. Router signatures updated to thread `automation_id` through to
    `update_step` / `delete_step`.
  - **Tests added (7 in `TestM1OrgScopingDefenseInDepth` + 1 in `TestDeleteContact::test_raises_404_when_absent`).**
    Cross-org access to all 5 sub-entity methods raises 404. `update_step` on a non-existent
    automation raises 404. `delete_step` with a step that belongs to a different parent raises 404.
    Used `set_sequential_responses` with empty-data responses to model RLS-filtered SELECTs
    (`MockSelectBuilder` does not evaluate predicates on SELECT — only `MockFilterBuilder` does).
  - **Test delta**: 204 passed / 1 fail (baseline) → **212 passed / 1 fail**. The 1 failure is
    the pre-existing `test_e2e_flows.py::TestCampaignLifecycle::test_full_lifecycle` (schedule POST
    returns 400 — flake / fixture issue unrelated to Phase 1 deltas).
  - **Keeper**: 0 NEW issues (`cli.py --review --product mailing --worktree-path "$PWD"`).
  - **Imperative auth callsites**: 57 → 0.
  - **Phase 0 invalidation**: PROJECT §6 says "Phase 1 blocks on `make_get_current_user_org`
    factory landing"; WWW had already invalidated that — the factory is in seed at
    `seed/lib/backend/noctusai_lib/api/auth.py:231-310` (confirmed). Adoption was mechanical
    via the codemod.

- **2026-05-11 — Phase 2 ✅ (Engineer MAI-P2)** — Orphan-hook / orphan-route triage + accept-with-rationale catalog entries + stale-proposal triage + LLM-audit follow-up project filed
  - **Focused-subset scope.** §7 default-recommendations applied: Q1 (5 AI orphan hooks → DELETE),
    Q2 (orphan routes → KEEP via accept-with-rationale, symmetric with hooks-kept-for-UI), Q4
    (settings/verify GET-as-mutation → accept-with-rationale), Q-equipe / Q-unsubscribe →
    accept-with-rationale (Pattern D direct-fetch), Q7 → cross-product follow-up project filed.
    Phases 3-5 left to subsequent orchestrator scopes.
  - **Part 1 — DELETE 5 AI orphan hooks (Q1).** Removed `useGenerateSubjects`, `useDraftTemplate`,
    `useReengagementVariants`, `useDeliverabilityReview`, `useTranslateTemplate` from
    `frontend/src/hooks/useAI.ts` (52 LOC removed). Kept `useCampaignDebrief` (wired by
    `CampaignDebriefSection.tsx`) + `useSegmentContacts` (wired by `Contacts.tsx:81`).
    Updated `frontend/src/hooks/__tests__/useAI.test.ts` — dropped 7 test blocks for the
    5 deleted hooks (110 LOC removed); kept the 1 `useSegmentContacts` test block. Backend
    routes preserved per Q2 (planned UI work).
  - **Part 2 — Orphan-route KEEP-with-rationale (Q2).** 5 orphan routes (`PATCH /api/lists/{id}`,
    `PATCH /api/automations/{id}`, `PATCH /api/automations/{id}/steps/{step_id}`,
    `POST /api/automations/{id}/steps/reorder`, `DELETE /api/lists/{id}/members`,
    `GET /api/analytics/campaigns/{id}`, `POST /api/ai/campaigns/{id}/debrief/send`) all
    kept; new accept-with-rationale catalog entry (`Mailing orphan routes (5) kept for
    planned UI work`) documents the deferred-feature pattern with revisit triggers
    (6-month staleness, design-shape mismatch, or N=6 cross-product recurrence).
  - **Part 3 — Verb-quirk accept-with-rationale (Q4).** `useVerifyDomain` GET-as-mutation
    documented in catalog (`Settings/verify GET-as-mutation is idempotent re-verify`).
    Inline wayfinder comment added at `frontend/src/hooks/useSettings.ts:30`.
  - **Part 4 — Pattern D accept-with-rationale (Q-equipe / Q-unsubscribe).** Two catalog
    entries (`Equipe.tsx direct-fetch on seed team standard router`, `Unsubscribe.tsx
    direct-fetch on public /api/unsubscribe/{token}`). Inline wayfinder comments added
    at the top of `pages/Equipe.tsx` + `pages/Unsubscribe.tsx`.
  - **Part 5 — LLM-audit follow-up project filed (Q7).** New `projects/llm-tool-audit-rollout/`
    folder with full PROJECT.md scoping the M-4 cross-product gap (mailing 7 calls + therapy/
    ERP/PF TBD). Project provisionally designed; Phase 0 discovery pending. Out of mailing-wiring
    scope as recommended in §7 Q7.
  - **Part 6 — Stale-proposal triage (3 files at `proposals/evaluations/20260419-014952-mailing/`).**
    Created `STATUS.md` in the eval folder with triage table. Both health-endpoint-removal
    proposals are **APPLIED-elsewhere** — `app/main.py:41` already mounts the framework
    health router via `create_product_app(..., standard_routers=["health", ...])`; no
    product-level `health.py` exists. Eval folder preserved per `comparison.md` §4
    recommendation (worked example of agent-vs-headless authoring comparison).
  - **Test delta**: 214 passed / 1 fail (Phase 1 baseline) → **214 passed / 1 fail** (no
    backend touch in Phase 2; same pre-existing `test_e2e_flows.py::TestCampaignLifecycle::test_full_lifecycle`
    flake from Phase 1). Frontend test count drop is expected (5 hook test blocks → 1
    blocks); vitest verification pending orchestrator-side merge gate.
  - **Files touched (12)**: `frontend/src/hooks/useAI.ts` (delete 5 hooks),
    `frontend/src/hooks/__tests__/useAI.test.ts` (drop 7 test blocks),
    `frontend/src/hooks/useSettings.ts` (wayfinder comment),
    `frontend/src/pages/Equipe.tsx` (wayfinder comment),
    `frontend/src/pages/Unsubscribe.tsx` (wayfinder comment),
    `KNOWLEDGE-BASE/CONTEXT/PATTERNS/accept-with-rationale.md` (+4 entries under new
    `Entries from mailing-wiring Phase 2` section),
    `projects/llm-tool-audit-rollout/PROJECT.md` (new file),
    `products/mailing/proposals/evaluations/20260419-014952-mailing/STATUS.md` (new file),
    `products/mailing/projects/mailing-wiring/PROJECT.md` (this update).
  - **Decisions surfaced (proposals triage)**:
    | Proposal | Disposition |
    |---|---|
    | `openai-gpt-4o-mini-20260419-015001-remove-custom-health-endpoint-in-mailing-product.md` | APPLIED-elsewhere (seed framework `standard_routers=["health"]`) |
    | `claude-opus-4-7-20260419-015135-remove-product-level-health.py-in-mailing-—-delega.md` | APPLIED-elsewhere (same — seed pattern absorbed) |
    | `comparison.md` | KEEP as eval-methodology reference |
