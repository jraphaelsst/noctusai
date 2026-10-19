# Agentes — MASTER-PROMPT

> Authoritative development guide for the `agents` product.
> Plan and milestones: `project-history/roadmaps/julia-agents-academia-2026-09.md`.

## Purpose

Home of the NoctusAI managed AI agents. An agent works **on** another product through that
product's scoped API and never touches its database. Two agents in this release:

- **Bia** runs here, on the Claude Agent SDK in headless mode. She is reachable only from
  this app's UI. Her job is helping with the Academia de Reciclagem project, which she does
  by reading the `academia-de-reciclagem` API and proposing writes to it. A person approves
  or denies every write before it happens.
- **One Chat** runs inside `social-wiring` (WhatsApp) and stays there. This product lists it
  and switches its auto-reply on/off through a scoped social-wiring endpoint.

**Status (2026-09-14):** scaffold only. Every domain item below is PLANNED.

## Architecture (planned)

### Backend

```
products/agents/backend/app/
  main.py            → create_product_app("Agentes", "agents", settings)
  runtime/           → AgentRuntime Protocol · ClaudeAgentSdkRuntime · FakeAgentRuntime · make_agent_runtime()
  gate/              → approval gate: tool classification, pending approvals, timeout = deny,
                       single-use signed approval assertions sent to the target product
  agents/bia/      → spec.yaml · BIA.md · plugin/skills/ar-* (baked, read-only, CODEOWNERS-guarded)
  tools/             → in-process SDK MCP tools that proxy HTTP to academia AFTER the gate
                       (the CLI subprocess never sees a product token)
  routers/           → conversations · messages · approvals · persona · agents (list, on/off)
  clients/           → academia API client · social-wiring toggle client (seed token scheme)
```

### Bia's hardened launch (non-negotiable)

- `setting_sources=[]`: no project `CLAUDE.md`, `settings.json` or hooks get loaded.
- Explicit `allowed_tools`: the academia tool proxies, `WebSearch`, and `Skill` restricted to
  an explicit skill list.
- Explicit `disallowed_tools`: Bash, Write, Edit, MultiEdit, NotebookEdit, Task, WebFetch,
  Read, Grep, Glob.
- `strict_mcp_config`, a minimal explicit `env`, and the CLI running under its own uid.
- Container: `cap_drop: ALL`, `no-new-privileges`, read-only root filesystem, `--workers 1`.
  The approval wait lives in one process, and each approval row records `instance_id`.

### Database — schema `agents`

`agents` · `agent_personas` (versioned, one active per agent) · `conversations` (owner) ·
`messages` · `approvals` (`instance_id`). Every table has RLS; the tables are org-scoped via
`public.current_org_id()`.

### Frontend

The Agents UI (Bia chat, inline approvals, persona, agent list with toggles) consumes the
seed `ChatWindow` organ and `useRealtimeStream`. It adds no local chat components.

### Platform-defined agents and org specs (Julia v2 — `app/studio/`)

- `definition_scope`: `org` (default — owns its versions) · `plataforma` (THE definition of a key, in the
  platform org, one per key) · `instancia` (an org's instance: no versions). Opt-in per key through
  `plataforma.py` (`julia` today). `conteudo_modo='linhas'` (always for plataforma/instancia): every
  compiler string is a row of `agent_version_textos`, the tools block lists `agent_version_ferramentas`,
  decisions are `agent_version_decisoes`, the `{{org.x}}` placeholders are declared in `agent_version_specs`;
  the org's values live in `agent_org_specs`. The registry (`textos_registry.py`, `ferramentas_registry.py`)
  holds KEYS only; a missing required text is a blocking warning and publish answers 409
  `conteudo_incompleto` — never a default string.
- `resolucao.resolve_agent_for_org(store, org_id, key)` → `(instancia, definicao, versao, specs)`;
  `compile_for_org` compiles the definition with that org's values (the hash covers texto + every content
  row + the pinned standard); `carimbo` = the version tuple stamped on messages; `ponto_cache` is the
  prompt-cache breakpoint (static prefix before the client block).
- Visibility tiers (server-side): definition reads (`versions`, `compiled`, `prompts/{hash}`, `diff`,
  textos/ferramentas/decisoes/payload, compiled-per-org) are **platform-admin only**, audited as
  `definicao_lida`; writes are platform admin or a `studio:content-write` token (audited
  `conteudo_editado_mcp`); an org admin gets `GET/PUT /agents/{key}/specs` (its own values; text that
  contradicts a platform-locked rule is refused 422) and `GET /agents/{key}/status` (booleans only).

## What the framework provides automatically

- `/api/health`, `/api/team`, `/api/notificacoes`, `/api/llm/*`
- CORS, Sentry, exception handlers, middleware, rate limiting, logging
- Sidebar, Header, AppShell, page status filtering, SSO context, trial/license warnings

## Rules

- **No database access to another product.** Use its API with a scoped, expiring product token.
- **Every agent write goes through the approval gate.** An unanswered request is denied.
- **No client or company facts in this directory.** The repository is public; knowledge lives
  in academia's database.
- **Auth tests assert strictly `== 401`.** Owner checks return 404 on a foreign conversation.
- **Loading states:** `showSkeleton = isPending && !data`, `isRefreshing = isFetching && !!data`.

## Testing

```bash
cd products/agents/backend && pytest
cd products/agents/frontend && npx vite build
```

## Dependencies

- Backend: `noctusai_lib` + `noctusai_seed`; `claude-agent-sdk` (planned, M4)
- Frontend: `@noctusai/lib` + `@noctusai/seed`
