# Commerce seed P3 — commerce core — Project Document

> Living document. Zero-context reader: start with the roadmap `project-history/roadmaps/commerce-seed-2026-10.md` (decisions D1–D29, phases P0–P13), then this file, then `CONTRACT.md` (the exact shapes every slice builds to). Live tracker: https://claude.ai/artifact/4mn1fH7nk2fsVeKQHdGdr4.

- **Created:** 2026-10-12
- **Last updated:** 2026-10-13
- **Status:** ✅ Phase 1 closed 2026-10-13 — slices A–D + D30/D31 + hardening on dev; next phase P4 (money)
- **Owner / stakeholders:** noc owner · tech-lead session · architect (advisor)
- **Related docs:** roadmap + market brief + digital-products companion · `KB § PATTERNS/architect/vertical-seed.md` · `KB § PATTERNS/architect/approved-cutover.md` · `KB § CONTEXT/GUIDES/new-product.md § Market products from a vertical seed` · `CONTRACT.md`
- **Project slug:** `commerce-seed-p3` (cross-product seed work → `projects/`)

---

## 1. Context & Purpose

P3 builds the generic commerce spine as **L1 seed organs** (`noctusai_lib/domain/commerce`, `@noctusai/lib` `commerce/*`) plus a reference host product `products/commerce` where the owner validates a generic store end to end (gate T2) before any market (photo → artifacts → Gilson's Store) is specialized.

## 2. Confirmed constraints

- **Layering (D1, D18)** — shared organs → one product per market → client = org; client-specific code only via packs. *(Rules out per-client branches in the organ.)*
- **Buyers (D26)** — guest checkout + magic link to "my orders"; enrich the customer record from form data AND payment data, **payment is the source of truth**. *(Field-level provenance in `commerce_customers.field_sources`.)*
- **Payments (D5, D27)** — Asaas first; each client's own Asaas account; **noc fee via Asaas split**, chosen after checking Asaas pricing (no published split fee; split computed on net value; refunds reverse the split; chargeback handling undocumented → fee counted only when settled). Fee rate is per org (`platform_fee_bps`, default 0) and only the platform admin sets it. *(Asaas list prices 2026: Pix/boleto R$1,99 each (R$0,99 first 3 months), card R$0,49 + 2,99% à vista — shown as estimates in the offers editor because flat fees dominate low-ticket items.)*
- **Addresses (D28)** — slug `commerce`, back office `commerce.noctusai.com`, one explicit test storefront subdomain for validation (owner consent flow); wildcard subdomains in P12.
- **Coupons (D29)** — percent or fixed, optional expiry + usage limit; bumps/upsells/affiliates later.
- **Store profile (D9, D16, D24)** — CNPJ required + check-digit validated; tax regime selectable; tax treatment per product type (photographer default `rights_receipt`); language + currency switchable.
- **Gilson (D25)** — not a lawyer; contract templates sold as templates with disclaimers (affects P13, not P3).

## 3. Design principles

1. Organs own tables through a pure SQL generator rendered into each product's own schema (card_hub precedent: `domain/card_hub/sql.py` + `products/igig/backend/migrations/019_card_hub.sql` + parity test).
2. Every external IO is Protocol + Fake + Real + factory; routers are factories taking the product's dependencies.
3. Buyers are NOT `noctus_users` (one-org-per-user model would collide across stores); per-org `commerce_customers`.
4. Price is always recomputed server-side; the order state machine is a pure function; every transition is an append-only event.

## 3a. Seed-first analysis

1. Contract identical for every product? **YES** — every market product gets the same catalog/checkout/order API.
2. Data source product-specific? **NO** — tables are generated per schema from one generator.
3. Placement product-specific? **NO** — `/admin/*` + storefront `/` in every market.
4. Visibility rule the same? **YES** — staff = license gate + org roles; storefront = host → org + active license.
5. Seam exists? **Partly** — payments organ + api_keys + identificador + cnpj_registry exist; commerce organ, event-inbox DDL generator and storefront host resolution are new.
6. Default-on? **OPT-IN** per product (commerce-family products only).

**Litmus:** a small section per product (config + generated migration + mounts + pages). Phases work in the seed; `products/commerce` is the reference wiring.

## 4. Scope

**In scope:** store profile + versions; storefront hosts; categories; products (`product_type`/`fulfillment_type` seams); offers with fee estimate; media (private bucket); coupons; customers + consents + privacy requests; quote + checkout (Asaas hosted checkout, Pix QR) + public order view + magic link; order state machine + events + webhook; host product `commerce`.

**Out of scope (later phases):** refunds/installments/chargeback states in the payments organ (P4), invoices (P4), digital delivery + downloads + license certificates (P5), products-inside-products MCP tools (P5), shipping (P9), buyer accounts with passwords (later), wildcard subdomains (P12).

## 4a. Dispatch routing

### 4a.1 Slice → Lens table

| Slice | Lens | Files | Dispatched as |
|---|---|---|---|
| A · backend organ | backend-engineer | `seed/lib/backend/noctusai_lib/domain/commerce/**`, `domain/payments/event_inbox_sql.py` (new), `seed/lib/backend/tests/domain/commerce/**`, `domain/__init__` export | Agent dispatch, worktree `commerce-p3-organ-be` |
| B · host product | backend-engineer | `products/commerce/**` backend + migrations + `start.sh` + port reservation + products row migration | Agent dispatch, worktree `commerce-p3-host`; scaffolds first, wires A's routers after A integrates |
| C · frontend organ | frontend-engineer | `seed/lib/frontend/src/commerce/**`, `seed/lib/frontend/src/index.ts` barrel | Agent dispatch, worktree `commerce-p3-organ-fe`; first commit `types.ts` |
| D · host pages | frontend-engineer | `products/commerce/frontend/src/**` | after B scaffolds + C's types land |

### 4a.2 Codification expectations

| Slice | s1 | s2 | s3 | s4 | Why |
|---|---|---|---|---|---|
| A | yes | no | yes (organ KB doc in `04-SHARED-LIBRARY.md`) | no | new canonical organ |
| B | yes | no | no | no | reference wiring; triage a `scaffold_product(vertical=…)` overlay at market #2 |
| C | yes | no | yes (organ catalog) | no | new canonical FE organ |

### 4a.3 Routes-not-taken

| Route | Why rejected |
|---|---|
| Evolve `products/store` into the spine | single-org (`STORE_ORG_ID`, no `org_id` on orders); its prod consent covers another surface |
| Buyers as `noctus_users` / `membro` | one org per user collides across stores; drags SSO + license gate into a public storefront; unknown auth triggers on `auth.users` |
| One shared `commerce` schema for all markets | per-market schemas keep the L3 dedicated-instance export cheap |
| Store profile in `org_settings` | untyped key/value text; secrets don't belong there either |
| Platform-owned Asaas + split to clients | noc would hold client money flow; owner chose client accounts + noc fee split (D27) |

### 4a.4 Notes

Each slice files a delivery note (`noctus.dev.file_proposal kind="delivery" project="commerce-seed-p3"`) with the two-leg footer (`drift-found:` / `scoped-improvement:`). A better route ⇒ surface note, block, wait.

## 5. Architecture / Data Model

See `CONTRACT.md` (enums, transitions, tables, staff + storefront + webhook API, FE organ, host product). Mining map of `products/store` (lift/keep/discard per file) is recorded in the tracker task t300 and summarized: lift checkout/webhook/assets/settings-ledger/key-tester patterns; keep landing + landing editor for Gilson's market (P13); discard boilerplate, `STORE_ORG_ID`, email allowlist, duplicated CPF/BRL helpers.

## 6. Implementation phases

### Phase 1 — Organs + reference product ✅
- [x] A · `domain/commerce` organ: types, order_state, sql generator, services (+ Fakes), router factories (staff, storefront, webhook), host resolver, `event_inbox_table_sql`; tests incl. per-table org isolation + generator snapshot
- [x] C · `@noctusai/lib` commerce organ: `types.ts` (parity with A's enums), hooks, staff + storefront components
- [x] B · scaffold `products/commerce` (ports, start.sh, products row `ativo=true, deploy_scope=dev`), generated migration + parity test, mounts, Asaas api-key spec + tester
- [x] D · `products/commerce` pages: `/admin/*` + storefront `/`
- [x] Merged-tip gates (pytest organ + product, vite build product, mcp tests if counts changed); `noc-wiring-audit` on `products/commerce`
- [x] Trial observations logged on `vertical-seed-commerce` and `new-product-v2`

Shipped: A `e0d18d4bd` · C `7fc41149c` · B `2737bbb33`+`f013e0f0c` · D `7ebe8e0f0`..`5adccf6c9` · D30 fiscal retention `5a1e2df7e` · D31 secdef-by-construction `0bedda8c8` · organ hardening `91e2c21cd` · core test fix `9b0d3f09d`. Merged-tip suites re-run by the tech-lead where integrate timed out: seed lib 8447 · igig 1052 · commerce 86/72 + vitest 28 · migration replay green. Wiring audit: green except one scanner false positive (factory-built organ routers).

**Improvements:**
- **Shipped this phase:** secdef keeper now verifies `rls-helper` markers against real policy references and the template is compliant by construction (D31); org-picker-aware organ default `current_org_id_for(<schema>)`; real rate limiter as a standing organ-test guard; Asaas environment selector + seed readiness verdict; core 070 schema-map test derives from post-070 seed-row migrations instead of a closed list.
- **Open (named destinations):** `scaffold_product` should append the FE test matrix, seed per-page `status_pagina` rows, and drop the example router/webhook (trial `new-product-v2`); `task_branch` should re-wire node_modules after a scaffold; `scan_wiring` should resolve seed-lib factory routers and typed `api.get<T>` calls; seed deep-link restore when `/` is public; `templates/product-seed-divergences.json` now holds 4 same-cause divergences (immutable seed originals) — consider a forward-migration mechanism; tracker owner-question ticks must ask for confirmation before acting (trial `learn-refine-self`). FE organ gaps D1–D8 → `NOC-REMEDIATE[commerce-*]` markers, triage at P5.

## 7. Open questions

1. **Asaas chargeback + split** — does a chargeback reverse the split? Ask Asaas support before P4 (fee counted only when settled until then).
2. **Auth triggers on `auth.users`** — ANSWERED 2026-10-13: both live in prod; every new auth user gets an `erp.profiles` row + ERP `corretor` role. Guest checkout unaffected (signed tokens, no auth users). Buyer password accounts need their own design before that phase.
3. **noc's Asaas wallet** — the platform wallet id for the fee split; owner to provide when fees are switched on.

## 8. Dependencies & blockers

- Asaas sandbox keys for the e2e test (P4/P6).
- Owner consent phrase for the test storefront hostname (P6).

## 9. Success criteria

- Organ + product tests green on the merged tip; generator snapshot and per-table org-isolation tests pass.
- `products/commerce` builds and serves `/admin` and a host-resolved storefront locally with real data from the organ endpoints (wiring audit green).
- No per-client or per-market branch in organ code (trial `vertical-seed-commerce`).

## 10. How to use this plan

Live-tick tasks; revise when understanding changes; contract changes go through the tech-lead and are logged below.

## 11. Change log

| Date | Change | By |
|---|---|---|
| 2026-10-12 | Created from the P3 Phase-0 audit + owner answers D26–D29 | tech-lead |
| 2026-10-13 | Owner decisions D30 (fiscal retention) + D31 (secdef by construction); Phase 1 closed; Q2 answered | tech-lead |
