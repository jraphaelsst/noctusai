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
No agent KEY lives in code either (migration 049): a platform definition is any `plataforma` row, created
with any key by `POST /api/studio/plataforma/agents` and configured by `GET/PATCH
/api/studio/plataforma/agents/{key}` — `escopo_qualificacao`, `padrao_qualificacao`, `rascunho_padrao`
(first-draft settings), `instanciavel` (published ⇒ instantiated in every org; DEFAULT false, never true for an `owner_product` definition — a closed one reaches only orgs granted via `definition_org_grants` / `noctus.agents.content action=conceder`; KB § PATTERNS/compliance/org-config-isolation.md), `papel`
(`gerador`/`exemplar`). `usa_canais` (derived: `owner_product` set and `runtime='llm'`) gates channel UI.
The only key literal left is the `lead-imob`→`julia` token alias (`app/channels/chaves_legadas.py`,
`NOC-REMEDIATE[drop-lead-imob-alias]`).

**AI-generated first drafts** (migration 049, `app/studio/geracao.py`): `POST
/api/studio/agents/{key}/geracoes {briefing, areas?, forcar?, limite_usd≤5}` → 202, background job (plan
call + one call per area: secoes, textos, ferramentas, decisoes, specs, skills, configuracoes), polled via
`GET .../geracoes[/{id}]`, per-area `repetir` and run `cancelar`. The generator is the published platform
agent with `papel='gerador'` (its sections `planejamento` + `area-<area>` are the instructions); the
structure exemplar is the published `papel='exemplar'` definition. Writes the DRAFT only, never publishes;
cost cap checked before every call (over budget ⇒ area `pulado`); skills only from `skills_biblioteca`;
generated-vs-published diff stored on first publish (`geracoes.aprendizado`). Chat path: MCP
`noctus.agents.content` actions `gerar` / `geracao` / `configurar_agente` / `definicao`.
Every agents table is **service-role only** (migration 036): the browser's Supabase session cannot read
any of them over PostgREST, except `status_pagina` (read-only). All reads go through the API tiers above
(keeper `check_no_authenticated_grant_on_content_tables`, DB probes `agents.content_tables.*`).

## Stack

- Backend: FastAPI via `create_product_app()` (`noctusai_seed`) + `noctusai_lib`
- Frontend: React + Vite + TypeScript via `createProductApp()` (`@noctusai/seed`)
  - Studio "Gerar com IA" (S3a): the new-agent wizard's "Gerar com IA" mode (`/agentes/novo`) sends the briefing on create; the agent Overview tab (`GeracaoPanel`) uses the `BriefingForm`; runs are polled until terminal; draft editors badge items from the latest run ("Gerado por IA" / "Gerado · editado").
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
| Julia (SDR) shared lead thread: one thread per lead across all agents, per-agent participants, hand-off notes, consent (opt-in / opt-out, with an auditable event + an in-app notice to the org's owners/admins when a lead asks to stop; the opt-out is a per-org setting owned by social-wiring, which reads the history, re-sends failed notices and reactivates a lead over token routes; a thread banner in the staff view), delete-by-lead | Julia v2 |
| Julia controls: ligado / drenando / desligado per agent (decided by the agents app on every turn, fail closed) and a per-conversation pause / resume | Julia v2 |
| Julia channel turn v2 (`POST /api/channels/turns`): resolves the platform definition + the org's specs, applies the controls under the turn lock, reads the dossier + thread context, runs a skill-gated toolset (schemas in code, descriptions in `agent_version_ferramentas`), stamps every reply with the version tuple; JSON Schema in `backend/contracts/channels.v2.json` | Julia v2 |
| Studio UI (tier-aware by the server's `definition_scope`): platform admins edit the definition (prompt sections, system texts, tool descriptions, decisions, the qualification standard, library skill pins, declared specs, conformance) and read the compiled view; org admins see only their specs form, controls (ligado / drenando / desligado with a confirmation dialog), conversations and results; members see none | Julia v2 |
| Julia conformance + IP protection: post-turn detectors (offered-property, ends-with-question, profile-cited-without-record, fallback, repeated-question) and the prompt-leak detector (per-org canary + 12-token shingles; blocks by default, also on the studio test chat and eval outputs for non-platform-admins); per-chat turn/day/spend limits and refusal/error budgets, all data (`conformidade_*`, `canal_limites`) | Julia v2 |
| Julia mechanism evals: scripted multi-turn cases with deterministic asserts, pass^k, cost cap; a green LIVE run for the current compiled hash gates publish (router + DB); synthetic fixtures only (PII-guarded), identity scripted with `[[cpf_sintetico_valido]]` / `[[email_sintetico]]` tokens generated per execution; cases writable by the `noctus.agents.content` MCP tool (kind `evals_mecanismo`) | Julia v2 |
| Content-token UI: platform admins mint / list / revoke the `noctus.agents.content` MCP token from the `/agentes` listing (expiry in days 1..365 or never, secret shown once, audited) | Julia v2 |
| Agent lifecycle: `DELETE /api/studio/agents/{key}` (platform admin or a content token minted with `permitir_exclusao`; refused 409 while published / with instances / with conversations / with an active channel / on; the audit log survives with a tombstone) and `POST /api/studio/plataforma/agents` creating an EMPTY platform definition; MCP actions `criar_agente` / `excluir_agente` | Agent lifecycle |
| Agent lifecycle UI: platform admins create an agent with the new-agent wizard (`/agentes/novo`: an empty shell that grows over time, or an AI-generated first draft; only publish is gated) and delete one from the `/agentes` listing with a type-the-key confirmation (409 reasons: published, instances, conversations, channel, active); the content token can opt in to `studio:agent-delete` so the MCP chat drives the same routes | Julia v2 |
| Julia public-line guardrails (migration 044, `projects/julia-v2/GUARDRAILS.md`): reply filters that block by default (`link_nao_permitido`, `contato_nao_permitido`, `pii_na_resposta`, `formato_suspeito`, `padroes_proibidos` with patterns as rule data; org specs `dominios_permitidos`/`contatos_oficiais`/`cnpj_oficial`), prompt-leak scan of staff-facing tool args, identity-claim signal, `escala_seguranca` (restricted tool set, then handoff `seguranca`); a claim never adds a capability | Julia v2 |
| Julia identity at rest (B8.4): after `registrar_identificacao` stores a CPF/RG the turn masks exactly that value (`***`) in the thread's `texto`/`blocks`/`meta` (incl. media `texto_extraido`); the thread's realtime scope is purged of the events carrying it (`redact_values`, a reconnecting client never replays it); failure = logged by type + `identificacao:redacao_falhou` event, reply unaffected; turn response flag `identificacao_registrada` (optional, default false) | Julia v2 |
| Julia provenance + leak tripwires (migration 046, `projects/julia-v2/GUARDRAILS.md` B2/B7): non-lead history (human, agent, event) reaches the model as `system` JSON envelopes keyed `plataforma_<tag>` (random per turn; a lead echoing a tag is the `forja_proveniencia` signal), lead text is always one plain `user` message; inbound `midia` (`tipo`, `texto_extraido` ≤2000, `legenda?`) and `truncado` render as labelled literals; `autor` only on the staff append route with `role: "humano"` (the lead turn route rejects it, 422); correction `evento` rows hold a code only (`conformidade:<regra>`, old rows redacted); inbound canary / prompt-shingle hit = `canario_recebido` (high, platform admins notified); a per-version honeytoken (`agent_version_marcadores`, DB-only) in a reply blocks as `vazamento_prompt`. New required texts: `historico.rotulo_midia`, `historico.rotulo_truncado`, `contexto.titulo_proveniencia`, `contexto.aviso_proveniencia`, `seguranca.marcador_interno` | Julia v2 |
| Julia consumer + Studio support: ordered stage list for consumers, pinned qualification standard per version, tiered capabilities catalog (`/api/agents/catalogo`), server-provided Studio tiers, conformance routes (incl. the rule list, MCP kind `conformidade_regras`), atomic draft lock (`expected_hash`, also on the draft-skill PATCH, migration 041), a content hash that covers the version's own skill bodies, async mechanism-eval runs | Julia v2 |
| Julia property search against SW's v2 contract: must-haves sent as `itens_essenciais`, SW's `relaxado` / `similar_a_encontrado` / `itens_nao_verificaveis` passed to the model; skill texts take `{{org.*}}` placeholders resolved per org | Julia v2 |
| Every agent in the same house (`projects/agents-unified/CONTRACT.md`): one listing `/agentes` (`GET /api/agents/painel`, one card per agent: papel, origin, state, capabilities) and ONE page `/agentes/:key` whose sections come from the server (`GET /api/agents/{key}/painel` — the sections this caller may open, from origin + tier) titled by the agent model (`GET /api/studio/modelo`: page sections, the 7 content areas with fields, the 10 wizard steps — derived from code, never duplicated); internals (`/painel/interno`, the areas, the wizard) 404 to anyone but a platform superadmin (D31); old shells (`/bia`, `/studio`, `/studio/:key`, `/agentes/catalogo`, `/agentes/:key/persona`) redirect; persona at `/api/agents/{key}/persona`; legacy chat found by data (`definition_mode='legacy'` + `claude_sdk`), not by key | agents-unified |
| New-agent wizard (`/agentes/novo`, platform admins; everyone else gets the standard not-found): the seed `JourneyWizard` over `GET /api/studio/modelo` → `assistente.passos` (steps and fields from the model, limits/defaults per field), start empty or "Gerar com IA" (AI draft capped at US$ 5), local unsaved draft, "Revisão" summary, "Publicar" → `POST /api/studio/plataforma/agents` → `/agentes/:key`; the former `/studio` console (create, import, delete, content token) folded into `/agentes` | agents-unified |
| Shared skill library: one standardised, versioned set of skills every agent opens the same way; agent versions pin library versions (`obrigatoria_para` gates tools), Studio shows "new version available"; platform-only authoring in the Studio Skills library page (`/studio/biblioteca-skills`: create, edit the draft body and reference files, publish) and the `noctus.agents.content` MCP tool (drafts only) | Julia v2 |

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
