# ommie-seed — Future Plan (Not Active)

**Status:** Concept / planning note. Not an active project. Do not start work until explicitly greenlit.

## Concept

`ommie-seed` mirrors the same **seed** concept used for NoctusAI's existing products, but applied to the **Omie** (Brazilian ERP, omie.com.br) ecosystem.

The goal is to **multiply Omie marketplace solutions to sell** — i.e., a reusable starter/template that can be cloned and specialized into many sellable Omie-integrated solutions on the Omie marketplace.

## Why it's worth considering

- Omie has a public REST API with uniform `call`/`param` envelope across all resources — one generic wrapper covers the entire API surface, which makes a seed/template approach very leverage-able.
- An MIT-licensed reference MCP exists (`@codespar/mcp-omie` in `codespar/mcp-dev-brasil`) — a useful study reference, not a fork target.
- Omie's marketplace is a distribution channel NoctusAI doesn't currently tap.

## When picking this up

- The directory `/Users/rapha/Documents/repository/NoctusAI/ommie-seed/` already exists (empty placeholder).
- Compare against the existing NoctusAI product seeds (`noctus-starter`, `noctusai-template`) to align conventions before scaffolding.
- Decide scope of the first seed: full ERP coverage vs. narrow vertical (e.g., products + orders only).

## Out of scope for now

No implementation. No scaffolding. No dependency choices. This note exists so the idea isn't lost.
