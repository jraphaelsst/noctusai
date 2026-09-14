# Agentes

Home of the NoctusAI managed AI agents. An agent here works **on** other products
through their scoped APIs — never through their databases.

- **Julia** — Claude Agent SDK (headless), reachable from this app's UI only. She helps
  run the Academia de Reciclagem project: reads its knowledge base and proposes writes,
  which you approve or deny before anything lands.
- **One Chat** — the WhatsApp assistant that keeps running inside `social-wiring`. Listed
  here with its on/off toggle (through social-wiring's scoped API); its behaviour is not
  managed from this product.

> **Status:** scaffolded 2026-09-14. Domain code is planned, not built — see
> `project-history/roadmaps/julia-agents-academia-2026-09.md` (milestones M1–M6).

## Stack

- Backend: FastAPI via `create_product_app()` (`noctusai_seed`) + `noctusai_lib`
- Frontend: React + Vite + TypeScript via `createProductApp()` (`@noctusai/seed`)
- Database: Supabase, schema `agents`
- Agent runtime: `claude-agent-sdk` behind an `AgentRuntime` Protocol (Fake + Real + factory)
- Realtime: `noctusai_lib.realtime` SSE

Ports: backend **8016**, frontend **8200** (single container in prod: uvicorn serves the API and the SPA).

## Running

```bash
./start.sh agents
```

## Planned capabilities

| Capability | Milestone |
|---|---|
| Chat with Julia (streamed turns, tool cards) | M4 |
| Approve / deny Julia's writes to Academia (single-use signed approvals, timeout denies) | M4 |
| Julia persona (admin-only, versioned, model allowlist) | M4 |
| Agent list with on/off — Julia, and One Chat via social-wiring | M4, M5 |
| Isolation suite (no platform secrets in Julia's env; cross-product token denials) | M4 |

## Tests

```bash
cd products/agents/backend && pytest
cd products/agents/frontend && npx vite build
```
