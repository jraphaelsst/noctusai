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

### Julia v2 — shared lead thread and controls (A-THREAD)

- A lead's conversation is ONE `conversations` row (`tipo='thread_lead'`) shared by every agent; each agent is a
  participant (`thread_participantes`, at most one `ativo`) and each message carries its author agent and the lead.
  Stores: `stores/threads.py` (lead_refs, participants, hand-offs, consent, per-agent context),
  `stores/agent_controles.py` (`modo_operacao`, `dreno_inatividade_dias`).
- `channels/controles.py::decidir` is the pure decision table (ligado / drenando / desligado x thread x participant x
  trigger); `aplicar_controles` reads the control fail closed (503 `controle_indisponivel`), creates the thread and
  applies the implied transition. The turn route calls it before persisting anything or calling a model.
- `routers/channel_threads_router.py`: thread read, append-without-a-turn, pause / resume (with optional until-when),
  controls (SW reads, Studio admin writes; turning ON also needs complete content via `conteudo_status`), hand-off
  notes, opt-in / opt-out, delete-by-lead, and an org-admin thread read that strips system rows, tool results and stamps.
- Migrations 033 (threads), 034 (controls), 035 (constraint swap — apply only after the backfill is verified).

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
  contradicts a platform-locked rule is refused 422) and `GET /agents/{key}/status` (booleans only). The clients,
  knowledge, evals and package-sync routers are platform-admin only too; the `studio:content-write` token is minted
  only via `POST /api/studio/plataforma/content-token` (issuer `noctus-platform`).

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
