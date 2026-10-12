# Commerce seed → three market stores — roadmap (2026-10)

> **Status:** PLAN APPROVED 2026-10-12 (T1 fired). P2 in progress. No commerce code yet.
> **Live tracker:** https://claude.ai/artifact/4mn1fH7nk2fsVeKQHdGdr4 — phases, tasks, decisions, activity (realtime). Agents update it with the `ArtifactData` tool (collections `meta/phases/tasks/decisions/log`, data model in the page's `<script>` header). Keep it in sync with this file: this file is the durable record, the tracker is the live view.
> **Market research:** [`commerce-seed-2026-10-market-brief.md`](commerce-seed-2026-10-market-brief.md) — module table generic vs digital vs physical vs vertical, BR payments/fiscal/consumer law, sources.
> **Digital products:** [`commerce-seed-2026-10-digital-products.md`](commerce-seed-2026-10-digital-products.md) — digital-product model, KPIs, Gilson's contract product, products-inside-products tools.
> **Method:** `KB § PATTERNS/architect/vertical-seed.md` (model) · `KB § CONTEXT/GUIDES/new-product.md § Market products from a vertical seed` (procedure) · `KB § PATTERNS/architect/approved-cutover.md` · skill `noc-learn-refine` + `KB § PATTERNS/common/method-trials.md`.
> **Owner:** the noc owner (product decisions) · tech-lead session (execution).

---

## Origin

2026-10-12. The owner has two real clients — a **photographer** (digital: image licensing) and a **Buddhist / Hindu / Indian / Afro-Brazilian artifacts shop** (physical: small-medium items, little storage) — plus **Gilson's Store** (software/digital products: contract templates, courses/e-books). Instead of building three stores, build a **generic e-commerce + ERP seed first**, then specialize it per market, so the same seed sells to the next photographer, videomaker, musician, or physical shop.

Owner's words (abridged): *"we need to build a generalistic product's seed first because then we can use this seed as a template to create products for other markets as well … e-commerce e2e with registration and auth up until delivery logistics and payment and financial management, the webstore … and the management-side … the most automated as it's possible."* And: *"I need that process documented on the first photo run, then refined to the artifacts store … refine the new product skill with it."* Precedent: `erp-imob` was meant as "ERP seed → real-estate specialization", but that intent was never recorded and `products/erp-imobiliario/` is a plain real-estate CRM — this roadmap is where the pattern gets written down for real.

Longer horizon (discussed later, P12): landing page → purchase → client data → market spec → **branded client instance** provisioned automatically. The commerce seeds are the first noc product seeds for commercialization.

## The model — four layers (the "vertical seed" chain)

```
L0 noc seed            products/seed + noctusai_seed / @noctusai/seed (auth, SSO, app factories)
  └ L1 vertical seed   COMMERCE organs in noctusai_lib/domain/commerce/* + @noctusai/lib commerce
                        components + a commerce product template (the "commerce seed")
      └ L2 market      one noc product per market: photo store · artifacts store · Gilson's Store
          └ L3 client   one ORG per client inside the market product (own keys, prices, brand,
                        catalog, CNPJ, tax regime, language/currency)
              └ (L3+)   optional upgrade path: extended tenant → dedicated instance → fork
```

Rule: anything 2+ markets need lives in L1; market-only behavior lives in L2 behind **named seams** (product type, fulfillment type, tax treatment); client differences are **settings, never code**.

### Client isolation levels (decision D1 + owner's follow-up question)

| Level | What the client gets | Setup | Ongoing cost | Blast radius |
|---|---|---|---|---|
| **L1 Branded tenant** — START HERE | brand, subdomain, keys, prices, catalog — inside the shared market product | none | ≈0 (one more org row) | a bug or bad deploy hits **every client of that market** |
| L2 Extended tenant | + client-only modules behind a seam + per-org feature flag | a seam module | low | same as L1 + their module |
| L3 Dedicated instance | same image, own container + own schema or Supabase project | org export → deploy → DNS → webhooks (~½ day with tooling) | +1 container (~0.3–0.5 GB RAM), Supabase Pro ≈US$25/mo if separate, every deploy/migration ×N | only that client; releases fan out per instance |
| L4 Personalized fork | own noc product derived from the market product | new product from the L2 template | highest — drift; every seed fix needs merge + verify per fork | only them; maintenance compounds |

**Built-in from day one so L3/L4 stay cheap:** everything keyed by `org_id` (RLS via `public.current_org_id()`); zero `if org == …` branches; all per-client config in org settings (`resolve_credential` org → platform → env); storage paths prefixed by org; a **per-org export/import** (also the LGPD portability duty); the product image supports a **single-org mode** pinned by config, so L3 is a deploy setting, not a project. Main option-1 risk = cross-org leakage through an RLS bug → org-isolation tests on every commerce table (existing keepers + new per-table isolation tests).

## Decision log (append-only)

- 2026-10-12 · **D1 layering** — option 1 (shared organs → product per market → client = org). Keep the upgrade path to a client's own version (levels above). *Owner wants costs/blast radius documented — done above.*
- 2026-10-12 · **D2 products/store** — mine what's valuable (landing, Asaas checkout, webhook fulfillment, signed downloads, admin, Fernet-encrypted keys) into the commerce seed, then **discard** it. Its market becomes **Gilson's Store** (software/digital products), rebuilt from the seed. Contract-selling landing + its management are considered done there.
- 2026-10-12 · **D3 markets + order** — three markets: **photography → artifacts (physical) → software (Gilson's Store)**.
- 2026-10-12 · **D4 photo offer** — image licensing to start: landscape, nature, objects, food, paintings/drawings. Expand later.
- 2026-10-12 · **D5 payments** — **Asaas first** (organ already ships Protocol + Fake + Real + factory); other gateways later behind the same Protocol. Stripe (already in the organ) is the route for foreign currency.
- 2026-10-12 · **D6 Gilson's catalog** — contract templates + courses / e-books (not 100% defined).
- 2026-10-12 · **D7 photo licensing** — **one price per photo**, one standard license (certificate + verification page still apply). Tiers later.
- 2026-10-12 · **D8 artifacts store** — has a physical shop, starting from zero online, wants marketplace channels (ML/Shopee/…). Shop + online share **one stock**. Unique pieces not the norm (stock=1 still supported).
- 2026-10-12 · **D9 invoices** — **issued by the system from v1** (NF-e for goods, NFS-e Nacional for services/licenses). **Tax regime (MEI / Simples / other) is a selectable field of the store profile.** **CNPJ is required and validated** (format + check digits). Tax treatment per product type is configurable (photo-licensing ISS is legally unsettled — see brief §C).
- 2026-10-12 · **D10 AI automations v1** — auto-describe + tag products (owner reviews), WhatsApp sales + support bot (WAHA), back-office copilot.
- 2026-10-12 · **D11 AI runtime** — **local models first** to measure impact, then hybrid with **Claude models for what's expensive to run locally**. One Protocol + Fake + local adapter + Claude adapter. Claude runs the evaluation with the owner (quality, latency, cost per automation).
- 2026-10-12 · **D12 deadlines** — none. Timeline bars are estimates.
- 2026-10-12 · **D13 artifacts shipping** — freight aggregator (Melhor Envio / Frenet) + pickup at the shop + local delivery.
- 2026-10-12 · **D14 local AI host** — a noc VPS (capacity check first: RAM/CPU for vision models).
- 2026-10-12 · **D15 storefront address** — `<client>.noctusai.com` subdomain now (validation and early operation). Custom domains maybe later via a **Cloudflare automation** (P12; may be non-functional at first).
- 2026-10-12 · **D16 language + currency** — switchable settings in the store profile.
- 2026-10-12 · **D17 tracker product** — becomes a noc product **after all three stores**.
- 2026-10-12 · **T1 fired** — owner approved the plan; P2 started.
- 2026-10-12 · **D18 client-specific code** — clients may need structurally different layouts or one-off scripts, so client-specific changes CAN be code: **client extension packs** in `products/<market>/clients/<slug>/`, loaded only for that org through declared seams (`vertical-seed.md` §3). Isolation level L2 now includes packs.
- 2026-10-12 · **D19 NFS-e cutover** — build the current flow (validation) AND the national NFS-e flow. At the switch: danger alert + Approve button; never automatic. After approval the old code stays for a validation window, then is retired (`approved-cutover.md`). Built in P4.
- 2026-10-12 · **D20 photo-licensing tax** — Claude designs a recommendation (below, *Parked recommendations*); owner evaluates later; the losing options are deleted after the decision.
- 2026-10-12 · **D21 digital products** — a digital-product model + KPIs from research (companion doc); Gilson's contract = first canonical digital catalog product; **products-inside-products tools** (MCP now, the same service powers in-app "new product" tools later).
- 2026-10-12 · **D22 continuous refinement** — the method, skill and tools are refined while building the commerce architecture AND at each store (photo, artifacts, Gilson's), not only at the learning-round phases.
- 2026-10-12 · **D23 learn-while-building** — new skill `noc-learn-refine` + tool `noctus.dev.method_trial`: methods in use are trials with hypothesis, metrics, observations and verdicts.

## Phases

Week numbers are estimates from 2026-10-12 (W1). Each phase gets its own `projects/commerce-seed-<phase>/PROJECT.md` (from `templates/PROJECT-TEMPLATE.md`) when it starts; this roadmap is the spine.

| Phase | Track | Est. | Gate / trigger | What ships | Verify recipe |
|---|---|---|---|---|---|
| **P0** Orient + research | method | W1 | — | ✅ market brief, codebase map, live tracker | brief file exists; tracker loads live |
| **P1** Interview + master plan | method | W1 | **T1 owner signs off this plan** | ✅ decisions D1–D17, this roadmap, `create_testing_ground` path fix | roadmap on `dev`; tracker decisions = D1–D17 |
| **P2** Vertical-seed method + skill v2 | method | W2 | T1 ✅ | `vertical-seed.md` (layers, seams, client extension packs, isolation levels) · `approved-cutover.md` · new-product guide § Market products from a vertical seed · `noc-new-product` v2.0.0 · skill `noc-learn-refine` + `method-trials.md` + tool `noctus.dev.method_trial` · digital-product spec · photo-tax recommendation | pre-commit keepers green; `method_trial` tests green; trials opened for the vertical-seed method, skill v2 and `noc-learn-refine` itself |
| **P3** Commerce core | seed | W2–3 | T1 | organs: customers + addresses + LGPD consent/rights; **store profile** (CNPJ required+validated, tax regime, language, currency, brand tokens, subdomain); catalog with `product_type` seam; one-price + coupons pricing; cart/checkout with Decreto 7.962 disclosures + immediate-delivery consent; order state machine with `fulfillment_type` seam. **Mine `products/store` first.** | contract-first per organ; Fake-backed tests; org-isolation test per table |
| **P4** Commerce money | seed | W3–4 | P3 | payments via Asaas organ (Pix, boleto, card + parcelamento, refunds, webhooks idempotent, `expired` + recovery); finance (AR/AP, cash flow, gateway settlement reconciliation); **invoice adapter** Protocol + Fake + Real (NF-e + current NFS-e + NFS-e Nacional, IBS/CBS fields) with the **approved cutover** for NFS-e (D19) | Asaas sandbox e2e; invoice Fake round-trip; real provider sandbox |
| **P5** Fulfillment seams, back-office, AI | seed | W4–5 | P4 | digital-product model (`deliverable_type` seam, versions, entitlements, KPIs + events — companion doc §2–3); digital delivery (private bucket, signed expiring URLs, download limits/log, license certificate + verify page); **products-inside-products MCP tools** (companion doc §5); client extension pack loader (D18); physical seam stub (filled in P9); admin + roles + reports; storefront theming per org; **AI layer** (Protocol + Fake + local + Claude) + **eval harness**; the 3 automations | eval report local vs Claude; wiring audit (`noc-wiring-audit`) green |
| **P6** Seed validation | seed | W6 | **T2 owner says "validated"** | e2e walk of a generic store on a subdomain | owner sign-off recorded in decision log |
| **P7** Photo store (digital) | photo | W6–7 | T2 | market product from the commerce template; watermark/preview pipeline; categories (landscape, nature, objects, food, paintings/drawings); one-price license; photographer org onboarded | client buys a photo end-to-end in Asaas sandbox, then prod |
| **P8** Learning round 1 | method | W8 | P7 shipped | photo-run lessons → vertical-seed guide, skill, spec library, organ knowledge sidecars | guide diff reviewed; skill version bumped |
| **P9** Artifacts store (physical) | artifacts | W8–9 | P8 | stock (one stock shop+online), variants, packaging/cubic weight, freight aggregator quotes + labels + tracking, shop pickup, local delivery, returns (7-day), NF-e; marketplace channel sync design | sandbox order → label → tracking webhook |
| **P10** Learning rounds 2+3 | method | W12 | P9 + P13 | physical + software lessons → final playbook; digital + physical + software spec templates | playbook covers all 3 markets |
| **P13** Gilson's Store (software) | software | W10–11 | P9 | market product from the template; products/store mined + retired (archive, learn-before-archive); **contract = first canonical `generated_document` product** (questionnaire → preview → pay → filled DOCX/PDF), then courses/e-books; refines the products-inside-products tools | Gilson buys/sells e2e; `products/store` archived |
| **P11** Tracker product | tracker | W12–13 | **T3 all three stores live** | noc product from this tracker's data model; realtime via the seed SSE bus (`seed/lib/frontend/src/realtime.ts`), kanban/pipeline organs | parity with the artifact tracker |
| **P12** Sell + provision pipeline | sales | W14–15 | T3 + owner session | landing → purchase → client data → market spec → branded org; Cloudflare custom-domain automation | to be specified with the owner |

## Trigger conditions

- **T1** — owner signs off this roadmap (tracker task "Your sign-off on the plan" → done). Unlocks P2–P5.
- **T2** — owner says the generic seed is validated ("on my say"). Unlocks every market phase. Nothing goes vertical before T2.
- **T3** — photo, artifacts and Gilson's stores all live with their first client. Unlocks P11 + P12.
- **T4** (upgrade path) — a client asks for their own version → pick the lowest isolation level (L2 → L3 → L4) that satisfies it; never jump straight to a fork.

## Anti-goals

- No per-client code (`if org == …`) — ever. Differences are settings or seams.
- No market-specific logic in L1 organs. If only one market needs it, it lives in that market product.
- No second payment gateway before the Asaas path is proven end-to-end.
- No marketplace sync in the first artifacts release beyond design (needs stock to be solid first).
- No face search / biometric features (LGPD sensitive data) unless a market explicitly asks — not in scope now.
- No custom domains before subdomains work (D15).
- Don't let `products/store` keep living in parallel: mine → retire (D2).

## Open questions (revisit at the named phase)

- **Gilson** — he already has an org on noc (*Gilson Tangerino*, org-per-brand 2026-10-07, licensed for `store`). Open: CNPJ for the store profile, final catalog (D6), and **whether he is a lawyer** (OAB Provimento 205 — companion doc §4). → P13 kickoff.
- **Photographer + artifacts shop tax setup** (MEI / Simples, municipality, ISS treatment of image licensing) — the regime is a profile field (D9) but the defaults per product type need their accountant. → P4.
- **Invoice provider** — FocusNFe (already used in `adconnect`) vs alternatives; NFS-e Nacional emitter API vs provider. → P4 Phase 0.
- **VPS capacity for local models** (D14) — which VPS, RAM/CPU headroom, which models. → P5 Phase 0.
- **Roles in the back-office** (owner only / staff / accountant access). → P5.
- **Marketplace channels for the artifacts shop** — which ones first (D8). → P9.
- **How a market spec is captured** — format of the spec library (YAML checklist vs KB doc vs `scaffold_interrogate` question sets). → P2.

## Parked recommendations (evaluate later · delete the losing options after the decision)

### R1 · Photo-licensing tax treatment (D20)

*The legal question:* is selling a license to use a photo a **service** (ISS, NFS-e) or the **assignment of a right / movable asset** (no ISS; São Paulo rulings and a 2026 STJ decision lean this way — brief §C)?

*Recommendation:* make tax treatment a per-product-type rule set in the store profile, with three presets, and default the photographer to **B** until the accountant confirms:

| Preset | Invoice | When it fits |
|---|---|---|
| A · Service | NFS-e (ISS) per sale | accountant treats licensing as a service, or the municipality requires it |
| **B · Rights assignment + receipt** (default) | no NFS-e; system issues a detailed sale receipt + license certificate; revenue still reported via the regime (DAS for MEI/Simples) | follows the São Paulo/STJ reading; lowest friction for one-price photo licenses |
| C · Mixed | NFS-e only for commissioned shoots/services; licenses under B | photographer also sells services through the store |

Switching preset is an owner-approved change per org (same audit trail as `approved-cutover.md`). *Discard rule:* once the owner decides, delete the unused presets from the code and this section keeps a one-line record of the decision.

## Phase 1 (SHIPPED with this file)

- Market research brief (sibling file).
- Decisions D1–D17 recorded here + in the tracker.
- Live tracker artifact (realtime db) for the run.
- Drift fixed on contact: `noctus.dev.create_testing_ground` pointed at `scripts/bootstrap-seed-workspace.sh`; the script lives at `scripts/bootstrap/`. Every call returned "bootstrap script not found". Path fixed + regression test (`test_create_testing_ground_finds_bootstrap_script_under_scripts_bootstrap`).

## What already exists (Phase 0 map, 2026-10-12)

- `seed/lib/backend/noctusai_lib/integrations/payments/` — Protocol, Fake, `real_asaas.py`, `real_stripe.py`, factory, hosted checkout, webhook events; `noctusai_lib/domain/payments` (idempotency inbox, subscription state machine).
- `products/store/` (schema `store`, port 8018, `ativo=false`) — landing → Asaas charge → webhook → email + signed download link; `/admin`; Fernet-encrypted keys. Docs: `products/store/projects/store-v1-CONTRACT.md`, `project-history/roadmaps/store-launch-2026-10.md` (its Asaas sandbox e2e "M4" never closed).
- `products/adconnect/` — catalog, cart, orders, financial, FocusNFe NF-e (`services/nfe_service.py`) — asleep, mineable.
- Tenancy: one Supabase DB, schema per product, `org_id` + RLS, license gate (`KB § PATTERNS/backend/tenancy-license-gate.md`), org-per-brand (2026-10-07).
- Not anywhere yet: shipping/freight, stock, vertical-seed concept, client provisioning flow.
- Tracker-relevant organs: kanban/pipeline (`seed/lib/frontend/src/components/kanban/`, `noctusai_lib/domain/pipeline/`), SSE realtime bus (`KB § PATTERNS/common/realtime-sse-bus.md`).

## Retrospective

_(filled at P8 and P10 — learning rounds.)_

## Composes with

`KB § CONTEXT/GUIDES/new-product.md` · `KB § CONTEXT/03-SEED-ARCHITECTURE.md` · `KB § PATTERNS/backend/seed-fake-real-adapter.md` · `KB § PATTERNS/architect/seed-canonical-defaults.md` · `KB § PATTERNS/backend/tenancy-license-gate.md` · `KB § PATTERNS/architect/products-consume-canonical-organs.md` · `KB § PATTERNS/common/build-learn-cache-mindset.md`.
