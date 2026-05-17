---
slug: whatsapp-connection-page
origin:
  - products/youtube-crawler/frontend/src/pages/Conexao.tsx
  - products/youtube-crawler/frontend/src/hooks/useWhatsAppConnection.ts
intended_noc_destination: none — product-local consumption layer. The
  reusable seam was ALREADY promoted to noc in seed-repo commit
  d81d88e (feat/whatsapp-connection-mgmt): the WAHA session-admin
  client/Fake/Protocol, the `whatsapp_admin` standard router, and the
  `createWhatsAppConnectionHooks(api)` frontend factory all live in
  the seed. These two files are the irreducible product-specific
  glue that every consuming product writes for itself.
layer_rationale: |
  Two-file product consumption layer over the seed capability:
  - useWhatsAppConnection.ts: a one-liner that binds the seed
    `createWhatsAppConnectionHooks` factory to THIS product's
    authenticated api client (from @noctusai/seed/infra). Identical
    in shape to how the product binds every other seed-hook factory
    (createLLMHooks, createCrudHooks). Not promotable — it is the
    per-product binding by definition.
  - Conexao.tsx: the page. pt-BR copy, product ui-kit
    (@/components/ui/*), product nav placement. Presentational and
    product-specific UX; the data + mutations all come from the seed
    hook. The shared logic is in the seed; this is the skin.
seed_first_analysis: |
  Q1 — Cross-product candidate? The CAPABILITY yes, and it was
  already lifted: client/Fake/Protocol + `whatsapp_admin` router +
  `createWhatsAppConnectionHooks` are in noc (commit d81d88e). What
  remains here is the per-product consumption, which is NOT a
  cross-product candidate by construction.
  Q2 — Variance? The binding hook varies per product (different api
  client). The page varies per product (language, ui kit, nav, which
  controls to expose). High variance → stays product-local.
  Q3 — Existing seed coverage? Full, for the reusable part. The seed
  ships the hook factory + backend router; products supply only the
  api binding + page chrome.
  Q4 — Fake+Real? N/A at this layer (frontend consumption). The
  seed client already ships Fake+Real+factory.
  Q5 — Migration cost? N/A — nothing to migrate; the seam is in noc.
  Q6 — Premature-lift risk? Lifting the page/binding would be the
  WRONG direction (over-abstraction) — per-product UX must stay
  per-product. Correctly NOT promoted.
dependencies_on_other_additions:
  - seed-repo feat/whatsapp-connection-mgmt @ d81d88e (the
    `whatsapp_admin` router + `createWhatsAppConnectionHooks` this
    page consumes)
promoted_on: not-applicable (product-local; reusable part already in noc)
---

## Why this addition exists

Slice 1 of the WhatsApp-flow management work. The connection-pairing
pain (QR + webhook wiring previously done via curl + the WAHA
dashboard) is solved by a seed-level `whatsapp_admin` capability
(authored + committed in the noc seed repo on branch
`feat/whatsapp-connection-mgmt`, commit `d81d88e`).

These two product files are the thin consumption layer that surfaces
that capability inside youtube-crawler:

- **useWhatsAppConnection.ts** binds the seed
  `createWhatsAppConnectionHooks(api)` factory to the product's
  authenticated API client — the same one-liner pattern used for
  every other seed-hook factory in this product.
- **Conexao.tsx** is the page: live session status, QR pairing
  (auto-polling until linked), webhook configuration, restart, and
  unlink — pt-BR, product ui-kit, mounted under a new "WhatsApp"
  nav section.

The reusable logic is entirely in the seed; this is the product skin
and api binding, which correctly stay product-local.

## Caveat (recorded honestly)

The `standard_routers=[..., "whatsapp_admin"]` opt-in in
`products/youtube-crawler/backend/app/main.py` is NOT in the same
commit — that one line is entangled with unrelated accumulated
lifespan/intake work in the same file and is committed separately by
the user. Until that line is committed, this Slice-1 frontend commit
is not independently runnable.
