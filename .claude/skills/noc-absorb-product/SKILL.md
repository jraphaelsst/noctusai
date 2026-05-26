---
name: noc-absorb-product
description: Use when folding an externally-developed seed-workspace into noc as a product — triggers "absorb the X workspace", "bring the sibling repo in", "fold it into noc as a product". The 10-gate end-to-end procedure.
version: 1.0.0
---

# noc-absorb-product — the 10-gate absorption

An absorption is a methodology-epoch merge: bring the source in, audit completeness, interrogate before deleting anything, scaffold + full seed-reconcile, port pilot-first, refactor to the house container shape, retire only when the user signs off.

## Workflow (gates)

1. **Snapshot** the source repo state.
2. **Bring source in-home** (under noc, not referenced externally).
3. **Completeness audit** — what ships vs what's claimed.
4. **Interrogate before delete** — `noctus.dev.scaffold_interrogate`; extract durable knowledge to KB/memory FIRST.
5. **Scaffold** the product shell (`noctus.dev.scaffold_product`).
6. **Full seed-reconcile** — every structural bone flows through the seed; divergent shapes resolve via back-compat-defaulted seed seam params (never degrade the consumer, never fork in-product, never silent-schema-migrate).
7. **Port + pilot-first** — prove on canonical pilots before fan-out.
8. **Consumer-adapt** — wire through named seams; ship the consume-side `KB § INTEGRATIONS/<x>.md` in the SAME project (R1).
9. **Teardown** — salvage-before-delete; recovery pointer to the ledger.
10. **Container-refactor** to the house single-container model + user-gated retirement.

## Guardrails
- Divergent container architecture MUST refactor to the house shape (one container, `serve_spa`, `FROM noctus-seed-*-base`). No fleet carve-out.
- Absorbed shape ⊥ seed contract (DDL cols / registered URL / security control) → extend the seed primitive with a back-compat default; N≥3 ⇒ MUST formalize.
- `noctus.dev.promote_from_seed_workspace` for promotion-manifest items.

## Depth
`KB § GUIDES/absorb-seed-workspace.md` (the 10 gates) · `KB § PATTERNS/absorbed-product-seed-shape-seam.md` · `KB § PATTERNS/containerization.md §12a`.
