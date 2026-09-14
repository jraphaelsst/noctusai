# Academia de Reciclagem — MASTER-PROMPT

> Authoritative development guide for the `academia-de-reciclagem` product.
> Plan and milestones: `project-history/roadmaps/julia-agents-academia-2026-09.md`.

## Purpose

The workspace of a real project run by One Consultoria: environmental education for company
employees (recycling, reuse, waste reduction). This product owns the project's **knowledge**
and keeps it in the database with full revision history:

- knowledge base
- decisions
- open questions
- roadmap and tasks
- content drafts
- research sources

Humans use it through the UI. Julia, who lives in `agents`, works on it only through the
scoped API, and a person approves every write. The project's video training platform will be
built here later (roadmap trigger T3).

**Status (2026-09-14):** scaffold only. Every domain item below is PLANNED.

## Architecture (planned)

### Backend

```
products/academia-de-reciclagem/backend/app/
  main.py        → create_product_app("Academia de Reciclagem", "academia-de-reciclagem", settings)
  knowledge/     → KnowledgeStore Protocol · PgKnowledgeStore · FakeKnowledgeStore · factory
  routers/       → kb · decisions · questions · roadmap · tasks · content · sources · import (admin)
  auth/          → SSO users + product tokens (seed resolver, scopes academia:*), audit;
                   single-use approval assertions checked on every agent write
```

### Database — schema `academia_de_reciclagem`

| Table | What it holds |
|---|---|
| `kb_entries` | `slug`, `category`, `tags`, `summary`, `body_md`, `current_revision_id` |
| `decisions` | D-nn. Append-only: only `superseded_by` may change |
| `open_questions` | Q-nn |
| `roadmap_phases` | Roadmap phases |
| `tasks` | T-nnn, `blocked_by` |
| `content_drafts` | Content drafts |
| `timeline_events` | Project timeline |
| `research_sources` | Citation and `accessed_at` are required |
| `code_counters` | D/Q/T numbers, allocated under a row lock |
| `kb_revisions` | Append-only history for every entity, enforced by a trigger that blocks UPDATE and DELETE. Provenance: `user_id`, `agent_id`, `approval_id`, `channel`, `conversation_id`. Imported history also keeps `git_sha`, author, date and message |

Every table has RLS and is org-scoped via `public.current_org_id()`.

### Import of the original workspace

- **Bundle:** a JSONL export of every file revision from the original git history, loaded
  through an admin endpoint.
- **Never in the repo:** the bundle is secret-scanned first and must not be committed, because
  the repository is public.
- **Verification:** the imported revision count must equal the git revision count, and each
  entry's latest body hash must equal the HEAD file.

### MCP

The root `mcp/academia/` is a thin HTTP client over this API. Terminal-Julia uses it with a
personal token. The vendored `_kit` copy goes; the server uses noc's `mcp/_kit`.

### Frontend

Pages: KB browser, Decisions, Open questions, Roadmap / Tasks. They consume seed organs,
including `KanbanBoard` for tasks, and every page shows real data and owns its CRUD.

## What the framework provides automatically

- `/api/health`, `/api/team`, `/api/notificacoes`, `/api/llm/*`
- CORS, Sentry, exception handlers, middleware, rate limiting, logging
- Sidebar, Header, AppShell, page status filtering, SSO context, trial/license warnings

## Rules

- **No knowledge content in git.** The repository is public.
- **Decisions and revisions are append-only.** Superseding writes a new row that points back.
- **No agent write without a valid, unused approval assertion** from the `agents` product.
- **Never invent a domain fact.** A regulatory claim needs a `research_sources` citation.
- **Language:** UI copy and knowledge content in PT-BR; code, commits and technical docs in EN.
- **Auth tests assert strictly `== 401`.**

## Testing

```bash
cd products/academia-de-reciclagem/backend && pytest
cd products/academia-de-reciclagem/frontend && npx vite build
```

## Dependencies

- Backend: `noctusai_lib` + `noctusai_seed`
- Frontend: `@noctusai/lib` + `@noctusai/seed`
