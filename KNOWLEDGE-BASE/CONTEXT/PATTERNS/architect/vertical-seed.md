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

### 1a · A market product composes several verticals (owner 2026-11-08)

One market = one product, and that product **mounts several vertical modules** (CRM, ERP, CMS, …) in sidebar groups ordered by `MODULE_GROUP_ORDER` (`@noctusai/lib` `design-system/components/nav-groups.ts`). Canons: social-wiring (real estate), orbity (digital agencies), monica (psychoanalysis clinics), core (SaaS — noc runs its own business on the same modules). A module is a `ModuleSpec` (BE: organs + page keys + permissions) plus `defineModule` (FE: nav group + routes + page keys); a market extends a module with `extendModule`, never with a copy. Market configuration the org can change (funnel stages, origins, lost reasons) is a **preset the market ships and the org edits** — the seed owns the mechanics, never the list. Roadmap: `project-history/roadmaps/crm-cms-erp-vertical-seeds-2026-11.md`.

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

### ERP seams (2026-10-14, `project-history/roadmaps/erp-seed-2026-10.md`)

The ERP vertical declares these before the first market ERP is built. Defaults are the seed's canonical answer, not one market's coincidence:

| Seam | Values / shape | Where a market differs |
|---|---|---|
| `item_type` | open string; the seed set is `goods` · `service` · `raw_material` · `asset` (`items`) | a market adds types (e.g. `recipe`, `kit`); stock applies only to stocked types |
| `party_role` | `customer` · `supplier` · `employee` · `carrier` (`parties`, PF/PJ, CPF/CNPJ) | a market adds roles; commerce `commerce_customers` links, never merges (E4) |
| `costing_method` | **average cost only** (`inventory` valuation `average_cost`) | none: LIFO is not permitted in Brazil (E14); lots/serials/BOM are market-specific modules, not a method switch |
| `approval_policy` | `purchasing`: org admin + membership in the org's approver list (`pur_approvers`) + a per-org threshold (`approval_threshold_cents`) | thresholds and approvers are org settings; a different policy is a named hook, never a fork |
| `billing_model` | `one_time` · `installments` · `recurring` · `retainer` (`contracts`, over finance recurrences; daily billing job) | indices/readjustment rules and the e-signature adapter (`get_signature`) |
| fiscal regime | `mei` · `simples` · `presumido` · `unknown` as a finance profile field (DRE, Livro Caixa, DAS views); IBS/CBS-in-DAS choice (E19) | Presumido obligations are the accountant's files (E13); the seed exports data, never files |
| quote accept | `QuoteAcceptHandler` (convert-on-accept), signed public link needs a host `get_link_secret` | what an accepted quote becomes (contract, sales order, work order) |

Scaffold a market ERP from this layer with `noctus.dev.scaffold_product(overlay="erp")` (`templates/product-erp/`, registered `deploy_scope='dev'` only): `../../GUIDES/new-product.md § Market products from a vertical seed`.

### CRM seams (2026-11-08)

| Seam | Values / shape | Where a market differs |
|---|---|---|
| `pipelines` | board keys per market (`CrmPreset.pipelines`) | RE `funil`+`processos_venda`; SaaS `funil_noc` (platform tenancy); agencies `comercial`; clinics `leads` |
| `stage_set` | `pipeline_stages` rows (slug immutable, label/cor/posicao editable, `papel`); preset seeded lazily by `ensure_default_stages`; org edits in settings | the default list |
| `stage_roles` | canonical `entrada`·`qualificado`·`proposta`·`proposta_aceite`·`ganho`·`final` + market roles; code keys on `papel`; a role the org's funnel lacks ⇒ declared no-op | RE `visita`; clinics `sessao_experimental`; agencies `briefing` |
| `lost_reasons` | `FunnelConfig.lost_reasons`, preset default | the list |
| `lead_origins` + `lead_source` | origin slugs (data) + `LeadSource` Protocol/Fake/Real (whatsapp, meta lead ads, website form, xlsx import, email) | RE portal webhooks (OLX, Imovelweb) are L2 adapters |
| `qualification_schema` | JSON schema per market, fed to the agent and shown on the card | fields per market |
| `agent_hook` | `LeadAgentHook` (on_inbound / on_created / on_stage_entered) → agents product by agent key | RE Julia; clinics `monica-leads`; others Fake |
| `assignment_strategy` | `round_robin`·`by_team`·`by_source`·`by_unit`·`manual` + capacity + out-of-office; custom = named hook (`strategy_hooks`); BUILT (W1-4): `../backend/assignment-organ.md` | who owns a lead |
| `activity_types` | `CrmPreset.activity_types`: `(slug, label, kind)` rows over the four kinds `task·call·meeting·visit`, seeded lazily per org (organ: `PATTERNS/backend/activities-organ.md`) | visita, chave_retirada/devolucao, manutenção and campo are RE rows; nullable `org_unit_id` rides on every activity (multi-branch convention) |
| `proposal_accept` / `on_won` | `QuoteAcceptHandler` + funnel action → `papel=proposta_aceite`; `on_stage_entered` | what a won deal becomes (processo de venda, contract, paciente, org) |
| `consent_channels` | opt-out registry + `OutboundGate` on every sender; the agent decides an opt-out, the seed records and enforces | retention note per market |
| `nouns` | Lead/Cliente/Paciente, Corretor/Terapeuta/Account | labels |

### CMS seams (2026-11-08)

| Seam | Values / shape | Where a market differs |
|---|---|---|
| `block_types` | page = ordered blocks over the landing organs; registry for market blocks | RE listing blocks; agencies cases |
| `content_types` | `page`·`post`·`listing`·`case` (open) | per market |
| `editorial_policy` | `domain/editorial` transitions + grants | who approves |
| `content_board` | `esteira` pipeline preset | stage list |
| `feed_publisher` | Protocol + Fake + Real (sitemap, RSS, Google Merchant/Meta catalog) | RE ZAP/VivaReal/OLX/Imovelweb adapters (L2) |
| `portal_audience` | `proprietario`·`paciente`·`membro`·`cliente`; token-scoped | what each audience sees |
| `domain` | per-org subdomain/custom domain via tunnel + DNS tools | none |

### ERP market specs (real estate, 2026-11-08)
Locação = `contracts` recurring + readjustment index (L1); vistorias, chaves, seguros = SW L2; manutenção/campo = `activities` types (+ supplier `parties`, finance payable); filiais = `org_unit_id` convention (L2, promote at N=2); comissões = finance split mechanism (L1) + RE policy (L2); DIMOB = SW export of data over contracts+finance, accountant-reviewed; banco/impostos = the finance organ.

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
- `ORGAN_REGISTRY` (`name -> OrganSpec`: migration generator, generated header, overrides, FE route, guard probes) is where ERP organs register; `mount_organs([...])` flattens mounted organs.
- Migration: `noctus.dev.render_organ_migration product=<p> organ=finance [confirm=True]` writes `NNN_<organ>.sql` (collision-safe number, header-found so idempotent, asleep products refused). Pass `worktree_path=<your worktree>` from a worktree: the file path AND the organ generator code are then taken FROM that tree (child interpreter with the tree's `seed/*/backend` on `PYTHONPATH`; no CLI flag, so nothing for `toolkit_freshness._MAPPED_PARAMS` to mirror), so an unmerged generator change is what is compared. Omitted => the server's own tree is used and the result flags it (`generator_source` + `warnings`) -- a primary-tree `up_to_date` is not a verdict on your branch. Pin it in the product's tests with `noctusai_lib.testing.organs.assert_organ_migration_current(product_dir, "finance", schema=...)`.
- **Applied organ migrations are frozen (security review B2, 2026-10-14).** `migrate_product` tracks files by name and never re-runs one, so re-rendering an applied file silently drifts prod. `migrate_product confirm=True` therefore mirrors every applied file + sha256 into `products/<p>/backend/migrations-applied.json` (`noctusai_lib.testing.migrations_applied`). Organ generators are re-runnable full-state scripts (`IF NOT EXISTS`, restated CHECKs), so when a generator changes: an UNAPPLIED latest file is refreshed in place; an APPLIED one yields a NEW `NNN_<organ>_rev<N>.sql` (`new_revision`) holding the full current output + a trailing `-- organ-revision: N` marker, and the earlier file is never touched. `assert_organ_migration_current` pins only the LATEST file to the generator (>=1 files); every earlier one must be recorded as applied and byte-identical to its recorded sha256. Backfill a product applied before the record existed: read its ledger read-only (`SELECT filename, checksum FROM <schema>.schema_migrations`) and call `record_applied(backend_dir, {...})` -- until then its files count as unapplied (refresh in place), so backfill BEFORE changing a generator.
- **Guards are declared with the generator.** Every UNIQUE / CHECK / trigger guard an organ's migration emits needs an `OrganGuardProbe` in `noctusai_lib/domain/<organ>/guards.py` (set as `OrganSpec.guard_probes`): the schema-parameterized violating operation, proven to refuse on PGlite. `noctus.dev.verify_db_guards` derives the probes for every product that rendered the organ (a table not applied yet reports `pending`), and `check_migration_guard_has_probe` treats an organ-rendered guard as covered iff the organ declares it -- so rendering an organ into a product never needs a hand-written probe or `_GUARD_PROBE_ALLOWLIST` entry, and a generator cannot add an unprobed guard (`test_organ_guard_probes.py` is the completeness gate). KB § PATTERNS/common/methodology-execution-discipline.md § 8.
- FE: the seed shell has no manifest-driven route mechanism; the host adds one lazy route (`/financeiro/*`, gated by `status_pagina`) whose page is a one-liner over the `FinanceRoutedPage` organ exported from `@noctusai/lib` (`basePath`, `api` or `hooks`, `isAdmin`, optional `isAccountant`/`title`). The organ owns the URL <-> section sync and the unknown-segment redirect; never hand-roll it per product (`finance-fe-route` closed).

## Mounting a module (CRM / ERP / CMS inside ONE market product)

Owner 2026-11-08: each market is ONE product that mounts modules as sidebar groups in `MODULE_GROUP_ORDER`; modules are switched **per org, ALL ON by default**, managed by NoctusAI admins. (ADR-1 of `project-history/roadmaps/crm-cms-erp-vertical-seeds-2026-11.plan.md`, which lives on the plan branch until it lands; its "per product for now" licensing is superseded: `license_key` is live.)

**BE** `noctusai_seed.modules`:

```python
crm = ModuleSpec(key="crm", organs=[leads, funnel],                       # MountedOrgans, flattened by mount_organs
                 pages=[PageSpec("crm/leads", "/crm/leads", "Leads")],     # PageSpec(key, path, label, status="producao")
                 permissions={"crm.write": "admin"}, license_key=None)    # enablement key defaults to `key`
app = create_product_app(..., modules=[crm], module_auth_dependency=get_current_user_org)
```

- `key` is a canonical module-group key (`noctusai_lib.domain.module_enablement.MODULE_GROUP_KEYS`, a BE test parses the FE `MODULE_GROUP_ORDER` and fails on divergence). A page lives in exactly one module; `module_manifest(specs)` is the page-key contract.
- Module routers sit behind a guard that depends on the host auth dependency: no auth => strict 401; org without the module => **403 `{"code": "module_disabled"}`**; enablement lookup outage => 503 (never "all on"). `public_routers` (signed links) are mounted unguarded and declare their own tier. `GET /api/modules` (tier org) tells the FE which of the product's modules the caller's org has.
- Storage: `public.org_modules(org_id, module_key, enabled, updated_by, updated_at)`, ONE platform table, service-only (`tier:platform`, no browser grant), absent row = ENABLED. Organ `module_enablement` (`noctus.dev.render_organ_migration product=core organ=module_enablement`); resolver `ModuleEnablement.enabled_modules(org_id)`. It keeps current state only; a change history, if wanted, uses the transition-log primitive, never a hand-written table.
- Write API for the core admin dashboard: `create_org_modules_admin_router(...)` (`GET/PUT /api/platform/org-modules/{org_id}[/{module_key}]`, `require_platform_admin`: 401 / 403 `platform_admin_required`). The core admin PAGE is a follow-up.

**FE** `@noctusai/lib` (`modules/`): `defineModule({ key, items: [{ label, path, pageKey, element, roles?, status?, children? }] })` -> `{ navGroup, routes, pageKeys }`; `extendModule(base, { items, insertAfter, override, remove })` is the only way a market adjusts a seed module; `composeModules({ modules, localGroups, enabledKeys, orgRole })` merges through `orderNavGroups` and **does not render** a module the org lacks (no nav group, no routes; while `useEnabledModules` is unanswered nothing renders and `pending` is true). `pageKey` = `status_pagina.nome_pagina`; `filterNavByPageStatus` still gates the result.

**Contract check.** BE `module_manifest(specs)` and FE `moduleManifest(modules)` emit the same JSON; a host commits it and asserts both sides (`assertManifestMatches` FE; BE compares `module_manifest(specs)` to the file). The seed pins the cross-language parity with `seed/lib/backend/tests/fixtures/module_manifest.json`.

**Planned (not built yet).** Every module page key needs a `status_pagina` row (keeper `check_module_page_status_rows`, follow-up). New module pages take the `/crm|/erp|/cms/…` prefix, and existing URLs never move. A new market is scaffolded with `scaffold_product(overlay=["crm","erp","cms"])`, with overlays generated from the module specs.

## Composes with

`../../03-SEED-ARCHITECTURE.md` · `seed-canonical-defaults.md` · `products-consume-canonical-organs.md` · `../backend/seed-fake-real-adapter.md` · `../backend/tenancy-license-gate.md` · `approved-cutover.md` · `project-execution.md`.

### CRM stage presets (W1-3, 2026-11-08)
Funnel stages are a **market default each org edits** (owner 2026-11-08): One's real-estate funnel has `Visita`, noc's and Senseys' do not. Seed (`noctusai_lib.domain.pipeline`): `CrmPreset` (`presets.py`: `pipelines` board→`StageDefault`s, `lost_reasons`, `lead_origins`), canonical roles `entrada·qualificado·proposta·proposta_aceite·ganho·final` + market roles `visita·sessao_experimental·briefing·contatado` (`KNOWN_CRM_ROLES`, usable as `PipelineConfig.stage_roles`). `ensure_preset_stages` seeds an org lazily (org edits win; slug immutable; a role-bearing stage is guarded — release the role first). **Code keys on `papel`; `stage_for_role(...)` returns None and logs at info when the org's funnel lacks the role — a declared no-op, never an exception.** `market_presets.py` holds today's values for the four markets as expand-phase reference (NOC-REMEDIATE[crm-preset-to-canon]: each moves to its canon's `app/market/crm_preset.py` when that canon migrates). Stage-move history is NOT built here: it goes through the transition-log primitive once it lands (no new hand-written movement table).
