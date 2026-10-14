# ERP seed → template for market ERPs — roadmap (2026-10)

> **Status:** IN PROGRESS 2026-10-14. Owner delegated every decision ("dont ask me anything, go all the to the end and to the prod … build. i'll refine later"; "recommended paths by you always"). Every E-decision below is a **tech-lead default — owner refines later**.
> **Method:** `KB § PATTERNS/architect/vertical-seed.md` (same as `commerce-seed-2026-10.md`) · accounting authority: agent `accountant` + `KB § PATTERNS/finance/dre-structure.md`.
> **Inputs:** ERP codebase map (2026-10-14, Explore) · architect design (2026-10-14) · ERP market brief [`erp-seed-2026-10-market-brief.md`](erp-seed-2026-10-market-brief.md) · commerce P4 decisions D32–D56.

## Origin

2026-10-14, owner: *"Full erp module seed, as we're building the ecommerce seed on other agents. Same idea"*; *"same mentality: seed first, specs to market later. we have to develop the erp seed and save it. then we'll specify to the product's market"*; *"later on we'll use erp seed to create other erp systems to different markets, but let's start with the seed, with multiplication possibilities to other markets as a template for starters"*. Earlier the same day: build the full financial structure, make it a seed other products consume, fan it out, ship to prod, and report on finances per product.

## Layers

```
L0 noc seed           auth, SSO, app factories
 └ L1 ERP organs      noctusai_lib/domain/{finance, parties, items, inventory, purchasing, quotes, contracts}
                      + FE organs @noctusai/lib/<x> + templates/product-erp overlay
     └ L2 market ERP  scaffolded later from the overlay (noc-new-product overlay=erp), one per market
         └ L3 client  one org per client
```
Commerce is a sibling vertical seed that **consumes** ERP organs (finance bridge, items, stock port).

## Decision log (append-only)

- 2026-10-14 · **E1 reference host = `products/commerce`** — no new product (a new prod product needs the owner's own consent phrase). It is prod-authorized and the only host exercising commerce↔inventory.
- 2026-10-14 · **E2 v1 modules, in order** — W0 finance + structured DRE + FE organ → W1 `parties` (PF/PJ, CPF/CNPJ, roles customer/supplier/employee/carrier) + `items` (sku, unit, NCM/CFOP/CEST, `item_type` seam) → W3 `inventory` (warehouses, append-only stock moves, balances, moving-average cost, `StockPort.reserve/commit/release`) → W3 `purchasing` (PO → receipt → stock in + AP entry; approval = permission `purchasing.approve` + threshold) → W4 `quotes` (N=3 in igig/erp-imob/social-wiring) + `contracts` (recurring billing over finance recurrences; N≥3) → W5 ERP dashboard (FE only) + `templates/product-erp` overlay.
- 2026-10-14 · **E3 later (named destinations, not v1)** — HR/payroll + time entries (igig `apontamento`, N=1), work orders (erp-imob `manutencao`), CNAB remittance, commissions/splits, fixed assets, tax apportionment, marketplace sync, multi-currency.
- 2026-10-14 · **E4 parties link, don't absorb** — `commerce_customers` stays authoritative (LGPD, consents); it gets a nullable `party_id` later. `fin_entries` gets nullable `party_id`, keeping `counterparty_*` as a snapshot.
- 2026-10-14 · **E5 items ≠ commerce catalog** — commerce `offers` are a sales-channel concept; `commerce_products.item_id` nullable FK; stock applies only when set (digital products need none).
- 2026-10-14 · **E6 stock in commerce through the fulfillment handler** — order created → reserve, paid → commit, expired/revoked → release (closes D35 "stock released"). Single-statement RPC + row lock + `CHECK (on_hand - reserved >= 0)` (stock=1 pieces, D8). Real CMV replaces D56's "purchases of the month".
- 2026-10-14 · **E7 sales orders = commerce orders** in v1; staff/manual orders are a commerce `channel` value.
- 2026-10-14 · **E8 placement** — backend `noctusai_lib/domain/<x>/` (config/types/sql generator/router/services/errors), prefixes `pty_ itm_ inv_ pur_ quo_ ctr_`; cross-organ FKs only when both organs are mounted (generator flags). FE `seed/lib/frontend/src/<x>/`, each page registered as an organ.
- 2026-10-14 · **E9 one-call mount** — `mount_finance(...)` (generalizing to `mount_organs([...])`) in `noctusai_seed`, + an MCP tool that renders an organ's migration into a product (`next_migration_number`) + a seed-inherited test pinning file == generator. The FE shell mounts `/financeiro` from the product manifest, gated by `status_pagina`.
- 2026-10-14 · **E10 finance fan-out** — mount in commerce (pilot), seed (template inherits), academia-de-reciclagem, agents, social-wiring, core (noc's own platform finances, platform org) and igig **in parallel** to its live NUMERIC finance (untouched). igig cutover = importer `domain/finance/importers/igig.py` (NUMERIC → cents, half-even via one seed `to_cents`, reconcile to the cent, dry-run first), retire igig finance only after one matching monthly close — `NOC-REMEDIATE[igig-finance-cutover]`.
- 2026-10-14 · **E11 per-product finance report is measured** — predeploy_check (schema exposure/drift, db guards) + spa_smoke `/financeiro` + sso_smoke, one row per product.
- 2026-10-14 · **E12 risks owned** — migrations re-runnable + `migration_replay` (applied twice) before `migrate_product`; RLS + org-picker path + strict 401 tests per table; NUMERIC→cents policy decided once in seed; stock concurrency guarded at the DB.

- 2026-10-14 · **E13 regimes** — data model covers MEI, Simples and Lucro Presumido (regime is a profile field); MEI + Simples get the deep behaviour first (Livro Caixa, Relatório Mensal de Receitas Brutas, DAS views). Presumido obligations (EFD-Contribuições, EFD ICMS/IPI, ECF) are the accountant's files — the seed exports data, never files.
- 2026-10-14 · **E14 inventory is generic** (brief §C: every operational ERP has it); valuation **average cost** (LIFO not permitted; brief §B). Lots/serials, Bloco K and production/BOM are market-specific.
- 2026-10-14 · **E15 bank feed** — v1 is OFX/CSV import (already in finance) + a `BankFeed` Protocol + Fake; a Real Open Finance aggregator adapter (e.g. Pluggy, ≥ R$2.500/mo) waits for a paying market. ERP cannot join Open Finance directly (brief §E).
- 2026-10-14 · **E16 accountant export** — new seed module after purchasing: Domínio layout first (documented), CSV/OFX already exist; an accountant **read-only role** instead of a white-label portal in v1.
- 2026-10-14 · **E17 NFC-e / PDV** — retail-market specific, not in the generic seed (SP requires NFC-e since CF-e-SAT ended 2026-01-01 — note for the artifacts store).
- 2026-10-14 · **E18 payroll** — via the accountant (no operational ERP in the brief ships native payroll); the seed keeps people as `parties` role employee + AP entries.
- 2026-10-14 · **E19 IBS/CBS** — the fiscal profile gets the 2027 "IBS/CBS inside or outside the DAS" choice now (data only, default "inside", provisional — contador); invoice IBS/CBS fields per NT v1.52 when the fiscal adapter is next touched.
- 2026-10-14 · **E20 one org = one CNPJ** — an owner with several CNPJs uses several orgs (multi-org exists); consolidated view later.
- 2026-10-14 · **E21 finance additions** — budget vs actual per category/month, Livro Caixa view, MEI monthly revenue report, an optional accounting code per category (for the Domínio export). Added to W5.
- 2026-10-14 · **E22 pricing/packaging** — not a seed concern; decided per market product (P12 of the commerce roadmap). Brief §D records the market levers (revenue band, users, feature tiers, AI credits).

- 2026-10-14 · **E23 commerce mounts the ERP organs (W3-W4 on the reference host)** — `products/commerce` mounts purchasing, quotes (+ the public signed accept link) and contracts (billing job on the seed scheduler). **Link delta, not a revision:** `commerce_products.item_id` (composite FK to `itm_items`), `commerce_orders.channel` (`storefront` | `manual`, E7) and `commerce_orders.source_ref` (`UNIQUE (org_id, source_ref)`: the idempotency key of an order made from a quote) ship as their own generator + registry organ `commerce_erp` (`domain/commerce/erp_sql.py`, requires `items` + `commerce_money`), because `012`/`014` are applied and frozen; `payment_method` / `gateway` become nullable (a manual order has no charge yet). Closes `NOC-REMEDIATE[items-commerce-link]` and `NOC-REMEDIATE[commerce-purchasing-mount]`.
- 2026-10-14 · **E24 stock in commerce = a fulfillment handler, held BEFORE the order exists** — `StockFulfillment` (`on_created` reserve / `on_paid` commit / `on_expired`+`on_cancelled`+`on_revoked` release) on the physical fulfillment types; only lines whose product has `item_id`; the order id is the stock ref, so every call is idempotent. An oversell refuses the checkout with 409 `estoque_insuficiente` and writes nothing (coupon given back). A paid order whose hold expired re-holds under `<order>:late` (the inventory RPC never re-reserves a released ref); if even that is refused the sale stands and the shortage is logged (`NOC-REMEDIATE[commerce-stock-short-alert]`). Refund/chargeback after commit does not restock (`NOC-REMEDIATE[commerce-return-to-stock]`).
- 2026-10-14 · **E25 accepted quote converts through seed handlers** — `RoutingQuoteAcceptHandler` (quotes) routes `convert_to`: goods → `CommerceQuoteAcceptHandler` (a `manual`-channel order in `created`, idempotent on the quote id, party → commerce customer, lines linked to the product of the same `item_id`, stock held; a party without e-mail / a fractional or free line fails the conversion in pt-BR and is retried after the fix), services → `ContractQuoteAcceptHandler` (a DRAFT contract for exactly the accepted total — header discount spread to the cent). Open: `NOC-REMEDIATE[commerce-manual-order-charge]` (a payment link for a manual order).

## Waves

| Wave | Slices | Class |
|---|---|---|
| W0 | finance DRE backend → finance FE organ (+ installment refunds, commerce) | sequence on `domain/finance` |
| W1 | `mount_finance` + migration-render tool ∥ `parties` ∥ `items` | disjoint |
| W2 | finance fan-out to 7 hosts ∥ `inventory` | disjoint; migration numbers from the tool |
| W3 | commerce↔inventory ∥ `purchasing` | serialize the commerce migration slot |
| W4 | `quotes` ∥ `contracts` | disjoint |
| W5 | ERP dashboard + `templates/product-erp` overlay + igig importer dry-run + accountant export (Domínio) + finance additions (E21) | disjoint |

Gate: `gate_sweep` on the merged dev tip before each bless; prod via `noc-ship` (predeploy_check + CI green; migrations via `migration_replay` then `migrate_product`).

## Prod exposure

No new product. The finance pages ship inside already-live products; page visibility through `status_pagina`.

## Anti-goals

- No per-client or per-market code in L1 organs.
- No merge of `commerce_customers` into `parties` in v1.
- No touching igig's live finance tables before the importer reconciles.
- No market ERP scaffolded to prod by an agent — market ERPs stop at `deploy_scope='dev'` until the owner consents.

## Composes with

`commerce-seed-2026-10.md` (D32–D56) · `projects/commerce-seed-p4/CONTRACT.md §10` · agent `accountant` · `KB § PATTERNS/architect/vertical-seed.md`.
