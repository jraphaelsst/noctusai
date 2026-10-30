# Agents unified model: CONTRACT

**Status:** W0 contract, implemented by S1/S2/S5 on `feat/agents-unified-model` · **Date:** 2026-10-29 · **Base:** `origin/dev@90aabe170` · **Branch-pointer project:** `agents-unified`.
**Builds on:** `products/agents/projects/julia-v2/CONTRACT.md` (the canonical agent model: `definition_scope` plataforma/instancia, `conteudo_modo='linhas'`, the 7 content areas) and roadmap `project-history/roadmaps/product-agents-platform-2026-10.md` (D31: agent internals are superadmin-only, everyone else gets 404).

## 0 · The idea

Every agent lives in the same house. A role agent (Julia, Bia, Renata, ...) and a product guardian are the same kind of thing: a NoctusAI-owned platform entity that each buying org gets an instance of. So there is:

- **one listing**: one card per agent of the caller's org;
- **one page** per agent (`/agentes/:key`), whose sections are rendered from the agent model, never from a per-key shell;
- **one wizard** to create an agent, whose steps are read from the same model.

Out of scope: IsaIA keeps its own pre-v2 content model (it is listed and opens on the same page, but it is not migrated); the academia agent (Bia) stays on the legacy chat runtime until the Renata cutover slice.

## 1 · Decisions

| # | Decision |
|---|---|
| U1 | The agent model is **derived, not hand-written**: the areas are `app.stores.studio_geracoes.AREAS`, each area's fields come from the item model the draft routers and the generator validate with (`app.schemas.studio_geracao.SAIDAS`), the `textos` keys come from `textos_registry.TEXTOS`, the tool names from `ferramentas_registry.FERRAMENTAS_CONHECIDAS`. Only pt-BR titles and the section-visibility table are written by hand, and tests tie them to the derived sets. Code: `backend/app/studio/modelo.py`. |
| U2 | **Origin** of an agent is data: `legado` (`definition_mode='legacy'`: Bia, One Chat) · `plataforma` (the definition, platform org) · `instancia` (an org's instance) · `org` (an org-owned Studio agent such as IsaIA). No route or page branches on an agent key. |
| U3 | **Caller tier**: `plataforma` (`noctus_users.role='admin'`) > `org_admin` (owner/admin of the selected org) > `membro`. A higher tier sees every section of a lower one. |
| U4 | **Internals are superadmin-only (D31)**: the 7 content areas, versions, compiled prompt, knowledge, evaluations. For anyone else the internals route answers **404, never 403**, and `GET /api/studio/modelo` omits the area structure and the wizard. Every internals read is audited (`definicao_lida`). |
| U5 | The section id **equals the pre-unification Studio tab id**, and the page keeps the `?tab=<id>` query, so every existing deep link (`/studio/:key?tab=…&secao=…`) keeps working through a redirect. |
| U6 | The section list is the **page map, not the gate**: every content route keeps enforcing its own tier. |

## 2 · `GET /api/studio/modelo` (S1)

Auth: any org member (`require_member`); 401 unauthenticated, 403 for a non-member role or a product token.

```jsonc
{
  "versao": 1,
  "tier": "membro" | "org_admin" | "plataforma",
  "conteudo_modo": "linhas",
  "origens": ["legado", "plataforma", "instancia", "org"],
  "secoes": [                      // only the sections the caller's tier may ever open
    {"id": "visao-geral", "titulo": "Visão geral", "grupo": "painel|conteudo|operacao|organizacao",
     "tier": "membro", "origens": ["legado", "..."], "area": null, "exige": []}
  ],
  "areas": [                       // [] unless tier == "plataforma"
    {"id": "ferramentas", "titulo": "Ferramentas", "descricao": "…", "ordem": 2, "multiplas_linhas": true,
     "campos": [{"chave": "ferramenta", "rotulo": "Ferramenta", "tipo": "texto|numero|booleano|escolha|lista|objeto",
                 "obrigatorio": true, "max_length": null, "opcoes": null}],
     "enumeracao": {"tipo": "opcoes", "opcoes": ["abrir_skill", "…"]},     // textos: {"tipo":"chaves_por_categoria","grupos":[…]}
     "secoes": ["ferramentas"]}
  ],
  "assistente": {"passos": [ … §6 … ]} // null unless tier == "plataforma"
}
```

`exige` names data facts a section needs: `linhas` / `legado` (content mode), `canais` (`usa_canais`), `dev_advisor` / `runtime` (`kind`), `chat` (an in-app chat runtime: a legacy `claude_sdk` agent, or an org runtime agent off-channel).

## 3 · Page sections (S1 table, rendered by S5)

| id | title | group | tier | origins | area | needs |
|---|---|---|---|---|---|---|
| visao-geral | Visão geral | painel | membro | all | | |
| conversar | Conversar | painel | membro | legado, org | | chat |
| persona | Persona | organizacao | org_admin | legado | | chat |
| especificacoes-org | Especificações da organização | organizacao | org_admin | instancia | | |
| controles | Controles | organizacao | org_admin | instancia | | |
| conversas | Conversas | organizacao | org_admin | instancia, plataforma | | |
| prompt | Prompt | conteudo | plataforma | plataforma, org | secoes | |
| textos · ferramentas · decisoes | (area titles) | conteudo | plataforma | plataforma, org | textos · ferramentas · decisoes | linhas |
| especificacoes | Especificações declaradas | conteudo | plataforma | plataforma, org | specs | linhas |
| biblioteca | Skills da biblioteca | conteudo | plataforma | plataforma, org | skills | linhas |
| skills | Skills | conteudo | plataforma | plataforma, org | skills | legado |
| configuracoes | Configurações | conteudo | plataforma | plataforma, org | configuracoes | |
| qualificacao · conformidade | | operacao | plataforma | plataforma, org | | linhas |
| conhecimento | | operacao | plataforma | org | | |
| clientes | | operacao | plataforma | org | | runtime |
| canais | | operacao | plataforma | plataforma, org | | canais |
| aprendizados | | operacao | plataforma | org | | dev_advisor |
| avaliacoes · versoes | | operacao | plataforma | plataforma, org | | |
| compilado | Prompt compilado | operacao | plataforma | plataforma, org, instancia | | |

## 4 · Painel (S2)

### 4.1 `GET /api/agents/painel` — the unified listing

Any org member. Ensures the legacy rows and the org's platform instances exist first (`ensure_default_agents`, `ensure_instancias`), then returns one card per agent: `{items: AgentePainel[], total}`.

### 4.2 `GET /api/agents/{key}/painel` — one card (the page header)

Any org member; 404 `agent_not_found` for a key the org does not have.

```jsonc
// AgentePainel — display-level only (no instruction, rule, tool description, version or hash)
{
  "key": "julia", "nome": "Julia",
  "descricao": "…",               // catalogue public description, else the agent's own descricao
  "papel": "sdr" | null,          // catalogue role
  "capacidades": ["…"],           // catalogue capability labels
  "origem": "legado|plataforma|instancia|org",
  "tipo": "runtime|dev-advisor", "runtime": "llm|claude_sdk|external", "owner_product": "social-wiring" | null,
  "usa_canais": true, "ativo": true,
  "estado_externo": {"auto_reply_enabled": true} | null, "aviso": "…" | null,   // external agents (One Chat)
  "secoes": ["visao-geral", "especificacoes-org", "controles", "conversas"],     // THIS caller, THIS agent, in order
  "pode_alternar": false          // legado agent + org admin: POST /api/agents/{key}/toggle
}
```

### 4.3 `GET /api/agents/{key}/painel/interno` — superadmin only (D31)

404 `agent_not_found` for every caller that is not a platform admin (org owners included) and for an unknown key. Audited `definicao_lida` (`o_que: "painel_interno"`).

```jsonc
{"key": "isaia", "origem": "org", "definition_scope": "org", "conteudo_modo": "legado",
 "versao_ativa": 3 | null, "tem_rascunho": true, "publicacao_limiar": 0.8 | null,
 "conteudo_status": {"textos_preenchidos": 0, "textos_total": 0, "obrigatorios_faltando": []} | null}
```

## 5 · Key pins removed (S2)

| Before | After |
|---|---|
| `conversations_router.BIA_KEY` (`agent_key` default `"bia"`, `if agent_key == "bia"`) | `AgentRecord.chat_legado` (`definition_mode='legacy' AND runtime='claude_sdk'`) + `legacy_chat_agent(store, org, key)`; no `agent_key` = the org's only legacy chat agent |
| `ConversationCreateRequest.agent_key = "bia"` | `None` (same derivation) |
| `persona_router` prefix `/api/agents/bia/persona` | `/api/agents/{key}/persona`, 404 for a key that is not a legacy chat agent; Bia still answers at `/api/agents/bia/persona` |
| `realtime.conversation_scope` = `agents:bia:conv:<id>` | `agents:conv:<id>` (publisher and SSE subscriber both build it in one function) |
| `Agentes.tsx` `agent.key === "bia" / "one-chat"` checks | painel `origem` / `estado_externo` / `pode_alternar` / `secoes` |
| nav `Bia` + `Catálogo de agentes` items, status_pagina rows `bia`, `agentes-catalogo` | one `Agentes` item; migration 051 drops the two rows |
| detail shells `/bia`, `/agentes/bia/persona`, `/studio/:key` | redirects to `/agentes/:key?tab=…` (generic `/agentes/:key/persona` → `?tab=persona`) |

Renata cutover (2026-10-30) removed the remaining pins: `config.py` `academia_agent_id` / `legacy_chat_max_turns` / `claude_cli_path` / `claude_cli_slots` (the old `BIA_*` / `JULIA_*` env names are still read, with a one-time deprecation log — `NOC-REMEDIATE[drop-bia-env-alias]`; the image keeps `BIA_CLI_SLOTS` and `/run/bia-K`), `get_build_legacy_chat_spec_dep`, the `agente_capacidade` error code, `DEFAULT_AGENT_KEYS = ("one-chat",)` (the code-defined `bia` row is no longer seeded). Credential key `bia_agent_id` → `academia_agent_id` (migration 053; the resolver still falls back to the old row).

## 6 · Wizard step schema (for the wizard slice)

Served in `GET /api/studio/modelo` → `assistente.passos` (platform admins only). Ten short categorized steps; each field is a `(modelo, chave)` pair of the body `POST /api/studio/plataforma/agents` already accepts (`studio_conteudo_router.py:632`, `PlataformaAgentCreateRequest`): `modelo='plataforma'` = a top-level field, `modelo='briefing'` = a field of its `briefing` (`Briefing`). Field type/required/limits/options are read from those Pydantic models.

| # | id | title | category | fields | feeds areas |
|---|---|---|---|---|---|
| 1 | identidade | Identidade | quem | plataforma.key, plataforma.nome, plataforma.descricao | |
| 2 | papel | Papel | quem | briefing.objetivo, briefing.publico, plataforma.padrao_qualificacao, plataforma.escopo_qualificacao | secoes, decisoes |
| 3 | personalidade | Personalidade e tom | quem | briefing.tom_de_voz, briefing.idioma | secoes, textos |
| 4 | conhecimento | Conhecimento | o_que | briefing.exemplos (files are uploaded on the agent page after creation) | secoes, skills |
| 5 | ferramentas | Ferramentas | o_que | none: the AI draft picks from the known tools; reviewed on the page | ferramentas |
| 6 | canais | Canais | como | briefing.canal, plataforma.runtime, plataforma.owner_product | textos, configuracoes |
| 7 | regras | Regras e limites | como | briefing.limites | secoes, decisoes, textos |
| 8 | rotinas | Rotinas | como | none: routines are switched on in each org instance's Controles after publish | |
| 9 | revisao | Revisão | fechamento | none (summary of the answers) | |
| 10 | publicar | Publicar | fechamento | plataforma.instanciavel, plataforma.limite_usd | |

Submit: `POST /api/studio/plataforma/agents` with `{key, nome, descricao, runtime, owner_product, escopo_qualificacao, padrao_qualificacao, instanciavel, limite_usd, briefing: {nome, objetivo, publico, canal, idioma, tom_de_voz, limites, exemplos}}`. The response is the definition (`PlataformaAgentOut`) plus the booked AI generation; the wizard then navigates to `/agentes/:key`. Creating makes a **draft**; publishing a version goes through the eval gate (`POST /draft/publish`), never through the wizard.

Frontend: the wizard is rendered with the seed `JourneyWizard` organ (built in parallel; props `steps[{id, title, category, content}]`, `onComplete`, `progress`): `id`/`title`/`category` come straight from `assistente.passos`, `content` renders the step's `campos`.

## 7 · Frontend (S5)

- `/agentes` — the unified listing: one card per item of `GET /api/agents/painel` (filter by `papel`), each linking to `/agentes/:key`; legacy agents get the on/off switch when `pode_alternar`.
- `/agentes/:key` — `AgentePage`: header from the painel; section nav = `painel.secoes`, titled by `modelo.secoes`; body = the section's renderer (a registry `section id → component`; the content-area renderers are the existing Studio tab components). Superadmin extras come from `/painel/interno`, fetched only when the page shows an internal section.
- States: skeleton only while there is no data yet (`isPending && !data`), a refetch never unmounts the page, error and empty states are explicit; never `isLoading` (KB server-state family).
- Redirects: `/bia`, `/julia`, `/agentes/bia/conversar` → `/agentes/<destino>?tab=conversar` and `/agentes/bia/persona`, `/agentes/julia/persona` → `/agentes/<destino>?tab=persona`, where `<destino>` = `GET /api/agents/painel/destino-chat` (the agent the academia principal names, else the org's code-defined chat agent, else `/agentes`); `/agentes/bia` itself is NOT redirected (the key is free for a new agent); `/agentes/:key/persona` → `/agentes/:key?tab=persona`; `/studio/:key` → `/agentes/:key` (query kept); `/studio/lead-imob` → `/agentes/julia`; `/agentes/catalogo` → `/agentes`.
- `/studio` (Agent Studio) stays as the create/import/delete console until the wizard slice; its rows link to `/agentes/:key`.

## 8 · What the next slices build

- **Wizard slice**: `JourneyWizard` over `assistente.passos`, submit to `POST /api/studio/plataforma/agents`; fold the `/studio` console's create/import/delete actions into `/agentes`.
- **Renata slice** (built, §9): academia tool group, history transfer + retire endpoints, dynamic `/bia` redirects. Left: drop the legacy chat path (`AgentRecord.chat_legado`, `get_build_legacy_chat_spec_dep`, `app/agents/bia/`) once no org has a code-defined chat agent.
- **Bia (marketing) slice**: the key `bia` is free after the cutover's retire step.

## 9 · Renata cutover (built 2026-10-30)

- **Academia tool group (S7).** `app.studio.ferramentas_registry.GRUPOS_FERRAMENTAS["academia"]`: every academia tool is a `ferramentas` content row `academia_<nome>` (the model sees `mcp__academia__<nome>`); a version's active, described rows switch them on. Class (read/write) = `app.runtime.gate`, never the row; write tools never join `allowed_tools` and always go through the approval broker; `claude_sdk` runtime only (`ferramentas_exigem_claude_sdk` otherwise); never on a channel turn (`app.channels.tool_registry.TOOLS` only). Argument validation + audit are the same handlers as the code-defined agent (`app.runtime.tools`).
- **Instances chat.** An org instance of a platform definition with `runtime=claude_sdk` and no channels has the `conversar` section; its conversations live under the instance row, its versions on the definition.
- **`POST /api/agents/{source_key}/transferir-historico`** `{target_key, dry_run=true}` — superadmin only (404 otherwise, 401 without a credential). One transaction (053 `agents.transferir_historico_agente`): conversations (+ messages, approvals, transcripts) and both tokens tables' `principal_agent_id` move; audit `historico_transferido`; idempotent; re-points the `academia_agent_id` credential when it named the source. 409 `origem_invalida` / `destino_invalido` / `mesmo_agente`.
- **`POST /api/agents/{key}/arquivar`** `{dry_run=true, todas_orgs=false}` — superadmin only. `definition_mode='arquivado'`, `ativo=false`, key → `<key>-arquivado-<id8>`; audit `agente_arquivado`; 409 `historico_pendente` while the row owns conversations; archived rows leave every listing.
- **`GET /api/agents/painel/destino-chat`** → `{key, origem: academia|legado}` or 404.
- Runbook: `RENATA-CUTOVER.md`.
