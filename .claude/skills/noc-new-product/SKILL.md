---
name: noc-new-product
description: Use when creating a product — triggers "create a new noc product", "scaffold a product", "new noc product", "add a product". Seed-first by construction; never hand-author the shape.
version: 1.0.0
---

# noc-new-product — scaffold seed-first

**Trigger phrases ARE the seed-first contract.** A new product inherits via the seed factories (`create_product_app` / `createProductApp`); customizations flow through NAMED seams only. Do NOT hand-author the structural shape.

## Workflow

1. Read the OPENING block of `KB § GUIDES/new-product.md` first.
2. `noctus.dev.reserve_port_range` — get the house port range (consults `RESERVED_RANGES`).
3. `noctus.dev.scaffold_product` — emit the seed-compliant skeleton (backend `main.py` via `create_product_app`, frontend `App.tsx` via `createProductApp`, vite/vitest factories, Dockerfile + compose from the seed base, day-one routes/webhook/tests). `url_base` = the HOUSE port (not the vestigial frontend port).
4. Fill domain code only — routers/services/schemas/pages/hooks. Pages wire to real endpoints that RETURN real data (run `noc-wiring-audit`).
5. Register the `public.products` row + seed its `status_pagina` nav rows + migration.
6. Finish: backend `pytest`, frontend `vite build`, `mcp/noctusai` tests if a `.tsx` count changed.

## Guardrails
- "Scaffolded" ≠ "complete" — backend and frontend at the SAME maturity before commit.
- SSO + cross-product nav work by construction IF you resolve core's URL via `env.CORE_URL`/`env.CORE_API_URL` — never hand-roll `import.meta.env.VITE_CORE_* || "literal"` (`check_handrolled_core_url` keeper).
- "Sandbox / isolated / testing-ground" instead → `noctus.dev.create_testing_ground`, not this.

## Depth
`KB § GUIDES/new-product.md` · `KB § CONTEXT/03-SEED-ARCHITECTURE.md` · `KB § PATTERNS/core-url-routing.md`.
