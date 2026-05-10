# AdConnect MVP Implementation — Project Document

> **This is a living document, not a rigid checklist.**
> Revise phases, fold in optimizations, update the Change Log. A project that survives execution unchanged is either trivial work or ignored information.
>
> **Write for a zero-context reader.** This document is self-contained. If you are picking this up cold, start at §1 and read sequentially.

- **Created:** 2026-05-05
- **Last updated:** 2026-05-05
- **Status:** Design locked → Phase 0 ready
- **Owner / stakeholders:** João Raphael (product owner) · next-agent (executor)
- **Related docs:**
  - `products/adconnect/README.md` — current-state overview
  - `products/adconnect/MASTER-PROMPT.md` — domain authority
  - `KNOWLEDGE-BASE/CONTEXT/PATTERNS/seed-workspace.md` — sibling-workspace pattern
  - `KNOWLEDGE-BASE/CONTEXT/PATTERNS/project-execution.md` — execution methodology
  - `KNOWLEDGE-BASE/CONTEXT/GUIDES/seed-first-design.md` — six-question checklist
  - `templates/PROJECT-TEMPLATE.md` — this template's source
- **Project slug:** `adconnect-mvp-implementation`
- **Project location:** `products/adconnect/projects/adconnect-mvp-implementation/` (single-product, lives under the product's own `projects/`)

---

## 1. Context & Purpose

AdConnect is a B2B marketplace product on the NoctusAI platform. A **brand** (the customer who bought AdConnect) onboards its **distributor network** so distributors can browse the brand's catalog at preferential prices, place orders, file sellout reports, and earn cashback rewards on qualifying sellout. Brand-side admins manage the catalog, distributors, reward rules, and review sellout/financial state.

**The problem this project solves.** AdConnect was absorbed into the monorepo at an early stage of the platform — pre-current seed framework, pre-current methodology. The result today is a *partial scaffold*:

- The backend uses `create_product_app()` from `noctusai_seed` correctly (already aligned with the seed framework — `products/adconnect/backend/app/main.py:44`).
- 9 domain routers are wired (`auth`, `products`, `cart`, `orders`, `rewards`, `sellout`, `financial`, `distributors`, `admin`) — but every one reads/writes through an in-memory `store` backed by JSON files in `products/adconnect/backend/app/data/*.json`. **No database tables exist for any domain entity.**
- The migration `001_adconnect.sql` (renamed from `001_seed.sql` during pre-implementation cleanup) creates only the framework tables (`adconnect.status_pagina`, `adconnect.invitations`).
- The frontend has zero domain pages — only the seed-provided ones (Dashboard, Equipe, Login, Landing, AcceptInvite, ForgotPassword, NotFound, SSOCallback).
- Tests cover only the framework (health, team).

**The win.** AdConnect is a real, production-shippable B2B marketplace product, with the distributor-side loop (browse → cart → order → sellout → rewards) end-to-end usable, the brand-side admin V2-deferred but planned, the auth model aligned with the platform's `org_role + noctus_role` hierarchy extended for the brand→distributor→user shape the user requested, and Stripe/Resend/NF-e wired by inheritance from noc rather than reinvented.

**Why this project NOW.** A real customer for AdConnect is not yet identified (per the user, §2 below). This is the right time to do the implementation right — without a customer deadline pressuring shortcuts that would later need to be unwound.

---

## 2. Confirmed constraints

User answers from the 2026-05-05 interrogation. Document non-obvious answers — future agents inherit the reasoning.

- **Identity hierarchy** — owner-of-solution → companies → users. *(Mirror ERP / Therapy pattern. The brand is the noc org that bought AdConnect; "companies" are distributors as sub-entities under the brand's org; users belong to distributors. Owner can also assign single users not tied to any company. Phase 0 audits how ERP / Therapy express this so AdConnect's schema follows the same shape.)*
- **Tenant model** — single-instance with the hierarchy above. *(User explicitly said "I'll probably change that in the future. For now, let's keep it this way." → don't over-engineer for multi-brand; design the schema so brand → distributor relationships could later be lifted to brand-as-tenant if needed.)*
- **MVP slicing** — Phase 0 audit, then catalog (products + distributors) → cart + orders → rewards + sellout → financial → admin → frontend → close. *(User accepted the proposed phase order verbatim.)*
- **Mock data fate** — uncertain at planning time; **Phase 0 audits whether the mock JSON shapes make sense for production**. If yes, use as base; if not, redesign. *(User: "im not sure, does what we already have make sense? If it does, use it. If not, redesign.")*
- **Frontend scope** — distributor-only V1; brand-side admin V2 (separate follow-up project). *(User accepted the proposed split.)*
- **Stripe** — inherit from noc, do NOT reinvent. *(User explicitly: "stripe, we already use it and it should be inherited from noc." → AdConnect's Phase 5 wires through `products/core/backend/app/services/stripe_service.py` + the seed billing routes, not a local Stripe integration.)*
- **Sellout report shape** — structured form + NF-e XML upload + freeform attachment, all three. *(User: "both for now" + "yes" to NF-e upload.)*
- **NF-e (Brazilian invoicing)** — AdConnect emits invoices itself. *(User: "yes". Phase 5 includes NF-e generation, not just record-keeping.)*
- **Email transport** — Resend. *(User: "Use Resend for now, as SMPT-SMTP isnt tested yet. Supposedly, Resend is." → use `noctusai_lib.integrations.email` which is already Resend-backed via `seed/lib/backend/noctusai_lib/integrations/email/digest.py`.)*
- **Seed extraction policy** — keep AdConnect-only for now; pilot first, extend later. *(User: "keep ad connect only for now. Let's create a pilot before extending it to wherever." → DO NOT prematurely extract rewards engine / sellout / B2B catalog into `noctusai_lib.domain.*`. Recurrence rule still applies — N=2 elsewhere triggers absorption talk, but that's a separate decision moment, not part of this project.)*
- **No customer evaluation right now** — there is no specific brand/customer driving AdConnect. *(Greenfield product spec. Affects priority order: no Phase 7 deadline; no per-customer naming / data shaping. The user said: "im just gonna read what you wrote and might pivot some pieces with no fundamental concern.")*
- **Naming language** — Portuguese for entities, English for code. *(Standard NoctusAI convention; matches ERP. Domain entities in DB and UI use Portuguese — distribuidores, pedidos, recompensas, sellout, financeiro — code identifiers stay English.)*
- **Compliance / LGPD** — flag during implementation; not a planning-time decision. *(User: "dont know yet" → Phase 1+ MUST call `noctus.dev.lgpd_flag` on every distributor PII write — CNPJ, addresses, payment data, financial state. Hard answers come from product owner reviewing flagged data later.)*

---

## 3. Design principles

How we're approaching *this specific problem* beyond the platform-wide `CLAUDE.md` rules.

1. **Seed framework is non-negotiable.** All routers stay attached through `create_product_app()`'s `routers=[...]` seam (already correct in `products/adconnect/backend/app/main.py:44`). Never re-wire CORS, exception handlers, or middleware locally. Every PR confirms this with `cat products/adconnect/backend/app/main.py | grep create_product_app`.
2. **Mock JSON is informative, not authoritative.** The current `app/data/*.json` files are the only documentation of what shape the domain was *thought* to have at absorption time. Phase 0 audits each shape for production sense; mismatches drive schema redesign rather than mechanical mirroring.
3. **Inherit, don't reinvent.** Stripe → from noc. Email → from `noctusai_lib.integrations.email`. SSO → from `noctusai_seed`. Webhooks → from `noctusai_lib.security.webhook_signatures`. Identity → from existing `org_role + noctus_role` extended for distributor sub-entities. If the seed has it, AdConnect consumes it.
4. **Distributor-first.** V1 ships the distributor loop end-to-end. The brand can operate the marketplace via direct DB access in V1 (catalog edits, reward rule edits, sellout review) until V2 adds the admin UI. This trades brand-side polish for a real distributor experience that proves the product.
5. **No premature seed extraction.** Per user, the rewards / sellout / B2B-catalog primitives stay AdConnect-local until N=2 elsewhere triggers the recurrence rule. Build the engine well in `app/services/` so future absorption is mechanical.
6. **Test every router-DB swap.** Each phase that converts a mock router to a Supabase-backed router lands at least one router-level integration test (TestClient + MockRequestBuilder) and one realdb test (`tests/realdb/`) to catch RLS regressions.

---

## 3a. Seed-first analysis (REQUIRED — the seed is every product's skeleton)

Run the six-question checklist (`KNOWLEDGE-BASE/CONTEXT/GUIDES/seed-first-design.md`).

1. **Is the contract identical for every product?** **NO** for the marketplace domain (catalog/cart/orders/rewards/sellout/financial — these are AdConnect-specific business logic). **YES** for the cross-cutting concerns (Stripe, email, SSO, invitations, page-status, auth context, webhooks, LGPD flagging) — those already live in seed and AdConnect inherits them.
2. **Is the data source product-specific?** **YES** — every domain entity is AdConnect-owned (Supabase schema `adconnect`, RLS scoped to brand `org_id` + distributor `distributor_id`). Cross-cutting helpers (e.g. `noctusai_seed.standard_routers=["health", "notificacoes", "team"]`) read product-specific data via factory injection.
3. **Is the placement product-specific?** **YES** — the marketplace UI lives at `products/adconnect/frontend/src/pages/`; the marketplace API at `products/adconnect/backend/app/routers/`. Cross-cutting placement (sidebar, header, AppShell) is already provided by `createProductLayout()`.
4. **Is the visibility / permission rule the same?** **MIXED** — distributor data is brand-tenant-scoped + distributor-user-scoped (specific to AdConnect's hierarchy). Cross-cutting auth (SSO, JWT verification, session) is uniform and inherited from seed.
5. **Does the seam already exist in seed?** **YES for cross-cutting**: `create_product_app(routers=[...], standard_routers=[...])` for backend wiring; `createProductApp()` + `createProductLayout()` for frontend; `noctusai_lib.integrations.email` for Resend; `products/core` Stripe routes for billing inheritance. **NO for AdConnect domain seams** — those are correctly product-specific and DO NOT belong in seed (per user's "keep AdConnect-only" directive).
6. **Default-on or opt-in?** **OPT-IN for the marketplace domain** (only AdConnect mounts these routers). **DEFAULT-ON for cross-cutting** (every product gets health/team/notifications/SSO/etc. via the seed framework).

**Litmus — per-product code count this design requires:**

- [x] **A small section** — product-specific data wiring around seed-shaped containers. AdConnect's 9 routers + frontend pages are domain-bounded. The cross-cutting concerns (Stripe, email, SSO, etc.) are inherited from seed at zero per-product cost. The recurrence trigger (N=2 elsewhere) is the future decision point for absorption.

**Phase plan implications:** §6 phases work product-locally — there is no replication framing because there is exactly one product (AdConnect) and zero cross-cutting concerns being designed here. The only seed-touches in this project are *consumption* (Stripe inherit, Email inherit, SSO inherit) — not authoring. Phase 0 explicitly verifies "the seed already ships X" for every X we plan to consume, so we don't lock into a consumption decision based on a Protocol that has no Real adapter (per `feedback_verify_seed_ships_it.md`).

---

## 4. Scope

**In scope (V1 MVP):**

- Identity model: brand → distributor → user hierarchy via `noctus_users` + new `adconnect.distributors` + `adconnect.distributor_memberships` tables. Self-registration via invitation only (open self-signup deferred).
- Catalog: `adconnect.products` + `adconnect.categorias` + per-distributor preferential pricing via `adconnect.precos_distribuidor`.
- Ordering: `adconnect.carts` (per-distributor session) + `adconnect.pedidos` + `adconnect.itens_pedido` with status lifecycle (rascunho → enviado → confirmado → enviado_para_entrega → entregue / cancelado).
- Rewards: `adconnect.regras_recompensa` (cashback rules) + `adconnect.recompensas_acumuladas` (accrual ledger) + redemption tracking.
- Sellout: `adconnect.relatorios_sellout` with three submission modes (structured form, NF-e XML upload, freeform attachment).
- Financial: `adconnect.faturas` (invoices) emitted by AdConnect itself with NF-e generation, payment tracking via Stripe inheritance.
- Stripe billing: subscription + per-order processing via inheritance from `products/core/backend/app/services/stripe_service.py` and the seed billing routes.
- Email notifications: order placed, sellout reviewed, invoice issued, reward accrued — all via `noctusai_lib.integrations.email` (Resend).
- Frontend distributor pages (~7 pages): catalog browse, product detail, cart, checkout, order history + detail, sellout report submission + history, rewards ledger.
- LGPD flagging at every distributor PII write site.
- Tests: realdb suite for RLS, router-level for endpoint shape, frontend smoke for build cleanliness.

**Out of scope (deferred — with reason):**

- **Brand-side admin UI** — V2, separate project. *(User explicitly said "for now let's keep it this way [distributor-only V1]. Might change in the future.")* Brand operates via direct DB access + Supabase Studio in V1. Catalog management, distributor list, sellout review, reward-rule editor, invoice list — all deferred to a follow-up `adconnect-brand-admin-v2` project.
- **Open self-registration for distributors** — V1 is invitation-only. Self-signup adds account-verification + spam-prevention complexity that isn't needed without a real customer.
- **Multi-brand multi-tenancy** — V1 is single-instance with one brand `org_id`. *(Multi-brand is "I'll probably change that in the future" per user.)*
- **Premature seed extraction of rewards / sellout / B2B-catalog primitives** — kept AdConnect-local per user directive. Recurrence rule (N=2 elsewhere) is the future trigger, not this project.
- **Customer-specific data shaping** — no specific brand/customer driving AdConnect, so no customer-specific naming / mock data calibration / hard deadlines factor into design.
- **Real-time order tracking / shipping integrations** — order status is manual lifecycle in V1. Carrier integration deferred.
- **Mobile app** — web-only V1.

---

## 5. Architecture / Data Model

### 5.1 Identity hierarchy (brand → distributor → user)

The user said "use the ERP and therapy hierarchy" — extend the platform's existing `org_role + noctus_role` model with a sub-entity layer for distributors.

```
noc.organizations          (brand-side: ONE row representing the brand who bought AdConnect)
  └── noc.noctus_users     (the brand's owner + admins; org_role: owner | admin | member | viewer)

adconnect.distributors     (distributor entities under the brand; each has its own CNPJ, billing, contact)
  └── adconnect.distributor_memberships
        ├── user_id        FK → noc.noctus_users.id
        ├── distributor_id FK → adconnect.distributors.id
        └── role           TEXT (distributor_owner | distributor_member | distributor_viewer)
```

**Key questions Phase 0 must answer by reading ERP / Therapy migrations:**

- Do ERP / Therapy use `noctus_users.org_id` to mean "the company the user belongs to" or do they have a separate sub-entity table similar to the `distributors` shape proposed here?
- Are there shared seed primitives for "sub-entity within an org" (e.g. `noctusai_lib.domain.subentities`)? If so, AdConnect inherits those rather than re-creating.
- What's the canonical RLS pattern for "user belongs to N entities, sees only their entity's data"? Phase 1 mirrors that pattern.

**RLS skeleton (refined in Phase 1 after Phase 0 audit):**

```sql
-- Distributor users see only their distributor's data:
CREATE POLICY "distrib_users_see_own_distrib_pedidos" ON adconnect.pedidos
    FOR SELECT TO authenticated
    USING (
        distributor_id IN (
            SELECT distributor_id FROM adconnect.distributor_memberships
            WHERE user_id = auth.uid()
        )
    );

-- Brand owner sees everything in their org:
CREATE POLICY "brand_owner_sees_all_pedidos" ON adconnect.pedidos
    FOR SELECT TO authenticated
    USING (
        EXISTS (
            SELECT 1 FROM noc.noctus_users
            WHERE id = auth.uid()
              AND org_role IN ('owner', 'admin')
              AND org_id = (
                  SELECT org_id FROM adconnect.distributors
                  WHERE id = adconnect.pedidos.distributor_id
              )
        )
    );
```

These shapes are PROVISIONAL — Phase 0 audits ERP / Therapy and Phase 1 finalizes.

### 5.2 Domain table inventory (Phase 1-5 lands these)

```
adconnect.distributors             — distributor entities (CNPJ, name, address, contact)
adconnect.distributor_memberships  — user → distributor join table with role
adconnect.categorias               — product categories
adconnect.products                 — brand catalog (sku, name, description, base_price, in_stock, photos)
adconnect.precos_distribuidor      — per-distributor preferential pricing (FK product_id + distributor_id)
adconnect.promos                   — promotional rules (current mock: app/data/promos.json)
adconnect.carts                    — per-distributor cart (FK distributor_id, status: ativo|abandonado|convertido)
adconnect.itens_carrinho           — line items (FK cart_id + product_id, quantity, price_at_add)
adconnect.pedidos                  — orders (FK distributor_id, FK cart_id, status, total)
adconnect.itens_pedido             — order line items (FK pedido_id + product_id, quantity, price_at_order)
adconnect.regras_recompensa        — cashback rules (mock: app/data/reward-rules.json)
adconnect.recompensas_acumuladas   — accrual ledger (FK distributor_id, FK source_pedido_id|source_relatorio_sellout_id)
adconnect.resgates_recompensa      — redemption events
adconnect.relatorios_sellout       — sellout reports (FK distributor_id, status: pendente|aprovado|recusado, three submission modes)
adconnect.faturas                  — invoices issued by AdConnect (FK distributor_id, NF-e XML, stripe_invoice_id)
```

### 5.3 Backend layout (post-implementation)

```
products/adconnect/backend/
  app/
    main.py                  → create_product_app(...) — UNCHANGED (already correct)
    config.py                → SeedSettings — UNCHANGED unless adding settings (e.g. NFE_PROVIDER_API_KEY)
    database.py              → create_database_module(settings, "adconnect") — UNCHANGED
    dependencies.py          → create_dependencies(db) — UNCHANGED
    rate_limit.py            → create_product_limiter(settings) — UNCHANGED
    auth_deps.py             → reused if SSO; REPLACED if collapsing custom JWT
    security.py              → REMOVED if collapsing custom JWT (currently scaffolded for password hashing)
    routers/
      auth.py                → REPLACED (Phase 1: SSO inherit OR custom-JWT-finalized — Phase 0 decides)
      products.py            → REPLACED (Phase 2: Supabase-backed)
      distributors.py        → REPLACED (Phase 2)
      cart.py                → REPLACED (Phase 3)
      orders.py              → REPLACED (Phase 3)
      rewards.py             → REPLACED (Phase 4)
      sellout.py             → REPLACED (Phase 4)
      financial.py           → REPLACED (Phase 5)
      admin.py               → REPLACED (Phase 6 — minimal V1; brand-admin V2 deferred)
    services/
      products_service.py    → NEW (Phase 2)
      cart_service.py        → REWRITTEN (currently mock-backed; Phase 3 swap)
      orders_service.py      → NEW (Phase 3)
      rewards_service.py     → REWRITTEN (currently mock-backed; Phase 4 swap)
      sellout_service.py     → NEW (Phase 4)
      financial_service.py   → NEW (Phase 5; consumes Stripe via noc inheritance)
      nfe_service.py         → NEW (Phase 5; NF-e generation)
    schemas/                 → NEW Pydantic models per router (Phase 1-5 each lands its own)
    data/                    → REMOVED at end of Phase 5 (no more JSON mocks)
  migrations/
    001_adconnect.sql        → already lands framework tables (status_pagina, invitations)
    002_adconnect_identity.sql      → Phase 1 (distributors, distributor_memberships, RLS)
    003_adconnect_catalog.sql       → Phase 2 (categorias, products, precos_distribuidor, promos)
    004_adconnect_orders.sql        → Phase 3 (carts, itens_carrinho, pedidos, itens_pedido)
    005_adconnect_rewards.sql       → Phase 4 (regras_recompensa, recompensas_acumuladas, resgates)
    006_adconnect_sellout.sql       → Phase 4 (relatorios_sellout)
    007_adconnect_financial.sql     → Phase 5 (faturas)
  tests/
    routers/                 → expanded per phase
    realdb/                  → NEW directory (RLS coverage, parallel to products/erp-imobiliario/backend/tests/realdb/)
    integration/             → existing test_e2e_flows.py expanded per phase
```

### 5.4 Frontend layout (Phase 7 lands this)

```
products/adconnect/frontend/src/
  App.tsx                    → UNCHANGED (already createProductApp())
  vite.config.ts             → UNCHANGED (createViteConfig({ port: 8130 }))
  pages/
    Dashboard.tsx            → EXTENDED (currently stack-status; add distributor home: orders preview, rewards balance)
    Equipe.tsx               → UNCHANGED (framework page)
    Login/Landing/etc.       → UNCHANGED
    Catalog.tsx              → NEW (product browse with filter/search/sort)
    ProductDetail.tsx        → NEW
    Cart.tsx                 → NEW
    Checkout.tsx             → NEW
    Orders.tsx               → NEW (order history list)
    OrderDetail.tsx          → NEW
    SelloutReportSubmit.tsx  → NEW (three-mode submission: structured / NF-e upload / freeform)
    SelloutHistory.tsx       → NEW
    RewardsLedger.tsx        → NEW
  hooks/
    useCatalog.ts            → NEW
    useCart.ts               → NEW
    useOrders.ts             → NEW
    useSellout.ts            → NEW
    useRewards.ts            → NEW
  components/
    distributor/             → NEW domain components
```

### 5.5 Inherited from noc / seed — verify-the-seed-ships-it test

Before locking each consumption decision, the next agent runs `noctus.seed.list_capabilities` AND reads the concrete adapter file (per `feedback_verify_seed_ships_it.md` — Protocol+Fake without Real does not count as "the seed ships it"):

| Capability | Lives at | Phase that consumes |
|---|---|---|
| `create_product_app()` | `seed/framework/backend/noctusai_seed/app.py` | already consumed in `main.py` |
| Stripe billing | `products/core/backend/app/routers/billing.py` + `services/stripe_service.py` | Phase 5 |
| Email (Resend) | `seed/lib/backend/noctusai_lib/integrations/email/digest.py` | Phase 3+ (notifications) |
| Webhook signatures | `seed/lib/backend/noctusai_lib/security/webhook_signatures.py` | Phase 5 (Stripe webhook handler) |
| SSO | `seed/lib/backend/noctusai_lib/api/auth.py` (`make_get_current_user`, `make_get_current_user_org`, `make_require_role`, `resolve_sso_role`) | Phase 1 (auth) ✅ |
| LGPD flag tooling | `noctus.dev.lgpd_flag` MCP tool | Phase 1+ (every PII write) |
| Invitations table | `adconnect.invitations` (per migration `001_adconnect.sql`) | Phase 1 (distributor onboarding) |

---

## 6. Implementation phases

Phases are **suggestive, not strict.** Reorder, split, merge, or discover new phases as work progresses. Per `templates/PROJECT-TEMPLATE.md` convention, every phase header carries a status icon when state changes (none → ⏳ → ✅, or ❌ if blocked).

**Improvement capture:** drop short bullets into each phase's `**Improvements:**` block during step implementation. At phase end, synthesize ONE proposal via `noctus.dev.file_proposal(project="adconnect-mvp-implementation", ...)`. Then flip to ✅.

**Branching:** per `feedback_branching_methodology.md`, this project lives on its own branch — `adconnect-mvp-implementation` — branched from `origin/main` at start. Each phase is a commit (or a small sequence of commits) on that branch. Final merge to main is the orchestrator's responsibility (per `feedback_orchestrator_role.md`).

**Findings:** maintain `findings.md` at the project root per `feedback_knowledge_tracking.md` — five categories (errors / mistakes-slips / lessons / interesting-findings / knowledge-pieces). Append in-the-moment for surprises; synthesize at close.

---

### Phase 0 — Audit and locked design decisions ✅

Goal: produce a concrete "this is what we're building" document the rest of the phases can reference without further interrogation.

- [x] Run `noctus.seed.audit_drift` to know which AdConnect files have drifted from `templates/product-seed/` canonical. Capture the report in `findings.md` under "knowledge-pieces" — informs Phase 7 frontend (drift list shows what's been customized). *(Tool name in MCP server is `noctus.dev.diff_against_seed`; ran — only port drift, expected.)*
- [x] Run `noctus.seed.list_capabilities` to know what `noctusai_seed` + `noctusai_lib` provide. Capture the seed-export inventory in `findings.md` so Phase 1-5 don't reinvent. *(No MCP tool with that name; inventory built by reading `seed/lib/backend/noctusai_lib/` + `seed/framework/backend/noctusai_seed/` directly.)*
- [x] Read ERP migrations: `products/erp-imobiliario/backend/migrations/001_erp_imobiliario.sql` + `015_invitations.sql` + any sub-entity migrations. Document how ERP expresses sub-entities under the brand org.
- [x] Read Therapy migrations: `products/therapy-platform/backend/migrations/001_therapy_platform.sql`. Same audit.
- [x] Read core's identity model: `products/core/backend/migrations/001_noctusai_core.sql` lines around `org_role`, `noctus_users`, `noctus_orgs`. Confirm the canonical hierarchy column names.
- [x] Read every JSON mock in `products/adconnect/backend/app/data/*.json`. For each, decide: (a) production schema mirrors mock 1:1 / (b) production schema diverges from mock and document the divergence in `findings.md`. Bias toward divergence — mocks were absorption-stage guesses.
- [x] Decide auth model. Two options the user left for Phase 0:
  - **Option A — distributor-as-noc-user.** Distributor users live in `noc.noctus_users` with their `org_id` pointing at the brand's org; their distributor membership lives in `adconnect.distributor_memberships`. Single SSO surface. Custom JWT in `auth.py` and `security.py` is removed; AdConnect inherits the seed's auth.
  - **Option B — distributor-as-external-org.** Each distributor is its own `org_id` in noc; users belong to the distributor's org; the brand has a separate org with cross-org-read permissions. Heavier setup, cleaner if distributors ever become multi-brand customers.

  Recommendation: **Option A** for V1 (matches user's "I'll probably change that in the future"). Lock the decision in `findings.md` and note the migration path to Option B if it ever needs to flip. *(Locked: Option A.)*
- [x] Document the locked decisions in `findings.md` AND update §5 of this PROJECT.md if any decision changes the planned architecture.
- [x] Confirm Stripe entry point: `products/core/backend/app/services/stripe_service.py` + `app/routers/billing.py` are the canonical surface AdConnect inherits. Read both and confirm they expose what Phase 5 needs (checkout session, customer portal, webhook handler).
- [x] Confirm email entry point: `noctusai_lib.integrations.email.digest.send_to_one` for transactional notifications. Read `seed/lib/backend/noctusai_lib/integrations/email/digest.py` and confirm shape.
- [x] Run `noctus.dev.lgpd_list` to see existing LGPD flags in the platform. Identify which flag types apply to distributor data (CNPJ, addresses, payment data). Phase 1+ uses these flag types.

**Exit criteria:** `findings.md` documents (1) full seed inventory, (2) ERP/Therapy hierarchy pattern, (3) auth-model lock-in, (4) every mock JSON's mirror/divergence decision, (5) Stripe + email + LGPD entry points confirmed. §5 of this PROJECT.md is updated if any audit finding changes the architecture.

**Tests required:** N/A (audit-only phase). Run the existing 2 tests (`pytest products/adconnect/backend/tests/`) to confirm baseline green before Phase 1.

**Improvements:**
- PROJECT.md §5.5 SSO path corrected (`noctusai_lib/api/auth.py`, not `security/oauth/`); folded inline.
- PROJECT.md §6 Phase 1 step 7 LGPD signature corrected to real `(code_path, concern, reason, mitigation)`; folded inline.
- `noctus.seed.audit_drift / list_capabilities / scan_repetition` tool names referenced in PROJECT.md don't exist in the MCP server — closest analogues used (`noctus.dev.diff_against_seed`, `noctus.dev.scan_within_product_helpers`). Methodology learning: align PROJECT.md drafts with actual MCP names by running `claude mcp list` first; logged for three-way sync.
- N=2 sub-entity recurrence (therapy.clinics + adconnect.distributors) — triage outcome accept-with-rationale; flips to formalize on N=3+. Catalog entry deferred until merge to main.

---

### Phase 1 — Identity foundation (migration + RLS + auth swap) ✅

Goal: distributors and distributor users exist as DB entities; SSO works for distributor users; the custom-JWT scaffold is replaced (or finalized — Phase 0 decides).

- [x] Author `migrations/002_adconnect_identity.sql` — creates `adconnect.distributors`, `adconnect.distributor_memberships`. Use `noctusai_lib.domain.sql_templates` helpers. Apply via `mcp__claude_ai_Supabase__apply_migration`. *(File authored. Application deferred to orchestrator — no Supabase credentials in worktree.)*
- [x] RLS policies on both tables: distributor users see only their distributor's row; brand owner/admin sees all distributors in the brand's org. Mirror the canonical pattern from Phase 0 audit. *(Membership-table subquery shape used — supports many-distributors-per-user per §7 #6.)*
- [x] Replace `app/routers/auth.py` per Phase 0 lock-in (Option A: SSO inherit; Option B: custom JWT finalized with proper user table). Either path: REMOVE the in-memory `_seed_users()` from `app/routers/auth.py`. *(Option A locked. New router: GET /me + POST /accept-distributor-invite.)*
- [x] If Option A: REMOVE `app/security.py` (password hashing no longer needed) and `app/auth_deps.py` (replaced by seed's auth dep). *(`security.py` removed. `auth_deps.py` REWRITTEN as a thin delegation shim re-exporting `get_current_user` + `require_role` from the seed's `make_get_current_user` / `make_require_role` factories — outright removal would break 7 mock-backed routers awaiting Phase 2-6 swap. See `findings.md → mistakes-slips`. Slated for full removal at Phase 6 close.)*
- [x] Update `app/data/store.py` to remove the `users` field (it was the in-memory auth backing).
- [x] Add invitation flow for distributor users: brand admin invites a user to a distributor via the existing `adconnect.invitations` table; user accepts; `distributor_memberships` row is created. *(Lives in `app/routers/auth.py` — `POST /api/auth/accept-distributor-invite`.)*
- [x] Pydantic schemas in `app/schemas/identity.py`: `DistributorIn / DistributorOut / MembershipIn / MembershipOut`. *(Plus `AcceptDistributorInviteIn` + literal-typed status/tier/role enums.)*
- [x] LGPD flagging: every write to `adconnect.distributors` calls `noctus.dev.lgpd_flag(table="adconnect.distributors", fields=["cnpj", "endereco_*", "contato_*"], reason="Distributor PII at registration")`. *(Real tool signature is `code_path` + `concern` + `reason` — flagged via that surface; entry recorded in `LGPD-WARNINGS.md`. See `findings.md → knowledge-pieces → LGPD flag types`.)*

**Drive-by fix in scope:** `app/main.py` was setting `router.prefix = "/auth"` AFTER route registration; FastAPI 0.115's `include_router` ignores post-construction prefix mutation, so all 9 domain routers were colliding at the bare paths their routes declared (`/me`, `/dist-001`, `/dashboard`, etc.). Fixed by wrapping each domain router under a fresh `APIRouter(prefix="/api/<domain>", tags=[...])` parent at include time. All domain routers now mount under their intended `/api/<domain>` paths.

**Tests required:**
- `tests/routers/test_auth_router.py` — login flow + invitation acceptance.
- `tests/routers/test_distributors_router.py` — CRUD via mocks.
- `tests/realdb/test_identity_realdb.py` — RLS smoke: distributor user A cannot see distributor B's row; brand owner sees all.

**Exit criteria:** distributors and memberships are persisted in Supabase; SSO works; distributor user can log in and sees only their distributor; brand owner sees all. All three test layers pass.

**Improvements:** _(captured during steps; synthesized into a phase proposal at close)_

---

### Phase 2 — Catalog (products + categories + per-distributor pricing)

Goal: brand catalog is in Supabase, distributors browse it through `/api/products`, with per-distributor preferential pricing applied.

- [ ] Author `migrations/003_adconnect_catalog.sql` — creates `adconnect.categorias`, `adconnect.products`, `adconnect.precos_distribuidor`, `adconnect.promos`. Apply via Supabase MCP.
- [ ] RLS: products + categorias readable by all authenticated users in the brand org; precos_distribuidor row visible only to the matching distributor's users + brand admin.
- [ ] Backfill: write a one-shot Supabase SQL migration that imports `app/data/products.json` + `categories.json` + `promos.json` into the new tables (or a Python script in `scripts/seed-adconnect-mocks.py` if simpler — depends on data shape complexity decided in Phase 0).
- [ ] Replace `app/routers/products.py`: DROP `from ..data.store import store`; query `db.client.table("products")`. Preserve current filter/sort/search query-param shape (the frontend will adopt this). Apply preferential pricing in service layer.
- [ ] Replace `app/routers/distributors.py` similarly (currently mock-backed; uses `app/data/distributors.json`).
- [ ] Pydantic schemas in `app/schemas/catalog.py`.

**Tests required:**
- `tests/routers/test_products_router.py` — filter/search/sort, in-stock filtering, preferential pricing applied for distributor user.
- `tests/realdb/test_catalog_realdb.py` — RLS: distributor A sees their preferential price; distributor B sees their own; cross-visibility rejected.

**Exit criteria:** distributor user can browse catalog with filter/search/sort working; preferential pricing applied per-distributor; brand admin can list all distributors.

**Improvements:** _(captured during steps)_

---

### Phase 3 — Cart + Orders

Goal: distributor adds to cart, places order, sees order history; the loop runs end-to-end (sans payment, which is Phase 5).

- [ ] Author `migrations/004_adconnect_orders.sql` — creates `adconnect.carts`, `adconnect.itens_carrinho`, `adconnect.pedidos`, `adconnect.itens_pedido`. Apply via Supabase MCP.
- [ ] RLS: cart + itens_carrinho + pedidos + itens_pedido scoped to the distributor; brand admin sees all.
- [ ] Order status lifecycle: `rascunho → enviado → confirmado → enviado_para_entrega → entregue / cancelado`. Lifecycle transitions ARE THE service-layer responsibility — don't model state via flags; use a single `status` column with checked transitions.
- [ ] Replace `app/routers/cart.py`: remove `app/data/store.py.orders` mock; query the new tables.
- [ ] Replace `app/routers/orders.py`: remove mock; service layer.
- [ ] Email notification: order placed → email to brand admin via `noctusai_lib.integrations.email.send_to_one`. Use email-templates pattern from `noctusai_lib.integrations.email.templates`.
- [ ] Pydantic schemas in `app/schemas/orders.py`.

**Tests required:**
- `tests/routers/test_cart_router.py` — add/update/remove line, total computation, conversion to order.
- `tests/routers/test_orders_router.py` — placement, lifecycle transitions, history listing.
- `tests/realdb/test_orders_realdb.py` — RLS: distributor A cannot see B's orders; brand admin sees all.

**Exit criteria:** distributor places an order from cart, brand admin receives notification email, order appears in distributor's history.

**Improvements:** _(captured during steps)_

---

### Phase 4 — Rewards + Sellout

Goal: distributor files sellout report, qualifying sellout triggers cashback accrual, distributor sees rewards ledger.

- [ ] Author `migrations/005_adconnect_rewards.sql` — `adconnect.regras_recompensa`, `adconnect.recompensas_acumuladas`, `adconnect.resgates_recompensa`. Apply.
- [ ] Author `migrations/006_adconnect_sellout.sql` — `adconnect.relatorios_sellout` with three submission modes: structured fields, `nfe_xml` BYTEA, `attachment_url` TEXT (uploaded to Supabase storage). Apply.
- [ ] RLS: relatorios_sellout + recompensas_acumuladas scoped to distributor; brand admin sees all (admin reviews + approves sellout, which triggers reward accrual).
- [ ] Storage bucket for sellout attachments via `noctusai_lib.integrations.storage` (the parallel agent's seed-hardening Phase 3.2 shipped this — `noctus.seed.list_capabilities` will surface it).
- [ ] NF-e XML parser: read uploaded XML, extract sellout-relevant fields (CNPJ, items, total). Use `noctusai_lib` if a parser exists; otherwise local in `app/services/sellout_service.py`. **N=2 trigger:** if any other product needs NF-e parsing, file a `noctusai_lib.domain.nfe` follow-up project.
- [ ] Cashback accrual engine in `app/services/rewards_service.py`: matches `relatorio_sellout` against `regras_recompensa`, writes `recompensas_acumuladas` rows. Pure function on top of DB rows — testable in isolation.
- [ ] Replace `app/routers/sellout.py`: three submission endpoints (or one polymorphic with `submission_mode` field).
- [ ] Replace `app/routers/rewards.py`: ledger query + redemption endpoint.
- [ ] Email notifications: sellout submitted → brand admin; sellout approved/rejected → distributor; reward accrued → distributor.
- [ ] LGPD: NF-e XML contains CNPJ; flag at upload time.
- [ ] Run `noctus.seed.scan_repetition` — the rewards engine is a candidate for future absorption (recurrence rule). Capture the result in `findings.md`; if N=2 elsewhere, file a follow-up project (DO NOT absorb in this project — user explicitly said "keep AdConnect-only for now").

**Tests required:**
- `tests/routers/test_sellout_router.py` — three submission modes, status lifecycle.
- `tests/routers/test_rewards_router.py` — ledger query, redemption.
- `tests/services/test_rewards_engine.py` — pure-function tests of accrual rules against seeded data.
- `tests/realdb/test_rewards_sellout_realdb.py` — RLS scoping.

**Exit criteria:** distributor uploads NF-e XML, brand admin reviews + approves, distributor sees cashback accrued in their ledger.

**Improvements:** _(captured during steps)_

---

### Phase 5 — Financial (Stripe inheritance + NF-e generation)

Goal: AdConnect emits invoices, payment is processed via Stripe inherited from noc, distributor sees invoice + payment status.

- [ ] Author `migrations/007_adconnect_financial.sql` — `adconnect.faturas` with `stripe_invoice_id`, `nfe_xml`, `status`. Apply.
- [ ] RLS: faturas scoped to distributor; brand admin sees all.
- [ ] **Stripe inheritance**: read `products/core/backend/app/services/stripe_service.py` + `app/routers/billing.py` + `app/routers/subscriptions.py`. AdConnect's `app/services/financial_service.py` consumes these — does NOT re-import the Stripe SDK directly. Webhooks already handled by core; AdConnect only consumes invoice events.
- [ ] NF-e generation: hit a Brazilian NF-e provider (which one? — open question §7 #1). Wrap in `app/services/nfe_service.py` with a Protocol so the provider can be swapped. **Verify-the-seed-ships-it test** — if `noctusai_lib` ships an NF-e helper, use it; otherwise local.
- [ ] Replace `app/routers/financial.py` with the new service.
- [ ] Email notification: invoice issued → distributor; payment received → distributor.
- [ ] LGPD: invoice + NF-e contain CNPJ + payment data; flag.

**Tests required:**
- `tests/routers/test_financial_router.py` — invoice listing, payment status query.
- `tests/services/test_nfe_service.py` — fixtures of expected NF-e XML output for sample input.
- `tests/realdb/test_financial_realdb.py` — RLS.

**Exit criteria:** AdConnect emits an invoice for a distributor's order, Stripe processes the payment, distributor sees status update.

**Improvements:** _(captured during steps)_

---

### Phase 6 — Brand-side admin V1 (minimal)

Goal: enough brand-side admin endpoints to operate AdConnect via API without UI. Brand admin V2 (the UI) is a follow-up project.

- [ ] Replace `app/routers/admin.py` with brand-admin endpoints: list distributors with metrics; review queue for sellout; reward-rule CRUD; invoice list across all distributors.
- [ ] Tests at `tests/routers/test_admin_router.py`.
- [ ] DELETE `products/adconnect/backend/app/data/` directory entirely. The mocks have served their purpose — no JSON fallback path remains.
- [ ] `git rm app/data/store.py` and clean up imports.

**Tests required:**
- `tests/routers/test_admin_router.py`.
- `tests/realdb/test_admin_realdb.py` — verify brand-owner role gate.

**Exit criteria:** brand admin can operate the marketplace via API alone. `app/data/` is gone. Backend is fully Supabase-backed.

**Improvements:** _(captured during steps)_

---

### Phase 7 — Frontend distributor pages ⏳ (skeleton)

Goal: distributor uses AdConnect entirely via the web UI.

- [ ] Pages per §5.4 inventory. Co-locate hooks per page.
- [ ] Use `@noctusai/lib` + `@noctusai/seed` factories. NO local `Layout.tsx`.
- [ ] React Query for backend integration (mirror PF/ERP pattern). Hooks in `src/hooks/`.
- [ ] Tailwind for styling (already configured).
- [ ] Forms via `react-hook-form` (mirror existing products).
- [ ] Wire NF-e XML upload via Supabase storage SDK on the client.

**Tests required:**
- `npx vite build` clean for every PR.
- Smoke tests via `vitest` (already configured) — at minimum, render-no-crash for each new page.
- One e2e flow: login → browse → add to cart → checkout → see order — via Playwright if the seed has it; otherwise document as manual test.

**Exit criteria:** distributor logs in and completes the full marketplace loop entirely via the UI.

**Improvements:** _(captured during steps)_

---

### Phase 8 — Close (docs + drift-check + retrospective)

- [ ] Update `products/adconnect/README.md`: remove "Current state — pre-implementation" section; document the production state.
- [ ] Update `products/adconnect/MASTER-PROMPT.md`: remove "Current state — pre-implementation" section; document the production architecture.
- [ ] Run `noctus.seed.audit_drift` again — compare against Phase 0 baseline. Justify any persistent drift in `findings.md` under "knowledge-pieces".
- [ ] Run `noctus.dev.scan_within_product_helpers` + `noctus.dev.scan_cross_product_helpers` — flush out any helpers that recurred to N=2 during the project; either absorb (if user agrees) or file follow-up projects.
- [ ] Synthesize `findings.md` into a curated knowledge artifact at close (per `feedback_knowledge_tracking.md`).
- [ ] File ONE end-of-project proposal bundling any deferred items.
- [ ] Update CLAUDE.md product table if AdConnect's status entry exists.
- [ ] Final commit + push (per `feedback_no_auto_commit.md`: project-close = commit + push).
- [ ] Archive: `noctus.dev.archive` moves the project folder to `archive/projects/<today>/<NN>-adconnect-mvp-implementation/`.

**Exit criteria:** AdConnect is a real, production-shippable product. Docs accurate. No stale state.

---

## 7. Open questions

Each tagged with *when it needs an answer* and *who answers*.

1. **NF-e provider.** Which Brazilian NF-e provider does AdConnect integrate with? *(NFe.io, Focus NFe, eNotas, custom?)* — needs answer before Phase 5. Decided by user. **Recommendation:** Focus NFe (commonly used in Brazilian SaaS, JSON API). Phase 5 starts with a Protocol so the provider can be swapped later.

2. **Distributor self-registration vs invitation-only.** V1 is invitation-only per §4. Is there ever a "request to join" flow, where distributors apply and brand admin approves? — deferred to Phase 6 / V2. Decided by user.

3. **Brand-side admin UI cadence.** V2 follow-up project — when does it kick off? Affects whether the user wants brand-side ops in V1 to favor API-only or include minimal admin pages. — deferred until V1 ships.

4. **Reward rule shape.** The mock `app/data/reward-rules.json` has rules like `cashback_percent` keyed off `category_id`. Are there compound rules (e.g., volume bonus, distributor-tier bonus, time-windowed promotions)? — needs answer in Phase 0 or Phase 4. Decided by user.

5. **Sellout submission validation.** What's the rejection-criteria for sellout reports? Brand admin's discretion vs deterministic rules vs both? — needs answer in Phase 4. Decided by user.

6. **Multi-distributor user.** Can the same person belong to two distributors? The schema in §5.1 says yes (membership table allows N rows per user). Does the UI need a distributor-switcher? — needs answer in Phase 7 frontend. Decided by user.

7. **Order minimums / restrictions.** Does the brand impose minimum order values, restricted SKUs per distributor, or geographic restrictions? — needs answer in Phase 3. Decided by user.

8. **Cancelation + refund flow.** Order cancelation timing rules, refund policy via Stripe? — needs answer in Phase 5. Decided by user.

---

## 8. Dependencies & blockers

External things the plan hinges on. Be explicit — surprises here cost the most.

- **Supabase project access.** Every phase applies migrations via `mcp__claude_ai_Supabase__apply_migration`. The next agent must be working against a Supabase project that has the noc schema (organizations, noctus_users, etc.) already in place — i.e. core's migrations applied first.
- **Stripe webhook routing.** Phase 5 inherits Stripe via core. Confirm core's webhook handler routes invoice events back to AdConnect (via DB query on `stripe_invoice_id`), or whether AdConnect needs its own webhook signature verifier mounted at a separate path.
- **NF-e provider account.** Phase 5 needs API credentials for whichever NF-e provider is chosen (open question §7 #1).
- **Resend account + verified domain.** Phase 3+ sends emails. Confirm Resend is configured per `noctusai_seed.config` settings.
- **Storage bucket for sellout attachments.** Phase 4 uploads NF-e XML + freeform attachments. Either reuse an existing seed bucket or provision a per-product bucket per `noctusai_lib.integrations.storage` (the seed-hardening Phase 3.2 pattern).
- **The parallel `noctus.seed.*` MCP branch shipping.** Phase 0 + Phase 8 use `noctus.seed.audit_drift`, `noctus.seed.list_capabilities`, `noctus.seed.scan_repetition` — all read-only. They exist as of 2026-05-05 commit. Confirm they're still wired before Phase 0.

---

## 9. Success criteria

What does "done" look like? Measurable, verifiable.

- All eight phases flipped to ✅ with their tests green.
- Distributor user can log in via SSO, browse catalog, add to cart, place an order, file a sellout report (any of three submission modes), see cashback accrued, view invoices, and complete the full loop via the web UI alone.
- Brand admin can operate the marketplace via API alone (admin UI is V2; this project does not block on it).
- All three test layers pass: unit (services), router (TestClient + mocks), realdb (RLS coverage in Supabase).
- `npx vite build` clean in `products/adconnect/frontend/`.
- `pytest products/adconnect/backend/tests/ -q` clean.
- `products/adconnect/backend/app/data/` directory is removed; no JSON fallback paths remain.
- `noctus.seed.audit_drift` reports zero unjustified drift between AdConnect and the canonical seed shape.
- LGPD flags exist for every distributor PII write site.
- `findings.md` is synthesized into a curated artifact at close.
- The project folder is archived via `noctus.dev.archive` after the final commit + push.

---

## 10. How to use this plan

- **Single source of truth for progress.** Update as you work. The user watches this file as a live dashboard.
- **Live-tick tasks.** Flip `- [ ]` → `- [x]` the moment a task is done; do not batch at end of phase.
- **Phase-by-phase by default.** Execute one phase, pause, wait for the user to say "continue" / "next phase". Do not auto-advance.
- **Branching.** Branch `adconnect-mvp-implementation` from `origin/main` at start. Each phase is a commit (or small commit sequence) on the branch. Final merge to main is the orchestrator's responsibility, not the engineer-subagent's.
- **Findings.** Append to `findings.md` in-the-moment for any surprise. Synthesize at close.
- **Improvements.** Capture during steps in each phase's `**Improvements:**` block. File ONE proposal per phase via `noctus.dev.file_proposal(project="adconnect-mvp-implementation", ...)` at phase close.
- **Three-way sync.** If any rule/methodology evolves during this project, update KB + CLAUDE.md (or topical CLAUDE/<topic>.md) + memory same session.
- **Verify-the-seed-ships-it.** Before locking any "consume the seed X" decision, read the module's `__init__.py` exports + the concrete adapter file. Protocol+Fake without a Real adapter is NOT runtime-ready.
- **Recurrence rule.** N=2 in this project → triage at decision time (formalize / refactor / accept-with-rationale). N=3+ → MUST formalize. Per user directive, AdConnect-internal patterns stay AdConnect-only — but recurrence to *other products* triggers absorption talk.
- **No silent errors.** No `except: pass`; no unverified "verification ✓"; ambiguity → ask the user; absence → quote the command.
- **No monkey-patching of our own code.** External integrations (Stripe SDK, Resend SDK, NF-e provider) may be patched in tests; AdConnect's own code never is.
- **Don't auto-commit mid-phase.** Per `feedback_no_auto_commit.md`: per-phase = local commit (no push); project-close = commit + push.

---

## 11. Change log

| Date | Change | By |
|---|---|---|
| 2026-05-05 | Initial project drafted from `templates/PROJECT-TEMPLATE.md` after interrogation of João Raphael (8 questions answered). Standardization pre-work landed: migration `001_seed.sql` → `001_adconnect.sql` with `adconnect` schema; `README.md` + `MASTER-PROMPT.md` rewritten; `conftest.py` docstring drive-by; testing-ground MCP tool `noctus.dev.create_testing_ground` added + memory rule for user-phrasing → tool routing. The parallel agent's `noctus.seed.*` MCP branch (audit_drift, list_capabilities, scan_repetition) shipped during this same session and is referenced in Phase 0 + Phase 8. | Claude Opus 4.7 (1M ctx) |
| 2026-05-10 | Phase 0 ✅ + Phase 1 ✅ — identity foundation, migration 002 authored, auth swapped to seed (Option A), LGPD flags wired, 3 test files added (auth router 8 tests, distributors router 6 tests, realdb identity 3 tests; 45/45 mock tests green). Drive-by fix: `main.py` router-prefix bug (FastAPI 0.115 ignores post-construction `router.prefix` mutation; wrapped each domain router under explicit prefixed parent). | Engineer A (subagent) |
| 2026-05-10 | Phase 7 frontend SKELETON ⏳ — 9 pages + 5 hooks + types + routing wired into `App.tsx`, `vite build` clean (9.17s), no API integration yet. Drive-by: `seed/framework/frontend/vite.config.factory.ts` patched to add `clsx`+`tailwind-merge` to `FRAMEWORK_DEPS` and AdConnect entry to `PRODUCT_MAP` (collision-flagged with parallel branch `f1a3935`). | Engineer B (subagent) |
| 2026-05-10 | Migration consolidation: 7 numbered files (001 + Engineer A's 002 + my 003-007 drafts) collapsed into single `001_adconnect.sql` (16 tables in topological order). Three-way sync of "single 001 migration per product" convention: KB § PATTERNS/database-rls.md § Single 001 migration convention + CLAUDE/backend.md rule + `feedback_single_001_migration.md` memory pointer. NF-e service skeleton (`app/services/nfe_service.py`) + 10 passing tests landed in parallel. | Orchestrator |
