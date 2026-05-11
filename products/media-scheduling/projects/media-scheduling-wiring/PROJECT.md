# Media Scheduling Wiring — Project Document

> **This is a living document, not a rigid checklist.**
> As we build and learn, this project document evolves. See
> `CLAUDE.md → Universal rules → Projects are living + planners interrogate first`.
>
> **Slug rationale (honest-scope check):** Mirrors the closed `personal-finance-wiring`
> (`archive/projects/2026-05-11/16-personal-finance-wiring/`) and in-flight
> `erp-wiring` / `therapy-platform-wiring` / `mailing-wiring` / `daily-life-wiring`.
> Same shape: close every scaffolding gap end-to-end across `media-scheduling`
> — admin (appointments, authorized_users, condominiums, oauth status), webhook,
> landing at green build + green pytest + 0 keeper issues. Pure *wiring*, not
> redesign or feature growth. Smallest product in the rollout (4 admin routes).

- **Created:** 2026-05-11
- **Last updated:** 2026-05-11 (Phase 0 ✅)
- **Status:** ⏳ **Phase 0 ✅ — awaiting "continue" before Phase 1.** Discovery
  pass complete; §5.4 populated; §6 phases derived from concrete gap data;
  §7 design batch surfaced. Per the project's pause-after-each-phase cadence,
  awaiting user signal before Phase 1 dispatch.
- **Owner / stakeholders:** Raphael (joaoraphaelsst@gmail.com) · Claude Opus 4.7
- **Related docs:**
  - `CLAUDE.md § Universal rules` — behavioral rules, loaded every session
  - `KNOWLEDGE-BASE/02-LANDSCAPE.md` — product surface inventory
  - `KNOWLEDGE-BASE/PATTERNS/project-execution.md` — cadence, naming, tests-with-code
  - `KNOWLEDGE-BASE/PATTERNS/proposals-and-improvements.md` — phase-end protocol
  - `KNOWLEDGE-BASE/PATTERNS/whatsapp-chatbot-seed.md` — chatbot framework media-scheduling consumes
  - `KNOWLEDGE-BASE/PATTERNS/scheduling-seed.md` — scheduling primitive
  - `KNOWLEDGE-BASE/PATTERNS/webhook-signatures.md` — 5-pin compliance contract
  - `archive/projects/2026-05-11/16-personal-finance-wiring/personal-finance-wiring-lessons.md` — PF retro inherited
  - `products/erp-imobiliario/projects/erp-wiring/PROJECT.md` — sibling in-flight, same shape
  - `products/media-scheduling/MASTER-PROMPT.md` — agent-facing product contract
- **Project slug:** `media-scheduling-wiring`

---

## 1. Context & Purpose

`media-scheduling` is the **smallest product in the rollout** — 4 admin routers + 1 webhook router (5 total product routers) + 3 standard routers (`health`, `notificacoes`, `team`) inherited via `create_product_app(...)`. It runs alongside `erp-wiring`, `therapy-platform-wiring`, `mailing-wiring`, `daily-life-wiring` as part of the master products-wiring rollout (PF closed 2026-05-11). The PF lessons retro recommends:

> **Phase 0 as the load-bearing phase.** A near-clean gap inventory lets the rest of the project execute almost entirely against §5.4 rows rather than re-discovery.

This project executes that recipe. Phase 0 (this document's first deliverable) produced a complete inventory: every router prefix + endpoint count, every hook + API call, every gap classified by the 7 Pattern shapes (A-G) inherited from therapy §5.4.2, every migration column cross-referenced against router-layer table-calls, plus PF lessons §b.2 Pattern H orphaned-hook column.

**media-scheduling already consumes a deep seed-lib slice** (chatbot, redis, whatsapp, webhook_signatures, scheduling, google_calendar, google_maps, tool_audit) — Phase 0's seed audit confirms 8 source files importing from `noctusai_lib` / `noctusai_seed`. The wiring project is therefore mostly *verify the consumed shapes still apply* + *close the Pattern F (auth-factory) and Pattern E (response_model) recurrences* — not large-scale absorption.

The win looks like: `vite build` clean, `pytest tests/` green (baseline 87 already green), every admin page loads with a 200 (Dashboard, Appointments, AuthorizedUsers, OAuth status, Equipe), and the Pattern F / Pattern H residue is closed.

---

## 2. Confirmed constraints

Mirrors PF + ERP + therapy §2:

- **Scope** — full product wiring sweep across admin routes + webhook + standard-router smokes + DTO sanity. Frontend pages → backend endpoints → migration columns must align end-to-end.
- **EN routes stay EN** — media-scheduling was scaffolded EN-only (`/api/appointments`, `/api/authorized-users`, `/api/condominiums`, `/api/oauth/google/*`). **Pattern A in §5.4.2 is therefore 0** — verified during Phase 0.
- **Tests** — always, per the three-layer discipline in `KB § PATTERNS/testing.md`.
- **Cadence** — phase-by-phase, pause after each, no auto-advance.
- **Seed sync** — patterns worth promoting mid-project land as phase-end proposals via `noctus.dev.file_proposal(project="media-scheduling-wiring", worktree_path="$PWD", …)`.
- **Verify-the-seed-ships-it test fires at every absorption decision** — PF Phase 1 lesson.
- **PF lessons retro is non-binding pre-reading** — every Phase 1+ engineer brief MUST link to it.

---

## 3. Design principles

How we're approaching *this specific problem* on top of platform-wide `CLAUDE.md` rules.

1. **Fix at the layer of the cause.** N=2 patterns inside media-scheduling get triaged at decision time; N=3+ across products (Pattern E, Pattern F) trigger seed-lib formalization.
2. **No band-aids.** No `?? ''` guards to tolerate bad DTOs; backend boundary is the source of truth.
3. **LGPD-first on every personal-data endpoint.** `authorized_users` touches phone numbers + names; webhook payloads carry conversation content. Every aggregation in a new shape gets a `noctus.dev.lgpd_flag` call.
4. **Migrations and applied SQL stay in lockstep.** Every DDL we apply via `mcp__claude_ai_Supabase__apply_migration` lives first as `products/media-scheduling/backend/migrations/NNN_<name>.sql`. Next free slot at Phase 0 close: **007**.
5. **Tests land in the same phase as the code.** Three-layer discipline, no exceptions. **Gap surfaced:** 4 of 5 product routers lack router-level tests at Phase 0 baseline.
6. **Discovery is an artifact, not a vibe.** Phase 0 produces a checked-in gap table in §5.4. Phases 2+ reference rows in that table.
7. **Status-code-assertion rule (PF retro §b.3) calibrated in Phase 0, not enforced reactively.** Surfaced as Wave 0 sub-task.

---

## 3a. Seed-first analysis (REQUIRED — the seed is every product's skeleton)

Six-question checklist per `KB § GUIDES/seed-first-design.md`:

1. **Is the contract identical for every product?** **MIXED.** Cross-cutting contracts (auth, response envelopes, request-id middleware, notifications, AI plumbing, scheduling primitive, chatbot framework, webhook signatures, google_calendar / google_maps adapters) are uniform → seed. Business-domain contracts (appointments / authorized_users / condominiums / oauth-status) are media-scheduling-specific → product.
2. **Is the data source product-specific?** **YES** for business tables (`appointments`, `authorized_users`, `condominiums`, `properties`, `service_types`, `crew_skills`, `route_groups`, `appointment_requests`, `oauth_credentials`, `conversation_summaries`, `pending_chat_identities`, `tool_call_audits`); **NO** for cross-product tables (`team_*`, `notifications` — seed-mounted).
3. **Is the placement product-specific?** **YES** for product pages (Appointments, AuthorizedUsers, OAuthStatus, Dashboard); **NO** for inherited (Equipe is byte-identical to `products/seed/frontend/src/pages/Equipe.tsx` — verified Phase 0).
4. **Is the visibility / permission rule the same?** **YES** — single-tenant admin (all authenticated SSO users have full admin access; no role split). Different from ERP (4 tiers) and therapy (clinic/clinic-admin/clinician).
5. **Does the seam already exist in seed?** **MOSTLY YES.** Audited at Phase 0 close — see §5.4.6.
6. **Default-on or opt-in?** media-scheduling's seed consumption is **default-on** via `create_product_app(standard_routers=["health", "notificacoes", "team"], lifespan_startup=worker_lifecycle, …)` at `app/main.py:37`. No opt-out flags.

**Litmus — per-product code count this design requires:**

- [x] **0 lines** for cross-product concerns (Pattern E + Pattern F formalizations land at seed; consumer-side fork count target is **0**).
- [x] **A small section** for product-specific wiring (appointments / authorized_users / condominiums / oauth — media-scheduling-bound, not seedable).
- [ ] **Multiple files / pages / mounts per product** — none planned. If a Phase surfaces this shape, STOP and re-design.

**Phase plan implications:** §6 phases work in-product (media-scheduling-domain wiring) **plus** mirror cross-product seed-side absorption decisions (Phase 1 verifies whether `make_get_current_user_org` shipped + adopts or defers). No "walk through products" framing — single-product wiring sweep.

---

## 4. Scope

**In scope:**

- Every `media-scheduling` backend endpoint that a frontend hook calls. Phase 0 inventory in §5.4 captures all 5 routers / 13 product endpoints / 3 hook files (8 named exports) / 11 pages.
- Every migration needed to close column drift (§5.4.5 — see findings, minor wire-shape only).
- Seed-side absorption decisions whose N=2+ baseline includes media-scheduling.
- Frontend corrections to consume corrected DTOs or fix UI bugs uncovered during sweep.
- Tests (unit + router + integration) landing in same phase as code — especially **closing the 4-router test coverage gap** (only oauth_credentials + webhooks have router tests today).
- LGPD awareness via `noctus.dev.lgpd_flag` where endpoints aggregate PII in new shapes.
- End-to-end verification: `vite build` + `pytest` + manual browser QA.

**Out of scope (for now — with reason):**

- **Other products** — separate parallel wiring projects (PF closed, ERP / therapy / mailing / daily-life in flight).
- **UX redesigns** — wiring project, not redesign.
- **New features** — no capability we aren't already carrying as scaffolded UI.
- **Google Calendar deep wiring** — `calendar_writer.py` service exists; deep two-way sync is a future project.
- **WAHA chatbot prompt tuning** — wire the existing surface; prompt engineering is a future project.
- **Real WAHA send loop with real Redis** — worker registers but no-ops without `REDIS_URL`; full ops-online testing is a deploy-drill follow-up, not this project.
- **Multi-tenant role tiers** — single-admin design is intentional.

---

## 5. Architecture / Data Model

*§5.1-5.3 are placeholders until seed-absorption decisions land in Phase 1. §5.4 is the Phase 0 deliverable, populated below.*

### 5.1 Shared `make_get_current_user_org` adoption *(delivered by Phase 1)*

PF retro §e row 1: PF + ERP + therapy + mailing + daily-life + **media-scheduling** = **N=6 confirmed** today. PF filed `make-get-current-user-org-factory` follow-up project. media-scheduling Phase 1 either:
- (a) Adopts the seed-side factory IF it ships before media-scheduling Phase 1 starts.
- (b) Defers — surfaces the gap to `accept-with-rationale.md` for media-scheduling, files a re-confirmation in the master rollout.

### 5.2 Pattern E (response_model) consolidation *(deferred — accept-with-rationale platform-wide)*

All 5 media-scheduling routers return `dict[str, Any]`. Same as PF / ERP / therapy / mailing / daily-life. **N=6 confirmed** across the platform. Default rec: accept-with-rationale at platform level; defer to a cross-product follow-up project (`platform-dto-contract` — to be filed).

### 5.3 Wire-shape translation helpers *(internal-uniform — KEEP)*

`appointments.py::_wire()` (3 lines) translates `start_at↔starts_at` / `end_at↔ends_at`. `authorized_users.py::_wire()` + `_persistable()` (~15 LoC each) translate `active↔is_active`. **N=2 within media-scheduling.** Triage time per the recurrence rule:
- Default rec: **KEEP inline** — helpers are small, product-local, and each handles a different field. Seed-side `wire_helper` would over-generalize. Re-evaluate at N=3.

### 5.4 Inventory *(populated 2026-05-11 by Phase 0)*

#### 5.4.1 Headline counts

| Surface | Count |
|---|---|
| Backend routers (product) | **5** (`appointments`, `authorized_users`, `condominiums`, `oauth`, `webhooks`) |
| Backend routers (standard via seed) | **3** (`health`, `notificacoes`, `team` mounted by `create_product_app`) |
| Backend endpoints (product) | **13** (`appointments`: 2; `authorized_users`: 5; `condominiums`: 1; `oauth`: 4 across public+admin; `webhooks`: 1) |
| Backend migrations | **6** (`001_seed.sql` → `006_invitations_accepted_columns.sql`; next free slot = **007**) |
| Frontend hook files | **3** (`useAppointments.ts`, `useAuthorizedUsers.ts`, `useOAuthStatus.ts`) |
| Named hook exports | **8** (useAppointments + useAppointment + useCondominiumOptions; useAuthorizedUsers + useAuthorizedUser + useCreate/Update/DeleteAuthorizedUser; useOAuthStatus + redirectToOAuthInit helper) |
| Frontend pages | **11** (Dashboard, AppointmentsPage, AuthorizedUsersPage, OAuthStatusPage, Equipe, Landing, Login, AcceptInvite, ForgotPassword, NotFound + App.tsx wiring) |
| Frontend pages with **direct** `useQuery`/`useMutation` (Pattern D) | **0** product-side; **1** `Equipe.tsx` (byte-identical to seed → carve-out) |
| Raw `fetch()` outside auth/api wrappers | **0** product-side |
| Unique frontend → backend API paths | **5** (`/api/appointments`, `/api/authorized-users`, `/api/condominiums`, `/api/oauth/google/status`, `/oauth/google/init`) |
| Backend routers with `response_model` declared | **0 / 5** — all 13 routes return `dict[str, Any]` (same shape as PF/ERP/therapy/mailing/daily-life) |
| Pytest baseline | **87 collected, 87 passed, 0 failed, 1 PendingDeprecationWarning (unrelated)** — green |
| Keeper review | **0 issues, 0 proposals** — clean bill |

#### 5.4.2 Systemic findings *(7 Pattern shapes A-G + PF lessons §b.2 Pattern H)*

**Pattern A — Portuguese ↔ English path mismatches: 0 occurrences.**

media-scheduling was scaffolded EN-only. Backend exposes 5 prefixes (`/api/appointments`, `/api/authorized-users`, `/api/condominiums`, `/api/oauth/google` admin + `/oauth/google` public, `/webhooks` for WAHA) + standard-router prefixes (`/api/team`, `/api/notificacoes`, `/api/health`). Hooks call exactly the matching EN path. **No PT-stray paths** — verified via `grep -rE "/api/(agendamentos|usuarios|condominios)" frontend/src/hooks/` returning empty.

**Pattern B — Admin namespace not split: N/A.**

media-scheduling is single-tenant single-admin — no `/api/admin/*` split needed. All authenticated SSO users have full admin access; no role tiers below admin. (Differs from ERP's 4-tier + therapy's clinic/clinician.)

**Pattern C — Detail endpoints missing: 0 surfaced.**

Cross-checked all 2 detail-path patterns in hooks (`/api/appointments/{id}`, `/api/authorized-users/{id}`) against router definitions. **Every frontend detail call has a matching router decorator.**
- `useAppointment(id)` → `appointments.py:88` `@router.get("/{appointment_id}")` ✅
- `useAuthorizedUser(id)` → `authorized_users.py:114` `@router.get("/{user_id}")` ✅

**Pattern D — Direct-fetch / Pattern-D bypass in pages: 0 in product code.**

Verified via `grep -n "fetch\|api\.\(get\|post\|patch\|delete\|put\)" pages/*.tsx`:
- `AppointmentsPage.tsx` — uses `useAppointments` / `useCondominiumOptions` only.
- `AuthorizedUsersPage.tsx` — uses `useAuthorizedUsers` + 4 mutation hooks only.
- `OAuthStatusPage.tsx` — uses `useOAuthStatus` + `refetch()` (tanstack-query method).
- `Dashboard.tsx` — static status page, no data fetching.
- `Equipe.tsx` — **byte-identical to `products/seed/frontend/src/pages/Equipe.tsx`** (verified `diff -q`); uses `api.get/post/delete` directly on `/api/team*` per seed's Equipe convention. This is the **seed-managed shape** (other products have drifted; media-scheduling has not). **Triage: NO ACTION** — seed-conformant.
- `AcceptInvite.tsx` — uses `acceptEndpoint="/api/team/accept"` prop (seed component).

**Pattern E — Implicit DTO contract: systemic (0 / 5 routers declare `response_model`).**

Same shape as PF / ERP / therapy / mailing / daily-life. All 13 routes return `dict[str, Any]` (mostly `{"data": [...]}` or wire-shape rows). Frontend types in `useAppointments.ts:18-33`, `useAuthorizedUsers.ts:13-21`, `useOAuthStatus.ts:14-22` carry the de-facto contract. **N=6 platform-wide confirmed.** Default recommendation in §7 design batch: defer to cross-product follow-up project `platform-dto-contract`; accept-with-rationale for this project.

**Sub-shape — ghost fields in frontend `Appointment` type:** `property_label`, `condominium_label`, `service_type_label`, `crew_assignee_id`, `crew_assignee_label`, `service_type_id` declared but backend `list_appointments` does `select("*")` on `appointments` table → none populated. Frontend renders `undefined` via `?.` access. **Surface as §7 Q-WIRE.**

**Pattern F — Legacy `Header(authorization) + await get_current_user(authorization)` shape: 6 occurrences (all 6 admin/webhook auth-gated routes).**

Every authenticated route uses the legacy positional-args shape:
- `appointments.py:50` + `:91` (list + detail)
- `authorized_users.py:79` + `:96` + `:117` + `:138` + `:164` (list/create/get/update/delete)
- `condominiums.py:27` (list)
- `oauth.py:238` (admin status; init endpoints are public by design)

**No `Depends(get_current_user_org)` factory shape anywhere** — this is the same gap PF/ERP/therapy/mailing/daily-life surfaced. **N=6 confirmed platform-wide.** PF filed `make-get-current-user-org-factory` follow-up; media-scheduling Phase 1 verifies + adopts or defers per `accept-with-rationale.md`.

**Pattern G — Path-shape mismatches inside clusters: 0 noted.**

5 routers, each owns a single resource cluster. No nested/flat mix.

**Pattern H — Orphaned hooks (no page/component consumer) — PF lessons §b.2 addition.**

Walked every hook export via `grep -rE "\\b<hook>\\b" pages/ components/`:

| Hook export | Consumer count | Triage |
|---|---|---|
| `useAppointments` | 1 (AppointmentsPage.tsx) | NOT orphan |
| `useAppointment(id)` | 0 page consumers; backend `GET /api/appointments/{id}` exists | **ORPHAN export** — see §7 Q-DETAIL |
| `useCondominiumOptions` | 1 (AppointmentsPage.tsx filter bar) | NOT orphan |
| `useAuthorizedUsers` | 1 (AuthorizedUsersPage.tsx) | NOT orphan |
| `useAuthorizedUser(id)` | 0 page consumers; backend `GET /api/authorized-users/{id}` exists | **ORPHAN export** — same shape as useAppointment(id) |
| `useCreateAuthorizedUser` | 1 (AuthorizedUsersPage.tsx) | NOT orphan |
| `useUpdateAuthorizedUser` | 1 (AuthorizedUsersPage.tsx) | NOT orphan |
| `useDeleteAuthorizedUser` | 1 (AuthorizedUsersPage.tsx) | NOT orphan |
| `useOAuthStatus` | 1 (OAuthStatusPage.tsx) | NOT orphan |
| `redirectToOAuthInit` | 1 (OAuthStatusPage.tsx) | NOT orphan |

**Confirmed orphans:** `useAppointment(id)` + `useAuthorizedUser(id)` — both detail-view hooks with LIVE backend endpoints already wired. Pattern: detail page is planned but not built. **Different shape from ERP Pattern H** (orphan hooks pointing at LIVE backend = future-use scaffolding; ERP had orphan hooks pointing at orphan backend routes = both-side cleanup). Default rec: **KEEP** the hooks (`Appointment` type's rich fields like `crew_assignee_label`, `service_type_label` hint at a planned `AppointmentDetailPage`). Surface as §7 Q-DETAIL.

#### 5.4.3 Per-router endpoint distribution

| Router | Endpoints | Notes |
|---|---|---|
| `authorized_users.py` | 5 | Full CRUD; inline Pydantic schemas; wire-shape `active↔is_active`; phantom `notes` field documented in docstring |
| `oauth.py` | 4 | 2 routers (public init+callback; admin status); single-account flow |
| `appointments.py` | 2 | list + detail; wire-shape `start_at↔starts_at`; ghost-field DTO drift |
| `webhooks.py` | 1 | WAHA inbound; 5-pin webhook compliance via seed helper |
| `condominiums.py` | 1 | read-only catalog; no auth role-gate beyond `get_current_user` |

#### 5.4.4 Backend orphans (no surveyed frontend caller)

None. All 13 product endpoints have a matching hook call OR are part of an OAuth flow consumed by browser redirect (`init` GET, `callback` GET) or webhook surface (`/webhooks/waha`).

#### 5.4.5 Migration column gap

**Cross-checked all 14 tables in `002_initial_schema.sql` against `.table("<name>")` calls in `app/routers/` + `app/services/`.**

| Code-referenced table | In migrations? | Notes |
|---|---|---|
| `appointments` | ✅ `002:215` | **Column wire drift:** DB `start_at`/`end_at` ↔ hook `starts_at`/`ends_at`; backend `_wire()` translates. Documented inline. |
| `authorized_users` | ✅ `002:72` | **Column wire drift:** DB `active` ↔ hook `is_active`; backend `_wire()`/`_persistable()` translates. **Phantom field:** hook declares `notes?: string` but DB has no `notes` column on this table. Documented inline. |
| `condominiums` | ✅ `002:93` | Schema clean |
| `oauth_credentials` | ✅ `002:256` | Schema clean |
| `pending_chat_identities` | ✅ `002:281` | Schema clean (LID-aware webhook) |
| `tool_call_audits` | ✅ `002:304` | Schema clean |
| `conversation_summaries` | ✅ `002:238` | Schema clean |
| `properties`, `service_types`, `crew_skills`, `route_groups`, `appointment_requests`, `appointment_request_services` | ✅ | Phase 1+ wiring tables (services exist; not yet hook-consumed) |

**No hard drift — only the 2 wire-shape aliases above.** Default rec for Phase 6 alignment: **KEEP wire helpers** (3-15 LoC each); revisit if a 3rd alias surfaces. Surface in §7 Q-WIRE.

#### 5.4.6 Should-use-seed candidates *(N=2+ across products including media-scheduling)*

Audited via `grep -rE 'from noctusai_(lib|seed)' app/` — 47 imports across 8 source files in media-scheduling backend.

| Seed module | Imports | Status |
|---|---|---|
| `noctusai_lib.domain.chatbot` | 3 (webhooks, scheduling_tools, conversation_worker) | Adopted |
| `noctusai_lib.integrations.whatsapp` | 2 (webhooks, conversation_worker) | Adopted |
| `noctusai_lib.integrations.redis` | 2 (webhooks, conversation_worker) | Adopted |
| `noctusai_lib.integrations.google_calendar` | 1 (calendar_writer) | Adopted |
| `noctusai_lib.integrations.google_maps` | 1 (routing_lookup) | Adopted |
| `noctusai_lib.security.webhook_signatures` | 1 (webhooks) | Adopted |
| `noctusai_lib.domain.scheduling` | 2 (scheduling_adapters, condominium_travel) | Adopted |
| `noctusai_lib.domain.ai.tool_audit` | 2 (audit_hook, conversation_worker) | Adopted |
| `noctusai_lib.primitives.responses` | 1 (responses.py re-export) | Adopted |
| `noctusai_lib.api.auth` (first_or_none + resolve_sso_role) | 1 (dependencies) | Adopted |
| `noctusai_seed.create_product_app` / `create_dependencies` / `create_database_module` / `create_product_limiter` / `ProductSettings` | 5 (main, dependencies, database, rate_limit, config) | Adopted |

**Absorption candidates whose N=2+ across products includes media-scheduling:**

| Candidate | N count | Action |
|---|---|---|
| `make_get_current_user_org` factory | N=6 (PF, ERP, therapy, mailing, daily-life, media-scheduling) | PF filed `make-get-current-user-org-factory`; media-scheduling Phase 1 verifies seed-ships-it; if shipped, adopt; else defer with destination |
| Pattern E DTO contract (`response_model=`) | N=6 platform-wide | Defer to follow-up `platform-dto-contract`; accept-with-rationale |
| Wire-shape helpers (`_wire`/`_persistable`) | N=2 within media-scheduling alone | KEEP inline (different fields per router); re-evaluate at N=3 |
| Empty `app/schemas/` + inline Pydantic in routers | N=? (not yet audited platform-wide) | Phase 1 — file as follow-up scan |

#### 5.4.7 Deletion-candidate batch *(surfaced at end-of-Phase-0 per PF Q3)*

| Candidate | Rationale | Default recommendation |
|---|---|---|
| `useAppointment(id)` hook export | 0 page consumers; backend route LIVE; rich `Appointment` type fields suggest planned detail page | **KEEP** (false-positive orphan; future-use scaffolding); surface in §7 Q-DETAIL |
| `useAuthorizedUser(id)` hook export | Same shape | **KEEP**; future-use |
| `notes` field on frontend `AuthorizedUser` type | DB column does not exist; backend silently drops | **REMOVE from type** (hook + page; Phase 4 cleanup) |
| Ghost fields on `Appointment` type | Backend `select("*")` doesn't populate `property_label` etc. | **EITHER** populate via joined query (Phase 4 backend) **OR** remove from type (Phase 4 frontend). Surface in §7 Q-WIRE |

All deletion-candidates land as §7 Q-NEW-DEL for user one-sweep approval before Phase 1 kicks off.

#### 5.4.8 Test coverage

- **87 collected, 87 passed, 0 failed, 1 PendingDeprecationWarning** in `products/media-scheduling/backend/` at Phase 0 close (run: `PYTHONPATH=seed/lib/backend:seed/framework/backend python3.11 -m pytest -q`).
- **Coverage gap surfaced:** 4 of 5 product routers lack router-level tests at Phase 0 baseline.
  - `tests/routers/test_oauth_credentials.py` ✅ (covers oauth router)
  - `tests/routers/test_webhooks_router.py` ✅ (covers webhook with 5-pin compliance)
  - `tests/routers/test_health.py` ✅ (standard router)
  - `tests/routers/test_team_router.py` ✅ (standard router)
  - **MISSING:** `test_appointments_router.py`, `test_authorized_users_router.py`, `test_condominiums_router.py`. **Phase 3 sub-task.**
- **PF Phase 7 lesson §d.4 — standard-router smoke per product:** main.py mounts `standard_routers=["health", "notificacoes", "team"]`. `test_health.py` + `test_team_router.py` exist; **`test_notificacoes_router.py` missing** — Phase 7 sub-task.
- **PF Phase 0 lesson §b.3 — status-code-assertion calibration:** run `noctus.dev.scan_block_patterns mode=status_assertion` over media-scheduling test corpus in Phase 0; produce inventory; either fix in Phase 0 OR pin as baseline-no-regress. **Action item filed for Phase 1 Wave 0.**

#### 5.4.9 Keeper review pass

```
python mcp/noctusai/cli.py --review --product media-scheduling --worktree-path "$PWD"
```

Run 2026-05-11 — **0 issues, 0 proposals filed.** Result: clean keeper bill of health on `media-scheduling`. The gap table in §5.4.2-§5.4.7 is the agent-authored signal for this project.

---

## 6. Implementation phases

Phases are **suggestive, not strict.** Reorder, split, merge, or discover new phases as work progresses.

**Phase status-icon convention** (per `KB § PATTERNS/project-execution.md §1`):

| Icon | Meaning |
|---|---|
| _(none)_ | Pending — not started |
| ⏳ | In progress / partially done |
| ✅ | Complete — every sub-task ticked |
| ❌ | Blocked or failed — see Change Log |

**Improvement capture happens during steps. Proposal authoring happens at end of phase.** One bundled proposal per phase, filed via `noctus.dev.file_proposal(project="media-scheduling-wiring", worktree_path="$PWD", …)` → lands in `products/media-scheduling/projects/media-scheduling-wiring/proposals/`.

---

### Phase 0 — Discovery & inventory ✅ *(2026-05-11)*

Produced the concrete gap table in §5.4. Every subsequent phase references rows from this table — no phantom scope.

- [x] **0.a — Backend route inventory:** enumerated every `prefix=` declaration across 5 product routers; counted endpoints via `@router.(get|post|put|patch|delete)`. Total: **13 product endpoints across 5 routers** + 3 seed-mounted standard routers. Per-router distribution in §5.4.3.
- [x] **0.b — Frontend hook + page inventory:** 3 hook files (8 named exports); 11 pages; surveyed 5 unique `/api/` paths from hooks. **0 raw `fetch()` in product code**; `Equipe.tsx` uses `api.*` directly per seed convention (byte-identical to seed → carve-out). Captured in §5.4.1.
- [x] **0.c — Gap table (7 Pattern shapes A-G + PF lessons §b.2 Pattern H orphaned-hook):** captured in §5.4.2. **Pattern counts:** A=0 (EN-only canonical), B=N/A (single-tenant), C=0 (every detail-path verified), D=0 (no product-side bypasses; Equipe is seed-conformant), E=systemic (0/5 routers declare `response_model`), F=6 routes using legacy `Header()` auth, G=0, H=2 confirmed orphan hooks (`useAppointment(id)` + `useAuthorizedUser(id)` — both detail-view with LIVE backend; future-use).
- [x] **0.d — Migration column cross-reference:** parsed `CREATE TABLE` statements across 6 migrations (14 tables); cross-checked against `.table(...)` calls in routers + services. **No hard drift; 2 wire-shape aliases** (`start_at↔starts_at`, `active↔is_active`) + **1 phantom field** (hook `AuthorizedUser.notes` — DB column missing) documented inline + flagged for Phase 4 cleanup. Captured in §5.4.5.
- [x] **0.e — Seed-lib export catalog inheritance:** `grep -rE 'from noctusai_(lib|seed)' app/` → 47 imports across 8 files; table in §5.4.6. **media-scheduling is the deepest seed-lib consumer** of any wiring product (chatbot + redis + whatsapp + webhook_signatures + scheduling + google_calendar + google_maps + tool_audit + 5 seed-app factories).
- [x] **0.f — Phase 0 deliverable:** PROJECT.md §5.4 populated; §6 phases promoted from placeholders to concrete sub-tasks; §7 design batch surfaced (5 Q items + Q-DETAIL + Q-WIRE for orphan-hook + ghost-field decisions); §11 first entry below.
- [x] Pytest baseline confirmed green: 87 collected, 87 passed, 0 failed.
- [x] Keeper review: **0 issues**.

**Deliverable produced:** §5.4 populated (5.4.1 counts → 5.4.9 keeper); phases 1-7 carry concrete work items rooted in §5.4 rows; design-batch surfaced in §7 (5 Q items + Q-DETAIL + Q-WIRE) for user sign-off before Phase 1.

#### Phase 0 → §7 design-batch handoff

Five design questions surfaced. All carry default recommendations; surface as one batch to user before Phase 1.
- §7 Q-A — Pattern A EN/PT alignment. Default rec: **NO RENAME** (media-scheduling is EN-canonical by scaffold-design).
- §7 Q-D — Pattern D supabase.from() bypass hooks. **N/A** — 0 occurrences product-side; Equipe is seed-conformant.
- §7 Q-E — Pattern E DTO contract via `response_model`. Default rec: **defer to cross-product follow-up project `platform-dto-contract`; accept-with-rationale** for this project (mirrors ERP/therapy/PF/mailing/daily-life — N=6).
- §7 Q-F — Pattern F `Header(authorization)` legacy shape (6 occurrences). Default rec: **adopt `make_get_current_user_org` from seed if it ships before Phase 1; else verify-seed-ships-it defer per PF retro §e.**
- §7 Q-DETAIL — `useAppointment(id)` + `useAuthorizedUser(id)` orphan-with-live-backend. Default rec: **KEEP** both; the planned detail pages are future-use scaffolding.
- §7 Q-WIRE — Ghost fields on `Appointment` type (`property_label`, etc.) + phantom `notes` field on `AuthorizedUser`. Default rec: **populate via joined queries in Phase 4 backend** (preferred — preserves UI affordance) OR **remove from frontend type** if scope creeps.
- §7 Q-NEW-DEL — Test coverage gap (4 missing router tests). Default rec: **address in Phase 3** (router-test batch) alongside any DTO touch-ups.

**Improvements:** none filed as a separate proposal. Captured inline in §5.4.2 Patterns A-H — the gap table itself is the Phase 0 artifact. Per `feedback_auto_improvement`.

---

### Phase 1 — Seed-side absorption verification + Pattern F sweep

Mirrors PF Phase 1 shape. For each cross-product candidate, run the verify-seed-ships-it test (read seed's `__init__.py` exports + concrete adapter), then:
- If seed ships it → adopt across media-scheduling backend.
- If seed has Protocol + Fake only → defer with destination.
- If seed is fully absent → file follow-up project, ship against Fake.

- [ ] **`make_get_current_user_org` adoption / defer decision.** N=6 platform-wide.
- [ ] **Pattern E (`response_model`) — defer to platform follow-up, accept-with-rationale this project.**
- [ ] **Status-code-assertion calibration** — run `noctus.dev.scan_block_patterns mode=status_assertion` over media-scheduling test corpus; produce inventory; either fix inline OR pin baseline-no-regress.
- [ ] **Verify each adopted seed module's current `__init__.py` exports** — Fake+Real audit for chatbot / whatsapp / redis / google_calendar / google_maps / scheduling / webhook_signatures / tool_audit.

### Phase 2 — Wire-shape + phantom-field cleanup

- [ ] **Decide:** populate `Appointment` ghost fields via joined query OR remove from frontend type. (Default rec: populate — preserves UI affordance for the planned detail page.)
- [ ] **Decide:** `AuthorizedUser.notes` — remove from frontend type (DB column missing).
- [ ] If populate path: add joined select in `list_appointments` + `get_appointment`; add response shape tests.
- [ ] Frontend type updates + page rendering for new fields.

### Phase 3 — Router test coverage

- [ ] `tests/routers/test_appointments_router.py` — list / detail / filter / 404 paths; status-code + body assertions.
- [ ] `tests/routers/test_authorized_users_router.py` — full CRUD with status + body assertions; wire-shape verification.
- [ ] `tests/routers/test_condominiums_router.py` — list-only.
- [ ] `tests/routers/test_notificacoes_router.py` — standard-router smoke (PF Phase 7 lesson §d.4).

### Phase 4 — Frontend type alignment + detail page (if user signals)

- [ ] Type cleanups from Phase 2.
- [ ] Optional: `AppointmentDetailPage` build if user signals (otherwise keep `useAppointment(id)` as future-use scaffolding).
- [ ] Optional: `AuthorizedUserDetailPage` build (same shape).

### Phase 5 — End-to-end verification

- [ ] `cd products/media-scheduling/frontend && npx vite build` — green.
- [ ] `cd products/media-scheduling/backend && PYTHONPATH=seed/lib/backend:seed/framework/backend python3.11 -m pytest -q` — green.
- [ ] `python mcp/noctusai/cli.py --review --product media-scheduling --worktree-path "$PWD"` — 0 issues.
- [ ] Manual browser QA: Dashboard, AppointmentsPage, AuthorizedUsersPage, OAuthStatusPage, Equipe all render 200.

### Phase 6 — Close

- [ ] Project retrospective written (lessons.md or inline §11).
- [ ] Follow-ups filed for any deferred items.
- [ ] Bundled proposals at `proposals/`.
- [ ] FF-to-main as literal last step (per `feedback_orchestrator_role` 2026-05-10 amendment).

---

## 7. Design batch — pending user sign-off

Five questions + Q-DETAIL + Q-WIRE + Q-NEW-DEL — all carry default recommendations. User signal needed before Phase 1.

| # | Question | Default rec |
|---|---|---|
| Q-A | EN/PT path alignment | NO RENAME — EN-canonical |
| Q-D | Pattern D bypass hooks | N/A — 0 occurrences |
| Q-E | `response_model` adoption | DEFER to `platform-dto-contract` follow-up; accept-with-rationale |
| Q-F | `make_get_current_user_org` adoption | Verify-seed-ships-it; adopt if shipped, defer if not |
| Q-DETAIL | `useAppointment(id)` + `useAuthorizedUser(id)` orphan-with-live-backend | KEEP — future-use scaffolding |
| Q-WIRE | Ghost fields on `Appointment` + phantom `notes` on `AuthorizedUser` | POPULATE in Phase 4 backend (preferred) OR remove from frontend type |
| Q-NEW-DEL | Router test coverage gap (3 missing) | ADDRESS in Phase 3 batch |

---

## 8. Risks

- **Redis-less dev path:** Webhook accepts but worker no-ops without `REDIS_URL`. Phase 5 manual QA needs the deploy-drill to set Redis OR explicit acceptance.
- **Google OAuth single-account assumption:** If product evolves to multi-tenant, the current `provider+account_email` UNIQUE shape in `oauth_credentials` becomes a constraint to revisit.
- **`useAppointment(id)` future-use scaffolding:** if the planned detail page is never built, the orphan hook + backend route become dead code. Phase 4 decision point.

---

## 9. Open questions

See §7 design batch.

---

## 10. Copy-paste — quick re-orient

```bash
# Baseline pytest
cd products/media-scheduling/backend && \
  PYTHONPATH="$PWD/../../../seed/lib/backend:$PWD/../../../seed/framework/backend" \
  python3.11 -m pytest -q

# Keeper review
python mcp/noctusai/cli.py --review --product media-scheduling --worktree-path "$PWD"

# Vite build
cd products/media-scheduling/frontend && npx vite build
```

---

## 11. Change log

### 2026-05-11 — Phase 0 ✅ (Engineer TTT, branch `worktree-agent-a4cd83c22ace4d8e7`)

**Discovery delivered:**
- Backend: 5 product routers (13 endpoints) + 3 seed-mounted standard routers.
- Frontend: 3 hook files (8 named exports) + 11 pages.
- 6 migrations, 14 tables.
- Pattern counts: A=0, B=N/A, C=0, D=0 (Equipe is seed-conformant), E=N=6 platform-wide, F=6 routes using legacy `Header()`, G=0, H=2 (future-use detail-page scaffolding).
- Seed-lib import depth: 47 imports across 8 files — deepest consumer of any wiring product.
- Migration drift: 2 wire-shape aliases (KEEP inline) + 1 phantom field (`AuthorizedUser.notes` — Phase 4 cleanup).
- Pytest baseline: **87/87 green**.
- Keeper: **0 issues, 0 proposals**.

**Cross-product recurrence count updates:**
- `make_get_current_user_org`: PF + ERP + therapy + mailing + daily-life + **media-scheduling = N=6 confirmed**.
- Pattern E (no `response_model=`): **N=6 confirmed platform-wide**.
- `useAppointment(id)` orphan-with-live-backend: N=1 within media-scheduling (NEW shape — different from ERP's both-side orphan).

**Improvements:** captured inline in §5.4.2.

**§7 design batch:** 7 Q items surfaced with default recommendations — awaiting user sign-off before Phase 1.

**Phase 0 phase_learning candidates (for `noctus.dev.phase_learning_log`):**
- Worktree bootstrap script (§16.7 step 3) does NOT pip-install backend deps; sqlalchemy was missing on python3.11 — surface to orchestrator.
- media-scheduling is the cleanest wiring baseline (no Pattern A/D/G, 0 hard drift, 87/87 green, 0 keeper) — recommend it as the master-tree calibration product when reviewing branching-first orchestration metrics.
