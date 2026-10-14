# Vertical seed — a seed for a market family, specialized per market, then per client

> **Rule.** When several products will serve the same *kind* of business (e-commerce, ERP, CRM), build a **vertical seed** first: the organs every market in that family needs, in the shared library, plus a product template. Each **market** becomes one noc product built from it. Each **client** is an org inside that market product. Client differences are **settings first, client extension packs second, dedicated instances last** — never `if org == …` in shared code.

Born 2026-10-12 from the commerce seed run (`project-history/roadmaps/commerce-seed-2026-10.md`): one generic e-commerce + ERP seed → photo store, artifacts store, Gilson's Store. Earlier intent with the same shape (`erp-imob`: "ERP seed → real-estate specialization") was never written down and the product shipped as a plain CRM — this file is that missing record.

---

## 1 · The four layers

| Layer | What it is | Lives in | Example (commerce) |
|---|---|---|---|
| **L0 noc seed** | the skeleton every product inherits | `products/seed/`, `noctusai_seed`, `@noctusai/seed` | auth, SSO, app factories, license gate |
| **L1 vertical seed** | organs + a product template for one market family | `noctusai_lib/domain/<family>/*`, `noctusai_lib/integrations/*`, `@noctusai/lib` components, template product | catalog, checkout, orders, payments, finance, invoices, fulfillment seams |
| **L2 market product** | one noc product per market, built from the L1 template | `products/<market>/` | photo store · artifacts store · Gilson's Store |
| **L3 client** | one org per client inside the market product | `org_id` rows + org settings | the photographer, the artifacts shop, Gilson |

**Placement test** (extends the 4-question test in `../../03-SEED-ARCHITECTURE.md`):

1. Needed by **2+ market families** → L0 / generic `noctusai_lib`.
2. Needed by **2+ markets of this family** → L1 (organ with a named seam where markets differ).
3. Needed by **one market** → L2, behind an L1 seam.
4. Needed by **one client** → L3: a setting if it's data; a **client extension pack** (§3) if it's code.

A thing that lands in the wrong layer is a structural fork (`../../03-SEED-ARCHITECTURE.md § Named seams vs structural forks`). Recurrence moves things *up*: the second client wanting a pack feature triggers triage to an L2 setting/seam; the second market wanting an L2 feature triggers triage to L1 (`project-execution.md` DRY rule, N=2 → triage).

## 2 · Named seams a vertical seed must declare up front

A vertical seed is only reusable if the places where markets differ are **named before the first market is built**. For commerce:

| Seam | Values / shape | Why |
|---|---|---|
| `product_type` | `digital` · `physical` · `service` · `print_on_demand` | one catalog, different data per type |
| `fulfillment_type` | `digital_delivery` · `shipping` · `pickup` · `local_delivery` | one order state machine, different fulfillment legs |
| `tax_treatment` | per product type, per org (regime: MEI / Simples / other) | invoices differ per market and per client; some cases are legally unsettled |
| payment gateway | Protocol + Fake + Real per gateway (`integrations/payments`) | client brings their own account |
| shipping provider | Protocol + Fake + Real (aggregator first) | physical markets only |
| invoice provider | Protocol + Fake + Real; variants switch via `approved-cutover.md` | regulation changes on a date |
| AI provider | Protocol + Fake + local + cloud | measure local before paying for cloud |
| storefront layout | theme tokens (settings) → layout slots → full layout override (pack) | brand → structure, cheapest first |
| lifecycle hooks | `order.paid`, `order.fulfilled`, `product.published`, … | where client scripts attach (§3) |

## 3 · Client extension packs — client-specific CODE, contained

Owner requirement (2026-10-12): a client may want a structurally different layout or a script no other client uses, so client-specific changes **can be code**. They live in a pack, never in shared code.

```
products/<market>/clients/<client-slug>/
  pack.yaml            # org_id, owner, what it overrides, hook list, blocking|advisory per hook
  backend/             # hook handlers + optional routes under /c/<client-slug>/
  frontend/            # layout override / slot components / storefront scripts
  tests/               # run in CI like any product test
```

- **Loaded only for that org.** The market product reads a pack registry keyed by `org_id`; the registry is the ONLY place an org id selects code. Shared code calls seams (`hooks.emit("order.paid", …)`, `<LayoutSlot name="storefront.header">`), never a client name.
- **Seams only.** A pack may fill a declared seam (layout slot, full layout override, lifecycle hook, namespaced route, extra JSON fields on its own rows). It may not edit shared modules, shared schema, or another pack. Needs a new seam → add the seam to L2/L1 first (that's a product change, reviewed as such).
- **Failure is visible, never silent.** Each hook declares `blocking` (failure stops the operation with an error the operator sees) or `advisory` (operation continues; failure is logged + raised as an admin alert). No swallowed exceptions (`01-PHILOSOPHY.md` no-silent-errors).
- **Own data.** Pack tables live in the market schema with a `client_<slug>_` prefix and `org_id` + RLS like any table; no cross-org reads.
- **Promotion.** A pack feature a second client wants is triaged up (setting → L2 seam → L1 organ). Packs are the place for genuinely one-off code, not a backlog of unpromoted features.
- **When a pack outgrows the shared process** (different runtime deps, heavy compute, its own release cadence) → move the client to a dedicated instance (§4 level L3) running the same image + its pack.

## 4 · Client isolation levels (upgrade path)

| Level | Client gets | Setup | Ongoing cost | Blast radius |
|---|---|---|---|---|
| L1 Branded tenant (default) | brand, subdomain, keys, prices, catalog | none | ≈0 | a bug/bad deploy hits every client of the market |
| L2 Extended tenant | + client extension pack (§3) | a pack + its tests | low, one codebase | as L1 + their pack (contained by seams + hook policy) |
| L3 Dedicated instance | same image (+ pack), own container + own schema or Supabase project | org export → deploy → DNS → webhooks (~½ day with tooling) | +1 container (~0.3–0.5 GB RAM), Supabase Pro ≈US$25/mo if separate, every deploy/migration ×N | only that client; releases fan out per instance |
| L4 Personalized fork | own product derived from the market product | new product from the L2 template | highest — drift; each seed fix merged + verified per fork | only them; maintenance compounds |

**Preconditions built from day one** so L2–L4 stay cheap: everything keyed by `org_id` with RLS; per-client config in org settings (`resolve_credential` org → platform → env); storage paths prefixed by org; per-org export/import (LGPD portability too); the product image supports a single-org mode pinned by config; packs load from the registry, so the same image serves L2 and L3. Always pick the **lowest** level that satisfies the client (roadmap trigger T4).

## 5 · Specs at each layer

- **Vertical spec** (L1): module classification table — generic vs per-type vs per-market (commerce: `project-history/roadmaps/commerce-seed-2026-10-market-brief.md § E`).
- **Market spec** (L2): the market's interview answers + vertical modules switched on + market-only modules.
- **Client spec** (L3): org profile (legal name, CNPJ validated, tax regime, language, currency, brand, subdomain), keys, catalog, pack (if any).

Procedure for building a market product from a vertical seed: `../../GUIDES/new-product.md § Market products from a vertical seed`.

## Mounting an organ: one call

An organ is bound to a product by `noctusai_seed.organs`, not by a per-product 3-file binding (the commerce host's ~180 LOC is the pre-seam shape):

```python
from noctusai_seed.organs import mount_finance
finance = mount_finance(schema="erp", auth_dependency=get_current_user_org,
                        get_admin_client=get_admin_client, get_core_client=lambda: _db.get_core_client())
app = create_product_app(..., organs=[finance])   # routers + upload-size overrides wired by construction
```

- `mount_finance` builds the finance + reconciliation routers with house auth (org staff reads, `is_org_admin` writes/exports, strict 401), a default storage backend, and the attachment/statement `max_body_path_overrides`; `create_product_app(organs=[...])` mounts them and merges the overrides (product entries win). `get_storage` / `get_charge_operations` are optional injections (no gateway => 503, the declared not-configured state).
- `ORGAN_REGISTRY` (`name -> OrganSpec`: migration generator, generated header, overrides, FE route) is where ERP organs register; `mount_organs([...])` flattens mounted organs.
- Migration: `noctus.dev.render_organ_migration product=<p> organ=finance [confirm=True]` writes `NNN_<organ>.sql` (collision-safe number, header-found so idempotent, asleep products refused). Pin it in the product's tests with `noctusai_lib.testing.organs.assert_organ_migration_current(product_dir, "finance", schema=...)`.
- **Applied organ migrations are frozen (security review B2, 2026-10-14).** `migrate_product` tracks files by name and never re-runs one, so re-rendering an applied file silently drifts prod. `migrate_product confirm=True` therefore mirrors every applied file + sha256 into `products/<p>/backend/migrations-applied.json` (`noctusai_lib.testing.migrations_applied`). Organ generators are re-runnable full-state scripts (`IF NOT EXISTS`, restated CHECKs), so when a generator changes: an UNAPPLIED latest file is refreshed in place; an APPLIED one yields a NEW `NNN_<organ>_rev<N>.sql` (`new_revision`) holding the full current output + a trailing `-- organ-revision: N` marker, and the earlier file is never touched. `assert_organ_migration_current` pins only the LATEST file to the generator (>=1 files); every earlier one must be recorded as applied and byte-identical to its recorded sha256. Backfill a product applied before the record existed: read its ledger read-only (`SELECT filename, checksum FROM <schema>.schema_migrations`) and call `record_applied(backend_dir, {...})` -- until then its files count as unapplied (refresh in place), so backfill BEFORE changing a generator.
- FE: the seed shell has no manifest-driven route mechanism; the host adds one lazy route (`/financeiro/*`, gated by `status_pagina`) once the FE organ exports from `@noctusai/lib` (`NOC-REMEDIATE[finance-fe-route]` in `organs.py`).

## Composes with

`../../03-SEED-ARCHITECTURE.md` · `seed-canonical-defaults.md` · `products-consume-canonical-organs.md` · `../backend/seed-fake-real-adapter.md` · `../backend/tenancy-license-gate.md` · `approved-cutover.md` · `project-execution.md`.
