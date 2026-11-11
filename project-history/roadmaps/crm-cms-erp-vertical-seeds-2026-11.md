# crm-cms-erp-vertical-seeds-2026-11 — CRM, CMS and ERP as seed modules mounted per market product

> **Status:** PLANNED 2026-11-08 (architect plan, owner direction verbatim in Origin). Target path: `project-history/roadmaps/crm-cms-erp-vertical-seeds-2026-11.md`. Full plan with evidence: [`crm-cms-erp-vertical-seeds-2026-11.plan.md`](crm-cms-erp-vertical-seeds-2026-11.plan.md) (§ 0 facts, § 1 ADRs, § 6 slices).

## Origin
Owner 2026-11-08: "what's shared with sw let's seed … let's start seeding erp cms and crm as products, so we get the core of them and project to other contexts … erps and crms for every market, building only market-specs … one's funel contains Visita stage, ours doesnt as Senseys doesnt." Answers: modules inside ONE product per market (sidebar groups in `MODULE_GROUP_ORDER`); canons SW = real estate (absorbs erp-imobiliario), orbity = digital agencies (absorbs igig), nosnolimiar = psychoanalysis clinics (absorbs therapy-platform + community), core = SaaS; absorbed products are erased after absorption; the market ships default config (funnel stages), each org edits it; priority CRM → CMS → ERP consolidation.

## Trigger conditions (the "when")
- **T-LIC** — first org asks to buy a module subset or a priced tier ⇒ activate `ModuleSpec.license_key` on the core license gate.
- **T-LOST** — an org asks to edit lost reasons ⇒ lost reasons become rows (like stages).
- **T-SLA** — a second market asks for Monitor/SLA alerts ⇒ lift SW `atendimento_blocos` + `supervisao`.
- **T-EMAIL** — a second market wants e-mail campaigns ⇒ lift SW `email_marketing`/`mailchimp` into a CRM sub-module.
- **T-INBOX** — SW touches its WhatsApp chat store for any reason ⇒ converge onto the seed `whatsapp-inbox` organ.
- **T-WO** — a second market needs maintenance/work orders ⇒ seed `work_orders` organ.
- **T-UNIT** — a second market needs branches/units ⇒ `org_unit` becomes an L0 org setting.
- **T-ANALYTICS** — a second market asks for lead analytics ⇒ lift SW `analytics_service`.

## Phase 1 — ADRs + KB (SHIPPED with this file)
- ADR-1 module = `ModuleSpec` (BE) + `defineModule` (FE), overlays generated from specs; ADR-2 one stage mechanism (`pipeline_stages` rows + market `CrmPreset`, code keys on `papel`, missing role = declared no-op); ADR-3 absorb-then-erase ladder A0–A7 with owner gates at A4 (per table), A6, A7.
- `vertical-seed.md`: module composition, CRM + CMS seam tables, ERP market-spec rows.
- Verify recipe: `noctus.dev.kb_sync action=verify` exit 0; `doc_staleness` clean.

## Phase 2 — CRM seed (W1–W3) (DEFERRED — fires now, owner priority 1)
| Slice | Owner | Depends | Verify recipe |
|---|---|---|---|
| W1-1 ModuleSpec BE | seed session | — | `create_product_app(modules=[...])` test mounts routers; strict 401 test |
| W1-2 defineModule FE | seed session | mq sidebar groups | vitest: nav group order + routes + page keys |
| W1-3 presets + roles | seed session | — | role-missing no-op test; SW preset reproduces today's 5+8 stages byte-for-byte |
| W1-4 assignment · W1-5 activities | seed session | — | organ guard probes green on PGlite (`migration_replay`) |
| W1-6 keepers (warn-first) | tooling-engineer | W1-1, W1-3 | keeper red on a planted literal stage tuple |
| W2-1 consent · W2-2 intake · W2-3 agent hook · W2-5 quotes accept | seed session | — | outbound gate refuses an opted-out number in a test; intake Fake round-trip |
| W2-4 leads-lite → stage rows + Nós no Limiar pilot | seed session + nosnolimiar | W1-3 | Nós no Limiar org edits a stage label in settings, board follows (live, prod) |
| W2-6 `crm_module` + `templates/product-crm` + `scaffold_product(overlay=list)` | seed + tooling | W1-*, W2-* | scaffold a throwaway `overlay=["crm","erp"]` product in a worktree; wiring tests green |
| W3-S1..S4 SW consumer (nav modules, preset, consent/assignment/quotes, ERP wave A) | noctusai-51 | W1-2, W1-3, W2-* | SW sidebar matches the approved nav map; Funil unchanged for One |
| W3-C1 core · W3-M1 nosnolimiar | seed / nosnolimiar | W2-6, owner Q4 | `spa_smoke` + page shows real data |

## Phase 3 — CMS seed (W5) (DEFERRED — fires when W2-6 lands)
Pages organ over the landing organs, editorial router + FE, media library (signed URLs only), `FeedPublisher` seam, external portal (fires on owner Q1). SW consumes: site, RE feed adapters, portal proprietário.

## Phase 4 — ERP consolidation (W4) (DEFERRED — W4-1/W4-2 may start in parallel with Phase 3)
E1 locação on `contracts` recurring + readjustment index; E2 commissions split in finance. SW market spec: vistorias, chaves, manutenção, seguros, campo, filiais (seam), comissões policy, DIMOB (after accountant review). Unfreeze order in PLAN § 4.

## Phase 5 — Absorptions (W6–W8) (DEFERRED — per product, owner-gated steps)
erp-imobiliario → SW (A5 decouple public fns before A7); wake orbity (owner go) → igig → orbity; therapy-platform + community + nos-no-limiar content → nosnolimiar (legal review first, owner Q2). Phase 6 = contract (W9): drop leads-lite literal path, SW SQL stage fn, orbity `lead_stages`; keepers flip to blocking.

> **Owner correction 2026-11-08 — what "erp" means here.** The only product absorbed into SW is **erp-imobiliario** (its database schema happens to be named `erp`; the "erp schema drop" in 51's S8 is THAT schema). **`templates/product-erp/` is the ERP product TEMPLATE and STAYS** — never absorbed, never erased; it is the L1 ERP vertical seed every market ERP is scaffolded from. There is no `products/erp` and no `erp` row in `public.products`. Owner: "erp que erp é esse? só me lembro do erp-imob, e o template de produto erp. esse erp deve ficar."


## Anti-goals (explicit non-goals)
- No separate CRM/ERP/CMS products or containers — modules mount into the market product.
- No market stage list, origin list or noun inside `seed/` (the seed ships one generic preset only).
- No `if org == …` / `if market == …` in seed code — presets and packs only.
- No data copy by default from absorbed products; copy is an owner decision per table.
- No automatic schema/bucket drop, ever.
- No rewrite of working SW features to "look seed" when a seam fill does the job.

## Open questions (to revisit at trigger time)
- Q1 public tier for CMS sites + portals · Q2 therapy-platform clinical data retention · Q3 module enablement per product vs per org · Q4 nosnolimiar slug (`nosnolimiar` rename) — recommendations in PLAN § 8.

## Decision log
- 2026-11-08: Shape = modules inside one product per market; canons SW/orbity/monica/core (owner).
- 2026-11-08: Seed owns stage mechanics, market ships default list, org edits in settings (owner).
- 2026-11-08: Priority CRM → CMS → ERP consolidation (owner).
- 2026-11-08: ADR-1/2/3 as above (architect; tech-lead to confirm at W1 dispatch).

## Retrospective (filled at first trigger fire)
_(empty)_

## Composes with
`KB § PATTERNS/architect/vertical-seed.md` · `seed-canonical-defaults.md` · `products-consume-canonical-organs.md` · `architecture-craft-canon.md` (§3 records, §10 expand-contract) · `product-working-scope.md` · `KB § GUIDES/absorb-seed-workspace.md` · skills `noc-absorb-product`, `noc-archive-absorb` · roadmaps `erp-seed-2026-10.md`, `commerce-seed-2026-10.md`, `nosnolimiar-v1-2026-10.md`, `community-modules-1-3-2026-09.md`.

## File trail
_(filled as slices land)_

## Owner answers to the plan's questions (2026-11-08)

- **Q1, public surfaces:** "follow the same pattern as sw and that should be canonical, even to noc ... sw should be way safer. let's use it as reference to seed security also and we can project to other products then". SW's hardened public/portal security model (2026-11-05/06 refinement) becomes the SEED canon. CMS sites and portals adopt it, and core and the other canons project from it. The W5-2 portal organ lifts SW's pattern rather than designing a new one.
- **Q2, therapy-platform data:** "Erase it all". No migration of its data; W8-M erases code and data after A0 measurement. The owner was told that CFP/LGPD clinical-record retention may apply and chose erasure.
- **Q3, module switches:** per COMPANY (org), **all modules on by default**, manageable from the admin dashboard. This supersedes ADR-1's "per product for now": `ModuleSpec.license_key` is live from W1-1. There is an org-level module enablement record, which noc admins toggle in core admin and which the FE nav and BE routes both honour.
- **Q4, Mônica slug:** finish the `nosnolimiar` rename BEFORE any Mônica absorption slice. It is still gated by the standing rule that the rename runs only after "Julia prod-verified".
- **UX fix (seed Sidebar):** in the collapsed icon rail, item badges (DEV, Em breve) must not push the icon sideways. Hide the badge when collapsed and show it when expanded, or use a better non-shifting indicator.
