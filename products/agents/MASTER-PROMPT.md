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

### Julia v2 — the channel runtime (A-RT)

- `POST /api/channels/turns` (`routers/channels_router.py` -> `channels/turno.py`): `resolve_agent_for_org` (platform
  definition + the org's specs) -> `aplicar_controles` under the turn lock (a non-`normal` status answers with no model
  call; the inbound is stored per the decision) -> abuse limits (`canal_limites`, per chat) -> `JuliaTurno` (server-side
  ids; the model never names an org or a lead) -> the provider-neutral runtime -> conformance -> one assistant row
  stamped with the version tuple. `contexto.estado` is closed and typed (attendant, re-engagement flavour, campaign
  origin, credit); the v1 request shape is still accepted for one release. The generated JSON Schema is
  `backend/contracts/channels.v2.json` (drift-tested): SW validates against it.
- `channels/tool_registry.py`: `TOOLS` = strict argument models (schema in code, no description); the description of a
  tool and of each parameter / enum value is a row of `agent_version_ferramentas`. Gates: required skill opened in this
  thread under the CURRENT compiled hash (`obrigatoria_skill` on the row, or the shared library's `obrigatoria_para`
  through `SkillFonte`), `trecho` in the lead's own words, `pode_ofertar`, `pode_concluir`, offered-before-react,
  identity only when the standard says so. Refusals are typed codes; the wording is `ferramenta.resultado.recusa.<codigo>`.
  Past `max_recusas_por_turno` / `max_erros_ferramenta_por_turno` the toolset stops the turn (`should_stop`) and the turn
  ends in a hand-off to the org owner + a flagged event (silence, or the DB text `runtime.parada_segura`).
- `channels/contexto.py`: the second system message (state + dossier + hand-off note + credit + re-engagement) rendered
  from DB texts; lead-influenced values are JSON literals on one line. `channels/extracao.py`: the summary (narrative
  only) and the transport decision (`agent_version_decisoes`; fallback = the row's `padrao` option).
- `channels/conformidade.py` + migration 037: detectors, the prompt-leak fingerprint (hashes only, computed at
  publish), policy per rule (`registrar` | `bloquear`; the leak rule blocks by default: suppress, ONE corrective re-run
  with the DB text, else silence + hand-off + a flagged row), the deterministic escalations (rule data), the
  extraction-attempt signal. Migration 037 also closes `qual-lead-ref-fk` (cascade erasure) and lets a hand-off end
  `concluido`.
- A new required text key must be seeded as data BEFORE the code that needs it deploys (`textos_registry`); an org
  seeded earlier gets 409 `conteudo_incompleto`, never a default string.

### Julia v2 — mechanism evals as the publish gate (A-EVAL)
- `eval_cases` gain `suite` (`mecanismo` | `comportamento`), `k`, `roteiro` (scripted multi-turn lead messages + fixture catalogue) and `asserts` (deterministic, code-checked: ferramentas_incluem/proibidas, estagio_final, criterios_registrados, ofertas_por_lote, sem_violacoes, identificacao_completa, handoff_para, sem_vazamento, skill_aberta_antes_de). Migration 038, service-role only.
- `app/studio/eval_mecanismo.py` runs pass^k (a case passes only if all k executions pass), supports sharded scenarios and a `limite_usd` cost cap; runs are stored in `eval_mecanismo_runs` / `eval_mecanismo_execucoes`.
- Publish of an agent with `exige_mecanismo` (or any active mecanismo case) requires the newest LIVE run for the current compiled hash to be complete, under budget and fully green — enforced in the router AND in the DB publish function (409 `mecanismo_reprovado`). The `comportamento` (judge) suite is advisory unless `comportamento_bloqueia`.
- The turn driver is a Protocol (`app/studio/eval_driver.py`, `tipo` live|fake); `POST /api/studio/agents/{key}/draft/mecanismo-runs` (platform admin) runs the suite. Eval fixtures are synthetic: a PII guard refuses phones/CPF/emails (never real WhatsApp transcripts — Meta WhatsApp Business terms §4.7).

### Julia v2 — consumer and Studio support (A-RT2, migration 040)
- `GET /api/channels/agents/{key}/qualificacao/estagios` (channel token) → ordered `[{chave, rotulo, ordem, conclusivo}]` only; the turn response carries `qualificacao.estagios_ordem`.
- Publish pins the qualification standard version on the agent version (`qualificacao_versao_id`, inherited by new drafts, covered by `compiled_hash`); `GET|PUT /api/studio/agents/{key}/(draft/)qualificacao` (platform admin).
- `GET /api/agents/catalogo` — tiered: org users get `{key, nome, papel, descricao_publica, runtime, capacidades}` from DB rows (`catalogo_agentes`, `catalogo_capacidades`); platform admins also tool keys + versions. One Chat is listed as `runtime=external`, papel `operador`.
- Studio support: `/capacidades` (server-provided tier + tabs), conformidade rule/violation routes (codes only), thread result + participant state on the channel conversation list, textos/ferramentas registry (structure only), `ponto_cache` in compiled outputs, mecanismo summary on versions.
- Atomic optimistic lock: the replace-set PUTs send `expected_hash` → `replace_draft_conteudo(p_expected_hash)` locks the draft row and refuses a stale writer (409 `conflito_de_versao`).
- Mechanism eval runs are async (202 + poll), use the live turn driver against the definition's real conformance rules, and orphaned runs are swept at startup.

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

`/agentes/catalogo` (`pages/AgentesCatalogo.tsx`, `hooks/useAgentesCatalogo.ts`; nav route `agentes-catalogo`, migration 040) shows one card per agent from `GET /api/agents/catalogo`: name, papel, runtime (Interno/Externo), public description, capability chips, with a papel filter. It renders display-level fields only; `ferramentas` / `versao_ativa` appear only when the server sends them (platform admins) and are never requested or inferred (owner IP rule, 2026-10-19).

#### Studio, tier-aware (Julia v2 — `frontend/src/pages/studio/`)

Which tabs render is decided by the SERVER row, never by a role string: `definition_scope` on
`/api/studio/agents[/{key}]` (`studioTier()` / `visibleTabsFor()` in `studioTabs.ts`).

| Surface (`definition_scope`) | Who | Tabs |
|---|---|---|
| `plataforma` (THE definition, platform org) | platform admin | Visão geral (+ Controles card) · Prompt · Textos do sistema · Ferramentas · Decisões · Qualificação · Skills da biblioteca (pins, `obrigatoria_para`, "nova versão") · Especificações declaradas · Avaliações · Configurações · Conformidade · Conversas · Versões · Compilado (version payload with cache breakpoint + every off-prompt row, and the per-org view) |
| `instancia` (this org's instance) | org admin | Visão geral (readiness only) · Especificações da org · Controles · Conversas. No Prompt / Ferramentas / Qualificação / Textos / Decisões; platform blocks are a label |
| `instancia` | org member | none of the Studio content tabs |
| `org` / legacy | admin | the pre-v2 tab set, unchanged |

Rules the screens keep: content lives only in DB rows (the bundle carries no prompt, rule or fixture
text; tests use synthetic fixtures under `__tests__`; the build ships no sourcemaps); edits are
draft-only and a replace-set `PUT` is preceded by a compare-before-write read (a moved server draft
raises the conflict banner and nothing is written); a save always refetches, nothing is cached as
truth; "Rascunho v{n} · editável" vs "Publicada v{n} · somente leitura" is always shown; loading uses
`showSkeleton = isPending && !data` / `isRefreshing = isFetching && !!data` (computed in the hooks).
Org-spec refusals (`spec_conflita_com_regra_fixa`) render inline on the offending field with the locked
block's label only; qualification publish refusals (`regras_invalidas`) list every rule error with its
path; the Controles dialog states what happens to the open conversations before a mode change.
Open gaps are marked `NOC-REMEDIATE[...]` in `types-julia.ts` and the `use*` hooks (conformidade
routes, studio thread state/results).

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
- DB lockdown (migration 036): every agents table is service-role only — no anon/authenticated grant or
  policy (except read-only `status_pagina`), so a browser session cannot read content over PostgREST.
  New migrations must keep it so (keeper `check_no_authenticated_grant_on_content_tables`).
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
  Reading, authoring and publish (rule validation, 422 with every problem) are platform-admin only (criteria, weights and rules are platform IP; orgs and SW only get the computed state); the `studio:content-write` token (the `noctus.agents.content` MCP tool) may read and write DRAFTS, never publish:
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

## Shared skill library (Julia v2, `app/stores/skills_biblioteca.py`, migration 039)

Agents use skills instead of their own judgement, from ONE standardised, versioned library used the same way by
every agent (CONTRACT D7/D8). Skill text is DB data; code carries no skill content.

- **Library** (platform-wide, no org): `skills_biblioteca` (key + admin label) -> `skill_versoes` (the one-line
  index description the model sees + the body; draft / published / archived, a published version is immutable by
  trigger) -> `skill_versao_arquivos` (reference files). Service-role only: no tenant grant on any of the four
  tables (IP). Authoring is platform-only: `/api/skills-biblioteca/*` (platform admin, or the `studio:content-write`
  token for DRAFTS; publishing a skill version stays a human act, 403 `user_required` for the token).
- **Pins**: `agent_version_skill_refs(version_id, skill_versao_id, obrigatoria_para[], ordem)` pins a library
  version to an agent version (`obrigatoria_para` = the tools that refuse until the skill was opened in the thread).
  A new draft inherits the pins by an AFTER INSERT trigger; a pin change invalidates the draft's `compiled_hash`
  and the pins are hash-covered (`compiler.hash_payload`, only when the version pins any). Pin / re-pin / unpin on
  the draft: `PUT|DELETE /api/studio/agents/{key}/draft/skills-biblioteca/{skill}`; each pin carries the
  "new version available" indicator (`nova_versao`).
- **Compiler**: a pinned skill joins the `# Skills` index (key + description) and the on-demand layer
  (`abrir_skill` / `ler_arquivo_skill`); a gate on a tool the code does not know is a blocking warning.
- **Runtime interface** (`app/studio/skills_contract.py`, tiny, imported by the compiler and by the runtime):
  `SkillsRuntime.skill_refs_for(version_id) -> [SkillRef(skill_key, skill_versao_id, obrigatoria_para, ...)]` and
  `abrir(skill_key, skill_versao_id) -> SkillAberta(corpo, arquivos) | None` (the PINNED version, never "latest").
  Every compile site reads the pins through one slot (`studio.bundles.configure_skill_refs_provider`, wired by
  `install_studio_seams`), so a hash can never differ by call site.
- **Channel turn**: `app/studio/skills_fonte.py` implements the runtime's `SkillFonte` over the library (`get_skills_factory_dep`): `abrir_skill` / `ler_arquivo_skill` serve the version's PINNED library version (never the latest), then its own skills; the pins' `obrigatoria_para` become the tool gates (`skill_nao_aberta`).
- **MCP**: `noctus.agents.content` (`mcp/noctusai/tools/noctus/agents/content.py`) writes any content kind
  (sections, textos, ferramentas, decisoes, spec declarations, library skills + pins, standard criteria/stages/
  parameters) into a target environment through these routes: drafts only, dry-run by default, payload from a
  file outside git, token from `NOCTUS_AGENTS_CONTENT_TOKEN`.

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
