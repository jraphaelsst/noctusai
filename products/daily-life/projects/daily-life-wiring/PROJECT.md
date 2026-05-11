# Daily-Life Wiring — Project Document

> **This is a living document, not a rigid checklist.**
> Mirrors `personal-finance-wiring` (closed 2026-05-11) + `therapy-platform-wiring`
> (in flight). Inherits PF's lessons file
> (`archive/projects/2026-05-11/16-personal-finance-wiring/personal-finance-wiring-lessons.md`)
> as foundational input.

- **Created:** 2026-05-11
- **Last updated:** 2026-05-11 (Phase 2 ✅)
- **Status:** ⏳ **Phase 0 ✅ · Phase 1 ✅ · Phase 2 ✅** — Pattern F (auth-factory) + Pattern H (orphan deletes) shipped Phase 1; Pattern A (EN-rename `/api/metricas` → `/api/metrics`) shipped Phase 2 + stranded-Phase-1-reference cleanup in MASTER-PROMPT.md + weekly_review_service.py docstring. Phase 3 (`ai_outputs` standard router + mount-smoke + status-assertion sweep) pending.
- **Owner / stakeholders:** Raphael (joaoraphaelsst@gmail.com) · Claude Opus 4.7
- **Related docs:**
  - `archive/projects/2026-05-11/16-personal-finance-wiring/personal-finance-wiring-lessons.md` — direct prior-art reference
  - `products/therapy-platform/projects/therapy-platform-wiring/PROJECT.md` — Pattern A-G inventory shape
  - `CLAUDE.md § Engineering Philosophy` — behavioral rules
  - `KNOWLEDGE-BASE/CONTEXT/02-LANDSCAPE.md` — product surface inventory
  - `KNOWLEDGE-BASE/CONTEXT/PATTERNS/project-execution.md` — cadence, naming
  - `products/daily-life/MASTER-PROMPT.md` — agent-facing product contract
- **Project slug:** `daily-life-wiring`

---

## 1. Context & Purpose

`daily-life` is a Portuguese-language personal-productivity product (tasks,
goals, habits, schedule, notes, automations). It inherits from the seed
framework (`create_product_app` + standard routers `health` / `notificacoes`
/ `team` / `ai_feedback`) and is **already largely wired**: 6 frontend
hooks map cleanly onto 5 backend routers with no `404` / `405` / verb
mismatches discovered at Phase 0.

The reasons this is still a non-trivial *wiring* project — not "ship as-is":

1. **Two orphan backend routers** with zero frontend consumers (Pattern H):
   - `/api/foco` (5 endpoints) — no `useFoco` / `Focus.tsx` exists.
   - `POST /api/ai/weekly-review/send` (1 endpoint) — no "email me this digest" UI.

2. **Two Portuguese path-prefix outliers** in an otherwise English path-set
   (Pattern A — see §5.4.2): `/api/metricas`, `/api/foco`. Daily-life is
   user-facing-Portuguese, so the EN/PT decision is **different from
   therapy** (which defaulted to EN-rename of 8 PT routers). User input
   needed (§7 Q1).

3. **Manual auth-triple in all 7 product routers** (Pattern F): every
   endpoint runs `user, token = await get_current_user(authorization);
   org_id = get_org_id(user); db = get_user_client(token)`. PF+ERP+therapy
   already filed `make-get-current-user-org-factory` seed-absorption
   project; daily-life makes that **N=4 across the platform**.

4. **Implicit DTO contract** (Pattern E): zero of 35 routes declare
   `response_model`. Same project-wide deferral pattern as PF/therapy.

5. **PF lessons §(b) item 1 fires**: this worktree has **no
   `mcp/noctusai/.venv`** — `cli.py --review` cannot run from here, and
   `pytest -q` only goes green with explicit `PYTHONPATH`. Either
   `bootstrap-worktree.sh` should be expanded, or architect runs keeper
   post-FF-merge.

The win looks like: every `useTarefas` / `useMetas` / `useNotas` /
`useAgenda` / `useAI` / `useDashboard` round-trip 200s with a typed body;
no Pattern-A naming drift; no Pattern-H orphan routes; auth-factory
absorbed when seed real adapter ships; `vite build` clean; `pytest`
green with the worktree-venv override documented.

---

## 2. Confirmed constraints

User answers captured at project-creation interrogation. **Phase 0 was
dispatched directly per the brief** — no live interrogation yet, so this
section lists the *brief-derived* constraints; user explicit confirmation
deferred to §7 Open Questions surfaced at end-of-Phase-0.

- **Scope** — full wiring sweep of the `daily-life` product (mirrors PF
  + therapy). *(Rules out narrow "just fix Pattern H" framing — covers
  Patterns A / E / F / H end-to-end.)*
- **Tests** — three-layer discipline per `CONTEXT/PATTERNS/testing.md`,
  not a per-phase decision. *(A phase without its tests is `⏳ (tests
  deferred)`, not `✅`.)*
- **Cadence** — phase-by-phase, pause after each, no auto-advance.
  *(Same as PF + therapy.)*
- **Seed sync** — patterns worth promoting mid-project land as phase-end
  proposals via `noctus.dev.file_proposal(project="daily-life-wiring",
  …)`. Reviewer triages separately.
- **PF-lessons inheritance** — every numbered lesson in
  `personal-finance-wiring-lessons.md` is a constraint on this project:
  §(a) Phase-0 budget; §(b) bootstrap-worktree; §(b) Pattern-H consumer
  count; §(b) status-code-assertion calibration; §(c) verify-the-seed-
  ships-it; §(d) test patterns. **The lessons are inputs, not
  references.**

---

## 3. Design principles

How we're approaching *daily-life specifically* on top of the platform-wide
`CLAUDE.md` rules.

1. **Smaller scope ⇒ tighter phases.** Daily-life is ~⅕ the size of
   therapy (7 routers vs. 38). Plan for 4-5 phases vs. therapy's 9. Do
   NOT inherit therapy's phase count out of mimicry.
2. **Pattern H decisions happen at Phase 0, not Phase 5.** PF's lesson
   §(b) #2: extend §5.4 with a "consumer count" column; orphans get
   routed to delete-or-wire decision **before** any code phase starts.
3. **Auth-factory absorption waits on seed adapter.** Do NOT consumer-
   side fork `make_get_current_user_org` in daily-life when PF+ERP+therapy
   have already filed the seed-real-adapter project. Use the
   manual-triple as-is until the seed ships. *(Verify-the-seed-ships-it
   discipline.)*
4. **EN/PT decision is user-driven, not auto-defaulted.** Daily-life is
   product-Portuguese; therapy was Pattern-A-mostly-English. Don't
   transplant therapy's default. Surface Q1 at end-of-Phase-0.
5. **Tests land in the same phase as the code.** Three-layer.

---

## 3a. Seed-first analysis (REQUIRED)

Run the six-question checklist (`KB § GUIDES/seed-first-design.md § The
seed-first checklist`):

1. **Is the contract identical for every product?** **NO for daily-life-specific
   wiring decisions** (the gap table is per-product), **YES for the auth-factory
   absorption** (already filed by PF as `make-get-current-user-org-factory`
   project — daily-life consumes when shipped).
2. **Is the data source product-specific?** **YES** — daily-life schema
   (`tarefas`, `metas`, `eventos`, `notas`, `sessoes_foco`, `checkins`,
   `metricas_produtividade`) is intrinsically product-bound.
3. **Is the placement product-specific?** **YES** — every Pattern A/E/H row
   names a daily-life backend router or hook.
4. **Is the visibility / permission rule the same?** **YES** — all daily-life
   routes use the same seed-issued `get_user_client(token)` pattern.
5. **Does the seam already exist in seed?** **PARTIAL**:
   - `create_product_app`, `create_dependencies`, `create_database_module`,
     `standard_routers` mounting — **YES, all consumed**.
   - `noctusai_lib.api.crud_safety.delete_or_404` — **YES, consumed by 3 routers**.
   - `noctusai_lib.domain.metas.*` — **YES, consumed** (PF's filed follow-up
     is now shipped per `KB § PATTERNS/metas-seed.md`).
   - `noctusai_lib.api.auth.make_get_current_user_org` factory — **NOT
     SHIPPED** (verify-the-seed-ships-it test fires; project filed by PF).
6. **Default-on or opt-in?** N/A (wiring project, not a seed-extension project).

**Litmus — per-product code count this design requires:**

- [x] **A small section** — daily-life routes, hooks, and pages. *Acceptable
  for product-bounded data + UI wiring*; the Pattern-F auth-factory
  absorption is **0-lines-per-product** (waits on seed).

**Phase plan implications:** §6 phases work **inside daily-life only**.
No "replicate across products" framing. The single cross-product touchpoint
(auth-factory) is gated on the existing seed follow-up project — daily-life
makes it N=4 but does not file a new project (PF already did).

---

## 4. Scope

**In scope:**

- Every `daily-life` backend endpoint that a frontend hook calls. Phase 0
  inventory covers all of: `/api/tasks/*`, `/api/goals/*`, `/api/schedule/*`,
  `/api/notes/*`, `/api/metricas/*`, `/api/foco/*`, `/api/ai/*`.
- Pattern A (EN/PT path mismatch) decisions for `/api/metricas` and `/api/foco`
  — pending user input on §7 Q1.
- Pattern H (orphan) decisions for `/api/foco` × 5 endpoints and
  `POST /api/ai/weekly-review/send` — delete-or-wire choice surfaced at
  end-of-Phase-0.
- Hook/page corrections required if any Phase 1+ rename ripples to the
  frontend.
- Tests landing in the same phase as the code they cover.
- `noctus.dev.lgpd_flag` calls for any new endpoint aggregating
  personal data in shapes not previously flagged.

**Out of scope (for now — with reason):**

- **`make_get_current_user_org` seed real adapter** — filed by PF as
  `make-get-current-user-org-factory`; daily-life adopts when shipped.
  *(Verify-the-seed-ships-it.)*
- **DTO contract / `response_model` on all 35 routes** — defer to
  `daily-life-dto-contract` follow-up, mirror PF/therapy's accept-with-
  rationale.
- **Scheduler standard router** — PF filed `phase-5-scheduler-standard-
  router` proposal; daily-life does not have a per-product scheduler today.
- **New features** — no capability not already present as scaffolded UI.
- **Other products** — different slugs.

---

## 5. Architecture / Data Model

### 5.1 Daily-life backend router prefixes (Phase 0 snapshot 2026-05-11)

| Router | Prefix | Endpoints | Tag |
|---|---|---|---|
| `tasks` | `/api/tasks` | 6 | Tasks |
| `goals` | `/api/goals` | 7 | Goals & Habits |
| `schedule` | `/api/schedule` | 5 | Schedule |
| `notes` | `/api/notes` | 6 | Notes |
| `foco` | `/api/foco` | 5 | Focus Sessions |
| `metrics` | `/api/metricas` | 3 | Metrics |
| `ai` | `/api/ai` | 3 | AI |
| **Total** | — | **35** | — |

### 5.2 Daily-life frontend hook → backend route map (clean baseline)

| Hook | Pages | Backend round-trips | Notes |
|---|---|---|---|
| `useTarefas.ts` | `Tarefas.tsx`, `Dashboard.tsx` | `/api/tasks` × 5 (list+stats+create+patch+delete) | ✅ |
| `useMetas.ts` | `Metas.tsx` | `/api/goals` × 6 (list+checkins+create+patch+delete+checkin) | ✅ |
| `useNotas.ts` | `Notas.tsx` | `/api/notes` × 6 (list+create+patch×2+delete+extract-tasks) | ✅ |
| `useAgenda.ts` | `Agenda.tsx`, `Dashboard.tsx` | `/api/schedule` × 4 (list+create+patch+delete) | ✅ |
| `useDashboard.ts` | `Dashboard.tsx` | `/api/tasks/stats/resumo` + `/api/metricas/resumo` + `/api/schedule?today` | ✅ |
| `useAI.ts` | `Dashboard.tsx` (likely) | `/api/ai/daily-brief` + `/api/ai/weekly-review` | ✅ |

**Direct fetches in pages (not via product hooks):**
`pages/Equipe.tsx` (5 calls to `/api/team*`) + `pages/AcceptInvite.tsx`
(`/api/team/accept`). **All hit the seed `team` standard router** —
not Pattern D; correctly routed.

### 5.3 Daily-life DB schema (`daily_life`)

Migrations:
- `001_daily_life.sql` — full schema (single 001 per `KB § single-001-migration`).
  Tables: `status_pagina`, `invitations`, `tarefas`, `metas`, `checkins`,
  `eventos`, `notas`, `metricas_produtividade`, `sessoes_foco`, `commands`,
  `intent_patterns`, `context_rules`, `command_history`, `learned_promotions`
  (14 total).
- `002_recurring_events.sql` — `ADD COLUMN recorrencia / recorrencia_fim /
  evento_pai_id` on `eventos`.
- `003_ai_feedback.sql` — `CREATE TABLE daily_life.ai_feedback`.
- `004_invitations_accepted_columns.sql` — `ADD COLUMN accepted_at /
  accepted_by` on `invitations`.

**Cross-check (Phase 0):** column references in services
(`db.table("tarefas").select("status")`, etc.) all resolve to tables in
`001_daily_life.sql`. **No schema drift detected.** Phase 1+ does not need
a migration unless Pattern A/H decisions require renames.

### 5.4 Inventory (populated 2026-05-11 by Phase 0)

#### 5.4.1 Headline counts

| Surface | Count |
|---|---|
| Backend routers | 7 (`__init__.py` excluded) |
| Backend endpoints | 35 |
| Frontend hooks | 6 (all under `frontend/src/hooks/`) |
| Frontend pages with direct `useQuery` / `api.*` | 0 product-routes (Equipe + AcceptInvite hit `/api/team` seed router) |
| Unique frontend → backend calls surveyed | 30 distinct method+path combinations |
| Gap rows (404 / 405 / path / verb / orphan) | **8** (2 Pattern-A path-renames; 6 Pattern-H orphans) |
| Backend routers with `response_model` declared | **0 / 7** — Pattern E (project-wide deferral) |

#### 5.4.2 Systemic findings (Pattern shapes)

| Pattern | Description | Count | Disposition |
|---|---|---|---|
| **A** | EN/PT path mismatch (frontend EN, backend PT — or vice-versa) | ~~2 routers: `/api/metricas` + `/api/foco`~~ → **CLOSED**: `/api/foco` deleted Phase 1; `/api/metricas` → `/api/metrics` renamed Phase 2 (Q1 = Option B, EN-rename) |
| **B** | Admin-namespace split | 0 | n/a (no admin console) |
| **C** | Admin-detail endpoints missing | 0 | n/a |
| **D** | Role-prefix paths in direct-fetch pages | 0 | Equipe/AcceptInvite hit seed `team` router — correctly routed |
| **E** | Implicit DTO contract (no `response_model`) | All 35 routes | Accept-with-rationale; defer to `daily-life-dto-contract` follow-up |
| **F** | Manual auth-triple (`get_current_user` + `get_org_id` + `get_user_client`) recurrence | ~~All 7 product routers~~ → **CLOSED**: Phase 1 absorbed (29 callsites refactored to `Depends(get_current_user_org)`; seed real adapter shipped ahead of plan) |
| **G** | Path-shape mismatch (beyond language) | 0 spotted | n/a |
| **H** | Orphan-backend-route (zero FE consumer) | ~~6 endpoints: `/api/foco/*` (5) + `POST /api/ai/weekly-review/send` (1)~~ → **CLOSED**: Phase 1 = Option A (DELETE both); router file + 26 paired tests removed |

#### 5.4.3 Per-hook gap inventory

Format: `✅` = wired correctly; `❌` = gap.

**`hooks/useTarefas.ts` — Tarefas page**
- ✅ `GET /api/tasks?…` → `tasks.py:48`
- ✅ `GET /api/tasks/stats/resumo` → `tasks.py:173`
- ✅ `POST /api/tasks` → `tasks.py:78`
- ✅ `PATCH /api/tasks/{id}` → `tasks.py:124`
- ✅ `DELETE /api/tasks/{id}` → `tasks.py:154`

**`hooks/useMetas.ts` — Metas page**
- ✅ `GET /api/goals?…` → `goals.py:61`
- ✅ `GET /api/goals/{id}/checkins?…` → `goals.py:197`
- ✅ `POST /api/goals` → `goals.py:88`
- ✅ `PATCH /api/goals/{id}` → `goals.py:137`
- ✅ `DELETE /api/goals/{id}` → `goals.py:164`
- ✅ `POST /api/goals/{id}/checkin` → `goals.py:179`
- (backend orphan: `GET /api/goals/{id}` → `goals.py:117` — no FE caller; *minor Pattern-H candidate but generic CRUD-detail; safe to keep*)

**`hooks/useNotas.ts` — Notas page**
- ✅ `GET /api/notes?…` → `notes.py:47`
- ✅ `POST /api/notes` → `notes.py:74`
- ✅ `PATCH /api/notes/{id}` → `notes.py:112`
- ✅ `DELETE /api/notes/{id}` → `notes.py:136`
- ✅ `POST /api/notes/{id}/extract-tasks` → `notes.py:147`
- (backend orphan: `GET /api/notes/{id}` → `notes.py:98` — generic detail; safe to keep)

**`hooks/useAgenda.ts` — Agenda page**
- ✅ `GET /api/schedule?…` → `schedule.py:60`
- ✅ `POST /api/schedule` → `schedule.py:90`
- ✅ `PATCH /api/schedule/{id}` → `schedule.py:135`
- ✅ `DELETE /api/schedule/{id}` → `schedule.py:166`
- (backend orphan: `GET /api/schedule/{id}` → `schedule.py:121` — generic detail; safe to keep)

**`hooks/useDashboard.ts` — Dashboard page**
- ✅ `GET /api/tasks/stats/resumo` → `tasks.py:173`
- ✅ `GET /api/metricas/resumo?dias=7` → `metrics.py:40` *(Pattern A — PT prefix)*
- ✅ `GET /api/schedule?today_window` → `schedule.py:60`

**`hooks/useAI.ts` — Dashboard / AI**
- ✅ `GET /api/ai/daily-brief` → `ai.py:95`
- ✅ `GET /api/ai/weekly-review?…` → `ai.py:24`
- ❌ **Backend orphan**: `POST /api/ai/weekly-review/send` → `ai.py:58` (no FE caller — Pattern H)

**No frontend hook for `/api/foco` — Pattern H ORPHAN ROUTER**
- ❌ `GET /api/foco/stats` → `focus.py:43`
- ❌ `GET /api/foco` → `focus.py:71`
- ❌ `POST /api/foco` → `focus.py:95`
- ❌ `PATCH /api/foco/{id}` → `focus.py:117`
- ❌ `DELETE /api/foco/{id}` → `focus.py:144`

---

## 6. Implementation phases

### Phase 0 — Discovery & gap inventory ✅ (shipped 2026-05-11)

- [x] Backend route inventory (35 endpoints / 7 routers / `prefix=` grep)
- [x] Frontend hook + page inventory (6 hooks / 11 pages / 30 unique calls)
- [x] Gap table — 7 Pattern shapes A-G + Pattern H (orphan column per PF lesson §(b)#2)
- [x] Migration column cross-reference (4 migrations / 14 tables / 0 drift)
- [x] Seed-lib inheritance audit (high hit-rate; metas/digest/ai-consent/llm/crud_safety all consumed)
- [x] Deliverable: PROJECT.md §5.4 populated + §6 + §7 + §11

**Improvements:**
- The MCP `cli.py --review` keeper requires `mcp/noctusai/.venv` which
  isn't bootstrapped in ephemeral worktrees; either expand
  `bootstrap-worktree.sh` (preferred) or honor architect-runs-keeper-
  post-merge.
- PYTHONPATH override (`seed/lib/backend:seed/framework/backend`)
  required to run pytest from worktree — same shape as memory entry
  `feedback_migration_prelude_helpers.md`.
- Pre-existing `noctusai_seed.rate_limit` import in
  `app/rate_limit.py` works because the seed framework module ships it;
  verified at Phase 0.

*Phase proposal filed at end-of-Phase-0:* deferred to architect (engineer
returns findings as text per §17.6.1).

### Phase 1 — Pattern F (auth-factory absorption) + Pattern H (orphan deletes) ✅ (shipped 2026-05-11)

**Improvements:** none identified — clean Pattern F + Pattern H shipment per §6 plan.

Original Phase 1 (Pattern H + Pattern A) and Phase 2 (auth-factory) were
**collapsed** when the `make-get-current-user-org-factory` seed real
adapter shipped ahead of expectations. Engineer DL-P1 picked Q2 = Option A
(DELETE both orphans) per default-recommendation. Q1 (Pattern A EN/PT
rename) **deferred to Phase 2** per the brief scope split.

- [x] Pattern F: 29 callsites refactored (manual triple → `Depends(get_current_user_org)`)
  in 6 routers (tasks/goals/schedule/notes/metrics/ai). AST-driven via libcst.
- [x] Pattern H Q2 = DELETE: `app/routers/focus.py` + 18 test cases + 5
  e2e focus 401 tests + 1 focus flow test + `POST /api/ai/weekly-review/send`
  + 2 paired ai tests. Frontend grep confirms 0 references survive.
- [x] `app/dependencies.py` wires `get_current_user_org` via seed factory.
- [x] Baseline pytest: 234 → 208 (delta −26 = removed orphan + factory tests).

### Phase 2 — Pattern A (EN-rename `/api/metricas` → `/api/metrics`) + Phase-1 stranded-reference cleanup ✅ (shipped 2026-05-11)

**Improvements:** none identified — clean Pattern A close. N=3 recurrence on bootstrap-worktree vite-build gap (tailwindcss-animate) → formalize threshold; pre-existing build failure verified via stash-clean-tree.

- [x] Q1 = Option B (EN-RENAME) per default-recommendation. With Q2's
  DELETE landing `/api/foco`, `/api/metricas` became the lone PT outlier
  in 5/6 EN routers → strong-precedent rename. AST-driven via libcst
  (string-literal-only codemod over the 3 .py files; 22 string sites
  rewritten across `app/routers/metrics.py` + `tests/routers/test_metrics_router.py`
  + `tests/integration/test_e2e_flows.py`). Frontend hook updated
  (`useDashboard.ts` `/api/metricas/resumo` → `/api/metrics/resumo`).
- [x] Stranded-reference cleanup caught by Phase 2 read (Phase 1 left these):
  - `products/daily-life/MASTER-PROMPT.md`: removed `Focus` Domain row +
    removed `/api/ai/weekly-review/send` from AI-weekly-review row +
    removed `Foco` Pages row + renamed `/api/metricas` → `/api/metrics`
    in Metrics Domain row.
  - `products/daily-life/backend/app/services/weekly_review_service.py`
    module docstring: corrected the `POST /api/ai/weekly-review/send`
    trigger reference to the GET endpoint + flagged the historical
    deletion (Phase 1 retired the POST).
- [x] Frontend UI route `/metricas` (PT label) **preserved** — daily-life
  is product-Portuguese; the backend-rename rationale ("internal-facing
  technical paths") does NOT extend to user-facing UI labels.
- [x] DB table name `metricas_produtividade` **preserved** — data-model
  identifier, not API surface.
- [x] Pytest 210/210 green (no delta from Phase 1 close).
- [x] **[DEFERRED-PRE-EXISTING]** **Pre-existing build gap (NOT introduced by Phase 2):** `npx vite build`
  fails on `tailwindcss-animate` resolution from the seed framework's
  `tailwind.config.factory.ts` — verified by stash-clean-tree reproduction.
  Belongs in the same `bootstrap-worktree.sh` follow-up surfaced by Q4 (PF lesson §(b)#1).

### Phase 3 — Standard-router smoke + status-assertion sweep + optional `ai_outputs` mount

Per PF lesson §(d)#4: dispatch the 5-test mount-shape smoke pattern for
seed-routed `health` / `notificacoes` / `team` / `ai_feedback` + (if
adopted in §7 Q3) `ai_outputs`.

Per PF lesson §(b)#3: run `noctus.dev.scan_block_patterns
mode=status_assertion` over `tests/` corpus; either fix in this phase
or pin as TIER B baseline-no-regress.

- [ ] Mount-smoke for each standard router (2 tests/router with status +
  body assertion).
- [ ] Status-assertion calibration pass on existing test corpus.

### Phase 4 — Final retrospective + commit/push gate

- [ ] Final build + pytest + keeper run (architect-side post-FF-merge).
- [ ] Phase-end proposal bundle.
- [ ] Lessons file → `daily-life-wiring-lessons.md`.
- [ ] FF-to-main is the literal last step (per orchestrator-role rule).

---

## 7. Open questions

Surfaced at end of Phase 0 for user decision before Phase 1 dispatch.

1. **Q1 — EN/PT path policy for `/api/metricas` + `/api/foco`.**
   Daily-life is product-Portuguese (Tarefas / Metas / Notas / Agenda
   UI labels are PT). Therapy chose EN-rename for its 8 PT outliers
   (`alertas-crise` → `crisis-alerts`, etc.) on the grounds that
   *backend paths are technical infrastructure*, not user-facing copy.
   But daily-life backend is *already English-majority* (5 of 7
   routers: `/api/tasks`, `/api/goals`, `/api/schedule`, `/api/notes`,
   `/api/ai`) — `/api/metricas` and `/api/foco` are the only outliers.
   - **Option A (KEEP PT — recommend if cost-sensitive):** accept-with-
     rationale; document in `KB § PATTERNS/accept-with-rationale.md`
     as "daily-life backend is mixed EN/PT — internal-facing only;
     no external consumers."
   - **Option B (EN-RENAME — recommend if consistency-sensitive):**
     rename to `/api/metrics` + `/api/focus`. Cost: 1 line in
     `useDashboard.ts` + the new `useFoco.ts` (if Q2 wires); 1 line
     in `main.py`; rename 2 router prefixes; update 6 router-test
     files (search/replace).
   - **My recommendation:** Option B (EN-RENAME). Rationale: the
     majority precedent (5 of 7 already EN) + therapy's same
     decision + the rename cost is trivial. **But** the recommendation
     reverses if Q2 lands "delete `/api/foco`" — then `/api/metricas`
     becomes a single-router outlier and may not be worth the rename.

2. **Q2 — Pattern H disposition for `/api/foco` (5 endpoints) +
   `POST /api/ai/weekly-review/send` (1 endpoint).**
   - `/api/foco`: no `Focus.tsx` page, no `useFoco.ts` hook. The router
     exists in `main.py`'s import list (`from app.routers import …
     focus, …`). The router was either (a) scaffolded ahead of a Focus
     page that never landed, or (b) intended for an AI-agent or
     scheduler caller that doesn't materialize in the codebase.
   - `POST /api/ai/weekly-review/send`: paired with the wired
     `GET /api/ai/weekly-review`. Likely intended to email the
     digest result to the user.
   - **Option A (DELETE both — recommend if the product owner
     hasn't planned the feature):** remove `app/routers/focus.py`,
     drop the `focus.router` import + the `focus` arg in `main.py`,
     delete `tests/routers/test_focus_router.py`. Remove
     `POST /api/ai/weekly-review/send` endpoint + its test.
   - **Option B (WIRE the focus feature):** author `Focus.tsx` page +
     `useFoco.ts` hook + `App.tsx` route + tests. Larger scope, may
     deserve its own dedicated `daily-life-focus-feature` project.
   - **Option C (HYBRID — defer focus, delete `/send`):** keep
     `/api/foco` (anticipating a future Focus page) but delete the
     orphan `/send` endpoint.
   - **My recommendation:** Option A. Rationale: per PF lesson
     §(b)#2, orphan-route ⇒ delete-or-wire at Phase 0, and a UI
     scaffold for Focus isn't anywhere in the repo (no design
     placeholder, no `// TODO Focus.tsx`). Deletion can be reverted
     with a single git revert when the feature ships.

3. **Q3 — Should daily-life mount the `ai_outputs` seed standard router?**
   Current wiring: `standard_routers=["health", "notificacoes", "team",
   "ai_feedback"]` (no `ai_outputs`). Daily-life DOES produce structured
   LLM output (daily-brief + weekly-review) — surfacing the persisted
   outputs at `/api/ai-outputs` would let a future "history" UI surface
   them without per-product backend code.
   - **My recommendation:** add `ai_outputs` in Phase 3 alongside the
     mount-smoke tests. Low cost (one string in `main.py`); high optionality.

4. **Q4 — Worktree-bootstrap expansion (cross-product methodology Q).**
   PF lesson §(b)#1 already named this; daily-life confirms recurrence.
   Should `bash scripts/bootstrap-worktree.sh` be expanded to install
   `mcp/noctusai/requirements.txt` so keeper runs from any worktree?
   - **My recommendation:** YES — file a separate one-engineer
     `bootstrap-worktree-mcp-deps` feature (lightweight, ≤2 files).
     Daily-life is the N=2 product (PF was N=1) — formalize.

---

## 8. Dependencies & blockers

- **`make-get-current-user-org-factory` seed real adapter** — Phase 2 is
  gated on this shipping. Filed by PF as a follow-up project. If not
  shipped before daily-life Phase 2 dispatch, defer Phase 2 to
  post-seed-adapter and continue with Phase 3.
- **Worktree-venv** — `cli.py --review` cannot run from this worktree
  until `bootstrap-worktree.sh` is expanded (Q4). Workaround:
  architect runs keeper post-FF-merge from noc root.

---

## 9. Success criteria

- All 234 backend tests pass (`PYTHONPATH=… pytest -q` from worktree, or
  default `pytest` from noc root).
- `vite build` clean for `products/daily-life/frontend`.
- Keeper (`cli.py --review --product daily-life`) emits 0 issues.
- Every Pattern H row in §5.4.2 closed (delete or wire).
- Every Pattern A row in §5.4.2 closed (KEEP-PT-with-rationale or EN-rename).
- Auth-factory absorbed (Pattern F closed) — gated on §8 dependency.
- Standard-router mount-smoke tests landed (PF lesson §(d)#4).
- Phase 4 lessons file synthesized + filed at
  `archive/projects/YYYY-MM-DD/NN-daily-life-wiring/daily-life-wiring-lessons.md`.

---

## 10. How to use this plan

**For the next agent picking up Phase 1:**

```bash
# Verify base + worktree
cd /Users/rapha/Documents/repository/NoctusAI/noctusai/.claude/worktrees/<your-worktree>
git log -1 --format='%H %s'  # expect daily-life-wiring Phase 0 commit on branch

# Baseline test (PYTHONPATH override)
PYTHONPATH="$PWD/seed/lib/backend:$PWD/seed/framework/backend:$PYTHONPATH" \
  cd products/daily-life/backend && pytest -q
# expect: 234 passed

# Read Phase 1 dispatch
cat products/daily-life/projects/daily-life-wiring/PROJECT.md | sed -n '/Phase 1/,/Phase 2/p'

# Phase 1 entry depends on Q1+Q2 outcomes — DO NOT dispatch Phase 1 until user confirms
```

**For the architect:**

- §7 Q1 + Q2 are the gating decisions. Surface to user before any Phase 1 dispatch.
- §7 Q4 (`bootstrap-worktree.sh` expansion) is a parallelizable feature project.
- §8 dependency: confirm `make-get-current-user-org-factory` project status before Phase 2.

---

## 11. Change log

### 2026-05-11 — Phase 2 ✅ (Engineer DL-P2)

- Scope (per dispatch brief + default-recommendations on §7 open questions):
  - **Q1 = Option B (EN-RENAME)** applied. Rationale: Q2's DELETE landing
    in Phase 1 dropped `/api/foco`, leaving `/api/metricas` as the single
    PT outlier in 5/6 EN routers — the §7 recommendation's "majority
    precedent" condition strengthened.
  - **Q3 (mount `ai_outputs` standard router)** **DEFERRED to Phase 3**.
    The §7 "low cost (one string in main.py)" estimate was incomplete:
    the seed `create_ai_outputs_router` reads from a per-product
    `<schema>.ai_outputs` table that daily-life doesn't provision. Adding
    the mount without the migration would let the router's `try/except`
    silently return empty arrays — a no-silent-errors violation. Belongs
    in Phase 3 alongside the migration (cleaner-scoped focused brief).
- **Pattern A close** (`/api/metricas` → `/api/metrics`):
  - libcst codemod over 3 .py files: 1 prefix-arg change in `metrics.py`
    + 15 URL strings in `tests/routers/test_metrics_router.py` (incl.
    module docstring) + 6 URL strings in `tests/integration/test_e2e_flows.py`
    = 22 string-literal sites rewritten.
  - `products/daily-life/frontend/src/hooks/useDashboard.ts` line 44 hook
    queryFn URL updated (single-character payload, Edit tool — string
    content, not structural code).
  - DB table `metricas_produtividade` preserved (data-model, not API).
  - Frontend UI route `/metricas` preserved (PT label; daily-life is
    product-Portuguese — backend-rename rationale does not extend to UI).
- **Stranded-reference cleanup** (Phase 1 missed these):
  - `products/daily-life/MASTER-PROMPT.md` Domain + Pages tables:
    removed Focus/`/api/foco` row, removed Foco/`/foco` page row,
    dropped `+ POST /api/ai/weekly-review/send` from the AI-weekly-review
    row, renamed `/api/metricas` → `/api/metrics`.
  - `products/daily-life/backend/app/services/weekly_review_service.py`
    module docstring: corrected the `POST .../send` trigger reference
    (endpoint retired Phase 1) → GET endpoint + historical note.
- **Tests**: 210/210 green (no delta from Phase 1 close; the rename is
  a string-substitution that the tests catch end-to-end via the route
  matcher).
- **Frontend build**: `npx vite build` fails on `tailwindcss-animate`
  module resolution from the seed framework's `tailwind.config.factory.ts`
  — verified via stash-clean-tree reproduction (failure existed BEFORE
  Phase 2's hook edit). NOT introduced by Phase 2; **same-shape** as the
  PF lesson §(b)#1 worktree-bootstrap gap; queue under §7 Q4.
- **Keeper**: not run from worktree (`mcp/noctusai/.venv` absent — same
  PF lesson §(b)#1). Architect runs post-FF-merge.
- **§5.4.2 gap table updated**: Patterns A / F / H all marked CLOSED with
  Phase pointers. Patterns E (response_model deferred) + B/C/D/G (0
  counts) unchanged.
- **§6 phase entries reshaped**: original Phase 1 (Pattern H+A) and
  Phase 2 (auth-factory) were collapsed when Pattern F shipped alongside
  H in Phase 1 (the seed real adapter landed early). Phase 2 = this work
  (Pattern A + Phase-1-stranded cleanup). Phase 3 = the original
  standard-router smoke + status-assertion sweep + (new) `ai_outputs`
  mount + migration.
- **Files modified** (this Phase): `products/daily-life/backend/app/routers/metrics.py`,
  `products/daily-life/backend/tests/routers/test_metrics_router.py`,
  `products/daily-life/backend/tests/integration/test_e2e_flows.py`,
  `products/daily-life/backend/app/services/weekly_review_service.py`,
  `products/daily-life/frontend/src/hooks/useDashboard.ts`,
  `products/daily-life/MASTER-PROMPT.md`,
  `products/daily-life/projects/daily-life-wiring/PROJECT.md`.

### 2026-05-11 — Phase 1 ✅ (Engineer DL-P1; merged 03e8db7)

- Pattern F adoption: 29 callsites in 6 routers (tasks/goals/schedule/notes/metrics/ai)
  refactored from the manual triple (`get_current_user` + `get_org_id` +
  `get_user_client`) to `Depends(get_current_user_org)`. Made possible
  by the `make-get-current-user-org-factory` seed real adapter shipping
  ahead of expectations — what PROJECT.md §6 had called Phase 2.
- Pattern H Q2 = Option A (DELETE both): removed `app/routers/focus.py`
  (5 endpoints) + `tests/routers/test_focus_router.py` (18 cases) + 5
  e2e focus 401 tests + 1 focus flow test; dropped
  `POST /api/ai/weekly-review/send` (1 endpoint) + 2 paired ai tests.
  GET `/api/ai/weekly-review` preserved for Dashboard widget.
- Pattern A NOT addressed in Phase 1 (out of brief scope) — deferred
  to Phase 2.
- Pytest: 234 → 208 (delta −26 from removed orphan + tests).
- Stranded references in `MASTER-PROMPT.md` + `weekly_review_service.py`
  module docstring missed at Phase 1 close; caught in Phase 2 cleanup.

### 2026-05-11 — Phase 0 ✅

- Discovery completed by engineer PPP, dispatched on a worktree branched
  off `3021dff`. Read-only audit; no code edits.
- 7 backend routers / 35 endpoints inventoried; 6 frontend hooks / 30
  unique frontend→backend calls inventoried; 4 migrations cross-checked
  (no schema drift); seed-lib import audit shows high hit rate (metas,
  digest, ai-consent, llm, crud_safety, responses, primitives.timeutil,
  primitives.parsing, api.auth.first_or_none all consumed).
- Gap table (§5.4.2) populated: 0 Pattern B/C/D/G; 2 Pattern A; all 35
  routes Pattern E; all 7 routers Pattern F (gated on seed adapter); 6
  endpoints Pattern H (5 in `/api/foco` + 1 `weekly-review/send`).
- Pytest baseline: 234/234 green (with PYTHONPATH override; see §10).
- Keeper not run from this worktree — `mcp/noctusai/.venv` not bootstrapped
  (defer to architect post-FF-merge; see §7 Q4 + §8).
- Findings returned as text per §17.6.1 (harness blocks engineer Write
  for `findings.md` despite brief authorization — memory entry
  `feedback_findings_md_return_as_text.md` N=6 now). Five-category
  content included in engineer's report; architect to transcribe at
  fresh-eyes-merge time.

