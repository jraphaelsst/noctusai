# Seed-First Design — How to scope a cross-product project

> A checklist + worked examples for thinking seed-first when planning ANY cross-product feature, before writing a `PROJECT.md` §6 phase plan. Pairs with `KB § PATTERNS/project-execution.md § The replication-to-seed symmetry rule` (the slip-pattern doc) — this guide is the proactive companion: how to design correctly from the start, not how to recognize the slip after the fact.

---

## When to use this guide

**Every project — at AUTHORING time, not at REPAIR time.** The seed is every product's skeleton, so seed-first thinking applies to EVERY project — not just cross-product ones. A single-product project might still have a pattern, component, or helper better placed in seed (so the next product to need it inherits for free). Single-product projects whose answers all point at "product-specific" still run §3a; the conclusion is the explicit confirmation that the design is correctly product-bounded.

Future agents are expected to deliver projects already seed-thought — the user does not refactor projects to apply seed-first thinking after the fact. The first version of every `PROJECT.md` runs this checklist as part of scaffolding (§3a in `templates/PROJECT-TEMPLATE.md`) and records the conclusions visibly in the doc.

Open this guide whenever:

- You are scaffolding a new project of any size or scope.
- You are reading or revising an existing project doc whose §3a is missing or whose §6 phases walk through products.
- You are mid-execution and a phase is about to make the same change to a 2nd product (the language-trigger rule fires; this guide is the corrective).
- You are reviewing another agent's project draft (the §3a entries should be present and reasoned).

**Use BEFORE writing §6.** §6 is the most expensive section to rewrite mid-flight; getting the per-product code count right (zero, almost always for cross-product concerns) before phase planning saves 5-10× the time. **A `PROJECT.md` lacking §3a is a bug, not a feature — even single-product ones.**

**Backfill policy for pre-2026-04-28 projects:** projects drafted before the §3a rule was formalized (2026-04-28) may lack the section. When such a project's execution resumes:

1. **The executing agent backfills §3a as part of Phase 0 audit.** Run the six-question checklist + per-product code-count litmus against the project's §1-§5; record the conclusions in §3a; note the backfill date in §11. This is part of Phase 0; the project is not "ready to execute" without it.
2. If §3a's findings invalidate §6, *expand loudly* per `§ 2.5` — revise §6 inline + log + continue.
3. Inaugural backfill examples (2026-04-28): `repo-state-consolidation` (§3a backfilled inline; analysis: platform-infra git operation, no DRY-into-seed concern), `keeper-phase-state-consistency-detector` (§3a backfilled; analysis: pure platform-infra keeper detector, per-product code = 0).

The backfill policy avoids a one-shot sweep of all pre-existing project files — instead the rule fires when each project's execution resumes. Closed projects (✅ shipped, no future execution) don't need §3a; they're audit history.

---

## The seed-first checklist (six questions)

Walk these in order. Each "no" is a green light to keep going seed-first; the first "yes" tells you what's legitimately product-specific.

### 1. Is the contract identical for every product?

If every product receives the same input, returns the same output, and uses the same protocol — the contract is uniform. Uniform contracts live in seed.

| Yes | No |
|---|---|
| `<AIConsentToggles/>` reads `GET /api/me/consents` (same shape for all products). | A product has different field semantics or a different endpoint. |
| `<PendingConsentBadge/>` shows count from the same response. | Some products have a different "pending" semantics. |
| Auth + routing flows are framework-mediated. | A product has a non-standard auth flow that's incompatible with the framework primitive. |

**If yes:** the consumer (component, hook, page, route, layout slot) is seedable.

### 2. Is the data source product-specific?

Even with a uniform contract, the *data* may be specific. Per-product data → per-product hook & data wiring; the visual *container* can still be seedable.

| Container is seedable | Data wiring stays product-side |
|---|---|
| `<DigestCard title prose feedback />` shape — three slots. | PF's monthly narrative consumes `useMonthlyNarrative`; Daily Life consumes `useWeeklyReview`. |
| `<LineChart data legend />` shape. | Each product passes its own `data`. |

**If yes:** ship the *shape* in seed; let products supply data via props. Per-product code stays minimal (one `<DigestCard prose={data}/>` line, not a re-implementation).

### 3. Is the placement product-specific?

Some surfaces are domain-bound — a campaign-debrief tab lives on `CampaignDetail.tsx` because it's per-campaign; an admin-only audit-digest page lives on `/admin/...` because it's an admin tool.

| Placement is universal (seed) | Placement is product-specific |
|---|---|
| `/settings/ai` (every authenticated user has consents). | `/admin/audit-digest` (Core admin tool). |
| `LayoutEnrichment.aiBadge` (every layout has the slot). | `CampaignDetail.tsx` "Debrief" tab (per-campaign). |
| `/billing` (every paid product surfaces it). | `/comissoes` (ERP-specific business). |

**If yes:** the placement is product-specific, but the *page hosting it* may still consume seed components. Don't conflate.

### 4. Is the visibility / permission rule the same?

If every product gates the surface the same way (admin-only / authed-only / role-X-only), the gate lives in seed. If gates differ, the gate is product-side.

| Gate is uniform (seed) | Gate is product-specific |
|---|---|
| Authenticated users only (default for any framework route). | Therapist-only surface (Therapy role-based routing). |
| Admin role globally. | Specific custom org-roles per product. |

**If yes:** the gate logic + the surface live together in seed.

### 5. Does the seam already exist in seed?

Before building a new seam, check what's already there. Common seams:

| Seam | Lives at | Use for |
|---|---|---|
| `createProductApp(...)` kwargs | `seed/backend/framework/noctusai_seed/app.py` + `seed/frontend/framework/src/app.tsx` | Backend / frontend app factories. New behavior added via a kwarg with safe defaults. |
| `createProductLayout` + `LayoutEnrichment` | `seed/frontend/framework/src/layout.tsx` | Layout-side product config (nav, branding) + layout-bound enrichment hooks (badge slots, theme persistence). |
| `LayoutEnrichment.aiBadge` | header slot | Ambient AI signals (consent pending, spend warning, daily-brief indicator). |
| `noctusai_lib.testing.bind_consent_module_to_mock` etc. | seed-lib testing helpers | Test-side wiring helpers consumable by every conftest. |
| `pytest11` entry-point plugin | `seed/backend/lib/noctusai_lib/testing/pytest_plugin.py` | Auto-loaded test bootstrap (catalog load, environment setup). |
| `noctusai_lib.ai.consent.register_feature` + `consent_required` | seed-lib | Per-feature consent catalog + FastAPI guard. |
| `standard_routers=[...]` | `noctusai_seed.app` | Bundled API routers products opt into. |
| Backend lifespan hooks | `lifespan_startup=`, `lifespan_shutdown=` | Schedulers, recovery tasks, framework cleanup. |

**Always check this list first.** If the seam exists, fill it; don't build a parallel one.

### 6. Default-on or opt-in?

When a feature is universally beneficial (LGPD consent UI, security warnings, accessibility primitives), make it **default-on** in the framework. Products opt OUT explicitly (a single config flag) when they have legitimate reasons.

When a feature is sometimes-applicable (custom branding, product-specific dashboards), it's opt-in.

| Default-on | Opt-in |
|---|---|
| Consent UI auto-mounted at `/settings/ai`. Products pass explicit `null` to opt out. | Custom dashboard widgets — products pass them in. |
| `<NotificationBell/>` in the header. | Per-product navbar items. |
| Audit logging for sensitive actions. | Per-product analytics events. |

**If yes (universally beneficial):** ship default-on. The right per-product code count for cross-product concerns is **zero** — products inherit by virtue of calling the factory.

---

## The litmus test

After running the checklist, count the per-product code your design requires. The answer should be one of:

- **0** — pure cross-product concern; lives entirely in seed. Products inherit from the factory. **(Most cases.)**
- **1 line** — opt-out flag (`consentUI: false`) or opt-in component prop. Acceptable when justified.
- **A small section** — product-specific data wiring around a seed-shaped container (e.g. `<DigestCard prose={useMonthlyNarrative().data}/>`). Acceptable for product-specific data sources.
- **Multiple files / pages / mounts per product** — **STOP**. The design is wrong. Apply the language-trigger rule (`KB § PATTERNS/project-execution.md § The replication-to-seed symmetry rule`) and re-scope.

If your design requires "mount on each product's settings page" or "scaffold a new file in each product's frontend" — the answer is wrong. Re-design in seed.

---

## Worked examples — reading actual project shapes

### Example 1: `consent-ui-rollout` (caught + restructured 2026-04-28)

**Original framing:** "build seed components, mount on each product's settings page" (Phases 2-4 walked through 6 products mounting the panel).

**Seed-first analysis:**
- Q1 (uniform contract?): YES — same backend, same response shape, same toggle UX.
- Q2 (data product-specific?): NO — `/api/me/consents` returns user-scoped catalog uniformly.
- Q3 (placement product-specific?): NO — `/settings/ai` is meaningful for every authenticated user.
- Q4 (gate uniform?): YES — authenticated only.
- Q5 (existing seam?): YES — `LayoutEnrichment.aiBadge` exists; route registration via `createProductApp` exists.
- Q6 (default-on?): YES — every authenticated user benefits.

**Litmus:** per-product code count = 0. Outcome: build seed components + add `/settings/ai` to a SEED route map auto-injected by `createProductApp` + default-fill `aiBadge`. Phases 2-4 of the original PROJECT.md collapsed into one framework-side phase.

### Example 2: `digest-ui-pages` (4 different surfaces — partly seedable)

**Framing:** PF monthly narrative card + Daily Life weekly review + Mailing campaign debrief + Core audit digest.

**Seed-first analysis:**
- Q1 (uniform contract?): MIXED — each digest has its own endpoint, but the rendering shape is uniform (title + prose paragraphs + feedback buttons).
- Q2 (data product-specific?): YES — different hooks, different responses.
- Q3 (placement product-specific?): YES — PF dashboard, Daily Life dashboard, Mailing CampaignDetail tab, Core admin page.
- Q4 (gate?): MIXED — some user-scoped, audit-digest is admin-only.
- Q5 (existing seam?): YES — `<AIFeedbackButtons/>` already exists for the per-surface feedback.
- Q6 (default-on?): NO — these are product-specific dashboard surfaces.

**Litmus:** the *container shape* (`<DigestCard prose feedback />`) is seedable; the *placement + data wiring* is product-specific. Per-product code count: 1 small component per product that wraps the seed container with its own hook. That's legitimate per-product code (different domains, different data sources) — NOT replication.

### Example 3: `llm-spend-badge-mount` (already seed-first as planned)

**Framing:** ship `<LLMSpendBadge/>` + add to default `aiBadge` stack.

**Seed-first analysis:** all 6 questions point at seed. The original Phase 2 already planned framework-default for `aiBadge`. Per-product code count = 0 (Daily Life is a single-line edit because it has its own product-specific badge that needs to compose with the defaults).

**Litmus:** seed-first by design. Execute as-planned.

---

## Anti-patterns (red flags to challenge)

### Phrasings that signal the slip

If any of these appear in a project doc, in a user prompt, or in your own response — STOP and re-design:

- "per-product X"
- "mount across N products"
- "for each product Y"
- "per-product mount table"
- "mount on each settings page" / "mount on each layout"
- "every product gets its own ___"
- any phrasing that implies the same thing happens N times

### "We'll add an opt-in flag per product"

Opt-in flags are fine when the feature is sometimes-applicable. They're an anti-pattern when the feature is universally beneficial — opt-out is the right posture (every product gets it; outliers explicitly opt out).

### "Products import + mount, don't reimplement"

If the rule allows products to "import + mount," the mount itself is one line per product = **N lines of identical code**. That's the replication-to-seed signal. The mount belongs in the framework too.

### "Per-product test"

If your design has a "we'll add a test per product" step, the test is also seedable (almost always). Either the test is contract-shaped (lives in seed-lib once, products auto-inherit via the pytest plugin) or it's product-specific data flow (lives once per product because the data wiring is genuinely product-specific).

---

## Cross-references

- `KB § PATTERNS/project-execution.md § The replication-to-seed symmetry rule` — the slip-pattern doc (catches it after the fact).
- `KB § PATTERNS/project-execution.md § 2.5 Phase 0 audits` — Phase 0 is where this checklist gets run.
- `KB § PATTERNS/project-execution.md § 2.6 Active robustness review` — execution-time inspection.
- `KB § 03-SEED-ARCHITECTURE § Seed Contract` — the canonical seam list for backend + frontend factories.
- `CLAUDE.md` rule "Replication-to-seed symmetry — fires at LANGUAGE time, not action time" — the user-facing pointer.
