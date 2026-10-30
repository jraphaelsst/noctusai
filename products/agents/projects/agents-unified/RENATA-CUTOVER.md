# Renata cutover — runbook

> **What happens.** The academia agent stops being the code-defined **Bia** (`app/agents/bia/`, `definition_mode='legacy'`) and becomes **Renata**, a Studio agent created with the wizard. Renata gets Bia's in-app history (conversations, messages, approvals, session transcripts), the academia token principal, and the old `/bia` URLs. The code-defined `bia` row is archived, which frees the key `bia` for a future marketing agent.
>
> **Built in:** migration `053_renata_cutover.sql` · `app/stores/cutover.py` · `app/routers/agentes_cutover_router.py` · the academia tool group (`app/studio/ferramentas_registry.py`) · CONTRACT §9.
>
> Every step can be re-run safely. Both writes default to `dry_run: true`, so check the counts before each real run.

## 0 · Preconditions

- The agents image carrying this branch is deployed and `noctus.dev.migrate_product product=agents` has applied **053** (`confirm=True`).
- You are a NoctusAI superadmin (`noctus_users.role='admin'`). Anyone else gets `404` on the cutover routes (D31).
- Env (optional rename): set `ACADEMIA_AGENT_ID` in place of `BIA_AGENT_ID` in `.env` / `.env.fleet`. The old name is still read and logs `agents.config.deprecated_env_name` once. The credential row itself is renamed by 053 (`bia_agent_id` → `academia_agent_id`), and the resolver still falls back to the old row. `BIA_CLI_SLOTS` and `/run/bia-K` stay as they are (they are the image's own contract).

## 1 · Create Renata (wizard, platform org)

`/agentes` → **Novo agente** (wizard, `POST /api/studio/plataforma/agents`):

| Step | Value |
|---|---|
| Identidade | key `renata`, nome `Renata`, descrição "Assistente do projeto Academia de Reciclagem: conhecimento, decisões, trilhas e conteúdo de treinamento." |
| Papel | objetivo / público taken from `app/agents/bia/BIA.md` §Identidade and §O que você faz (a colleague on a knowledge and training-content project; the people on the project are the audience) |
| Personalidade | tom from BIA.md §Postura and §Como você escreve; idioma `pt-BR` |
| Conhecimento | (after creation) upload the `ar-*` skill bodies (`app/agents/bia/plugin/skills/ar-*/SKILL.md`) as skills |
| Ferramentas | see step 2 |
| Canais | **runtime `claude_sdk`**, **no `owner_product`**, no channel (the agent is in-app only) |
| Regras | BIA.md §O que você nunca faz |
| Publicar | `instanciavel = false` (the academia org gets an explicit grant) |

Persona fields that used to live in `agent_personas` (org/project display names) go into the identity section or the org specs.

## 2 · Switch on the academia tool group

On Renata's draft, under **Ferramentas**, add one active row per tool the agent should have, each with a description (a row without a description is not offered):

- read tools: `academia_kb_buscar`, `academia_kb_ler`, `academia_decisao_listar`, `academia_pergunta_listar`, `academia_historico_timeline`, `academia_roadmap_ler`, …
- write tools: `academia_kb_escrever`, `academia_decisao_registrar`, `academia_conteudo_salvar`, …

The full list is `GRUPOS_FERRAMENTAS["academia"].ferramentas`; the content name is the gate name without `mcp__` and with `academia_` in place of `academia__`. Whether a tool reads or writes comes from `app.runtime.gate`, never from the row. A write tool always asks for human approval in the chat (the approval card), which is the same rule Bia had. A tool group only runs on `claude_sdk`: publishing it on `llm` fails with `ferramentas_exigem_claude_sdk`. It is never offered on a WhatsApp/lead channel turn.

Publish (`POST /api/studio/agents/renata/draft/publish`, eval gate).

## 3 · Give the academia org an instance

```
POST /api/studio/plataforma/agents/renata/grants   {"org_id": "<academia org uuid>"}
```

Turn the instance on in the academia org (`/agentes/renata`, on/off). An instance with `claude_sdk` and no channels gets the **Conversar** section.

## 4 · Transfer the history (per academia org)

Run as superadmin, from the academia org's session:

```
POST /api/agents/bia/transferir-historico   {"target_key": "renata"}                    # dry run: counts only
POST /api/agents/bia/transferir-historico   {"target_key": "renata", "dry_run": false}  # real
```

The response has `conversas`, `mensagens`, `aprovacoes`, `transcricoes`, `tokens`, `tokens_academia`, `executado`, and `credencial_academia`:

- `repontado`: `academia_agent_id` named Bia and now names Renata's instance.
- `ja_aponta`
- `nao_aplicavel`: it names another agent. Leave it.
- `seria_repontado`: dry run.
- `falhou`: the history moved but the credential write failed. Set it on **Credenciais**.

What happens in one transaction (`agents.transferir_historico_agente`): conversations (and the messages, approvals and transcripts hanging off them) are re-owned. `principal_agent_id` of `agents.api_tokens` and `academia_de_reciclagem.api_tokens` move to Renata, so the existing `ACADEMIA_API_TOKEN` keeps working (academia's principal check now expects Renata's id). The definition audit row `historico_transferido` is written.

A second run moves nothing (`executado: false`, `conversas: 0`, `ja_aponta`). Errors:

- `409 origem_invalida`: the source is not a code-defined agent of this org.
- `409 destino_invalido`: the target is not a Studio agent of this org.
- `404`: unknown key.

## 5 · Retire the code-defined rows (frees `bia`)

```
POST /api/agents/bia/arquivar   {"todas_orgs": true}                    # dry run: linhas, com_historico
POST /api/agents/bia/arquivar   {"todas_orgs": true, "dry_run": false}
```

Each row becomes `definition_mode='arquivado'`, `ativo=false`, key `bia-arquivado-<id8>`, audited as `agente_arquivado`, and leaves every listing. The response is `409 historico_pendente` while any row still owns a conversation: run step 4 for that org first (`com_historico` tells you how many orgs). The code no longer seeds `bia` (`DEFAULT_AGENT_KEYS = ("one-chat",)`), so the key stays free. A new agent can be created as `bia`.

## 6 · Verify

- `GET /api/agents/painel/destino-chat` (as an academia member) → `{"key": "renata", "origem": "academia"}`.
- `/bia`, `/julia`, `/agentes/bia/persona`, `/agentes/bia/conversar` land on `/agentes/renata?tab=…`. `/agentes/bia` itself is NOT redirected (that key is free).
- In Renata's Conversar, the old conversations are listed. A write request shows the approval card, and approving it writes to academia.
- `/agentes` shows no Bia card.
- `noctus.dev.deploy_verify products=["agents"]` and `noctus.dev.spa_smoke products=["agents"]`.

## 7 · Rollback

Everything is a data move, so nothing is dropped:

- Re-transfer with source and target swapped. This first needs the archived row back to `legacy` (SQL by hand, as superadmin; the function accepts an `arquivado` source but only a `studio` target, so the reverse is a manual `UPDATE agents.conversations SET agent_id = <bia id> WHERE agent_id = <renata id>`).
- Restore the key with `UPDATE agents.agents SET key='bia', definition_mode='legacy', ativo=true WHERE id=<bia id>`.
- Set `academia_agent_id` back on **Credenciais**.
- Do this before a new `bia` agent is created.

## Left for later

- Drop the legacy chat path (`AgentRecord.chat_legado`, `get_build_legacy_chat_spec_dep`, `app/agents/bia/`, the `BIA_*` env aliases `NOC-REMEDIATE[drop-bia-env-alias]`) once no org has a code-defined chat agent.
- The seed `domain/ai/tool_audit` is not used by the agents product. Academia tool calls are audited by the academia side (signed approval assertion) plus `agent_approvals`, the same as before the cutover.
