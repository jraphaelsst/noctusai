# YouTube Crawler Wiring — Project Document

> **This is a living document, not a rigid checklist.**
> Revise phases, fold in optimizations, update §11 Change Log as work
> progresses. See `CLAUDE.md → §1 Universal rules → No incomplete commits /
> Estimate off evidence / Replication-to-seed symmetry` and
> `KB § PATTERNS/project-execution.md`.
>
> **Slug rationale.** Mirrors the sister `*-wiring` projects
> (`personal-finance-wiring` closed; `therapy-platform-wiring`,
> `erp-wiring`, `mailing-wiring`, `daily-life-wiring`,
> `media-scheduling-wiring` in flight): a discovery + gap inventory of every
> `youtube-crawler` surface end-to-end, closing every gap at the layer it
> belongs to (seed vs. product). Intent = `wiring` per
> `KB § PATTERNS/project-execution.md §8`.
>
> **Honest-scope note.** `youtube-crawler` is **the seed reference product**
> per `products/youtube-crawler/MASTER-PROMPT.md` — "the spine with no
> organs." `templates/product-seed/` auto-syncs from this product. The wiring
> sweep is therefore unusually small by design: every gap surfaced here is
> almost always a seed-side gap (because the consumer surface IS the seed
> reference), not a product-domain gap. Phase 0 confirms this hypothesis.

- **Created:** 2026-05-11
- **Last updated:** 2026-05-11 (Phase 0 ✅ — discovery + gap inventory)
- **Status:** ⏳ **Phase 0 ✅ — awaiting "continue" before Phase 1.**
  Discovery pass complete; §5.4 populated; §6 phases rewritten from concrete
  gap data; §7 design batch surfaced. Per the project's pause-after-each-phase
  cadence, awaiting user signal before Phase 1 dispatch (if any).
- **Owner / stakeholders:** Raphael (joaoraphaelsst@gmail.com) · Claude Opus 4.7
- **Related docs:**
  - `products/youtube-crawler/MASTER-PROMPT.md` — agent-facing product contract
  - `products/youtube-crawler/README.md` — product overview
  - `templates/product-seed/` — template auto-synced from this product
  - `archive/projects/2026-05-11/16-personal-finance-wiring/personal-finance-wiring-lessons.md` — sister-project lessons (pre-reading for Phase 1+ if any)
  - `products/erp-imobiliario/projects/erp-wiring/PROJECT.md` — sister project, same Phase 0 shape (larger product)
  - `products/mailing/projects/mailing-wiring/PROJECT.md` — sister project, same Phase 0 shape (smaller product)
  - `products/daily-life/projects/daily-life-wiring/PROJECT.md` — sister project
  - `KB § PATTERNS/project-execution.md` — cadence, slug naming, tests-with-code
  - `KB § PATTERNS/proposals-and-improvements.md` — phase-end protocol
  - `KB § PATTERNS/database-rls.md` — migration discipline (`youtube_crawler` schema)
  - `KB § PATTERNS/lgpd.md` — personal-data guardrails (N/A at this product surface today — no domain PII)
  - `CLAUDE.md § Universal rules` — loaded every session
- **Project slug:** `youtube-crawler-wiring`
- **Lives at:** `products/youtube-crawler/projects/youtube-crawler-wiring/`

---

## 1. Context & Purpose

`youtube-crawler` is **the smallest product in the platform** per
`KB § 02-LANDSCAPE.md` and the canonical seed reference product per
`products/youtube-crawler/MASTER-PROMPT.md`. It has:

- **0 product-side routers** (`app/routers/` contains only `__init__.py`).
- **0 product-side services** (`app/services/` contains only `__init__.py`).
- **0 product-side schemas** (`app/schemas/` contains only `__init__.py`).
- **0 frontend hooks** (no `frontend/src/hooks/` directory exists).
- **0 frontend components** (no `frontend/src/components/` directory exists).
- **3 backend standard routers** mounted via the seed factory:
  `standard_routers=["health", "notificacoes", "team"]` at `app/main.py:35`.
- **7 frontend pages** — 6 seed-reference shells (Landing, Login,
  AcceptInvite, ForgotPassword, Dashboard, NotFound) + Equipe (the only
  product-mediated UI calling `/api/team*`).
- **2 SQL migrations** — `001_seed.sql` (status_pagina + invitations) +
  `002_invitations_accepted_columns.sql` (lockstep with seed's
  `accept_invitation` real adapter, 2026-05-11).
- **31 backend tests passing** — every single test inherits from
  `noctusai_lib.testing.*` suites (HealthCheckSuite, TeamRouter*Suite,
  FrameworkEndpointsSuite, TeamFlowSuite, NotificationFlowSuite,
  AuthBoundarySuite). Zero copy-pasted product test code.

**Sister-project sizing for comparison:**

| Product | Routers | Endpoints | Hooks | Pages | Migrations | Tests |
|---|---|---|---|---|---|---|
| `erp-imobiliario` | 60 | 321 | 65 | 67 | 29 | 1901 |
| `mailing` | 10 | 60 | 8 | 21 | 4 | (per project §5.4) |
| `youtube-crawler` | **0** | **0** | **0** | **7** | **2** | **31** |

The win looks like: every navigable page in `youtube-crawler` loads with a
200 (Landing public, Login, AcceptInvite, ForgotPassword, Dashboard, Equipe,
NotFound), the 3 seed-mounted standard routers respond correctly,
`pytest products/youtube-crawler/backend/` is green (already true), and
every Phase 0-surfaced gap is either closed inline OR routed to a
seed-side follow-up (because the product surface IS the seed reference).

**Pattern A=0 hypothesis confirmed.** This product carries no business-domain
routes today — only seed-mounted standard routers. No EN/PT split exists to
audit. Most Pattern-shape findings are N/A because the product has no
domain code.

---

## 2. Confirmed constraints

User answers captured during interrogation. **Future agents inherit the
reasoning, not just the outcome.** Inherits the sister-project methodology —
PF + therapy carry-forward unless flagged below.

### 2.1 Inherited from `personal-finance-wiring` / `therapy-platform-wiring`

- **Scope breadth — widest (A ⇒ B ⇒ C).** Fix known regressions, sweep the
  user-facing surface end-to-end, close pre-existing scaffolding debt. For
  this product, "scaffolding debt" mostly means **seed-side** gaps — see §3a.
- **Tests** — three-layer discipline per `KB § PATTERNS/testing.md`. Not a
  per-phase decision. The current 31-test corpus is 100% framework-inherited
  (`noctusai_lib.testing.*`); no copy-pasted shapes to absorb.
- **Cadence** — phase-by-phase, pause after each, no auto-advance.
- **Seed sync** — patterns worth promoting mid-project land as phase-end
  proposals via `noctus.dev.file_proposal(project="youtube-crawler-wiring", …)`.
- **Triage at decision time** — every divergence lands on
  `formalize / refactor / accept-with-rationale`.
- **Commit + push only your own work.** Per-phase local commit; final commit
  + push at project close.
- **Verify-the-seed-ships-it test** fires at every absorption decision (PF
  Phase 1 lesson).

### 2.2 YouTube-Crawler-specific

- **This product IS the seed reference.** Per `MASTER-PROMPT.md`, this
  product has ZERO domain code by design. `templates/product-seed/` syncs
  from this folder via post-commit hook. **Adding domain code here changes
  the template downstream** — Phase 1+ must surface every "product-side"
  change as a seed-template-shape question first.
- **Schema name** — `youtube_crawler` (snake_case). Standard pattern.
- **`002_invitations_accepted_columns.sql`** — lockstep with seed's
  `accept_invitation` real adapter (Phase 2 of `seed-team-router-accept-real-adapter`,
  2026-05-11). Cross-product migration sibling — verified present in PF +
  mailing + therapy too.
- **APScheduler** — Not used. No `noctusai_lib.api.scheduler` consumer here.
- **Webhook receiver** — Not used today. Seed ships a canonical reference
  via `products/seed/backend/app/routers/webhook_router.py` per
  `feedback_webhook_verify_before_side_effect`. Not adopted in this product.
- **AI features** — None registered. `consent_features=...` is commented out
  in `app/main.py:38-39` per the MASTER-PROMPT shape. If AI features land
  here, the consent catalog goes in `app/services/ai_consent_features.py`.
- **No `useQuery` / `useMutation` / `useQueryClient` anywhere.** Phase 0 grep
  returned 0 occurrences. The single product-mediated UI (Equipe) uses
  `api.get/post/delete` from `@noctusai/seed/infra` directly — synchronous
  `useEffect`+`useState` flow.
- **No raw `fetch(/api/...)`.** Phase 0 grep returned 0 occurrences. All
  HTTP goes via the seed-provided `api` client.
- **No `supabase.from()` or `supabase.functions.invoke()` bypass hooks.**
  Phase 0 grep returned 0 occurrences. Pattern D therefore = **0**.

---

## 3. Design principles

How we're approaching *this specific problem* on top of platform-wide
`CLAUDE.md` rules.

1. **The seed IS the product.** Per MASTER-PROMPT, every change here is
   structurally a seed change. Any "wiring" gap surfaced should resolve at
   the seed layer first (the consumer is also the seed reference). N=2+
   recurrence rule fires INSTANTLY because the consumer IS one of N+1.
2. **No band-aids.** No `?? ''` guards to tolerate bad DTOs. (No domain
   DTOs exist today — N/A.)
3. **LGPD-first on every personal-data endpoint.** This product touches
   only `auth.users` (via team router) and the seed-shipped `invitations`
   table. No domain PII surfaces. **LGPD scan = clean.**
4. **Migrations and applied SQL stay in lockstep.** 002 already lockstep
   per §2.2. Next free slot = **003**.
5. **Tests land in the same phase as the code.** 31 tests already pass via
   inheritance from `noctusai_lib.testing.*`. No copy-pasted shapes here.
6. **Discovery is an artifact, not a vibe.** §5.4 below.
7. **Status-code-assertion rule (PF retro §b.3)** — N/A for this corpus
   because all tests inherit from `noctusai_lib.testing.framework_test_suites`,
   which already encodes the rule at the seed layer.

---

## 3a. Seed-first analysis (REQUIRED — the seed is every product's skeleton)

Six-question checklist per `KB § GUIDES/seed-first-design.md`:

1. **Is the contract identical for every product?** **YES.** Every surface
   in this product comes from the seed — there is no product-domain
   contract that differs.
2. **Is the data source product-specific?** **MIXED.** The two
   product-schema tables (`youtube_crawler.status_pagina`,
   `youtube_crawler.invitations`) live in the product's schema but mirror
   the seed shape — they're the seed-shipped pair that every product
   inherits via 001_seed.sql.
3. **Is the placement product-specific?** **NO.** Every file in this
   product is the seed shape: `main.py` 19 lines, `App.tsx` 73 lines,
   `Dashboard.tsx` is the seed-reference status card.
4. **Is the visibility / permission rule the same?** **YES.** Pure org-scoped
   via the seed-mounted team router. No bespoke role-gating.
5. **Does the seam already exist in seed?** **YES — all of them.**
   - `create_product_app` ✅
   - `create_database_module` + `create_dependencies` ✅
   - `make_get_current_user_org` (canonical factory) ✅ — wired at
     `app/dependencies.py:35-39`. **This product is the canonical adopter
     of the PF-filed `make-get-current-user-org-factory` follow-up.**
   - `noctusai_lib.primitives.responses` ✅ — re-exported via
     `app/responses.py`
   - `noctusai_lib.api.auth.first_or_none` + `resolve_sso_role` ✅
   - `noctusai_seed.rate_limit.create_product_limiter` ✅
   - `noctusai_lib.testing.*` suites ✅ — 100% test coverage via inheritance
   - `@noctusai/seed/infra` ✅ — `useAuthStore`, `supabase`, `api`
   - `@noctusai/seed` `createProductApp` + `createProductLayout` ✅
   - `@noctusai/lib` `LoginForm`, `AcceptInvitePage`, `resolveSSOContext` ✅
6. **Default-on or opt-in?** **DEFAULT-ON** across the board. `standard_routers=["health", "notificacoes", "team"]` at `app/main.py:35`.

**Litmus — per-product code count this design requires:**

- [x] **0 lines** for cross-product concerns. **CONFIRMED at the byte level
  for this product.**
- [x] **A small section** for product-specific wiring. **None today —
  by design.** If a Phase 1+ surfaces a need, it's a seed-template
  question first.
- [x] **Multiple files / pages / mounts per product** — none planned. If a
  Phase surfaces this shape, STOP and re-design.

**Phase plan implications:** §6 phases are largely vacuum-cleanup or
seed-side follow-ups. The product itself has no scaffolding debt that
isn't already a seed-shape question. **Phase 1 may be a no-op
("project closes after Phase 0") depending on user signal.**

---

## 4. Scope

**In scope:**

- Every `youtube-crawler` backend mount that a frontend page reaches —
  inventory in §5.4.
- Every `youtube-crawler` migration needed to close column drift
  (§5.4.5 — **none found at Phase 0**).
- Seed-side absorption candidates whose N≥2 elsewhere flips to N=3 with
  this product as a consumer — though for this product, every cross-cutting
  seam is already adopted by design (§3a Q5).
- Frontend corrections to consume corrected DTOs or fix UI bugs uncovered
  during sweep.
- Tests (unit + router + integration) landing in same phase as code.
- LGPD awareness via `noctus.dev.lgpd_flag` where endpoints aggregate PII
  in new shapes — **N/A** at current surface.
- End-to-end verification: `vite build` + `pytest` + manual browser QA of
  the 6 navigable pages.
- **Template-sync awareness** — any change to `products/youtube-crawler/`
  propagates to `templates/product-seed/` via post-commit hook. Phase 1+
  decisions must consider downstream template effect.

**Out of scope (for now — with reason):**

- **Other products** — separate `*-wiring` projects (PF closed; therapy /
  ERP / mailing / daily-life / media-scheduling in flight).
- **Adding domain features to youtube-crawler** — this is the seed
  reference; new domain code belongs in a different product OR lands at
  the seed first.
- **YouTube data ingestion features** — the product NAME implies a future
  YouTube ingestion capability; today the product is a pure seed
  reference. Domain expansion = separate project.
- **Vista / WhatsApp / Resend / Stripe** — not used here.

---

## 5. Architecture / Data Model

*§5.1-5.3 are placeholders. §5.4 is the Phase 0 deliverable, populated below.*

### 5.1 Shared `make_get_current_user_org` adoption *(already adopted)*

**Status:** ✅ adopted at `app/dependencies.py:35-39` per the late-binding
lambda pattern (closure re-resolves on every request — required so test
patches on `_db.get_client` reach call sites). This product is the
canonical adopter shape for the seed factory.

### 5.2 AI plumbing wrappers adoption *(N/A)*

No AI features registered. `consent_features=...` is commented out in
`app/main.py:38-39`. When AI features land here, the wrappers
(`safe_persist_indicator`, `require_credential_or_422`,
`check_openai_configured`) get consumed from the seed-side absorption
candidate.

### 5.3 Metas / Scheduler / Digest adoption *(N/A)*

No metas, no scheduler, no digest service in this product. The seed
primitives exist (`noctusai_lib.domain.metas`, `noctusai_lib.api.scheduler`,
`noctusai_lib.domain.digest.BaseDigestService`) — consumed by other products,
not here.

### 5.4 Inventory *(populated 2026-05-11 by Phase 0 — Engineer UUU)*

#### 5.4.1 Headline counts

| Surface | Count |
|---|---|
| Backend product routers | **0** (`app/routers/` has only `__init__.py`) |
| Backend product services | **0** (`app/services/` has only `__init__.py`) |
| Backend product schemas | **0** (`app/schemas/` has only `__init__.py`) |
| Backend product endpoints | **0** product-side; **3 standard routers** mounted via seed factory (`health`, `notificacoes`, `team`) |
| Backend migrations | **2** (`001_seed.sql`, `002_invitations_accepted_columns.sql`; next free slot = **003**) |
| Migration table count | **2** (`youtube_crawler.status_pagina`, `youtube_crawler.invitations`) |
| Frontend hooks | **0** (no `frontend/src/hooks/` directory) |
| Frontend components | **0** (no `frontend/src/components/` directory) |
| Frontend pages | **7** (Landing, Login, AcceptInvite, ForgotPassword, Dashboard, Equipe, NotFound) |
| Frontend pages with **direct** `useQuery`/`useMutation` (Pattern D) | **0** |
| Frontend pages hitting `/api/` via seed `api` client | **2** (`Equipe.tsx` × 5 calls; `AcceptInvite.tsx` × 1 via `AcceptInvitePage` component prop) |
| Raw `fetch()` outside auth/api wrappers | **0** |
| Unique frontend → backend API paths surveyed | **5** (`/api/team`, `/api/team/invitations`, `/api/team/invite`, `/api/team/{id}`, `/api/team/invitations/{id}`, `/api/team/accept`) — all on the seed-mounted `team` standard router |
| Direct `supabase.from(...)` reads (Pattern D-variant) | **0** |
| Direct `supabase.functions.invoke(...)` | **0** |
| Backend routers with `response_model` declared | **0/0** — N/A, no product routers exist; standard routers' contract is the seed's responsibility |
| Pytest baseline | **31 collected, 31 passed, 0 skipped, 0 failed (1 warning)** — green |
| Keeper review | **0 issues, 0 proposals** — clean bill |

#### 5.4.2 Systemic findings *(7 Pattern shapes A-G + PF-lessons H)*

**Pattern A — Portuguese ↔ English path mismatches: 0 occurrences (expected).**

This product carries no business-domain routes — only the 3 seed-mounted
standard routers (`/api/health`, `/api/notificacoes`, `/api/team`). The PT
prefix (`notificacoes`) is the seed standard; the EN prefixes (`health`,
`team`) are seed standards too. **No EN/PT split exists at this product
surface.** Verified via `grep -rE "'/api/" frontend/src/` returning only
`/api/team*` paths.

**Pattern B — Admin namespace not split: 0 occurrences.**

No bespoke admin gate exists. All role-gating defers to the seed's
`team` router's RLS + JWT shape (admin/owner/member). The Equipe page's
`isAdmin` computation (`ssoCtx.isProductAdmin || ssoCtx.org.role === "owner" || ssoCtx.org.role === "admin"`) is the seed's `resolveSSOContext`
shape, not a product-bespoke gate.

**Pattern C — Detail endpoints missing: 0 occurrences (N/A).**

No product detail-endpoints exist. The 5 `/api/team*` calls all resolve
to the seed-mounted team router which carries the full CRUD.

**Pattern D — Direct-fetch / supabase.from() bypass: 0 occurrences.**

| Hook | Bypass shape | Should route through |
|---|---|---|
| _(none)_ | _(none)_ | _(none)_ |

`grep -rnE "supabase\.from|supabase\.functions|fetch\(" products/youtube-crawler/frontend/src/`
returned 0 matches. **Cleanest product surface in the platform on this
axis.**

**Pattern E — Implicit DTO contract: N/A.**

0 product routers exist → `response_model` audit is a null query. The 3
seed-mounted standard routers ship their own DTO discipline; auditing
their `response_model` adoption is a seed-side concern, not a
youtube-crawler-wiring concern.

**Pattern F — `require_role` recurrence inside this product: 0 occurrences.**

No `require_role` re-implementation; no inline `if role not in (...)` check.
The product uses the seed's `make_get_current_user_org` factory and defers
role checks to the standard routers. **Cleanest product surface in the
platform on this axis.**

**Pattern G — Path-shape mismatches inside clusters: 0 occurrences (N/A).**

No path clusters exist at this product — only 5 paths total, all on the
seed-mounted team router with the canonical RESTful shape
(`/api/team`, `/api/team/{id}`, `/api/team/invite`, etc.). No
nested-vs-flat mixing.

**Pattern H — Orphaned hooks (PF lessons §b.2): 0 occurrences (N/A).**

No hooks exist (`frontend/src/hooks/` does not exist). Pattern H is a
hook-orphan detector and there is nothing to detect. **Cleanest product
surface on this axis too.**

**Pattern aggregate: A=0 / B=0 / C=0 / D=0 / E=N/A / F=0 / G=0 / H=0.**
The only Pattern surface with content is the seed-mounted standard routers
themselves, which are the seed's responsibility — not a wiring-project
deliverable.

#### 5.4.3 Per-router endpoint distribution

N/A — 0 product routers. The 3 seed-mounted standard routers
(`health`, `notificacoes`, `team`) have their endpoint distribution
documented in the seed framework itself
(`seed/framework/backend/noctusai_seed/`), not at the product layer.

#### 5.4.4 Backend orphans (no surveyed frontend caller)

N/A — no product routers exist to be orphaned. The Equipe page (the
only product-mediated UI) consumes the seed-mounted team router.

#### 5.4.5 Migration column gap

**Cross-checked all 2 tables in `migrations/001..002.sql` against
`.table("<name>")` calls.**

| Code-referenced table | In youtube-crawler migrations? | Notes |
|---|---|---|
| `status_pagina` | ✅ present (001) | Seed-shipped table; consumed by seed framework |
| `invitations` | ✅ present (001 + 002 column additions) | Seed-shipped; 002 adds `accepted_at` + `accepted_by` lockstep with seed real adapter |

**No drift found.** **No service-layer `.table(...)` calls exist** because
`app/services/` is empty. Migration discipline is clean.

`grep -rE "service_role_bypass" products/youtube-crawler/backend/migrations/`
returned 0 matches — these tables predate the service_role_bypass backfill
project but are seed-shipped + don't need bypass at this product. **Surface
to user for triage:** if all `*_invitations` tables across the platform
need service_role_bypass for parity with mailing/ERP/PF, the
youtube-crawler 001 + 002 may need a sister 003 migration. **Default rec:
defer to seed-side audit** — the seed is the canonical owner of the
invitations table shape.

#### 5.4.6 Should-use-seed candidates *(adoption table)*

Audited via `grep -rE "from noctusai_(lib|seed)" products/youtube-crawler/backend/`
— **13 imports across 7 files.** Adoption is essentially complete by
design (this product IS the seed reference).

| Seed module | Imports | Status |
|---|---|---|
| `noctusai_seed` (top-level — `create_product_app`, `create_database_module`, `create_dependencies`, `ProductSettings`, `default_llm_config`) | 5 | Adopted |
| `noctusai_lib.api.auth` (`first_or_none`, `make_get_current_user`, `make_get_current_user_org`, `resolve_sso_role`) | 1 | Adopted (canonical adopter shape) |
| `noctusai_seed.rate_limit.create_product_limiter` | 1 | Adopted |
| `noctusai_lib.integrations.llm.chat_completion` | 1 | Documented in `main.py` docstring (not invoked — no AI features today) |
| `noctusai_lib.primitives.responses` | 1 | Re-exported via `app/responses.py` |
| `noctusai_lib.testing` (HealthCheckSuite, TeamRouter*Suite, FrameworkEndpointsSuite, TeamFlowSuite, NotificationFlowSuite, AuthBoundarySuite, MockSupabaseClient, MockUser, AuthClient, etc.) | 4 | **100% test-corpus inheritance** — 31 tests, 0 copy-pasted shapes |

**Absorption candidates whose N≥2 elsewhere flips to N=3 with this
product as a consumer:** **none new today.** Every cross-cutting seam this
product *could* consume is already adopted — the product IS the seed
reference, so by construction it leads adoption rather than lagging it.

**Sister-project N-counts for context:**

- `make_get_current_user_org`: PF + ERP + youtube-crawler = **N=3 already**
  (the PF-filed `make-get-current-user-org-factory` follow-up has 3
  consumers including this product). Therapy adoption flips to N=4.
- `noctusai_lib.testing` framework-test suites: this product +
  PF + ERP + therapy + mailing + daily-life adoption brings the N=4
  byte-identical baseline that lifted the suites to N=5+. **This product
  is the cleanest demonstrator** — 100% test inheritance, zero shadows.

#### 5.4.7 Deletion-candidate batch *(none surfaced)*

No orphan hooks, no dead routes, no unused services. The 7 pages are
all navigable from the navbar / login flow. The 2 migrations are both
load-bearing.

#### 5.4.8 Test coverage

- **31 collected, 31 passed, 0 skipped, 0 failed (1 PendingDeprecationWarning from starlette)** at Phase 0 close.
- Coverage spans:
  - `tests/routers/test_health.py` → `HealthCheckSuite` (inherited)
  - `tests/routers/test_team_router.py` → `TeamRouterListMembersSuite` + `TeamRouterInviteSuite` + `TeamRouterRemoveMemberSuite` (inherited)
  - `tests/integration/test_e2e_flows.py` → `FrameworkEndpointsSuite` + `TeamFlowSuite` + `NotificationFlowSuite` + `AuthBoundarySuite` (inherited)
- **PF Phase 7 lesson §d.4 — standard-router smoke per product:** ALREADY
  HELD. `main.py:35` mounts `standard_routers=["health", "notificacoes", "team"]`
  → all 3 have inherited smoke suites at `tests/routers/`. **No gap.**
- **PF Phase 0 lesson §b.3 — status-code-assertion calibration:** N/A.
  The framework-test suites encode status-code assertions at the seed
  layer; product-side tests are 100% inherited. No drift possible.

#### 5.4.9 Keeper review pass

```
python mcp/noctusai/cli.py --review --product youtube-crawler --worktree-path "$PWD"
```

Run 2026-05-11 — **0 issues, 0 proposals filed.** Result: clean keeper
bill of health.

---

## 6. Implementation phases

Phases are **suggestive, not strict.** Reorder, split, merge, or discover
new phases as work progresses. **For this product specifically, Phase 1+
may be a no-op** — the gap inventory is empty.

**Phase status-icon convention** (per `KB § PATTERNS/project-execution.md §1`):

| Icon | Meaning |
|---|---|
| _(none)_ | Pending — not started |
| ⏳ | In progress / partially done |
| ✅ | Complete — every sub-task ticked |
| ❌ | Blocked or failed — see Change Log |

**Improvement capture happens during steps. Proposal authoring happens at
end of phase.** One bundled proposal per phase, filed via
`noctus.dev.file_proposal(project="youtube-crawler-wiring", worktree_path="$PWD", …)`.

---

### Phase 0 — Discovery & inventory ✅ *(2026-05-11)*

Produced the concrete gap table in §5.4. Every subsequent phase (if any)
references rows from this table — no phantom scope.

- [x] **0.a — Backend route inventory:** confirmed `app/routers/` /
  `app/services/` / `app/schemas/` all contain only `__init__.py`. **0
  product-side routers / 0 endpoints.** Standard routers mounted via
  `create_product_app(..., standard_routers=["health", "notificacoes", "team"])`
  at `app/main.py:35`.
- [x] **0.b — Frontend hook + page inventory:** **0 hooks** (no
  `frontend/src/hooks/` directory), **0 components**, **7 pages**. Surveyed
  HTTP calls via `grep -nE "supabase\.from|supabase\.functions|fetch\(|api\.(get|post|put|patch|delete)" products/youtube-crawler/frontend/src/`
  → 5 `api.*` calls in `Equipe.tsx` + 1 endpoint prop in `AcceptInvite.tsx`.
  **0 raw fetch, 0 supabase bypass.**
- [x] **0.c — Gap table (7 Pattern shapes A-G + PF lessons §b.2 Pattern H):**
  captured in §5.4.2. **Pattern counts: A=0 / B=0 / C=0 / D=0 / E=N/A / F=0 / G=0 / H=0.**
  Cleanest pattern surface on the platform.
- [x] **0.d — Migration column cross-reference:** parsed `CREATE TABLE`
  statements across 2 migrations (2 tables). **0 service-layer `.table(...)`
  calls** because `app/services/` is empty. **Zero migration drift.** §5.4.5
  surfaces one user-triage Q: should youtube-crawler `*_invitations` carry
  a sister `service_role_bypass` migration for parity? **Default rec: defer
  to seed-side audit.**
- [x] **0.e — Seed-lib export catalog inheritance:** `grep -rE 'from noctusai_(lib|seed)' app/` →
  13 imports across 7 files; table in §5.4.6. **100% test-corpus inheritance
  via `noctusai_lib.testing.*` suites.** No absorption candidates surfaced;
  this product is canonical adopter, not laggard.
- [x] **0.f — Phase 0 deliverable:** PROJECT.md §5.4 populated; §6 phases
  promoted; §7 design batch surfaced (3 Q items); §11 first entry below.
- [x] Pytest baseline confirmed green: **31 collected, 31 passed, 0 skipped, 0 failed**.
- [x] Keeper review: **0 issues**.

**Deliverable produced:** §5.4 populated (5.4.1 counts → 5.4.9 keeper);
phases 1-3 carry concrete (mostly no-op) work items; design-batch surfaced
in §7 (3 Qs) for user sign-off.

#### Phase 0 → §7 design-batch handoff

Three design questions surfaced. All carry default recommendations; surface
as one batch before Phase 1 (or before deciding "project closes after
Phase 0").

- §7 Q-A — service_role_bypass parity migration for `youtube_crawler.invitations` + `status_pagina`. Default rec: **DEFER to seed-side audit** (the seed owns the canonical shape; cross-product parity is a seed concern).
- §7 Q-B — Project scope after Phase 0: close-as-no-op vs. seed-side follow-up phase. Default rec: **close as no-op** — no product-side wiring gaps surfaced; any work belongs in seed-side projects (already filed: `make-get-current-user-org-factory`, `ai-plumbing-seed-absorption`, `phase-5-scheduler-standard-router`).
- §7 Q-C — Template-sync awareness for future product growth (when YouTube ingestion features land, do they expand this product or fork to a new one?). Default rec: **fork to new product** (`youtube-ingest` slug) to preserve youtube-crawler as the seed reference. Decided by: user, before any domain code lands here.

**Improvements:** none filed as a separate proposal. Captured inline in
§5.4.2 Patterns A-H — the gap table itself is the Phase 0 artifact. Per
sister-project pattern.

---

### Phase 1 — Seed-side absorption batch *(likely no-op for this product)*

Mirrors PF Phase 1 shape. For this product specifically, **every seam is
already adopted** (§3a Q5 + §5.4.6). Phase 1 may collapse into a close-out
checklist:

- [ ] **Verify `make_get_current_user_org` adoption is the canonical shape.** Already wired at `app/dependencies.py:35-39` per the late-binding lambda pattern. Phase 1 checkpoint: cross-reference with sister adopters (PF + ERP + therapy) for shape uniformity.
- [ ] **Verify `noctusai_lib.testing.*` suites stay in sync.** `tests/routers/test_health.py` + `tests/routers/test_team_router.py` + `tests/integration/test_e2e_flows.py` — these MUST stay as pure inheritance shells (no overrides). Phase 1 checkpoint: assert via grep.
- [ ] **service_role_bypass parity migration for `youtube_crawler.status_pagina` + `invitations`** (per §7 Q-A). Default: DEFER to seed-side audit; flag the decision.
- [ ] **Status-code-assertion baseline** — N/A (100% inherited). Phase 1 checkpoint: confirm no `tests/` file overrides a parent method with a status-less assertion.
- [ ] Phase-1 proposal filed via `noctus.dev.file_proposal` (likely "none identified" note).

### Phase 2 — Project close

- [ ] Sister-project lessons retro at `archive/projects/<YYYY-MM-DD>/<seq>-youtube-crawler-wiring/youtube-crawler-wiring-lessons.md`.
- [ ] **Key retro point:** "the smallest product is the cleanest" — every Pattern N=0 outcome at §5.4.2 is structural evidence that the seed-first methodology compounds (this product inherits everything; there are no consumer-side forks because the consumer IS the seed reference).
- [ ] FF-to-main per `feedback_orchestrator_role` final-step rule.

---

## 7. Open questions

Unresolved items. Each tagged with *when it needs an answer* and *who answers*.

### Design batch from Phase 0 discovery *(surfaced 2026-05-11)*

**Q-A — `service_role_bypass` parity migration for `youtube_crawler.invitations` + `status_pagina`.** *(Project-level scope decision.)* — **DEFAULT REC:** DEFER to seed-side audit. The seed owns the canonical invitations + status_pagina table shape; cross-product parity is a seed concern, not a per-product migration. **Surfacing in case user wants to bring this product to parity with mailing/ERP/PF — those have `service_role_bypass` policies on their analogous tables per AAA's 2026-05-11 backfill.** Decided by: user.

**Q-B — Project scope after Phase 0: close-as-no-op vs. seed-side follow-up phase.** *(Project-level scope decision.)* — **DEFAULT REC:** CLOSE as no-op after Phase 1 verification. No product-side wiring gaps surfaced. Any work belongs in already-filed seed-side projects (`make-get-current-user-org-factory`, `ai-plumbing-seed-absorption`, `phase-5-scheduler-standard-router`). **Alternative:** if user wants to use this project as the umbrella for a youtube-crawler domain expansion (actual YouTube ingestion features), §6 phases rewrite around the new scope. Decided by: user.

**Q-C — Template-sync awareness for future product growth.** *(Project-level / future-design.)* — When YouTube ingestion domain features eventually land, do they expand this product or fork to a new one (`youtube-ingest` or similar)? **DEFAULT REC:** FORK to new product to preserve youtube-crawler as the seed reference. `templates/product-seed/` auto-syncs from this folder; adding domain code here would propagate to every newly-scaffolded product. Decided by: user, before any domain code lands.

### Sub-project gate questions

**Q-1 — Sister `*-wiring` cross-pollination.** *(Phase 1.)* — Should Phase 1 cross-reference findings with the in-flight `erp-wiring` / `mailing-wiring` / `therapy-platform-wiring` / `daily-life-wiring` for an N-count refresh on the absorption candidates table (§5.4.6)? **DEFAULT REC:** YES — quick grep across sister-project §5.4.6 tables to confirm N-counts stay aligned. Decided by: Phase 1 engineer (default-rec-accepted unless user overrides).

---

## 8. Dependencies & blockers

- **Supabase MCP access** — already granted via blanket approval (`feedback_supa_mcp_proactive`).
- **PF follow-up projects (filed, pending)** — `make-get-current-user-org-factory` (3 consumers already incl. this product), `ai-plumbing-seed-absorption`, `phase-5-scheduler-standard-router`, `cross-schema-organization-reach-audit`. None block this product's Phase 1 because it doesn't depend on the deferred work.
- **Sister `*-wiring` projects in flight** — N-count drift on absorption candidates might propagate here. Re-check at Phase 1 kickoff per §7 Q-1.
- **Template-sync hook** — `templates/product-seed/` auto-syncs from `products/youtube-crawler/` on commit. Phase 1+ changes MUST consider template downstream effect.
- **Baseline test stability** — Phase 0 confirmed 31 passed / 0 skipped / 0 failed. Every subsequent phase must not regress this.

---

## 9. Success criteria

- **0 `404`s, 0 `405`s** on every navigable URL (Landing public + Login + AcceptInvite + ForgotPassword + Dashboard + Equipe + NotFound).
- **`pytest products/youtube-crawler/backend/` green** (already true at Phase 0).
- **`npx vite build` clean** for youtube-crawler frontend.
- **No new LGPD warnings** without planned resolution. (None at current surface.)
- **§7 Q-A + Q-B + Q-C answered** by user.
- **Sister-project lessons retro produced at project close.**
- **N=3+ absorption candidates either formalized at seed or filed as follow-up projects** — **already true at Phase 0** for every cross-cutting seam this product consumes.

---

## 10. How to use this project

- **Single source of truth for progress.** Update as work progresses.
- **Live-tick tasks as they complete.** Flip `- [ ]` → `- [x]` immediately and save.
- **Phase-by-phase cadence.** Execute exactly one phase, then pause. Don't auto-advance. User overrides with explicit throughput instructions.
- **Revise phases when reality diverges.** Log the revision in §11.
- **Commit project changes with the code.** PROJECT.md evolves in the same commit as the phase's implementation.
- **Interrogate before designing revised phases.** Ask if a phase needs a scope call.

### Verification commands *(run at end of every phase)*

```bash
# Frontend build
cd products/youtube-crawler/frontend && npx vite build

# Backend tests
cd products/youtube-crawler/backend && \
  /Users/rapha/Documents/repository/NoctusAI/noctusai/venv/bin/python -m pytest tests/ -q

# Seed tests (Phase 1 if any seed-side change)
cd seed/lib/backend && \
  /Users/rapha/Documents/repository/NoctusAI/noctusai/venv/bin/python -m pytest tests/

# Keeper review pass
/Users/rapha/Documents/repository/NoctusAI/noctusai/venv/bin/python mcp/noctusai/cli.py --review --product youtube-crawler --worktree-path "$PWD"
```

---

## 11. Change log

| Date | Change | By |
|---|---|---|
| 2026-05-11 | Phase 0 ✅ — Discovery & inventory complete. §5.4 populated: 0 product-side routers / 0 endpoints / 0 hooks / 7 pages / 2 migrations baseline; Pattern A=0, B=0, C=0, D=0, E=N/A, F=0, G=0, H=0 — cleanest pattern surface on the platform. Pytest 31 passed / 0 failed. Keeper 0 issues. §6 phases written from concrete data; §7 design batch surfaced (Q-A through Q-C + 1 sub-project gate Q). Project structurally complete after Phase 0 — Phase 1 likely no-op, awaiting user decision on §7 Q-B (close as no-op vs. expand scope). | Engineer UUU (worktree `agent-ab6fb1428ff8fb492`) |
