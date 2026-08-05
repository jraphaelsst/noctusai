# ommie-seed — Future Plan (Not Active)

**Status:** Concept / planning note. Not an active project. Do not start work until explicitly greenlit.

> **Update 2026-08-05 — the connector leg is BUILT.** The API-access half of
> this idea now ships as **`mcp/omie`** (connector MCP, composes `mcp/_kit`):
> complete coverage of Omie's 134 endpoints / 461 methods, multi-company
> "environment" profiles with readonly pinning, and a bundled offline API
> catalog harvested from Omie's developer portal. See `mcp/omie/README.md`.
>
> What remains conceptual is the **seed/marketplace** half below — a product
> template cloned into sellable Omie-integrated solutions. That is still not
> greenlit. The connector is infrastructure such a seed would consume, not the
> seed itself.

## Concept

`ommie-seed` mirrors the same **seed** concept used for NoctusAI's existing products, but applied to the **Omie** (Brazilian ERP, omie.com.br) ecosystem.

The goal is to **multiply Omie marketplace solutions to sell** — i.e., a reusable starter/template that can be cloned and specialized into many sellable Omie-integrated solutions on the Omie marketplace.

## Why it's worth considering

- Omie has a public REST API with uniform `call`/`param` envelope across all resources — one generic wrapper covers the entire API surface, which makes a seed/template approach very leverage-able.
  **Confirmed in practice:** `mcp/omie/api.py` is that one wrapper, and it reaches all 461 methods.
- An MIT-licensed reference MCP exists (`@codespar/mcp-omie`, in `codespar/mcp-dev-brasil` → now `codespar/mcp-dev-latam`) — a useful study reference, not a fork target. `mcp/omie` was built house-native on `_kit`, not forked.
- Omie's marketplace is a distribution channel NoctusAI doesn't currently tap.

## When picking this up

- The directory `/Users/rapha/Documents/repository/NoctusAI/ommie-seed/` already exists (empty placeholder).
- Compare against the existing NoctusAI product seeds (`noctus-starter`, `noctusai-template`) to align conventions before scaffolding.
- Decide scope of the first seed: full ERP coverage vs. narrow vertical (e.g., products + orders only).
- **Consume `mcp/omie`** for API access rather than re-implementing a client — transport, fault classification, rate limiting and the environment model are already solved there.

## Out of scope for now

No seed scaffolding. No product template. No dependency choices for the seed
itself. This note exists so the idea isn't lost.
