# Academia de Reciclagem

The workspace of a real project run by One Consultoria: environmental education for
company employees (recycling, reuse, waste reduction). This product holds the project's
**knowledge** — knowledge base, decisions, open questions, roadmap and tasks — in its
database, with full revision history. Later it will host the project's video training
platform.

Julia (the AI assistant in the `agents` product) works on this project only through this
product's scoped API, with every write approved by a person.

> **Status:** live in prod at `https://academia.noctusai.com` behind SSO since 2026-09-16;
> the original workspace history was imported and verified on 2026-09-17 (M2). See
> `project-history/roadmaps/julia-agents-academia-2026-09.md` for milestones M1–M6.
>
> **Public repository:** no client or company facts belong in this directory. Knowledge
> lives in the database; import bundles are loaded from outside the repo.

## Stack

- Backend: FastAPI via `create_product_app()` (`noctusai_seed`) + `noctusai_lib`
- Frontend: React + Vite + TypeScript via `createProductApp()` (`@noctusai/seed`)
- Database: Supabase, schema `academia_de_reciclagem`

Ports: backend **8015**, frontend **8190** (single container in prod).

## Running

```bash
./start.sh academia-de-reciclagem
```

## Capabilities

| Capability | Status |
|---|---|
| Knowledge base entries with append-only revisions and provenance | shipped (M2) |
| Decisions (D-nn, append-only), open questions (Q-nn), roadmap phases, tasks (T-nnn) | shipped (M2) |
| Import of the original workspace history (verified revision counts + hashes) | shipped (M2) |
| Scoped API (SSO users + product tokens) consumed by Julia and the `academia.*` MCP tools | shipped (M2) |
| UI: KB browser, Decisions, Open questions, Roadmap / Tasks | shipped (M2) |
| Video training platform | deferred (roadmap T3) |

## Tests

```bash
cd products/academia-de-reciclagem/backend && pytest
cd products/academia-de-reciclagem/frontend && npx vite build
```
