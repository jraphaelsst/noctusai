# Agentes

Home of the NoctusAI managed AI agents. An agent here works **on** other products
through their scoped APIs — never through their databases.

- **Bia** — Claude Agent SDK (headless), reachable from this app's UI only. She helps
  run the Academia de Reciclagem project: reads its knowledge base and proposes writes,
  which you approve or deny before anything lands.
- **One Chat** — the WhatsApp assistant that keeps running inside `social-wiring`. Listed
  here with its on/off toggle (through social-wiring's scoped API); its behaviour is not
  managed from this product.

> **Status:** scaffolded 2026-09-14. Domain code is planned, not built — see
> `project-history/roadmaps/julia-agents-academia-2026-09.md` (milestones M1–M6).

## Platform-defined agents (Julia v2)

**Julia** (the real-estate SDR) is ONE definition for every org, specified per org. The definition
— prompt sections, skills, system texts, tool descriptions, decisions, the qualification standard — is a
set of DB rows owned by the platform org (`definition_scope='plataforma'`), edited and read **only by
platform admins** (Studio / `noctus.agents.content`); each org has an *instance* row
(`definition_scope='instancia'`: on/off, LLM key, budget) plus its **org specs** (`agent_org_specs`: agency
name, regions, knowledge, ...) that the definition references as `{{org.chave}}`. An org admin sees and edits
only its own specs and a readiness status — never the prompt, hashes, tool descriptions or rules. No prompt
text lives in code (keeper `check_agent_prompt_text_in_code`). Design: `projects/julia-v2/CONTRACT.md` §2.6.

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
| Chat with Bia (streamed turns, tool cards) | M4 |
| Approve / deny Bia's writes to Academia (single-use signed approvals, timeout denies) | M4 |
| Bia persona (admin-only, versioned, model allowlist) | M4 |
| Agent list with on/off — Bia, and One Chat via social-wiring | M4, M5 |
| Isolation suite (no platform secrets in Bia's env; cross-product token denials) | M4 |

## Tests

```bash
cd products/agents/backend && pytest
cd products/agents/frontend && npx vite build
```
