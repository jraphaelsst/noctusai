# Academia de Reciclagem

The workspace of a real project run by One Consultoria: environmental education for
company employees (recycling, reuse, waste reduction). This product holds the project's
**knowledge** — knowledge base, decisions, open questions, roadmap and tasks — in its
database, with full revision history. Later it will host the project's video training
platform.

Julia (the AI assistant in the `agents` product) works on this project only through this
product's scoped API, with every write approved by a person.

> **Status:** scaffolded 2026-09-12. Domain code is planned, not built — see
> `project-history/roadmaps/julia-agents-academia-2026-09.md` (milestones M1–M6).
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

## Planned capabilities

| Capability | Milestone |
|---|---|
| Knowledge base entries with append-only revisions and provenance | M2 |
| Decisions (D-nn, append-only), open questions (Q-nn), roadmap phases, tasks (T-nnn) | M2 |
| Import of the original workspace history (verified revision counts + hashes) | M2 |
| Scoped API (SSO users + product tokens) consumed by Julia and the `academia.*` MCP tools | M2 |
| UI: KB browser, Decisions, Open questions, Roadmap / Tasks | M2 |
| Video training platform | deferred (roadmap T3) |

## Tests

```bash
cd products/academia-de-reciclagem/backend && pytest
cd products/academia-de-reciclagem/frontend && npx vite build
```
