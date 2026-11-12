# Agentes — MASTER-PROMPT

> Authoritative development guide for the `agents` product.
> Plan and milestones: `project-history/roadmaps/julia-agents-academia-2026-09.md`.

## Purpose

Home of the NoctusAI managed AI agents. An agent works **on** another product through that
product's scoped API and never touches its database. Two agents in this release:

- **The academia agent** runs here, on the Claude Agent SDK in headless mode, reachable only
  from this app's UI. It helps with the Academia de Reciclagem project by reading the
  `academia-de-reciclagem` API and proposing writes to it; a person approves or denies every
  write before it happens. Until the Renata cutover it was the code-defined **Bia**
  (`app/agents/bia/`); since then it is a Studio agent (Renata) whose version switches on the
  `academia_*` tool group (`app/studio/ferramentas_registry.py`), and the key `bia` is free.
  Runbook: `projects/agents-unified/RENATA-CUTOVER.md`.
- **Julia** (SDR) is hosted here and consumed by `social-wiring` via API; she is the WhatsApp line
  (legacy name "One Chat", retired as a separate operator bot 2026-11-04).

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
- Julia v3 controls (migration 056): `stores/plataforma_controles.py` (`agents.plataforma_controles`, service-role only,
  one row per agent key) is the PLATFORM kill, toggled by `GET|PUT /api/studio/plataforma/agentes/{key}/controle`
  (`routers/plataforma_controle_router.py`, `require_platform_admin`, audited `plataforma_desligada|religada`).
  `decidir(..., desligado_plataforma=)` reads it FIRST: `True` -> status `agente_desligado_plataforma` for every
  trigger and org (inbound stored only for an existing thread; the turn route skips key/budget/LLM), `None`
  (unreadable) -> 503 `controle_indisponivel`. `GET /api/channels/agents/{key}/status` adds `desligado_plataforma`.
- Evaluation mode (migration 056, contract §12.12): `agents.agents.modo_avaliacao` + `avaliacao_usuarios` (noctus user ids,
  max 20; NO phones stored), written by `set_agent_avaliacao` (audit `modo_avaliacao_alterado`) through the org controle PUT
  (same `modo` ⇒ no mode preconditions; 422 `avaliacao_usuario_fora_da_org` / `avaliacao_sem_telefone`). Each user's phone is
  read from noc (`stores/usuarios_avaliacao.py`, `noctus_users.telefone`) per turn in `aplicar_controles`, never cached; an
  unresolvable phone ⇒ nobody allowed (fail closed, logged). `decidir(..., modo_avaliacao=, avaliacao_numeros=,
  telefone_e164=)`: after the kill and the mode (`desligado` keeps its status), a contact whose normalised
  `contact.phone_e164` is not among the resolved phones (or has none) ⇒ `restrito_avaliacao`, every trigger, no LLM,
  inbound stored only for an existing thread, never a new thread/participant. Unreadable flag ⇒ 503.
  `GET /api/channels/agents/{key}/status` carries `modo_avaliacao` only. The org controle GET/PUT add `avaliacao_resolvidos` (users from noc; full phone to org admins, masked to members) + `avaliacao_resolucao_erro` (lookup failed: null name/phone, never a 500).
  **One evaluation switch on Julia's core, obeyed by every company instance (owner 2026-11-05; migration 065):** the state lives ONLY on the core (`definition_scope='plataforma'` row; an instance reaches it via `definition_agent_id`); an instance's own `modo_avaliacao`/`avaliacao_usuarios` columns are dead (`NOC-REMEDIATE[drop-instance-modo-avaliacao]`). `SupabaseAgentControleStore.get` returns the core's state (`avaliacao_herdada=True`, `avaliacao_org_id`=core org, where the NoctusAI evaluators' phones are resolved); an unresolvable core raises `NucleoIndisponivel` ⇒ 503 `controle_indisponivel`. Only a NoctusAI platform admin writes it, on the core page (instance PUT ⇒ 409 `avaliacao_somente_no_nucleo`; `set_agent_avaliacao` refuses instances). A blocked (`restrito_avaliacao`) message is never persisted. The instance view shows a read-only "Julia em modo de avaliação" badge.

### Platform grants (Julia-line S3) — how a product gets its credential

- `app/grants/` (`registry.py` server-side product + scope registry, `store.py` ledger `agents.agent_product_grants` (060),
  `orgs.py`, `service.py`) behind `routers/plataforma_grants_router.py` (`/api/studio/plataforma/grants`, platform admin
  only). Create = mint the channel token (agents schema, target org) + the tools token (product schema, secret kept in the
  per-org encrypted store) + a 5-minute delivery token, `GrantDelivery.deliver`, revoke the delivery token; any failure
  revokes everything minted and leaves the grant `falhou`. Rotate overlaps; revoke kills both and tells the product.
  Nobody pastes a token: `PUT /api/channels/ferramentas-token` is gone. Never log or return a secret. README section
  "Platform grants" has the routes. UI: `/conexoes-plataforma` (`pages/ConexoesPlataforma.tsx`, `hooks/useGrants.ts`), platform
  admin only; the old channel-token paste card AND the human `POST|DELETE /api/agents/{key}/channel-token` routes are deleted; `ChannelsTab`
  lists the agent's own non-revoked grants (produto · org, status, prefix; 403 ⇒ hint only) and links to the page. Grant responses carry `token_prefix` (stored prefix only), never a secret.
  Platform AI calls UI: `/agentes-plataforma` ("Agentes da plataforma", group Plataforma, platform admin only, `status_pagina` row `agentes-plataforma`, migration 069; `pages/AgentesPlataforma.tsx`, `hooks/usePlataformaAgentes.ts`): pick a call, choose Fornecedor + Modelo (filtered by vendor/capacidade) and edit ONE whole-prompt field; unsaved-draft guard, Descartar alterações, 422 `modelo_invalido` inline.

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
  Refusals are two classes (`RECUSAS_CORRIGIVEIS` / `RECUSAS_CONTADAS`, fail-closed): a CORRECTABLE one (skill not opened,
  no campaign code, react before offered, unknown skill/file) is guidance and does NOT spend `max_recusas_por_turno` (the
  it also refunds the per-tool call count, the global `max_chamadas_ferramenta_turno` still bounds a loop); every other code counts. The refusal log line carries `classe=`.
  Past `max_recusas_por_turno` / `max_erros_ferramenta_por_turno` the toolset stops the turn (`should_stop`) and the turn
  ends in a hand-off to the org owner + a flagged event (silence, or the DB text `runtime.parada_segura`).
- Emergency (migration 079): `sinalizar_alerta tipo=emergencia` sets `thread_participantes.fecha_inativo_min=10`; the thread stays open, the `agents_thread_inatividade` job (every minute) closes the participant via `transicionar` (motivo `inatividade`) once `conversations.last_message_at` + window passed (every message, including the agent's reply, refreshes it); `encerrar` is refused with `emergencia_aberta` meanwhile (a lead's stop request is exempt).
- Julia v3 (CONTRACT §12): `sinalizar_alerta` (-> `agents.thread_alertas`, action `alerta`, one per tipo per turn),
  `registrar_documento` (an ID photo/scan -> flag on `lead_identificacao`, CPF satisfied pending extraction, action
  `documento_identificacao`; the id is checked against the inbound lead message, whose `provider_message_id` is stored
  in the row's `meta` at intake), the hand-off/conclusion `relatorio` (`channels/relatorio.py`: ONE `/resumo`-generator
  call through the `get_relatorio_resumo_factory_dep` seam + deterministic parts; a failure degrades to a
  deterministic text + a `relatorio:degradado` thread event, never blocking the hand-off; also stored in the hand-off
  note's `perfil.relatorio`), `qualificacao.imoveis_oferecidos`. Identification: required = `cpf` only
  (`obrigatorios_do_padrao`), desired = rg/email/nome (`avaliar_lead.identificacao_desejada`); `nome` is registrable at
  any point and overrides the contact's name in the report header. Migration 057.
- `channels/contexto.py`: the second system message (state + dossier + hand-off note + credit + re-engagement) rendered
  from DB texts; lead-influenced values are JSON literals on one line. `channels/extracao.py`: the summary (narrative
  only) and the transport decision (`agent_version_decisoes`; fallback = the row's `padrao` option).
- `channels/conformidade.py` + migration 037: detectors, the prompt-leak fingerprint (hashes only, computed at
  publish), policy per rule (`registrar` | `bloquear`; the leak rule blocks by default: suppress, ONE corrective re-run
  with the DB text, else silence + hand-off + a flagged row), the deterministic escalations (rule data), the
  extraction-attempt signal. Migration 037 also closes `qual-lead-ref-fk` (cascade erasure) and lets a hand-off end
  `concluido`.
- Public-line guardrails (migration 044; threat model + build order in `projects/julia-v2/GUARDRAILS.md`): reply
  filters `link_nao_permitido` / `contato_nao_permitido` / `pii_na_resposta` / `formato_suspeito` / `padroes_proibidos`
  block by default (patterns are rule data; allow-lists come from org specs `dominios_permitidos`, `contatos_oficiais`,
  `cnpj_oficial`); `proteger_args` scans the staff-facing tool args for prompt text; `alegacao_identidade` +
  extraction signals feed `escala_seguranca` (24h per thread: restricted tool set, then handoff `seguranca`).
  Invariant (keeper-tested): a detector or a claim can only REMOVE capabilities, never add one.
- Go-live hardening (migration 063; GUARDRAILS B12): the `padroes_proibidos` / `alegacao_identidade` patterns are a
  code-side floor (`stores/conformidade.py`) merged under the stored rows (a missing row still has it; readiness
  `regras_seguranca_sem_parametros` blocks publish); allowlists come from `ValoresOrg.limpos` (validated specs only);
  `studio/normalizador_texto.py` is the one invisible-character / de-obfuscation module (schema boundary + detectors +
  `spec_formatos`); `valor_sem_ferramenta` blocks an unbacked R$ / %; `transferencia_sem_handoff` blocks a reply that promises a transfer to a person ("vou te transferir", "um especialista vai falar com você") when the turn made no `handoff` call (a promise of contact such as "um corretor vai entrar em contato" is also backed by a successful `registrar_intencao_visita` / `concluir_qualificacao` in the turn; an offer such as "posso te transferir se quiser?" does not fire; blocks by default, one corrective re-run with `conformidade.correcao.transferencia_sem_handoff`); `insatisfacao_sem_alerta` blocks a turn where the lead's message complains about the service ("já te falei", "você não presta atenção") and no `sinalizar_alerta` call succeeded (never on a stop request, a hand-off turn or an `encerrar`; blocks by default, one corrective re-run with `conformidade.correcao.insatisfacao_sem_alerta`); `vazamento_prompt` ignores the quoted example speech of the prompt (what the agent is meant to say) and the correction texts; `opt_out_palavras` opts a lead out on an exact
  `PARAR|PARE|PARA|PAREM|SAIR|SAI|STOP|CANCELAR|CHEGA|NÃO QUERO MAIS` with no model call, in EVERY conversation state (paused / handed over / agent off / killed / draining too: the refusal path records it via the same `aplicar_encerramento` and answers `encerrar`+`opt_out`; see julia-v2 CONTRACT §5.2); `contexto.estado.texto_base` / `atendente_nome` are
  validated like a spec; `encaminhada: true` messages are marked for the model and never evidence.
- Provenance + leak tripwires (migration 046, `channels/proveniencia.py`, `stores/marcadores.py`; GUARDRAILS B2/B7):
  authorship is structural, never inferred from text. Lead lines stay one plain `user` message; human / other-agent /
  event lines are `system` JSON envelopes keyed `plataforma_<tag>` (tag random per turn, told to the model in DB text
  `contexto.aviso_proveniencia`; earlier tags kept in `messages.meta.tag`; a lead echoing one = `forja_proveniencia`).
  Inbound `midia` and `truncado` render as labelled JSON literals (`historico.rotulo_midia` / `rotulo_truncado`); only
  audio transcription counts as the lead's words. `autor: {nome, papel?}` is accepted ONLY on
  `/api/channels/threads/{id}/mensagens` with `role: "humano"`; `/api/channels/turns` rejects it (422). Correction
  `evento` rows persist `conformidade:<regra>` only (046 redacts old rows; CHECK enforces it). An inbound canary or
  12-token prompt run = `canario_recebido` (severity alta, platform admins only). A per-version honeytoken
  (`agent_version_marcadores`, service-role, never returned) appended via `seguranca.marcador_interno`: in a reply it
  blocks as `vazamento_prompt`; inbound or in tool args it is recorded only.
- Identity at rest (GUARDRAILS B8.4, `channels/turno.py::_redigir_identificacao`, `MessageStore.redigir_identificacao`): once
  `registrar_identificacao` stores a CPF/RG, the turn replaces exactly that value (digits/letters, any separator) by
  `***` in `texto`, `blocks` and `meta` (incl. `midia.texto_extraido`) of every row of the thread - also when the turn
  aborts. Other numbers are left alone. A failure is logged by type only and booked as the `identificacao:redacao_falhou`
  event; the reply is never blocked. The thread's realtime scope is purged too (`noctusai_lib.realtime.redact_values`: the
  lead's `message.new` published before the registration is deleted from the retained window, so a reconnecting subscriber
  never replays the number; failure logged by type only). The masking itself is `noctusai_lib.primitives.identificador_redacao`.
  The turn response carries `identificacao_registrada` (any field registered in the turn).
- A new required text key must be seeded as data BEFORE the code that needs it deploys (`textos_registry`); an org
  seeded earlier gets 409 `conteudo_incompleto`, never a default string.
- Skill texts are org-resolved: the turn wraps its `SkillFonte` in `SkillsComSpecs`, so `abrir_skill` /
  `ler_arquivo_skill` return the index line, body and files with every `{{org.chave}}` replaced by the org's value -
  the same `especificacoes.resolver_texto` the prompt sections go through (own and pinned library skills).
- Org specs are UNTRUSTED DATA (Julia-line E1-E3): every value is validated by its declared `tipo`
  (`spec_formatos.py`: texto_curto/texto/texto_longo(4000)/url/dominios/contatos/cnpj/creci/horario/duracao/lista) through
  the one `especificacoes_service.validar` (studio PUT, readiness, compiler). `SPEC_VALIDATION_MODE=report|block`
  (default report: accept + `spec_org_invalida` aviso; block: 422 + bloqueante). Free-text values are never inlined -
  prompt text AND opened skills show `[dado: chave]`; one section "Dados da organização" (rows
  `compilador.titulo_dados_org` / `compilador.dados_org_intro`) carries them as JSON. Never add a path that inlines a
  free-text spec value. Details: `projects/julia-v2/CONTRACT.md` §2.6.
- Optional enum parameters (`Literal[...] | None`, `anyOf [enum, null]` in the schema) get their value labels from the
  row too (`enriquecer_schema`), like required ones. The extraction-only tools (`registrar_resumo` /
  `registrar_escolha`, `ferramentas_registry.FERRAMENTAS_DE_EXTRACAO`) are never offered on a turn and are not listed in
  the conversation prompt's `# Ferramentas` block (their rows stay hashed content).
- `oferecer_imoveis` speaks SW's v2 `buscar_imoveis`: the lead's must-haves (criterion `itens_essenciais`) go as
  `itens_essenciais` (SW hard filters), nice-to-haves as `caracteristicas`; the answer's `restantes_estimados`,
  `relaxado` (axes SW widened), `similar_a_encontrado` and `itens_nao_verificaveis` (asked items SW's catalogue cannot
  verify — pets, proximidades — which did not filter; Julia confirms them) reach the model next to the listings
  (explicit allowlist `BUSCA_META`, now in `app/catalogos/imoveis_sw.py`).
  **Offer catalogue seam (migration 081).** `oferecer_opcoes` / `detalhes_opcao` / `registrar_reacao_opcao` are the
  catalogue-neutral twins of the three imóvel tools and share ONE core with them (`app/channels/tool_registry.py`); the
  catalogue is an adapter behind `app.catalogos.CatalogoOpcoes` (`imoveis_sw`, `fixture`; `catalogo_para` refuses an
  unknown key). The agent's catalogue is `qualificacao_parametros.catalogo`; readiness blocks `oferecer_opcoes` active
  without one (`catalogo_ausente`); lead events carry `lead_imovel_eventos.catalogo` (duplicate-offer is per catalogue).
  `encerrar` ends the participation: a later re-engagement is ignored (no model call) and the thread reports
  `reengajamento_suprimido`; the lead-level opt-out (`POST /leads/{ref}/opt-out`) does the same for every agent.
  `encerrar` with motive `lead_pediu_parar` (+ a required `motivo_texto`) IS that lead-level opt-out: a lead who
  asks to stop is never dropped silently. `app/channels/opt_out.py` (`OptOutService`) records the opt-out, ends every
  agent's participation and writes an `agents.lead_opt_out_eventos` row (origin agente | operador | integracao, the
  agent / thread / operator, the reason, the lead's own message, how many participations ended), then notifies the org's
  owners/admins in-app (`kind agents.lead_opt_out`, deduped on the event; the sink is `app/notifications.py`). The
  outcome of the notice is on the event (`pendente | enviada | falhou` + the error): a failed notice is a visible row and
  an error log and never undoes the opt-out. A repeat while the opt-out is in force records no second event and notifies
  nobody again; an opt-in lifts it. The thread and the opt-in / opt-out responses expose the latest event as
  `opt_out_evento`. Migration 042. The opt-out is a per-ORG setting owned by social-wiring (owner decision 2026-10-21):
  agents stores and enforces it and has NO Opt-outs page; SW calls the token routes below.
  Token routes for SW (all `require_channel_*`, org from the token, human sessions 403): `GET
  /api/channels/leads/{ref}/consentimento` (thread-independent; unknown lead -> 404 `lead_desconhecido`);
  `GET /api/channels/opt-outs?limit=1..100&cursor=&lead_ref=` (`{items, next_cursor}`, newest first, both `tipo`s);
  `POST /api/channels/opt-outs/{evento_id}/notificar` `{ator_user_id}` (re-send a `falhou`/`pendente` notice, idempotent;
  a re-send that fails again is 200 with `falhou`); `POST /api/channels/leads/{ref}/reativar` `{ator_user_id, motivo}`
  (both required) lifts the opt-out (`opt_in_origem` `reativacao_manual`) and records a `tipo=reativacao` event in one
  RPC (`agents.reativar_lead`), notifies the org admins; 409 `sem_opt_out_ativo` / 404 `lead_desconhecido`. The lead is
  back in the flow: its next message reopens the `encerrado` participation (controles). `lead_opt_out_eventos.tipo`
  (`opt_out` | `reativacao`) is on every `OptOutEventoOut`. Notices carry `metadata.product=social-wiring` and
  `metadata.link=/julia/opt-outs?evento=<id>` (SW's julia pages). `GET /api/conversations/channel` items carry
  `opt_out_evento`; the staff thread view shows it as a plain-text banner. The seed `NotificationBell` opens
  `link`/`metadata.link` on click (`onNavigate`, wired in `createProductInfra`). Migration 043.

### Julia v2 — mechanism evals as the publish gate (A-EVAL)
- `eval_cases` gain `suite` (`mecanismo` | `comportamento`), `k`, `roteiro` (scripted multi-turn lead messages + fixture catalogue) and `asserts` (deterministic, code-checked: ferramentas_incluem/proibidas, estagio_final, criterios_registrados, ofertas_por_lote, sem_violacoes, identificacao_completa, handoff_para, sem_vazamento, skill_aberta_antes_de; adversarial keys: acoes_incluem/proibidas `[type | {type, ...arg subset}]`, handoff_motivo, sem_handoff, violacoes_incluem, bolhas_sem_padrao `[regex]`, bolhas_max_chars, sem_links_externos (catalogue `link`s allowed), sem_pii (valid-DV CPF, CNPJ, RG, third-party token value), sem_resposta, participante_estado, solicitacao_titular `tipo` of the `registrar_solicitacao_titular` call; follow-ups: roteiro turn `{retomada: true|{tier?,texto_base?}}` with `fixture.retomada {tier,texto_base,seguidas_previas}` runs a `reengajamento` turn, asserts retomada_status (normal|reengajamento_ignorado) + retomada_tier_usado; the cap (`seguidas_previas`>0, `limite_retomadas`) is refused until its store lands). Migration 038, service-role only.
- `app/studio/eval_mecanismo.py` runs pass^k (a case passes only if all k executions pass), supports sharded scenarios and a `limite_usd` cost cap; runs are stored in `eval_mecanismo_runs` / `eval_mecanismo_execucoes`.
- Publish of an agent with `exige_mecanismo` (or any active mecanismo case) requires the newest LIVE run for the current compiled hash to be complete, under budget and fully green — enforced in the router AND in the DB publish function (409 `mecanismo_reprovado`). The `comportamento` (judge) suite is advisory unless `comportamento_bloqueia`.
- The turn driver is a Protocol (`app/studio/eval_driver.py`, `tipo` live|fake); `POST /api/studio/agents/{key}/draft/mecanismo-runs` (platform admin) runs the suite; the studio's "Prontidão para publicar" panel exposes it as the **Rodar suíte de mecanismo** button (`ProntidaoAcao.tsx` + `hooks/studio/useMecanismo.ts`: POST then poll the GET run until terminal, then refetch prontidão); several runs of one version may execute at once (migration 071 dropped both one-in-flight indexes; each run has its own id, results and `limite_usd`), and the button follows the newest run it started, alongside **Rodar avaliação completa**, **Ligar agente** and **Atualizar skills** — `acao_sugerida` copy never names an API path. A roteiro's `fixture.origem` (`{canal_origem?, codigo_imovel_campanha?}`, validated by `ContextoOrigem`, unknown keys refused, both suites) makes the eval thread an ad lead: the live driver (`contexto_de_avaliacao`) hands the turn a SW `estado.origem`, so the state block shows the campaign code and `oferecer_imoveis modo=campanha` (exempt from `pode_ofertar`; a re-request resends the card + link) resolves it against the case's `catalogo`. Eval fixtures are synthetic: a PII guard refuses phones/CPF/emails (never real WhatsApp transcripts — Meta WhatsApp Business terms §4.7).
- Identity flows are scripted with TOKENS (`app/studio/eval_sinteticos.py`): `[[cpf_sintetico_valido]]` (a random, check-digit-valid CPF generated per execution, never a fixed one) `[[cpf_sintetico_terceiro]]` (a second valid CPF, a third party's; `sem_pii` forbids the agent repeating it) and `[[email_sintetico]]` (`lead.<random>@example.com`, RFC 2606) are substituted by the live driver right before the turn; an unknown `[[token]]` is refused at validation. `skill_aberta_antes_de` reads `abrir_skill`'s real argument, derived from `AbrirSkillArgs` (`nome`).
- Mechanism cases are written through the eval case API (`suite`/`k`/`roteiro`/`asserts`), by a platform admin or the `studio:content-write` token (`noctus.agents.content` kind `evals_mecanismo`, audited `conteudo_editado_mcp`); deleting a case stays human platform-admin; the run routes (start / list / read / cancel, both suites) are platform admin or the platform-issued `studio:evals-run` token (mint: `POST /api/studio/plataforma/content-token` `{label, tipo: "avaliacoes"}`), which reaches nothing else.
- Eval-loop gate (migration 076; contract `docs/eval-loop-gate-contract.md`): `app/studio/eval_loop.py` holds the pure rules (G1-G7), `eval_loop_service.py` the admission (`hash_inalterado`, `orcamento_do_loop_atingido`, `rodada_em_andamento`, ...), the round close hook (called by `EvalRunner.execute` and the mechanism route's background task) and the mid-flight stop notice through the agents `NotificationSink`; `studio_eval_loops_router.py` the loop endpoints. A run started with `loop_id` is a whole-suite round (no `case_ids` / `repetir_falhas_de` / `modelo_geracao`); its cost is the run's own `custo_usd`, never a second spend tracker. Runs without a loop are unchanged. Owner kinds `eval_loop_parada` / `eval_loop_checkpoint` (whatsapp + in_app) are declared in `app/notification_kinds.py`; the pt-BR WhatsApp texts are built by `app/studio/eval_loop_whatsapp.py`; the send is a seam (`NOC-REMEDIATE[eval-loop-owner-whatsapp]`) until `notify_owner` is wired, the in-app bell is unchanged.
- Token-started eval runs (`studio:evals-run`) are bounded against denial of wallet: `limite_usd` above the settings default is 422 `limite_usd_above_default`, a `modelo_geracao` override 422 `modelo_geracao_not_allowed`, a non-draft `version_id` 422 `version_not_draft`, and the org's rolling 24h token-run spend (`EvalStore.org_spend_since`, ceiling `studio_eval_token_daily_budget_usd`) is fail-closed: 429 `eval_daily_budget_exceeded`. The scope is evals-only (a token that also carries `studio:publish` falls back to the dev-advisor rule) and is rejected by the generic mint route (strict `MINTABLE_TOKEN_SCOPES`); token reads of run detail are audited (`definicao_lida`).

### Julia v2 — consumer and Studio support (A-RT2, migration 040)
- `GET /api/channels/agents/{key}/qualificacao/estagios` (channel token) → ordered `[{chave, rotulo, ordem, conclusivo}]` only; the turn response carries `qualificacao.estagios_ordem`.
- `GET|PUT /api/channels/agents/{key}/specs` (channel token, scope `agents:channel-specs`, bound to `{key}`) → the org's business specs, SW's editor behind `/api/julia/especificacoes`; the same service as the studio `PUT /api/studio/agents/{key}/specs` (`aplicar_org_specs`: declared keys only, `especificacoes_service.validar`, report → 200 + `invalidas`, block → 422 + `violacoes`, undeclared → 422 `spec_nao_declarada`). PUT body also carries `ator {user_id, nome?, email?}` (REQUIRED, product-attested by the channel token; absent → 422 `ator_obrigatorio`; recorded as `updated_by`/`updated_by_nome`/`updated_by_token`, migration 062, and in the audit with the token id); `valores[]` expose `updated_by`, `updated_by_nome`. Values are DATA (fenced in the compiled prompt); `routers/channel_specs_router.py`.
- Publish pins the qualification standard version on the agent version (`qualificacao_versao_id`, inherited by new drafts, covered by `compiled_hash`); `GET|PUT /api/studio/agents/{key}/(draft/)qualificacao` (platform admin).
- `GET /api/agents/catalogo` — tiered: org users get `{key, nome, papel, descricao_publica, runtime, capacidades}` from DB rows (`catalogo_agentes`, `catalogo_capacidades`); platform admins also tool keys + versions.
- Every Studio 409 reads pt-BR text keyed by its `code` (`MENSAGENS_CONFLITO` / `mensagem_conflito` / `erro_de_item` in `app/stores/_db_errors.py`); the exception's own message (raw Postgres text with constraint names, or internal English) never reaches a person. A test fails when a conflict code raised in `app/` has no text.
- Studio support: `/capacidades` (server-provided tier + tabs), conformidade rule/violation routes (codes only), thread result + participant state on the channel conversation list, textos/ferramentas registry (structure only), `ponto_cache` in compiled outputs, mecanismo summary on versions.
- Atomic optimistic lock: the replace-set PUTs send `expected_hash` → `replace_draft_conteudo(p_expected_hash)` locks the draft row and refuses a stale writer (409 `conflito_de_versao`). The draft-skill PATCH (`/draft/skills/{id}`) takes the same `expected_hash` → `update_draft_skill(..., p_expected_hash)` (migration 041). The content hash covers the version's own skills (name, index line, body, order, flag, files by sha256), so a skill edit moves it and breaks a stale CAS.
- Conformance rules: `GET /api/studio/agents/{key}/conformidade/regras` lists them; the `studio:content-write` token (kind `conformidade_regras`) may read/write the DEFINITION's row only (403 `org_id_nao_permitido` for another org). Rules are not versioned: a write applies from the next turn.
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

#### Every agent in the same house (`projects/agents-unified/CONTRACT.md`)

`/agentes` (`pages/Agentes.tsx`, `GET /api/agents/painel`) is THE listing: one card per agent of the org (legacy,
platform instance, org Studio agent), with papel / origin / state / capabilities from data, a papel filter, and the
on/off switch only when the server sends `pode_alternar`. Every card opens ONE page, `/agentes/:key`
(`pages/agente/AgentePage.tsx`): header from `GET /api/agents/{key}/painel`, section nav = `painel.secoes` (the
sections THIS caller may open, decided server-side from origin + tier) titled by `GET /api/studio/modelo`, the section
in `?tab=<id>`. Section ids are the former Studio tab ids, so the content renderers are the Studio tabs below; the
renderer of `conversar` / `compilado` is chosen by the agent's origin, never its key. Agent internals
(`/painel/interno`, the model's areas + wizard steps) answer 404 to anyone but a platform superadmin (D31).
The former shells redirect, keeping the query: `/studio/:key`, `/agentes/:key/persona`, `/agentes/catalogo`; the
academia ones (`/bia`, `/julia`, `/agentes/bia/persona|conversar`) go to the agent `GET /api/agents/painel/destino-chat`
names (the academia principal's agent, else the org's code-defined chat agent). Superadmin-only cutover routes:
`POST /api/agents/{source_key}/transferir-historico` and `POST /api/agents/{key}/arquivar` (migration 053).
`/studio` redirects to `/agentes`: the former console's actions live on the listing — "Novo agente" (platform
admins, from `modelo.tier`) opens the wizard, "Importar pacote" (org admins), and for platform admins the skills
library link, a per-card "Excluir" (type-the-key confirm; not on legacy / external agents) and the MCP content-token
card. `GET /api/agents/catalogo` (migration 040) still feeds the cards' papel / description / capabilities.
Migration 052 drops the orphan `studio` status_pagina row (same cleanup as 051).

#### New-agent wizard (`/agentes/novo` — `pages/agente/NovoAgente.tsx`, CONTRACT §6)

Platform admins only: the page reads `GET /api/studio/modelo` and renders the standard not-found when the caller's
tier is not `plataforma` (or `assistente` is null / the read is 403). The journey is the seed `JourneyWizard` organ
(`@noctusai/lib/journey`) over `modelo.assistente.passos` — steps, order, categories and each step's fields come from
the model; field widgets, required flags, limits (`min_length`, `max_length`, `pattern`, `minimo_exclusivo`,
`maximo`), options and defaults (`padrao`) come from each `CampoModelo` (`lib/assistente.ts` holds only pt-BR
fallback labels, hints and option names plus three create-body facts the schema cannot express: a new key needs `nome`, `limite_usd` only matters
with a briefing, `briefing.nome` = the agent's name). A step mixing `plataforma` and `briefing` fields splits into
subtabs. Two start modes: "Começar vazio" (definition only, briefing fields hidden) or "Gerar com IA" (the briefing
is sent and the server writes the first DRAFT, capped at the model's `limite_usd.maximo` = US$ 5, shown on screen).
Answers live in a localStorage draft (`agents:novo-agente:rascunho:v1`, try/catch, a refused write is said on
screen) with the seed `UnsavedChangesNotice` until "Publicar"; "Revisão" summarises them with per-step edit.
"Publicar" re-validates every step (jumps to the first invalid one), POSTs the §6 body to
`POST /api/studio/plataforma/agents` via `useCreatePlatformAgent` (cache-writes: the new card is committed into
`["agents","painel"]` and `["agents","painel",key]`, plus the Studio list), then opens `/agentes/:key`. Creating
makes a draft; publishing a version is the eval-gated `POST /draft/publish`, never the wizard. An existing key is
refused by the route (409 `agente_ja_existe` unless the body sends `reutilizar: true` — only the MCP `criar_agente`
does, to stay idempotent); the wizard catches it, returns to the step that owns the key and shows the refusal on the
field. Field labels are the models' pt-BR `title=` (`Briefing`, `PlataformaAgentCreateRequest`, served as `rotulo`);
the FE table is only a fallback.

#### Studio, tier-aware (Julia v2 — `frontend/src/pages/studio/`)

These tabs render as sections of `/agentes/:key` (above). Which tabs render is decided by the SERVER row, never by a role string: `definition_scope` on
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
truth; "Rascunho v{n} · editável" vs "Publicada v{n} · somente leitura" is always shown, and on an editable
draft the header carries "Publicar rascunho" (admin only; the SAME `components/studio/PublishDraftDialog.tsx`
Versões uses — blocking warnings, eval gate, limiar — disabled with "Salve as alterações antes de publicar"
while the tab is dirty; it publishes the whole version, decisions included); loading uses
`showSkeleton = isPending && !data` / `isRefreshing = isFetching && !!data` (computed in the hooks).
Org-spec refusals (`spec_conflita_com_regra_fixa`) render inline on the offending field with the locked
block's label only; qualification publish refusals (`regras_invalidas`) list every rule error with its
path; the Controles dialog states what happens to the open conversations before a mode change.
Open gaps are marked `NOC-REMEDIATE[...]` in `types-julia.ts` and the `use*` hooks (conformidade
routes, studio thread state/results).

### DB-source dev agents (Agent Packages A11/A12, migration 070)

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

### Agent layers (BASE → SDR → agent; roadmap `agent-templates-2026-11`)

`app/studio/camadas.py`: a child agent's version holds only its OWN rows; the compiler, the runtime turn, the eval driver and readiness read the EFFECTIVE rows (`EfetivoStore`), the parent chain merged in per piece by key. Prose section with the same key: the child APPENDS (parent title, order and active flag kept). Single values (text, tool row, decision, org-spec declaration, own skill): the child REPLACES, reported as an override. Files follow their skill. Editors keep reading own rows. A cycle or a chain deeper than 4 is refused (`EfetivoStore.cadeia` lists root → self). Migration 073: `agents.modelo` (a template: platform-owned, never instanciavel nor channel-owned) and `agents.pai_agent_id` (parent must be a template of the same org, no cycle; trigger `guard_agent_camada`, 409 `pai_invalido`); `agent_versions.pai_versao_id` is written only by publish. A child's DRAFT reads its parent's draft (else its active version) live; its PUBLISH pins the parent's current active version: the router recompiles the child against that version and refuses `pai_desatualizado` (409) when the hash differs from the evaluated one, `pai_nao_publicado` when the parent has none. A version published before its agent had a parent stays exactly as it was. Setting a layer: `POST /plataforma/agents` and `PATCH /plataforma/agents/{key}` (and `noctus.agents.content` `criar_agente` / `configurar_agente`) carry `modelo` + `pai_agent_id`, and the response shows them; at create the layer is validated BEFORE the row exists (`validar_camada_nova`), so a refused parent leaves no un-layered definition, then applied via `update_definicao` (as `superficie_claude`).

**Hand-off fallback number (migration 074).** When an agent hands a conversation to a person, the team is notified at `numero_fallback_atendimento`: ONE E.164 number for every org for now (owner 2026-11-09; per-org later), a platform runtime setting on the admin page "Configurações do agente" (`PUT /api/admin/agent-settings`, normalized by `noctusai_lib.primitives.phone`, DB CHECK backstop). Unset ⇒ readiness item `numero_fallback_ausente` (bloqueante) and publish 409 `numero_fallback_ausente` for every conversational agent (`prontidao.falta_numero_fallback`; the internal generator is exempt).

### Creating a complete agent (Julia as the reference — `KNOWLEDGE-BASE/CONTEXT/GUIDES/agent-creation.md`, skill `noc-new-agent`)
- The recipe, the artifact map (what Julia has, where it lives), the publish-gate table and "what never comes from AI" live in that guide; read it before building or generating an agent.
- `app/studio/prontidao.py` + `GET /api/studio/agents/{key}/prontidao`: the draft's readiness. `compor` is pure (`Entrada` -> items `{codigo, grupo, severidade, mensagem, acao_sugerida, recusa_publicacao, detalhe}`), `coletar` reads. A BLOCKING item names the publish 409 code it stands for (`RECUSAS_PUBLICACAO`); the publish route and the view share the predicates (`recusa_de_compilacao`, `juiz_aprovado`, `decidir_portao`) and `tests/studio/def/test_prontidao.py` publishes a draft in every refusal state to keep them in lock-step. Every publish 409 carries the same `prontidao` list. Advisory (never blocking): stale skill pins, tools the configuration expects without a description row, tool parameters without a label (`rotulo_parametro_ausente`), unfilled org specs, generator gaps, controls off.
- Generation: area `evals` (behaviour eval cases through `EvalCaseInput`; per-case PII guard -> `lacunas`; an author-typed slug is never overwritten); `referencia` on `POST .../geracoes` = an exemplar agent key (`agents.agents.exemplar`, migration 058; toggled ONLY by `PUT /api/studio/plataforma/agentes/{key}/exemplar`, platform-admin session). `estrutura_exemplar` adds tool parameter labels, decision options, eval-case shapes and the standard key; verbatim text only inside the platform org, the leak guard covers all of it. The per-area instruction text is DATA (generator agent's `area-<area>` sections), never code.
- `POST .../draft/skills-biblioteca/atualizar`: explicit re-pin of every pinned skill to its newest PUBLISHED version (keeps `obrigatoria_para`/`ordem`; audited; re-stamps the hash). MCP: `noctus.agents.content action=prontidao | atualizar_skills`.

### Platform-defined agents and org specs (Julia v2 — `app/studio/`)

- `definition_scope`: `org` (default — owns its versions) · `plataforma` (THE definition of a key, in the
  platform org, one per key) · `instancia` (an org's instance: no versions). A platform definition is ANY
  `definition_scope='plataforma'` row — there is NO code registry and no agent key is known to the code (migration
  049): what a registry used to carry is DATA on the row (`runtime`, `owner_product`, `escopo_qualificacao`,
  `padrao_qualificacao`, `rascunho_padrao` = the first draft's settings, `instanciavel`, `papel` = `gerador`, `exemplar`), written through
  `POST/PATCH /api/studio/plataforma/agents[/{key}]` (platform admin or the content token; `GET` reads it) and read by
  every mechanism from the definition record (`plataforma.escopo_de/padrao_de`, compile, the channel turn, org-instance
  creation). `usa_canais` (on the agent summary/detail) is DERIVED from that data (`owner_product` set on an `llm`
  runtime — the compiler's own `canal` rule), so the UI shows the channels tab off it, not off a key.
  An org gets an instance of every PUBLISHED definition that is `instanciavel` (default false; never for an owned definition) OR granted to it (`definition_org_grants`) on first list (`plataforma.ensure_instancias`)
  and of a channel agent on first channel use (`ensure_instancia`). A key that is a platform definition is refused as an
  org agent (`key_taken`); the only legacy key knowledge left is `channels/chaves_legadas.py`
  (`NOC-REMEDIATE[drop-lead-imob-alias]`). `conteudo_modo='linhas'` (always for plataforma/instancia): every
  compiler string is a row of `agent_version_textos`, the tools block lists `agent_version_ferramentas`,
  decisions are `agent_version_decisoes`, the `{{org.x}}` placeholders are declared in `agent_version_specs`;
  the org's values live in `agent_org_specs`. The registry (`textos_registry.py`, `ferramentas_registry.py`)
  holds KEYS only; a missing required text is a blocking warning and publish answers 409
  `conteudo_incompleto` — never a default string.
- `resolucao.resolve_agent_for_org(store, org_id, key)` → `(instancia, definicao, versao, specs)`;
  `compile_for_org` compiles the definition with that org's values (the hash covers texto + every content
  row + the version's own skills + the pinned standard); spec usage (`spec_nao_usada` / `spec_nao_declarada`) is read
  from the AUTHORED rows (and the placeholders a pinned library skill uses, `SkillRef.placeholders`), never from the
  org-resolved text; the identity block lists criterion labels, never keys; `carimbo` = the version tuple stamped on messages; `ponto_cache` is the
  prompt-cache breakpoint (static prefix before the client block).
- DB lockdown (migration 036): every agents table is service-role only — no anon/authenticated grant or
  policy (except read-only `status_pagina`), so a browser session cannot read content over PostgREST.
  New migrations must keep it so (keeper `check_no_authenticated_grant_on_content_tables`).
- Visibility tiers (server-side): definition reads (`versions`, `compiled`, `prompts/{hash}`, `diff`,
  textos/ferramentas/decisoes/payload, compiled-per-org) are **platform-admin only**, audited as
  `definicao_lida`; writes are platform admin or a `studio:content-write` token (audited
  `conteudo_editado_mcp`); an org admin gets `GET/PUT /agents/{key}/specs` (its own values; text that
  contradicts a platform-locked rule is refused 422) and `GET /agents/{key}/status` (booleans only). The clients,
  The `agent_audit_log.acao` CHECK must list every action in `stores/studio_definitions.AUDIT_ACOES` (047 restored
  `definicao_lida` + `specs_org_editadas` after 034 dropped them; `tests/test_migration_audit_acao_check.py` pins the
  latest definition).
  knowledge, evals and package-sync routers are platform-admin only too; the `studio:content-write` token is minted
  only via `POST /api/studio/plataforma/content-token` (issuer `noctus-platform`, platform admin, org-bound to the
  platform org) with `expira_em_dias` 1..365 (omitted = 30, explicit `null` = never expires: a NULL `expires_at`,
  not a far date). `GET /api/studio/plataforma/content-tokens` lists the platform org's content tokens (label, prefix,
  created/by, expiry, last use, status; never the secret) and `DELETE .../content-token/{id}` revokes (idempotent);
  mint and revoke are audited. The Studio home (`/studio`) carries the platform-admin "Token de conteúdo (MCP)"
  section: "Gerar token" dialog (label, days or "Nunca expira" with a warning), the secret shown once with where to
  put it (`NOCTUS_AGENTS_CONTENT_TOKEN=` in `~/.config/noctus/agents.env`), the list and a confirmed "Revogar".
  The mint dialog's "Permitir excluir agentes" checkbox (`permitir_exclusao`) adds scope `studio:agent-delete`;
  such tokens carry a badge in the list. The agent list (platform admins) has "Criar agente" (`CriarAgentePlataformaDialog`:
  a key -> `POST /plataforma/agents`, an empty shell; a creation-mode seam `MODOS_CRIACAO` for the coming AI-generated
  draft) and a per-row "Excluir" (`ExcluirAgenteDialog`: type the key to confirm; 409 reasons from the flat error body
  mapped to hints in `lib/agentLifecycle.ts`). Hooks: `hooks/studio/useAgentLifecycle.ts` (cache writes, no invalidate-only).
  Scope: the token is org-bound to the platform org, so it reaches every platform-defined agent there through the
  draft routes only; it never publishes.
- Agent lifecycle (S1, migration 048): an agent can be DELETED and created EMPTY. `DELETE /api/studio/agents/{key}`
  (204; platform admin, or the content token minted with `permitir_exclusao` = extra scope `studio:agent-delete`,
  `require_agent_delete`; a plain content token is 403 `scope_missing`) runs `agents.excluir_agente` (SECURITY
  DEFINER, service role): it re-checks the guards in SQL and answers 409 (flat body `{code, message, detail}`) with
  `publicado` (any non-draft version) · `tem_instancias` (a plataforma definition with instances) · `tem_conversas`
  (a conversation with >= 1 message, a message authored by the agent, or lead records it collected) · `tem_canal`
  (an unrevoked, unexpired channel token whose principal is the agent) · `ativo` (on). 404 `agente_nao_encontrado`.
  Empty conversations, the draft and every dependent go with it. The audit log OUTLIVES the agent:
  `agent_audit_log.agent_id` is nullable (FK ON DELETE SET NULL), `agent_key`/`agent_nome` are snapshotted on every
  row (BEFORE INSERT trigger), the append-only guard permits exactly one mutation (`agent_id` -> NULL, only while the
  transaction-local flag `agents.agent_delete` is on) and the RPC writes an `agente_excluido` tombstone (agent_id NULL).
  `POST /api/studio/plataforma/agents {key, nome, ...}` (ANY valid key `^[a-z0-9][a-z0-9-]{1,62}$`; `nome` required for
  a new key, 422 `nome_obrigatorio`; platform admin OR the content token) creates the EMPTY platform definition (no text
  required: only publish is gated by completeness) and audits `agente_criado` once; the 201 body carries the definition's
  data + `geracao` (see below). MCP: `noctus.agents.content` actions `criar_agente` / `configurar_agente` / `definicao` /
  `excluir_agente` / `gerar` / `geracao` (writes are dry-run unless `confirm=True`).
- AI-generated first drafts (S3a, migration 049; `app/studio/geracao.py` + `geracao_itens.py`,
  `routers/studio_geracoes_router.py`, `stores/studio_geracoes.py`, seed `chat_completion_with_usage`).
  `NOC-REMEDIATE[ai-draft-generation-seed]` (N=1, agents-only). A short creation form (`Briefing`) becomes a DRAFT starting
  point — sections, system texts, tool descriptions, decisions, org-spec declarations, library-skill pins and initial
  settings — never a published version. The generator is a platform agent found by ROLE (`papel='gerador'`; its
  PUBLISHED version: sections -> system prompt, `planejamento` + `area-<area>` sections = the instructions, model/provider
  = the version's, priced from the seed catalog or `409 gerador_indisponivel`); `papel='exemplar'` definitions give the
  STRUCTURE the output imitates (their verbatim text only when the target is in the platform org; otherwise the leak
  check — fingerprint, `GuardaVazamento` — blocks an output that reproduces it). No instruction text lives in code:
  the call carries `{instrucao, briefing, plano, diretriz, contexto, exemplar, schema_saida}` as JSON data.
  Routes (all `require_platform_content_admin`, flat `{code, message, detail}` errors): `POST /agents/{key}/geracoes`
  (202; one `pendente|executando` run per agent; `forcar`; `limite_usd` 0..5.00, DB-capped), `GET .../geracoes[/{id}]`,
  `POST .../geracoes/{id}/areas/{area}/repetir`, `POST .../cancelar`. Pipeline: 1 planning call + 1 call per area
  (<= 2 parallel, background task like the eval runs; startup sweep marks stale runs `falhou`/`interrompida`). Cost: a
  worst-case estimate (input chars/2.5 + max_tokens x price) must fit the remaining budget BEFORE each call, else the area
  is `pulado` (`limite_de_custo`); unmeasured usage is charged at the estimate. Each area's JSON is validated by a BE
  schema (the same item models the manual routes use) and MERGED into the draft through the same store functions the draft
  routers use (rows a previous generation wrote are replaced, the author's rows are kept). Item identity is a hash stored
  at write time; `gerado` vs `editado` is recomputed at read time, and a re-generation without `forcar` is 409
  `conteudo_editado` (`detail` = the area names). On the FIRST publish after a generation the per-area
  generated-vs-published diff is stored in `geracoes.aprendizado`. Audit `agente_gerado`. `GET /agents/{key}` carries
  `conteudo_status {textos_preenchidos, textos_total, obrigatorios_faltando}` (null for legado agents / instances).

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
  (factor after N days without a lead reply). `parametros.lote_ofertas` = up to 3 properties per offer run (owner's
  rule 2026-11-03; migration 055 column default; 1..5, shown in the editor).
  Follow-up cap (owner 2026-11-10): `parametros.max_retomadas_seguidas` (default **2**, 0..10, migration 080) is the most
  follow-ups (`gatilho:"reengajamento"`) in a row with no reply from the lead; `controles.decidir` refuses one more with
  status `limite_retomadas` (no model call, nothing stored; opt-out is decided first), every outcome is one append-only
  `thread_retomada_eventos` row, and social-wiring ends that contact's sequence.
- **Store timestamps**: every Real-store row mapper parses `timestamptz` through `app.stores._util.db_ts`
  (PostgREST returns ISO strings, the Fakes hold `datetime`; a passthrough 500'd every published-version read).
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
  Studio authoring UI: `/studio/biblioteca-skills` (list + "Nova skill") and `/studio/biblioteca-skills/:chave`
  (name/label, versions, the draft editor for the model description + body + notes + reference files, discard,
  and "Publicar" behind a confirmation). The agent's "Skills da biblioteca" tab links each library card there.
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
  parameters, mechanism eval cases `evals_mecanismo`, conformance rules `conformidade_regras`) into a target
  environment through these routes: drafts only (eval cases and rules are not versioned and the result says so;
  nothing ever publishes or runs), dry-run by default, payload from a file outside git, token from
  `NOCTUS_AGENTS_CONTENT_TOKEN`.
- DB guards of migrations 031-041 are proven by behaviour probes (`noctus.dev.verify_db_guards`,
  `_AGENTS_JULIA_V2_PROBES`, parked `pending_migration` until applied); only `agents_one_plataforma_per_key` stays
  allowlisted (reason in `compliance._GUARD_PROBE_ALLOWLIST`).

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


## Julia turn redesign (2026-11-05)

Skill gate -> auto-load (`DECISAO-SKILL-AUTOLOAD.md` under `projects/julia-v2/`): `tool_registry._handler` opens a tool's skill for the turn and attaches `procedimento_obrigatorio`; `JuliaTurno.skills_carregadas` is turn-scoped and `reiniciar_tentativa()` resets budgets for a re-run. `turno.executar` splits the stop causes (`PARADAS_PROCEDURAIS`: silent re-run, fallback + `alertar_operacao`, no hand-off). `turno._compilar` caches published compiles (`ESTATISTICAS`, `limpar_cache_compilacao`). `EvalRunner` takes a `turn_driver_factory` so judge cases run on `LiveEvalTurnDriver` (`ThreadState.contexto_caso` -> state block; `definir_modelo/temperatura/historico` are A/B knobs). Version temperature: `tool_policy.temperature`, default 0.3 — inert on Anthropic models since API 2026-10-21 (the provider never sends it; JL-020).

Leak fingerprint (turn redesign): `JuliaTurno.textos_derivados` collects every skill body / file the tools hand the model; `conformidade.impressao_com` adds them to the fingerprint for the turn's reply check, and `avaliar_resposta` runs `vazamento_prompt` on `esqueleto(resposta)` too.

- Grants are per (agent, product, org) with a personal token; channel requests re-check the grant is live (`assert_channel_grant_live`). Grant lifecycle changes are recorded in `agents.agent_product_grant_eventos` (migration 083, trigger-written, append-only). Staff edit an org's specs only under a live grant (`/api/studio/plataforma/agents/{key}/products/{product}/orgs/{org_id}/specs`, migration 064 `especificacoes_editor`).

- **Turn metrics (migration 066, CONTRACT §14):** `agents.turn_metrics`, one row per turn (cost from the summed priced D25 events, speed, UTF-8 payload bytes), written once at the end of `turno.executar` and never failing the turn; read ONLY by platform admins through `/api/studio/agents/{key}/metricas*`; shown only in the agents app (agent page section `metricas`, `frontend/src/pages/studio/tabs/MetricasTab.tsx`; the section is registered in `studio/modelo.py` `SECOES_PAGINA`, tier `plataforma`).
