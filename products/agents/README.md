# Agentes

Home of the NoctusAI managed AI agents. An agent here works **on** other products
through their scoped APIs — never through their databases.

- **Bia** — Claude Agent SDK (headless), reachable from this app's UI only. She helps
  run the Academia de Reciclagem project: reads its knowledge base and proposes writes,
  which you approve or deny before anything lands.
- **Julia** — the SDR agent, hosted here and consumed by `social-wiring` via API; she is the
  WhatsApp line (legacy name "One Chat", the separate operator bot retired 2026-11-04).

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
text lives in code (keeper `check_agent_prompt_text_in_code`). Org specs are untrusted data: typed, validated
(`SPEC_VALIDATION_MODE=report|block`) and fenced in the compiled prompt (`projects/julia-v2/CONTRACT.md` §2.6). Design: `projects/julia-v2/CONTRACT.md` §2.6.
No agent KEY lives in code either (migration 049): a platform definition is any `plataforma` row, created
with any key by `POST /api/studio/plataforma/agents` and configured by `GET/PATCH
/api/studio/plataforma/agents/{key}` — `escopo_qualificacao`, `padrao_qualificacao`, `rascunho_padrao`
(first-draft settings), `instanciavel` (published ⇒ instantiated in every org; DEFAULT false, never true for an `owner_product` definition — a closed one reaches only orgs granted via `definition_org_grants` / `noctus.agents.content action=conceder`; KB § PATTERNS/compliance/org-config-isolation.md), `papel`
(`gerador`) and `exemplar` (migration 058: the AI generator may imitate this definition; toggled ONLY by a platform-admin session via `PUT /api/studio/plataforma/agentes/{key}/exemplar`). `usa_canais` (derived: `owner_product` set and `runtime='llm'`) gates channel UI.
The only key literal left is the `lead-imob`→`julia` token alias (`app/channels/chaves_legadas.py`,
`NOC-REMEDIATE[drop-lead-imob-alias]`).

**Readiness actions**: every fixable item of `GET .../prontidao` renders a button in the studio's "Prontidão para publicar" panel (Rodar suíte de mecanismo, Rodar avaliação completa, Ligar agente, Atualizar skills); runs are polled to completion and the checklist is then refetched. Several runs of one version may execute at once, in both suites (migration 071); each has its own id, results and cost cap, and the panel follows the newest run it started. Every Studio 409 reads pt-BR text per `code` (`app/stores/_db_errors.py` `MENSAGENS_CONFLITO`), never the database's own message. `acao_sugerida` is human copy, never an API path.

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
| Agent list with on/off — Bia and Julia | M4, M5 |
| Isolation suite (no platform secrets in Bia's env; cross-product token denials) | M4 |
| Julia (SDR) shared lead thread: one thread per lead across all agents, per-agent participants, hand-off notes, consent (opt-in / opt-out, with an auditable event + an in-app notice to the org's owners/admins when a lead asks to stop; the opt-out is a per-org setting owned by social-wiring, which reads the history, re-sends failed notices and reactivates a lead over token routes; a thread banner in the staff view), delete-by-lead | Julia v2 |
| Julia controls: ligado / drenando / desligado per agent (decided by the agents app on every turn, fail closed) and a per-conversation pause / resume | Julia v2 |
| Julia v3 controls: a **platform kill** per agent key (`GET|PUT /api/studio/plataforma/agentes/{key}/controle`, platform admin only; status `agente_desligado_plataforma` for every org, read first, fail closed) | Julia v3 |
| Julia v3 **evaluation mode** (`modo_avaliacao` + `avaliacao_usuarios`, per org instance, on the controle PUT / GET): while on the agent replies only to the phones of the listed noc users (read from noc per turn, never stored here); anyone else (or a contact without a phone) gets status `restrito_avaliacao` with no reply and no new thread; off = open to everybody | Julia v3 | **One testing switch on Julia's core, obeyed by every company instance (owner 2026-11-05; migration 065):** the state lives ONLY on the core (`definition_scope='plataforma'` row; an instance reaches it via `definition_agent_id`); an instance's own `modo_avaliacao`/`avaliacao_usuarios` columns are dead (`NOC-REMEDIATE[drop-instance-modo-avaliacao]`). `SupabaseAgentControleStore.get` returns the core's state (`avaliacao_herdada=True`, `avaliacao_org_id`=core org, where the NoctusAI evaluators' phones are resolved); an unresolvable core raises `NucleoIndisponivel` ⇒ 503 `controle_indisponivel`. Only a NoctusAI platform admin writes it, on the core page (instance PUT ⇒ 409 `avaliacao_somente_no_nucleo`; `set_agent_avaliacao` refuses instances). A blocked (`restrito_avaliacao`) message is never persisted. The instance view shows a read-only "Julia em modo de avaliação" badge.
| Agent turn metrics (migration 066, `agents.turn_metrics`; CONTRACT §14) | Platform admins only, agents app only | One row per turn written at its end by `turno.executar` (fire-and-forget safe, failure logged): cost/tokens summed from the turn's priced D25 events (`coletar_uso`, never re-priced), speed (turn/LLM/tool ms), size (UTF-8 payload bytes; no media). `origem` canal vs eval. Read: `GET /api/studio/agents/{key}/metricas`, `.../metricas/turnos`, `.../metricas/threads[/{id}]` (`require_platform_admin`). Types: `frontend/src/api/studio/types-metricas.ts`. UI: the "Métricas" section of the agent page (`?tab=metricas`, `MetricasTab`; period/origem/org filters, KPI tiles, daily charts, per-version/org/thread tables, paginated turns, thread drill-down). |
| Julia channel turn v2 (`POST /api/channels/turns`): resolves the platform definition + the org's specs, applies the controls under the turn lock, reads the dossier + thread context, runs a skill-gated toolset (schemas in code, descriptions in `agent_version_ferramentas`), stamps every reply with the version tuple; JSON Schema in `backend/contracts/channels.v2.json` | Julia v2 |
| Studio UI (tier-aware by the server's `definition_scope`): platform admins edit the definition (prompt sections, system texts, tool descriptions, decisions, the qualification standard, library skill pins, declared specs, conformance) and read the compiled view; org admins see only their specs form, controls (ligado / drenando / desligado with a confirmation dialog), conversations and results; members see none | Julia v2 |
| Julia conformance + IP protection: post-turn detectors (offered-property, ends-with-question, profile-cited-without-record, fallback, repeated-question) and the prompt-leak detector (per-org canary + 12-token shingles; blocks by default, also on the studio test chat and eval outputs for non-platform-admins); per-chat turn/day/spend limits and refusal/error budgets, all data (`conformidade_*`, `canal_limites`) | Julia v2 |
| Julia mechanism evals: scripted multi-turn cases with deterministic asserts, pass^k, cost cap; a green LIVE run for the current compiled hash gates publish (router + DB); synthetic fixtures only (PII-guarded), `fixture.origem` makes a case an ad lead (campaign code on the SW state), identity scripted with `[[cpf_sintetico_valido]]` / `[[email_sintetico]]` tokens generated per execution; cases writable by the `noctus.agents.content` MCP tool (kind `evals_mecanismo`) | Julia v2 |
| Eval-loop gate (migration 076, G1-G7; `docs/eval-loop-gate-contract.md`): a refinement LOOP of one suite (`comportamento` or `mecanismo`) declares planned rounds, target 100%, floor = `publicacao_limiar` and a budget (default US$ 20); runs started with `loop_id` are its rounds. At each round end the gate stops the loop at 100%, after 2 consecutive rounds without a score improvement, or at the budget, flags every non-improving round as an overcall with its cost, refuses a re-run on an unchanged hash beyond the consolidation passes (409 `hash_inalterado`) and notifies the platform admins in-app mid-flight (score series, what changed, failing cases). `POST/GET .../evals/loops`, `GET .../evals/loops/{id}`, `POST .../evals/loops/{id}/stop`; platform admin or the `studio:evals-run` token | Eval loops Owner kinds `eval_loop_parada` / `eval_loop_checkpoint` (whatsapp + in_app) are declared in `app/notification_kinds.py`; the pt-BR WhatsApp texts are built by `app/studio/eval_loop_whatsapp.py`; the send is a seam (`NOC-REMEDIATE[eval-loop-owner-whatsapp]`) until `notify_owner` is wired, the in-app bell is unchanged. |
| Content-token UI: platform admins mint / list / revoke the `noctus.agents.content` MCP token from the `/agentes` listing (expiry in days 1..365 or never, secret shown once, audited) | Julia v2 |
| Agent lifecycle: `DELETE /api/studio/agents/{key}` (platform admin or a content token minted with `permitir_exclusao`; refused 409 while published / with instances / with conversations / with an active channel / on; the audit log survives with a tombstone) and `POST /api/studio/plataforma/agents` creating an EMPTY platform definition (an existing key is 409 `agente_ja_existe` unless `reutilizar: true`, which the MCP `criar_agente` sends to stay idempotent); MCP actions `criar_agente` / `excluir_agente` | Agent lifecycle |
| Agent lifecycle UI: platform admins create an agent with the new-agent wizard (`/agentes/novo`: an empty shell that grows over time, or an AI-generated first draft; only publish is gated) and delete one from the `/agentes` listing with a type-the-key confirmation (409 reasons: published, instances, conversations, channel, active); the content token can opt in to `studio:agent-delete` so the MCP chat drives the same routes | Julia v2 |
| Julia public-line guardrails (migration 044, `projects/julia-v2/GUARDRAILS.md`): reply filters that block by default (`link_nao_permitido`, `contato_nao_permitido`, `pii_na_resposta`, `formato_suspeito`, `padroes_proibidos` with patterns as rule data; org specs `dominios_permitidos`/`contatos_oficiais`/`cnpj_oficial`), prompt-leak scan of staff-facing tool args, identity-claim signal, `escala_seguranca` (restricted tool set, then handoff `seguranca`); a claim never adds a capability. The product-generic detectors (leak canary + shingle fingerprint, link/contact/PII/format/pattern filters, the de-obfuscating skeleton, tool-result redaction, answer bounds) live in the seed organ `noctusai_lib.integrations.llm.guardrails` (`OutputGuard` Fake+Real+factory); `channels/conformidade.py` keeps the agent-specific rules and the policy, `public_ask/postfilter.py` consumes the bounds | Julia v2 |
| Julia identity at rest (B8.4): after `registrar_identificacao` stores a CPF/RG the turn masks exactly that value (`***`) in the thread's `texto`/`blocks`/`meta` (incl. media `texto_extraido`); the thread's realtime scope is purged of the events carrying it (`redact_values`, a reconnecting client never replays it); failure = logged by type + `identificacao:redacao_falhou` event, reply unaffected; turn response flag `identificacao_registrada` (optional, default false) | Julia v2 |
| Emergency inactivity close (migration 079): `sinalizar_alerta tipo=emergencia` (the alert row is the recorded marking) sets `thread_participantes.fecha_inativo_min=10`; the deadline is `conversations.last_message_at` + window (lead, agent reply and human messages all refresh it); the `agents_thread_inatividade` job (every minute) closes via the atomic `transicionar` (motivo `inatividade`, one participant event, replica-safe); `encerrar` answers `emergencia_aberta` while a window is open (the lead's own stop request is exempt); `NOC-REMEDIATE[inatividade-por-agente]` = per-agent window. | Julia v3 |
| Julia go-live hardening (migration 063, `projects/julia-v2/GUARDRAILS.md` B12): pattern-rule floor in code under the DB rows (`PADROES_PROIBIDOS_PISO`; readiness `regras_seguranca_sem_parametros` blocks), allowlists from validated org specs only (report mode never trusts a failing value), one inbound normalizer (`studio/normalizador_texto.py`: invisible/tag characters stripped, de-obfuscated skeleton for the detectors), detector `valor_sem_ferramenta` (R$/% no tool backs), detector `transferencia_sem_handoff` (a reply promising a transfer to a person in a turn with no `handoff` call; blocks by default, code-side patterns, no row; a promise of contact is also backed by a visit intention / `concluir_qualificacao` in the turn; required text `conformidade.correcao.transferencia_sem_handoff`), detector `insatisfacao_sem_alerta` (the lead's message complains about the service and no `sinalizar_alerta` call succeeded; blocks by default, code-side patterns, never on a stop request / hand-off / `encerrar`; required text `conformidade.correcao.insatisfacao_sem_alerta`), deterministic STOP (`opt_out_palavras`, no model; honoured in every conversation state, also on a paused / handed-over / off / killed / draining thread), regua text validated, `encaminhada` flag on inbound messages. New texts: `conformidade.correcao.valor_sem_ferramenta`, `runtime.confirmacao_opt_out` (required), `historico.rotulo_encaminhada` (optional) | Julia v2 |
| Julia provenance + leak tripwires (the leak fingerprint skips the prompt's quoted example speech and the correction texts, JL-028; migration 046, `projects/julia-v2/GUARDRAILS.md` B2/B7): non-lead history (human, agent, event) reaches the model as `system` JSON envelopes keyed `plataforma_<tag>` (random per turn; a lead echoing a tag is the `forja_proveniencia` signal), lead text is always one plain `user` message; inbound `midia` (`tipo`, `texto_extraido` ≤2000, `legenda?`) and `truncado` render as labelled literals; `autor` only on the staff append route with `role: "humano"` (the lead turn route rejects it, 422); correction `evento` rows hold a code only (`conformidade:<regra>`, old rows redacted); inbound canary / prompt-shingle hit = `canario_recebido` (high, platform admins notified); a per-version honeytoken (`agent_version_marcadores`, DB-only) in a reply blocks as `vazamento_prompt`. New required texts: `historico.rotulo_midia`, `historico.rotulo_truncado`, `contexto.titulo_proveniencia`, `contexto.aviso_proveniencia`, `seguranca.marcador_interno` | Julia v2 |
| Julia history window: the labelled thread history the model reads (last `llm_history_messages`, default 40) is fitted to `llm_history_max_tokens` (default 40000, estimated) by the server (`app.channels.turno.ajustar_janela_historico` over the seed's `integrations/llm/context_window.fit_history`): over budget, the OLDEST turns are dropped (pure trimming, no model call; latest turn always kept); a history that fits is sent byte-identical | Julia v2 |
| Julia consumer + Studio support: ordered stage list for consumers, pinned qualification standard per version, tiered capabilities catalog (`/api/agents/catalogo`), server-provided Studio tiers, conformance routes (incl. the rule list, MCP kind `conformidade_regras`), atomic draft lock (`expected_hash`, also on the draft-skill PATCH, migration 041), a content hash that covers the version's own skill bodies, async mechanism-eval runs | Julia v2 |
| Prompt-exposure closure (security audit, 2026-11): the definition, eval and knowledge tables (`compiled_prompts`, `agent_prompt_sections`, `agent_skills*`, `agent_version*`, `skills_biblioteca`, `skill_versao*`, `eval_*`, `knowledge_*`, `agent_audit_log`, ...) are service-role only -- migration 036 revokes every `anon`/`authenticated` privilege and drops the browser policies, later tables are private by default; the replay test `mcp/noctusai/tests/test_agents_browser_lockdown_probes_on_replay.py` proves a SELECT as `authenticated`/`anon` is refused on each after the whole chain. Streamed `message.delta` events of a guarded turn (non-admin studio test chat) are released only behind the leak guard (`FiltroDeltas`: accumulated text is checked every delta, the last `2 x SHINGLE_TOKENS` words are held back, a leaking message releases nothing more). `GET /api/studio/agents/{key}/evals/runs[/{id}]` need a platform admin (strict 403 `platform_admin_required` for any org member) or a `studio:publish` token on a dev-advisor agent | Julia v2 |
| Julia property search against SW's v2 contract: must-haves sent as `itens_essenciais`, SW's `relaxado` / `similar_a_encontrado` / `itens_nao_verificaveis` passed to the model; skill texts take `{{org.*}}` placeholders resolved per org | Julia v2 |
| Every agent in the same house (`projects/agents-unified/CONTRACT.md`): one listing `/agentes` (`GET /api/agents/painel`, one card per agent: papel, origin, state, capabilities) and ONE page `/agentes/:key` whose sections come from the server (`GET /api/agents/{key}/painel` — the sections this caller may open, from origin + tier) titled by the agent model (`GET /api/studio/modelo`: page sections, the 7 content areas with fields, the 10 wizard steps — derived from code, never duplicated); internals (`/painel/interno`, the areas, the wizard) 404 to anyone but a platform superadmin (D31); old shells (`/bia`, `/studio`, `/studio/:key`, `/agentes/catalogo`, `/agentes/:key/persona`) redirect; persona at `/api/agents/{key}/persona`; legacy chat found by data (`definition_mode='legacy'` + `claude_sdk`), not by key | agents-unified |
| Renata cutover (migration 053, `projects/agents-unified/RENATA-CUTOVER.md`): the academia toolset as a content-configurable tool group (`ferramentas` rows `academia_*`, `claude_sdk` only, writes always through the approval broker, never on a channel turn); org instances of a platform definition chat in-app; superadmin-only `POST /api/agents/{source_key}/transferir-historico` (one transaction, audited, idempotent, dry run by default, re-points the academia principal) and `POST /api/agents/{key}/arquivar` (`definition_mode='arquivado'`, frees the key); `GET /api/agents/painel/destino-chat` drives the `/bia` redirects; neutral runtime names (`ACADEMIA_AGENT_ID`, `CLAUDE_CLI_PATH`, `CLAUDE_CLI_SLOTS`, `LEGACY_CHAT_MAX_TURNS`; old `BIA_*` names still read with a deprecation log) | agents-unified |
| New-agent wizard (`/agentes/novo`, platform admins; everyone else gets the standard not-found): the seed `JourneyWizard` over `GET /api/studio/modelo` → `assistente.passos` (steps and fields from the model, limits/defaults per field), start empty or "Gerar com IA" (AI draft capped at US$ 5), local unsaved draft, "Revisão" summary, "Publicar" → `POST /api/studio/plataforma/agents` → `/agentes/:key`; the former `/studio` console (create, import, delete, content token) folded into `/agentes` | agents-unified |
| Publish from any content tab: the draft header of Prompt, Textos, Ferramentas, Decisões, Especificações and Skills fixadas carries "Publicar rascunho" (admin only), opening the shared `PublishDraftDialog` that Versões uses (blocking warnings + eval gate); disabled while the tab has unsaved edits. Decisions are rows of the draft version — there is no per-decision publish | Julia v2 |
| Shared skill library: one standardised, versioned set of skills every agent opens the same way; agent versions pin library versions (`obrigatoria_para` gates tools), Studio shows "new version available"; platform-only authoring in the Studio Skills library page (`/studio/biblioteca-skills`: create, edit the draft body and reference files, publish) and the `noctus.agents.content` MCP tool (drafts only) | Julia v2 |

## Platform grants (agent -> product wiring, `app/grants/`)

Nobody pastes a token. A **platform admin** (`require_platform_admin`) picks agent + product + org and agents mints and
DELIVERS the credential (Julia-line CONTRACT D1-D4; migration 060 `agents.agent_product_grants`, one live grant per
(org, agent, product)). The product registry is server-side (`app/grants/registry.py`: only `social-wiring` + `julia`
today) and so is the strict scope allow-list the grant token admin mints from.

| Route | Does |
|---|---|
| `GET /api/studio/plataforma/grants` | every grant `{items, total}` (ids, status `pendente\|ativo\|revogado\|falhou`, `last_error`; never a secret) |
| `GET /api/studio/plataforma/grants/opcoes?q=&limit=` | the pickers: `{produtos:[{slug,label,agent_keys}], orgs:[{id,nome,slug}]}` |
| `POST /api/studio/plataforma/grants {agent_key, product, org_id, expira_em_dias?}` | create = mint + deliver (201 grant; no expiry unless asked; 409 `grant_exists`; 502 `mint_failed` / `tools_store_failed` / `delivery_failed`) |
| `POST /api/studio/plataforma/grants/{id}/rotate` | overlapping rotation: new pair delivered first, then the old pair revoked |
| `DELETE /api/studio/plataforma/grants/{id}` | revoke both tokens + best-effort `DELETE` at the product (204, idempotent) |
| `GET /api/studio/plataforma/agents/{key}/products/{product}/orgs` | staff picker: orgs with a LIVE grant + status/`editavel` (platform admin) |
| `GET\|PUT /api/studio/plataforma/agents/{key}/products/{product}/orgs/{org_id}/specs` | NoctusAI staff fill that org's agent specs; needs the admin login AND a grant `ativo`+unexpired for exactly (org, key, product) with `especificacoes_editor='plataforma'` (migration 064; else 409 `sem_concessao_ativa` / `editor_nao_plataforma`); audit = the real admin |

**Org business specs (Julia-line S9).** `GET|PUT /api/channels/agents/{key}/specs` (`routers/channel_specs_router.py`) is what
social-wiring's editor calls with the granted channel token (scope `agents:channel-specs`, bound to the org instance; the org
is the token's). It runs the studio PUT's own code (`aplicar_org_specs` / `ler_org_specs`): declared keys only,
`especificacoes_service.validar`, the PUT's required, product-attested `ator {user_id, nome?, email?}` (422 `ator_obrigatorio`; stored as `updated_by*`, migration 062), 200 + `invalidas` in report mode, 422 + `violacoes` in block mode, 422 `spec_nao_declarada`.

Create: (1) channel token in `agents.api_tokens` for the TARGET org (issuer = the transport `social-wiring`, scopes
`agents:channel-turn|channel-status|channel-specs`, bound to the org's instance via `ensure_instancia`); (2) tools token
in the product's `api_tokens` (issuer `agents`, `social-wiring:lais-tools`), its secret kept in agents' per-org encrypted
store; (3) a 5-minute one-shot delivery token (`platform:grant-receive`); (4) the seed `GrantDelivery` PUTs the channel
credential to `{product}/api/platform/grants/agents`; (5) the delivery token is revoked. Any failure revokes every token
of that attempt, restores the stored tools secret, marks the grant `falhou` with `last_error` (stage + error class, no
secrets). MFA is not required to mint (seed `MintPolicy` default); secrets are shown to nobody and never logged.
The former `PUT /api/channels/ferramentas-token` paste intake is retired (it is gone, 404); `DELETE` stays. The human
`POST|DELETE /api/agents/{key}/channel-token` mint/revoke routes are deleted (Julia-line S5): a channel token exists only
through a grant. The channel-token AUTH dependency (turns / status / specs) is unchanged. Responses carry `token_prefix`
(the stored `noc_ab12`-style prefix, from `agents.api_tokens.token_prefix`); agents keeps only the hash, so the prefix is
the whole display. The UI is `/conexoes-plataforma` ("Conexões da plataforma", platform
admin only, nav item + `status_pagina` row `conexoes-plataforma`, migration 061): pick agente → produto → organização →
confirmar; the list shows status, the stored credential prefix (`noc_ab12…`), expiry, last delivery and last error; rotate and
revoke ask for confirmation. The Canais tab of an agent lists that agent's non-revoked connections inline (produto · organização,
status, credential prefix, last delivery; no agent name — the page is the agent) and links there to manage them; a
non platform admin (403) sees only the hint. Status badges: `GRANT_STATUS_BADGE` in `hooks/useGrants.ts`, shared by both.

Platform AI calls UI: `/agentes-plataforma` ("Agentes da plataforma", group Plataforma, platform admin only, `status_pagina` row `agentes-plataforma`, migration 069; `pages/AgentesPlataforma.tsx`, `hooks/usePlataformaAgentes.ts`): pick a call, choose Fornecedor + Modelo (filtered by vendor/capacidade) and edit ONE whole-prompt field; unsaved-draft guard, Descartar alterações, 422 `modelo_invalido` inline.

## DB-source dev agents (Agent Packages A11/A12, migration 070)

A dev agent can be authored in the Studio instead of git: `agents.fonte = 'db'` (immutable) makes the DB the source of
truth, and git holds only a GENERATED mirror (`.claude/agents/<key>.md` + `agents/<key>/`) exported from the published
version (`products/agents/projects/agent-packages/CONTRACT.md` §M). `agents.kind` adds `dev-executor` (may carry
write tools; `dev-advisor` stays read-only, A10). `agents.superficie_claude = {tools, model, owns_kb}` is the
Claude Code surface, set at `POST /plataforma/agents` (or MCP `criar_agente`) and changed through the definition
PATCH (`configurar_agente`). Every agent creation surface (store create, insert payload, row mapping,
request/response models, route forwarding, MCP keys) is declared in `app/stores/structure_parity.py` and held by
keeper `check_structure_constructor_parity` (`KB § PATTERNS/backend/structure-constructor-parity.md`): a new
field on `StudioAgentRecord` must reach each of them or be exempted with a reason.

At publish, a DB-source dev agent's mirror is rendered from the draft by `app/studio/espelho.py` (via the ONE
Claude Code renderer `app/studio/claude_surface.py`, shared with the git package build) and stored on the version
before the flip; no mirror means no publish (409 `espelho_falhou`). `versao_semver` = `<versao>.0.0`.

## Agent layers (BASE → SDR → agent; roadmap `agent-templates-2026-11`)

`app/studio/camadas.py`: a child agent's version holds only its OWN rows; the compiler, the runtime turn, the eval driver and readiness read the EFFECTIVE rows (`EfetivoStore`), the parent chain merged in per piece by key. Prose section with the same key: the child APPENDS (parent title, order and active flag kept). Single values (text, tool row, decision, org-spec declaration, own skill): the child REPLACES, reported as an override. Files follow their skill. Editors keep reading own rows. A cycle or a chain deeper than 4 is refused (`EfetivoStore.cadeia` lists root → self). Migration 073: `agents.modelo` (a template: platform-owned, never instanciavel nor channel-owned) and `agents.pai_agent_id` (parent must be a template of the same org, no cycle; trigger `guard_agent_camada`, 409 `pai_invalido`); `agent_versions.pai_versao_id` is written only by publish. A child's DRAFT reads its parent's draft (else its active version) live; its PUBLISH pins the parent's current active version: the router recompiles the child against that version and refuses `pai_desatualizado` (409) when the hash differs from the evaluated one, `pai_nao_publicado` when the parent has none. A version published before its agent had a parent stays exactly as it was. Setting a layer: `POST /plataforma/agents` and `PATCH /plataforma/agents/{key}` (and `noctus.agents.content` `criar_agente` / `configurar_agente`) carry `modelo` + `pai_agent_id`, and the response shows them; at create the layer is validated BEFORE the row exists (`validar_camada_nova`), so a refused parent leaves no un-layered definition, then applied via `update_definicao` (as `superficie_claude`).

**Section rules (migration 078).** A prompt section declares the rules its text carries in `agent_prompt_sections.regras` (closed list in `app/studio/regras_secao.py`, today `discordar-com-respeito`; unknown rule = 422 in pt-BR). Readiness (`sem_secao_discordar`) checks that an ACTIVE, non-blank section of the agent's EFFECTIVE sections declares the rule, never a section key (the canonical template keeps it inside `honestidade`); a child section appended onto a parent's keeps the parent's rules and gains its own. The generator's `SecaoGerada`, bundles, copy-draft and the Studio editor (read-only chips) carry the rules.

**Hand-off fallback number (migration 074).** When an agent hands a conversation to a person, the team is notified at `numero_fallback_atendimento`: ONE E.164 number for every org for now (owner 2026-11-09; per-org later), a platform runtime setting on the admin page "Configurações do agente" (`PUT /api/admin/agent-settings`, normalized by `noctusai_lib.primitives.phone`, DB CHECK backstop). Unset ⇒ readiness item `numero_fallback_ausente` (bloqueante) and publish 409 `numero_fallback_ausente` for every conversational agent (`prontidao.falta_numero_fallback`; the internal generator is exempt).

## Creating a complete agent (Julia as the reference)

`KNOWLEDGE-BASE/CONTEXT/GUIDES/agent-creation.md` (skill `noc-new-agent`) is the recipe: the artifacts a production agent has and
where Julia's live, the step order (`criar_agente` → `gerar` with `referencia=<exemplar>` → read the `lacunas` → standard → specs →
evals → readiness → eval run → **human** publish), the gate table, the generator's cost cap and what never comes from AI.

| Surface | What |
|---|---|
| `GET /api/studio/agents/{key}/prontidao` (platform admin or content token; `app/studio/prontidao.py`) | What the DRAFT still owes: items `{codigo, grupo, severidade bloqueante\|aviso\|ok, mensagem, acao_sugerida, recusa_publicacao, detalhe}` + `pronto_para_publicar` (true iff publish would not refuse it — blocking items name the publish 409 code they stand for; a parity test keeps gate and view in lock-step). The same list rides in every publish 409 (`prontidao`) |
| `POST /api/studio/agents/{key}/geracoes {briefing, areas?, forcar?, limite_usd?, referencia?}` | AI first draft; new area `evals` (behaviour eval cases, PII-guarded, drafts only); `referencia` = an exemplar agent key (422 `referencia_invalida`), else every exemplar. The reference's tool parameter labels, decision options, eval-case shapes and standard key reach the generator (verbatim text only inside the platform org; leak guard on) |
| `PUT /api/studio/plataforma/agentes/{key}/exemplar {exemplar}` | Mark/unmark an exemplar — platform ADMIN session only (not the content token, not PATCH) |
| `POST /api/studio/agents/{key}/draft/skills-biblioteca/atualizar` | Explicit re-pin of EVERY pinned library skill to its newest published version; returns the diff; audited; re-stamps the draft hash |
| MCP `noctus.agents.content action=prontidao \| atualizar_skills` | The read and the (dry-run-first) re-pin from the chat |

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
  (factor after N days without a lead reply). `parametros.lote_ofertas` (properties per offer run) defaults to **3**
  by the owner's rule (at most 3 per run, then Julia asks whether the lead wants more; migration 055 default, 1..5,
  shown in the Studio editor).
  Follow-up cap (owner 2026-11-10): `parametros.max_retomadas_seguidas` (default **2**, 0..10, migration 080) is the most
  follow-ups (`gatilho:"reengajamento"`) in a row with no reply from the lead; `controles.decidir` refuses one more with
  status `limite_retomadas` (no model call, nothing stored; opt-out is decided first), every outcome is one append-only
  `thread_retomada_eventos` row, and social-wiring ends that contact's sequence.
- **Timestamps** read back from the DB go through `app.stores._util.db_ts` (PostgREST returns ISO strings,
  the Fakes hold `datetime`); a mapper that passes the string through 500s the first `.isoformat()`.
- **Stages** are rules in a closed DSL (`todos/algum/nao`, `criterio`, `score` incl. `eixo`, `evento`,
  `contagem`, `identificacao: completa`); every node may carry an `id` (explainability: `regra_id` +
  per-axis `detalhe`). A `terminal` stage is only ever **suggested** (`descartado_sugerido`); a human
  confirms it (`POST /api/channels/leads/{ref}/descarte/confirmar`, actor stored) - LGPD art. 20.
- **Service** (`QualificacaoService`): `avaliar`, `registrar_perfil` (the `trecho` must be in the lead's own
  recent messages), `registrar_evento_imovel`, `pode_concluir`, `confirmar_terminal`, `apagar_por_lead`.
  Refusals are typed codes; their wording lives in DB texts. Correctable ones (skill not opened, no campaign code) do not spend `max_recusas_por_turno`; the rest do (`RECUSAS_CORRIGIVEIS` / `RECUSAS_CONTADAS`).
- **Lead identity** (`identificacao.py`): name/e-mail/CPF/RG apart from the records, CPF/RG Fernet-encrypted
  with the fleet `ENCRYPTION_KEY`, masked by default, clear text only for org owner/admin via an audited
  endpoint; 180-day retention and delete-by-lead cover it.

## Tests

```bash
cd products/agents/backend && pytest
cd products/agents/frontend && npx vite build
```


## Julia turn (2026-11-05 redesign)

A tool tied to a skill is auto-loaded for the turn (no `skill_nao_aberta` refusal); a procedural stop is a silent re-run, then fallback + operator alert, never a hand-off; the compiled prompt of a published version is cached per (version, specs, standard); judge cases run on the real channel path; the channel temperature is per version (default 0.3; inert on Anthropic models, whose API no longer accepts it). See `projects/julia-v2/DECISAO-SKILL-AUTOLOAD.md`.

Leak fingerprint: skill bodies/files handed to the model in a turn are added to the reply check (`conformidade.impressao_com`), and the check also reads the de-obfuscated reply.

**Personal tokens.** A grant is one (agent, product, org) with its own channel token; every `/api/channels/*` request also checks the token's grant is live and names this (org, agent) (403 `grant_inativo` / `agent_not_allowed`), so a revoked grant stops turns and edits at once and a token never reaches another agent.

> Eval loop (2026-11-08): the platform-issued `studio:evals-run` token (mint via `POST /api/studio/plataforma/content-token` with `tipo: "avaliacoes"`) starts, lists, reads and cancels eval runs of both suites (a token-started run is capped at the default cost, the default model, the current draft, and a fail-closed per-org 24h spend ceiling; `studio:evals-run` is never mintable through the generic token route); see MASTER-PROMPT.
