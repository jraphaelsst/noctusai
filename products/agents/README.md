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
Every agents table is **service-role only** (migration 036): the browser's Supabase session cannot read
any of them over PostgREST, except `status_pagina` (read-only). All reads go through the API tiers above
(keeper `check_no_authenticated_grant_on_content_tables`, DB probes `agents.content_tables.*`).

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
| Julia (SDR) shared lead thread: one thread per lead across all agents, per-agent participants, hand-off notes, consent (opt-in / opt-out), delete-by-lead | Julia v2 |
| Julia controls: ligado / drenando / desligado per agent (decided by the agents app on every turn, fail closed) and a per-conversation pause / resume | Julia v2 |
| Julia channel turn v2 (`POST /api/channels/turns`): resolves the platform definition + the org's specs, applies the controls under the turn lock, reads the dossier + thread context, runs a skill-gated toolset (schemas in code, descriptions in `agent_version_ferramentas`), stamps every reply with the version tuple; JSON Schema in `backend/contracts/channels.v2.json` | Julia v2 |
| Studio UI (tier-aware by the server's `definition_scope`): platform admins edit the definition (prompt sections, system texts, tool descriptions, decisions, the qualification standard, library skill pins, declared specs, conformance) and read the compiled view; org admins see only their specs form, controls (ligado / drenando / desligado with a confirmation dialog), conversations and results; members see none | Julia v2 |
| Julia conformance + IP protection: post-turn detectors (offered-property, ends-with-question, profile-cited-without-record, fallback, repeated-question) and the prompt-leak detector (per-org canary + 12-token shingles; blocks by default, also on the studio test chat and eval outputs for non-platform-admins); per-chat turn/day/spend limits and refusal/error budgets, all data (`conformidade_*`, `canal_limites`) | Julia v2 |
| Julia mechanism evals: scripted multi-turn cases with deterministic asserts, pass^k, cost cap; a green LIVE run for the current compiled hash gates publish (router + DB); synthetic fixtures only (PII-guarded) | Julia v2 |
| Shared skill library: one standardised, versioned set of skills every agent opens the same way; agent versions pin library versions (`obrigatoria_para` gates tools), Studio shows "new version available"; platform-only authoring and the `noctus.agents.content` MCP tool (drafts only) | Julia v2 |

## Lead qualification standard (Julia v2, `app/qualificacao/`)

One platform-wide standard (`imob-lead`), versioned, the same for every org: no per-org fork. The
model only records criterion values through tools; **score and stage are computed** by the pure
`engine.calcular` and never judged by a model. Everything that is content is DB data:

- **Library** (migration 032): `qualificacao_padroes/_versoes/_criterios/_estagios/_parametros`;
  a published version is immutable (triggers); `agent_versions.qualificacao_versao_id` pins one.
  Reading, authoring and publish (rule validation, 422 with every problem) are platform-admin only (criteria, weights and rules are platform IP; orgs and SW only get the computed state):
  `/api/qualificacao/*`.
- **Criteria** carry a score `eixo` (several named axes + the total), `escopo` (sdr / financeiro / ...:
  a scope's `avaliar_lead` only asks its own criteria, records are shared on the lead), `validade_dias`
  (older records stop counting), type `derivado` (system signals the model cannot record) and
  `identificacao`. Axis config (`parametros.eixos`): `max`, `multiplicadores` (rule x factor), `decaimento`
  (factor after N days without a lead reply).
- **Stages** are rules in a closed DSL (`todos/algum/nao`, `criterio`, `score` incl. `eixo`, `evento`,
  `contagem`, `identificacao: completa`); every node may carry an `id` (explainability: `regra_id` +
  per-axis `detalhe`). A `terminal` stage is only ever **suggested** (`descartado_sugerido`); a human
  confirms it (`POST /api/channels/leads/{ref}/descarte/confirmar`, actor stored) - LGPD art. 20.
- **Service** (`QualificacaoService`): `avaliar`, `registrar_perfil` (the `trecho` must be in the lead's own
  recent messages), `registrar_evento_imovel`, `pode_concluir`, `confirmar_terminal`, `apagar_por_lead`.
  Refusals are typed codes; their wording lives in DB texts.
- **Lead identity** (`identificacao.py`): name/e-mail/CPF/RG apart from the records, CPF/RG Fernet-encrypted
  with the fleet `ENCRYPTION_KEY`, masked by default, clear text only for org owner/admin via an audited
  endpoint; 180-day retention and delete-by-lead cover it.

## Tests

```bash
cd products/agents/backend && pytest
cd products/agents/frontend && npx vite build
```
