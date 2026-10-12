---
name: noc-new-product
description: Use when creating a product — triggers "create a new noc product", "scaffold a product", "new noc product", "add a product", "new e-commerce / store / ERP for <market>", "a product for <client>", "build the <market> version of the seed", "new product inside the store" — seed-first by construction; never hand-author the shape. Routes plain products, market products from a vertical seed, client onboarding, client extension packs and products-inside-products.
version: 2.0.0
---

# noc-new-product — seed-first, layer-aware

**Trigger phrases ARE the seed-first contract.** A product inherits via the seed factories (`create_product_app` / `createProductApp`); customizations flow through NAMED seams only. Never hand-author the structural shape.

## Workflow

0. **Classify the ask — which layer is it?** (`KB § PATTERNS/architect/vertical-seed.md` §1)
   - **Plain product** (no market family) → steps 3–7.
   - **Market product from a vertical seed** (e.g. a photo store from the commerce seed) → steps 1–8.
   - **New client of an existing market product** → NOT a new product: onboard an org (step 6) — profile, license, keys, brand.
   - **Client-specific code** (own layout, own script) → a client extension pack inside the market product (`vertical-seed.md` §3), not a product.
   - **A sellable item inside a store** (a contract, a course, a photo pack) → products-inside-products tools, not this skill (`project-history/roadmaps/commerce-seed-2026-10-digital-products.md`).
   - **Sandbox / isolated / testing-ground** → `noctus.dev.create_testing_ground`.
1. **Learning round?** First run of a market, seed or process ⇒ skill `noc-learn-refine` — open trials on the method (this skill included) before step 2.
2. **Market spec (vertical/market products).** Follow `KB § CONTEXT/GUIDES/new-product.md § Market products from a vertical seed`: market research brief → module classification (generic / per-type / per-market) → interview in AskUserQuestion rounds (never assume) → decisions written to the roadmap before code.
3. **Verify the seed ships it.** Skill `noc-verify-seed` for every organ the product will consume; missing organ ⇒ build it in the seed/vertical layer first, not in the product.
4. **Scaffold.** `noctus.dev.reserve_port_range` → `noctus.dev.scaffold_product` (brief = the market spec). `url_base` = the HOUSE port.
5. **Fill seams + domain code only**, contract-first (skill `noc-contract-first`). Pages wire to real endpoints that return real data (`noc-wiring-audit`).
6. **Register + onboard.** `public.products` row + `status_pagina` nav rows + migration; for each client: org, license, store profile (CNPJ validated, tax regime, language/currency, brand, subdomain), keys via org settings.
7. **Finish gates.** Backend `pytest`, frontend `vite build`, `mcp/noctusai` tests if a `.tsx` count changed.
8. **Learning round close.** `noctus.dev.method_trial action=verdict` per trial; fold what changed into the guide, this skill (bump `version`) and the market spec library.

## Guardrails
- "Scaffolded" ≠ "complete" — backend and frontend at the SAME maturity before commit.
- No `if org == …` in shared code; client differences are settings, then packs, then dedicated instances (`vertical-seed.md` §4).
- SSO + cross-product nav work by construction IF you resolve core's URL via `env.CORE_URL`/`env.CORE_API_URL` — never hand-roll `import.meta.env.VITE_CORE_* || "literal"` (`check_handrolled_core_url` keeper).

## Depth
`KB § CONTEXT/GUIDES/new-product.md` · `KB § PATTERNS/architect/vertical-seed.md` · `KB § CONTEXT/03-SEED-ARCHITECTURE.md` · `KB § PATTERNS/frontend/core-url-routing.md`.
